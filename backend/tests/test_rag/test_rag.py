from typing import Any, cast

import pytest
from qdrant_client.models import Distance, PointStruct, VectorParams

from bioagent import rag
from bioagent.rag import Embedder, RagClient


class _Vec:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def tolist(self) -> list[float]:
        return self._values


class _FakeModel:
    def __init__(self, dim: int = 3) -> None:
        self._dim = dim

    def encode(self, text: str) -> _Vec:
        return _Vec([0.1, 0.2, 0.3])

    def get_embedding_dimension(self) -> int:
        return self._dim


class _FakeEmbedder:
    def __init__(self, dim: int = 384, vector: list[float] | None = None) -> None:
        self._dim = dim
        self._vector = vector if vector is not None else [0.1] * dim

    def embed(self, text: str) -> list[float]:
        return self._vector

    @property
    def dim(self) -> int:
        return self._dim


class _FakePoint:
    def __init__(self, payload: dict[str, Any] | None, score: float) -> None:
        self.payload = payload
        self.score = score


class _FakeQueryResponse:
    def __init__(self, points: list[_FakePoint]) -> None:
        self.points = points


class _FakeQdrant:
    def __init__(self) -> None:
        self.exists = False
        self.created: list[tuple[str, VectorParams]] = []
        self.upserted: list[list[PointStruct]] = []
        self.query_points_result: list[_FakePoint] = []
        self.query_calls: list[dict[str, Any]] = []
        self.closed = False

    async def collection_exists(self, name: str) -> bool:
        return self.exists

    async def create_collection(self, collection_name: str, vectors_config: VectorParams) -> bool:
        self.created.append((collection_name, vectors_config))
        return True

    async def upsert(self, collection_name: str, points: list[PointStruct]) -> None:
        self.upserted.append(points)

    async def query_points(self, collection_name: str, query: Any, limit: int) -> _FakeQueryResponse:
        self.query_calls.append({"collection_name": collection_name, "query": query, "limit": limit})
        return _FakeQueryResponse(self.query_points_result)

    async def close(self) -> None:
        self.closed = True


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    embedder: Embedder | None = None,
    top_k: int = 5,
    exists: bool = False,
) -> tuple[RagClient, _FakeQdrant]:
    fake_client = _FakeQdrant()
    fake_client.exists = exists

    def factory(url: str) -> _FakeQdrant:
        return fake_client

    monkeypatch.setattr(rag, "AsyncQdrantClient", factory)
    emb = embedder if embedder is not None else cast(Embedder, _FakeEmbedder())
    client = RagClient(emb, "http://localhost:6333", "kb", top_k)
    return client, fake_client


# ---- Embedder ----

def test_embedder_embed_and_dim(monkeypatch: pytest.MonkeyPatch) -> None:
    def factory(name: str) -> _FakeModel:
        return _FakeModel(dim=3)

    monkeypatch.setattr(rag, "SentenceTransformer", factory)
    embedder = Embedder("all-MiniLM-L6-v2")
    assert embedder.embed("hello") == [0.1, 0.2, 0.3]
    assert embedder.dim == 3


# ---- RagClient.query ----

async def test_query_records_and_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_embedder = _FakeEmbedder(dim=384, vector=[0.5, 0.6])
    client, fake_client = _make_client(monkeypatch, embedder=cast(Embedder, fake_embedder), top_k=3)
    fake_client.query_points_result = [
        _FakePoint({"text": "alpha"}, 0.9),
        _FakePoint({"text": "beta"}, 0.8),
    ]
    result = await client.query("query text")
    assert result == [{"text": "alpha", "score": 0.9}, {"text": "beta", "score": 0.8}]
    assert fake_client.query_calls[0]["collection_name"] == "kb"
    assert fake_client.query_calls[0]["query"] == [0.5, 0.6]
    assert fake_client.query_calls[0]["limit"] == 3


async def test_query_payload_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake_client = _make_client(monkeypatch)
    fake_client.query_points_result = [
        _FakePoint(None, 0.9),
        _FakePoint({"no_text": "x"}, 0.8),
    ]
    result = await client.query("q")
    assert result == [{"text": "", "score": 0.9}, {"text": "", "score": 0.8}]


# ---- RagClient.ingest ----

async def test_ingest_uploads_and_returns_count(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_embedder = _FakeEmbedder(dim=2, vector=[0.1, 0.2])
    client, fake_client = _make_client(monkeypatch, embedder=cast(Embedder, fake_embedder))
    docs = [{"id": "a", "text": "doc a"}, {"id": "b", "text": "doc b"}]
    count = await client.ingest(docs)
    assert count == 2
    points = fake_client.upserted[0]
    assert [str(p.id) for p in points] == ["a", "b"]
    assert points[0].vector == [0.1, 0.2]
    assert points[0].payload == {"text": "doc a"}


async def test_ingest_empty_skips_upsert(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake_client = _make_client(monkeypatch)
    count = await client.ingest([])
    assert count == 0
    assert fake_client.upserted == []


# ---- RagClient.ensure_collection ----

async def test_ensure_collection_creates_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_embedder = _FakeEmbedder(dim=384)
    client, fake_client = _make_client(monkeypatch, embedder=cast(Embedder, fake_embedder), exists=False)
    await client.ensure_collection()
    assert len(fake_client.created) == 1
    name, params = fake_client.created[0]
    assert name == "kb"
    assert params.size == 384
    assert params.distance == Distance.COSINE


async def test_ensure_collection_skips_when_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake_client = _make_client(monkeypatch, exists=True)
    await client.ensure_collection()
    assert fake_client.created == []


# ---- RagClient.close ----

async def test_close(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake_client = _make_client(monkeypatch)
    await client.close()
    assert fake_client.closed
