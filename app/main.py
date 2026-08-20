"""FastAPI app：路由、生命週期管理、靜態檔掛載。"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles

from app import embeddings
from app.config import Settings, get_settings
from app.ingest import chunk_text, extract_pages
from app.models import Answer, AskRequest, Chunk, DocumentInfo, HealthStatus
from app.rag import answer as rag_answer
from app.store import Store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

_HEALTH_TIMEOUT_SECONDS = 5.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """啟動時建立 DB 連線池，關閉時釋放 —— 存放在 app.state，不用全域變數。"""
    settings = get_settings()
    app.state.settings = settings
    app.state.store = Store(settings)
    logger.info("Store 連線池已建立")
    try:
        yield
    finally:
        app.state.store.close()
        logger.info("Store 連線池已關閉")


app = FastAPI(title="offline-doc-qa", lifespan=lifespan)


def _get_store(request: Request) -> Store:
    return request.app.state.store


def _get_settings(request: Request) -> Settings:
    return request.app.state.settings


@app.post("/api/documents", response_model=DocumentInfo)
async def upload_document(request: Request, file: UploadFile) -> DocumentInfo:
    """上傳一份 PDF：解析文字 → 切塊 → embedding → 寫入資料庫。"""
    settings = _get_settings(request)
    store = _get_store(request)

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只接受 PDF 檔案")

    pdf_bytes = await file.read()

    try:
        pages = extract_pages(pdf_bytes)
    except Exception as exc:
        logger.exception("PDF 解析失敗 (filename=%s)", file.filename)
        raise HTTPException(status_code=400, detail="PDF 解析失敗，檔案可能已損毀") from exc

    if not any(p.text.strip() for p in pages):
        raise HTTPException(
            status_code=422,
            detail="這份 PDF 沒有可抽取的文字層（可能是掃描檔），目前不支援 OCR",
        )

    document_id = uuid.uuid4()

    # 先切塊、蒐集每塊對應的頁碼，再一次做 embedding，減少呼叫次數。
    page_for_chunk: list[int] = []
    texts: list[str] = []
    for page in pages:
        for chunk in chunk_text(page.text, settings.chunk_size, settings.chunk_overlap):
            page_for_chunk.append(page.page_no)
            texts.append(chunk)

    if not texts:
        raise HTTPException(status_code=422, detail="切塊後沒有任何內容可供索引")

    try:
        vectors = await embeddings.embed(texts, settings)
    except Exception as exc:
        logger.exception("文件 embedding 失敗 (filename=%s)", file.filename)
        raise HTTPException(status_code=502, detail="embedding 服務呼叫失敗") from exc

    chunks = [
        Chunk(document_id=document_id, page_no=page_no, content=text, embedding=vector)
        for page_no, text, vector in zip(page_for_chunk, texts, vectors, strict=True)
    ]

    try:
        store.insert_document(document_id, file.filename, len(pages))
        store.insert_chunks(chunks)
    except Exception as exc:
        logger.exception("寫入資料庫失敗 (filename=%s)", file.filename)
        raise HTTPException(status_code=500, detail="寫入資料庫失敗") from exc

    logger.info("文件已上傳 (filename=%s, pages=%d, chunks=%d)", file.filename, len(pages), len(chunks))
    documents = store.list_documents()
    return next(d for d in documents if d.id == document_id)


@app.get("/api/documents", response_model=list[DocumentInfo])
async def list_documents(request: Request) -> list[DocumentInfo]:
    """列出所有已上傳的文件。"""
    store = _get_store(request)
    try:
        return store.list_documents()
    except Exception as exc:
        logger.exception("讀取文件清單失敗")
        raise HTTPException(status_code=500, detail="讀取文件清單失敗") from exc


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: uuid.UUID, request: Request) -> dict[str, str]:
    """刪除一份文件（連帶刪除其所有切塊）。"""
    store = _get_store(request)
    try:
        store.delete_document(doc_id)
    except Exception as exc:
        logger.exception("刪除文件失敗 (doc_id=%s)", doc_id)
        raise HTTPException(status_code=500, detail="刪除文件失敗") from exc
    return {"status": "deleted"}


@app.post("/api/ask", response_model=Answer)
async def ask(body: AskRequest, request: Request) -> Answer:
    """對已上傳的文件提問，回傳答案與引用來源。"""
    settings = _get_settings(request)
    store = _get_store(request)

    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question 不可為空")

    try:
        return await rag_answer(body.question, settings, embeddings.embed, store)
    except Exception as exc:
        logger.exception("回答問題失敗 (question=%s)", body.question)
        raise HTTPException(status_code=502, detail="回答問題失敗") from exc


@app.get("/api/health", response_model=HealthStatus)
async def health(request: Request) -> HealthStatus:
    """健康檢查，順便回報 Ollama 是否連得上。"""
    settings = _get_settings(request)
    ollama_reachable = False
    try:
        async with httpx.AsyncClient(timeout=_HEALTH_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            ollama_reachable = response.status_code == 200
    except Exception:
        logger.warning("Ollama 健康檢查失敗，視為無法連線", exc_info=True)
        ollama_reachable = False

    return HealthStatus(status="ok", ollama_reachable=ollama_reachable)


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
