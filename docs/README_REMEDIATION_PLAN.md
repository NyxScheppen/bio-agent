# README 声明校正与实现补齐计划

状态：已实施（2026-09-30）
范围：README 声明校正、运行契约修复与能力契约测试

实施结果：

- 已完成运行时依赖统一、Python 3.11/3.12 检查、配置驱动的 Uvicorn 启动。
- 已完成 planned Skill fail-closed、命令状态展示与 ML 未知算法拒绝。
- 已将 GEO 定位为已上传文件导入/预览，并校正 README 全部相关声明。
- 已增加能力数量、命令状态、启动 URL、ML 拒绝和 planned Skill 短路测试。
- GEO 联网下载、完整 Seurat/空间流程、XGBoost、自动自改进和正式 Linux 支持仍按计划保留为独立立项。
- 验证结果：`183 passed`，`pip check`、`compileall` 和 Windows 环境检查通过。

## 1. 目标与原则

本计划用于解决 README 中夸大、未实现、描述不准确及示例不可执行的问题。

执行原则：

1. 安装、启动、配置和错误处理属于产品契约，优先修代码，不能仅靠降低文档承诺规避。
2. 工具数量、Skill 数量和实现状态属于事实信息，优先移除易漂移的营销数字，或从注册表生成。
3. GEO 下载、完整单细胞/空间转录组、XGBoost 等新增领域能力不在本轮临时补做；先诚实标注，再作为独立功能立项。
4. 底层函数存在不等于用户可用。README 只把能够从 Agent/命令入口到达并通过契约测试的能力列为“已实现”。
5. 所有 README 功能表统一使用 `已实现`、`部分实现`、`规划中` 三种状态。

## 2. 逐项决策

| # | 当前问题 | README | 代码 | 本轮建议 |
|---|---|---|---|---|
| 1 | 快速启动遗漏 PyYAML、networkx | 修改 | 修改 | 将依赖安装描述改为经过验证的行为；补齐并统一依赖清单，增加干净环境启动冒烟测试。 |
| 2 | 声称支持 Python 3.10，但锁定依赖要求 3.11+ | 修改 | 修改 | README 改为 3.11/3.12；启动脚本删除 3.10 回退，并在版本过低时给出明确错误。 |
| 3 | 宣称 GEO 联网下载，实际只能读取已上传文件 | 修改 | 修改配置 | README 改为“GEO 文件导入/预览”；保留兼容的 Skill ID，但修改 Skill 名称、描述、命令帮助和澄清文案。暂不实现联网下载。 |
| 4 | 单细胞、空间转录组、虚拟扰动被写成可用功能 | 修改 | 修改入口保护 | README 标为“规划中/实验性底层工具”；命令系统不得把 planned Skill 当作可执行能力，直接调用时返回结构化的未实现提示。 |
| 5 | “54 个 Skill、16 类”混淆定义数和可用数 | 修改 | 可选校验 | 改为“54 条定义：19 implemented、2 partial、33 planned；15 个 category”。更推荐不在首页写固定数量。 |
| 6 | “18 个 YAML Skill 定义”实际为 16 个 YAML 包 | 修改 | 不改 | 改为“16 个 YAML 包、54 条 Skill 定义”，或删除数字。 |
| 7 | “45+ 专业工具”实际注册 36 个 | 修改 | 可选校验 | 改为“36 个已注册工具”，或删除固定数量；不为凑数新增包装工具。 |
| 8 | 宣称 XGBoost，实际只支持 Logistic/RF/SVM | 修改 | 修改 | README 和 `/compare` 示例移除 XGBoost；工具收到未知算法时显式报错，禁止静默回退 RF 或静默过滤。XGBoost 另行立项。 |
| 9 | “自改进闭环”实际只有自动记录，分析需人工调用 | 修改 | 不改 | 改为“失败记录 + 手动生成改进建议”，明确不会自动修改 Skill。本轮不增加自动调度和自动写配置。 |
| 10 | Linux 兼容缺少安装、启动和验证路径 | 修改 | 后续功能 | 本轮改为“Windows 主平台；后端具备部分 POSIX 兼容，Linux 未形成正式支持”。`start_app.sh`、Linux CI 和 R 路径验证另行立项。 |
| 11 | API_HOST/API_PORT 不影响官方启动脚本 | 修改 | 修改 | 让官方启动入口读取 `app.core.config` 后启动 Uvicorn；README 保留变量并补充生效说明。避免在 batch 中重复解析 `.env`。 |
| 12 | Waterfall Racing 被描述成通用竞速 | 修改 | 不改 | 改为“DEG 分析工具竞速”，列明当前只覆盖 limma/连续表达与 DESeq2/count 两个候选。 |
| 13 | 19 个命令数字正确，但表格漏 `/risk` 且含不可用命令 | 修改 | 修改入口保护 | 补 `/risk`；给 `/geo` 标“部分实现”、`/scrna` 标“规划中”，`/help` 从 Skill 状态生成可用性标记。 |
| 14 | 新增工具示例缺少 `make_error_result` 导入 | 修改 | 不改 | 修正示例导入，并增加最小可复制示例测试或文档代码检查。 |
| 15 | “全量回归测试”实际只运行一个快速脚本 | 修改 | 修改测试依赖 | 新增开发测试依赖文件并安装 pytest；全量命令改为 `python -m pytest -q backend/tests`，原脚本改称“ToolResult 快速冒烟测试”。 |

## 3. 推荐实施范围

### 阶段 A：修复真实产品契约

这些问题只改 README 不够，应优先修改代码：

1. **统一 Python 依赖来源**
   - 明确根 `requirements.txt` 为启动脚本使用的唯一运行时依赖清单。
   - 补充 `PyYAML`、`networkx`，核对 `backend/requirements.txt`，避免两份清单继续漂移。
   - 新增 `requirements-dev.txt`，至少包含 pytest；生产环境不强制安装测试工具。

2. **收紧 Python 版本契约**
   - `start_app.bat` 仅接受 Python 3.11/3.12。
   - 对 `where python` 找到的解释器同样验证版本，不能只验证命令存在。
   - 版本不符时显示所需版本和当前版本。

3. **让端口配置真正生效**
   - 新增或复用 Python 启动入口，由 `app.core.config.API_HOST/API_PORT` 调用 `uvicorn.run()`。
   - `start_app.bat` 调用该入口，不再硬编码主机与端口。
   - 浏览器自动打开地址应与实际绑定配置一致；`0.0.0.0` 等监听地址需映射为本地可访问 URL。

4. **拒绝虚假的算法降级**
   - `run_ml_classification_model()` 对未知算法返回明确错误。
   - `run_multi_model_comparison()` 报告所有不支持的算法；禁止悄悄删除 `xgboost`。
   - 增加大小写、空列表、混合合法/非法列表的边缘测试。

5. **planned Skill 入口 fail-closed**
   - 命令解析仍可识别命令，但 planned Skill 不进入正常 Planner/Executor 流程。
   - 返回稳定的 `not_implemented`/`planned_skill` 结果，说明可用替代路径。
   - `/help` 显示 Skill 状态，防止把 planned 命令展示为已可用。
   - GEO 作为 `partial`，只允许文件导入/预览，不出现联网下载措辞。

6. **建立能力清单校验**
   - 增加只读脚本或测试，输出 YAML 包数、Skill 状态数、category 数、注册工具数和命令数。
   - README 尽量不硬编码这些数字；若保留，则由测试检查声明与运行时一致。

### 阶段 B：校正 README

代码契约修复完成后统一修改 README，避免文档先描述尚未合入的行为：

1. Python 要求改为 3.11/3.12，说明干净环境安装路径。
2. 将“54 个 Skill”改为定义数与实现状态，或直接去掉首页数字。
3. 将“45+ 工具”改为准确注册数量，或改成不带数量的类别描述。
4. 功能矩阵增加状态列；单细胞、空间转录组、虚拟扰动标为规划中。
5. GEO 改为本地文件导入/解析；删除下载承诺。
6. ML 删除 XGBoost；保留 Logistic、随机森林、SVM、LASSO。
7. 自改进改成被动记录和人工触发分析。
8. Racing 明确当前仅用于 DEG 工具组。
9. Linux 改为未正式支持，不提供“兼容 Linux”的无条件承诺。
10. 命令表补 `/risk`，显示 `/geo` 和 `/scrna` 状态。
11. 修复 `make_error_result` 示例导入。
12. 用真实 pytest 命令替换“全量回归测试”，保留快速脚本但准确命名。
13. 目录结构数字改为“16 个 YAML 包”，或不写固定数量。

### 阶段 C：独立功能立项，不并入本轮

以下工作会显著扩大依赖、安全面或测试矩阵，不建议为了保留 README 文案仓促实现：

1. **GEO 联网下载**：需要 accession 校验、允许域名、DNS/重定向 SSRF 防护、下载预算、缓存、解压预算及数据格式兼容测试。
2. **完整 Seurat 流程**：需要明确输入格式、Seurat 版本/R 包、稀疏矩阵预算、QC/聚类/marker 契约和真实数据集回归。
3. **空间转录组和虚拟扰动**：当前 Skill 为 planned，应分别设计输入输出契约和科学有效性边界。
4. **XGBoost**：需要选择 Python 或 R 后端、依赖安装策略、参数验证、模型复现和比较输出契约。
5. **自动自改进闭环**：自动写 Skill/Prompt 前需要审批、审计、回滚和离线评估，当前仅保留人工审核。
6. **正式 Linux 支持**：需要 `start_app.sh`、Linux CI、Rscript 探测、前端资源和文件权限测试。

## 4. 建议提交拆分

为便于审查和回滚，建议拆成四个提交：

1. `fix(setup): align runtime dependencies and Python support`
   - 依赖统一、Python 版本检查、干净环境冒烟测试。
2. `fix(runtime): honor server config and reject unsupported capabilities`
   - API_HOST/API_PORT、ML 算法校验、planned Skill/命令保护。
3. `test(capabilities): verify registry and command contracts`
   - 能力统计、命令状态、帮助输出和全量测试入口。
4. `docs(readme): align claims with executable capabilities`
   - README 的所有事实与示例校正。

README 提交放在代码和测试之后，使文档描述对应同一提交序列中已经存在的行为。

## 5. 验收标准

### 安装与启动

- 在全新 Python 3.11 和 3.12 虚拟环境中，运行依赖安装后可成功 `import app.main`。
- Python 3.10 启动时在安装依赖前失败，并提供清晰提示。
- 不依赖开发机中历史安装的 PyYAML 或 networkx。
- 设置非默认 `API_HOST`/`API_PORT` 后，Uvicorn 使用对应配置。

### 能力与命令

- `xgboost` 等未知算法返回错误，不会执行随机森林。
- planned Skill 不会进入工具执行流程。
- `/help` 能区分已实现、部分实现、规划中。
- `/geo` 不声称或尝试联网下载。
- `/scrna` 在未正式启用前返回明确的规划中状态。

### 文档与测试

- README 中每项“已实现”功能都存在可达的用户入口和自动化测试。
- Skill、工具、category、YAML 包和命令数量与能力清单测试一致，或 README 不再硬编码数量。
- README 的完整测试命令能够收集并运行整个 `backend/tests` 套件。
- 文档示例通过最小导入/语法检查。
- 完整测试、`compileall` 和注册契约测试通过。

## 6. 审阅决策点

请重点确认以下产品取舍：

1. 是否接受将 Python 3.10 从支持范围删除，而不是降级 NumPy/Pandas 等依赖。
2. 是否接受首页移除固定的 Skill/工具数量，避免随注册表变化持续漂移。
3. 是否接受本轮将 GEO、单细胞、空间转录组、虚拟扰动降级为部分实现/规划中，而不是立即补齐完整功能。
4. 是否把 Linux 正式支持、XGBoost、GEO 下载分别拆成后续独立任务。
5. planned 命令是继续显示并标注状态，还是从 `/help` 默认列表隐藏；本计划推荐“显示并标注”，便于表达路线图但不误导可用性。
