"""
Cell 통합 카드 이미지 생성기 (Streamlit)

엑셀 업로드 -> 시트 3개(Rule Reminder Card / Error Spotlight / 교재 Practice 문항)를
'챕터' + 'Cell (개념)' 기준으로 묶어서, 각 Cell마다
[Rule Reminder + Error Spotlight + Practice] 를 하나로 쌓은 통합 이미지 1장을 생성한다.
"""
import io
import re
import zipfile
from functools import lru_cache
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------------
# 폰트는 서버 환경(OS)에 무관하게 항상 동작하도록 앱과 함께 배포되는
# fonts/ 폴더의 파일을 사용한다 (시스템 폰트 경로에 의존하지 않음).
FONTS_DIR = Path(__file__).parent / "fonts"

FONT_FILES = {
    "title_regular": FONTS_DIR / "Know_Regular.ttf",   # 아는체 Regular - 제목용
    "title_bold": FONTS_DIR / "Know_Bold.ttf",         # 아는체 Bold - 제목용
    "body_light": FONTS_DIR / "Do_Light.ttf",          # 하는체 Light - 본문용
    "body_regular": FONTS_DIR / "Do_Regular.ttf",      # 하는체 Regular - 본문용
    "body_bold": FONTS_DIR / "Do_Bold.ttf",            # 하는체 Bold - 본문용
}

# 커스텀 폰트(아는체/하는체)에 글리프가 없는 특수문자를 안전하게 치환한다.
# (예: ⚠ -> 네모(□)로 깨짐, ✓/✗ -> 깨짐)
SYMBOL_REPLACEMENTS = {
    "⚠": "※",
    "✓": "(O)",
    "✗": "(X)",
    "∙": "·",
    "☑": "(O)",
    "☒": "(X)",
    "❌": "(X)",
    "✅": "(O)",
    "—": "―",   # em dash(U+2014, 폰트에 없음) -> horizontal bar(U+2015, 폰트에 있음)
    "–": "―",   # en dash(U+2013, 폰트에 없음) -> horizontal bar
    "‐": "-",   # hyphen(U+2010, 폰트에 없음) -> hyphen-minus
    "−": "-",   # minus sign(U+2212, 폰트에 없음) -> hyphen-minus
}

# 위 치환 사전에도 없는 미지의 문자가 나올 경우를 대비한 안전망 폴백 폰트
# (Noto Sans CJK에서 기호/문장부호 영역만 추출한 경량 서브셋)
FALLBACK_FONT_FILE = FONTS_DIR / "NotoFallback-Regular.ttf"

_missing_font_warned = set()


def sanitize_text(text: str) -> str:
    """폰트에 없는 것으로 확인된 특수문자를 안전한 문자로 치환."""
    for bad, good in SYMBOL_REPLACEMENTS.items():
        if bad in text:
            text = text.replace(bad, good)
    return text


@lru_cache(maxsize=8)
def _cmap_for(path_str: str):
    """폰트 파일의 지원 코드포인트 집합 (커버리지 체크용, 실패 시 None)."""
    try:
        from fontTools.ttLib import TTFont
        return frozenset(TTFont(path_str).getBestCmap().keys())
    except Exception:
        return None


@lru_cache(maxsize=8)
def get_fallback_font(size: int):
    if FALLBACK_FONT_FILE.exists():
        try:
            return ImageFont.truetype(str(FALLBACK_FONT_FILE), size)
        except OSError:
            pass
    return ImageFont.load_default()


@lru_cache(maxsize=64)
def get_font(style: str, size: int):
    """스타일(title_bold/title_regular/body_bold/body_regular/body_light)별
    폰트를 불러온다. 파일이 없으면 PIL 기본 폰트로 대체하고 1회만 경고한다."""
    path = FONT_FILES.get(style)
    if path is not None and path.exists():
        try:
            font = ImageFont.truetype(str(path), size)
            font._cmap = _cmap_for(str(path))  # 커버리지 체크용 (없으면 None)
            return font
        except OSError:
            pass
    if style not in _missing_font_warned:
        _missing_font_warned.add(style)
        try:
            st.warning(
                f"'{style}' 폰트 파일을 찾을 수 없어 기본 폰트로 대체합니다. "
                f"(fonts/ 폴더에 해당 파일이 있는지 확인해 주세요: {path})"
            )
        except Exception:
            pass
    font = ImageFont.load_default()
    font._cmap = None
    return font


def measure_text_safe(draw, text, font):
    """font에 없는 문자는 폴백 폰트 폭으로 계산해서 정확한 폭을 반환."""
    cmap = getattr(font, "_cmap", None)
    if not text:
        return 0
    if cmap is None or all(ord(ch) in cmap or ch == " " for ch in text):
        return draw.textlength(text, font=font)
    fb_font = get_fallback_font(getattr(font, "size", 16))
    return sum(
        draw.textlength(ch, font=(font if (ord(ch) in cmap or ch == " ") else fb_font))
        for ch in text
    )


def draw_text_safe(draw, xy, text, font, fill):
    """font에 없는 문자는 폴백 폰트로 그려서 네모(□)로 깨지는 것을 방지."""
    cmap = getattr(font, "_cmap", None)
    if not text:
        return
    if cmap is None or all(ord(ch) in cmap or ch == " " for ch in text):
        draw.text(xy, text, font=font, fill=fill)
        return
    fb_font = get_fallback_font(getattr(font, "size", 16))
    x, y = xy
    for ch in text:
        use_font = font if (ord(ch) in cmap or ch == " ") else fb_font
        draw.text((x, y), ch, font=use_font, fill=fill)
        x += draw.textlength(ch, font=use_font)


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


CELL_NUM_RE = re.compile(r"cell\s*0*([0-9]+)", re.IGNORECASE)


def extract_cell_num(cell_text):
    """'Cell 1. 조동사의 종류와 강도 Ⅰ (의무·허락·요청)' -> '1'
    시트마다 Cell 뒤 설명 문구가 조금씩 달라도(괄호 유무 등) 같은 Cell로 묶기 위해
    'Cell 번호'만 추출해서 그룹 키로 사용한다. 번호를 못 찾으면 원문 텍스트를 그대로 키로 사용."""
    m = CELL_NUM_RE.search(str(cell_text))
    if m:
        return m.group(1)
    return str(cell_text).strip()


def ordered_pairs(df):
    """(챕터, Cell번호, 원문 Cell텍스트) 조합을 최초 등장 순서대로 반환."""
    if df is None:
        return []
    pairs = df.iloc[:, [0, 1]].drop_duplicates()
    result = []
    for chapter, cell_text in pairs.itertuples(index=False, name=None):
        result.append((chapter, extract_cell_num(cell_text), cell_text))
    return result


def build_groups(dfs):
    """모든 시트를 통틀어 (챕터, Cell번호) 그룹 목록 생성 (등장 순서 유지).
    시트별로 Cell 설명 문구가 정확히 일치하지 않아도 Cell 번호만 같으면 하나로 묶는다."""
    seen = []
    seen_set = set()
    display_text = {}  # (chapter, cell_num) -> 대표로 보여줄 Cell 텍스트 (가장 긴 것 사용)
    for key in ["rule", "error", "practice"]:
        for chapter, cell_num, cell_text in ordered_pairs(dfs.get(key)):
            gkey = (chapter, cell_num)
            if gkey not in seen_set:
                seen_set.add(gkey)
                seen.append(gkey)
            # 여러 시트 중 가장 설명이 풍부한(긴) 텍스트를 대표 라벨로 채택
            if gkey not in display_text or len(str(cell_text)) > len(str(display_text[gkey])):
                display_text[gkey] = cell_text

    groups = []
    for chapter, cell_num in seen:
        cell_label = display_text[(chapter, cell_num)]
        entry = {"chapter": chapter, "cell": cell_label}
        for key in ["rule", "error", "practice"]:
            df = dfs.get(key)
            if df is None:
                entry[key] = None
                continue
            row_cell_nums = df.iloc[:, 1].apply(extract_cell_num)
            sub = df[(df.iloc[:, 0] == chapter) & (row_cell_nums == cell_num)]
            content_cols = df.columns[2:]
            entry[key] = sub[content_cols].reset_index(drop=True)
        groups.append(entry)
    return groups


# ------------------------------------------------------------------
# 이미지 렌더링 (표 하나)
# ------------------------------------------------------------------
def _wrap_text(draw, text, font, max_width):
    text = sanitize_text(str(text))
    lines = []
    for raw_line in text.split("\n"):
        if raw_line == "":
            lines.append("")
            continue
        current = ""
        for ch in raw_line:
            trial = current + ch
            if measure_text_safe(draw, trial, font) > max_width and current:
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

    header_font = get_font("body_bold", 17)
    body_font = get_font("body_regular", 16)
    label_font = get_font("title_bold", 17)

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
    draw_text_safe(draw, (PAD, 7), label, label_font, (20, 20, 20))
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
            tw = measure_text_safe(draw, line, header_font)
            tx = x + (col_widths[c] - tw) // 2
            draw_text_safe(draw, (tx, ty), line, header_font, (20, 20, 20))
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
                tw = measure_text_safe(draw, line, body_font)
                tx = x + (col_widths[c] - tw) // 2 if centered else x + PAD
                draw_text_safe(draw, (tx, ty), line, body_font, TEXT_COLOR)
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


def make_quiz_practice_df(practice_df):
    """Practice 표의 '정답' 관련 컬럼을 '정답은?' 문구로 가려서 빈칸 연습용 버전을 만든다."""
    if practice_df is None or len(practice_df) == 0:
        return practice_df
    df = practice_df.copy()
    answer_cols = [c for c in df.columns if "정답" in str(c)]
    target_cols = answer_cols if answer_cols else df.columns[-1:]
    for c in target_cols:
        df[c] = "정답은?"
    return df


def render_combined_cell_image(group, practice_mode="answer"):
    """practice_mode: 'answer' (정답·해설 포함) 또는 'quiz' (정답 가림)."""
    sections = []
    for key in ["rule", "error", "practice"]:
        meta = SECTION_META[key]
        df = group.get(key)
        if key == "practice" and practice_mode == "quiz":
            df = make_quiz_practice_df(df)
        img = render_section_image(
            meta["label"], meta["color"], df,
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


LEVEL_RE = re.compile(r"(?:^|[_\-\.\s])([HE])(?:[_\-\.\s]|$)")


def extract_level_from_filename(filename: str):
    """업로드 파일명에서 레벨 코드(H 또는 E)를 찾는다.
    예: 'CH1-3_문법정리_H.xlsx' -> 'H', 'CH1-3_문법정리_E.xlsx' -> 'E'.
    못 찾으면 None."""
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", filename)
    m = LEVEL_RE.search(stem)
    if m:
        return m.group(1)
    # 마지막 글자가 H/E인 경우도 보조로 체크 (예: '...H')
    if stem and stem[-1] in ("H", "E"):
        return stem[-1]
    return None


CHAPTER_NUM_RE = re.compile(r"ch\s*0*([0-9]+)", re.IGNORECASE)


def extract_chapter_num(chapter_text: str):
    """'CH1. 문장의 형식' -> '01' (2자리 0채움). 못 찾으면 원문 그대로."""
    m = CHAPTER_NUM_RE.search(str(chapter_text))
    if m:
        return f"{int(m.group(1)):02d}"
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", str(chapter_text)) or "00"


def build_filename(level: str, chapter_text: str, cell_num: str, variant: str) -> str:
    """BOOST-GR-{레벨}-CH{챕터 2자리}-C{셀번호}-{1=정답/2=문제}.png 형식."""
    level = level or "X"
    chapter_num = extract_chapter_num(chapter_text)
    cell_num = re.sub(r"[^0-9A-Za-z가-힣]+", "", str(cell_num)) or "0"
    return f"BOOST-GR-{level}-CH{chapter_num}-C{cell_num}-{variant}"


# ------------------------------------------------------------------
# 화면
# ------------------------------------------------------------------
def main():
    st.title("📘 Cell 통합 카드 이미지 생성기")
    st.caption(
        "엑셀을 업로드하면 '챕터 + Cell(개념)' 단위로 Rule Reminder / Error Spotlight / "
        "Practice 내용을 하나로 합친 이미지를 Cell마다 2장(정답 포함 / 빈칸 연습용)씩 만들어 드립니다."
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

    detected_level = extract_level_from_filename(uploaded.name)
    col_a, col_b = st.columns([1, 3])
    with col_a:
        level = st.text_input(
            "레벨 코드 (파일명용)",
            value=detected_level or "",
            max_chars=2,
            help="파일명이 'BOOST-GR-{레벨}-...' 형식으로 만들어집니다. "
                 "업로드한 엑셀 파일명에서 자동으로 찾은 값이며, 다르면 직접 수정하세요.",
        ).strip().upper()
    if not detected_level:
        st.warning("업로드한 파일명에서 레벨 코드(H/E)를 찾지 못했습니다. 위 칸에 직접 입력해 주세요.")

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
                cell_num = extract_cell_num(g["cell"])

                img_answer = render_combined_cell_image(g, practice_mode="answer")
                img_quiz = render_combined_cell_image(g, practice_mode="quiz")
                if img_answer is None:
                    continue

                fname_answer = build_filename(level, g["chapter"], cell_num, "1") + ".png"
                fname_quiz = build_filename(level, g["chapter"], cell_num, "2") + ".png"
                all_images[fname_answer] = img_answer
                if img_quiz is not None:
                    all_images[fname_quiz] = img_quiz

                with st.expander(f"🔹 {g['cell']}", expanded=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.caption("✅ 정답·해설 포함")
                        st.image(img_answer, use_container_width=True)
                        buf = io.BytesIO()
                        img_answer.save(buf, format="PNG")
                        st.download_button(
                            label=f"⬇ {fname_answer} 다운로드",
                            data=buf.getvalue(),
                            file_name=fname_answer,
                            mime="image/png",
                            key=f"dl_{fname_answer}",
                        )
                    with col2:
                        st.caption("📝 빈칸 연습용 (정답 가림)")
                        if img_quiz is not None:
                            st.image(img_quiz, use_container_width=True)
                            buf2 = io.BytesIO()
                            img_quiz.save(buf2, format="PNG")
                            st.download_button(
                                label=f"⬇ {fname_quiz} 다운로드",
                                data=buf2.getvalue(),
                                file_name=fname_quiz,
                                mime="image/png",
                                key=f"dl_{fname_quiz}",
                            )
                        else:
                            st.caption("(Practice 내용 없음)")

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
