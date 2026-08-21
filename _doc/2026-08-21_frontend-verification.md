# 前端實機驗證與 demo 截圖

日期：2026-08-21

## 為什麼

初版（`2026-08-20_initial-implementation.md`）留了兩個未驗證項：前端沒有經過瀏覽器實際操作，`docs/screenshot.png` 也因此缺席。README 誠實標了出來，但那是這個 repo 唯一還掛著的洞，而且是面試官會直接看到的位置。

本次用 headless Chromium 補完——不需要 GUI 環境。

## 做了什麼

裝 `playwright` 與 chromium headless shell 到 `business` env，寫一支腳本走完整前端流程：開首頁 → 選檔 → 按「上傳 PDF」→ 等索引完成 → 填問題 → 送出 → 等來源出現 → 全頁截圖。

**刻意走 UI 而非直接打 API**，因為這一輪要驗的就是前端本身，後端在上一輪已經驗過。

截圖存成 `docs/screenshot.png`，README 的「Demo 截圖」區塊改為實際嵌入，並移除「已知限制」中的截圖缺席項與「前端未經視覺驗收」那句。

### 第一次跑失敗：等待條件寫錯

腳本用 `#doc-list li` 當作「上傳完成」的判斷依據，但**空狀態「尚未上傳任何文件」本身也是一個 `<li>`**，所以選擇器立刻就命中了，腳本在索引還在跑的時候就送出提問。

結果是 `/api/ask` 回 200 但 `sources` 為空陣列，前端因此不渲染 `.meta`，腳本等到逾時。

一度誤判成前端沒送出請求——實際看 `docker compose logs` 才發現 `POST /api/ask` 確實是 200。**這是我的測試腳本的 bug，不是應用程式的 bug。** 修法是改等實際檔名出現（`#doc-list li:has-text('udhr.pdf')`）。

值得記下來的是：`sources` 為空時前端不會顯示任何提示，畫面看起來就像沒反應。這不影響正常使用（有文件就會有來源），但列在下方待辦。

## 驗證

- **已驗證**：完整前端流程以 headless Chromium 實際操作成功。腳本輸出顯示文件清單為 `'udhr.pdf (8 頁)'`，回答為 "Article 6 ... states: Everyone has the right to recognition everywhere as a person before the law."，五筆來源中第二筆為 `udhr.pdf · 第 3 頁 · score 0.709`，內容確實是 Article 6 原文。
- **已驗證**：`docs/screenshot.png` 是該次操作的產物，非手工合成。
- **已驗證**：`DELETE /api/documents/{id}` 回 200 且清單歸零（測試前清資料時順帶確認）。
- **已驗證**：`/api/health` 回報 `ollama_reachable: true`，前端狀態列顯示「Ollama: 連線正常」。
- **未驗證**：只測過這一份 8 頁的英文 PDF。中文 PDF、掃描檔、超大檔案的前端行為都沒測過。
- **未驗證**：只在 1440×900 的 viewport 截過圖，沒有測過窄螢幕或行動裝置版面。
- **未驗證**：沒有測過錯誤路徑的前端呈現（Ollama 斷線、上傳非 PDF、索引失敗）。

## 待辦 / 已放棄

- **待辦**：檢索命中零筆時前端沒有任何提示，畫面看起來像沒反應。應該顯示「找不到相關內容」之類的訊息。
- **待辦**：錯誤路徑的前端呈現未測。
- **已放棄**：不做 asciinema 終端機錄影。它錄不到瀏覽器畫面，解決不了這個缺口；而 A/B 實驗的證據力已經由 `claude-code-standards` 那邊的原始 JSON（含 session_id 與成本，可對照帳單）承擔，`.cast` 檔反而更容易偽造。
