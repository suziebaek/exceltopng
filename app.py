"""
Cell 통합 카드 이미지 생성기 (Streamlit)

엑셀 업로드 -> 시트 3개(Rule Reminder Card / Error Spotlight / 교재 Practice 문항)를
'챕터' + 'Cell (개념)' 기준으로 묶어서, 각 Cell마다
[Rule Reminder + Error Spotlight + Practice] 를 하나로 쌓은 통합 이미지 1장을 생성한다.
"""
import io
import re
import zipfile

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------------
FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

TOTAL_WIDTH = 1400
PAD = 16
LINE_H = 24

RULE_COLOR = (185, 166, 222)      # 연보라
ERROR_COLOR = (233, 165, 165)     # 연분홍
PRACTICE_COLOR = (163, 209, 181)  # 연초록
ALT_BG = (247, 247, 250)
BODY_BG = (255, 255, 255)
BORDER_COLOR = (190, 190, 190)
TEXT_COLOR = (35, 35, 35)

# 시트를 찾기 위한 키워드 (시트 이름이 조금 달라도 매칭되도록)
SHEET_KEYWORDS = {
    "rule": ["rule reminder", "rule_reminder"],
    "error": ["error spotlight", "error_spotlight"],
    "practice": ["practice"],
}

SECTION_META = {
    "rule": {"label": "Rule Reminder", "color": RULE_COLOR, "center_cols": [0]},
    "error": {"label": "Error Spotlight", "color": ERROR_COLOR, "center_cols": [0, 3]},
    "practice": {"label": "Practice", "color": PRACTICE_COLOR, "center_cols": [0]},
}

st.set_page_config(page_title="Cell 통합 카드 생성기", layout="wide")


# ------------------------------------------------------------------
# 엑셀 로드 & 정리
# ------------------------------------------------------------------
def find_sheet(sheet_names, keywords):
    for name in sheet_names:
        low = name.lower()
        if any(k in low for k in keywords):
            return name
    return None


@st.cache_data
def load_and_prepare(file_bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    sheet_names = xls.sheet_names

    dfs = {}
    for key, keywords in SHEET_KEYWORDS.items():
        sheet = find_sheet(sheet_names, keywords)
        if sheet is None:
            dfs[key] = None
            continue
        # 1행은 제목(합쳐진 셀), 2행이 실제 컬럼 헤더
        df = xls.parse(sheet, header=1)
        df = df.dropna(how="all")
        # 첫 두 컬럼(챕터, Cell(개념))은 병합 셀 -> 앞쪽 값으로 채움
        df.iloc[:, 0] = df.iloc[:, 0].ffill()
        df.iloc[:, 1] = df.iloc[:, 1].ffill()
        df = df.fillna("")
        dfs[key] = df
    return dfs


def ordered_pairs(df):
    """(챕터, Cell) 조합을 최초 등장 순서대로 반환."""
    if df is None:
        return []
    pairs = df.iloc[:, [0, 1]].drop_duplicates()
    return list(pairs.itertuples(index=False, name=None))


def build_groups(dfs):
    """모든 시트를 통틀어 (챕터, Cell) 그룹 목록 생성 (등장 순서 유지)."""
    seen = []
    seen_set = set()
    for key in ["rule", "error", "practice"]:
        for pair in ordered_pairs(dfs.get(key)):
            if pair not in seen_set:
                seen_set.add(pair)
                seen.append(pair)

    groups = []
    for chapter, cell in seen:
        entry = {"chapter": chapter, "cell": cell}
        for key in ["rule", "error", "practice"]:
            df = dfs.get(key)
            if df is None:
                entry[key] = None
                continue
            sub = df[(df.iloc[:, 0] == chapter) & (df.iloc[:, 1] == cell)]
            content_cols = df.columns[2:]
            entry[key] = sub[content_cols].reset_index(drop=True)
        groups.append(entry)
    return groups


# ------------------------------------------------------------------
# 이미지 렌더링 (표 하나)
# ------------------------------------------------------------------
def _font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


def _wrap_text(draw, text, font, max_width):
    lines = []
    for raw_line in str(text).split("\n"):
        if raw_line == "":
            lines.append("")
            continue
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


def render_section_image(label, color, df, col_width_ratios, center_cols):
    """섹션 하나(label 배너 + 표)를 이미지로 렌더링. df가 비어있으면 None 반환."""
    if df is None or len(df) == 0:
        return None

    n_cols = len(df.columns)
    ratio_sum = sum(col_width_ratios)
    col_widths = [int(TOTAL_WIDTH * r / ratio_sum) for r in col_width_ratios]

    header_font = _font(17, bold=True)
    body_font = _font(16)
    label_font = _font(16, bold=True)

    dummy = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    header_lines = [
        _wrap_text(dummy, str(col), header_font, col_widths[c] - 2 * PAD)
        for c, col in enumerate(df.columns)
    ]
    header_h = max(len(l) for l in header_lines) * LINE_H + 2 * PAD

    body_rows_lines = []
    body_row_heights = []
    for _, row in df.iterrows():
        row_lines = []
        for c in range(n_cols):
            lines = _wrap_text(dummy, row.iloc[c], body_font, col_widths[c] - 2 * PAD)
            row_lines.append(lines)
        h = max(len(l) for l in row_lines) * LINE_H + 2 * PAD
        body_rows_lines.append(row_lines)
        body_row_heights.append(h)

    label_h = 34
    total_h = label_h + header_h + sum(body_row_heights)

    img = Image.new("RGB", (TOTAL_WIDTH, total_h), BODY_BG)
    draw = ImageDraw.Draw(img)

    # 섹션 라벨 배너
    draw.rectangle([0, 0, TOTAL_WIDTH, label_h], fill=color)
    draw.text((PAD, 7), label, font=label_font, fill=(20, 20, 20))
    y = label_h

    # 표 헤더
    light = tuple(min(255, int(c + (255 - c) * 0.65)) for c in color)
    draw.rectangle([0, y, TOTAL_WIDTH, y + header_h], fill=light)
    x = 0
    for c, col in enumerate(df.columns):
        lines = header_lines[c]
        block_h = len(lines) * LINE_H
        ty = y + (header_h - block_h) // 2
        for line in lines:
            tw = draw.textlength(line, font=header_font)
            tx = x + (col_widths[c] - tw) // 2
            draw.text((tx, ty), line, font=header_font, fill=(20, 20, 20))
            ty += LINE_H
        x += col_widths[c]
    y += header_h

    # 표 본문
    for r, row_lines in enumerate(body_rows_lines):
        row_h = body_row_heights[r]
        bg = ALT_BG if r % 2 == 1 else BODY_BG
        draw.rectangle([0, y, TOTAL_WIDTH, y + row_h], fill=bg)
        x = 0
        for c, lines in enumerate(row_lines):
            block_h = len(lines) * LINE_H
            ty = y + (row_h - block_h) // 2
            centered = c in center_cols
            for line in lines:
                tw = draw.textlength(line, font=body_font)
                tx = x + (col_widths[c] - tw) // 2 if centered else x + PAD
                draw.text((tx, ty), line, font=body_font, fill=TEXT_COLOR)
                ty += LINE_H
            x += col_widths[c]
        y += row_h

    # 구분선 / 외곽선
    x = 0
    for w in col_widths[:-1]:
        x += w
        draw.line([(x, label_h), (x, total_h)], fill=BORDER_COLOR, width=1)
    draw.line([(0, label_h + header_h), (TOTAL_WIDTH, label_h + header_h)],
              fill=BORDER_COLOR, width=1)
    draw.rectangle([0, 0, TOTAL_WIDTH - 1, total_h - 1], outline=BORDER_COLOR, width=1)

    return img


COL_RATIOS = {
    "rule": [1, 3.3],
    "error": [1.2, 1.6, 1.6, 1.4],
    "practice": [0.9, 2.6, 3.0],
}

GAP = 14  # 섹션 사이 여백


def render_combined_cell_image(group):
    sections = []
    for key in ["rule", "error", "practice"]:
        meta = SECTION_META[key]
        img = render_section_image(
            meta["label"], meta["color"], group.get(key),
            COL_RATIOS[key], meta["center_cols"],
        )
        if img is not None:
            sections.append(img)

    if not sections:
        return None

    total_h = sum(s.height for s in sections) + GAP * (len(sections) - 1)
    combined = Image.new("RGB", (TOTAL_WIDTH, total_h), BODY_BG)
    y = 0
    for i, s in enumerate(sections):
        combined.paste(s, (0, y))
        y += s.height
        if i < len(sections) - 1:
            y += GAP
    return combined


def safe_filename(chapter, cell):
    text = f"{chapter}_{cell}"
    text = re.sub(r"[^0-9A-Za-z가-힣]+", "_", text).strip("_")
    return text


# ------------------------------------------------------------------
# 화면
# ------------------------------------------------------------------
def main():
    st.title("📘 Cell 통합 카드 이미지 생성기")
    st.caption(
        "엑셀을 업로드하면 '챕터 + Cell(개념)' 단위로 Rule Reminder / Error Spotlight / "
        "Practice 내용을 하나로 합친 이미지를 Cell마다 1장씩 만들어 드립니다."
    )

    uploaded = st.file_uploader("엑셀 파일 업로드 (.xlsx)", type=["xlsx"])

    if uploaded is None:
        st.info("Rule Reminder Card / Error Spotlight / 교재 Practice 문항 시트가 들어있는 "
                "엑셀 파일을 업로드해 주세요. (각 시트는 '챕터', 'Cell (개념)' 컬럼을 포함해야 합니다)")
        st.stop()

    dfs = load_and_prepare(uploaded.getvalue())

    missing = [k for k, v in dfs.items() if v is None]
    if missing:
        st.warning(f"다음 시트를 찾지 못했습니다: {missing}. 시트 이름에 'Rule Reminder', "
                   f"'Error Spotlight', 'Practice' 라는 단어가 포함되어 있는지 확인해 주세요.")

    groups = build_groups(dfs)

    if not groups:
        st.error("Cell 그룹을 만들 수 없습니다. 엑셀 구조를 확인해 주세요.")
        st.stop()

    chapters = list(dict.fromkeys(g["chapter"] for g in groups))

    all_images = {}  # filename -> PIL Image

    chapter_tabs = st.tabs(chapters)

    for tab, chapter in zip(chapter_tabs, chapters):
        with tab:
            chapter_groups = [g for g in groups if g["chapter"] == chapter]
            for g in chapter_groups:
                img = render_combined_cell_image(g)
                if img is None:
                    continue
                fname = safe_filename(g["chapter"], g["cell"]) + ".png"
                all_images[fname] = img

                with st.expander(f"🔹 {g['cell']}", expanded=True):
                    st.image(img, use_container_width=True)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    st.download_button(
                        label=f"⬇ {fname} 다운로드",
                        data=buf.getvalue(),
                        file_name=fname,
                        mime="image/png",
                        key=f"dl_{fname}",
                    )

    st.divider()
    st.subheader(f"전체 {len(all_images)}개 이미지 ZIP 다운로드")
    if all_images:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            for fname, img in all_images.items():
                b = io.BytesIO()
                img.save(b, format="PNG")
                zf.writestr(fname, b.getvalue())
        st.download_button(
            label="⬇ 전체 이미지 ZIP으로 다운로드",
            data=zip_buf.getvalue(),
            file_name="cell_combined_cards.zip",
            mime="application/zip",
        )


if __name__ == "__main__":
    main()
