# Multi-Agent 修复计划

状态：已实施

## 目标

使委派、依赖调度、确定性并行和工具竞速形成可执行、可失败、可测试的闭环，同时保持原有 Router -> Planner -> Executor -> Reporter 串行路径兼容。

## 边缘情况分析

| 范围 | 边缘情况 | 预期行为 |
|---|---|---|
| LLM 输出 | 调用异常、空对象、`{"error": ...}` | 进入安全 fallback，不把错误对象当计划 |
| 执行模式 | 历史 `direct_answer`、未知值 | 分别归一化为 `answer_only`、`tool_execution` |
| Planner | 参数缺失或仍是自然语言策略 | 确定性执行拒绝步骤，不用 `{}` 猜测调用 |
| 依赖 | 字符串键、非连续 step ID | 统一转为整数并按 ID 调度 |
| 依赖 | 重复 ID、未知 ID、自依赖、循环 | 明确拒绝或标记 `blocked`，不得死循环 |
| 失败传播 | 上游 `error`、`partial`、`timeout` | 下游 `blocked`，工具不得启动 |
| 并发 | 完成顺序不稳定 | 对外结果保持 Planner 顺序 |
| 引用 | 嵌套 `$step_N`、无文件结果、未知步骤 | 递归解析；无法解析时阻塞当前步骤 |
| 委派 | 工具不存在、参数/依赖类型错误 | 整体拒绝该委派计划，回退普通 Executor |
| 重试 | 有副作用的工具被重复执行 | 提供明确上限；此类任务应设置 `max_retries=0` |
| 超时 | Future 已经开始运行 | 停止等待但不承诺强杀线程，依赖工具自身超时 |
| 竞速 | 同组工具参数签名不同 | 仅保留能接受同一参数对象的候选 |
| 竞速 | 快工具成功、慢工具仍运行 | 立即返回 winner；取消未启动任务并记录运行中 loser |
| ASGI | 同步 LLM/工具阻塞事件循环 | 整条同步 Agent 流水线放入工作线程 |
| Hook | 开关关闭、主流程异常 | 尊重开关；开启时最终触发 `POST_AGENT_TURN` |

## 实施阶段

1. 协议统一
   - 统一执行模式。
   - Planner 输出结构化 `parameters`、`step_dependencies` 和 `parallel_groups`。
   - Router/Planner 错误进入安全 fallback。

2. 委派闭环
   - 接入 Delegator import。
   - 校验子任务并交给 Orchestrator/SubAgentManager。
   - 将结果转换回统一 Executor 协议。

3. 调度正确性
   - 增加依赖规范化、拓扑校验和无进展退出。
   - 实现失败级联阻断、稳定结果顺序、重试/超时/运行时统计。

4. 并行与竞速
   - 让 `parallel_groups` 真正参与分批。
   - 严格解析 `$step_N`。
   - 按参数签名筛选竞速候选，并在首个成功时提前返回。

5. 异步和生命周期
   - 将同步流水线移出 FastAPI 事件循环。
   - 修正 PRE/POST Tool Hook 时序，补触发 `POST_AGENT_TURN`。

6. 验证与文档
   - 新增 `backend/tests/test_multi_agent.py`。
   - 更新测试清单。
   - 编写 `docs/multi-agent-behavior.md` 作为长期行为契约。

## 验收条件

- 多 Agent 专项测试全绿。
- 相关文件 `ruff check` 零错误。
- 相关文件 `pyright` 零错误。
- Python 编译检查通过。
- 全仓测试除已识别、与本修改无关的基线问题外无新增失败。
- 行为文档明确失败传播、超时和竞速不能强杀线程的边界。
