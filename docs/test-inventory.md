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
