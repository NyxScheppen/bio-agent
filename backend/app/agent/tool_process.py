"""Killable process boundary for individual tool calls."""

from __future__ import annotations

import multiprocessing
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import Any, Callable, Dict, Optional

try:
    import cloudpickle
except ImportError:  # pragma: no cover - compatibility with older environments
    from joblib.externals import cloudpickle

try:
    import psutil
except ImportError:  # pragma: no cover - optional hardening dependency
    psutil = None


PROCESS_EXIT_GRACE_SECONDS = 0.5
PROCESS_KILL_GRACE_SECONDS = 1.0
PROCESS_POLL_INTERVAL_SECONDS = 0.05
PROCESS_SAMPLE_INTERVAL_SECONDS = 0.2


@dataclass
class ToolProcessOutcome:
    result: Any = None
    error: str = ""
    timed_out: bool = False
    cancelled: bool = False
    worker_pid: Optional[int] = None
    tree_terminated: bool = False
    peak_memory_mb: Optional[float] = None
    avg_cpu_percent: Optional[float] = None


def _tool_process_entry(send_conn: Connection, payload: bytes) -> None:
    """Deserialize and execute a tool inside its isolated worker process."""
    if os.name != "nt":
        try:
            os.setsid()
        except OSError:
            pass

    try:
        func, function_args = cloudpickle.loads(payload)
        try:
            raw_result = func(**function_args)
            envelope = {"kind": "result", "payload": raw_result}
            response = cloudpickle.dumps(envelope)
        except BaseException as exc:
            response = cloudpickle.dumps({
                "kind": "error",
                "message": f"{type(exc).__name__}: {exc}",
            })

        try:
            send_conn.send_bytes(response)
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        send_conn.close()


def _snapshot_descendants(pid: int) -> list[Any]:
    if psutil is None:
        return []
    try:
        return psutil.Process(pid).children(recursive=True)
    except (psutil.Error, OSError):
        return []


def _sample_worker_tree(pid: int, stop_event: threading.Event, samples: list) -> None:
    """Periodically record (rss_mb, cpu_percent) of a process tree until stopped.

    Process 对象必须跨采样轮复用：`cpu_percent(interval=None)` 依赖上一次对同一
    实例的调用作基线，每轮重建实例会让每次读数都退化为 0。
    """
    if psutil is None:
        return
    try:
        root = psutil.Process(pid)
    except (psutil.Error, OSError):
        return

    procs: dict[int, Any] = {root.pid: root}
    for child in root.children(recursive=True):
        procs.setdefault(child.pid, child)
    for p in procs.values():
        try:
            p.cpu_percent(interval=None)  # establish baseline; first read is 0
        except (psutil.Error, OSError):
            pass

    while not stop_event.is_set():
        stop_event.wait(PROCESS_SAMPLE_INTERVAL_SECONDS)
        # 刷新后起的子进程（如 worker 内再 spawn 的 Rscript）
        try:
            for child in root.children(recursive=True):
                if child.pid not in procs:
                    procs[child.pid] = child
                    try:
                        child.cpu_percent(interval=None)
                    except (psutil.Error, OSError):
                        pass
        except (psutil.Error, OSError):
            pass

        rss = 0.0
        cpu = 0.0
        dead: list[int] = []
        for p in procs.values():
            try:
                rss += p.memory_info().rss
                cpu += p.cpu_percent(interval=None)
            except (psutil.Error, OSError):
                dead.append(p.pid)
        for d in dead:
            procs.pop(d, None)
        if procs:
            samples.append((rss / (1024 * 1024), cpu))


def _summarize_samples(samples: list) -> tuple[Optional[float], Optional[float]]:
    """Reduce samples to (peak_memory_mb, avg_cpu_percent)."""
    if not samples:
        return None, None
    peak = max(s[0] for s in samples)
    avg_cpu = sum(s[1] for s in samples) / len(samples)
    return round(peak, 2), round(avg_cpu, 1)


def _terminate_process_tree(process: BaseProcess) -> bool:
    """Force-stop the worker and descendants, then verify they exited."""
    pid = process.pid
    if pid is None:
        return not process.is_alive()

    descendants = _snapshot_descendants(pid)

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                check=False,
                timeout=PROCESS_KILL_GRACE_SECONDS,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass

    if process.is_alive():
        process.kill()

    if psutil is not None and descendants:
        for child in descendants:
            try:
                child.kill()
            except (psutil.Error, OSError):
                pass
        try:
            _, alive = psutil.wait_procs(
                descendants,
                timeout=PROCESS_KILL_GRACE_SECONDS,
            )
        except (psutil.Error, OSError):
            alive = descendants
    else:
        alive = []

    process.join(timeout=PROCESS_KILL_GRACE_SECONDS)
    return not process.is_alive() and not any(
        child.is_running() for child in alive
    )


def run_tool_in_subprocess(
    func: Callable[..., Any],
    function_args: Dict[str, Any],
    timeout_seconds: float,
    cancellation_event: Optional[threading.Event] = None,
) -> ToolProcessOutcome:
    """Run one tool in a spawn process that can be killed on timeout."""
    try:
        payload = cloudpickle.dumps((func, function_args))
    except Exception as exc:
        return ToolProcessOutcome(
            error=f"工具调用无法序列化: {type(exc).__name__}: {exc}",
        )

    context = multiprocessing.get_context("spawn")
    recv_conn, send_conn = context.Pipe(duplex=False)
    process = context.Process(
        target=_tool_process_entry,
        args=(send_conn, payload),
        name="bio-tool-worker",
    )

    try:
        process.start()
    except Exception as exc:
        recv_conn.close()
        send_conn.close()
        return ToolProcessOutcome(
            error=f"工具执行进程启动失败: {type(exc).__name__}: {exc}",
        )
    finally:
        send_conn.close()

    outcome = ToolProcessOutcome(worker_pid=process.pid)

    # 后台采样 worker 进程树的内存/CPU，得到工具本身的资源消耗。
    samples: list = []
    stop_sampling = threading.Event()
    sampler = None
    if psutil is not None and process.pid is not None:
        sampler = threading.Thread(
            target=_sample_worker_tree,
            args=(process.pid, stop_sampling, samples),
            name="bio-tool-sampler",
            daemon=True,
        )
        sampler.start()

    deadline = time.monotonic() + max(0.0, timeout_seconds)

    try:
        while True:
            if cancellation_event is not None and cancellation_event.is_set():
                outcome.cancelled = True
                outcome.tree_terminated = _terminate_process_tree(process)
                return outcome

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                outcome.timed_out = True
                outcome.tree_terminated = _terminate_process_tree(process)
                return outcome

            if recv_conn.poll(min(PROCESS_POLL_INTERVAL_SECONDS, remaining)):
                try:
                    envelope = cloudpickle.loads(recv_conn.recv_bytes())
                except EOFError:
                    process.join(timeout=PROCESS_EXIT_GRACE_SECONDS)
                    outcome.error = (
                        "工具执行进程未返回结果"
                        f"（exit_code={process.exitcode}）"
                    )
                    return outcome
                except Exception as exc:
                    outcome.error = (
                        "工具执行结果无法反序列化: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    return outcome

                process.join(timeout=PROCESS_EXIT_GRACE_SECONDS)
                if process.is_alive():
                    outcome.tree_terminated = _terminate_process_tree(process)

                if envelope.get("kind") == "result":
                    outcome.result = envelope.get("payload")
                else:
                    outcome.error = str(
                        envelope.get("message") or "工具执行进程返回未知错误"
                    )
                return outcome

            if not process.is_alive():
                process.join(timeout=PROCESS_EXIT_GRACE_SECONDS)
                outcome.error = (
                    "工具执行进程异常退出且未返回结果"
                    f"（exit_code={process.exitcode}）"
                )
                return outcome
    finally:
        stop_sampling.set()
        if sampler is not None:
            sampler.join(timeout=PROCESS_KILL_GRACE_SECONDS)
        outcome.peak_memory_mb, outcome.avg_cpu_percent = _summarize_samples(samples)
        recv_conn.close()
        if process.is_alive() and not (outcome.timed_out or outcome.cancelled):
            outcome.tree_terminated = _terminate_process_tree(process)
