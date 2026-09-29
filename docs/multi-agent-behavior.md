# Multi-Agent 行为契约

本文档描述 BioAI Agent 多 Agent 流水线的实际运行语义。它是 Router、Planner、Delegator、Executor、Orchestrator、SubAgentManager 和 Reporter 之间的维护契约。

## 1. 主流程

```text
HTTP request
  -> run_bio_agent()                    # asyncio.to_thread，不阻塞 ASGI 事件循环
  -> Router                             # 分类、复杂度、执行模式
  -> Skill Selector
  -> Planner                            # 步骤、参数、依赖、并行组
  -> Delegator?                         # 仅复杂且至少 3 步，并受 feature flag 控制
     -> Orchestrator -> SubAgentManager # 委派路径
     -> Executor                        # 未委派路径
        -> dependency-aware executor    # 有依赖或并行组
        -> LLM tool loop                # 普通串行路径
  -> Reporter
  -> POST_AGENT_TURN hook
```

`run_bio_agent()` 是异步 Facade，但 Router、Planner、工具和 Reporter 仍是同步实现。Facade 将整条同步流水线放入工作线程，避免阻塞 FastAPI 事件循环。

## 2. 执行模式

合法模式只有三种：

| 模式 | 行为 |
|---|---|
| `answer_only` | 不执行工具，直接调用 Reporter 生成回答 |
| `tool_execution` | 进入委派或 Executor 路径 |
| `ask_user` | 返回追问，不执行工具 |

历史值 `direct_answer` 会归一化为 `answer_only`。未知或缺失值默认使用 `tool_execution`。

Router 或 Planner 的 LLM 调用报错、返回空对象或无法解析时，不再把 `{"error": ...}` 当作正常计划。Router 降级为 `ask_user`；Planner 根据 Router 的安全模式生成空步骤 fallback。

## 3. Planner 输出契约

```json
{
  "execution_mode": "tool_execution",
  "steps": [
    {
      "step_id": 1,
      "goal": "探测文件",
      "preferred_tools": ["probe_data_file"],
      "parameters": {"file_path": "uploads/input.csv"},
      "parameter_strategy": "从上传上下文取得 file_path",
      "success_criteria": "识别列名和文件格式"
    },
    {
      "step_id": 2,
      "goal": "分析数据",
      "preferred_tools": ["analysis_tool"],
      "parameters": {"input_file": "$step_1"},
      "parameter_strategy": "使用步骤 1 的第一个输出文件"
    }
  ],
  "step_dependencies": {"2": [1]},
  "parallel_groups": []
}
```

约束：

- `step_id` 在单个计划中必须唯一且可转成整数。
- `parameters` 必须是能直接传给工具的 JSON 对象。`parameter_strategy` 只供 LLM 解释，执行器不会解析自然语言参数。
- `step_dependencies` 的键和值都是 `step_id`。JSON 字符串键和 Python 整数键都可接受。
- `parallel_groups` 是允许并发的 `step_id` 列表。一个步骤不能出现在多个并行组。
- 依赖关系优先于并行组；同组中互相依赖的步骤仍会被拆到不同拓扑批次。
- 未知、重复、自依赖和循环依赖都会使并行计划失败，不会偷偷退化为串行执行。

## 4. 步骤结果引用

参数中的精确字符串 `$step_N` 引用步骤 `N` 的结果。字典和列表中的嵌套引用也会递归解析。

解析顺序：

1. 前置步骤必须存在且状态为 `success`。
2. 有输出文件时，使用第一个文件的 `relative_path`，其次使用 `url`。
3. 没有文件时，使用 `result_summary`。
4. 引用不存在、前置步骤失败或没有可传递结果时，当前步骤标记为 `blocked`。

引用只在整个字符串等于 `$step_N` 时生效；`"prefix-$step_1"` 不会被替换。

## 5. Delegator 和子 Agent

只有同时满足以下条件才调用 Delegator：

- `FEATURE_FLAGS["sub_agent_delegation"]` 为 `True`；
- Router 复杂度为 `complex`；
- Planner 至少生成 3 个步骤。

Delegator 输出的 `sub_tasks` 使用零基索引声明 `depends_on`。系统在执行前校验：

- 子任务必须是对象；
- `tool` 必须已注册；
- `args` 必须是对象；
- `depends_on` 必须是列表，只能引用现有索引，不能依赖自身。

任一子任务无效时，本轮委派整体拒绝，回到普通 Executor 路径。Planner 步骤转换成子任务时，原始 `step_id` 和 `$step_N` 会一起映射为零基子任务索引。

## 6. 调度和状态传播

Orchestrator 使用以下状态机：

```text
TODO -> IN_PROGRESS -> DONE
                    -> FAILED
TODO ----------------> BLOCKED
```

SubAgentResult 状态包括 `success`、`partial`、`error`、`timeout` 和 `blocked`。只有 `success` 能解除下游依赖；其他状态都会令依赖任务进入 `blocked`。

| 边缘情况 | 行为 |
|---|---|
| 空任务列表 | 立即返回空结果 |
| 工具未注册 | 当前任务 `error` |
| 依赖索引越界或依赖自身 | 当前任务 `blocked` |
| 前置任务失败、部分成功或超时 | 下游任务 `blocked`，工具不会启动 |
| 循环依赖 | 环中的待执行任务全部 `blocked` |
| 未知 Orchestrator 任务 ID | 当前任务 `blocked` |
| 多个独立任务 | 最多 `max_workers` 个并发执行 |
| 并发完成顺序不同 | 对外结果仍按 Planner/子任务顺序返回 |

子 Agent 会使用独立会话名：`<parent_session>_sub_<index>`。

## 7. 重试和超时

`SubAgentTask` 默认 `max_retries=1`，即首次执行失败后最多再执行一次；允许范围为 0 到 3。`timeout` 范围为 10 到 3600 秒，默认 600 秒。

重试具有至少一次执行语义。可能产生外部副作用的工具应设置 `max_retries=0`，或者由工具自身实现幂等键。只有最终结果会写入 SubAgentResult，`attempts` 记录实际尝试次数。

Python 线程无法被安全强杀。超时后生命周期包装器会立即停止等待、取消尚未开始的 Future 并返回 `timeout/error`；已经运行的线程可能继续到工具函数自行结束。调用外部进程、网络或 R 的工具仍必须实现自身的进程级或请求级超时。

## 8. 依赖感知并行

Executor 仅在 `parallel_execution` 开启并且计划包含 `step_dependencies` 或 `parallel_groups` 时进入确定性并行路径。否则使用原有 LLM 工具循环。

执行器先做拓扑分层，再使用 `parallel_groups` 限制每层内允许同时启动的步骤。未列入并行组的步骤保持单独批次。每个批次结束后才会启动下一批次。

`parameters` 缺失或不是对象时，步骤返回 `invalid_parameters`，不会以空参数猜测执行。

## 9. Waterfall Racing

竞速只发生在确定性并行执行的单个步骤内部，并同时满足：

- `waterfall_racing` 开启；
- 至少两个可见工具具有相同 `racing_group`；
- 所有候选工具的函数签名都能接受同一组参数。

第一个返回 `success` 的工具成为 winner，调用方立即继续。尚未开始的候选会被取消；已运行的 Python 线程无法强制终止，状态记为 `running`，可能在后台完成。没有成功结果时，执行器使用第一个完成的失败结果作为诊断 fallback，不会伪造成功。

参数签名不兼容的同组工具不会竞速。例如一个工具要求 `expression_file`，另一个要求 `count_file`，除非 Planner 提供的参数同时满足两者，否则只执行首选工具。

## 10. Feature Flags

| Flag | 默认值 | 控制范围 |
|---|---:|---|
| `parallel_execution` | `True` | 是否启用确定性依赖/并行执行入口 |
| `waterfall_racing` | `True` | 并行步骤内是否尝试兼容工具竞速 |
| `sub_agent_delegation` | `True` | 复杂任务是否调用 Delegator |

关闭 Delegator 不影响 Planner 和普通 Executor。关闭并行执行时，即使 Planner 输出并行元数据，也会走原有 LLM Executor。关闭竞速只影响候选工具选择，不影响步骤调度。

## 11. 输出和报告

委派路径和普通 Executor 都转换为同一协议：

```json
{
  "executor_text": "执行摘要",
  "tool_observations": [],
  "output_files": []
}
```

Reporter 只基于真实 observation 和文件生成最终回复。任务失败或阻塞仍会进入 Reporter，使最终回答能够说明未完成原因。所有输出文件在返回前按 URL、相对路径和名称去重。

无论主流程成功、追问、直接回答还是抛出异常，异步 Facade 最终都会触发 `POST_AGENT_TURN` Hook。

## 12. 维护要求

修改多 Agent 协议时至少运行：

```powershell
python backend/tests/test_multi_agent.py
python -m pytest backend/tests
ruff check backend/app/agent backend/tests/test_multi_agent.py
pyright backend/app/agent backend/tests/test_multi_agent.py
```

新增字段时必须同步修改 Planner prompt、本行为文档和 `backend/tests/test_multi_agent.py`。不要让 LLM prompt 与执行器读取的字段名再次分叉。
