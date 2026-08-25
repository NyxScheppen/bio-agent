import asyncio
import json
import os
from typing import Any

import pytest

from bioagent.r_runner import RRuntimeError, RRunner


class _FakeProcess:
    def __init__(
        self,
        returncode: int = 0,
        stdout: bytes = b"{}",
        stderr: bytes = b"",
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.input: bytes | None = None

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        self.input = input
        return self.stdout, self.stderr


def _install_fake(
    monkeypatch: pytest.MonkeyPatch, process: _FakeProcess
) -> list[tuple[Any, ...]]:
    captured: list[tuple[Any, ...]] = []

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProcess:
        captured.append(args)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return captured


async def test_script_path_joined(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _FakeProcess()
    captured = _install_fake(monkeypatch, process)
    runner = RRunner("/srv/scripts")
    await runner.run("dge.R", {"x": 1})
    args = captured[0]
    assert args[0] == "Rscript"
    assert args[1] == os.path.join("/srv/scripts", "dge.R")


async def test_args_json_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _FakeProcess()
    _install_fake(monkeypatch, process)
    runner = RRunner("/srv/scripts")
    await runner.run("dge.R", {"genes": ["a", "b"]})
    assert process.input == json.dumps({"genes": ["a", "b"]}).encode("utf-8")


async def test_serialize_failure_does_not_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    # payload 在 spawn 之前序列化：args 不可 JSON 化时不得起子进程
    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProcess:
        raise AssertionError("create_subprocess_exec must not be called")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    runner = RRunner("/srv/scripts")
    with pytest.raises(TypeError):
        await runner.run("dge.R", {"x": object()})


async def test_success(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _FakeProcess(returncode=0, stdout=b'{"a": 1}')
    _install_fake(monkeypatch, process)
    runner = RRunner("/srv/scripts")
    result = await runner.run("dge.R", {})
    assert result == {"a": 1}


async def test_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _FakeProcess(returncode=1, stderr=b"Error in eval(expr): ...")
    _install_fake(monkeypatch, process)
    runner = RRunner("/srv/scripts")
    with pytest.raises(RRuntimeError) as exc:
        await runner.run("dge.R", {})
    assert "Error in eval" in str(exc.value)


async def test_non_json_stdout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _FakeProcess(returncode=0, stdout=b"not json")
    _install_fake(monkeypatch, process)
    runner = RRunner("/srv/scripts")
    with pytest.raises(RRuntimeError):
        await runner.run("dge.R", {})


async def test_invalid_utf8_stdout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _FakeProcess(returncode=0, stdout=b"\xff\xfe")
    _install_fake(monkeypatch, process)
    runner = RRunner("/srv/scripts")
    with pytest.raises(RRuntimeError):
        await runner.run("dge.R", {})


async def test_non_object_stdout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _FakeProcess(returncode=0, stdout=b"[1,2,3]")
    _install_fake(monkeypatch, process)
    runner = RRunner("/srv/scripts")
    with pytest.raises(RRuntimeError):
        await runner.run("dge.R", {})


async def test_rscript_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProcess:
        raise FileNotFoundError("No such file")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    runner = RRunner("/srv/scripts")
    with pytest.raises(RRuntimeError):
        await runner.run("dge.R", {})
