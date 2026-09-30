# BioAI Agent 项目代码汇报

生成日期：2026-09-29

## 一、结论摘要

这是一个面向生物信息学研究场景的本地全栈 AI Agent。系统以 FastAPI 提供聊天、上传、历史记录和文件访问接口，以 DeepSeek 的 OpenAI 兼容 API 驱动 Router、Planner、Executor、Reporter 流水线，再将任务落到 Python/R 生信工具上。前端是已经构建好的 React/Vite SPA，源码未随仓库提交。

当前主干已经具备较完整的工程骨架：会话隔离、Skill 匹配、工具白名单、统一 ToolResult、工具生命周期、结果文件回传、SQLite 审计、失败恢复和依赖感知并行均有实际代码与测试。它适合作为本地研究助手继续演进，但尚不宜把全部文档特性视为生产可用。

最需要优先处理的三点是：

1. 工具超时和资源限制没有做到真正隔离或终止，长耗时任务可能在报告“超时”后仍继续占用资源。
2. 5 个 Skill ID 在不同 YAML 包中重复，加载顺序会静默覆盖配置，现有测试因此失败。
3. Waterfall Racing、Delegator、部分 Hook 和 Feature Flag 处于“有实现但未完整接入主链路”的状态，文档描述高于实际能力。

## 二、项目定位与技术栈

- 产品定位：用自然语言驱动生信分析，覆盖数据上传、任务规划、R/Python 工具执行、图表/文件回传和报告生成。
- 后端：Python 3.10-3.12、FastAPI、Uvicorn、Pydantic。
- LLM：DeepSeek API，通过 OpenAI Python SDK 调用。
- 数据：SQLite + SQLAlchemy，保存会话、消息、文件和工具执行审计。
- 分析：Pandas、NumPy、SciPy、Scikit-learn、Matplotlib、Seaborn，以及 R/Bioconductor。
- 前端：React 18 + Vite 的预构建静态包；仓库内没有前端源代码和 package.json。
- 运行环境：Windows 是主平台，启动脚本会创建虚拟环境、安装依赖、定位 Rscript 并启动服务。

代码规模约为：后端应用 70 个 Python 文件、12,298 行；测试 11 个 Python 文件、1,777 行；Skill 配置 17 个 YAML 文件、1,274 行。

## 三、实际请求链路

用户请求的核心路径如下：

```text
React SPA
  -> POST /api/chat
  -> chat_service：会话、历史消息、附件上下文、结果文件持久化
  -> bio_agent：上下文压缩与 Session Memory
  -> Router：判断任务类型、复杂度和是否追问
  -> Skill Router：按任务、关键词、输入文件和实现状态评分
  -> Planner：生成步骤、参数策略、工具类别和并行关系
  -> Executor：筛选工具并执行
  -> run_tool_with_lifecycle：job 目录、标准返回、产物收集、审计与恢复
  -> Reporter：生成中文结构化答复
  -> {reply, files, session_id, title}
```

系统的关键架构中心不是某个领域工具，而是 `run_tool_with_lifecycle()`：Executor、并行执行、恢复策略、审计、Hook、ToolResult 和输出文件收集都通过它衔接。这也是知识图谱中最重要的跨社区桥梁。

## 四、能力现状

### 已实际接入

- Router -> Skill -> Planner -> Executor -> Reporter 主流水线。
- 19 个斜杠命令。
- 54 个唯一 Skill：19 个 implemented、2 个 partial、33 个 planned。
- 默认导入 37 个业务工具；自动发现后为 40 个，其中 3 个来自示例模块。
- 生存分析、转录组、富集、机器学习、单细胞、网络药理学、文献、文件和系统诊断等工具类别。
- Rscript 自动定位、私有 R 包库和 UTF-8 子进程环境。
- Session Memory、短回复解析、上下文压缩。
- ToolResult 标准协议、输出文件自动收集、SQLite 审计记录。
- 重复调用检测、连续错误熔断和六类恢复策略。
- Planner 显式给出并行组时的依赖感知批次执行。

### 尚未完整接入

- Waterfall Racing：实现文件和 `racing_group` 已存在，但 Executor 主路径没有调用 `race_tools()`，失败分支仍为 `pass`。
- Delegator：默认关闭；打开后 `bio_agent.py` 缺少 `run_delegator_agent` 导入，而且生成的 `sub_tasks` 没有被 Executor 消费。
- Feature Flags：多数开关只是声明，没有在对应执行路径中统一检查。
- Hook：工具前后 Hook 会触发，但 `POST_AGENT_TURN` 清理 Hook 没有调用点。
- 前端可维护性：只有压缩后的 bundle，无法正常进行组件级开发、类型检查和前端测试。

## 五、验证结果

- Python 3.12.10、R 4.5.2 可用，核心 Python 依赖导入成功。
- `compileall backend/app` 通过。
- FastAPI 应用可导入，路由表完整，包括聊天、上传、历史、系统、健康检查和 SPA 静态服务。
- 项目未安装 pytest；按仓库约定直接运行 10 个测试脚本。
- 9 个测试脚本通过，1 个失败。
- 失败项：`test_skill_packs.py::test_all_skill_ids_unique`。
- 重复 ID：`geo_data_download`、`multi_model_comparison`、`lasso_feature_selection`、`deseq2_count_deg`、`bulk_pca_analysis`。
- 路径穿越防护、文件 URL、ToolResult、工具生命周期、工具注册、Skill 路由等测试均通过。

## 六、主要风险与建议

### P0：工具超时和资源限制不是硬限制

`run_tool_with_lifecycle()` 使用单线程 `ThreadPoolExecutor` 和 `future.result(timeout=...)`。超时只能停止等待，不能终止正在运行的线程；离开 executor 上下文时还会等待线程结束。返回文案“已中断”与实际行为不一致。`ResourceMonitor` 只读取起止内存，没有后台采样、CPU 采样或阈值终止逻辑。

建议把高风险工具放到独立进程中执行，按 job 管理 PID，并在超时或内存越界时终止完整进程树。R 工具可以直接围绕 `subprocess.Popen` 做取消和资源治理。

### P1：Skill 重复 ID 导致配置覆盖

注册表遇到重复 ID 只打印警告并覆盖，最终行为依赖文件加载顺序。测试已明确失败，且重复项包含 DEG、PCA、GEO 和 ML 等核心能力。

建议确定每个 Skill 的唯一所有者，删除重复定义或改为显式继承/变体 ID；生产加载时应对重复 ID fail fast。

### P1：文档和实际能力漂移

README 写“45+ 专业工具”和“并行 + 竞速”，而默认运行时是 37 个工具，自动发现后是 40 个；Racing 尚未接入。建议生成能力清单，或在 CI 中从注册表自动校验 README 数字。

### P1：本地边界清晰，服务化安全不足

服务默认绑定 `127.0.0.1`，符合本地工具定位；但 API 没有认证，CORS 允许所有来源，历史、文件和删除接口只依赖可猜测的 session_id。若部署到局域网或公网，需要认证授权、可信 Origin、请求体/上传大小限制和 session 所有权校验。

### P2：前端仅保留构建产物

压缩 bundle 约 328 KB，功能可以运行，但缺少源代码、构建配置和前端测试。建议恢复并纳入 `frontend/` 源码，再由 CI 产出 `backend/static/`。

### P2：依赖清单存在双轨

根目录 `requirements.txt` 是固定版本的完整运行环境，`backend/requirements.txt` 是未固定的最小集合，且内容不完全一致。实际启动脚本使用根目录文件。建议只保留一个权威依赖源，或明确生产锁文件与开发输入文件的生成关系。

## 七、建议路线

1. 先修复 5 个重复 Skill ID，使全量测试恢复为绿色。
2. 将工具执行从线程迁移到可终止的独立进程，补超时、取消、内存上限和僵尸进程测试。
3. 对高级特性做一次“接入审计”：Racing、Delegator、Hooks、Feature Flags，要么接通并测试，要么在文档标为实验性。
4. 增加 API 鉴权和会话所有权模型，再考虑非本机部署。
5. 恢复前端源码和标准构建链，统一依赖与 CI 质量门。

## 八、Graphify 分析说明

Graphify 扫描了 119 个文件、约 65,305 词，生成 2,102 个节点、5,472 条构建后关系和 99 个社区。由于仓库包含压缩后的前端 bundle，图谱产生了大量短变量名节点；健康检查还发现 196 条悬空边、30 个自环和 549 组无向同端点折叠关系。因此图谱适合导航和发现跨模块桥梁，不应被当作精确的软件度量。

完整产物：

- `graph.html`：交互式关系图。
- `GRAPH_REPORT.md`：Graphify 审计报告。
- `graph.json`：原始图数据。
- `.graphify_health.json`：图健康诊断。

Graphify 的 token 计数记录为 0，因为语义提取由当前本地会话完成，未通过可返回 usage 的外部 Gemini 后端；这不表示分析没有计算成本。
