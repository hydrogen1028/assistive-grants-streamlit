
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

# ---------- UI State ----------
if "ui_theme" not in st.session_state: st.session_state["ui_theme"] = "light"
if "font_scale" not in st.session_state: st.session_state["font_scale"] = 100
if "view" not in st.session_state: st.session_state["view"] = "list"
if "selected_id" not in st.session_state: st.session_state["selected_id"] = None

with st.sidebar:
    st.header("外觀設定")
    st.session_state["font_scale"] = st.slider("字體大小（%）", 80, 140, st.session_state["font_scale"], 5)
    st.session_state["ui_theme"] = st.radio("Theme", ["light", "dark"], index=0, horizontal=True)
    if st.button("清除快取"): st.cache_data.clear(); st.rerun()

def inject_css(theme: str, scale: int):
    st.markdown(f"<style>html {{ font-size: {scale}% }}</style>", unsafe_allow_html=True)
    if theme == "dark":
        st.markdown("<style>body,.stApp{background:#0B1220;color:#E5E7EB}</style>", unsafe_allow_html=True)
    else:
        st.markdown("<style>body,.stApp{background:#F8FAFC;color:#0F172A}</style>", unsafe_allow_html=True)
    st.markdown(
        """
        <style>
          .chip {
            display:inline-block;
            border:1px solid #e5e7eb;
            border-radius:9999px;
            padding:2px 8px;
            margin-left:6px;
            font-size:.8em;
          }
        </style>
        """, unsafe_allow_html=True
    )

inject_css(st.session_state["ui_theme"], st.session_state["font_scale"])

# ---------- Data ----------
@st.cache_data
def load_devices():
    return json.loads((DATA_DIR / "devices.json").read_text(encoding="utf-8"))

@st.cache_data
def build_photo_index():
    allow = {".jpg",".jpeg",".png",".webp",".gif"}
    idx = {}
    if not IMAGES_DIR.exists(): return idx
    for sub in IMAGES_DIR.iterdir():
        if sub.is_dir():
            dev=sub.name
            files=[p for p in sub.rglob("*") if p.is_file() and p.suffix.lower() in allow]
            if files: idx.setdefault(dev, []); idx[dev]+=[str(p) for p in sorted(files)]
    for p in IMAGES_DIR.glob("*"):
        if p.is_file() and p.suffix.lower() in allow and "-" in p.stem:
            dev=p.stem.split("-")[0]; idx.setdefault(dev, []); idx[dev].append(str(p))
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

# ---------- Helpers ----------
def _is_url(p: str) -> bool: return p.lower().startswith(("http://","https://","data:"))
def pick_best_image(paths, target_width=1200):
    if not paths: return None
    local=[p for p in paths if not _is_url(p)]
    if not local: return paths[0]
    cand=[]
    for p in local:
        try:
            with Image.open(p) as im: w,h=im.size
            diff=abs(w-target_width); cand.append((diff, w>=target_width, w, p))
        except Exception: pass
    if not cand: return local[0]
    cand.sort(key=lambda x: (x[0], not x[1], -x[2])); return cand[0][3]

def format_currency(n): return f"NT${n:,.0f}" if isinstance(n,(int,float)) else "—"
def percent(p): return f"{round(p*100)}%" if isinstance(p,(int,float)) else "—"
def normalize(s: str) -> str: return (s or "").lower()
def cite_tag(): return "<span class='chip'>資料來源</span>"

def collect_sources(d: dict):
    out=[]
    for doc in d.get("documents",[]) or []:
        url=doc.get("url")
        if url and all(url!=x.get("url") for x in out): out.append({"label":doc.get("label","文件"),"url":url,"note":""})
    for c in d.get("citySpecifics",[]) or []:
        url=c.get("sourceUrl")
        if url and all(url!=x.get("url") for x in out): out.append({"label":f"{c.get('city','—')} {c.get('program','')} 公告","url":url,"note":"地方政府公告"})
    for s in d.get("sources",[]) or []:
        url=s.get("url")
        if url and all(url!=x.get("url") for x in out): out.append({"label":s.get("label","來源"),"url":url,"note":s.get("note","")})
    return out

# ---------- PDF ----------
def build_device_pdf(d: dict) -> bytes:
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A4); W,H=A4; x,y=20*mm, H-20*mm
    def line(text, size=12, leading=14):
        nonlocal y; c.setFont("Helvetica", size)
        for seg in str(text).splitlines(): c.drawString(x,y,seg); y-=leading
    c.setTitle(d.get("name","資料")); line(d.get("name",""), size=18, leading=22); y-=5
    img=pick_best_image(d.get("photos") or [], 1200)
    if img:
        try:
            with Image.open(img) as im: iw,ih=im.size
            maxw=W-40*mm; scale=min(1.0, maxw/iw); neww=iw*scale; newh=ih*scale
            c.drawImage(ImageReader(img), x, y-newh, width=neww, height=newh, preserveAspectRatio=True, mask='auto'); y-=newh+10
        except Exception: pass
    cap=d.get("funding",{}).get("amountCap"); ratio=d.get("funding",{}).get("ratioCap"); life=d.get("lifespanYears")
    line(f"金額上限：{format_currency(cap)}"); line(f"補助比例：{percent(ratio)}"); line(f"使用年限：{life} 年" if life else "使用年限：—"); y-=5
    line("補助資格：", size=14, leading=18)
    for e in d.get("eligibility",[]) or []: line(f"• {e}", size=11)
    if d.get("citySpecifics"):
        y-=5; line("各縣市差異：", size=14, leading=18)
        for cty in d["citySpecifics"]:
            cap2=(cty.get("funding") or {}).get("amountCap"); ratio2=(cty.get("funding") or {}).get("ratioCap")
            line(f"• {cty.get('city','—')} / {cty.get('program','—')} - 上限 {format_currency(cap2)}，比例 {percent(ratio2)}", size=10)
    y-=5; line("參考資料來源：", size=14, leading=18)
    srcs=collect_sources(d)
    if srcs:
        for i,s in enumerate(srcs,1): line(f"{i}. {s.get('label','來源')}  {s.get('url','')}", size=10, leading=12)
    else:
        line("（尚未設定來源）", size=10)
    c.showPage(); c.save(); return buf.getvalue()

# ---------- QR ----------
def show_qr_dialog(d: dict):
    url=""
    for c in d.get("citySpecifics",[]) or []:
        if c.get("sourceUrl"): url=c["sourceUrl"]; break
    if not url:
        for s in d.get("documents",[]) or []:
            if s.get("url"): url=s["url"]; break
    if not url: url=f"Assistive: {d.get('name','')}"
    img=qrcode.make(url); bio=io.BytesIO(); img.save(bio, format="PNG"); qr=bio.getvalue()
    if hasattr(st,"dialog"):
        @st.dialog("掃描 QR 以開啟來源/此筆資料連結")
        def _dlg():
            st.image(qr, caption=url, use_column_width=True)
            st.caption("可改為指向你的站內詳細頁永久連結")
        _dlg()
    else:
        with st.expander("QR Code"): st.image(qr, caption=url, use_column_width=True)

# ---------- Search / Controls ----------
st.title("輔具補助查詢")
q = st.text_input("搜尋輔具名稱或別名", placeholder="輸入：輪椅、助行器、移位帶、助聽器…")

label_to_id = {}; labels=[]
for d in devices:
    labels.append(d["name"]); label_to_id[d["name"]] = d["id"]
    for a in d.get("aliases",[]) or []:
        lbl=f"{a}（{d['name']}）"; labels.append(lbl); label_to_id[lbl]=d["id"]
picked = st.selectbox("📋 直接選擇輔具（含別名）", ["— 直接選擇 —"]+labels, index=0)
if picked and picked!="— 直接選擇 —":
    st.session_state["selected_id"]=label_to_id[picked]; st.session_state["view"]="detail"; st.rerun()

program = st.radio("體系過濾", ["全部","LTC","PWD"], index=0, horizontal=True)

def match_device(d):
    if program!="全部" and program not in d.get("programs",[]): return False
    if q:
        qn = normalize(q.strip())
        return (qn in normalize(d["name"])) or any(qn in normalize(a) for a in d.get("aliases",[]) or [])
    return True
filtered = [d for d in devices if match_device(d)]
st.caption(f"找到 {len(filtered)} 項")

# ---------- Views ----------
def render_list_view():
    for d in filtered:
        with st.container(border=True):
            c1,c2,c3 = st.columns([1,3,1])
            with c1:
                img=pick_best_image(d.get("photos") or [], 800)
                if img: st.image(img, use_column_width=True)
                else: st.caption("（無圖片）")
            with c2:
                st.subheader(d["name"])
                aliases=d.get("aliases",[]) or []
                if aliases:
                    chips=" ".join([f"<span class='chip'>{a}</span>" for a in aliases[:6]])
                    st.markdown(chips, unsafe_allow_html=True)
                st.caption(f"{d.get('category','—')}｜體系：{' / '.join(d.get('programs', []))}")
                cap=d.get("funding",{}).get("amountCap"); ratio=d.get("funding",{}).get("ratioCap")
                st.caption(f"金額上限：{format_currency(cap)}　補助比例：{percent(ratio)}")
            with c3:
                if st.button("查看詳情", key=f"view-{d['id']}"):
                    st.session_state["selected_id"]=d["id"]; st.session_state["view"]="detail"; st.rerun()

def render_detail_view():
    d = next((x for x in devices if x["id"]==st.session_state["selected_id"]), None)
    if not d:
        st.warning("找不到該項目")
        if st.button("返回列表"): st.session_state["view"]="list"; st.rerun()
        return
    t1,t2,t3 = st.columns([1,1,1])
    if t1.button("← 返回列表"): st.session_state["view"]="list"; st.rerun()
    pdf = build_device_pdf(d)
    t2.download_button("下載此筆 PDF", data=pdf, file_name=f"{d['id']}.pdf", mime="application/pdf")
    if t3.button("顯示 QR Code"): show_qr_dialog(d)

    st.header(d["name"])
    big=pick_best_image(d.get("photos") or [], 1200)
    if big: st.image(big, use_column_width=True)

    c1,c2,c3=st.columns(3)
    cap=d.get("funding",{}).get("amountCap"); ratio=d.get("funding",{}).get("ratioCap"); life=d.get("lifespanYears")
    c1.metric("金額上限", format_currency(cap))
    c2.metric("補助比例", percent(ratio))
    c3.metric("使用年限", f"{life} 年" if life else "—")

    st.markdown("### 補助資格（通用） " + cite_tag(), unsafe_allow_html=True)
    for e in d.get("eligibility",[]) or []: st.write(f"- {e}")

    st.markdown("### 使用年限與汰換規則 " + cite_tag(), unsafe_allow_html=True)
    if d.get('lifespanYears'): st.write(f"- 建議使用年限：**{d.get('lifespanYears')} 年**")
    else: st.write("- 建議使用年限：**依公告**")
    if d.get('renewalIntervalYears'): st.write(f"- 最短汰換間隔：**{d.get('renewalIntervalYears')} 年**")
    if d.get('usageNotes'):
        for n in d['usageNotes']: st.write(f"- {n}")

    st.markdown("### 各縣市差異（上限/比例/條件） " + cite_tag(), unsafe_allow_html=True)
    rows=[]
    for c in d.get("citySpecifics",[]) or []:
        rows.append({
            "縣市": c.get("city","—"),
            "體系": c.get("program","—"),
            "金額上限": format_currency((c.get("funding") or {}).get("amountCap")),
            "比例": percent((c.get("funding") or {}).get("ratioCap")),
            "額外條件": "、".join(c.get("extraEligibility",[]) or []) or "—",
            "效期": c.get("effectiveTo","—"),
            "來源": c.get("sourceUrl","—")
        })
    if rows:
        df=pd.DataFrame(rows); st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("尚無差異資料。")

    st.markdown("---"); st.subheader("參考資料來源")
    srcs=collect_sources(d)
    if srcs:
        for i,s in enumerate(srcs,1):
            label=s.get("label",f"來源 {i}"); url=s.get("url",""); note=s.get("note","")
            if url: st.markdown(f"{i}. [{label}]({url}) — {note}")
            else: st.markdown(f"{i}. {label} — {note}")
    else:
        st.caption("（此筆尚未設定來源，請後台補充）")

if st.session_state["view"]=="list": render_list_view()
else: render_detail_view()
