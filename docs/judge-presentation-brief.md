# iGEM 评委答辩材料速查

> 用途：上台前的一页纸速查 + 演讲/答辩口径。所有「证据」都指向仓库里的可验证文件，避免口说无凭。
>
> 注意：团队 wiki（https://2026.igem.wiki/lzu-gansu）是 JS 渲染的静态站，脚本抓取只能拿到标题、读不到正文。**Human Practices 的具体证据需从 wiki 手工填写**（见 §5 占位模板）；其余工程/安全/定位材料均已从仓库文档提炼。

## 0. 一句话定位（电梯陈述）

> BioAI Agent 是面向生物信息学/合成生物学研究者的**本地** AI 助手：用中文自然语言驱动 40 个生信工具，经 Router→Planner→Executor→Reporter 多 Agent 自动编排，落地到 Python/R(Bioconductor) 真实分析，把「数据上传→分析→图表/文件回传→中文报告」全流程自动化，且数据不出本机。

**核心数字**（运行时实测一致）：40 个注册工具 · 54 个 Skill（22 实现 / 3 部分 / 29 规划）· 21 个斜杠命令 · **230 个测试全绿** · Python 3.12 / R 4.5。

## 1. 差异化定位（"和 ChatGPT / Galaxy / AutoBA 有什么不同"）

| 维度 | BioAI Agent | 通用 LLM（ChatGPT/Copilot） | Galaxy / Shiny | 同类 AI 生信 agent |
|---|---|---|---|---|
| 交互 | 中文自然语言对话 | 通用对话 | 图形/表单为主 | 对话/API |
| 生信专精 | 40 工具 + 54 Skill 白名单 | 需用户自己写代码 | 工具全但偏手工 | 多为单点分析 |
| 编排 | 多 Agent 自动（Router/Planner/Executor/Reporter） | 无 | 无 | 部分 |
| R/Bioconductor | 子进程 Rscript + 私有包库 + UTF-8 环境 | 无 | 内置 | 部分 |
| 数据隐私 | **本地 127.0.0.1，数据不出机** | 数据上云 | 服务器 | 云/本地不一 |
| 护栏 | 工具白名单、超时硬终止、恢复策略、审计 | 无 | 无 | 部分 |
| 可复现/开源 | MIT + CI + 锁文件 + 230 测试 | 闭源 | 部分 | 开源为主 |

**一句护城河**：不是「让大模型写 R 代码」，而是「把 40 个经过验证的分析流程封装成**可审计、可白名单、可终止**的工具，再让多 Agent 可靠地调度它们」——可靠性、本地隐私、可追溯是三个通用 LLM 给不了的。

## 2. 工程证据（"你怎么证明它能跑、且跑得对"）

核心来源：[docs/README_FEATURE_VERIFICATION.md](README_FEATURE_VERIFICATION.md)（2026-10-01 逐项实测）——区分「代码存在」与「真实跑通」：

- **真实执行（非 mock）**：生存分析（KM/Cox/LASSO/风险模型）、limma + DESeq2 差异表达、PCA、GSEA（21355 个真实 SYMBOL 排序）、Logistic/RF/SVM、STRING PPI、网络药理学、Europe PMC 文献、单细胞 10X、Visium 空间、扰动响应——均真实运行产出文件。
- **测试**：`python -m pytest -q backend/tests` → **230 passed**（含新增的数值正确性基准 `test_scientific_benchmarks.py`）。
- **数值正确性口径**：管道正确性用 mock 契约测试；确定性的计算核心用 known-result 基准（见 [test_scientific_benchmarks.py](../backend/tests/test_scientific_benchmarks.py)）；R 分析的数值正确性用合成/真实已知数据人工验证（见 README_FEATURE_VERIFICATION.md）。
- **护栏是真实现**：超时通过独立进程 + `taskkill /T /F` 硬终止整个进程树（[test_tool_lifecycle.py](../backend/tests/test_tool_lifecycle.py) 的 `test_process_timeout_reaps_descendant` 验证不遗留孤儿进程）；本次补上了 worker 内存/CPU 采样（`test_process_records_resource_samples`）。

## 3. 安全 / 数据隐私 / Responsible AI

详见 [docs/security-and-data-model.md](security-and-data-model.md)。要点口径：

- **数据存哪**：`backend/storage/uploads/{session}`、`backend/storage/generated/{session}`、SQLite 在 `backend/db_data/`。
- **谁能访问**：仅 127.0.0.1 本机单用户；CORS 白名单（非 `*`）；session id 用 `crypto.randomUUID()` 不可猜；已移除 `"default"` 共享桶。
- **何时删**：`DELETE /api/chat/session/{id}` 物理删文件 + 清 DB + 清记忆。
- **威胁模型**：本地单用户工具；若公网部署需认证 + TLS（见文档「已知边界」）。
- **Responsible AI**：模型 = DeepSeek chat；分析结果需人工复核；外部数据库（KEGG/STRING/Europe PMC 等）依赖实时可用性，外部失败不记为成功。

## 4. 归因（Attribution）

来源：[docs/IGEM_SUBMISSION.md](IGEM_SUBMISSION.md) + `README.md`。

- 队伍：iGEM 2026 **Team LZU GANSU**（兰州大学 Lanzhou University），official slug `lzu-gansu`。
- 软件仓库（canonical）：`https://gitlab.igem.org/2026/software/lzu-gansu/bio-agent`；开发史镜像：`https://github.com/NyxScheppen/bio-agent`。
- 冻结日：Soft 提交为 **2026-10-21**（已过，见 README；到 GitHub wiki 更新记录）。
- **仍需队伍填写**（代码无法自动推断）：成员/指导教师/顾问署名、Human contribution statement、演示媒体、DOI/引用。

## 5. Human Practices（⚠️ 需从 wiki 手工补齐）

脚本抓不到 wiki 正文，请从 https://2026.igem.wiki/lzu-gansu/human-practices 手工提取，并按下面模板填入（评委专看「闭环」——反馈如何改了设计）：

```
- 接触对象：谁？（湿实验研究者 / 生信专家 / 临床医生 / …）
- 他们的问题/痛点：一句话
- 由此做出的设计改动：具体到某个功能/工具/Skill（例：因"我需要一键 DESeq2"→ 新增 deseq2_count_deg Skill）
- 证据：会议记录 / 问卷 / 邮件截图 / wiki 引用
```

要能回答三个追问：**"你和真实用户聊过吗？"→"聊了谁、在哪记录？"→"然后你改了什么？"**

## 6. 关键问题 → 一行口径速查

| 评委问题 | 口径 | 证据 |
|---|---|---|
| "测试测管道还是数值？" | 管道用 mock 契约，数值用 known-result 基准 + 合成/真实数据人工验证 | `test_scientific_benchmarks.py`、README_FEATURE_VERIFICATION.md |
| "超时能不能真停？" | 独立进程 + `taskkill /T /F` 硬终止进程树，测试证明无孤儿进程 | `tool_process.py`、`test_process_timeout_reaps_descendant` |
| "和 ChatGPT 差别？" | 本地隐私 + 可审计工具白名单 + 多 Agent 可靠编排 | §1 对比表 |
| "数据存哪/谁能访问/何时删？" | 见 §3 | security-and-data-model.md |
| "AI 会不会分析错？" | 结果需人工复核 + 免责声明 + 外部依赖不虚报成功 | Responsible AI 段 |
| "测试绿吗？" | `pytest -q backend/tests` → 230 passed | 本仓库实测 |

---

> 生成：2026-11-03。数字随代码可能变动，上台前重跑一次 `python -m pytest -q backend/tests` 复核最新数字。