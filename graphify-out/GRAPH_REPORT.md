# Graph Report - bio_test  (2026-09-29)

## Corpus Check
- 119 files · ~65,305 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2102 nodes · 5472 edges · 99 communities (85 shown, 6 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 725 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Frontend Bundle 0
- Frontend Bundle 1
- Frontend Bundle 2
- Frontend Bundle 3
- Frontend Bundle 4
- Frontend Bundle 5
- Data and File Tools
- Frontend Bundle 7
- Frontend Bundle 8
- Recovery Strategies
- Tool Registry Routing
- Tool Lifecycle Tests
- Frontend Bundle 12
- Tool Result Tests
- Bioinformatics R Tools
- Frontend Bundle 15
- Frontend Bundle 16
- Tool Result Protocol
- Frontend Bundle 18
- Session Context Memory
- Database CRUD Models
- Frontend Bundle 21
- Tool Registration Tests
- Frontend Bundle 23
- Skill System Tests
- System Architecture Concepts
- Frontend Bundle 26
- Agent Orchestration
- Chat File Responses
- Agent Utility Tests
- Executor Agent Flow
- Skill Models Loading
- Session Cleanup API
- Bio Agent Pipeline
- Frontend Bundle 34
- Frontend Bundle 35
- Frontend Bundle 36
- Frontend Bundle 37
- Commands and Delegation
- Skill Pack Tests
- Upload File Service
- Frontend Bundle 41
- Runtime System Paths
- Frontend Bundle 43
- Core Data Skills
- Frontend Bundle 45
- Agent Utilities
- Lifecycle Hooks
- Waterfall Racing
- FastAPI History API
- Literature Tools
- R Preprocessing Tools
- Skill Selection Logic
- Skill Loader
- Frontend Bundle 54
- Parallel Tool Execution
- Frontend Bundle 56
- Structured Rules Engine
- Skill Export
- Pydantic Tool Examples
- Skill Improvement Logs
- Tool Execution Context
- File URL Utilities
- Machine Learning Skills
- Tool Lifecycle Bridge
- Tool Audit Logging
- Product Architecture Overview
- Enrichment Skills
- Single Cell Skills
- Survival Skills
- Frontend Bundle 70
- Network Pharmacology Skills
- Frontend Bundle 72
- Engineering Guidelines
- Regression Test Inventory
- Modeling Skills
- Spatial Skills
- Session File Lookup
- Root Dependencies
- Aptamer Skills
- Docking Skills
- Drug Screening Skills
- Literature Report Skills
- Perturbation Skills
- Single Gene Skills
- Frontend Bundle 85
- Backend Dependencies
- Vite Brand Asset
- R Integration Design
- Rules Engine Design
- Persistence Design

## God Nodes (most connected - your core abstractions)
1. `n()` - 176 edges
2. `t()` - 101 edges
3. `l()` - 77 edges
4. `i()` - 74 edges
5. `r()` - 73 edges
6. `jx()` - 69 edges
7. `register_tool()` - 65 edges
8. `s()` - 56 edges
9. `u()` - 55 edges
10. `o()` - 54 edges

## Surprising Connections (you probably didn't know these)
- `Memory System` --semantically_similar_to--> `Session Memory`  [INFERRED] [semantically similar]
  docs/mindmap.html → TECHNICAL_DOCUMENTATION.md
- `Agent System` --semantically_similar_to--> `BioAI Request Pipeline`  [INFERRED] [semantically similar]
  docs/mindmap.html → TECHNICAL_DOCUMENTATION.md
- `Bio Agent SPA Shell` --implements--> `Vite React SPA`  [INFERRED]
  backend/static/index.html → README.md
- `run_bio_agent()` --calls--> `run_delegator_agent()`  [INFERRED]
  backend/app/agent/bio_agent.py → backend/app/agent/delegator_agent.py
- `run_bio_agent()` --uses--> `SkillSpec`  [INFERRED]
  backend/app/agent/bio_agent.py → backend/app/agent/skills/skill_models.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **BioAI Multi-Agent Pipeline** — technical_documentation_router_agent, technical_documentation_skill_select, technical_documentation_planner_agent, technical_documentation_delegator_agent, technical_documentation_executor_agent, technical_documentation_reporter_agent [EXTRACTED 1.00]
- **Tool Execution Reliability System** — technical_documentation_tool_lifecycle, technical_documentation_toolresult_protocol, technical_documentation_resource_monitor, technical_documentation_recovery_strategies, technical_documentation_hook_system [EXTRACTED 1.00]
- **BioAI Architecture Pillars** — docs_mindmap_agent_system, docs_mindmap_tool_system, docs_mindmap_memory_system [EXTRACTED 1.00]

## Communities (99 total, 6 thin omitted)

### Community 0 - "Frontend Bundle 0"
Cohesion: 0.02
Nodes (114): _0(), A1(), al, aw(), b, b0(), bk, bt (+106 more)

### Community 1 - "Frontend Bundle 1"
Cohesion: 0.04
Nodes (74): p(), ax(), i(), r(), v(), y(), d(), cv() (+66 more)

### Community 2 - "Frontend Bundle 2"
Cohesion: 0.04
Nodes (45): T(), O(), oe(), R(), S(), X(), I(), L() (+37 more)

### Community 3 - "Frontend Bundle 3"
Cohesion: 0.07
Nodes (67): j(), Es(), a(), f(), s(), u(), hx(), i() (+59 more)

### Community 4 - "Frontend Bundle 4"
Cohesion: 0.07
Nodes (59): ak(), a(), c(), d(), E(), f(), g(), h() (+51 more)

### Community 5 - "Frontend Bundle 5"
Cohesion: 0.05
Nodes (59): a(), t(), a(), o(), s(), u(), ds(), f0() (+51 more)

### Community 6 - "Data and File Tools"
Cohesion: 0.08
Nodes (54): _build_preview_response(), _count_csv_rows(), _count_text_table_rows(), load_large_bio_data(), preview_table_file(), 统计文本表格数据行数。 返回值不包含 header 行。, CSV 行数统计。 不把整个文件读入内存。 返回值不包含 header 行。, read_csv_data() (+46 more)

### Community 7 - "Frontend Bundle 7"
Cohesion: 0.05
Nodes (52): ah(), c(), f(), p(), s(), bs(), cy(), dd() (+44 more)

### Community 8 - "Frontend Bundle 8"
Cohesion: 0.06
Nodes (49): t(), s(), ci(), Co(), cp(), da(), Dp(), dv (+41 more)

### Community 9 - "Recovery Strategies"
Cohesion: 0.07
Nodes (19): ABC, ColumnMissingRecovery, DependencyRecovery, EncodingRecovery, FileParseRecovery, Any, 统一工具恢复/重试策略系统 (Feature 3: Retry Strategies). 将 executor_agent.py…, 检测到文件读入/解析错误时，自动调用 probe_unknown_file 探测文件格式。 触发条件：结果文本包含 file not found /… (+11 more)

### Community 10 - "Tool Registry Routing"
Cohesion: 0.08
Nodes (45): categories_from_preferred_tools(), collect_preferred_tools_from_plan(), filter_tools_schema_by_effective_categories(), filter_tools_schema_by_plan(), get_effective_tool_category(), infer_categories_from_text(), infer_category_from_tool_name(), normalize_categories() (+37 more)

### Community 11 - "Tool Lifecycle Tests"
Cohesion: 0.09
Nodes (39): create_tool_context(), 工厂函数：创建 ToolExecutionContext。 自动生成 job_id 和 job_dir。 Args: tool_name: 工具名…, collect_generated_files(), execute_recovery_strategies(), _inject_lifecycle_args(), Any, 扫描 job_dir 下所有文件，返回标准文件列表。 支持递归扫描，跳过目录。 Returns: List of file dicts compatible…, 将生命周期相关参数注入工具函数参数中。 如果工具函数签名包含以下参数名，则自动注入： - session_id → context.session_id -… (+31 more)

### Community 12 - "Frontend Bundle 12"
Cohesion: 0.08
Nodes (43): ac(), ar(), ay(), ba(), cn(), ct(), t(), dy() (+35 more)

### Community 13 - "Tool Result Tests"
Cohesion: 0.10
Nodes (41): normalize_tool_result(), 将任意工具返回归一化为标准 ToolResult。 这是 Executor 调用工具后必须调用的统一入口。 支持输入： 1. 已经是 ToolResult →…, _assert(), _assert_equal(), Phase 1: ToolResult 统一工具返回格式 单元测试。 运行方式（在 backend 目录下）： python -m pytest…, JSON 字符串应被解析为 dict 再归一化。, 确保 output_files 被正确提取。, 无 output_files 时为空列表。 (+33 more)

### Community 14 - "Bioinformatics R Tools"
Cohesion: 0.14
Nodes (31): 工具注册装饰器。 【旧写法 - 仍兼容】 @register_tool(name="xxx", description="xxx",…, register_tool(), calculate_gc_content(), run_go_kegg_enrichment(), run_gsea_analysis(), run_gsva_analysis(), run_virtual_knockdown_bulk_analysis(), build_expression_preprocess_r() (+23 more)

### Community 15 - "Frontend Bundle 15"
Cohesion: 0.09
Nodes (36): _1(), b1(), bh(), bx(), dh(), dt(), gk(), f() (+28 more)

### Community 16 - "Frontend Bundle 16"
Cohesion: 0.08
Nodes (37): au(), bd(), bm(), bo(), bu(), Dl(), fd(), gl() (+29 more)

### Community 17 - "Tool Result Protocol"
Cohesion: 0.13
Nodes (34): _ensure_tool_result_types(), 延迟导入 ToolResult 类型，避免循环引用。, _build_from_plain_value(), _coerce_output_file(), _extract_output_files_from_list(), _is_json_safe(), make_error_result(), make_success_result() (+26 more)

### Community 18 - "Frontend Bundle 18"
Cohesion: 0.11
Nodes (34): d(), p(), bv(), a(), f(), s(), ew(), g0() (+26 more)

### Community 19 - "Session Context Memory"
Cohesion: 0.11
Nodes (30): build_session_memory_system_message(), clear_all_session_memory(), clear_session_memory(), compact_output_files(), debug_get_session_memory(), _empty_session_state(), enrich_context_with_session_memory(), extract_numbered_choices() (+22 more)

### Community 20 - "Database CRUD Models"
Cohesion: 0.11
Nodes (30): create_session(), delete_file_records_by_session(), delete_generated_file_records_by_session(), delete_messages_by_session(), delete_session_record(), delete_tool_executions_by_session(), delete_upload_file_records_by_session(), ensure_session_title() (+22 more)

### Community 21 - "Frontend Bundle 21"
Cohesion: 0.10
Nodes (21): cl(), Gh(), hf(), jo, Mv(), r(), of(), Ps() (+13 more)

### Community 22 - "Tool Registration Tests"
Cohesion: 0.10
Nodes (23): auto_discover_tools(), _discover_in_path(), list_discovered_tools(), 工具自动发现模块。 自动扫描 app.tools 包下所有 .py 模块并触发工具注册。 跳过 __init__.py，支持递归子目录，避免重复注册。, 列出所有已注册工具的摘要。 Returns: {tool_name: {category, schema_source, tags}}, 自动发现并导入指定包下的所有工具模块。 递归扫描子包，跳过 __init__.py 和已加载模块。 Args: package_name: 包全限定名，默认…, _assert(), _assert_equal() (+15 more)

### Community 23 - "Frontend Bundle 23"
Cohesion: 0.12
Nodes (31): bn(), Ca(), ce(), gd(), hd(), hr(), Ia(), Il() (+23 more)

### Community 24 - "Skill System Tests"
Cohesion: 0.15
Nodes (28): 注册所有内置 Skill。 优先从 YAML packs 加载，失败时使用 Python fallback。 返回注册的 skill_id 列表。, register_all_builtin_skills(), find_skills_by_task_type(), get_skill(), 根据 skill_id 获取 Skill。, 按 task_type 和 subtask_type 查找 Skill。 匹配优先级（只返回最高优先级匹配）： 1. task_type +…, _assert(), _assert_equal() (+20 more)

### Community 25 - "System Architecture Concepts"
Cohesion: 0.07
Nodes (29): Agent System, Memory System, Session Key Validation and Isolation, Short Reply Resolution, Skill Router Multidimensional Scoring, BioAI Agent v2.0 System Architecture, Tool System, Turn Write-Back (+21 more)

### Community 26 - "Frontend Bundle 26"
Cohesion: 0.09
Nodes (19): ch(), fh(), t(), fw(), fx(), hh(), hk(), Jl() (+11 more)

### Community 27 - "Agent Orchestration"
Cohesion: 0.13
Nodes (16): _collect_all_files(), KanbanTask, Orchestrator, Any, Enum, 多Agent 编排器 (Phase 3.3: Kanban Orchestrator). 参考 Hermes agent 的 Kanban 多Agent…, 执行所有任务，按依赖分批。 Returns: { "completed": [...], "failed": [...], "blocked": [...],…, Kanban 编排器。 管理多步骤生信分析流程: 1. 添加任务（带依赖声明） 2. 按批次执行（TODO → IN_PROGRESS → DONE） 3.… (+8 more)

### Community 28 - "Chat File Responses"
Cohesion: 0.12
Nodes (24): append_files_markdown(), build_uploaded_files_context(), dedupe_files(), extract_file_marker_from_message(), generate_session_title(), handle_chat(), merge_files(), normalize_agent_file() (+16 more)

### Community 29 - "Agent Utility Tests"
Cohesion: 0.13
Nodes (23): is_error_result(), 读取对象/字典的 status 字段并小写；无 status 时返回空串。, result_status(), _assert(), _assert_equal(), _Plain, BaseModel, Phase 2: 重复逻辑合并 — to_plain_dict / result_status / is_error_result 单元测试。 运行方式（在… (+15 more)

### Community 30 - "Executor Agent Flow"
Cohesion: 0.17
Nodes (25): 把 Pydantic 模型（v1/v2）或 dict 解包为普通 dict。 None / 非 dict 且无 model_dump/dict 的对象返回…, safe_json_loads(), to_plain_dict(), build_executor_messages(), _coerce_to_text(), dedupe_output_files(), _extract_error_pattern(), get_effective_max_tool_rounds() (+17 more)

### Community 31 - "Skill Models Loading"
Cohesion: 0.15
Nodes (19): Built-in Skills - 现在从 YAML packs 加载。 加载方式： from app.agent.skills.builtin_skills…, Skill System - Higher-level task capability packages. A Skill encapsulates: -…, Any, Convert a YAML dict into a SkillSpec instance., _yaml_dict_to_skillspec(), parse_clarification(), parse_examples(), parse_params() (+11 more)

### Community 32 - "Session Cleanup API"
Cohesion: 0.14
Nodes (21): chat_endpoint(), delete_chat_session_endpoint(), _force_delete_session_files(), delete, Path, post, Session, _safe_remove_tree() (+13 more)

### Community 33 - "Bio Agent Pipeline"
Cohesion: 0.17
Nodes (16): maybe_add_markdown_guidance(), remove_fake_markdown_images(), sanitize_final_answer(), _dedupe_files(), _make_agent_result(), Any, 去重文件列表，避免同一个文件被重复返回给前端。, 统一 Agent 返回格式。 重要： 以前 run_bio_agent 只返回字符串 final_answer， 导致 chat_service… (+8 more)

### Community 34 - "Frontend Bundle 34"
Cohesion: 0.10
Nodes (22): a0(), s(), aS(), bc(), C1(), Cf(), cr(), eh() (+14 more)

### Community 35 - "Frontend Bundle 35"
Cohesion: 0.11
Nodes (23): ae(), gw(), i(), l(), kw(), i(), l(), r() (+15 more)

### Community 36 - "Frontend Bundle 36"
Cohesion: 0.15
Nodes (21): ai(), i(), cc(), cd(), dn(), Ea(), Fa(), fc() (+13 more)

### Community 37 - "Frontend Bundle 37"
Cohesion: 0.13
Nodes (21): _d(), Ey(), Gf(), hn(), It(), iu(), ju(), kc() (+13 more)

### Community 38 - "Commands and Delegation"
Cohesion: 0.16
Nodes (17): extract_json_object(), build_help_response(), Any, 斜杠命令系统 (Phase 5.3: Slash Commands). 参考 ECC 的 92 个 slash commands，提供快捷命令直接映射到…, 解析用户消息中的斜杠命令。 如果消息以 / 开头且匹配已知命令，返回命令的元信息。 否则返回 None（走正常 Router 流程）。 Returns:…, resolve_command(), Any, Delegator Agent (Phase 3.2). 在 Planner 之后判断复杂任务是否应拆分为子Agent 并行执行。 参考 Hermes… (+9 more)

### Community 39 - "Skill Pack Tests"
Cohesion: 0.21
Nodes (19): _apply_skill_tool_filter(), 根据 Skill.allowed_tools 白名单过滤工具 schema。 规则： 1. 如果 skill 没有 allowed_tools → 不过滤…, ensure_skills_loaded(), 确保内置 Skills 已从 YAML packs 加载。 幂等：如果 SKILL_REGISTRY 已有 skill，只补充尚未加载的。 首次调用时从…, load_all_skill_packs(), Load all skill packs and return summary., _assert(), _assert_equal() (+11 more)

### Community 40 - "Upload File Service"
Cohesion: 0.17
Nodes (18): get_uploaded_files(), delete, get, post, Session, remove_uploaded_file(), upload_files(), delete_uploaded_file() (+10 more)

### Community 41 - "Frontend Bundle 41"
Cohesion: 0.14
Nodes (19): _a(), Bi(), Du(), _h(), ja(), jp(), l0(), Lo() (+11 more)

### Community 42 - "Runtime System Paths"
Cohesion: 0.19
Nodes (15): get, system_info(), build_r_subprocess_env(), check_rscript_version(), find_rscript(), get_backend_root(), get_project_root(), Path (+7 more)

### Community 43 - "Frontend Bundle 43"
Cohesion: 0.18
Nodes (16): Bp(), a(), c(), f(), n(), s(), u(), Do() (+8 more)

### Community 44 - "Core Data Skills"
Cohesion: 0.13
Nodes (18): Advanced Bio Skill Pack, 批次效应校正 [planned], Bulk RNA-seq PCA 分析 [implemented], DESeq2 原始 count 差异分析 [implemented], GEO 数据下载与预处理 [implemented], 免疫浸润分析 [planned], 时间序列表达分析 [planned], Core File Skill Pack (+10 more)

### Community 45 - "Frontend Bundle 45"
Cohesion: 0.12
Nodes (16): ao(), Ei(), Hm(), im(), lm(), Lr(), Mp(), Nf() (+8 more)

### Community 46 - "Agent Utilities"
Cohesion: 0.26
Nodes (14): build_compact_tool_summary(), build_file_display_hint(), _dedupe_output_files(), extract_output_files(), get_real_image_urls(), _normalize_output_file_item(), parse_tool_result(), Any (+6 more)

### Community 47 - "Lifecycle Hooks"
Cohesion: 0.16
Nodes (11): _default_cleanup_temp_files(), _default_error_notification(), HookManager, HookPoint, Any, Enum, Hook 系统 (Phase 5.2: Event-Based Automation). 参考 ECC 的 Hooks…, 轻量级 Hook 管理器。 支持同步和异步回调。 回调失败不传播异常——单个 Hook 失败不影响其他 Hook 或主流程。 (+3 more)

### Community 48 - "Waterfall Racing"
Cohesion: 0.17
Nodes (15): _find_racing_candidates(), get_racing_candidates_for_step(), _get_racing_group(), _is_success(), Any, race_tools(), RaceResult, Waterfall Racing 竞速执行器 (Phase 1.2). 参考 Firecrawl 的 "多引擎竞速" 模式:… (+7 more)

### Community 49 - "FastAPI History API"
Cohesion: 0.19
Nodes (13): get_history(), list_history(), get, Session, get_all_sessions(), get_session_files(), get_session_messages(), get_db() (+5 more)

### Community 50 - "Literature Tools"
Cohesion: 0.26
Nodes (16): _auto_route_sources(), _build_result(), _clamp_max_results(), download_open_access_pdf(), fetch_paper_details(), _is_http_url(), _normalize_text(), 校验 URL 是否为 http/https 协议，防止 SSRF（file://、非 http 重定向等）。 (+8 more)

### Community 51 - "R Preprocessing Tools"
Cohesion: 0.21
Nodes (13): run_ml_classification_model(), run_ml_feature_selection_lasso(), run_multi_model_comparison(), build_feature_df_preprocess_r(), build_matrix_preprocess_r(), build_single_value_preprocess_r(), 用于表达矩阵预处理。 适用场景： - 表达矩阵相关性 - bulk PCA - limma 连续表达矩阵差异分析 - GSVA 类矩阵输入 R 侧输出： -…, 用于机器学习特征表预处理。 适用场景： - 机器学习分类 - LASSO 特征筛选 - 多模型比较 注意： - ML 特征不一定是表达值，所以额外支持… (+5 more)

### Community 52 - "Skill Selection Logic"
Cohesion: 0.22
Nodes (14): _create_fallback_skills(), 当 YAML 加载失败时，创建旧版硬编码 Skill 作为 fallback。 正常情况下不调用此函数。, 技能规格定义。 一个 Skill 封装了某类生信任务的完整元信息： - 何时触发 - 需要什么输入 - 使用什么 workflow - 暴露哪些工具 -…, SkillSpec, Any, Skill Router — score and select the best matching Skill. Scoring dimensions…, 根据 Router 的 task_type / subtask_type 打分。, 根据用户消息和 Router 结果选择最佳 Skill。 Args: latest_user_message: 用户最新消息 router_result:… (+6 more)

### Community 53 - "Skill Loader"
Cohesion: 0.24
Nodes (14): _get_packs_dir(), load_skill_pack_dir(), load_skills_from_directory(), load_skills_from_markdown(), load_skills_from_yaml(), Path, YAML Skill Pack Loader. Loads SkillSpec definitions from YAML files, converting…, 从 SKILL.md 文件加载技能定义。 格式: YAML frontmatter + Markdown body --- skill_id:… (+6 more)

### Community 54 - "Frontend Bundle 54"
Cohesion: 0.17
Nodes (15): ad(), Ap(), Hg(), ma(), sd(), tl(), ud(), Up() (+7 more)

### Community 55 - "Parallel Tool Execution"
Cohesion: 0.24
Nodes (13): execute_parallel_steps(), _execute_single_step(), _extract_files_from_result(), Any, 依赖感知并行执行器 (Phase 1.1: Parallel Tool Execution). 将 Planner 输出的步骤按依赖关系分组并行执行。 参考…, 从步骤的 preferred_tools 中选择第一个可用的工具。 若 step 有 "tool" 字段直接使用。, 按批次并行执行步骤。 Args: batches: 拓扑排序后的批次 available_tool_names: 可用工具名集合 session_id: 会话…, 执行单个 Planner 步骤。 返回 (observations, output_files)。 (+5 more)

### Community 56 - "Frontend Bundle 56"
Cohesion: 0.22
Nodes (5): df(), Gv(), sh(), c(), f()

### Community 57 - "Structured Rules Engine"
Cohesion: 0.23
Nodes (8): _init_core_rules(), BaseModel, 结构化规则引擎 (Phase 5.1: Rules Engine). 参考 ECC 的 Rules 系统，将 task_prompts.py 中硬编码的规则…, 规则引擎：按 Agent 角色和工具有类别过滤并格式化规则。, 获取当前上下文下应激活的规则。 Args: categories: 当前工具类别列表（如 ["survival", "file_io"]）…, 将规则列表格式化为 prompt 可用的文本块。, Rule, RulesEngine

### Community 58 - "Skill Export"
Cohesion: 0.23
Nodes (11): _build_markdown_body(), export_all_skills(), export_skill_to_markdown(), Any, 技能导出工具 (Phase 2.3: Marketplace 准备). 将已注册 Skill 导出为独立的 SKILL.md 文件， 格式兼容…, 将单个 Skill 导出为 SKILL.md 文件。 Args: skill: SkillSpec 实例 output_path: 输出文件路径（.md）…, 将所有已注册 Skill 导出为独立 SKILL.md 文件。 Args: output_dir: 输出目录 enabled_only: 只导出启用的…, 将 SkillSpec 转为 YAML frontmatter 字典。 (+3 more)

### Community 59 - "Pydantic Tool Examples"
Cohesion: 0.17
Nodes (10): calculate_gc_content_v2(), count_sequence_bases(), GCContentParams, BaseModel, Phase 3 示例：使用 Pydantic params_model 注册工具。 演示三种注册方式： 1. 旧写法：显式 parameters dict…, 反向互补（旧 parameters dict 示例）。, 计算 GC 含量（Pydantic params_model 示例）。 session_id 和 job_dir 由生命周期自动注入，不出现在 OpenAI…, 统计碱基数量（函数签名自动生成 schema 示例）。 (+2 more)

### Community 60 - "Skill Improvement Logs"
Cohesion: 0.31
Nodes (10): analyze_and_suggest(), clear_logs(), _ensure_log_dir(), get_stats(), Any, 技能自改进反馈循环 (Phase 4.4: Self-Improvement). 参考 Hermes agent 的自主 Skill 创建和自改进机制。…, 记录一次工具有失败，用于后续分析。 Args: tool_name: 工具名 error_pattern: 错误描述（简短关键词，如 "missing…, 分析失败日志，生成改进建议。 Returns: 建议列表，每条包含: { "type": "clarification_rule" |… (+2 more)

### Community 61 - "Tool Execution Context"
Cohesion: 0.27
Nodes (7): _make_job_dir(), Any, Path, 工具执行上下文 ToolExecutionContext。 统一工具执行时的元数据容器： - job_id / job_dir 自动生成 -…, 工具执行上下文。 包含： - job_id: 本次工具调用的唯一 ID - session_id: 会话 ID - tool_name: 工具名 -…, _safe_path_segment(), ToolExecutionContext

### Community 62 - "File URL Utilities"
Cohesion: 0.31
Nodes (9): _guess_file_type(), build_file_url(), 根据相对路径生成可访问 URL。 例如 generated/pheno_analysis/a.png ->…, _assert_equal(), Phase 2: 重复逻辑合并 — build_file_url 单元测试。 运行方式（在 backend 目录下）： python -m pytest…, 相对路径拼接为 /files/ 前缀 URL。, test_build_file_url_basic(), test_build_file_url_edge_cases() (+1 more)

### Community 63 - "Machine Learning Skills"
Cohesion: 0.25
Nodes (9): LASSO 特征选择 [implemented], Machine Learning Skill Pack, 二分类机器学习模型 [implemented], 多模型比较 [implemented], SHAP 模型解释 [planned], 生存机器学习模型 [planned], LASSO 特征选择 [implemented], Advanced ML Skill Pack (+1 more)

### Community 64 - "Tool Lifecycle Bridge"
Cohesion: 0.28
Nodes (5): 工具执行资源消耗快照 (Feature 1: Resource Limits)., ResourceUsage, 停止监控，返回 ResourceUsage 快照。, 工具执行资源监控器。 使用 psutil 监控当前进程的内存和 CPU 使用。 psutil 不可用时自动降级为仅计时。 用法: monitor =…, ResourceMonitor

### Community 65 - "Tool Audit Logging"
Cohesion: 0.33
Nodes (8): audit_tool_execution(), audit_tool_execution_safe(), Any, 非阻塞审计日志模块 (Feature 2: Audit Logs). 将 ToolProvenance + ToolResult 持久化到 SQLite…, audit_tool_execution 的完全安全包装。 即使 audit 模块本身有 bug，也不会影响调用方。, 安全 JSON 序列化，失败返回 None。, 将一次工具有执行持久化到数据库。 设计为 fire-and-forget：任何异常都被捕获并打印警告， 绝不向上传播影响工具执行流。 Args:…, _safe_json_dumps()

### Community 66 - "Product Architecture Overview"
Cohesion: 0.22
Nodes (9): Bio Agent SPA Shell, BioAI Agent v2.0, Execution Guardrails and Auto-Recovery, FastAPI Backend, Router-Planner-Executor-Reporter Multi-Agent Pipeline, Rscript and Bioconductor Integration, Vite React SPA, Cross-Turn Session Memory (+1 more)

### Community 67 - "Enrichment Skills"
Cohesion: 0.33
Nodes (6): Enrichment Skill Pack, GO 富集分析 [implemented], GSEA 基因集富集分析 [implemented], GSVA 通路活性分析 [planned], KEGG 通路富集分析 [implemented], 多数据库综合富集 [planned]

### Community 68 - "Single Cell Skills"
Cohesion: 0.33
Nodes (6): 单细胞类型注释 [planned], 单细胞通讯分析 [planned], 单细胞多样本整合 [planned], Single-Cell RNA Skill Pack, 单细胞标准分析流程 [planned], 单细胞轨迹/拟时序分析 [planned]

### Community 69 - "Survival Skills"
Cohesion: 0.33
Nodes (6): 竞争风险分析 [planned], LASSO-Cox 预后模型 [implemented], 预后风险评分模型 [implemented], 单基因生存分析 [implemented], Survival Analysis Skill Pack, 批量单因素 Cox 回归 [implemented]

### Community 70 - "Frontend Bundle 70"
Cohesion: 0.40
Nodes (4): Oo, sv(), uo(), wv()

### Community 71 - "Network Pharmacology Skills"
Cohesion: 0.40
Nodes (5): Cytoscape 网络导出 [planned], 中药成分-靶点分析 [partial], 网络药理学全流程 [implemented], Network Pharmacology Skill Pack, PPI 蛋白互作网络分析 [implemented]

### Community 72 - "Frontend Bundle 72"
Cohesion: 0.40
Nodes (3): tt, wr(), Xa

### Community 73 - "Engineering Guidelines"
Cohesion: 0.40
Nodes (5): Engineering Guidelines, Minimal and Surgical Change Principle, Mock LLM Testing Principle, Ruff Pyright Pytest Quality Gate, Typed Async Python Standard

### Community 74 - "Regression Test Inventory"
Cohesion: 0.40
Nodes (5): File URL Normalization Tests, Output File Alias Coercion Tests, Storage Path Containment Tests, Tool Result Normalization Tests, Regression Test Inventory

### Community 75 - "Modeling Skills"
Cohesion: 0.50
Nodes (4): 蛋白结构域与 Motif 分析 [planned], Modeling Skill Pack, 蛋白结构预测 [planned], 序列比对分析 [planned]

### Community 76 - "Spatial Skills"
Cohesion: 0.50
Nodes (4): 空间转录组反卷积 [planned], 空间转录组聚类 [planned], Spatial Transcriptomics Skill Pack, 空间区域差异分析 [planned]

### Community 77 - "Session File Lookup"
Cohesion: 0.50
Nodes (4): get_files_by_session(), get_session_files 的别名。, fallback_attached_files_from_db(), 如果前端 attached_files 没传到，则尝试从数据库按 session 回查 upload 文件记录

### Community 78 - "Root Dependencies"
Cohesion: 0.50
Nodes (4): Pandas NumPy SciPy Scikit-learn Data Science Stack, FastAPI 0.135.3, OpenAI Python SDK 2.31.0, Pinned Python Dependency Manifest

### Community 79 - "Aptamer Skills"
Cohesion: 0.67
Nodes (3): 适配体-靶标结合预测 [planned], Aptamer Skill Pack, 适配体序列设计 [planned]

### Community 80 - "Docking Skills"
Cohesion: 0.67
Nodes (3): Docking Skill Pack, 分子对接 [planned], 虚拟筛选 [planned]

### Community 81 - "Drug Screening Skills"
Cohesion: 0.67
Nodes (3): 药物重定位分析 [planned], Drug Screening Skill Pack, 药物敏感性预测 [planned]

### Community 82 - "Literature Report Skills"
Cohesion: 0.67
Nodes (3): Literature and Report Skill Pack, 文献检索与综述 [implemented], 科研报告生成 [planned]

### Community 83 - "Perturbation Skills"
Cohesion: 0.67
Nodes (3): Perturbation Skill Pack, 扰动响应分析 [planned], 虚拟基因敲低 [planned]

### Community 84 - "Single Gene Skills"
Cohesion: 0.67
Nodes (3): 基因集相关性分析 [implemented], 单基因表达分析 [implemented], Single Gene Skill Pack

## Knowledge Gaps
- **121 isolated node(s):** `_c`, `Vu`, `Qu`, `b`, `se` (+116 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 536 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_tool_with_lifecycle()` connect `Tool Lifecycle Tests` to `Tool Lifecycle Bridge`, `Tool Registry Routing`, `Tool Result Tests`, `Lifecycle Hooks`, `Waterfall Racing`, `Tool Result Protocol`, `Parallel Tool Execution`, `Agent Orchestration`, `Executor Agent Flow`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Why does `n()` connect `Frontend Bundle 1` to `Frontend Bundle 0`, `Frontend Bundle 2`, `Frontend Bundle 3`, `Frontend Bundle 4`, `Frontend Bundle 5`, `Frontend Bundle 7`, `Frontend Bundle 8`, `Frontend Bundle 12`, `Frontend Bundle 15`, `Frontend Bundle 18`, `Frontend Bundle 21`, `Frontend Bundle 23`, `Frontend Bundle 26`, `Frontend Bundle 35`, `Frontend Bundle 36`, `Frontend Bundle 37`, `Frontend Bundle 41`, `Frontend Bundle 43`, `Frontend Bundle 45`, `Frontend Bundle 54`, `Frontend Bundle 70`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Why does `jx()` connect `Frontend Bundle 2` to `Frontend Bundle 0`, `Frontend Bundle 1`, `Frontend Bundle 34`, `Frontend Bundle 3`, `Frontend Bundle 4`, `Frontend Bundle 5`, `Frontend Bundle 8`, `Frontend Bundle 15`, `Frontend Bundle 18`, `Frontend Bundle 26`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Are the 51 inferred relationships involving `n()` (e.g. with `_1()` and `r()`) actually correct?**
  _`n()` has 51 INFERRED edges - model-reasoned connections that need verification._
- **Are the 36 inferred relationships involving `t()` (e.g. with `_1()` and `ay()`) actually correct?**
  _`t()` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Are the 46 inferred relationships involving `l()` (e.g. with `_1()` and `f()`) actually correct?**
  _`l()` has 46 INFERRED edges - model-reasoned connections that need verification._
- **Are the 46 inferred relationships involving `i()` (e.g. with `a0()` and `f()`) actually correct?**
  _`i()` has 46 INFERRED edges - model-reasoned connections that need verification._