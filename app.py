import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

try:
    import pytesseract
except Exception:
    pytesseract = None

APP_TITLE = "OCR 기반 콘서트 기록 자동 정리 애플리케이션"
DATA_PATH = Path("concert_records.csv")
SAMPLE_IMAGE_PATH = Path("assets/sample_ticket.png")

st.set_page_config(page_title="Concert OCR Archive", page_icon="🎫", layout="wide")


def load_data() -> pd.DataFrame:
    if DATA_PATH.exists():
        return pd.read_csv(DATA_PATH)
    return pd.DataFrame(columns=["date", "artist", "concert", "venue", "price", "ocr_text", "created_at"])


def save_record(record: dict) -> None:
    df = load_data()
    df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
    df.to_csv(DATA_PATH, index=False, encoding="utf-8-sig")


def run_ocr(image: Image.Image) -> str:
    """이미지에서 텍스트를 추출한다. Tesseract가 설치되지 않은 환경에서도 앱이 멈추지 않도록 처리한다."""
    if pytesseract is None:
        return ""
    try:
        # Korean language data가 없을 수도 있으므로 kor+eng 실패 시 eng로 재시도
        return pytesseract.image_to_string(image, lang="kor+eng")
    except Exception:
        try:
            return pytesseract.image_to_string(image, lang="eng")
        except Exception:
            return ""


def parse_text(text: str) -> dict:
    """OCR 텍스트에서 날짜, 아티스트, 공연명, 장소, 가격을 간단히 추정한다."""
    result = {"date": "", "artist": "", "concert": "", "venue": "", "price": 0}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = "\n".join(lines)

    patterns = {
        "artist": r"(?:ARTIST|아티스트|가수)\s*[:：]\s*(.+)",
        "concert": r"(?:CONCERT|공연명|공연)\s*[:：]\s*(.+)",
        "venue": r"(?:VENUE|장소|공연장)\s*[:：]\s*(.+)",
        "price": r"(?:PRICE|가격|티켓 가격)\s*[:：]\s*([0-9,]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, joined, flags=re.IGNORECASE)
        if m:
            value = m.group(1).strip()
            if key == "price":
                result[key] = int(re.sub(r"[^0-9]", "", value) or 0)
            else:
                result[key] = value

    date_match = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})(?:\s+(\d{1,2}:\d{2}))?", joined)
    if date_match:
        y, m, d, time_part = date_match.groups()
        result["date"] = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        if time_part:
            result["date"] += f" {time_part}"

    # 라벨이 없는 티켓 이미지를 위한 보조 추정
    if not result["artist"] and lines:
        for line in lines:
            if len(line) <= 30 and not re.search(r"ticket|date|venue|price|concert", line, re.I):
                result["artist"] = line
                break
    if not result["concert"]:
        for line in lines:
            if re.search(r"tour|concert|live|festival|공연|콘서트", line, re.I):
                result["concert"] = line
                break
    return result


def normalize_month(date_value: str) -> str:
    try:
        return pd.to_datetime(date_value).strftime("%Y-%m")
    except Exception:
        return "날짜 미입력"


st.title(APP_TITLE)
st.caption("티켓 이미지 또는 예매 화면을 업로드하면 OCR로 텍스트를 읽고, 공연 기록과 소비 통계를 정리하는 예시 프로젝트입니다.")

if "ocr_text" not in st.session_state:
    st.session_state.ocr_text = ""
if "parsed" not in st.session_state:
    st.session_state.parsed = {"date": "", "artist": "", "concert": "", "venue": "", "price": 0}

tab1, tab2, tab3 = st.tabs(["🎫 이미지 등록", "📋 기록 목록", "📊 통계"])

with tab1:
    st.subheader("1. 이미지 업로드 및 OCR 인식")
    col_img, col_form = st.columns([1, 1])

    with col_img:
        uploaded = st.file_uploader("공연 티켓/예매 화면/포스터 이미지를 업로드하세요", type=["png", "jpg", "jpeg"])
        use_sample = st.checkbox("샘플 티켓 이미지로 시연하기", value=(uploaded is None))
        image = None
        if uploaded is not None:
            image = Image.open(uploaded).convert("RGB")
        elif use_sample and SAMPLE_IMAGE_PATH.exists():
            image = Image.open(SAMPLE_IMAGE_PATH).convert("RGB")

        if image is not None:
            st.image(image, caption="업로드된 이미지", use_column_width=True)
            if st.button("OCR 실행", type="primary"):
                text = run_ocr(image)
                if not text.strip():
                    text = "ARTIST: TXT\nCONCERT: WORLD TOUR ACT : PROMISE\nDATE: 2026-07-12 18:00\nVENUE: KSPO DOME\nPRICE: 154,000 KRW"
                    st.info("현재 실행 환경에서 OCR 엔진을 사용할 수 없어 샘플 텍스트로 시연합니다.")
                st.session_state.ocr_text = text
                st.session_state.parsed = parse_text(text)
        else:
            st.info("이미지를 업로드하거나 샘플 티켓 이미지를 선택하세요.")

    with col_form:
        st.subheader("2. 인식 결과 확인 및 수정")
        st.text_area("OCR 추출 텍스트", value=st.session_state.ocr_text, height=160, key="ocr_text_box")
        if st.button("텍스트 기준으로 다시 자동 입력"):
            st.session_state.ocr_text = st.session_state.ocr_text_box
            st.session_state.parsed = parse_text(st.session_state.ocr_text_box)

        parsed = st.session_state.parsed
        with st.form("record_form"):
            date = st.text_input("공연 날짜", value=parsed.get("date", ""), placeholder="예: 2026-07-12 18:00")
            artist = st.text_input("아티스트", value=parsed.get("artist", ""), placeholder="예: TXT")
            concert = st.text_input("공연명", value=parsed.get("concert", ""), placeholder="예: WORLD TOUR")
            venue = st.text_input("장소", value=parsed.get("venue", ""), placeholder="예: KSPO DOME")
            price = st.number_input("티켓 가격(KRW)", min_value=0, step=1000, value=int(parsed.get("price", 0) or 0))
            submitted = st.form_submit_button("공연 기록 저장")
            if submitted:
                save_record({
                    "date": date,
                    "artist": artist,
                    "concert": concert,
                    "venue": venue,
                    "price": int(price),
                    "ocr_text": st.session_state.ocr_text_box,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                st.success("공연 기록이 저장되었습니다.")

with tab2:
    st.subheader("저장된 공연 기록")
    df = load_data()
    if df.empty:
        st.info("아직 저장된 기록이 없습니다.")
    else:
        st.dataframe(df[["date", "artist", "concert", "venue", "price"]])

with tab3:
    st.subheader("공연 기록 통계")
    df = load_data()
    if df.empty:
        st.info("통계를 표시하려면 먼저 공연 기록을 저장하세요.")
    else:
        df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0).astype(int)
        df["month"] = df["date"].apply(normalize_month)
        now_month = datetime.now().strftime("%Y-%m")
        monthly_cost = int(df.loc[df["month"] == now_month, "price"].sum())
        total_cost = int(df["price"].sum())

        c1, c2, c3 = st.columns(3)
        c1.metric("총 관람 횟수", f"{len(df)}회")
        c2.metric("이번 달 지출", f"{monthly_cost:,} KRW")
        c3.metric("누적 지출", f"{total_cost:,} KRW")

        st.markdown("### 가장 많이 본 아티스트 순위")
        artist_rank = df["artist"].value_counts().reset_index()
        artist_rank.columns = ["artist", "count"]
        st.dataframe(artist_rank)
        st.bar_chart(artist_rank.set_index("artist"))

        st.markdown("### 월별 공연 소비 금액")
        month_cost = df.groupby("month", as_index=False)["price"].sum()
        st.dataframe(month_cost)
        st.bar_chart(month_cost.set_index("month"))
