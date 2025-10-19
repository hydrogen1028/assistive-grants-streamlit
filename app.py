import json
from pathlib import Path
import streamlit as st
import pandas as pd

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
                st.image(resolve_photo(photos[0]), use_column_width=True)
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
