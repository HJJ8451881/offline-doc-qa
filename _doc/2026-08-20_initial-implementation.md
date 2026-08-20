# 初版實作與端到端驗證

日期：2026-08-20

## 為什麼

依 `_doc/v1.0.md` 從零建立整個專案：PDF 上傳 → PyMuPDF 解析 → 切塊 → Ollama embedding → pgvector 檢索 → 本地 LLM 生成附頁碼引用的答案，全程離線。

## 做了什麼

照規格建出全部模組（`app/` 下 config / models / ingest / embeddings / store / rag / main / static、`db/init.sql`、`tests/`、Docker Compose 一組）。規格沒列但實際需要的兩個檔案另外補上：`pytest.ini` 與根層 `conftest.py`，讓 `tests/` 能正確 import `app` 套件。

### 修掉的 bug：pgvector 的 list 參數在 SELECT 情境不會自動轉型

第一次呼叫 `/api/ask` 時失敗：

```
psycopg.errors.UndefinedFunction:
operator does not exist: vector <=> double precision[]
```

診斷：`pgvector.psycopg.register_vector()` 只替 `numpy.ndarray` 與 `Vector` 註冊 dumper。傳 plain Python list 時：

- **INSERT 可以**——PostgreSQL 對 assignment（寫入已知型別的欄位）會做隱式 cast，所以 `insert_chunks()` 一路正常。
- **SELECT 不行**——`<=>` operator 的參數解析不走 assignment cast，`double precision[]` 找不到對應的 operator 就直接炸。

這個不對稱是踩到坑的原因：**索引建得起來、資料寫得進去，看起來一切正常，直到第一次查詢才爆**。

修法：`store.py` 的 `search()` 在 SQL 裡對參數加顯式 `::vector` cast（`c.embedding <=> %s::vector`），不改 embedding 的資料型別。

### 開發環境的 port 衝突

`db` 服務原本對外映射 5432，但開發機上已有其他 PostgreSQL 佔用該埠，`docker compose up` 直接失敗。移除對外映射即可——app 容器走 docker network 內部連線，完全不受影響。已在 README「已知限制」記錄，並說明想從 host 用 `psql` 除錯時怎麼加回來。

### 用詞修正

`頁碼焼進`（日文漢字）→ `燒進`、`一起载入`（簡體）→ `載入`。

## 驗證

- **已驗證**：`./test.sh` → 13 passed（`test_ingest.py` 9 個切塊／解析測試、`test_rag.py` 4 個以 fake embedding client + fake store 驗證 prompt 組裝與來源回傳，不打真的 Ollama）。
- **已驗證**：`docker compose up` 端到端。上傳公開 PDF（聯合國《世界人權宣言》英文版，8 頁，自 ohchr.org 下載），提問 "What does Article 6 of the Universal Declaration of Human Rights say?"，答案內容正確且引用標示第 3 頁——事先用 PyMuPDF 讀過原文確認 Article 6 確實在第 3 頁，不是採信模型自述。
- **已驗證**：`GET /api/documents`、`DELETE /api/documents/{doc_id}`、`GET /api/health`（`ollama_reachable: true`）、靜態首頁 `/` 皆以 `curl` 確認回傳預期結果。測完 `docker compose down -v`，容器與 volume 已清乾淨。
- **已驗證**：模型改用 `nomic-embed-text`（274MB）與 `qwen2.5:7b`（4.7GB），與 `.env.example` 的預設值一致，不是拿機器上剛好有的其他模型頂替。
- **未驗證**：**前端畫面沒有經過瀏覽器實際點擊的視覺驗收**——開發環境無 GUI。只驗證了它呼叫的 API 行為正確，版面、互動、錯誤提示的呈現都沒有人看過。
- **未驗證**：`docs/screenshot.png` 因上述原因沒有實體截圖，README 只留了位置並註明原因。

## 待辦 / 已放棄

- **待辦**：在有 GUI 的環境實跑一次，人工點過前端，補上 `docs/screenshot.png`，並清掉上面兩個未驗證項。
- **待辦**：尚未 commit。
- **已放棄**：不整合 OCR。掃描檔目前直接被 API 擋下（`422`）而非靜默產生空索引——寧可明確失敗。列在 README「後續可擴充」。
- **已放棄**：不做 embedding batch 化。Ollama 的 `/api/embeddings` 本身不支援單次多筆輸入，改了也沒有效果；等上游支援或換 embedding server 再說。
