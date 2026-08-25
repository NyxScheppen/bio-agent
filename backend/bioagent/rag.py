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
