
# 輔具補助查詢（Streamlit 版）

可直接部署到 **Streamlit Community Cloud**。

## 本機執行
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 部署到 Streamlit Community Cloud
1. 將此資料夾推上 GitHub（例如 repo 名稱：`assistive-grants-streamlit`）。
2. 前往 https://streamlit.io → Sign In → **New app**。
3. 選擇你的 repo、分支（main）、App file 選 `app.py`，Python 版本選 3.10 或 3.11。
4. Deploy 後會取得公開網址。

> 若要接真實 API，可在 `app.py` 以 `requests.get(...)` 取得資料，或將每日爬蟲輸出的 JSON 覆蓋 `data/devices.json`。
