# README 功能逐项验证报告

验证日期：2026-10-01

本文对照根目录 `README.md` 验证已声明能力。证据分为真实工具执行、真实外部请求、Agent 端到端执行和自动化契约测试，避免把“代码存在”误写为“功能已跑通”。

## 1. 状态定义

- `PASS`：本机真实执行成功，或基础设施能力通过针对性契约测试。
- `PARTIAL`：功能按文档边界只实现其中一部分，或一次复合执行只有部分分支成功。
- `PLANNED`：Skill 明确标记为规划中，并在 Planner/Executor 前停止。
- `BLOCKED`：实现存在，但本次验证被外部服务、网络或环境阻断。
- `402`：外部 API 明确返回 HTTP 402 或额度不足。本文没有此状态。

## 2. 环境与总账

| 项目 | 结果 | 证据 |
|---|---|---|
| Python | PASS | Python 3.12.10 |
| R | PASS | R 4.5.2 |
| Python 私有环境 | PASS | `.venv` 执行 `pip check`：No broken requirements found |
| R 私有包库 | PASS | `install_r_packages.R` 从 `env/r_libs` 加载全部 27 个顶层包及必需依赖 |
| Python 编译 | PASS | `python -m compileall -q backend/app` |
| 后端回归 | PASS | `220 passed` |
| Multi-Agent/Skill 契约 | PASS | 68 个聚焦测试通过 |
| 注册工具 | PASS | 运行时共 40 个，与 README 一致 |
| Skill | PASS | 54 个：22 implemented、3 partial、29 planned |
| 斜杠命令 | PASS | 运行时共 21 个，与 README 一致 |
| 前端产物 | PASS | React 19.2.0 + TypeScript/Vite 源码、npm 锁文件和 `backend/static` 生产构建均通过 lint、类型检查、测试与构建 |
| HTTP 402/额度不足 | PASS | 所有本次请求均未出现 402 或额度不足 |

系统 Python 上另有与本项目无关的 `nyx-server` 缺失依赖，因此权威依赖检查使用项目 `.venv`，结果为通过。

## 3. README 能力逐项验证

| README 能力 | 状态 | 验证方式与结果 |
|---|---|---|
| Multi-Agent Router → Planner → Executor → Reporter | PASS | `/env` 真实主链通过；路由、计划、工具结果和 Reporter 摘要均保留 |
| YAML Skill 系统 | PASS | 加载 16 个 YAML 包、54 个 Skill；工具引用、状态、白名单和轮次上限契约通过 |
| 依赖感知并行执行 | PASS | 并行组白名单、依赖、环、失败阻断、参数校验契约通过 |
| DEG 竞速 | PASS | 首个成功结果和不兼容签名过滤契约通过 |
| 护栏 | PASS | Skill 白名单闭合、规划能力停止、轮次上限、超时进程终止和错误传播测试通过 |
| Session Memory | PASS | 会话上下文、真实 session ID 委派和跨轮短回复相关契约通过 |
| 改进反馈 | PASS | 失败记录和人工分析路径存在；README 已明确不会自动修改 Skill |
| 生存分析 | PASS | 单基因 KM/Cox 真实运行生成 4 文件；批量 Cox 3 文件；LASSO-Cox 4 文件；风险模型 6 文件 |
| limma 差异表达 | PASS | 合成连续表达矩阵真实运行成功 |
| DESeq2 差异表达 | PASS | 合成 count 矩阵真实运行成功，含小样本离散度回退 |
| PCA | PASS | 合成表达矩阵和分组真实运行，生成 3 文件 |
| GO | PASS | 本地注释和富集真实运行，生成结果表与 dotplot |
| KEGG | BLOCKED | 代码分支已执行，但 `rest.kegg.jp` 在 60 秒内不可达；状态写入 `enrichment_status.csv`，GO 结果仍保留 |
| GSEA | PASS | 21,355 个真实 SYMBOL 排序基因执行成功，生成 20 条 Hallmark 结果、dotplot 和诊断表；项目缓存与 DNS 诊断均生效 |
| Logistic/RF/SVM | PASS | 三模型真实比较成功，生成比较指标与预处理审计表 |
| LASSO 特征选择 | PASS | 真实运行成功，生成 4 文件；模板顺序有回归测试 |
| STRING PPI | PASS | 10 个基因全部映射，返回 30 条高置信 PPI 边，生成 7 文件 |
| 网络药理学 | PASS | 3 个合成成分、10 个靶点真实运行，STRING 成功，生成 12 文件 |
| 文献检索 | PASS | Europe PMC 真实请求返回 3 条文献及 DOI/PubMed/PMC 链接 |
| 开放获取 PDF | PASS | 下载安全边界由 SSRF、重定向、媒体类型和文件生命周期测试覆盖；本轮未重复下载远端 PDF |
| 单基因表达 | PASS | 真实运行成功 |
| 单基因相关性 | PASS | 真实运行成功 |
| 单基因 ROC | PASS | 真实运行成功 |
| 文件预览/探测 | PASS | 当前会话 CSV 的 preview、read 和 large-file 路径均成功 |
| 已上传 GEO 文件导入 | PARTIAL | 本地已上传文件导入与预览成功；不提供 GEO 在线下载，与 README 边界一致 |
| R/Python 环境诊断 | PASS | `/env` 真实 Multi-Agent 主链成功 |
| 单细胞 10X 标准流程 | PASS | 合成 10X ZIP 真实执行，生成 QC、UMAP、marker、元数据、RDS 和版本等 9 个文件 |
| Visium 标准流程 | PASS | 合成 Space Ranger ZIP 真实执行，生成 11 个文件；结果是表达聚类投影，不是空间感知聚类 |
| 表达缩放情景 | PARTIAL | 真实执行成功；仅缩放目标基因表达，不预测下游效应 |
| 真实扰动响应 limma | PASS | control/perturbed 连续表达真实执行成功 |
| 真实扰动响应 DESeq2 | PASS | control/perturbed count 数据真实执行成功 |
| 预测型虚拟扰动 | PLANNED | GEARS、scGen、LINCS 自动下载和 CRISPR 建模未实现，按设计停止 |
| DeepSeek API | PASS | 最小真实请求返回 `OK`，未出现 402 |
| FastAPI + 静态 SPA | PASS | `/api/health`、`/` 和 SPA 静态资源 HTTP 冒烟通过 |

GO/KEGG 相互隔离：KEGG 外部失败不会丢弃已经完成的 GO 结果。GSEA 首次复测时 `zenodo.org` 恢复为公网 DNS 解析并写入项目私有缓存；后续系统解析再次失败时，真实分析仍从缓存完成。代码会把 DNS sinkhole、依赖下载超时、输入预检和分析失败分别归因；这些状态都不会误报为 HTTP 402 或额度不足。

## 4. 21 个斜杠命令

| 命令 | 状态 | 证据 |
|---|---|---|
| `/survival` | PASS | 单基因生存真实执行 |
| `/cox` | PASS | 批量 Cox 真实执行 |
| `/lasso` | PASS | LASSO-Cox 真实执行 |
| `/risk` | PASS | 风险模型真实执行 |
| `/deg` | PASS | limma 差异表达真实执行 |
| `/deseq2` | PASS | DESeq2 差异表达真实执行 |
| `/pca` | PASS | PCA 真实执行 |
| `/enrich` | PARTIAL | GO 通过；KEGG 本次被外部端点阻断 |
| `/gsea` | PASS | 真实 Hallmark GSEA 成功，生成结果表、dotplot 和结构化诊断 |
| `/ml` | PASS | 分类与 LASSO 工具真实执行 |
| `/compare` | PASS | Logistic/RF/SVM 真实比较 |
| `/ppi` | PASS | STRING 真实请求成功 |
| `/netpharm` | PASS | 完整网络药理真实执行 |
| `/probe` | PASS | 当前会话文件探测成功 |
| `/geo` | PARTIAL | 只处理已上传 GEO 文件，不在线下载 |
| `/lit` | PASS | Europe PMC 真实请求成功 |
| `/env` | PASS | Multi-Agent 端到端执行成功 |
| `/scrna` | PASS | 10X ZIP 真实执行 |
| `/spatial` | PASS | Visium ZIP 真实执行 |
| `/perturb` | PASS | limma 与 DESeq2 两种真实响应均通过 |
| `/help` | PASS | 实时展示命令、Skill 状态和规划能力提示的契约测试通过 |

## 5. Skill 状态核验

`implemented` 的 22 个 Skill 均引用已注册工具。`partial` 的 3 个 Skill 为：

- `geo_data_download`：仅导入当前会话已上传文件。
- `herb_compound_target`：只覆盖现有成分-靶点数据处理边界。
- `virtual_knockdown`：只做表达缩放情景。

以下 29 个 Skill 为 `planned`，没有可执行工具白名单，并会在 Planner/Executor 前停止：

`aptamer_binding_prediction`、`aptamer_sequence_design`、`batch_correction`、`batch_effect_correction`、`competing_risk_analysis`、`cytoscape_network_export`、`data_merge`、`domain_motif_analysis`、`drug_repurposing`、`drug_sensitivity_prediction`、`file_convert`、`gsva_pathway`、`immune_infiltration`、`molecular_docking`、`multi_db_enrichment`、`protein_structure_prediction`、`scientific_report_generation`、`scrna_cell_annotation`、`scrna_cell_communication`、`scrna_integration`、`scrna_trajectory`、`sequence_alignment`、`shap_interpretation`、`spatial_cell_deconvolution`、`spatial_region_de`、`survival_ml`、`time_series_deg`、`time_series_expression`、`virtual_screening`。

## 6. 本轮修复

1. 修复三个机器学习工具在读取 `df` 前计算 `feature_cols` 的模板顺序错误。
2. 将 `tabulate` 加入 Python 运行依赖，修复 PPI/网络药理报告阶段失败。
3. 修复 R 安装器把脚本父目录误判为项目根的问题。
4. R 安装器只认可项目私有库与系统库，并递归检查 `Depends`、`Imports`、`LinkingTo`，避免用户全局库掩盖缺失依赖。
5. GO 与 KEGG 分支隔离并生成 `enrichment_status.csv`；一个外部端点失败时保留另一分支结果。
6. `msigdbr` 调用更新为 `collection = "H"`。
7. GSEA 增加 `zenodo.org` DNS 预检，识别未解析、`0.0.0.0`、`::`、回环、私网和链路本地 sinkhole 响应。
8. GSEA 返回稳定的 `failure_stage`、错误码、解析地址、缓存状态和明确的非 402 说明；项目缓存存在时允许离线继续。
9. MSigDB 数据缓存固定到项目 `R_LIBS_USER/.cache`；外层 R 超时提高到 900 秒，覆盖依赖下载的 600 秒预算。
10. 兼容 `msigdbr` 新版 `ncbi_gene` 与旧版 `entrez_gene`，并预检有限 score、映射数、映射率及最大基因集重叠。
11. 按 score 符号自动选择 `pos`、`neg` 或 `std`，并强制 GSEA 使用串行 BiocParallel 后端，避免与 R 子进程安全护栏冲突。
12. KEGG 单次 R 网络预算设为 30 秒并重试一次；Windows/libcurl 可能对多个地址分别等待，因此仍保留 300 秒外层硬上限。只要 GO 已成功，最终状态保持 `partial`。

## 7. 额度结论

本轮没有 HTTP `402`，没有 DeepSeek 或其他计费 API 的额度不足。当前仍存在的外部失败只有 KEGG REST 请求超时。

系统 DNS `100.64.164.3` 对 `zenodo.org` 的响应不稳定：先前返回 `0.0.0.0`/`::`，随后短暂恢复为 CERN 公网 IPv4/IPv6 地址，之后又出现 `getaddrinfo failed`。首次恢复窗口已成功建立项目缓存；后续解析失败期间，GSEA 仍从缓存成功执行。无缓存且 DNS 异常时工具返回 `gsea_dependency_dns_unavailable`；已有项目缓存时响应包含 `using_cache_without_dns=true` 并继续离线执行。
