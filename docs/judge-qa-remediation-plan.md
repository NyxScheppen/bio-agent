# iGEM 评委答辩准备 · 问题整改计划

> 目的：把"如果 iGEM 评委提问"倒推出来的风险点，逐条落实成可验证的整改，保证答辩时每个问题都能给出**有代码/测试证据支撑**的回答。
>
> 生成日期：2026-11-03（基于对仓库**当前代码的实测**，而非历史结论）

---

## 0. 重要更正：9 月的历史报告已过时

此前有一份 2026-09-29 的 `graphify-out/PROJECT_REPORT_CN.md`，其中列为 P0/P1 的多数"硬伤"**在当前代码里已经修好了**。本计划以 2026-11-03 重新核实的现状为准：

| 历史报告说的"硬伤" | 当前实测 | 证据 |
|---|---|---|
| 5 个 Skill ID 重复 → 测试失败 | ✅ 已修 | `test_skill_packs.py` 8/8 全绿；54 个 skill 全唯一 |
| 超时只停等待、杀不掉进程 | ✅ 已修 | `tool_process.py` 独立进程 + `taskkill /T /F` 杀进程树；`test_tool_lifecycle.py` 含 `test_process_timeout_reaps_descendant` 等测试 |
| Racing「没接入主链路」 | ✅ 已接入 | `parallel_executor.py:429` 调用 `race_tools()`；DEG 工具注册 `racing_group="deg_analysis"` |
| README 数字漂移（45+ vs 实际） | ✅ 已对齐 | README 现写「54 条 / 22 实现 / 40 工具」，与运行时一致 |
| 前端只有压缩 bundle、无源码 | ✅ 已恢复 | `frontend/src/` 完整 React 源码在仓库内 |
| 前端 session 用弱随机 ID | ✅ 已修 | `frontend/src/App.jsx:31` 用 `crypto.randomUUID()` |

---

## 1. 测试基线（2026-11-03 实测）

- 仓库未安装 `pytest`（`.venv` 里没有），而 `backend/tests/` 有 18 个 `test_*.py`。
- 按仓库约定「直接运行测试脚本」，实测结果：

| 结果 | 数量 | 说明 |
|---|---|---|
| 通过（独立脚本） | **13** | `agent_utils`/`capability_contracts`/`file_resolver`/`file_utils`/`integration`/`multi_agent`/`phase3_verify`/`skill_packs`/`skill_system`/`tool_lifecycle`/`tool_registration`/`tool_result`/`windows_launcher` |
| 跑不了 | **5** | `file_artifact_contracts`、`omics_workflows`、`security_boundaries`、`skill_tool_prompt_contracts` 报 `No module named 'pytest'`；`frontend_delivery` 报 `No module named 'app'` |

**更新（同日）**：已安装 `pytest`（`requirements-dev.txt` 早就声明了它，只是 venv 没装），`python -m pytest -q backend/tests` → **224 passed, 0 failed**。此前 5 个跑不了的文件全部通过；`test_frontend_delivery` 的 `No module named 'app'` 是「单文件直跑」的路径问题，pytest 下正常。**测试全绿达成。**

---

## 2. 剩余工作项（按优先级）

### P0 —— 真安全口子（本次先修）

#### A. CORS 全开（`allow_origins=["*"]`）
- **位置**：`backend/app/main.py:70`
- **风险**：本地服务绑定 `127.0.0.1`，但 CORS 允许任意来源 + 无鉴权，用户浏览器访问任何恶意网页时，该网页可用 `fetch` 读取 `/api/history`、`/files/...`、甚至 DELETE 会话（经典 localhost 服务攻击面）。
- **动作**：改为**可配置白名单**（默认仅本机 Vite 开发来源 `localhost:5173` / `127.0.0.1:5173`；生产前端由 FastAPI 同源提供，无需额外来源）。
- **验收**：`allow_origins` 不再是 `*`；非白名单 Origin 无法跨域读数据。

#### B. `session_id="default"` 共享桶
- **位置**：`backend/app/schemas/chat.py:13`（默认 `"default"`）、`backend/app/api/upload.py:19`（`Form("default")`）
- **风险**：客户端不传 `session_id` 时，所有人挤进同一个 `default` 会话，历史/文件互相串号。
- **动作**：去掉 `"default"` 兜底——chat 缺 session 则拒绝（`handle_chat` 已有空值守卫，只因 schema 默认值绕过了它）；upload 改为必填。
- **注意**：**多 session 模型不变**——每个对话绑定一个 session，前端已用 `crypto.randomUUID()` 生成不可猜 ID，后端只负责校验格式 + 拒绝空值。

### P1 —— 让"全绿"名副其实 + 部署闭合

#### C. ✅ 装 pytest，跑通全量测试（已完成）
- **动作**：`.venv/Scripts/python.exe -m pip install "pytest>=8,<10"`，再 `python -m pytest -q backend/tests`。
- **结果**：`224 passed, 0 failed`，5 个此前跑不了的文件全部通过。

#### D. ✅ 前端构建产物（已确认完整）
- **核实**：`backend/static/index.html` 已是 Vite 构建产物，引用 `assets/index-CeaUZHnE.js`（328 KB，minified）+ CSS；bundle 内含 `crypto.randomUUID()`，即最新前端源码的产物，无需重构建。

#### E. 威胁模型 / 数据隐私文档
- **动作**：在 `TECHNICAL_DOCUMENTATION.md`（或独立 doc）写清——本地单用户定位与 `127.0.0.1` 绑定、session 随机 ID 策略、上传/生成文件的存储位置与删除时机、CORS 白名单策略、外部数据库（KEGG/STRING/Europe PMC 等）依赖声明。
- **验收**：能一句话答"数据存哪、谁能访问、何时删、威胁模型是什么"。

### P2 —— 答辩证据（不改核心逻辑，产出能念的材料）

#### F. Racing/超时 的端到端验证（对应 D2=A、D3=B）
- 两者"已接入"已被代码证实，但**主链路是否真的能触发**仍需一个端到端证据：构造一个 planner 产出 racing_group 的场景，断言最终走了 `race_tools`。
- ResourceMonitor 目前只有起止快照、无后台 CPU/内存采样（`tool_runner.py:96-107`）——要么补采样，要么在文档里把它从"资源限制"降级为"计时监控 + 超时硬终止"。

#### G. 生信数值正确性基准
- 为 DESeq2 / limma / 生存分析各补 1–2 个**已知结果**基准，弥补"只测管道不测数值"的短板。

#### H. 差异化定位 + HP + Attribution + Responsible AI
- 对比 ChatGPT / Galaxy / AutoBA 的 3 分钟口径 + 对比表；真实用户接触记录；source-of-truth 与贡献归属；模型局限与免责声明。

---

## 3. 决策点记录

| 决策 | 结论 | 现状 |
|---|---|---|
| D1 会话模型 | 多 session、每个对话绑定一个 session；ID 不可猜 | 前端已 `crypto.randomUUID()`；遗留 `"default"` 桶 → 本计划 P0-B 修 |
| D2 Racing | 真正接入 executor | 已接入（`parallel_executor.py:429`）→ 剩 P2-F 端到端验证 |
| D3 超时范围 | 只迁高风险/长任务工具 | 已用独立进程覆盖所有工具 → 剩 ResourceMonitor 采样（P2-F） |

---

## 4. 建议执行顺序

`A → B → C → D → E → F → G → H`

（先堵安全口子，再让测试全绿，再闭合部署文档，最后补答辩证据。）