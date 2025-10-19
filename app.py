import io, json
from pathlib import Path
import streamlit as st
import pandas as pd
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import qrcode

st.set_page_config(page_title="輔具補助查詢", page_icon="🧰", layout="wide")

DATA_DIR = Path("data")
IMAGES_DIR = DATA_DIR / "images"

# ---- UI state ----
if "ui_theme" not in st.session_state: st.session_state["ui_theme"] = "light"
if "font_scale" not in st.session_state: st.session_state["font_scale"] = 100
if "view" not in st.session_state: st.session_state["view"] = "list"
if "selected_id" not in st.session_state: st.session_state["selected_id"] = None

with st.sidebar:
    st.header("外觀設定")
    st.session_state["ui_theme"] = st.radio("Theme", ["light", "dark"], index=0, horizontal=True)
    st.session_state["font_scale"] = st.slider("字體大小（%）", 80, 140, st.session_state["font_scale"], 5)
    if st.button("清除快取"):
        st.cache_data.clear(); st.rerun()

def inject_css(theme: str, scale: int):
    st.markdown(f"<style>html {{ font-size: {scale}% }}</style>", unsafe_allow_html=True)
    if theme == "dark":
        st.markdown("<style>body,.stApp{background:#0B1220;color:#E5E7EB}</style>", unsafe_allow_html=True)
    else:
        st.markdown("<style>body,.stApp{background:#F8FAFC;color:#0F172A}</style>", unsafe_allow_html=True)
inject_css(st.session_state["ui_theme"], st.session_state["font_scale"])

# ---- data ----
@st.cache_data
def load_devices():
    return json.loads((DATA_DIR / "devices.json").read_text(encoding="utf-8"))

@st.cache_data
def build_photo_index():
    allow = {".jpg",".jpeg",".png",".webp",".gif"}
    idx = {}
    if not IMAGES_DIR.exists(): return idx
    # A: subfolders
    for sub in IMAGES_DIR.iterdir():
        if sub.is_dir():
            dev_id = sub.name
            files = [p for p in sub.rglob("*") if p.is_file() and p.suffix.lower() in allow]
            if files:
                idx.setdefault(dev_id, [])
                idx[dev_id] += [str(p) for p in sorted(files)]
    # B: root prefix
    for p in IMAGES_DIR.glob("*"):
        if p.is_file() and p.suffix.lower() in allow and "-" in p.stem:
            dev_id = p.stem.split("-")[0]
            idx.setdefault(dev_id, []); idx[dev_id].append(str(p))
    # dedupe
    for k,v in idx.items():
        seen=set(); out=[]
        for x in v:
            if x not in seen: out.append(x); seen.add(x)
        idx[k]=out
    return idx

devices = load_devices()
photo_index = build_photo_index()
for d in devices:
    auto = photo_index.get(d["id"], [])
    d.setdefault("photos", [])
    d["photos"] = auto + d["photos"]

# ---- helpers ----
def _is_url(p: str) -> bool: return p.lower().startswith(("http://","https://","data:"))
def pick_best_image(paths, target_width=1200):
    if not paths: return None
    local_files = [p for p in paths if not _is_url(p)]
    if not local_files: return paths[0]
    cand=[]
    for p in local_files:
        try:
            with Image.open(p) as im: w,h = im.size
            diff = abs(w - target_width)
            cand.append((diff, w>=target_width, w, p))
        except Exception: pass
    if not cand: return local_files[0]
    cand.sort(key=lambda x: (x[0], not x[1], -x[2]))
    return cand[0][3]

def format_currency(n):
    return f"NT${n:,.0f}" if isinstance(n,(int,float)) else "—"
def percent(p):
    return f"{round(p*100)}%" if isinstance(p,(int,float)) else "—"
def normalize(s: str) -> str: return (s or "").lower()

def cite_tag(): return "<span style='border:1px solid #e5e7eb;border-radius:9999px;padding:2px 8px;font-size:.8em;margin-left:6px'>資料來源</span>"

# ---- search ----
st.title("輔具補助查詢")
q = st.text_input("搜尋輔具名稱或別名", placeholder="輸入：輪椅、助行器、移位帶、助聽器…")
program = st.radio("體系過濾", ["全部","LTC","PWD"], index=0, horizontal=True)

def match_device(d):
    if program!="全部" and program not in d.get("programs",[]): return False
    if q:
        qn = normalize(q)
        return (qn in normalize(d["name"])) or any(qn in normalize(a) for a in d.get("aliases",[]))
    return True
filtered = [d for d in devices if match_device(d)]

# ---- PDF ----
def build_device_pdf(d: dict) -> bytes:
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A4); W,H=A4; x,y=20*mm, H-20*mm
    def line(text, size=12, leading=14):
        nonlocal y; c.setFont("Helvetica", size)
        for seg in str(text).splitlines(): c.drawString(x,y,seg); y-=leading
    c.setTitle(d.get("name","資料")); line(d.get("name",""), size=18, leading=22); y-=5
    big = pick_best_image(d.get("photos") or [], 1200)
    if big:
        try:
            with Image.open(big) as im: iw,ih=im.size
            maxw=W-40*mm; scale=min(1.0, maxw/iw); neww=iw*scale; newh=ih*scale
            c.drawImage(ImageReader(big), x, y-newh, width=neww, height=newh, preserveAspectRatio=True, mask='auto'); y-=newh+10
        except Exception: pass
    cap=d.get("funding",{}).get("amountCap"); ratio=d.get("funding",{}).get("ratioCap"); life=d.get("lifespanYears")
    line(f"金額上限：{format_currency(cap)}"); line(f"補助比例：{percent(ratio)}"); line(f"使用年限：{life} 年" if life else "使用年限：—"); y-=5
    line("補助資格：", size=14, leading=18)
    for e in d.get("eligibility",[]): line(f"• {e}", size=11)
    y-=5; line("參考資料來源：", size=14, leading=18)
    srcs = list(d.get("sources",[]) or [])
    if not srcs and d.get("citySpecifics"):
        for cty in d["citySpecifics"]:
            if cty.get("sourceUrl"): srcs.append({"label":f"{cty.get('city','—')}公告","url":cty["sourceUrl"],"note":"地方政府公告"})
    if srcs:
        for i,s in enumerate(srcs,1): line(f"{i}. {s.get('label',f'來源 {i}')}  {s.get('url','')}", size=10, leading=12)
    else:
        line("（尚未設定來源）", size=10)
    c.showPage(); c.save(); return buf.getvalue()

# ---- QR ----
def show_qr_dialog(d: dict):
    url=""
    for c in d.get("citySpecifics",[]) or []:
        if c.get("sourceUrl"): url=c["sourceUrl"]; break
    if not url:
        for s in d.get("sources",[]) or []:
            if s.get("url"): url=s["url"]; break
    if not url: url=f"Assistive Device: {d.get('name','')}"
    img = qrcode.make(url); bio=io.BytesIO(); img.save(bio, format="PNG"); qr=bio.getvalue()
    if hasattr(st,"dialog"):
        @st.dialog("掃描 QR 以開啟來源/此筆資料連結")
        def _dlg(): st.image(qr, caption=url, use_column_width=True)
        _dlg()
    else:
        with st.expander("QR Code"): st.image(qr, caption=url, use_column_width=True)

# ---- views ----
def render_list_view():
    st.caption(f"找到 {len(filtered)} 項")
    for d in filtered:
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 3, 1])

            with c1:
                img = pick_best_image(d.get("photos") or [], target_width=800)
                if img:
                    st.image(img, use_column_width=True)
                else:
                    st.caption("（無圖片）")

            with c2:
                st.subheader(d["name"])
                aliases = d.get("aliases", [])
                if aliases:
                    chips = " ".join([
                        f"<span style='border:1px solid #e5e7eb;border-radius:9999px;padding:2px 8px;font-size:.8em;margin-right:6px'>{a}</span>"
                        for a in aliases
                    ])
                    st.markdown(chips, unsafe_allow_html=True)
                st.caption(f"{d.get('category','—')}｜體系：{' / '.join(d.get('programs', []))}")

            with c3:
                if st.button("查看詳情", key=f"view-{d['id']}"):
                    st.session_state["selected_id"] = d["id"]
                    st.session_state["view"] = "detail"
                    st.rerun()

def render_detail_view():
    d = next((x for x in devices if x["id"]==st.session_state["selected_id"]), None)
    if not d:
        st.warning("找不到該項目"); 
        if st.button("返回列表"): st.session_state["view"]="list"; st.rerun()
        return
    t1,t2,t3 = st.columns([1,1,1])
    if t1.button("← 返回列表"): st.session_state["view"]="list"; st.rerun()
    pdf = build_device_pdf(d); t2.download_button("下載此筆 PDF", data=pdf, file_name=f"{d['id']}.pdf", mime="application/pdf")
    if t3.button("顯示 QR Code"): show_qr_dialog(d)

    st.header(d["name"])
    big = pick_best_image(d.get("photos") or [], 1200)
    if big: st.image(big, use_column_width=True)
    cap=d.get("funding",{}).get("amountCap"); ratio=d.get("funding",{}).get("ratioCap"); life=d.get("lifespanYears")
    c1,c2,c3 = st.columns(3)
    c1.metric("金額上限", format_currency(cap)); c2.metric("補助比例", percent(ratio)); c3.metric("使用年限", f"{life} 年" if life else "—")

    st.markdown("### 補助資格（通用） "+cite_tag(), unsafe_allow_html=True)
    for e in d.get("eligibility", []): st.write(f"- {e}")

    st.markdown("### 使用年限與汰換規則 "+cite_tag(), unsafe_allow_html=True)
    if d.get('lifespanYears'): st.write(f"- 建議使用年限：**{d.get('lifespanYears')} 年**")
    else: st.write("- 建議使用年限：**依公告**")
    if d.get('renewalIntervalYears'): st.write(f"- 最短汰換間隔：**{d.get('renewalIntervalYears')} 年**")

    st.markdown("---"); st.subheader("參考資料來源")
    sources = list(d.get("sources",[]) or [])
    if not sources and d.get("citySpecifics"):
        for c in d["citySpecifics"]:
            if c.get("sourceUrl"): sources.append({"label":f"{c.get('city','—')}公告","url":c["sourceUrl"],"note":"地方政府公告"})
    if sources:
        for i,s in enumerate(sources,1):
            label=s.get("label",f"來源 {i}"); url=s.get("url",""); note=s.get("note","")
            st.markdown(f"{i}. [{label}]({url}) — {note}" if url else f"{i}. {label} — {note}")
    else:
        st.caption("（此筆尚未設定來源，請後台補充）")

if st.session_state["view"]=="list": render_list_view()
else: render_detail_view()
