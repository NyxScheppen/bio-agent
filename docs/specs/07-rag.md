# RAG 向量检索（Embedder + RagClient）

> 范围：`backend/bioagent/rag.py`（`Embedder` + `RagClient`）。本地 sentence-transformers 向量化 + Qdrant 检索（Docker 独立容器）。
> 纯基础设施 spec：只管「文本 → 向量 → 查 top_k / 写入」，不含知识库内容/清洗/分块策略（那是数据工程）、不含 Facade、不含 API。
> `Embedder` / `RagClient` 定义内联在本文件；`embedding.model` / `rag.*` 取自 02-config（由组合根传入，非本 spec import）。

## 元信息

- **包根路径**：Python 包 `bioagent` 源码在 `backend/bioagent/`，import 为 `bioagent.xxx`（`backend/` 在 sys.path 上）
- **前置依赖**：02-config（`EmbeddingConfig` / `RagConfig` 的字段语义对应构造参数，但 `rag.py` **不 import** 任何 `bioagent` 模块）

## 用户故事

> 作为 bio agent 系统的开发者，我想要一个文本向量化 + Qdrant 检索的单一入口，以便 planner 与 reporter 用「query 一个文本 → 拿 top_k 相关块」做领域知识接地（规划接地 + 用户问知识时的报告接地），写入与查询都走同一条路。

## 验收标准

- [ ] `backend/bioagent/rag.py` 含 `Embedder` + `RagClient`，与「`backend/bioagent/rag.py`（完整）」段代码逐字一致
- [ ] `Embedder.embed(text)` 返回 `list[float]`（长度 = 模型维度）；`dim` 属性返回维度
- [ ] `RagClient.ensure_collection()` 建 collection（维度 = embedder.dim、距离 COSINE）
- [ ] `RagClient.query(text)` 返回 `list[dict]`（每条 `{"text", "score"}`），条数 ≤ top_k
- [ ] `RagClient.ingest(documents)` 上传向量点，返回写入条数
- [ ] `pyright` strict 零报错

## 技术方案

- **新文件**：`backend/bioagent/rag.py`（无 Facade、无 API、无数据变更）
- **库**：`sentence-transformers`（本地 embedding，`all-MiniLM-L6-v2`，dim=384）、`qdrant-client`（`AsyncQdrantClient`，Docker 独立容器，url 来自 `config.rag.qdrant_url`）
- **公开面**：`from bioagent.rag import Embedder, RagClient`（不加 `__all__`）
- **谁构造**：组合根（`main.py`，归 10-api）用 `config.embedding.model` 建 `Embedder`，用 `config.rag.*` 建 `RagClient`，注入 planner 与 reporter（09-orchestration，两处接地）。与 06-r-runner 同款注入
- **Embedder 是同步纯计算**：sentence-transformers 是 CPU/GPU 计算非 I/O，故 `embed()` 保持同步（符合 CLAUDE.md「纯计算函数保持同步」）。查询时单条短文本、耗时可忽略；**写入（ingest）是离线批量**（seed 脚本/启动时，不在请求路径）
- **collection 建一次**：`ensure_collection()` 由组合根在启动时调（幂等由 Qdrant 的 `collection_exists` 判定），query/ingest 前不重复建
- **Qdrant 是 Docker 独立容器**：compose 里 app + qdrant 两个服务，url 指向 `http://qdrant:6333`（容器名）或 `localhost:6333`（开发）
- **依赖 pin（实现时锁）**：`sentence-transformers`、`qdrant-client` 锁精确版本；`query_points`/`upsert`/`create_collection` 的方法签名以锁定版本为准，升级须重跑本 spec 测试
- **不做**：不做分块/清洗策略（数据工程，非本 spec）；不内嵌知识库内容；不做多 collection 管理（MVP 单 collection）

### `backend/bioagent/rag.py`（完整）

```python
from typing import Any, cast

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer


class Embedder:
    """文本向量化：本地 sentence-transformers（同步，CPU/GPU 计算）。"""

    def __init__(self, model_name: str) -> None:
        self._model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]:
        return cast(list[float], self._model.encode(text).tolist())  # pyright: ignore[reportUnknownMemberType]

    @property
    def dim(self) -> int:
        return cast(int, self._model.get_embedding_dimension())


class RagClient:
    """Qdrant 检索客户端：建 collection / 写入 / 查询 top_k。"""

    def __init__(self, embedder: Embedder, url: str, collection: str, top_k: int) -> None:
        self._embedder = embedder
        self._collection = collection
        self._top_k = top_k
        self._client = AsyncQdrantClient(url=url)

    async def ensure_collection(self) -> None:
        if not await self._client.collection_exists(self._collection):
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=self._embedder.dim, distance=Distance.COSINE),
            )

    async def ingest(self, documents: list[dict[str, str]]) -> int:
        """写入文本块，返回条数。document = {"id": str, "text": str}。"""
        points: list[PointStruct] = []
        for doc in documents:
            vector = self._embedder.embed(doc["text"])
            points.append(
                PointStruct(id=doc["id"], vector=vector, payload={"text": doc["text"]})
            )
        if points:
            await self._client.upsert(collection_name=self._collection, points=points)
        return len(points)

    async def query(self, text: str) -> list[dict[str, Any]]:
        vector = self._embedder.embed(text)
        result = await self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=self._top_k,
        )
        return [
            {"text": (point.payload or {}).get("text", ""), "score": point.score}
            for point in result.points
        ]

    async def close(self) -> None:
        await self._client.close()
```

## 测试要点

- [ ] 单元测试 `tests/test_rag/`（`pytest-asyncio`，注入 fake `Embedder` 与 fake `AsyncQdrantClient`）：
  - [ ] `Embedder.embed`：注入 fake `SentenceTransformer`（`encode` 返回预设 numpy 向量）→ `embed("x")` 返回 `list[float]`；`dim` 返回 `get_sentence_embedding_dimension()` 的值
  - [ ] `RagClient.query`：fake client 的 `query_points` 记录 `collection_name`/`query`（= fake embedder 返回的向量）/`limit`（= top_k）；返回预设 points → `query()` 输出 `[{"text", "score"}]`
  - [ ] `RagClient.query` 兜底：返回的 point `payload=None` 或 `payload` 缺 `"text"` → 不崩，对应 `text` 为 `""`（`score` 仍照填）
  - [ ] `RagClient.ingest`：fake `upsert` 记录 points（id/vector/payload）；返回 `len(documents)`；空列表 → 返回 0 且不调 `upsert`
  - [ ] `RagClient.ensure_collection`：`collection_exists` 返回 `False` → 调 `create_collection`（dim = embedder.dim、COSINE）；返回 `True` → 不调
  - [ ] `RagClient.close` 调 `client.close()`
- [ ] 集成测试：无（不连真实 Qdrant / 不下载真实模型）
- [ ] E2E 测试：无

## 完成定义

- [ ] `ruff check` 零报错
- [ ] `pyright` 零报错
- [ ] `pytest` 全绿
- [ ] `test-inventory.md` 已更新
- [ ] 组合根（10-api）用 `config.embedding.model` + `config.rag.*` 构造 `Embedder`/`RagClient`，启动时 `ensure_collection()`；planner 与 reporter 经注入的 `RagClient` 做检索接地（见 09-orchestration）
