# Skill、工具与 Prompt 行为契约

本文定义当前后端中 Skill、工具和 Prompt 的运行时行为。新增 Skill、工具或 Agent 时，应保持这些契约。

## 总体流程

```text
用户消息与上传文件
        |
        v
Router -> 结构校验 -> Skill Router
                         |
                         v
Planner -> 结构校验 -> Delegator（仅复杂且可委派任务）
                         |
                         v
Executor / Orchestrator -> Tool lifecycle
                         |
                         v
Reporter -> 最终文本与真实文件
```

Prompt 用于指导模型，Python 代码负责实施不可绕过的约束。工具白名单、依赖校验、轮次上限和真实文件检查不能只写在 Prompt 中。

## Skill 加载与注册

Skill 来源为 `backend/app/agent/skills/packs/` 下的 YAML，以及扩展目录中的 `SKILL.md`。

加载规则：

1. `skill_id` 是稳定主键，必须全局唯一。
2. 重复 ID 立即抛出 `DuplicateSkillError`，不会覆盖已有定义。
3. `max_tool_rounds` 必须在 1 到 20 之间。
4. implemented/partial Skill 必须声明非空 `allowed_tools`。
5. allowlist 和 denylist 中的名称必须存在于工具注册表。
6. planned Skill 可以不声明工具；此时运行时只暴露 `file_io` 工具。

加载失败不是普通用户错误。重复 ID、未知工具等配置错误应在启动或 CI 中处理，不应降级为另一个同名 Skill。

## Skill 选择

Skill Router 使用三个评分维度：

| 维度 | 权重 | 说明 |
|---|---:|---|
| task/subtask | 0.45 | Router 类型与 Skill 声明的匹配程度 |
| keyword | 0.35 | 用户消息中的中英文触发词 |
| input | 0.20 | 结构化上传附件名与 required inputs 的匹配 |

implemented 和 partial 状态分别提供排序加分，但状态加分不能创建匹配。候选必须至少具备一种真实证据：

- task type 精确命中；
- subtask type 精确命中；
- 至少一个触发关键词命中；
- 至少一个 required input 与可用文件名命中。

英文关键词按 token 边界匹配。中文关键词按子串匹配。没有候选达到证据和分数要求时返回 `None`，系统进入自由规划。

同分时使用 Skill `priority`，再使用 `skill_id`，因此结果不依赖 YAML 文件遍历顺序。

`general`、`bioinformatics`、`file_processing`、`unclear` 和 `unknown` 属于宽泛 task type，不能单独作为匹配证据，也不能仅依靠输入文件补足证据。它们必须与具体 subtask 或关键词组合使用。输入文件证据只在具体 Router task type 与 Skill 声明兼容时生效，避免会话中遗留的上传文件劫持无关的新请求。

## 上传文件参与路由

聊天服务把当前会话的附件对象通过 `available_files` 结构化参数传给 Bio Agent。Bio Agent 只读取这些附件对象的 `filename`、`name` 或 `relative_path`，并把 basename 传给 Skill Router。摘要、用户消息和 system context 中出现的文件名文本都不属于上传证据。

例如：

```json
{
  "filename": "counts.csv",
  "relative_path": "uploads/session/counts.csv"
}
```

会产生 `available_files=["counts.csv"]`。`count_file` 可通过 `count` 别名命中；`data_file` 不会使用过宽的 `data` 别名命中任意 metadata 文件。

文件名匹配只用于路由评分。工具执行仍使用聊天上下文中的真实相对路径或绝对路径提示。

## 工具注册与工具策略

每个工具通过 `register_tool()` 同时写入：

- `TOOL_REGISTRY`：名称到 Python callable；
- `TOOLS_SCHEMA`：发送给模型的 function schema；
- `TOOL_META`：类别、标签、超时和恢复元数据。

工具名必须唯一。第二次注册同名工具会抛出 `DuplicateToolError`，避免 callable 被覆盖但旧 Schema 仍残留。

`run_r_analysis` 是注册领域分析工具使用的内部执行函数，不写入上述三个 Agent 工具注册结构。任意 R 代码与宿主进程具有相同权限，不能依靠 R 函数遮蔽形成安全沙箱，因此模型不能直接调用该函数。

Skill 工具策略如下：

| Skill 状态 | allowed_tools | 行为 |
|---|---|---|
| 未选择 Skill | 不适用 | 使用 Router/Planner 的类别过滤结果 |
| implemented/partial | 非空 | 只允许 `类别结果 ∩ allowlist - denylist` |
| implemented/partial | 空 | 配置错误，运行时工具集为空 |
| planned | 非空 | 只允许 allowlist 中已经注册的工具 |
| planned | 空 | 只允许注册表中的 `file_io` 工具 |

过滤后没有工具时，Executor 返回 `no_skill_allowed_tools`，不会回退到全局工具集。Delegator 和普通 Executor 使用同一套工具策略。

文件读取或编码失败时，恢复策略使用已注册的 `preview_table_file` 做安全预览。恢复策略返回的工具名同样必须存在于注册表，且不会对 `preview_table_file` 自身递归恢复。

## Router 契约

Router 的正常输出是 JSON 对象，关键字段包括：

```json
{
  "task_type": "bioinformatics",
  "subtask_type": "deg_analysis",
  "complexity": "medium",
  "need_clarification": false,
  "tool_categories": ["transcriptome"],
  "suggested_mode": "tool_execution"
}
```

`task_type`、`subtask_type`、`complexity` 必须是字符串；`need_clarification` 必须是布尔值；`tool_categories` 必须是数组。解析失败或类型错误时，Router 回退为 `unclear/unknown + ask_user`，不会把畸形值传入 Skill Router。

## Planner 契约

Planner 接收：

- 对话上下文与 Router 结果；
- 当前允许的工具简介；
- workflow policy；
- 选中 Skill 的 required inputs、参数规则、追问规则、安全规则、预期产物和轮次上限。

每个 Planner step 必须包含唯一、可转为整数的 `step_id`。`preferred_tools` 必须是数组，`parameters` 必须是对象。`step_dependencies` 必须是对象且值为数组，`parallel_groups` 必须是数组的数组。

结构不合法时使用安全回退计划：不包含执行步骤，并依据 Router 决定回答、追问或工具模式。

Planner 返回的 `available_tools` 是 Delegator 的权威工具列表。选中 Skill 后，Planner 还会返回：

- `skill_id`；
- `skill_safety_rules`；
- `skill_output_expectations`；
- `skill_max_tool_rounds`。

`max_tool_rounds` 会被限制到 `1..skill_max_tool_rounds`。

## Delegator 契约

只有功能开关启用、Router 判定为 complex 且 Planner 至少有 3 个步骤时才考虑委派。

Planner 中的 `step_id` 是业务 ID，可以从 1 开始或不连续。Delegator 的 `sub_tasks` 使用从 0 开始的数组索引：

```json
{
  "goal": "读取第一步产物",
  "tool": "preview_table_file",
  "args": {"file_path": "$step_0"},
  "depends_on": [0]
}
```

Planner 路径进入委派时，后端负责把 `$step_<planner step_id>` 转换成 `$step_<subtask index>`。未知引用、非法引用、未知工具、Skill 禁止的工具、错误参数类型或错误依赖索引都会让委派被拒绝。

Delegator 产生的任务采用至多一次执行语义：`max_retries=0`。Prompt 不能提高该值。

## Executor 契约

Executor 依次应用类别过滤和 Skill 工具策略，只把最终 Schema 暴露给模型。

Skill 的安全规则以独立 system message 进入 Executor。预期产物会注明“仅为目标”；只有工具生命周期返回的 `output_files` 才能证明文件已生成。

轮次计算顺序：

1. 读取 Planner 请求值；
2. 应用普通任务、生信任务和复杂任务的默认值或最小值；
3. 应用全局硬上限；
4. 最后应用 `skill_max_tool_rounds`。

因此 Skill 上限优先于生信默认最小轮次。

## Reporter 契约

Reporter 使用 `agent_role="reporter"` 构造领域 Prompt，因此可以收到 reporter-only 输出规则。

Reporter 接收 Planner 的 Skill 安全规则，并额外获得 Skill 报告章节、安全声明和预期产物列表。预期产物中没有出现在 Executor `output_files` 的项目不得声称已生成。

最终回复经过以下处理：

- 清理占位引用；
- 删除不对应真实输出文件的伪造 Markdown 图片；
- 保留真实文件和图片链接；
- Reporter 失败时回退到 Executor 摘要。

## Prompt 安全边界

Prompt 不是权限系统。系统采用以下分层：

1. Prompt 告诉模型应该做什么。
2. JSON 结构校验决定模型输出能否进入下一阶段。
3. 工具 Schema 过滤决定模型能看见什么。
4. 执行前 allowlist/denylist 再次检查工具名称。
5. 工具生命周期规范化结果并收集真实文件。
6. Reporter 清理不真实的文件或图片引用。

即使用户内容或模型输出要求调用白名单外工具，执行层也会拒绝。

## 扩展规范

新增工具时：

1. 使用唯一、稳定的 `register_tool(name=...)` 名称。
2. 确保 Schema required/properties 与函数签名一致。
3. 设置正确 category，必要时配置 timeout 和恢复策略。
4. 将真实注册名写入 Skill allowlist。
5. 运行工具注册一致性测试。

新增 Skill 时：

1. 选择全局唯一 `skill_id`。
2. 为 implemented/partial Skill 声明真实工具 allowlist。
3. 提供具体 task/subtask 或关键词，避免只依赖宽泛 task type。
4. 把医学、实验和数据尺度限制写入 `safety_rules`。
5. 把产物目标写入 `output_expectations`，不要把它当成功状态。
6. 设置不超过 20 的 `max_tool_rounds`。
7. 添加正确匹配、无关请求、缺失输入和工具缺失测试。

修改 Prompt 时：

1. 同步检查输出 JSON 的 Python 校验器和消费者。
2. 明确 ID 是业务 ID 还是数组索引。
3. 不在 Prompt 中承诺运行时代码没有实施的行为。
4. 安全约束同时进入相关 Agent，并由执行层强制实施。

## 验证命令

```powershell
cd backend
python -m pytest -q tests/test_skill_system.py tests/test_skill_packs.py tests/test_skill_tool_prompt_contracts.py
python -m pytest -q
```
