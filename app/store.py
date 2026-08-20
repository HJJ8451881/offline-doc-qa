"""pgvector 存取層。所有 SQL 皆為參數化查詢，避免 SQL injection。"""

from __future__ import annotations

import logging
from uuid import UUID

from pgvector.psycopg import register_vector
from psycopg import Connection
from psycopg_pool import ConnectionPool

from app.config import Settings
from app.models import Chunk, DocumentInfo, Source

logger = logging.getLogger(__name__)


def _configure(conn: Connection) -> None:
    """每個新連線都註冊 pgvector 的型別轉換，讓 python list 能直接寫入 vector 欄位。"""
    register_vector(conn)


class Store:
    """包住一個 psycopg 連線池，提供文件與片段的 CRUD / 向量檢索。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool = ConnectionPool(
            conninfo=settings.postgres_dsn,
            min_size=1,
            max_size=5,
            configure=_configure,
            open=True,
        )

    def close(self) -> None:
        """關閉連線池，供應用程式關閉時呼叫。"""
        try:
            self._pool.close()
        except Exception:
            logger.exception("關閉資料庫連線池失敗")

    def insert_document(self, document_id: UUID, filename: str, page_count: int) -> None:
        """新增一筆文件紀錄。"""
        try:
            with self._pool.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO documents (id, filename, page_count)
                    VALUES (%s, %s, %s)
                    """,
                    (document_id, filename, page_count),
                )
        except Exception:
            logger.exception("寫入 documents 失敗 (filename=%s)", filename)
            raise

    def insert_chunks(self, chunks: list[Chunk]) -> None:
        """批次寫入切塊與其向量。"""
        if not chunks:
            return
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(
                        """
                        INSERT INTO chunks (document_id, page_no, content, embedding)
                        VALUES (%s, %s, %s, %s)
                        """,
                        [
                            (c.document_id, c.page_no, c.content, c.embedding)
                            for c in chunks
                        ],
                    )
        except Exception:
            logger.exception("寫入 chunks 失敗 (count=%d)", len(chunks))
            raise

    def search(self, query_vec: list[float], top_k: int) -> list[Source]:
        """用 cosine 距離（`<=>`）檢索最相關的 top_k 個片段。"""
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT d.filename, c.page_no, c.content,
                               1 - (c.embedding <=> %s::vector) AS score
                        FROM chunks c
                        JOIN documents d ON d.id = c.document_id
                        ORDER BY c.embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (query_vec, query_vec, top_k),
                    )
                    rows = cur.fetchall()
        except Exception:
            logger.exception("向量檢索失敗")
            raise

        return [
            Source(doc_name=filename, page=page_no, snippet=content, score=float(score))
            for filename, page_no, content, score in rows
        ]

    def list_documents(self) -> list[DocumentInfo]:
        """列出所有已上傳的文件。"""
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, filename, page_count, created_at
                        FROM documents
                        ORDER BY created_at DESC
                        """
                    )
                    rows = cur.fetchall()
        except Exception:
            logger.exception("讀取 documents 清單失敗")
            raise

        return [
            DocumentInfo(id=doc_id, filename=filename, page_count=page_count, created_at=created_at)
            for doc_id, filename, page_count, created_at in rows
        ]

    def delete_document(self, document_id: UUID) -> None:
        """刪除文件（含其所有 chunks，透過 ON DELETE CASCADE）。"""
        try:
            with self._pool.connection() as conn:
                conn.execute("DELETE FROM documents WHERE id = %s", (document_id,))
        except Exception:
            logger.exception("刪除 document 失敗 (id=%s)", document_id)
            raise
