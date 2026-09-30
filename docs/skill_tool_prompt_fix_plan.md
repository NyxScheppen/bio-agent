# Skill、工具与 Prompt 修复计划

## 目标

修复 Skill 配置、工具注册表和多 Agent Prompt 之间的契约断裂，使错误配置在启动或测试阶段失败，使 LLM 输出在进入执行层之前经过结构校验，并保证 Skill 的工具、安全和预算限制无法被后续 Agent 绕过。

## 已分析的边缘情况

### Skill 加载

- 两个 YAML 文件使用相同 `skill_id`：禁止按文件顺序静默覆盖，直接抛出 `DuplicateSkillError`。
- 单个 YAML 内部重复 ID、YAML 与 `SKILL.md` 重复 ID：采用相同的失败策略。
- implemented/partial Skill 未声明 `allowed_tools`：视为配置错误；运行时返回空工具集。
- `allowed_tools` 或 `banned_tools` 引用未注册工具：启动校验失败。
- planned Skill 没有工具实现：仅允许已注册的 `file_io` 工具做文件探测，不开放分析工具。
- Skill 的 `max_tool_rounds` 小于 1 或大于 20：模型校验失败。

### Skill 路由

- completely unrelated 请求：implemented 状态、priority 和中性分不能单独构成匹配证据。
- 单字符英文关键词，例如 `R`：必须按完整 token 匹配，不能命中 `weather` 中的字母。
- 中文关键词：保留子串匹配，适配没有空格的中文表达。
- 空消息但 Router 有明确 task/subtask：允许依靠 Router 的精确类型匹配。
- Router 不明确但上传文件名匹配 required input：允许文件名作为匹配证据。
- `data_file`、`input_file` 等过于宽泛的字段：不使用 `data`/`input` 作为模糊别名，防止 `metadata.csv` 误命中。
- 同分候选：依次按分数、Skill priority、`skill_id` 排序，结果与加载顺序无关。
- 无匹配证据：返回 `None`，进入自由规划，而不是强选一个 Skill。

### Router、Planner 和 Delegator 输出

- 非 JSON 或顶层不是对象：使用既有解析失败回退。
- JSON 合法但字段类型错误，例如 `steps: "abc"`：在下游消费前拒绝并回退。
- Planner 步骤缺少 `step_id`、ID 重复、参数不是对象、工具列表不是数组：拒绝该计划。
- `parallel_groups` 或 `step_dependencies` 类型错误：拒绝该计划。
- Delegator 收到非步骤数组：返回 `should_delegate=false`，不抛异常。
- Delegator 返回非布尔 `should_delegate` 或非数组 `sub_tasks`：拒绝委派。
- `$step_N` 引用未知 Planner step：拒绝计划，不把原始字符串传给工具。
- Planner 使用业务 `step_id`；Delegator 输出使用从 0 开始的子任务数组索引。转换发生在委派边界。

### 工具和执行预算

- 重复工具名：注册时抛出 `DuplicateToolError`，避免 Registry、Schema、Meta 三张表不一致。
- Skill allowlist 中工具被类别路由过滤掉：取两个集合的交集；交集为空时拒绝执行。
- banned tool 同时出现在 allowlist：banned 优先。
- Skill 未选中：按 Router/Planner 工具类别正常路由，不应用 Skill 白名单。
- 生信任务的默认最小轮次高于 Skill 上限：Skill 上限最终优先，不能被 Executor 再提高。
- Planner 返回超大轮次、字符串轮次或非正数：转换并限制到 `1..skill.max_tool_rounds`。

### Prompt 与报告

- `safety_rules` 同时进入 Planner、Executor 和 Reporter 上下文。
- `output_expectations` 是执行目标，不是生成成功的证据。
- Reporter 只能报告 `executor_result.output_files` 中真实存在的文件。
- Reporter 必须使用 `agent_role="reporter"` 构造领域规则，确保 reporter-only 规则生效。
- answer-only 路径同样使用 Reporter 角色规则，并通过 Planner result 获取 Skill 安全约束。
- 用户文本仍作为数据 payload 发送；运行时工具白名单是最终安全边界，不能只依赖 Prompt。

## 实施顺序

1. 清理重复 Skill 定义，统一所有工具名称到 `TOOL_REGISTRY` 的实际名称。
2. 为 Skill 和工具注册增加重复检测，为 Skill 工具引用增加启动期校验。
3. 为 Skill Router 增加真实证据门槛、关键词边界和确定性排序，并接入上传文件名。
4. 为 Router、Planner、Delegator 增加结构校验和失败回退。
5. 将 Skill 安全规则、预期产物和工具列表贯穿 Planner、Executor、Delegator、Reporter。
6. 让 Skill 轮次成为硬上限，修正 Reporter 的角色 Prompt。
7. 增加专项边界测试，运行 Agent 和完整后端测试。
8. 编写运行时行为文档，记录扩展 Skill、工具和 Prompt 时的契约。

## 验收标准

- Skill ID 全局唯一，当前稳定加载 54 个 Skill。
- `TOOL_REGISTRY`、`TOOLS_SCHEMA`、`TOOL_META` 名称一致，当前稳定注册 37 个工具。
- 所有 Skill 的 allowlist/denylist 均只引用真实工具。
- 无关天气请求不再选择任何生信 Skill。
- 畸形结构化输出不会导致 AttributeError 或进入工具执行层。
- Skill 安全规则在三个运行阶段均可见。
- Skill 最大轮次不能被 Planner 或 Executor 提高。
- 新增专项测试和原有 Skill 测试全部通过。

## 实施状态

以上 8 个实施步骤均已完成。专项 Skill/工具/Prompt 契约测试通过，完整后端测试结果为 `119 passed`。
