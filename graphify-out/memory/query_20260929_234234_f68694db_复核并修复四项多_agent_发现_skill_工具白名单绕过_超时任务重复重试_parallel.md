---
type: "query"
date: "2026-09-29T23:42:34.818773+00:00"
question: "复核并修复四项多 Agent 发现：Skill 工具白名单绕过、超时任务重复重试、parallel_groups 语义丢失、未满足的 $step_N 引用被透传。"
contributor: "graphify"
outcome: "useful"
source_nodes: ["Orchestrator", "SubAgentManager", "run_delegator_agent()"]
---

# Q: 复核并修复四项多 Agent 发现：Skill 工具白名单绕过、超时任务重复重试、parallel_groups 语义丢失、未满足的 $step_N 引用被透传。

## Answer

Expanded from original query via graph vocab: [agent, skill, allowed, delegator, tools, timeout, retry, parallel, dependencies, orchestrator, step]. 四项发现均确认并修复：统一 fail-closed Skill 工具策略覆盖普通、并行和委派路径；子 Agent 默认零重试且超时永不重试；parallel_groups 转换为独立 schedule_after 屏障而不制造失败依赖；$step_N 必须存在、成功、可传递并显式声明依赖，否则 blocked。相关测试 45/45 通过，全仓 92 通过，仅保留既有重复 Skill ID 失败。

## Outcome

- Signal: useful

## Source Nodes

- Orchestrator
- SubAgentManager
- run_delegator_agent()