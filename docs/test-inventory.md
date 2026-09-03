# 测试清单

> 每次编写测试后追加条目。每条记录：新增了哪些测试 / 检查方向 / 所属系统 / 在哪个功能阶段编写。

## 条目

### 01-types：枚举 + 实体类型

- **新增测试**：
  - `tests/test_types/test_enums.py` — 3 个枚举穷尽断言、命名约定断言、StrEnum 序列化断言
  - `tests/test_types/test_types.py` — ToolDefinition 形状（Python/R 工具）、`default_factory` 隔离、TypedDict 键集合断言
- **检查方向**：
  - 功能正确：枚举值集合完整、值 = 成员名小写、`json.dumps` 直接序列化；dataclass 字段与默认值、TypedDict 键完整性
  - 回归保护：防枚举漏成员/多成员/改值；防 `frontend` 两次实例化共享
- **所属系统**：类型与枚举（`backend/bioagent/enums.py` / `types.py`）
- **阶段**：spec 01-types 实现

### 02-config：配置加载

- **新增测试**：
  - `tests/test_config/test_config.py` — `validate_config` 纯函数测试（7 条）、`load_config` 测试（11 条，tmp yaml + monkeypatch + 真实 config.yaml）
- **检查方向**：
  - 功能正确：缺键填默认、`BIOAGENT_CONFIG` 覆盖路径、`path=None` 读 `config.yaml`；合法配置通过、`base_url=None` 放行
  - 边界鲁棒：未知顶层/段内键报错、嵌套段非 dict 报错、文件缺失/坏 YAML 报错、重复键（段内 `model:` 两次 / 段 `llm:` 两次）报错、越界值（`judge_sample_rate=1.5` / `top_k=0`）报错、错类型（`"20"` / `True`）报错、`base_url=""` 报错
  - 回归保护：加载真实 `config.yaml` 校验字段值（`llm.model` / `rag.top_k`）
- **所属系统**：配置（`backend/bioagent/config.py` / `config.yaml`）
- **阶段**：spec 02-config 实现

### 03-db：SQLite 连接 + 建表 + 迁移

- **新增测试**：
  - `tests/test_db/test_db.py` — `migrate`（建表/索引、可空性对齐、幂等、版本门控、原子回滚）5 条 + `connect`（返回 Database、pragma/row_factory、错误路径不泄漏、父目录自动创建）3 条
- **检查方向**：
  - 功能正确：4 张业务表 + `schema_version` 建表、2 个显式索引、版本推进到 `_MIGRATIONS` 最高版本；`connect` 返回 `Database`（conn+lock），`journal_mode=WAL`、`foreign_keys=ON`、`row_factory` 生效、父目录自动 `mkdir`（首次启动 `data/` 尚不存在）
  - 边界鲁棒：可空性对齐（`token_usage.correlation_id` / `task.error` 可空，其余非 Optional 列 NOT NULL）、`migrate` 幂等、版本门控（只套未应用版本）、失败原子回滚（版本不推进）、`connect` 错误路径连接不泄漏（close 被调用）
- **所属系统**：数据库（`backend/bioagent/db.py`）
- **阶段**：spec 03-db 实现

### 04-llm：统一 LLM 客户端

- **新增测试**：
  - `tests/test_llm/test_llm.py` — `_to_lc`（system/user/assistant/未知角色）4 条、`_extract_usage`（dict / Pydantic / None / 值 None / 非数字 / 未知形状）6 条、`_resolve_base_url`（显式 / 已知 provider / 未知 provider）3 条、`complete`（字段填充、token 抽取、缺失计 0、json_mode 转发、非 json_mode 省略、消息顺序、非文本抛错、记账写入、记账失败 best-effort）9 条、`from_config`（未知 provider / 缺 key / ollama 免 key / normal / openai / 自定义 base_url）6 条
- **检查方向**：
  - 功能正确：`_to_lc` 角色映射、`_extract_usage` 兼容 dict 与 Pydantic 两种 `usage_metadata` 形状、`_resolve_base_url` 显式优先于内置映射；`complete` 组装 `LLMOutput`（id/module/type/model/content/token_usage/correlation_id）、`json_mode` 注入 `response_format`、消息按序转为 LangChain 消息、按 `LLMOutput` 写 `token_usage` 一行并 commit
  - 边界鲁棒：未知角色抛 `ValueError`、非文本 content 抛 `RuntimeError`、token 用量缺失/None/非法值计 0、未知 provider 抛 `ConfigError`、缺 API key 抛 `ConfigError`（ollama 免 key 用 dummy）；记账失败不阻断主流程（best-effort，仍返回 `LLMOutput`）
  - 回归保护：`from_config` 走 ChatOpenAI 统一封装（非裸 httpx）、显式传 `model_name` 不依赖 LangChain 属性
- **所属系统**：LLM 客户端（`backend/bioagent/llm/client.py`）
- **阶段**：spec 04-llm 实现

### 05-tools：工具注册表 + 自动发现

- **新增测试**：
  - `tests/test_tools/test_tools.py` — `register`/`get`（命中/未命中/重名）3 条、`register` runtime 契约（R 无脚本/空脚本/带 run、Python 无 run/带脚本、合规 P/R）7 条、`for_categories`（过滤/空集合）2 条、`all_tools`/`__iter__`/`__len__` 1 条、`discover`（fixture 包只注册 TOOL、非幂等）2 条
  - `tests/fixtures/fake_tools/`（`dge_foo.py` 导 `TOOL`、`junk.py` 导非 `ToolDefinition`、`__init__.py` 不导出）— discover 集成测试的 fixture 包
- **检查方向**：
  - 功能正确：`register` 后 `get` 返回同一实例、重名抛 `ValueError`；`for_categories` 按类别裁剪、空集合返回空；`all_tools`/迭代/`__len__` 协议一致；`discover` 递归收集 `TOOL` 导出
  - 边界鲁棒：runtime 契约严格校验（R 工具须非空 `r_script` 且 `run=None`，Python 工具须 `run` 且 `r_script=None`，违反 `ValueError`）；`get` 未命中 `KeyError`；`discover` 跳过不导 `TOOL`/导非 `ToolDefinition` 的模块（`isinstance` 守卫）；`discover` 非幂等（重复注册撞同名 `ValueError`，生产只调一次）
  - 回归保护：fixture 包验证「加工具 = 加文件」自动发现机制，防止后续工具（11-15）破坏 `discover()`
- **所属系统**：工具注册表（`backend/bioagent/tools/__init__.py`）
- **阶段**：spec 05-tools 实现

### 06-r-runner：R 子进程执行器

- **新增测试**：
  - `tests/test_r_runner/test_r_runner.py` — `run` 路径拼接、args JSON 经 stdin 传入、序列化失败不 spawn、成功解析、非零退出、stdout 非 JSON、stdout 非法 UTF-8、stdout 非对象、Rscript 缺失 9 条
- **检查方向**：
  - 功能正确：`script_path = os.path.join(scripts_dir, script_name)` 作为 `["Rscript", script_path]` 列表第二元素（`shell=False` 防命令注入）；args 以 `json.dumps(args).encode("utf-8")` 经 `communicate` 传入 stdin；成功路径 stdout 解析为 `dict`
  - 边界鲁棒：非零退出码抛 `RRuntimeError`（消息含 stderr 文本）；stdout 非合法 JSON 抛 `RRuntimeError`；stdout 非法 UTF-8 经 `decode('utf-8','replace')` 兜底（不抛裸 `UnicodeDecodeError`）；stdout 非对象（如 `[1,2,3]`）抛 `RRuntimeError`；`Rscript` 缺失（`FileNotFoundError`）抛 `RRuntimeError`；args 不可 JSON 化时先抛 `TypeError`、不 spawn 子进程（payload 前置在 spawn 之前）
  - 回归保护：mock R 子进程（不真跑 Rscript），防后续 R 工具（11-15）直接 `subprocess` 绕过 `RRunner`
- **所属系统**：R 执行器（`backend/bioagent/r_runner.py`）
- **阶段**：spec 06-r-runner 实现

### 07-rag：RAG 向量检索（Embedder + RagClient）

- **新增测试**：
  - `tests/test_rag/test_rag.py` — `Embedder.embed`/`dim`（注入 fake SentenceTransformer）1 条、`RagClient.query`（记录 collection/query/limit、返回 `{"text","score"}`、payload 兜底）2 条、`RagClient.ingest`（upsert 记录 points、空列表跳过）2 条、`RagClient.ensure_collection`（缺失建 collection/COSINE、已存在跳过）2 条、`RagClient.close` 1 条
- **检查方向**：
  - 功能正确：`Embedder.embed` 返回 `list[float]`、`dim` 返回模型维度；`query` 用 embedder 向量 + `top_k` 调 `query_points` 并投影为 `[{"text","score"}]`；`ingest` 按 document 逐条 embed + 组 `PointStruct`，经 `upsert` 上传，返回 `len(documents)`；`ensure_collection` 以 `VectorParams(size=dim, distance=COSINE)` 建 collection
  - 边界鲁棒：`query` 遇 point `payload=None` 或缺 `"text"` 兜底为 `""`（不崩）；`ingest` 空列表返回 0 且不调 `upsert`；`ensure_collection` 幂等（`collection_exists=True` 时不再建）
  - 回归保护：mock `AsyncQdrantClient` 与 `SentenceTransformer`（不连真实 Qdrant、不下载真实模型）；锁定 `upsert`（非 `upload_points`——1.19.0 里后者是同步方法，`await` 会运行时崩）
- **所属系统**：RAG（`backend/bioagent/rag.py`）
- **阶段**：spec 07-rag 实现

### 08-eval：评测（两个 judge + 落库）

- **新增测试**：
  - `tests/test_eval/test_eval.py` — `parse_scores`（报告 3 维 / 工具 2 维 / 坏 JSON / 非对象 / 非数字，parametrize 5 条）、`judge_report`（fake client 记录参数、返回预设 `LLMOutput`）1 条、`judge_tool_call`（prompt 含 intent 与 tool_calls）1 条、`evaluate_report`（fake db 记录 SQL、返回 `EvalReport` type=report）1 条、`evaluate_tool_call`（type=tool_call）1 条
- **检查方向**：
  - 功能正确：`parse_scores` 合法 JSON → 5 维（报告 judge 只 3 键时工具 2 维计 0，反之亦然）；`judge_*` 以 `output_type="eval"`、`json_mode=True`、`module="eval"` 调 `client.complete`，prompt 注入 query/report/intent/tool_calls；`evaluate_*` 写 1 行 `eval_report`、返回 `EvalReport`（`type` 判别 report/tool_call、`output_id==output.id`、`scores` 由 `parse_scores(judge.content)` 得出）
  - 边界鲁棒：坏 JSON / 非对象（`[1,2]`）/ 非数字（`{"format":"high"}`）对应维度计 0 不抛；`token_usage` 表写 0 行（token 记账归 04-llm，本 spec 不写）
  - 回归保护：注入 fake `LlmClient` 与 fake `Database`（不触真实 LLM / 真实 SQLite 文件）；`parse_scores` 纯函数单独测全
- **所属系统**：评测（`backend/bioagent/eval/judge.py` / `evaluate.py`）
- **阶段**：spec 08-eval 实现

### 09-orchestration：LangGraph 四节点编排

- **新增测试**：
  - `tests/test_orchestration/test_orchestration.py` — `make_router_node`（fake client 记录参数、返回 JSON）1 条、`make_planner_node`（`sample_rate=0.0` 不评 / `=1.0` 评且参数正确）2 条、`make_executor_node`（Python/R 分派）1 条、`_resolve_files`（合法 uuid 解析 1 条 + 非法 file_id/路径穿越拒绝 1 条）2 条、`make_reporter_node`（markdown + eval 抽样）1 条、`build_graph` 集成（真实 langgraph 编译 + 全 fake 依赖）1 条，共 8 条
- **检查方向**：
  - 功能正确：router 以 `module="router"`/`output_type="intent"`/`json_mode=True`/`correlation_id` 透传调 LLM，prompt 含 `allowed` 全量类别值 + query 文本；planner 以 `registry.for_categories({Category(c)...})` 裁剪工具、`json_mode=True` 产出 plan；executor 按 `tool.runtime` 分派（`Runtime.R`→`runner.run(r_script, args)`、否则 `tool.run(**args)`），每步 `{tool, status:"completed", result}`；reporter 产出 `report`（`json_mode` 缺省）；`build_graph` 集成终态含 `intent`/`categories`/`plan`/`steps`/`report`，四节点按序（router→planner→reporter，executor 不调 LLM）
  - 边界鲁棒：`_resolve_files` 只解析 `*_file` 结尾的 str 值成 `upload_dir` 绝对路径、非 str（如 int）不动；非法 file_id（非 uuid 如 `"abc"`、路径穿越 `"../etc/passwd"`）→ `ValueError`；eval 抽样用 `sample_rate=0.0`/`1.0` 两个极端验证确定性（不 mock `random`）
  - 回归保护：全 fake 注入（`LlmClient`/`ToolRegistry`/`RRunner`/`Database`/`RagClient`，不触真实 LLM/R/文件系统）；集成测试用真实 `langgraph` 编译验证图拓扑 `START→router→planner→executor→reporter→END`
- **所属系统**：编排（`backend/bioagent/orchestration/state.py` / `nodes.py` / `graph.py`）
- **阶段**：spec 09-orchestration 实现

### 10-api：FastAPI 端点 + 组合根

- **新增测试**：
  - `tests/test_api/test_api.py` — task CRUD 单元（`create_task`/`set_task_status`/`complete_task`/`fail_task`）4 条 + 端点集成（`/chat` 成功流、`/chat` 失败、`/chat` 空 message 422、`/tasks` 倒序、`/tasks/{id}` 详情 + 404、`/uploads` 成功/非法类型 415/超限 413、`/tools`）9 条，共 13 条
- **检查方向**：
  - 功能正确：`create_task` 写 task 一行（`status="pending"`、`plan/steps="[]"`、`report=""`）；`set_task_status` 更新 status + `updated_at`；`complete_task` 写 `status="completed"` + plan/steps（`json.dumps`）+ report；`fail_task` 写 `status="failed"` + error；`/chat` 用 fake graph（`astream` yield 预设 state）→ SSE `data:` 行流、末条 `{"done": true, task_id}`、task 置 completed；`/tasks` 按 `created_at` 倒序摘要、`/tasks/{id}` 返回完整 detail（plan/steps 已 `json.loads`）；`/uploads` 落盘 uuid 重命名 + 写 upload 表；`/tools` 返回工具元数据（name/category/runtime/input_schema/frontend）
  - 边界鲁棒：`/chat` 失败（fake `astream` 抛异常）→ 流末条含 `error`、task 置 `failed` 且 error 落库；`/chat` 空 message → 422（`min_length=1`）；`/uploads` 非法类型（`.xlsx`）→ 415、超限（monkeypatch `_MAX_UPLOAD_SIZE`）→ 413；`/tasks/nope` → 404
  - 回归保护：task CRUD 用真实 aiosqlite `:memory:`（验证 SQL 真落库）；端点集成用裸 `FastAPI` + 手动 `app.state`（**不跑 lifespan**）+ fake graph/registry 注入，不触真实 LLM/R/上传目录（`tmp_path` 当 `upload_dir`）；`/tools` 验证 `frontend` 字段透传
- **所属系统**：API 层（`backend/bioagent/main.py` / `api.py`）
- **阶段**：spec 10-api 实现

### 11-single-gene：单基因表达分析工具

- **新增测试**：
  - `tests/test_tools_single_gene/test_single_gene.py` — `run` 成功（3 基因 × 6 样本 TSV）1 条、JSON 可序列化 1 条、基因缺失 / 样本缺失 / 空组 `ValueError` 3 条、单样本组 `sd=None` 1 条、三组 `p_value=None` 1 条、`TOOL` 形状 1 条，共 8 条
- **检查方向**：
  - 功能正确：`run` 读 TSV 矩阵（`sep="\t", index_col=0`）按 `groups` 分组，算 `samples`（组→每样本值）+ `summary`（组→{n, mean, median, sd}）+ `p_value`（恰两组 t 检验）；`TOOL` 导出 `name`/`category`/`runtime`/`run`/`r_script` 契约
  - 边界鲁棒：基因名不在矩阵 / 样本名不在矩阵 / 空组（n=0）→ `ValueError`（消息含对应名）；单样本组（n=1）→ 该组 `sd=None` 且 `p_value=None`（非 `nan`）；组数非 2（给 3 组）→ `p_value=None` 但 `samples`/`summary` 仍返回
  - 回归保护：`json.dumps(result)` 不抛（numpy 标量已 `float()`/`.tolist()`，Python 原生 `float`/`int`），防 reporter `json.dumps` 炸；`TOOL` 形状断言防 `discover()` 误注册（`r_script is None` 确保 Python 工具契约）
- **所属系统**：单基因表达分析工具（`backend/bioagent/tools/single_gene/expression.py`）
- **阶段**：spec 11-single-gene 实现

### 12-dge：差异表达分析工具（R limma）

- **新增测试**：
  - `tests/test_tools_dge/test_dge.py` — `TOOL` 形状 1 条、`register()` 契约 1 条、R 脚本 stdin/stdout + limma 流程 1 条、样本对齐下限 1 条、样本校验 1 条，共 5 条
- **检查方向**：
  - 功能正确：`TOOL` 导出 `name`/`category`/`runtime`/`r_script`/`run`（R 工具 `run=None`）；`register()` 通过 R 工具契约校验（`r_script` 非空 + `run is None`）；R 脚本文本含 `fromJSON(file("stdin"))` → `lmFit` → `eBayes` → `topTable` → `cat(jsonlite::toJSON(...))` 完整 limma 流程（stdin 读 args JSON / stdout 输出 JSON）
  - 边界鲁棒：R 脚本含 `if (length(case) < 2 || length(control) < 2)` + `stop(...)`（退化输入走非零退出 → 06-r-runner 转 `RRuntimeError`）；含 `setdiff(c(args$case, args$control), colnames(mat))` 且缺失即 `stop`（样本名不在矩阵 → 非零退出）
  - 回归保护：字符串断言 R 脚本文本（不真跑 Rscript、不依赖真实 R/limma 环境，与 06-r-runner 一致）；`register()` 契约断言防 R 工具声明错误（`run` 非空或 `r_script` 空 → `ValueError`）
- **所属系统**：差异表达分析工具（`backend/bioagent/tools/dge/limma_dge.py` / `backend/bioagent/r_scripts/limma_dge.R`）
- **阶段**：spec 12-dge 实现

### 13-enrichment：富集分析工具（R clusterProfiler）

- **新增测试**：
  - `tests/test_tools_enrichment/test_enrichment.py` — `TOOL` 形状 1 条、`register()` 契约 1 条、R 脚本 core 流程 1 条、空基因列表 1 条，共 4 条
- **检查方向**：
  - 功能正确：`TOOL` 导出 `name`/`category`/`runtime`/`r_script`/`run`（R 工具 `run=None`）；`register()` 通过 R 工具契约校验；R 脚本文本含 `enrichGO`（`keyType = "SYMBOL"`/BP）、`enrichKEGG`（`tryCatch` 包裹 best-effort）、`cat(jsonlite::toJSON(...))` 完整富集流程
  - 边界鲁棒：R 脚本含 `if (length(genes) == 0)` + `stop("gene_list 为空")`（空输入走非零退出 → 06-r-runner 转 `RRuntimeError`）；KEGG 失败 `tryCatch` 返空 `data.frame()`（GO 不受影响，与 CLAUDE.md「best-effort 旁路」一致）
  - 回归保护：字符串断言 R 脚本文本（不真跑 Rscript、不依赖真实 clusterProfiler/org.Hs.eg.db 环境）；`register()` 契约断言防 R 工具声明错误
- **所属系统**：富集分析工具（`backend/bioagent/tools/enrichment/go_kegg.py` / `backend/bioagent/r_scripts/go_kegg.R`）
- **阶段**：spec 13-enrichment 实现

### 14-network：蛋白互作网络工具（Python networkx + STRING PPI）

- **新增测试**：
  - `tests/test_tools_network/test_ppi.py` — `run` 成功 1 条、JSON 可序列化 1 条、空基因列表 1 条、空 body 1 条、STRING 非 200 1 条、`TOOL` 形状 1 条，共 6 条
- **检查方向**：
  - 功能正确：`run` 调 `httpx.AsyncClient.get` 取 STRING `network` 端点 TSV，按 header 名（`preferredName_A`/`preferredName_B`/`score`，不依赖列顺序）解析、建 `nx.Graph`、只保留 gene_list 内部互作（`set` 成员判定 O(1)）；`nodes` 含所有 gene_list 节点（`id`+`degree`）、`edges` 含 `source`/`target`/`score`；`TOOL` 导出 Python 工具契约（`run` 非空、`r_script is None`）
  - 边界鲁棒：空 `gene_list` → `{"nodes": [], "edges": []}` 不抛；STRING 返回空 body → `lines` 空即返回节点全 degree 0 + 空边（`lines[0]` 不越界）；STRING 非 200 → `raise_for_status()` 抛 `httpx.HTTPStatusError`（不吞）；`degree` 是 `int`、`score` 是 `float`（`json.dumps` 不抛，无 numpy 类型）
  - 回归保护：`monkeypatch` `httpx.AsyncClient` 返回 fixture TSV（不真连 STRING）；fixture header 打乱列序（`score` 在前）验证按 header 名取列；1 行 target 不在 gene_list 内验证边过滤
- **所属系统**：网络药理工具（`backend/bioagent/tools/network/ppi.py`）
- **阶段**：spec 14-network 实现

### 15-survival：生存分析工具（R survival）

- **新增测试**：
  - `tests/test_tools_survival/test_survival.py` — `TOOL` 形状 1 条、`register()` 契约 1 条、R 脚本 core 流程 1 条、列名默认值回退 1 条、strata 切片 1 条、校验 1 条、序列化 1 条、cox 守卫 1 条，共 8 条
- **检查方向**：
  - 功能正确：`TOOL` 导出 R 工具契约（`r_script="km_cox.R"`、`run=None`）；`register()` 通过校验；R 脚本文本含 `Surv` → `survfit`（KM）→ `survdiff`（log-rank）→ `coxph`（Cox）→ `cat(jsonlite::toJSON(...))` 完整生存分析流程
  - 边界鲁棒：`time_col`/`event_col`/`group_col` 默认值回退（`is.null(args$x_col) ... else args$x_col`）；临床表缺列 `%in% colnames(clin)` 即 `stop`、`length(levels(group)) != 2` 非二组即 `stop`（退化输入非零退出 → 06-r-runner 转 `RRuntimeError`）；`summary(cox)$coefficients` 按 `nrow(cox_sum)` 守卫 + `"Pr(>|z|)"` 列名取 p（某组全删失不越界）
  - 回归保护：字符串断言 R 脚本文本（不真跑 Rscript、不依赖真实 survival 环境）；`seq_along(fit$strata)` + `fit$strata[i]` 切片还原每组 KM 曲线（spec 标注最易写错的点）；`jsonlite::unbox`（标量显式 unbox）+ `levels(group)[i]`（group 名去前缀）
- **所属系统**：生存分析工具（`backend/bioagent/tools/survival/km_cox.py` / `backend/bioagent/r_scripts/km_cox.R`）
- **阶段**：spec 15-survival 实现

### 16-frontend：前端（React + Vite + TS + ECharts + Tailwind）

- **新增测试**：
  - `src/charts/options.test.ts` — 五种 `*Option` 纯函数各 1 条（boxplot/volcano/barplot/network/km_curve 返回确定性 option、`series.type` 正确、空 genes 空 series 不抛）+ boxplot 中位数取 `summary.median` 1 条 + volcano p=0 不产生 Infinity 1 条 + barplot p=0 不产生 Infinity 1 条，共 8 条
  - `src/hooks/useSSE.test.ts` — 逐帧 onEvent + done 结束 1 条、非 200 置 error 并 reject 1 条、stop() 中止 reader 1 条，共 3 条
  - `src/stores/chatStore.test.ts` — send 入消息/快照随帧更新/report 后 done 1 条、error 帧 → status error 1 条，共 2 条
  - `src/components/ResultChart.test.tsx` — limma_dge→volcano→scatter 分发 1 条、未知 result_type→JSON 不崩 1 条，共 2 条
  - `src/components/FileUpload.test.tsx` — 选文件→upload→fileId 1 条
  - `src/components/StepList.test.tsx` — 失败任务时已完成步骤仍 ✓、未执行步骤 ✗ 1 条
  - `src/components/ChatPanel.test.tsx` — report（markdown 渲染为 heading）与纯文字步骤结果渲染在对话 1 条
  - `src/stores/taskStore.test.ts` — `open` 取回任务并把 plan/steps/report 回填主视图（`chatStore.currentState`/`status="done"`）1 条、失败任务回填 `status="error"` 1 条，共 2 条
- **检查方向**：
  - 功能正确：五种 `*Option` 是纯函数（同输入同输出、含期望 `series.type`、`xAxis`/`yAxis` 等关键字段无 `undefined`）；`useSSE` 的 `run` POST 后按 `\n\n` 切帧、剥 `data: ` 前缀 JSON.parse，done 帧 resolve / error 帧 reject / 否则 `onEvent(快照)`；`chatStore.send` 入用户消息 + 逐帧写 `currentState`、report 出现后 `status="done"`；`taskStore.open` 取 `TaskDetail` 后把 plan/steps/report 回填 `chatStore.currentState`（复用主视图渲染），失败任务回填 `status="error"`；`ResultChart` 按 `tool→result_type` 分发到对应 `*Option`，未知类型回退 JSON；`ChatPanel` 把 report 经 react-markdown 渲染、纯文字步骤结果渲染为 JSON 气泡（App 按 `result_type` 是否图表分流：图表进「结果」、纯文字进「对话」）；`FileUpload` 选文件后调 `client.upload` 写 `fileId`
  - 边界鲁棒：`volcanoOption` 空 genes 返空 series 不抛、p=0 时 `-log10` clamp 不产生 Infinity；`barplotOption` p=0 时同样 `-log10` clamp 不产生 Infinity；`boxplotOption` 中位数取 `summary.median`（非 floor 下标）、q1/q3 线性插值；`useSSE` 非 200 置 `error` 并 reject、error 帧 `reader.cancel()` 后 reject；`stop()` 调 `reader.cancel()` 中止读取；`ResultChart` 未知 result_type 渲染 `<pre>` JSON 而非崩；`StepList` 失败任务时已完成步骤仍 ✓
  - 回归保护：mock 全局 `fetch`（`vi.stubGlobal`）返回 fake 流（`vi.fn` 逐步 yield 帧），不真连后端；`ResultChart` mock `ECharts` 组件（echarts `init` 在 jsdom 无 canvas 会失败），断言 series.type 而非真实渲染；`FileUpload` mock `client.upload`；`taskStore` mock `client.getTask` 返回预设 `TaskDetail`，断言跨 store 回填而非真实 HTTP；测试不依赖真实 ECharts/DOM 布局
- **所属系统**：前端（`frontend/src/{charts,hooks,stores,components}`）
- **阶段**：spec 16-frontend 实现

### multi-turn（多轮上下文）：DB 迁移 v2 —— `message` 表

- **新增测试**：
  - `tests/test_db/test_db.py` — `test_migrate_message_table_columns` 新增；`test_migrate_creates_all_tables_and_indexes` / `test_migrate_idempotent` 期望集合加入 `message` 表与 `idx_message_conversation` 索引；`test_migrate_incremental_gate` 改为追加 v3（真实 `_MIGRATIONS` 已达 v2）；`_table_names` helper 排除 `sqlite_%` 内部表
- **检查方向**：
  - 功能正确：v2 迁移建 `message` 表（`AUTOINCREMENT` PK、`conversation_id`/`role`/`content` NOT NULL、`created_at REAL`）与索引 `idx_message_conversation(conversation_id, created_at)`，`schema_version` 最高版本推进到 2
  - 边界鲁棒：`AUTOINCREMENT` 触发的 SQLite 内部 `sqlite_sequence` 表被 helper 过滤，不混入业务表集合
  - 回归保护：版本门控测试用追加 v3 验证只套未应用版本
- **所属系统**：数据库（`backend/bioagent/db.py`）
- **阶段**：多轮上下文阶段

### multi-turn（多轮上下文）：api message 持久化助手

- **新增测试**：
  - `tests/test_api/test_api.py` — `test_append_and_list_messages`（功能正确，api 系统，多轮上下文阶段）
- **检查方向**：
  - 功能正确：`append_message` 写 `message` 一行（`conversation_id`/`role`/`content`/`created_at`）并 commit；`list_messages` 按 `created_at ASC, id ASC` 只取某 `conversation_id` 的 `role`/`content`，元素形如 `{"role": ..., "content": ...}`；跨对话隔离（conv-2 不入 conv-1）；无历史对话返回 `[]`
- **所属系统**：API 层（`backend/bioagent/api.py`）
- **阶段**：多轮上下文阶段

### multi-turn（多轮上下文）：state/nodes 注入 history

- **新增测试**：
  - `tests/test_orchestration/test_orchestration.py` — `test_router_node_includes_history`（功能正确，orchestration 系统，多轮上下文阶段）
- **检查方向**：
  - 功能正确：`_with_history` 产出 `[system] + history`（user/assistant 交替、当前 query 含在 prompt 内）；router 带 `history` 时 `messages[1]`/`messages[2]` 为前轮 user/assistant 消息；空 `history` 退化为单条 system（既有节点测试保持绿）
- **所属系统**：编排（`backend/bioagent/orchestration/state.py` / `nodes.py`）
- **阶段**：多轮上下文阶段

### multi-turn（多轮上下文）：/chat 端点接线（conversation_id + history + 落库）

- **新增测试**：
  - `tests/test_api/test_api.py` — `test_chat_persists_conversation_and_injects_history`（功能正确，api 系统，多轮上下文阶段）、`test_chat_generates_new_conversation_when_absent`（边界鲁棒，api 系统，多轮上下文阶段）
- **检查方向**：
  - 功能正确：带 `conversation_id` 的请求复用该对话——`list_messages` 已存历史注入 `graph.initial["history"]`（user/assistant 交替）、成功轮次把本轮 Q&A 追加到 `message` 表、SSE 结束帧携带 `conversation_id`；`initial` 同时含 `query`/`correlation_id`/`conversation_id`/`history`
  - 边界鲁棒：缺省 `conversation_id` 时 `/chat` 生成新 `uuid`，结束帧返回该 id、`list_messages` 返回本轮 user + assistant 两条
- **所属系统**：API 层（`backend/bioagent/api.py`）
- **阶段**：多轮上下文阶段

### multi-turn（多轮上下文）：chatStore conversationId + assistant 消息 + reset

- **新增测试**：
  - `src/stores/chatStore.test.ts` — 改写 `send` 测试（入消息、快照随帧更新、report 后追加 assistant 消息、`conversation_id` 进请求体）1 条、新增 `reset` 测试（清空消息并生成新 conversationId）1 条
- **检查方向**：
  - 功能正确：`send` 把 `conversation_id`（`get().conversationId`）一并 POST 进 `/chat` 请求体；SSE 结束帧后把最后一帧 report 追加为 `messages` 里的 assistant 消息（`{role:'assistant', content: report}`）；`reset` 清空 `messages` 并生成新 `conversationId`（`crypto.randomUUID()`）、`currentState`/`status` 归位
- **所属系统**：chatStore（`frontend/src/stores/chatStore.ts`）
- **阶段**：多轮上下文阶段

### multi-turn（多轮上下文）：ChatPanel 从 messages 渲染 + App 新对话按钮

- **新增测试**：
  - `src/components/ChatPanel.test.tsx` — 改写为无 props（读 store）测试：`messages` 里的 assistant markdown 经 react-markdown 渲染为 heading 与链接 1 条
- **检查方向**：
  - 功能正确：`ChatPanel` 无 props（内部 `useChatStore` 读 `messages`/`status`/`send`），assistant 消息走 `ReactMarkdown`（`remarkGfm`）渲染（`# 分析报告` → heading、`[KEGG](https://kegg.jp)` → 链接文本）；App 不再传 `report`/`textSteps`，对话头部新增「新对话」按钮调 `useChatStore.getState().reset()`
- **所属系统**：ChatPanel（`frontend/src/components/ChatPanel.tsx` / `frontend/src/App.tsx`）
- **阶段**：多轮上下文阶段

### multi-turn（多轮上下文）：taskStore.open 回看回填 messages

- **新增测试**：
  - `src/stores/taskStore.test.ts` — 改写 `open` 测试（取回任务并把内容回填主视图与对话，追加 `c.messages` 断言）1 条
- **检查方向**：
  - 功能正确：`taskStore.open` 取 `TaskDetail` 后把 plan/steps/report 回填 `chatStore.currentState`（复用主视图渲染），并把该任务 `userMessage` + `report` 追加进 `chatStore.messages`（`{role:'user'}` / `{role:'assistant'}`），使回看报告继续显示在对话面板；失败任务仍回填 `status="error"`
- **所属系统**：taskStore（`frontend/src/stores/taskStore.ts`）
- **阶段**：多轮上下文阶段
