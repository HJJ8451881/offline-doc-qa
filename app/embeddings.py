"""Ollama embedding client。"""

from __future__ import annotations

import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 60.0


async def embed(texts: list[str], settings: Settings) -> list[list[float]]:
    """呼叫 Ollama `/api/embeddings`，把每段文字轉成向量。

    Ollama 的 `/api/embeddings` 端點一次只吃一段 prompt，所以這裡逐一呼叫；
    對這個作品集規模（單次上傳一份 PDF）已經足夠，若要處理大量文件建議
    改用有 batch 支援的 embedding server。

    Args:
        texts: 要向量化的文字列表。
        settings: 應用程式設定（含 Ollama base URL 與 embedding model 名稱）。

    Returns:
        與 `texts` 等長、順序對應的向量列表。

    Raises:
        RuntimeError: Ollama 呼叫失敗（連線錯誤、逾時、非 2xx 回應）。
    """
    vectors: list[list[float]] = []
    url = f"{settings.ollama_base_url}/api/embeddings"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            for text in texts:
                response = await client.post(
                    url,
                    json={"model": settings.embed_model, "prompt": text},
                )
                response.raise_for_status()
                data = response.json()
                vectors.append(data["embedding"])
    except (httpx.HTTPError, KeyError, ValueError):
        logger.exception("呼叫 Ollama embedding API 失敗 (model=%s)", settings.embed_model)
        raise RuntimeError("embedding 服務呼叫失敗") from None

    return vectors
