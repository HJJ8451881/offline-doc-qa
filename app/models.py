"""Pydantic schema，用於 API 的請求 / 回應與內部資料傳遞。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class Page(BaseModel):
    """PyMuPDF 抽出的單一頁面內容。"""

    page_no: int
    text: str


class Chunk(BaseModel):
    """切塊後、準備寫入資料庫的一個文字片段。"""

    document_id: UUID
    page_no: int
    content: str
    embedding: list[float]


class DocumentInfo(BaseModel):
    """`GET /api/documents` 回傳的文件摘要。"""

    id: UUID
    filename: str
    page_count: int
    created_at: datetime


class AskRequest(BaseModel):
    """`POST /api/ask` 的請求 body。"""

    question: str


class Source(BaseModel):
    """一筆回答所引用的來源片段。"""

    doc_name: str
    page: int
    snippet: str
    score: float


class Answer(BaseModel):
    """`POST /api/ask` 的回應。"""

    answer: str
    sources: list[Source]


class HealthStatus(BaseModel):
    """`GET /api/health` 的回應。"""

    status: str
    ollama_reachable: bool
