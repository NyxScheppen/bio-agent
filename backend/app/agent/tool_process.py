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


@dataclass
class ToolProcessOutcome:
    result: Any = None
    error: str = ""
    timed_out: bool = False
    cancelled: bool = False
    worker_pid: Optional[int] = None
    tree_terminated: bool = False


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
        recv_conn.close()
        if process.is_alive() and not (outcome.timed_out or outcome.cancelled):
            outcome.tree_terminated = _terminate_process_tree(process)
