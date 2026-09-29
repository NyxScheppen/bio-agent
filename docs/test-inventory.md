# 测试清单

## Multi-Agent 系统

阶段：多 Agent 稳定性修复

| 测试 | 方向 | 检查内容 |
|---|---|---|
| `test_execution_mode_alias` | 回归保护 | 历史 `direct_answer` 与未知执行模式的归一化 |
| `test_router_and_planner_errors_fall_back_safely` | 回归保护 | Router/Planner LLM 错误进入安全追问模式 |
| `test_delegator_converts_ids_to_task_indexes` | 功能正确 | Planner step ID、依赖和结果引用转换为子任务索引 |
| `test_orchestrator_preserves_planner_parameters` | 回归保护 | Planner 参数和字符串依赖键进入 Orchestrator |
| `test_delegated_tasks_reach_sub_agent_manager` | 功能正确 | Delegator 结果实际进入 SubAgentManager |
| `test_sub_agent_invalid_and_cyclic_dependencies_are_blocked` | 边界鲁棒 | 越界、自锁和循环依赖不会死循环 |
| `test_sub_agent_failure_blocks_dependents` | 功能正确 | 上游失败后下游工具不会启动 |
| `test_sub_agent_retry_and_runtime` | 功能正确 | 重试上限、超时透传、尝试次数和运行时统计 |
| `test_parallel_groups_and_cycle_validation` | 边界鲁棒 | 并行组生效，循环依赖被拒绝 |
| `test_parallel_failure_blocks_downstream` | 回归保护 | 并行批次中的失败级联阻断 |
| `test_parallel_step_rejects_missing_parameters` | 边界鲁棒 | 确定性执行拒绝缺失的结构化参数 |
| `test_nested_step_references_are_strict` | 边界鲁棒 | 嵌套 `$step_N` 解析和未知引用失败 |
| `test_racing_returns_first_success` | 功能正确 | Waterfall Racing 在首个成功结果后提前返回 |
| `test_racing_filters_incompatible_signatures` | 边界鲁棒 | 同竞速组但参数签名不兼容的工具被排除 |
| `test_async_entry_does_not_block_event_loop` | 回归保护 | 同步 Agent 流水线不会阻塞 ASGI 事件循环 |
