"""測試 app.ingest 的純函式：extract_pages 與 chunk_text。"""

from __future__ import annotations

import fitz
import pytest

from app.ingest import chunk_text, extract_pages


def _make_pdf_bytes(page_texts: list[str]) -> bytes:
    """用 PyMuPDF 建一個記憶體內的最小 PDF，供測試 extract_pages 用。"""
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestExtractPages:
    def test_preserves_page_numbers_and_text(self) -> None:
        pdf_bytes = _make_pdf_bytes(["Hello page one", "Hello page two"])
        pages = extract_pages(pdf_bytes)

        assert len(pages) == 2
        assert pages[0].page_no == 1
        assert pages[1].page_no == 2
        assert "Hello page one" in pages[0].text
        assert "Hello page two" in pages[1].text

    def test_invalid_pdf_bytes_raises(self) -> None:
        with pytest.raises(Exception):
            extract_pages(b"this is not a pdf")


class TestChunkText:
    def test_short_text_produces_single_chunk(self) -> None:
        chunks = chunk_text("這是一段很短的文字。", size=500, overlap=80)
        assert len(chunks) == 1
        assert chunks[0] == "這是一段很短的文字。"

    def test_empty_text_produces_no_chunks(self) -> None:
        assert chunk_text("", size=500, overlap=80) == []
        assert chunk_text("   \n\n  ", size=500, overlap=80) == []

    def test_no_chunk_is_blank(self) -> None:
        text = ("這是一段測試文字。" * 100) + "\n\n" + ("Another sentence. " * 100)
        chunks = chunk_text(text, size=500, overlap=80)
        assert all(chunk.strip() for chunk in chunks)

    def test_respects_size_upper_bound_roughly(self) -> None:
        # 每塊不應該遠超過 size（允許斷句延伸，但不能無限制地長）。
        text = "句子" * 2000
        chunks = chunk_text(text, size=500, overlap=80)
        assert all(len(c) <= 500 + 1 for c in chunks)

    def test_overlap_between_consecutive_chunks(self) -> None:
        # 用沒有斷句符號的長文字，逼迫演算法用固定視窗切塊，方便驗證 overlap。
        text = "".join(str(i % 10) for i in range(2000))
        chunks = chunk_text(text, size=500, overlap=80)
        assert len(chunks) >= 2

        # 第一塊結尾的最後 80 字元，應該等於第二塊開頭的前 80 字元。
        tail_of_first = chunks[0][-80:]
        head_of_second = chunks[1][:80]
        assert tail_of_first == head_of_second

    def test_mixed_chinese_and_english_not_broken_mid_sentence(self) -> None:
        sentence_zh = "這是中文句子，測試混排是否正確。"
        sentence_en = "This is an English sentence for mixed testing. "
        text = (sentence_zh + sentence_en) * 30
        chunks = chunk_text(text, size=500, overlap=80)

        assert len(chunks) > 1
        # 每個切出來的塊，串接起來應該完全還原成原字串的一段連續子字串
        # （允許 overlap 重複，但不應該出現原文中不存在的字元組合）。
        for chunk in chunks:
            assert chunk in text

    def test_invalid_arguments_raise(self) -> None:
        with pytest.raises(ValueError):
            chunk_text("hello", size=0, overlap=0)
        with pytest.raises(ValueError):
            chunk_text("hello", size=10, overlap=10)
        with pytest.raises(ValueError):
            chunk_text("hello", size=10, overlap=-1)
