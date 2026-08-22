# How: 安全规范

## 原则

基础安全——防常见漏洞和泄露，不追求军工级防护。MVP 单用户本地/内网部署，不做多租户。

## API Key 管理

- LLM API Key（DeepSeek 等）通过 `.env` 注入环境变量，**绝不硬编码**在源码中
- `.env` 加入 `.gitignore`，不提交到版本控制
- 提供 `.env.example` 模板文件（含空值，不含真实 Key）

## 文件上传安全

- 上传目录固定（如 `data/uploads/`），不信任用户文件名——用 uuid 重命名，原始名只存元数据
- 限制文件类型与大小（表达矩阵/临床数据：CSV/TSV/TXT，上限 100MB）
- 工具读文件一律走 `file_id` → 服务端解析出的安全路径，**不拼接用户输入的原始路径**（防路径穿越）

## R 子进程安全

- `subprocess` 禁用 `shell=True`，参数用列表传（防命令注入）
- R 脚本是服务端固定代码，**不接受用户提供的 R 代码**
- 传给 R 的数据/参数经 JSON 序列化，不拼接进命令字符串

## 网络出口（防 SSRF）

- 出站请求仅允许固定域名白名单：LLM API、STRING、PubMed、Qdrant
- 不做任意 URL 抓取
- 所有出站请求使用 HTTPS

## CORS

- 后端 CORS 仅允许前端 origin（开发 `localhost`，生产同源）

## 输入安全

- LLM 返回内容在前端渲染前做基本清理（React 默认转义，不把 LLM 输出拼进 `dangerouslySetInnerHTML`）

## 不涵盖

- 不实现用户认证/多账户（MVP 单用户）
- 不做端到端加密
- 不做企业级审计日志（观测走 LangSmith）
