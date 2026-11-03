# iGEM 评委面试 Q&A 双语对策（BioAI Agent / DENTAL SHIELD）

> 用法：每个问题先给「可能出现的 2–3 种问法」（中英），再给「中文要点」和「可直接念的英文答案」。按**最可能被问 → 不太可能被问**排序。Tier 1 是 Software 赛道评审几乎必问的；Tier 2 是补充/压力题。
>
> 证据来源：软件页 `software.docx`、`human-practices.docx`、`contribution.docx`、`team-members.docx`（gitlab.igem.org/2026/lzu-gansu），以及仓库代码、`docs/README_FEATURE_VERIFICATION.md`、`docs/security-and-data-model.md`。
>
> 当前可引用的硬数字：**40 个注册工具 · 54 个 Skill（22 实现 / 3 部分 / 29 规划）· 21 个斜杠命令 · 230 个测试全绿** · Python 3.12 + R 4.5 · MIT 开源。

---

## Tier 1 —— 高概率（几乎必问）

### Q1. 你的软件是什么？给谁用、解决什么问题？
**问法变体**：① "What does your software do?" ② "Who is it for, and what problem does it solve?" ③ "给我一句话概括 BioAI Agent / explain it to a non-expert."

**中文要点**：
- 定位：Local-first 生信智能工作站；不是"替代生信专家的判断"，而是消除"提出科学假设 → 完成第一次可复现计算分析"之间的操作摩擦。
- 目标用户：湿实验研究者 + 需要标准化生信流程的团队（中文自然语言即可）。
- 一句话：上传本地组学数据 → 用自然语言说意图 → 系统给规划 → 出结果文件/图/日志/方法总结。

**English answer**:
"BioAI Agent is a **local-first bioinformatics workstation** we built for wet-lab researchers who can state a biological question clearly but don't want to fight Python/R environments. You upload local omics data, describe the analysis in natural language — in Chinese or English — and the system plans the workflow, runs the appropriate of our **40 registered tools**, and returns downloadable result files, figures, logs, and a methods summary. Our principle is explicit: it is *not* meant to replace a bioinformatician's judgment — it removes the friction between 'I have a hypothesis' and 'I have a first, reproducible computational result'."

---

### Q2. 你的软件和你的主项目 DENTAL SHIELD 有什么关系？
**问法变体**：① "How does the software serve your project?" ② "Why did your oral-health project need a bioinformatics tool?" ③ "你们 Software 是自己项目用的，还是一个独立通用工具？"

**中文要点**：
- 关联：DENTAL SHIELD 需要把生物问题转成可复现的计算证据（湿实验设计、靶点筛选、公开数据重分析、文献证据整合），团队里做计算/建模/生信的人需要统一工具 → 于是开发了 BioAI Agent。
- 它既**服务本项目**（干实验），又是一个**可复用、开放的通用生信工具**（Best Software Tool 定位）。
- 由 HP 催生：在 DENTAL SHIELD 的 Human Practices 里，跨学科交流暴露了"生信门槛高、文本对话不可靠"的痛点，团队把 RRI/SCQAB 方法直接映射成软件的功能边界。

**English answer**:
"DENTAL SHIELD — our engineered *Lactococcus lactis* system for early oral-disease detection — required a lot of dry-lab work: target screening, reanalysis of public transcriptome datasets, literature mining, and modeling. In our Human Practices, interdisciplinary conversations with clinicians, computational biologists and biomaterials researchers kept coming back to the same pain: turning a biological question into *reproducible computational evidence* is slow and error-prone for non-specialists. So we built BioAI Agent to standardize exactly that work for the team — and, because it uses declarative Skills and a tool allowlist, it works as a general-purpose bioinformatics tool for anyone, not just our project."

---

### Q3. 你怎么保证分析结果是科学正确的？大模型不是会瞎编吗？
**问法变体**：① "How do you validate that the analysis is biologically correct?" ② "LLMs hallucinate — how do you stop it from inventing results?" ③ "你的测试是测管道还是测数值？"

**中文要点**（这是 AI 生信工具最尖锐的一问）：
- 三层防线：① **LLM 只做规划/路由，不直接生成可执行代码**——工具是预注册的确定性 Python/R 代码，走显式白名单；② **数值正确性**：确定性计算核心用 known-result 基准（`test_scientific_benchmarks.py`），R 分析用合成/真实已知数据人工验证（README_FEATURE_VERIFICATION.md 记录了 DESeq2/limma/生存分析等真实运行）；③ **证据链**：每个工具产出标准 ToolResult + provenance（工具名、参数、job_id、耗时、版本）+ SQLite 审计，绝不把"看起来流畅的文字"当成功。
- 关键一句：**错误不是"文本幻觉"，而是"脚本是否真实执行并产出文件"**——我们把执行挪到可审计、可终止的边界里。

**English answer**:
"We designed against hallucination structurally. The LLM only **plans and routes** — it never generates runnable analysis code. What actually executes is one of our **40 registered, deterministic tools** (Python or R), selected through a whitelist. Correctness is validated in three layers: pipeline tests verify the flow; **known-result benchmarks** (`test_scientific_benchmarks.py`) verify numerical outputs of the deterministic core; and R workflows (DESeq2, limma, survival) were validated against synthetic and real known datasets — recorded in `README_FEATURE_VERIFICATION.md`. Finally, every run produces a structured `ToolResult` with provenance and an audit record, so a 'smooth-looking answer' is never treated as evidence — only produced files and logs are."

---

### Q4. 超时/资源限制是真的能停吗？（护栏实不实）
**问法变体**：① "What happens when a tool runs too long or uses too much memory?" ② "How do your guardrails actually work?" ③ "你文档里写的护栏，工程上防住了什么？"

**中文要点**：
- 每个工具在**独立子进程**执行；超时或取消时用 `taskkill /T /F`（Windows）**硬终止整个进程树**，不是"只停等待"。
- 有测试证明不遗留孤儿进程（`test_process_timeout_reaps_descendant`）；本次还补上了 worker 进程树的**峰值内存 + 平均 CPU 采样**（`test_process_records_resource_samples`）。
- 另有：Skill 白名单闭合、规划中能力在 Planner/Executor 前停止、轮次上限、恢复策略、错误传播。

**English answer**:
"Real termination, not just waiting. Each tool runs in a **separate subprocess**; on timeout or cancellation we **hard-kill the whole process tree** (`taskkill /T /F` on Windows), so a runaway R job is actually stopped — we have a regression test asserting no orphan descendant survives (`test_process_timeout_reaps_descendant`). We also sample the worker tree's peak memory and average CPU (`test_process_records_resource_samples`). On top of that: Skill allowlists, planned capabilities stop before execution, round limits, and recovery strategies."

---

### Q5. 这和直接问 ChatGPT / 用 Galaxy 有什么不同？（护城河）
**问法变体**：① "Why not just ask ChatGPT to write the R code?" ② "What's different from Galaxy or existing tools?" ③ "What's your unique contribution?"

**中文要点**：五个通用 LLM 做生信的屏障 → BioAI Agent 的对应解法：
- Interface（不会命令行/R 脚本）→ 自然语言 + 图形界面对话
- Workflow（步骤顺序/依赖/参数）→ 54 个 YAML Skill 固化标准流程
- Reproducibility（文本对话不等于证据）→ 产物文件 + provenance + 审计
- Trust（LLM 伪造路径/虚构图）→ 声明式工具白名单 + 确定性执行
- Data-Control（数据上云风险）→ **Local-first，数据不出本机**

**English answer**:
"We identified five specific barriers to using general LLMs for bioinformatics, and BioAI Agent answers each: *Interface* (no command-line/R skill needed — natural language + GUI), *Workflow* (54 declarative YAML Skills encode the correct step order and parameters), *Reproducibility* (real files, versions and logs, not a chat transcript), *Trust* (the LLM never emits code — only a vetted tool allowlist executes), and *Data-Control* (**local-first** — omics data never leaves the researcher's machine). Galaxy gives pipelines but few agents; ChatGPT gives text but no verification. We combine an agent **with** verified, local, auditable execution."

---

### Q6. 数据存哪、谁能访问、怎么保护隐私 / Responsible AI？
**问法变体**：① "Where is the data stored and who can access it?" ② "How do you handle sensitive/patient-derived omics data?" ③ "Your Responsible AI statement?"

**中文要点**：
- 数据物理位置：`backend/storage/uploads|generated/{session}` + SQLite；仅 `127.0.0.1` 本地。
- session_id 用 `crypto.randomUUID()` 不可猜；已移除 `"default"` 共享桶；上传/生成严格校验路径穿越；危险内联文件（html/svg/js）强制下载 + CSP sandbox。
- CORS 白名单（非 `*`）；文献下载 SSRF 校验。
- 诚实边界：本地单用户定位，若公网部署需认证 + TLS。
- Responsible AI：模型 = DeepSeek，结果需人工复核，外部数据库失败不记为成功。

**English answer**:
"By default it is a **single-user, local** tool bound to `127.0.0.1` — raw data and results stay in local `storage/` directories plus a local SQLite DB, and deleting a session removes its files, records, and memory. Sessions use `crypto.randomUUID()` (unguessable), we removed the shared `"default"` bucket, enforce path-containment, serve dangerous inline files as attachments with a CSP sandbox, and CORS is an allowlist. Our honest boundary: if you deploy beyond localhost you must add auth and TLS — documented in `security-and-data-model.md`. For Responsible AI: the model is DeepSeek, outputs require human review, and external-database failures are never reported as successful analyses."

---

### Q7. 怎么证明工程是"成功"的？（DBTL / 测试证据）
**问法变体**：① "Walk me through your engineering success." ② "What's tested, and does it pass?" ③ "Give me your DBTL evidence."

**中文要点**：
- 230 个测试全绿（`pytest -m pytest -q backend/tests`）。
- 真实执行验证（非 mock）：生存分析/DESeq2/limma/PCA/GSEA/ML/PPI/网络药理/文献/单细胞/空间/扰动都真实跑通出文件——见 `README_FEATURE_VERIFICATION.md`。
- 主链路 Router→Planner→Executor→Reporter，以及 Skill 加载、依赖并行、竞速、恢复、审计、超时终止，均有针对性测试。
- CI（`.gitlab-ci.yml`）+ 锁文件（Python/npm/renv）。

**English answer**:
"Three things. First, **230 automated tests pass** (`pytest`) covering the agent pipeline, Skill loading, parallel/racing execution, recovery, audit, and hard timeout. Second, the analysis tools were validated **with real execution**, not mocks — survival, DESeq2, limma, PCA, GSEA, ML, PPI, network pharmacology, literature retrieval, single-cell, spatial, and perturbation all produced real output files, recorded in `README_FEATURE_VERIFICATION.md`. Third, reproducibility is pinned: Python requirements, npm lockfile, R lockfile, and `.gitlab-ci.yml` CI."

---

### Q8. 我（评委/别人）怎么能跑起来？可复现吗？
**问法变体**：① "How do I install and run it?" ② "Can someone else reproduce your demo?" ③ "What are the build/run instructions?"

**中文要点**：
- `check_env.bat`（环境检测）→ `install_r_packages.R`（R 包）→ 配 `.env`（DeepSeek key）→ `start_app.bat`（自动建 venv + 装依赖 + 定位 Rscript + 启动，浏览器打开 `127.0.0.1:8000`）。
- 前端源码在 `frontend/`，构建到 `backend/static/`（已含生产构建）。
- 锁文件 + CI + MIT + 双 README（中/英）。

**English answer**:
"Exactly three commands on Windows: `check_env.bat`, then `Rscript install_r_packages.R` (first run), then `start_app.bat` — the launcher creates the virtualenv, installs Python deps, locates `Rscript`, and opens the app at `127.0.0.1:8000`. Everything is pinned (Python requirements, npm lockfile, `renv.lock` for R), CI is in `.gitlab-ci.yml`, and the frontend source plus its production build are both in the repo."

---

### Q9. 为什么选择这个架构 / 最大的权衡是什么？
**问法变体**：① "Why this architecture? Key design trade-offs?" ② "What was the hardest engineering decision?" ③ "Why local-first, and why not a pure LLM agent?"

**中文要点**：
- 核心权衡：**放弃"让 LLM 自由写代码"，换取"确定性、可审计、可终止"**——用 Router/Skill/Planner/Executor/Reporter 五层 + 声明式工具白名单。
- SCQAB 映射：Situation（生信工具散落）→ Complication（文本对话不可靠）→ Question（如何降门槛又保合规/可复现/本地安全）→ Answer（Local-first + 沙箱隔离 + 声明式权限）→ Build（40 工具 + 54 Skill + 测试/CI）。
- 另一权衡：Windows 优先（面向生信湿实验室主流环境），牺牲部分 POSIX 便利。

**English answer**:
"The core trade-off was deliberate: we **gave up 'let the LLM write arbitrary code' to gain determinism, auditability, and kill-switch**. That's why BioAI Agent is a five-layer Router → Skill → Planner → Executor → Reporter, with every action gated by a declarative tool allowlist. We mapped this through a **SCQAB** framework — Situation (tools scattered across R/Python/DBs) → Complication (chat can't prove computation) → Question (lower the barrier while keeping compliance, reproducibility, local security) → Answer (local-first + sandboxed declarative execution) → Build (40 tools, 54 Skills, tests, CI). We also chose Windows-first because that's the dominant OS in the wet-lab teams we serve."

---

## Tier 2 —— 中低概率（补充 / 压力题）

### Q10. "竞速 / 并行 / 恢复 / Hook / Feature Flag" 这些特性是真的在跑吗？
**问法变体**：① "Is your 'parallel + racing' claim real?" ② "Some READMEs overstate features — what actually runs?"

**中文要点**：都给证据，不夸大。
- **依赖感知并行**：Planner 出并行组时按拓扑分批执行（真实现 + 测试）。
- **DEG 竞速**：continuous vs count 两个 DEG 工具注册 `racing_group="deg_analysis"`，`parallel_executor` 调 `race_tools()` 取首个成功（真接入 + 测试）。
- **恢复策略**：文件解析/编码/列缺失等六类自动恢复（有测试）。
- 坦承：部分高级项（Racing 之外的某些实验性能力）在文档里诚实标注，避免过度承诺。

**English answer**:
"All the features we claim are wired and tested: dependency-aware **parallel** execution batches planner steps by group; **DEG racing** genuinely races the continuous-expression and count-based DEG tools (both registered with `racing_group="deg_analysis"`) and returns the first success; **recovery strategies** auto-handle file-parse/encoding/column-missing errors. Where something is still experimental, we mark it honestly rather than overstating it — our principle is 'what it says, it must run'."

---

### Q11. 软件的可访问性 / 谁真的用过？
**问法变体**：① "Has a real non-expert used this?" ② "Any adoption beyond your team?"

**中文要点**：
- 面向人群明确（生信湿实验研究者）；界面做中文自然语言 + 会话隔离 + 文件回传。
- 诚实回答：当前主要是团队内部使用 + 开放给 iGEM 社区（开源、文档、CI 齐备）；"真实第三方用户"若有则补证据，没有就讲清楚定位与下一步（见 Q14）。

**English answer**:
"We designed it for and validated it with our own interdisciplinary team (clinicians, materials scientists, computational biologists) during DENTAL SHIELD. It is now open-source with documentation, CI, and a reproducible launcher so the bioinformatics community can adopt it. If you push on external adoption, I'll be honest: the tool is ready and open, and growing real third-party users is our immediate post-competition goal."

---

### Q12. 安全 / 合规 / 生物安全（把软件和主项目连起来问）
**问法变体**：① "How does the software support your project's safety/ethics?" ② "Any dual-use or data-risk concerns?"

**中文要点**：
- 主项目 DENTAL SHIELD 有双重安全模块（Δalr 营养缺陷自杀 + ΔnisK 屏蔽本底）+ 伦理评审 + 定量伦理风险评估模型——软件页 HP 里写了。
- 软件侧：无病原体/序列生成类工具；危险文件（html/svg/js）强制下载 + CSP；文献 SSRF 防护；本地数据不出机。
- 负责任立场：生信分析工具本身不产生生物体，风险主要在数据隐私（已按本地优先处理）。

**English answer**:
"Two angles. Biologically, DENTAL SHIELD uses dual safety modules — a Δalr auxotrophy self-destruct and ΔnisK background silencing — plus ethics review and a quantitative ethical-risk model. The software touches no wet-lab risk: it performs computational analysis only, so its main risk is data privacy, which we handle by being local-first. We also harden against malicious inputs (path traversal, SSRF, dangerous inline-file handling)."

---

### Q13. 归因（Attribution）—— 谁做了什么？
**问法变体**：① "Who built this, and who did what?" ② "Any attribution you want to highlight?"

**中文要点**：
- 团队 LZU-GANSU（兰州大学），34 名成员（口腔/临床/预防医学/公卫/生科/生态/材料等），PI：Cheng Peng、He Dengqi，另有副 PI/讲师/顾问。
- 软件侧归属 + GitHub 开发史公开；iGEM 官方软件仓库在 GitLab `2026/software/lzu-gansu/bio-agent`。
- （按队伍 Attributions Form 最终版补齐个人署名。）

**English answer**:
"Team LZU-GANSU from Lanzhou University — 34 members across medicine, dentistry, life sciences, materials, and engineering, led by PIs Prof. Cheng Peng and Prof. He Dengqi. The software component is maintained in our dedicated iGEM GitLab repo with a public development history on GitHub. Individual member credits align with our Attributions Form on the wiki."

---

### Q14. 下一步 / 商业化 / 长期影响？
**问法变体**：① "What's next for the software?" ② "How will it make a wider impact?"

**中文要点**：
- 短期：扩大真实用户、补更多 Skill（单细胞注释/拟时序、空间反卷积等规划中的能力）、完善文档/教程视频。
- 长期：作为标准化生信工作站的开放基座，降低生信门槛、提升可复现性；服务资源有限的团队（呼应 DENTAL SHIELD 关注口腔健康资源匮乏地区）。
- 商业模式诚实回答：以开源 + 社区为主，现阶段重心是影响而非盈利。

**English answer**:
"Short term: grow real users, add the planned Skills (single-cell annotation/trajectory, spatial deconvolution, docking), and produce tutorials. Long term: make BioAI Agent an open, standard base for reproducible bioinformatics, lowering the entry barrier for under-resourced teams — mirroring DENTAL SHIELD's own focus on people with scarce access to care. Our current priority is impact and adoption, not revenue."

---

### Q15. （压力题）"这不就是一个调用 DeepSeek 的壳吗？" / "为什么相信你的工具比专家手动更省事？"
**问法变体**：① "Isn't this just a wrapper around an LLM?" ② "A bioinformatician could just run R — why your tool?"

**中文要点**：
- 不是"LLM 壳"：LLM 只做规划与路由，真正执行的是 40 个预注册的确定性工具 + 可终止/可审计边界——这是"Agent"与"包装"的本质区别。
- 面向的不是"已经会跑 R 的专家"，而是"有生物学问题、但被环境/依赖/格式拖住的人"；我们消除的是重复劳动，不是替代专家判断。

**English answer**:
"Fair challenge. If the LLM wrote R code, it *would* just be a shell — that's exactly what we rejected. Here the LLM only plans and routes; execution is 40 deterministic, version-controlled tools inside a killable, auditable sandbox. And the target user is not the bioinformatician who already runs R — it's the biologist whose bottleneck is environment setup, format checking, dependency conflicts, and reproducible bookkeeping. We remove the friction, never the expert's judgment."

---

## 附：三句万能收尾（被追问时）

- 中文："我们有一条底线：**文档里写的能力，就必须有对应的测试或真实执行证据**。您问到的每一点，我都能在仓库里指到对应文件。"
- English: "Our one constant rule is: **if we claim it, there is a test or a real-execution record for it.** Anything you ask, I can point to the file in the repo."

> 上台前复核：`python -m pytest -q backend/tests`（当前 230 passed）；`README_FEATURE_VERIFICATION.md` 里的数字；Attribution 最终版。