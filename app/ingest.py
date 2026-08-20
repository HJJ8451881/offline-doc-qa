"""PDF 解析與文字切塊。

`extract_pages` 會碰檔案格式解析（PyMuPDF），但不做任何 I/O（吃 bytes、吐資料）；
`chunk_text` 是純函式。兩者都刻意不碰網路或磁碟，方便單元測試。
"""

from __future__ import annotations

import logging

import fitz  # PyMuPDF

from app.models import Page

logger = logging.getLogger(__name__)

# 切塊時優先尋找的斷句字元，依優先順序排列。
_BREAK_CHARS: tuple[str, ...] = ("\n\n", "\n", "。", ". ", "！", "？")


def extract_pages(pdf_bytes: bytes) -> list[Page]:
    """用 PyMuPDF 逐頁抽出文字，保留頁碼（1-based，供引用使用）。

    掃描檔（純圖片、無文字層）的頁面會抽出空字串 —— 這是已知限制，
    沒有做 OCR。呼叫端應過濾掉整份都是空字串的文件。
    """
    pages: list[Page] = []
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for i, page in enumerate(doc):
                text = page.get_text()
                pages.append(Page(page_no=i + 1, text=text))
    except Exception:
        logger.exception("解析 PDF 失敗（可能不是合法的 PDF 或檔案已損毀）")
        raise
    return pages


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """滑動視窗切塊，優先在句號/換行處斷開，避免把句子從中間切碎。

    Args:
        text: 單一頁面（或任意來源）的原始文字。
        size: 每塊的目標字元數上限。
        overlap: 相鄰兩塊重疊的字元數，用來維持跨塊語意連續性。

    Returns:
        不含空白/空字串塊的切塊列表。輸入為空白字串時回傳空列表。
    """
    if size <= 0:
        raise ValueError("size 必須大於 0")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap 必須介於 0 與 size 之間")

    stripped = text.strip()
    if not stripped:
        return []

    chunks: list[str] = []
    start = 0
    text_len = len(stripped)

    while start < text_len:
        end = min(start + size, text_len)

        # 如果還沒到文字結尾，嘗試在斷句字元處收尾，避免切碎句子。
        if end < text_len:
            best_break = -1
            for break_char in _BREAK_CHARS:
                # 在 [start, end] 窗口內，從後往前找最後一次出現的斷句字元。
                idx = stripped.rfind(break_char, start, end)
                if idx != -1:
                    candidate = idx + len(break_char)
                    # 只採用會讓這塊至少有一半目標長度的斷點，避免塊太短碎。
                    if candidate - start >= size // 2:
                        best_break = max(best_break, candidate)
            if best_break != -1:
                end = best_break

        chunk = stripped[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break

        # 下一塊往回重疊 overlap 個字元，但至少要往前推進，避免無窮迴圈。
        next_start = end - overlap
        start = next_start if next_start > start else end

    return chunks
