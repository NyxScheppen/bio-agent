# 上传文件、生成文件与图片行为契约

本文定义后端对上传、文件解析、工具产物、图片、下载和删除的运行时行为。新增文件工具或生成型分析工具时必须保持这些契约。

## 存储布局

```text
backend/storage/
  uploads/{session_id}/{filename}
  generated/{session_id}/{job_id}/{artifact}
  temp/
```

通过工具生命周期执行的注册工具必须使用注入的 `job_dir`。没有生命周期的内部直接调用使用带随机后缀的独立目录，不能复用固定全局输出目录。

`session_id` 必须匹配：

```text
^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$
```

这意味着长度为 1 到 64，只允许 ASCII 字母、数字、下划线和连字符，且首字符必须为字母或数字。接口不会把非法 ID 静默改写成另一个目录。

## 上传接口

`POST /api/upload` 接收 multipart `files` 和 `session_id`。正常返回中的 URL 是相对地址：

```json
{
  "filename": "expression matrix.csv",
  "relative_path": "uploads/session-1/expression matrix.csv",
  "url": "/files/uploads/session-1/expression%20matrix.csv",
  "type": "table",
  "size_bytes": 1024
}
```

资源限制在服务启动时从环境变量读取：

| 变量 | 默认值 | 含义 |
|---|---:|---|
| `MAX_UPLOAD_FILES` | 20 | 单批文件数 |
| `MAX_UPLOAD_FILE_BYTES` | 104857600 | 单文件实际内容字节数 |
| `MAX_UPLOAD_BATCH_BYTES` | 262144000 | 单批所有文件实际内容总字节数 |

请求体还有一个派生上限 `MAX_UPLOAD_REQUEST_BYTES`，等于批次上限加 multipart 开销预算。它在 Starlette 解析和临时落盘 `UploadFile` 之前生效。超过请求体或文件内容预算返回 HTTP 413；非法 ID 或文件名返回 HTTP 400。

文件名处理规则：

1. 删除客户端目录前缀，只保留 basename。
2. 控制字符和 Windows 非法字符替换为下划线。
3. 去除末尾的点和空格。
4. 空名称、`.`、`..`、Windows 保留名和 UTF-8 超过 240 字节的名称被拒绝。
5. 大小写不敏感的 `.upload-` 和 `.delete-` 前缀属于内部保留名，上传时直接拒绝。
6. 同名文件依次使用 `_1`、`_2` 等后缀，不覆盖已有文件。

上传先写入同目录 `.upload-<uuid>.tmp`，完成流式预算检查、`flush` 和 `fsync` 后，再以不覆盖语义原子发布。最终文件名在完整内容写完之前不可下载。

一个上传批次是全有或全无：任一文件读取、预算、发布或数据库操作失败，数据库回滚，并删除本批已发布文件和暂存文件。

## 上传列表和单文件删除

`GET /api/uploads/{session_id}` 只列出该会话目录中的普通文件。查询不存在的会话不会创建目录；`.upload-*` 和 `.delete-*` 不可见。

`DELETE /api/uploads/{session_id}/{filename}` 执行：

1. 为目标创建同目录 `.delete-<uuid>.tmp` 硬链接守卫，但保留原文件名；
2. 删除对应 upload 数据库记录并提交；
3. 提交成功后确认守卫与公开路径仍指向同一实体，再删除两条链接；
4. 提交失败则回滚并只删除守卫，原路径从未释放。

因此删除事务进行时，并发同名上传会获得 `_1` 等后缀；失败回滚不会覆盖并发上传的新内容，也不会按相同路径误删它的数据库记录。找不到实体文件返回 404。

## 文件解析

带 `session_id` 的工具解析遵循严格规则：

- 纯文件名只检查 `uploads/{session_id}/`；
- `uploads/...` 必须属于当前会话；
- `generated/...` 必须属于当前会话；
- 未命中返回 `None`，不扫描其他会话，不回退到 storage 根目录；
- storage 外绝对路径、路径穿越和非法会话 ID 返回 `None`。

没有 session 的内部兼容调用可以按纯文件名惰性搜索 storage。Agent 入口和注册工具的正常调用应始终携带 session，不能依赖这个兼容行为。

## 表格和压缩文件预览

预览只返回有限行和最多 80 个列名，不返回完整数据。相关环境变量：

| 变量 | 默认值 | 行为 |
|---|---:|---|
| `MAX_PREVIEW_SCAN_BYTES` | 67108864 | 普通文本总行数扫描和 `.xls` 大小上限 |
| `MAX_PREVIEW_DECOMPRESSED_BYTES` | 134217728 | gzip 行数扫描和 XLSX 未压缩成员总量上限 |
| `MAX_PREVIEW_LINE_BYTES` | 2097152 | 单行/单字段早期预算 |
| `MAX_PREVIEW_XLSX_ENTRIES` | 10000 | XLSX ZIP 中央目录最大条目数 |

普通 CSV/TSV 超过扫描上限时，仍可读取前几行，但 `shape.rows` 为 `null`，并注明未统计总行数。gzip 行数扫描达到解压预算后停止。XLSX 在构造 `ZipFile` 之前以常量内存解析中央目录，拒绝条目数超限、分卷、ZIP64 或目录结构异常的容器；随后才累计 member 的 `file_size`，解压预算超限时拒绝预览。

`.xls` 不是 ZIP 容器，只应用普通扫描大小上限。此规则不把预览工具当作通用恶意文档沙箱。

## 工具产物生命周期

生命周期为每次调用创建唯一 `job_id` 和：

```text
generated/{session_id}/{job_id}/
```

如果函数签名包含 `job_dir`、`session_id` 或 `context`，执行器自动注入对应值。生成型工具应只在 `job_dir` 下写文件，并通过相对路径或显式 `output_files` 返回。

执行结束后：

1. 扫描当前 job 目录；
2. 合并工具显式声明的文件；
3. 解析所有候选的真实路径；
4. 只保留当前 job 内实际存在的普通文件；
5. 从实际路径重建 `name`、`relative_path`、URL 和字节数；
6. 按规范路径去重。

声明不存在的文件、其他 job/session 的文件或 upload 文件不会进入最终 `ToolResult.output_files`。工具不能通过伪造 `name`、URL 或类型把任意路径登记成产物。

## 图片行为

PNG、JPEG、GIF、WebP 等普通图片作为 `image` 文件类型返回，可由前端以内联图片展示。SVG 属于主动内容，即使文件类型推断为 image，下载路由也强制作为二进制附件返回，不能以内联 SVG 执行脚本。

生成图片和其他产物使用相同的 job 所有权、存在性和数据库去重规则。动态 gene/project 名称不应直接进入输出文件名；使用稳定文件名，把分析参数放入 provenance 或结果表。

## 聊天附件和回复兜底

前端提交的 `attached_files` 不受信任。进入 Agent 上下文前，后端要求：

- 路径位于 uploads 或 generated；
- 路径的第二段等于当前 `session_id`；
- 文件实际存在且为普通文件；
- 文件名、类型、大小和 URL从实际文件重建。

Agent 显式返回的文件只接受当前会话 generated 文件。展示名和文件类型来自规范路径，不使用模型提供的伪造值。

当 Agent 没有显式文件时，后端可以从回复文本提取文件引用：

- 完整路径必须是当前会话 generated 路径；
- 带斜杠的相对路径被解释为当前会话 generated 子路径；
- 单独 basename 只在当前会话 generated 树中搜索，按修改时间取最近三个；
- URL 编码穿越、upload 路径和其他会话路径被丢弃。

最终文件记录按 `session_id + relative_path` 去重。

## 文件下载

`GET|HEAD /files/{relative_path}` 只允许 `uploads` 和 `generated` 根。响应统一设置：

```text
X-Content-Type-Options: nosniff
Cache-Control: private, no-store
```

HTML、HTM、XHTML、SVG、XML、JS、MJS 和 CSS 额外使用：

```text
Content-Type: application/octet-stream
Content-Disposition: attachment
Content-Security-Policy: sandbox; default-src 'none'
```

临时名、删除守卫、目录、缺失文件和穿越路径返回 404。

当前应用没有用户认证层，因此 `/files` 不是基于登录用户的授权下载接口。它防止目录逃逸和主动内容执行，但知道有效 URL 的客户端仍可请求该文件。若以后加入多用户认证，应在该路由增加会话/用户授权，不能只依赖路径不可猜测。

## R 生成型工具

`run_r_analysis` 是注册领域工具的内部执行器，不注册为 Agent 可调用工具。R 模板遵循：

- Python 字符串进入 R 字符串前转义反斜杠、双引号和控制字符；
- 公式/列名只允许 `^[A-Za-z_][A-Za-z0-9_.]*$`；包含空格、连字符或反引号的列名当前会被拒绝；
- 多列参数用逐项转义的 R character vector；
- 预处理模式只允许 `auto`、`log2`、`non_log2`、`raw_count`，ML 额外允许 `none`；
- 数值参数在 Python 侧转换并限制范围；
- 生命周期注入的 job 目录必须位于 generated 根下；
- 生命周期会从 `generated/{session_id}/{job_id}` 派生 session，并把 `smart_read` 与 R 文件连接限制在该 session 的 upload/generated 根；
- `analysis.R` 不作为用户产物返回。

没有 session 的内部直接调用保留 storage 范围兼容模式。R prelude 的路径限制和函数遮蔽仍只是纵深防护，不构成任意 R 代码沙箱。新增领域工具只能拼接经过结构校验的模板参数，不得把用户或模型提供的任意 R 源码传入执行器。

## 会话清理

generated-only 清理只处理 `source_type=generated` 的记录和实体文件，保留：

- ChatSession；
- ChatMessage；
- upload 文件和记录；
- tool execution log。

完整会话删除处理 upload 和 generated 文件，并删除消息、工具执行日志和会话记录。实体文件在数据库事务期间保留公开路径，并用同目录硬链接守卫固定实体身份；数据库提交成功后才物理删除。数据库失败只删除守卫，原路径从未释放，因此不会覆盖并发上传。

兼容历史数据：

- 实体已缺失时删除失效记录；
- 多会话共享同一 `relative_path` 时只删当前记录，不物理删除；
- `generated/<legacy_job_id>/<file>` 形式的升级前、无共享引用生成物可随当前会话删除；若第二段仍对应一个现存会话，则按跨会话路径拒绝；
- 当前记录指向其他会话且没有其他引用时，视为非法状态并中止整个事务；
- 目录不会按文件记录递归删除。

API 不执行目录级兜底删除；实体删除决策只由持有数据库引用上下文的服务层完成。服务成功后 API 仅清空会话内存，服务失败时不得清空内存。

## 扩展规范

新增上传或解析入口时：

1. 复用 `storage_contracts`，不要再实现一套 session/path 正则。
2. 同时考虑请求体、实际文件流、解压体积和单行/单字段四种资源预算。
3. 数据库与磁盘跨资源操作采用暂存、提交、恢复顺序。
4. 返回相对 `/files` URL，并对路径段做 URL 编码。

新增生成型工具时：

1. 函数签名接受 `job_dir`，并把它传给底层执行器。
2. 只写 job 目录；不要使用固定全局输出目录。
3. 文件名使用稳定 ASCII 名称；用户文本只进入经过校验的文件内容或元数据。
4. 返回真实 `output_files`，但仍预期生命周期会复核存在性和所有权。
5. 为越界声明、不存在文件和同名产物增加测试。

## 验证命令

```powershell
cd backend
python -m compileall -q app tests
python -m pytest -q tests/test_file_artifact_contracts.py
python -m pytest -q
```
