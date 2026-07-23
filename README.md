# 문법 카드 이미지 생성기 (Streamlit)

`grammar_content.xlsx`의 세 시트를 읽어서 각각의 표를 이미지(PNG)로 만들어주는 Streamlit 앱입니다.

- `rule_reminder` 시트 → `rule_reminder.png`
- `error_spotlight` 시트 → `error_spotlight.png`
- `practice_ref` 시트 → `practice_ref.png`

## 파일 구성
```
grammar_app/
├── app.py                 # Streamlit 앱
├── build_excel.py         # grammar_content.xlsx 를 생성하는 스크립트 (내용 수정 시 재실행)
├── grammar_content.xlsx   # 3개 시트를 담은 엑셀 (앱이 읽는 데이터 소스)
└── requirements.txt
```

## 실행 방법
```bash
pip install -r requirements.txt
streamlit run app.py
```
브라우저가 열리면 탭에서 각 카드를 확인하고, `⬇ ○○.png 다운로드` 버튼으로 이미지를 받을 수 있습니다.
'전체 미리보기' 탭에서는 3개 이미지를 한 번에 ZIP으로도 받을 수 있습니다.

## 내용을 수정하고 싶다면
1. `grammar_content.xlsx`를 직접 열어 표 내용을 수정 (시트 이름은 `rule_reminder`, `error_spotlight`, `practice_ref` 그대로 유지)
   - 또는 `build_excel.py` 안의 데이터를 고친 뒤 `python build_excel.py`로 재생성
2. Streamlit 앱을 새로고침하면 바로 반영됩니다.

## 참고
- 한글 폰트는 시스템에 설치된 Noto Sans CJK KR을 사용합니다. 다른 환경(예: 로컬 Windows/Mac)에서 실행할 경우
  `app.py` 상단의 `FONT_REGULAR` / `FONT_BOLD` 경로를 해당 OS에 있는 한글 폰트 경로로 바꿔주세요.
