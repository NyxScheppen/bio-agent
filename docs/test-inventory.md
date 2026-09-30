# 测试清单

## Multi-Agent 系统

阶段：多 Agent 稳定性修复

| 测试 | 方向 | 检查内容 |
|---|---|---|
| `test_execution_mode_alias` | 回归保护 | 历史 `direct_answer` 与未知执行模式的归一化 |
| `test_router_and_planner_errors_fall_back_safely` | 回归保护 | Router/Planner LLM 错误进入安全追问模式 |
| `test_delegator_converts_ids_to_task_indexes` | 功能正确 | Planner step ID、依赖和结果引用转换为子任务索引 |
| `test_delegator_preserves_parallel_group_allowlist` | 回归保护 | 委派路径将并行白名单转换为批次屏障 |
| `test_orchestrator_schedule_barrier_does_not_cascade_failure` | 边界鲁棒 | 调度屏障等待终态但不产生虚假失败级联 |
| `test_orchestrator_preserves_planner_parameters` | 回归保护 | Planner 参数和字符串依赖键进入 Orchestrator |
| `test_delegated_tasks_reach_sub_agent_manager` | 功能正确 | Delegator 结果实际进入 SubAgentManager |
| `test_delegation_enforces_skill_tool_policy` | 安全边界 | 委派工具不能绕过 Skill 白名单和黑名单 |
| `test_skill_tool_policy_fails_closed` | 安全边界 | Skill 过滤为空时不回退到全局工具表 |
| `test_sub_agent_invalid_and_cyclic_dependencies_are_blocked` | 边界鲁棒 | 越界、自锁和循环依赖不会死循环 |
| `test_sub_agent_failure_blocks_dependents` | 功能正确 | 上游失败后下游工具不会启动 |
| `test_sub_agent_retry_and_runtime` | 功能正确 | 重试上限、超时透传、尝试次数和运行时统计 |
| `test_sub_agent_timeout_is_never_retried` | 回归保护 | 已超时的工具不会被重复启动 |
| `test_parallel_groups_and_cycle_validation` | 边界鲁棒 | 并行组生效，循环依赖被拒绝 |
| `test_parallel_failure_blocks_downstream` | 回归保护 | 并行批次中的失败级联阻断 |
| `test_parallel_step_rejects_missing_parameters` | 边界鲁棒 | 确定性执行拒绝缺失的结构化参数 |
| `test_nested_step_references_are_strict` | 边界鲁棒 | 嵌套 `$step_N` 解析和未知引用失败 |
| `test_step_reference_requires_declared_dependency` | 边界鲁棒 | 参数引用不能隐式绕过依赖声明 |
| `test_orchestrator_blocks_undeclared_step_reference` | 回归保护 | Orchestrator 对未声明引用 fail-closed |
| `test_racing_returns_first_success` | 功能正确 | Waterfall Racing 在首个成功结果后提前返回 |
| `test_racing_filters_incompatible_signatures` | 边界鲁棒 | 同竞速组但参数签名不兼容的工具被排除 |
| `test_async_entry_does_not_block_event_loop` | 回归保护 | 同步 Agent 流水线不会阻塞 ASGI 事件循环 |

## 工具生命周期

| 测试 | 方向 | 检查内容 |
|---|---|---|
| `test_process_timeout_stops_late_side_effect` | 安全边界 | 超时终止后执行体不能继续产生迟到文件副作用 |
| `test_process_timeout_reaps_descendant` | 资源回收 | 超时会终止工具启动的后代进程，不遗留孤儿进程 |
| `test_unserializable_process_result_becomes_error` | 边界鲁棒 | 不可序列化的跨进程返回值转换为明确错误 |
| `test_abnormal_process_exit_becomes_error_immediately` | 边界鲁棒 | 工具进程异常退出时立即报错，不等待完整超时 |
