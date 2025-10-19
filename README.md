# 輔具補助查詢（Streamlit 版，自動載入圖片）

此版本會自動從 `data/images/` 讀取圖片並依「品項」配對。支援兩種命名規則：

## 規則 A：子資料夾（推薦）
- `data/images/<device_id>/01.jpg`
- 例如：
  - `data/images/wheelchair/01.jpg`
  - `data/images/walker/01.jpg`

## 規則 B：檔名前綴
- `data/images/<device_id>-任意名稱.jpg`
- 例如：
  - `data/images/wheelchair-側面.jpg`
  - `data/images/walker-v2.png`

> `<device_id>` 對應 `data/devices.json` 中的 `id` 欄位。

放好圖之後，重新部署即可自動顯示。

## 本機執行
```bash
pip install -r requirements.txt
streamlit run app.py
```