"""測試 app.rag：用 fake embedding client 與 fake store，
不打真的 Ollama，只驗證檢索結果有正確組進 prompt、來源有正確回傳。
"""

from __future__ import annotations

from typing import Any

import pytest

from app import rag
from app.config import Settings
from app.models import Source


class FakeEmbedClient:
    """假的 embedding client：記錄呼叫參數，回傳固定維度但可辨識的向量。"""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def __call__(self, texts: list[str], settings: Settings) -> list[list[float]]:
        self.calls.append(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeStore:
    """假的向量檢索：不碰資料庫，直接回傳預先準備好的來源。"""

    def __init__(self, sources: list[Source]) -> None:
        self._sources = sources
        self.last_query_vec: list[float] | None = None
        self.last_top_k: int | None = None

    def search(self, query_vec: list[float], top_k: int) -> list[Source]:
        self.last_query_vec = query_vec
        self.last_top_k = top_k
        return self._sources


class _FakeChatResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
    """假的 httpx.AsyncClient：攔截 chat 呼叫，把送出的 payload 記錄下來供斷言。"""

    captured_payloads: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        return False

    async def post(self, url: str, json: dict[str, Any]) -> _FakeChatResponse:
        _FakeAsyncClient.captured_payloads.append(json)
        return _FakeChatResponse({"message": {"content": "這是測試回答"}})


@pytest.fixture
def settings() -> Settings:
    return Settings(top_k=3)


@pytest.fixture(autouse=True)
def _reset_captured() -> None:
    _FakeAsyncClient.captured_payloads = []


@pytest.fixture
def patch_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rag.httpx, "AsyncClient", _FakeAsyncClient)


async def test_answer_returns_sources_from_store(settings: Settings, patch_httpx: None) -> None:
    sources = [
        Source(doc_name="manual.pdf", page=3, snippet="重要片段內容", score=0.91),
        Source(doc_name="manual.pdf", page=7, snippet="另一段內容", score=0.85),
    ]
    fake_embed = FakeEmbedClient()
    fake_store = FakeStore(sources)

    result = await rag.answer("這是什麼？", settings, fake_embed, fake_store)

    assert result.sources == sources
    assert result.answer == "這是測試回答"


async def test_answer_embeds_question_and_uses_top_k(settings: Settings, patch_httpx: None) -> None:
    fake_embed = FakeEmbedClient()
    fake_store = FakeStore([])

    await rag.answer("問題文字", settings, fake_embed, fake_store)

    assert fake_embed.calls == [["問題文字"]]
    assert fake_store.last_top_k == settings.top_k
    assert fake_store.last_query_vec == [0.1, 0.2, 0.3]


async def test_sources_are_composed_into_prompt(settings: Settings, patch_httpx: None) -> None:
    sources = [
        Source(doc_name="規章.pdf", page=12, snippet="請假需提前三日申請", score=0.9),
    ]
    fake_embed = FakeEmbedClient()
    fake_store = FakeStore(sources)

    await rag.answer("請假規定是什麼？", settings, fake_embed, fake_store)

    assert len(_FakeAsyncClient.captured_payloads) == 1
    sent_messages = _FakeAsyncClient.captured_payloads[0]["messages"]
    user_message = next(m["content"] for m in sent_messages if m["role"] == "user")

    assert "規章.pdf" in user_message
    assert "第 12 頁" in user_message
    assert "請假需提前三日申請" in user_message
    assert "請假規定是什麼？" in user_message


async def test_no_sources_still_calls_llm_with_placeholder(settings: Settings, patch_httpx: None) -> None:
    fake_embed = FakeEmbedClient()
    fake_store = FakeStore([])

    result = await rag.answer("查無資料的問題", settings, fake_embed, fake_store)

    assert result.sources == []
    sent_messages = _FakeAsyncClient.captured_payloads[0]["messages"]
    user_message = next(m["content"] for m in sent_messages if m["role"] == "user")
    assert "沒有檢索到任何相關內容" in user_message
