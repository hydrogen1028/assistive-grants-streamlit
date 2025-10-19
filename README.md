# 輔具補助查詢（Streamlit 可部署版）
功能
- 全品項下拉（含別名）→ 直接進入詳細頁
- 搜尋（支援別名）與體系過濾
- 圖片最佳尺寸挑選（避免失真）
- 列表 / 詳細頁切換
- 字體大小調整（80%~140%）
- 詳細頁：單筆 PDF 下載（ReportLab）、QR Code 彈窗（來源/頁面連結）、小標「資料來源」＋文末完整來源清單

## 本機執行
```bash
pip install -r requirements.txt
streamlit run app.py
```

## GitHub + Streamlit Cloud
1. 推上 GitHub（repo 例如：assistive-grants-streamlit）
2. 到 https://share.streamlit.io 建立新 App：
   - Repository: 你的 repo
   - Branch: main
   - Main file path: app.py
3. Deploy！

## 放圖片
放到 `data/images/<device_id>/`（例：`data/images/wheelchair/1.jpg`）
或放 `data/images/` 根目錄，檔名 `wheelchair-xxx.jpg` 也會自動匹配。