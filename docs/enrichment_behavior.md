# GO、KEGG 与 GSEA 行为规范

本文记录 `backend/app/tools/enrichment_tools.py` 的执行、缓存和故障诊断契约。

## 1. GO/KEGG

`run_go_kegg_enrichment` 将 GO 与 KEGG 作为独立组件执行。GO 使用本地物种注释包；KEGG 访问 `rest.kegg.jp`，单次 R 网络预算为 30 秒，最多尝试两次，重试间隔 2 秒。Windows/libcurl 可能对多个解析地址分别应用等待，因此外层仍保留 300 秒硬上限。

工具始终尽可能写出：

- `go_enrichment_results.csv`
- `kegg_enrichment_results.csv`
- `enrichment_status.csv`
- 有结果时对应的 dotplot

`enrichment_status.csv` 记录组件状态、错误消息和尝试次数。一个组件成功、另一个失败时，顶层状态为 `partial`；即使 R 外层随后超时，已经完成的成功组件也不会被重新标记为整体失败。摘要同时保留 `runner_status`、`runner_message` 和 `runner_timed_out`，防止顶层 `partial` 隐藏底层硬超时。两个组件均失败时返回 `error`。

## 2. GSEA 输入与执行

`run_gsea_analysis` 接受包含 `gene` 和 `score` 列的排序基因表，支持 human 和 mouse。执行前会：

1. 删除空基因名和非有限 score。
2. 按绝对 score 保留重复 SYMBOL 中的信息量最大者。
3. 将 SYMBOL 映射到 ENTREZID，并按相同规则消除重复 ENTREZID。
4. 要求至少 10 个有效映射基因，并记录输入数、映射数和映射率。
5. 兼容新版 `msigdbr` 的 `ncbi_gene` 和旧版的 `entrez_gene`。
6. 要求至少一个 Hallmark 基因集与排序列表重叠 10 个基因。
7. 全正 score 使用 `pos`，全负使用 `neg`，正负混合使用 `std`。

GSEA 使用 `BiocParallel::SerialParam()`。这避免 `fgsea` 创建 SOCK worker，与应用禁止 R 模板启动外部进程的安全护栏保持一致。R 外层超时为 900 秒，MSigDB 下载预算为 600 秒。

主要输出：

- `gsea_results.csv`
- `gsea_dotplot.png`，仅在存在结果时生成
- `gsea_diagnostics.csv`

诊断表记录缓存目录、输入与映射数量、映射率、score 类型、并列 score 比例、使用的 MSigDB ID 列和最大基因集重叠。

## 3. MSigDB 缓存

MSigDB 缓存固定在项目私有 R 库下：

```text
R_LIBS_USER/.cache/R/msigdbr
```

首次成功下载后，ZIP 与拆分后的 RDS 会跨作业复用。若 DNS 暂时不可用但所需项目缓存已存在，工具允许 R 离线读取缓存；若无缓存，则在启动 R 前返回结构化 DNS 错误。

## 4. DNS 响应诊断

GSEA 在执行前解析 `zenodo.org`。诊断状态为：

- `ok`：至少返回一个可全局路由地址。
- `sinkhole`：返回 `0.0.0.0`、`::`、回环、私网、链路本地、保留或组播地址。
- `error`：解析抛出错误或没有返回地址。

无缓存且 DNS 不是 `ok` 时，返回：

```json
{
  "status": "error",
  "errors": ["gsea_dependency_dns_unavailable"],
  "summary": {
    "failure_stage": "dns_resolution",
    "retryable": true,
    "dns_diagnostic": {
      "host": "zenodo.org",
      "status": "sinkhole",
      "addresses": ["0.0.0.0", "::"]
    }
  }
}
```

消息会明确说明这不是 HTTP 402 或额度不足。若 Python 预检通过，但 R 下载阶段随后出现 `Could not resolve host`，结果也会归类为 `dns_resolution`；下载超时归类为 `dependency_download`；映射数、有效 score 或基因集重叠不足归类为 `input_validation`；其余失败归类为 `analysis`。

## 5. 当前验证结论

2026-10-01 复测时，系统 DNS `100.64.164.3` 对 `zenodo.org` 出现波动：曾返回 CERN 公网 IPv4/IPv6 地址，也出现过 `getaddrinfo failed`；此前还返回过 `0.0.0.0`/`::`。恢复窗口已完成首次缓存下载。随后在 DNS 再次失败时，21,355 个真实人类 SYMBOL 排序基因仍从项目缓存完成 Hallmark GSEA：映射率 100%，最大基因集重叠 200，生成 20 条结果及 dotplot。这是 DNS 可用性问题，不是 402。

同次复测中 KEGG 端点仍超时；GO 正常完成，因此复合能力保持 `partial`。
