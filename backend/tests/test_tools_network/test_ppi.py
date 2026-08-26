import json
from typing import Any

import httpx
import pytest

from bioagent.enums import Category, Runtime
from bioagent.tools.network.ppi import TOOL, run


_FIXTURE = (
    "score\tpreferredName_B\tpreferredName_A\n"
    "0.9\tMDM2\tTP53\n"
    "0.8\tBRCA1\tTP53\n"
    "0.7\tUNKNOWN\tTP53\n"
)


class _FakeResponse:
    def __init__(self, text: str, status: int = 200) -> None:
        self.text = text
        self._status = status

    def raise_for_status(self) -> None:
        if self._status != 200:
            request = httpx.Request("GET", "https://string-db.org/api/tsv/network")
            response = httpx.Response(self._status, request=request)
            raise httpx.HTTPStatusError("boom", request=request, response=response)


class _FakeClient:
    def __init__(self, text: str, status: int = 200) -> None:
        self._text = text
        self._status = status

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        pass

    async def get(self, url: str, params: dict[str, str]) -> _FakeResponse:
        return _FakeResponse(self._text, self._status)


@pytest.fixture
def fake_httpx(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    client = _FakeClient(_FIXTURE)
    monkeypatch.setattr(httpx, "AsyncClient", lambda: client)
    return client


@pytest.fixture
def fake_httpx_error(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    client = _FakeClient(_FIXTURE, status=500)
    monkeypatch.setattr(httpx, "AsyncClient", lambda: client)
    return client


async def test_run_success(fake_httpx: _FakeClient) -> None:
    result = await run(["TP53", "MDM2", "BRCA1"])
    assert {n["id"] for n in result["nodes"]} == {"TP53", "MDM2", "BRCA1"}
    assert len(result["edges"]) == 2  # UNKNOWN 边被过滤
    by_id = {n["id"]: n["degree"] for n in result["nodes"]}
    assert by_id["TP53"] == 2
    assert by_id["MDM2"] == 1
    assert all(isinstance(e["score"], float) for e in result["edges"])


async def test_run_json_serializable(fake_httpx: _FakeClient) -> None:
    result = await run(["TP53", "MDM2", "BRCA1"])
    json.dumps(result)  # 不抛（无 numpy 类型）
    assert all(isinstance(n["degree"], int) for n in result["nodes"])


async def test_run_empty_gene_list() -> None:
    result = await run([])
    assert result == {"nodes": [], "edges": []}


async def test_run_non_200(fake_httpx_error: _FakeClient) -> None:
    with pytest.raises(httpx.HTTPStatusError):
        await run(["TP53", "MDM2"])


def test_tool_shape() -> None:
    assert TOOL.name == "ppi_network"
    assert TOOL.category is Category.NETWORK
    assert TOOL.runtime is Runtime.PYTHON
    assert TOOL.run is not None
    assert TOOL.r_script is None
