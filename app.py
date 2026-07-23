"""
문법 카드 이미지 생성기 (Streamlit)
- grammar_content.xlsx 의 3개 시트를 읽어서
  rule_reminder.png / error_spotlight.png / practice_ref.png 로 렌더링/다운로드
"""
import io
import textwrap
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------------
EXCEL_PATH = Path(__file__).parent / "grammar_content.xlsx"

FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

HEADER_BG = (185, 166, 222)      # 이미지의 연보라색 헤더
HEADER_FG = (30, 30, 30)
BODY_BG = (255, 255, 255)
ALT_BG = (247, 245, 251)
BORDER_COLOR = (170, 160, 190)
TEXT_COLOR = (35, 35, 35)

SHEETS = {
    "rule_reminder": {
        "title": "■ Rule Reminder Card",
        "center_cols": [0],
    },
    "error_spotlight": {
        "title": "■ Error Spotlight",
        "center_cols": [0, 3],
    },
    "practice_ref": {
        "title": "■ 교재 Practice 문항",
        "center_cols": [0],
    },
}

st.set_page_config(page_title="문법 카드 이미지 생성기", layout="wide")


# ------------------------------------------------------------------
# 데이터 로드
# ------------------------------------------------------------------
@st.cache_data
def load_sheets(path: str):
    xls = pd.ExcelFile(path)
    return {name: xls.parse(name).fillna("") for name in xls.sheet_names}


# ------------------------------------------------------------------
# 이미지 렌더링
# ------------------------------------------------------------------
def _font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


def _wrap_text(draw, text, font, max_width):
    lines = []
    for raw_line in str(text).split("\n"):
        if raw_line == "":
            lines.append("")
            continue
        words = list(raw_line)  # 한글/영문 혼용 -> 글자 단위 wrap이 더 안전
        current = ""
        for ch in raw_line:
            trial = current + ch
            if draw.textlength(trial, font=font) > max_width and current:
                lines.append(current)
                current = ch
            else:
                current = trial
        if current:
            lines.append(current)
    return lines


def render_table_image(title, df, center_cols=None, col_width_ratios=None):
    center_cols = center_cols or []
    n_cols = len(df.columns)
    col_width_ratios = col_width_ratios or [1] * n_cols

    total_width = 1400
    pad = 16
    header_font = _font(18, bold=True)
    body_font = _font(17)
    title_font = _font(22, bold=True)

    ratio_sum = sum(col_width_ratios)
    col_widths = [int(total_width * r / ratio_sum) for r in col_width_ratios]

    dummy_img = Image.new("RGB", (10, 10))
    dummy_draw = ImageDraw.Draw(dummy_img)

    # 각 셀의 wrap된 줄과 행 높이 계산
    header_lines = []
    for c, col in enumerate(df.columns):
        lines = _wrap_text(dummy_draw, str(col), header_font, col_widths[c] - 2 * pad)
        header_lines.append(lines)
    header_row_h = max(len(l) for l in header_lines) * 24 + 2 * pad

    body_rows_lines = []
    body_row_heights = []
    for _, row in df.iterrows():
        row_lines = []
        for c in range(n_cols):
            lines = _wrap_text(dummy_draw, row.iloc[c], body_font, col_widths[c] - 2 * pad)
            row_lines.append(lines)
        h = max(len(l) for l in row_lines) * 24 + 2 * pad
        body_rows_lines.append(row_lines)
        body_row_heights.append(h)

    title_h = 44
    total_height = title_h + header_row_h + sum(body_row_heights) + 20

    img = Image.new("RGB", (total_width, total_height), BODY_BG)
    draw = ImageDraw.Draw(img)

    # 제목
    draw.text((4, 6), title, font=title_font, fill=(20, 20, 20))
    y = title_h

    # 헤더
    x = 0
    draw.rectangle([0, y, total_width, y + header_row_h], fill=HEADER_BG)
    for c, col in enumerate(df.columns):
        lines = header_lines[c]
        block_h = len(lines) * 24
        ty = y + (header_row_h - block_h) // 2
        for line in lines:
            tw = draw.textlength(line, font=header_font)
            tx = x + (col_widths[c] - tw) // 2
            draw.text((tx, ty), line, font=header_font, fill=HEADER_FG)
            ty += 24
        x += col_widths[c]
    y += header_row_h

    # 본문
    for r, row_lines in enumerate(body_rows_lines):
        row_h = body_row_heights[r]
        bg = ALT_BG if r % 2 == 1 else BODY_BG
        draw.rectangle([0, y, total_width, y + row_h], fill=bg)
        x = 0
        for c, lines in enumerate(row_lines):
            block_h = len(lines) * 24
            ty = y + (row_h - block_h) // 2
            centered = c in center_cols
            for line in lines:
                tw = draw.textlength(line, font=body_font)
                tx = x + (col_widths[c] - tw) // 2 if centered else x + pad
                draw.text((tx, ty), line, font=body_font, fill=TEXT_COLOR)
                ty += 24
            x += col_widths[c]
        y += row_h

    # 테이블 외곽/구분선
    x = 0
    for w in col_widths[:-1]:
        x += w
        draw.line([(x, title_h), (x, total_height - 20)], fill=BORDER_COLOR, width=1)
    draw.rectangle([0, title_h, total_width - 1, total_height - 20], outline=BORDER_COLOR, width=2)
    draw.line([(0, title_h + header_row_h), (total_width, title_h + header_row_h)],
               fill=BORDER_COLOR, width=2)

    return img


COL_RATIOS = {
    "rule_reminder": [1, 3.3],
    "error_spotlight": [1.2, 1.6, 1.6, 1.4],
    "practice_ref": [0.5, 2.6, 3.0],
}


# ------------------------------------------------------------------
# 메인 화면
# ------------------------------------------------------------------
st.title("📘 문법 카드 이미지 생성기")
st.caption("grammar_content.xlsx 의 세 시트를 읽어서 rule_reminder / error_spotlight / practice_ref 이미지를 만듭니다.")

if not EXCEL_PATH.exists():
    st.error(f"엑셀 파일을 찾을 수 없습니다: {EXCEL_PATH}")
    st.stop()

sheets = load_sheets(str(EXCEL_PATH))

tabs = st.tabs(["Rule Reminder", "Error Spotlight", "Practice Ref", "전체 미리보기"])

generated_images = {}

for tab, (key, meta) in zip(tabs[:3], SHEETS.items()):
    with tab:
        df = sheets.get(key)
        if df is None:
            st.warning(f"'{key}' 시트를 엑셀에서 찾을 수 없습니다.")
            continue

        st.subheader(meta["title"])
        st.dataframe(df, use_container_width=True, hide_index=True)

        img = render_table_image(
            meta["title"], df,
            center_cols=meta["center_cols"],
            col_width_ratios=COL_RATIOS[key],
        )
        generated_images[key] = img

        st.image(img, use_container_width=True)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        st.download_button(
            label=f"⬇ {key}.png 다운로드",
            data=buf.getvalue(),
            file_name=f"{key}.png",
            mime="image/png",
            key=f"dl_{key}",
        )

with tabs[3]:
    st.subheader("전체 미리보기 & 일괄 다운로드")
    for key, meta in SHEETS.items():
        if key in generated_images:
            st.markdown(f"**{meta['title']}**")
            st.image(generated_images[key], use_container_width=True)

    if len(generated_images) == 3:
        import zipfile

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            for key, img in generated_images.items():
                b = io.BytesIO()
                img.save(b, format="PNG")
                zf.writestr(f"{key}.png", b.getvalue())
        st.download_button(
            label="⬇ 3개 이미지 ZIP으로 다운로드",
            data=zip_buf.getvalue(),
            file_name="grammar_cards.zip",
            mime="application/zip",
        )
