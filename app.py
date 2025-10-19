import json
from pathlib import Path
import streamlit as st
import pandas as pd
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import qrcode

from PIL import Image
from pathlib import Path

def _is_url(p: str) -> bool:
    return p.lower().startswith(("http://", "https://", "data:"))

def pick_best_image(paths, target_width=1200):
    """
    從多張圖片中挑最接近 target_width 的「本地檔」；若都只有 URL 就用第一張。
    這樣不會硬把小圖拉到很大（避免糊掉），也不會拿超大圖造成浪費。
    """
    if not paths:
        return None
    local_files = [p for p in paths if not _is_url(p)]
    if not local_files:
        return paths[0]

    candidates = []
    for p in local_files:
        try:
            with Image.open(p) as im:
                w, h = im.size
            # 以「寬度最接近」作為挑選依據，並偏好略大於 target 的圖
            diff = abs(w - target_width)
            candidates.append((diff, w >= target_width, w, p))
        except Exception:
            continue

    if not candidates:
        return local_files[0]

    # 排序：差距小 → 寬度≥target 優先 → 較寬者優先
    candidates.sort(key=lambda x: (x[0], not x[1], -x[2]))
    return candidates[0][3]


st.set_page_config(page_title="輔具補助查詢", page_icon="🧰", layout="wide")

DATA_DIR = Path("data")
IMAGES_DIR = DATA_DIR / "images"

@st.cache_data
def load_devices():
    return json.loads((DATA_DIR / "devices.json").read_text(encoding="utf-8"))

def format_currency(n):
    if isinstance(n, (int, float)):
        return f"NT${n:,.0f}"
    return "—"

def percent(p):
    if isinstance(p, (int, float)):
        return f"{round(p*100)}%"
    return "—"

def normalize(s: str) -> str:
    return (s or "").lower()

def resolve_photo(p: str) -> str:
    p = p or ""
    if p.lower().startswith(("http://", "https://", "data:")):
        return p
    return str(Path(p))

@st.cache_data
def build_photo_index():
    # Scan data/images with two rules:
    # A) data/images/<device_id>/*.(jpg|jpeg|png|webp|gif)
    # B) data/images/<device_id>-*.(jpg|jpeg|png|webp|gif)
    idx = {}
    if not IMAGES_DIR.exists():
        return idx

    exts = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.gif")
    # Rule A: subfolders
    for sub in IMAGES_DIR.iterdir():
        if sub.is_dir():
            dev_id = sub.name
            files = []
            for ext in exts:
                files += list(sub.glob(ext))
            if files:
                idx.setdefault(dev_id, [])
                idx[dev_id] += [str(p.relative_to(Path("."))) for p in sorted(files)]

    # Rule B: filename prefix
    for ext in exts:
        for p in IMAGES_DIR.glob(ext):
            name = p.stem
            if "-" in name:
                dev_id = name.split("-")[0]
                idx.setdefault(dev_id, [])
                idx[dev_id].append(str(p.relative_to(Path("."))))

    # dedupe & sort
    for k, v in idx.items():
        uniq = []
        seen = set()
        for x in v:
            if x not in seen:
                uniq.append(x); seen.add(x)
        idx[k] = sorted(uniq)
    return idx

devices = load_devices()
photo_index = build_photo_index()

# 合併自動圖片到每個品項
for d in devices:
    auto_photos = photo_index.get(d["id"], [])
    d.setdefault("photos", [])
    d["photos"] = auto_photos + d["photos"]  # 讓本地自動圖優先顯示

# 上方工具列：清快取 + 偵錯
with st.sidebar:
    st.subheader("工具")
    if st.button("清除快取並重新整理"):
        st.cache_data.clear()
        st.rerun()

    with st.expander("偵錯（圖片配對）"):
        st.write("以下顯示每個 id 配到的圖片清單：")
        for d in devices:
            st.write(f"**{d['id']}** / {d['name']}")
            pics = d.get("photos", [])
            if pics:
                for p in pics:
                    st.write("-", p)
            else:
                st.warning("沒有配到圖片（請檢查 data/images/ 與 id 是否一致）")

# Search options
name_to_id = {}
options = []
for d in devices:
    options.append(d["name"])
    name_to_id[d["name"]] = d["id"]
    for a in d.get("aliases", []):
        label = f"{a}（{d['name']}）"
        options.append(label)
        name_to_id[label] = d["id"]

st.title("輔具補助查詢（Streamlit 版 Demo）")
st.caption("輸入或選擇輔具名稱 → 顯示照片、補助資格、上限/比例、使用年限與各縣市差異。圖片會自動從 data/images/ 匹配載入。")

col_search, col_filters = st.columns([3, 1])
with col_search:
    q = st.text_input("關鍵字（例：輪椅、助行器、移位帶、助聽器）", placeholder="輸入關鍵字…")
    picked = st.selectbox("或從清單中選擇", options=["— 選擇項目 —"] + options, index=0)

with col_filters:
    program = st.radio("體系過濾", options=["全部", "LTC", "PWD"], index=0, horizontal=True)

def match_device(d):
    if program != "全部" and program not in d.get("programs", []):
        return False
    if q:
        qn = normalize(q)
        if qn in normalize(d["name"]) or any(qn in normalize(a) for a in d.get("aliases", [])):
            return True
        return False
    if picked and picked != "— 選擇項目 —":
        return name_to_id.get(picked) == d["id"]
    return True

filtered = [d for d in devices if match_device(d)]

st.write(f"共找到 **{len(filtered)}** 項結果")
left, right = st.columns([1.2, 2.0])

with left:
    for d in filtered:
        with st.container(border=True):
            photos = d.get("photos") or []
            if photos:
                img = pick_best_image(d.get("photos") or [], target_width=800)  # 列表用 800
                big = pick_best_image(d.get("photos") or [], target_width=1200)
                if img:
                    st.image(img, use_column_width=True)               
                if big:
                    st.image(big, use_column_width=True)

            st.subheader(d["name"])
            st.caption(f"{d['category']}｜適用體系：{' / '.join(d.get('programs', []))}")
            cap = d.get("funding", {}).get("amountCap")
            ratio = d.get("funding", {}).get("ratioCap")
            c1, c2, c3 = st.columns(3)
            c1.metric("金額上限", format_currency(cap))
            c2.metric("補助比例", percent(ratio))
            life = d.get("lifespanYears")
            c3.metric("使用年限", f"{life} 年" if life else "—")
            if st.button("查看詳情", key=f"btn-{d['id']}"):
                st.session_state["selected_id"] = d["id"]

selected = None
if "selected_id" in st.session_state:
    selected = next((x for x in devices if x["id"] == st.session_state["selected_id"]), None)
elif filtered:
    selected = filtered[0]

with right:
    if not selected:
        st.info("從左側選擇一項或輸入關鍵字開始查詢。")
    else:
        d = selected
        st.header(d["name"])

        photos = d.get("photos") or []
        if photos:
            key = f"photo_idx_{d['id']}"
            if key not in st.session_state:
                st.session_state[key] = 0
            big = photos[min(st.session_state[key], len(photos)-1)]
            st.image(resolve_photo(big), use_column_width=True)

            if len(photos) > 1:
                st.caption("其他圖片")
                cols = st.columns(min(len(photos), 5))
                for i, p in enumerate(photos[:5]):
                    with cols[i]:
                        if st.button(" ", key=f"thumb-{d['id']}-{i}"):
                            st.session_state[key] = i
                        st.image(resolve_photo(p), use_column_width=True)

        cap = d.get("funding", {}).get("amountCap")
        ratio = d.get("funding", {}).get("ratioCap")
        c1, c2, c3 = st.columns(3)
        c1.metric("金額上限", format_currency(cap))
        c2.metric("補助比例", percent(ratio))
        life = d.get("lifespanYears")
        c3.metric("使用年限", f"{life} 年" if life else "—")

        if d.get("funding", {}).get("notes"):
            st.markdown("**補助備註**")
            for n in d["funding"]["notes"]:
                st.write(f"- {n}")

        st.markdown("### 補助資格（通用）")
        for e in d.get("eligibility", []):
            st.write(f"- {e}")

        st.markdown("### 使用年限與汰換規則")
        if d.get('lifespanYears'):
            st.write(f"- 建議使用年限：**{d.get('lifespanYears')} 年**")
        else:
            st.write(f"- 建議使用年限：**依公告**")
        if d.get('renewalIntervalYears'):
            st.write(f"- 最短汰換間隔：**{d.get('renewalIntervalYears')} 年**")
        else:
            st.write(f"- 最短汰換間隔：**依公告**")
        if d.get("usageNotes"):
            for n in d["usageNotes"]:
                st.write(f"- {n}")

        st.markdown("### 各縣市差異（Beta）")
        rows = []
        for c in d.get("citySpecifics", []) or []:
            rows.append({
                "縣市": c.get("city", "—"),
                "體系": c.get("program", "—"),
                "金額上限": format_currency((c.get("funding") or {}).get("amountCap")),
                "比例": percent((c.get("funding") or {}).get("ratioCap")),
                "額外條件": "、".join(c.get("extraEligibility", []) or []) or "—",
                "效期": c.get("effectiveTo", "—"),
                "來源": c.get("sourceUrl", "—")
            })
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("尚無差異資料。")

        if d.get("legalRefs"):
            st.markdown("### 法規/要點（參考）")
            for r in d["legalRefs"]:
                st.write(f"- {r}")

        st.caption(f"資料更新：{d.get('lastUpdated', '—')}")
if "view" not in st.session_state:
    st.session_state["view"] = "list"     # "list" 或 "detail"
if "selected_id" not in st.session_state:
    st.session_state["selected_id"] = None
def render_list_view(devices):
    st.caption(f"找到 {len(devices)} 項")
    for d in devices:
        with st.container(border=True):
            cols = st.columns([1, 3, 1])
            # 左：縮圖
            img = pick_best_image(d.get("photos") or [], target_width=800)
            with cols[0]:
                if img:
                    st.image(img, use_column_width=True)
                else:
                    st.caption("（無圖片）")
            # 中：基本資訊
            with cols[1]:
                st.subheader(d["name"])
                aliases = d.get("aliases", [])
                if aliases:
                    chips = " ".join([f"<span style='border:1px solid #e5e7eb;border-radius:9999px;padding:2px 8px;font-size:.8em;margin-right:6px'>{a}</span>" for a in aliases])
                    st.markdown(chips, unsafe_allow_html=True)
                st.caption(f"{d.get('category','—')}｜體系：{' / '.join(d.get('programs', []))}")
            # 右：查看詳情
            with cols[2]:
                if st.button("查看詳情", key=f"view-{d['id']}"):
                    st.session_state["selected_id"] = d["id"]
                    st.session_state["view"] = "detail"
                    st.rerun()

def render_detail_view(all_devices):
    d = next((x for x in all_devices if x["id"] == st.session_state["selected_id"]), None)
    if not d:
        st.warning("找不到該項目")
        if st.button("返回列表"): 
            st.session_state["view"] = "list"; st.rerun()
        return

    top = st.columns([1,1,1,3])
    if top[0].button("← 返回列表"):
        st.session_state["view"] = "list"; st.rerun()
    # 下載 PDF（第 3 點下面有）與 QR Code（第 5 點下面有）會放在 top[1]/top[2]

    st.header(d["name"])
    big = pick_best_image(d.get("photos") or [], target_width=1200)
    if big:
        st.image(big, use_column_width=True)

    # ……(詳細內容顯示放在第 3 點)
if st.session_state["view"] == "list":
    render_list_view(filtered)  # filtered 是你搜尋後的資料
else:
    render_detail_view(devices)

def cite_tag():
    return "<span style='border:1px solid #e5e7eb;border-radius:9999px;padding:2px 8px;font-size:.8em;margin-left:6px'>資料來源</span>"
st.markdown("### 補助資格（通用） " + cite_tag(), unsafe_allow_html=True)
for e in d.get("eligibility", []):
    st.write(f"- {e}")

st.markdown("### 使用年限與汰換規則 " + cite_tag(), unsafe_allow_html=True)
# 顯示 lifespan / renewalInterval / usageNotes
st.markdown("### 地方差異（上限/比例/條件） " + cite_tag(), unsafe_allow_html=True)
st.markdown("---")
st.subheader("參考資料來源")
sources = d.get("sources", [])
if not sources and d.get("citySpecifics"):
    derived = []
    for c in d["citySpecifics"]:
        if c.get("sourceUrl"):
            derived.append({"label": f"{c.get('city','—')}公告", "url": c["sourceUrl"], "note": "地方政府公告"})
    sources = derived

if sources:
    for i, s in enumerate(sources, 1):
        label = s.get("label", f"來源 {i}")
        url   = s.get("url", "")
        note  = s.get("note", "")
        if url:
            st.markdown(f"{i}. [{label}]({url}) — {note}")
        else:
            st.markdown(f"{i}. {label} — {note}")
else:
    st.caption("（此筆尚未設定來源，請後台補充）")

if "ui_theme" not in st.session_state:
    st.session_state["ui_theme"] = "light"
if "font_scale" not in st.session_state:
    st.session_state["font_scale"] = 100

with st.sidebar:
    st.header("外觀設定")
    st.session_state["ui_theme"] = st.radio("Theme", ["light", "dark"], index=0, horizontal=True)
    st.session_state["font_scale"] = st.slider("字體大小（%）", 80, 140, st.session_state["font_scale"], 5)
def inject_css(theme: str, scale: int):
    st.markdown(f"""
    <style>
      html {{ font-size: {scale}% }}
    </style>
    """, unsafe_allow_html=True)

    if theme == "dark":
        st.markdown("""
        <style>
          body, .stApp { background: #0B1220; color: #E5E7EB; }
          div[role="group"] > div { background: #0F172A; }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
          body, .stApp { background: #F8FAFC; color: #0F172A; }
          div[role="group"] > div { background: #FFFFFF; }
        </style>
        """, unsafe_allow_html=True)

inject_css(st.session_state["ui_theme"], st.session_state["font_scale"])

def build_device_pdf(d: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    x, y = 20*mm, H - 20*mm

    def line(text, size=12, leading=14):
        nonlocal y
        c.setFont("Helvetica", size)
        for seg in str(text).splitlines():
            c.drawString(x, y, seg)
            y -= leading

    # 標題
    c.setTitle(d.get("name", "輔具資料"))
    line(d.get("name",""), size=18, leading=22)
    y -= 5

    # 插入代表圖
    big = pick_best_image(d.get("photos") or [], target_width=1200)
    if big:
        try:
            with Image.open(big) as im:
                iw, ih = im.size
            maxw = W - 40*mm
            scale = min(1.0, maxw / iw)
            neww = iw * scale
            newh = ih * scale
            c.drawImage(ImageReader(big), x, y - newh, width=neww, height=newh, preserveAspectRatio=True, mask='auto')
            y -= newh + 10
        except Exception:
            pass

    cap = d.get("funding", {}).get("amountCap")
    ratio = d.get("funding", {}).get("ratioCap")
    life = d.get("lifespanYears")
    line(f"金額上限：{cap if cap is not None else '—'}")
    line(f"補助比例：{f'{round(ratio*100)}%' if isinstance(ratio,(int,float)) else '—'}")
    line(f"使用年限：{life} 年" if life else "使用年限：—")
    y -= 5

    line("補助資格：", size=14, leading=18)
    for e in d.get("eligibility", []) or []:
        line(f"• {e}", size=11)

    y -= 5
    line("參考資料來源：", size=14, leading=18)
    sources = d.get("sources", [])
    if not sources and d.get("citySpecifics"):
        for cty in d["citySpecifics"]:
            if cty.get("sourceUrl"):
                sources.append({"label": f"{cty.get('city','—')}公告", "url": cty["sourceUrl"], "note": "地方政府公告"})
    if sources:
        for i, s in enumerate(sources, 1):
            label = s.get("label", f"來源 {i}")
            url   = s.get("url", "")
            note  = s.get("note", "")
            line(f"{i}. {label}  {url}  {note}", size=10, leading=12)
    else:
        line("（尚未設定來源）", size=10)

    c.showPage(); c.save()
    return buf.getvalue()
# top = st.columns([...]) 裡
pdf_bytes = build_device_pdf(d)
top[1].download_button("下載此筆 PDF", data=pdf_bytes, file_name=f"{d['id']}.pdf", mime="application/pdf")

def show_qr_dialog(d: dict):
    # 選一個有意義的連結
    url = ""
    for c in d.get("citySpecifics", []) or []:
        if c.get("sourceUrl"):
            url = c["sourceUrl"]; break
    if not url:
        for s in d.get("sources", []) or []:
            if s.get("url"):
                url = s["url"]; break
    if not url:
        url = f"Assistive Device: {d.get('name','')}"

    img = qrcode.make(url)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    qr_bytes = bio.getvalue()

    # Streamlit 新版有 st.dialog（若沒有就用 expander 當後備）
    if hasattr(st, "dialog"):
        @st.dialog("掃描 QR 以開啟來源/此筆資料連結")
        def _dlg():
            st.image(qr_bytes, caption=url, use_column_width=True)
            st.caption("可以改為指向你網站上的單筆資料永久連結")
        _dlg()
    else:
        with st.expander("QR Code"):
            st.image(qr_bytes, caption=url, use_column_width=True)

