"""檢索 + 生成（RAG）。"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from app.config import Settings
from app.models import Answer, Source

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 60.0

_SYSTEM_PROMPT = (
    "你是一個文件問答助理。只能根據下面提供的「參考內容」回答問題，"
    "不可使用參考內容以外的知識。如果參考內容不足以回答，"
    "請直接說「根據現有文件，我不知道答案」，不要編造。"
    "回答時請使用與問題相同的語言。"
)


class EmbedClient(Protocol):
    """`embed()` 的介面，方便測試時用 fake 取代真正的 Ollama 呼叫。"""

    async def __call__(self, texts: list[str], settings: Settings) -> list[list[float]]: ...


class ChunkStore(Protocol):
    """`store.search()` 的介面，方便測試時用 fake store。"""

    def search(self, query_vec: list[float], top_k: int) -> list[Source]: ...


def _build_prompt(question: str, sources: list[Source]) -> str:
    """把檢索到的片段組成給 LLM 的參考內容區塊。"""
    if not sources:
        context = "（沒有檢索到任何相關內容）"
    else:
        context = "\n\n".join(
            f"[來源 {i + 1}：{s.doc_name} 第 {s.page} 頁]\n{s.snippet}"
            for i, s in enumerate(sources)
        )
    return f"參考內容：\n{context}\n\n問題：{question}"


async def answer(
    question: str,
    settings: Settings,
    embed_client: EmbedClient,
    store: ChunkStore,
) -> Answer:
    """embed 問題 → 檢索 top_k → 組 prompt → 呼叫 Ollama chat → 回傳答案與來源。

    Args:
        question: 使用者問題。
        settings: 應用程式設定。
        embed_client: 產生 embedding 的呼叫（生產環境傳 `embeddings.embed`）。
        store: 提供向量檢索的物件（生產環境傳 `store.Store` 實例）。
    """
    try:
        vectors = await embed_client([question], settings)
    except Exception:
        logger.exception("問題 embedding 失敗")
        raise

    query_vec = vectors[0]

    try:
        sources = store.search(query_vec, settings.top_k)
    except Exception:
        logger.exception("向量檢索失敗")
        raise

    prompt = _build_prompt(question, sources)
    url = f"{settings.ollama_base_url}/api/chat"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                json={
                    "model": settings.chat_model,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            answer_text = data["message"]["content"]
    except (httpx.HTTPError, KeyError, ValueError):
        logger.exception("呼叫 Ollama chat API 失敗 (model=%s)", settings.chat_model)
        raise RuntimeError("生成回答失敗") from None

    return Answer(answer=answer_text, sources=sources)
