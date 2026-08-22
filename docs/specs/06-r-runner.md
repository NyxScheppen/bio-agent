# R 子进程执行器

> 范围：`bioagent/r_runner.py`（`RRunner` + `RRuntimeError`）。用 `Rscript` 子进程跑服务端固定 R 脚本，JSON 走 stdin/stdout，`shell=False`。
> 纯基础设施 spec：只管「跑 R 脚本 → 返回 JSON」，不含任何具体 R 脚本内容（那是 11-15 spec 的活）、不含 Facade、不含 API。
> `RRunner` / `RRuntimeError` 定义内联在本文件；`scripts_dir` 取自 02-config 的 `storage.r_scripts_dir`（由组合根传入，非本 spec import）。

## 元信息

- **前置依赖**：01-types（`ToolDefinition.r_script` 语义对应脚本名，但 `r_runner.py` **不 import** 任何 `bioagent` 模块）

## 用户故事

> 作为 bio agent 系统的开发者，我想要一个共享的 R 子进程执行器——R 工具只声明脚本名、executor 持 runner 跑、参数与结果 JSON 化、失败带 stderr 上抛，以便所有 R 分析（DGE/富集/生存/网络）走同一条执行路、不重复 subprocess 样板。

## 验收标准

- [ ] `bioagent/r_runner.py` 含 `RRunner` + `RRuntimeError`，与「`bioagent/r_runner.py`（完整）」段代码逐字一致
- [ ] `run(script_name, args)` 用 `asyncio.create_subprocess_exec` 以 `["Rscript", script_path]` 列表调用（**`shell=False`**），`script_path = os.path.join(scripts_dir, script_name)`
- [ ] args 以 JSON 字节经 stdin 传入（`json.dumps(args).encode("utf-8")`），结果从 stdout 解析为 `dict`
- [ ] 非零退出码 → `RRuntimeError`（携带 stderr 文本）；stdout 非合法 JSON / 非对象 → `RRuntimeError`；`Rscript` 缺失（`FileNotFoundError`）→ `RRuntimeError`
- [ ] `pyright` strict 零报错

## 技术方案

- **新文件**：`bioagent/r_runner.py`（无 Facade、无 API、无数据变更）
- **公开面**：`from bioagent.r_runner import RRunner, RRuntimeError`（不加 `__all__`）
- **谁持有 runner**：`RRunner` 在组合根（`main.py`，归 10-api）用 `config.storage.r_scripts_dir` 构造一次，注入 09-orchestration 的 executor。R 工具（11-15）的 `ToolDefinition` 只声明 `r_script` 脚本名，`run=None`——不自己碰 subprocess（见 01-types / 05-tools 的 runtime 契约）
- **为什么列表调用**：`create_subprocess_exec("Rscript", script_path, ...)` 直接传参数列表，不经 shell 解析，防命令注入（`how-security.md` 的 R 子进程安全）
- **JSON 契约（R 脚本侧）**：脚本读参数 `args <- jsonlite::fromJSON(file("stdin"))`，算完写 `cat(jsonlite::toJSON(result, auto_unbox = TRUE))` 到 stdout。依赖 `jsonlite`（Docker 镜像预装，非本 spec 管）
- **不做**：不设超时/重试（R 分析时长不定，超时策略留给编排层按需加）；不管理 R 包安装（镜像层职责）；不接受任何用户提供的 R 代码——脚本名是服务端注册表里的固定值

### `bioagent/r_runner.py`（完整）

```python
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
            data = json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RRuntimeError(
                f"{script_name} 输出非合法 JSON：{stdout.decode('utf-8', 'replace')[:200]}"
            ) from exc
        if not isinstance(data, dict):
            raise RRuntimeError(
                f"{script_name} 输出必须是 JSON 对象，得到 {type(data).__name__}"
            )
        return cast(dict[str, Any], data)
```

## 测试要点

- [ ] 单元测试 `tests/test_r_runner/`（`pytest-asyncio`，`monkeypatch` `asyncio.create_subprocess_exec` 返回 fake process）：
  - [ ] `script_path` 拼接：fake process 捕获命令，断言首元素 `"Rscript"`、第二元素 = `os.path.join(scripts_dir, script_name)`
  - [ ] args JSON 传入：fake `communicate` 记录 input，断言 `== json.dumps(args).encode("utf-8")`
  - [ ] 成功路径：fake 返回 `returncode=0`、`stdout=b'{"a": 1}'` → `run()` 返回 `{"a": 1}`
  - [ ] 非零退出：fake 返回 `returncode=1`、`stderr=b"Error in ..."` → `RRuntimeError`，消息含 stderr 文本
  - [ ] stdout 非 JSON：fake 返回 `returncode=0`、`stdout=b"not json"` → `RRuntimeError`
  - [ ] stdout 非对象：fake 返回 `returncode=0`、`stdout=b'[1,2,3]'` → `RRuntimeError`
  - [ ] Rscript 缺失：`create_subprocess_exec` 抛 `FileNotFoundError` → `RRuntimeError`
- [ ] 集成测试：无（不真跑 Rscript，测试不依赖真实 R 环境）
- [ ] E2E 测试：无

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] `test-inventory.md` 已更新
- [ ] 09-orchestration 的 executor 用 `RRunner` 执行 `runtime==R` 的工具；11-15 的 R 工具不再出现 `subprocess`/`create_subprocess` 代码
