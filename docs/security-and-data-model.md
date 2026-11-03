# 安全与数据模型（威胁模型 / 数据隐私）

> 用于回答 iGEM 评委的「数据存哪、谁能访问、何时删、威胁模型是什么」类问题，
> 以及答辩时的 Responsible AI 部分。所有描述均对应仓库当前代码。

## 定位

本地**单用户** AI 生信工具，默认绑定 `127.0.0.1`（`API_HOST`），面向在个人电脑上运行的研究者。设计上信任**同一台机器的当前用户**，不面向公网多租户部署。

## 会话模型

- **多会话**：每个对话 = 一个 session，历史消息、上传文件、生成文件均按 `session_id` 隔离。
- **session_id 生成**：前端用 `crypto.randomUUID()`（128 位随机，不可猜测，见 `frontend/src/App.jsx`）；后端 `validate_session_id`（`backend/app/utils/storage_contracts.py`）校验格式为 1–64 位 ASCII 字母/数字/下划线/连字符。
- **已移除 `"default"` 兜底**：不传 `session_id` 时，`/api/chat` 会拒绝、`/api/upload` 返回 422，杜绝「所有人挤进同一个 default 桶」的串号问题。

## 数据存储与生命周期

| 数据类型 | 位置 | 清理时机 |
|---|---|---|
| 上传文件 | `backend/storage/uploads/{session_id}/` | 删除会话时物理删除 |
| 生成文件 | `backend/storage/generated/{session_id}/` | 删除会话时物理删除 |
| 临时/暂存 | `backend/storage/temp` 及 `.upload-*` / `.delete-*` 暂存名 | 上传完成即原子发布 / 失败即清理 |
| 数据库 | `backend/db_data/*.db`（SQLite） | 删除会话清 message / file / tool_execution 记录 |

删除入口：`DELETE /api/chat/session/{session_id}` → 由 `session_service.delete_session_with_files` 统一删除物理文件 + 数据库记录 + 会话记忆。

## 访问与网络边界

- 默认只监听 `127.0.0.1`，不绑定公网地址。
- **CORS 白名单**（`backend/app/core/config.py` 的 `CORS_ORIGINS`，默认 `http://localhost:5173`、`http://127.0.0.1:5173`），已移除 `allow_origins=["*"]`。
- `/files/{path}` 严格限定在 `uploads` / `generated` 根下，防路径穿越（拒绝 `..`、拒绝符号链接），危险内联文件（`.html`/`.svg`/`.js`/`.css` 等）强制附件下载并加 `Content-Security-Policy: sandbox`。
- 文献工具对下载 URL 做 SSRF 校验（仅 `http/https`，拒绝 `file://` 与非 http 重定向，见 `backend/app/tools/literature_tools.py`）。

## 外部服务依赖

KEGG、MSigDB/Zenodo、STRING、Europe PMC 等实时在线服务；外部端点失败不会被记为分析成功（见 `docs/README_FEATURE_VERIFICATION.md`）。

## 已知边界（诚实声明）

1. **无鉴权 / 无多租户**：接口把 `session_id` 当作能力凭证——持有 session_id 即可访问该会话。对「单机单用户、仅监听 127.0.0.1」的运行方式足够；若要部署到局域网或公网，必须补认证、会话所有权校验与 TLS。
2. **本机其它进程可直连 8000 端口**：CORS 只限制浏览器跨域来源，不阻止非浏览器客户端。这是本地工具可接受的边界。
3. **LLM 结果需人工复核**：分析输出可能受模型幻觉影响，当前尚未在 Reporter 输出中强制标注不确定性（已列入后续整改）。

## Responsible AI

- 模型：DeepSeek chat（OpenAI 兼容接口，`backend/app/core/config.py` 可配置）。
- 局限：LLM 生成的分析结果需研究人员复核；外部数据库的质量与实时可用性不可完全控制。