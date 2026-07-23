# Cell 통합 카드 이미지 생성기 (Streamlit)

엑셀 파일을 업로드하면, `챕터 + Cell (개념)` 단위로 **Rule Reminder / Error Spotlight / Practice**
세 가지 내용을 하나로 이어붙인 이미지를 Cell마다 1장씩 만들어줍니다.

## 엑셀 파일 요구 조건
시트 3개(이름에 아래 키워드가 포함되어 있으면 자동으로 인식합니다):
- `Rule Reminder ...` — 컬럼: 챕터 / Cell (개념) / 구성 요소 / 내용
- `Error Spotlight ...` — 컬럼: 챕터 / Cell (개념) / 오류 패턴 / 틀린 문장 / 올바른 문장 / 이유
- `... Practice ...` — 컬럼: 챕터 / Cell (개념) / 유형 / 내용 / 정답 및 해설

각 시트의 1행은 제목(병합 셀), 2행이 실제 컬럼 헤더입니다. `챕터`, `Cell (개념)` 컬럼은
병합 셀로 비어있는 행이 있어도 자동으로 위쪽 값을 채워서(forward-fill) 처리합니다.

## 파일 구성
```
grammar_app/
├── app.py            # Streamlit 앱
├── sample_input.xlsx # 테스트용 예시 엑셀 (CH1~3 문법정리)
└── requirements.txt
```

## 실행 방법
```bash
pip install -r requirements.txt
streamlit run app.py
```
브라우저가 열리면 엑셀 파일을 업로드하세요. 업로드 후:
- 챕터별 탭으로 나뉘어 각 Cell의 통합 이미지가 펼쳐서 보여집니다.
- 각 이미지 아래 `⬇ 다운로드` 버튼으로 개별 PNG를 받을 수 있습니다.
- 맨 아래 `⬇ 전체 이미지 ZIP으로 다운로드`로 모든 Cell 이미지를 한 번에 받을 수 있습니다.

## 이미지 구성
한 장의 이미지 안에 위에서부터
1. **Rule Reminder** (연보라 배너) — 해당 Cell의 핵심 규칙 표
2. **Error Spotlight** (연분홍 배너) — 해당 Cell의 오류 패턴 표
3. **Practice** (연초록 배너) — 해당 Cell의 연습 문항 표

가 순서대로 쌓입니다. "Cell 1. 자동사"처럼 셀 이름 자체를 이미지 위에 표시하지는 않으며,
내용(규칙 설명)에서 어떤 개념인지 알 수 있도록 구성했습니다. 대신 다운로드되는 파일명에는
`챕터_Cell명.png` 형태로 구분 정보가 들어갑니다 (예: `CH1_동사의_종류_Cell_1_자동사.png`).

특정 Cell에 Rule/Error/Practice 중 하나라도 내용이 없으면 해당 섹션은 이미지에서 자동으로
제외됩니다.

## 다른 교재 파일로 확장하려면
- 시트 이름과 컬럼 이름 규칙(위 "엑셀 파일 요구 조건")을 지키면 어떤 챕터/과목이든 그대로 동작합니다.
- 색상, 폰트 크기, 이미지 너비 등은 `app.py` 상단의 상수(`RULE_COLOR`, `TOTAL_WIDTH`, `LINE_H` 등)에서
  조정할 수 있습니다.
- 한글 폰트는 시스템에 설치된 Noto Sans CJK KR을 사용합니다. 다른 환경에서 실행할 경우
  `app.py` 상단의 `FONT_REGULAR` / `FONT_BOLD` 경로를 해당 OS의 한글 폰트 경로로 바꿔주세요.
