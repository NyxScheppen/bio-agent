# 单细胞、Visium 与扰动分析行为规范

本文记录 BioAI Agent 当前已实现的单细胞、空间转录组和扰动分析契约。实现入口分别位于 `backend/app/tools/scrna_tools.py`、`spatial_tools.py`、`perturbation_tools.py`，安全输入准备位于 `omics_input.py`。

## 1. 通用执行与文件生命周期

所有公开工具都通过工具生命周期执行器运行：

1. 每次调用创建独立的 `generated/{session_id}/{job_id}` 作业目录。
2. 委派到子 Agent 时保留原始 `session_id`；job UUID 提供调用级隔离。
3. 工具只解析当前会话的上传文件，不能通过同名文件搜索读取其他会话数据。
4. 重型流程注册超时为 3600 秒、内存预算为 16 GB 或 8 GB；委派任务默认零重试。
5. ZIP 内容只解压到作业目录内的 `.omics-input-*` 私有暂存目录。
6. 暂存目录在成功、R 错误、Python 异常和父进程发现硬超时后清理；其中的输入文件不会出现在 `output_files`。
7. 分析脚本 `analysis.R` 也不会作为用户生成物返回。

## 2. 10X/Visium ZIP 安全契约

ZIP 在写盘前检查中央目录，并在流式解压时再次执行实际字节预算：

- 最多 512 个条目。
- 总解压大小最多 2 GiB，单条目最多 1 GiB。
- 单条目和整体压缩比最多 200:1。
- 拒绝绝对路径、盘符路径、`..`、空路径片段、加密条目和符号链接。
- 路径按大小写不敏感规则去重，避免 Windows 上的覆盖歧义。
- 不支持多卷 ZIP 和 ZIP64；一个压缩包只允许一个待分析数据集。
- `.h5` 文件在交给 R 前校验 HDF5 文件签名。

安全预检只验证容器和必需布局。矩阵维度、稀疏矩阵结构、条形码一致性等内容校验由 Seurat 读取阶段完成，失败时工具返回真实 R 错误。

## 3. 单细胞标准流程

工具：`run_scrna_standard_pipeline`

支持输入：

- 单个 10X H5 文件；
- 含一个 `matrix.mtx[.gz]`、`barcodes.tsv[.gz]`、`features.tsv[.gz]`/`genes.tsv[.gz]` 完整组合的 ZIP；
- 含一个标准 10X H5 的 ZIP。

执行顺序：

1. `Read10X_h5` 或 `Read10X` 读取 Gene Expression assay。
2. `CreateSeuratObject` 应用 `min_cells`，计算人/鼠线粒体比例。
3. 应用 `min_features`、`max_features`、`max_mt_percent` 和正 count 过滤。
4. 执行 LogNormalize、HVG、ScaleData 和自适应维数 PCA。
5. 根据保留细胞数调整邻居数，执行聚类和 UMAP；随机种子默认 2026。
6. 多 cluster 时执行 `FindAllMarkers`；单 cluster 或 marker 失败不会丢失前面的 QC/聚类输出，状态写入摘要。

主要输出：QC 小提琴图、过滤前 QC 表、QC 摘要、UMAP、全部/Top marker、细胞元数据、Seurat RDS、软件版本表。

不支持：h5ad、任意 CSV/TSV 计数矩阵、用户上传的任意 RDS、多样本整合、自动细胞注释、拟时序和细胞通讯。

## 4. Visium 标准流程

工具：`run_visium_standard_pipeline`

输入必须是一个完整 Space Ranger 输出 ZIP，至少包含：

- `filtered_feature_bc_matrix.h5`；
- `spatial/tissue_positions.csv` 或 `tissue_positions_list.csv`；
- `spatial/scalefactors_json.json`；
- 低分辨率或高分辨率组织 PNG。

执行顺序：`Load10X_Spatial`、QC 过滤、`SCTransform`、PCA、邻居图、表达聚类、`SpatialDimPlot`、marker 分析，以及可选的目标基因 `SpatialFeaturePlot`。PCA 维数和邻居数会按保留 spot 数自适应，随机种子默认 2026。

这里的 cluster 由表达空间计算，再投影到组织坐标。实现没有把邻接空间坐标纳入聚类目标，所以不得称为“空间感知聚类”。当前也不提供反卷积、空间通讯和多切片整合。

## 5. 表达缩放情景

工具：`run_expression_scaling_scenario`

输入为包含 `gene` 列的数值表达矩阵、目标基因和 `scaling_ratio`。工具只执行：

```text
目标基因缩放后表达 = 原表达 * (1 - scaling_ratio)
```

它输出目标行前后值、完整缩放后矩阵和限制说明。它不使用调控网络、不修改其他基因、不预测下游通路，也不等同于真实基因敲低或敲除。旧工具名 `run_virtual_knockdown_bulk_analysis` 仅作为兼容入口保留，语义相同。

## 6. 真实扰动响应分析

工具：`run_observed_perturbation_response_analysis`

输入包括含 `gene` 列的表达矩阵、含样本和条件列的元数据、control 标签及 treatment 标签。元数据样本必须唯一且全部存在于表达矩阵，每组至少两个样本。

- `data_type=raw_count`：要求非负整数，过滤低表达基因后用 DESeq2。
- `data_type=continuous`：用 limma；`expression_preprocess` 可声明已 log2、未 log2、无需处理或使用可审计的 auto 启发式。

输出包括完整差异表、上调/下调表、火山图、可生成时的 Top 50 热图、方法与样本量摘要、软件版本表。可选 `target_gene` 只从真实差异结果中摘录该基因的 log2FC 和校正 p 值。

该流程比较真实样本组，报告观测关联。混杂因素、批次效应和实验设计仍可能影响结论；当前接口只实现二组基本设计，不宣称因果推断。

## 7. Agent 路由与能力状态

- `/scrna` 绑定 `scrna_standard_pipeline`，状态为 `implemented`，白名单只开放原子单细胞工具。
- `/spatial` 绑定 `spatial_clustering`，状态为 `implemented`，白名单只开放原子 Visium 工具。
- `/perturb` 绑定 `perturbation_response`，状态为 `implemented`，开放真实响应工具及可选 GO/KEGG 富集工具。
- 表达缩放 Skill 状态为 `partial`，用于强调其科学能力有限，而不是执行代码不完整。
- 细胞注释、拟时序、细胞通讯、多样本整合、空间反卷积、GEARS/scGen 和预测型虚拟扰动仍为 `planned`，会在 Planner/Executor 前停止。

## 8. 失败行为

以下情况会明确失败，不进行猜测或静默降级：输入不属于当前会话、格式不支持、ZIP 安全预算超限、布局不完整、多个数据集、HDF5 签名无效、QC 后细胞/spot 太少、样本名不匹配、分组缺失、raw count 含小数或负数、目标基因不存在、所需 R 包缺失或 R 执行超时。

错误不会被报告为成功；已生成且位于当前 job 内的诊断文件可以随错误结果返回，私有解压输入永远不会返回。
