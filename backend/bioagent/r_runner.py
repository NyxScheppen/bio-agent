import asyncio
import json
import os
from typing import Any, cast


class RRuntimeError(Exception):
    """R 脚本执行失败（Rscript 缺失 / 非零退出 / 输出非 JSON）。"""


class RRunner:
    """R 子进程执行器：Rscript + JSON 走 stdin/stdout，shell=False。

    由 09-orchestration 的 executor 持有并注入；R 工具只声明 r_script 脚本名。
    """

    def __init__(self, scripts_dir: str) -> None:
        self._scripts_dir = scripts_dir

    async def run(self, script_name: str, args: dict[str, Any]) -> dict[str, Any]:
        script_path = os.path.join(self._scripts_dir, script_name)
        try:
            proc = await asyncio.create_subprocess_exec(
                "Rscript",
                script_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RRuntimeError("Rscript 未安装或不在 PATH 中") from exc
        payload = json.dumps(args).encode("utf-8")
        stdout, stderr = await proc.communicate(payload)
        if proc.returncode != 0:
            raise RRuntimeError(
                f"{script_name} 失败（exit {proc.returncode}）："
                f"{stderr.decode('utf-8', 'replace').strip()}"
            )
        try:
            data = json.loads(stdout.decode("utf-8", "replace"))
        except json.JSONDecodeError as exc:
            raise RRuntimeError(
                f"{script_name} 输出非合法 JSON：{stdout.decode('utf-8', 'replace')[:200]}"
            ) from exc
        if not isinstance(data, dict):
            raise RRuntimeError(
                f"{script_name} 输出必须是 JSON 对象，得到 {type(data).__name__}"
            )
        return cast(dict[str, Any], data)
