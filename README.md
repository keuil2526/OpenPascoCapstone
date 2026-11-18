# OpenPASCO

Ubuntu Linux용 PASCO 센서 데이터 수집·분석 프로그램 (개발 중, 개인·비상업·교육 목적).

조사 결과와 Phase 1 계획: [docs/phase1_feasibility.md](docs/phase1_feasibility.md)

## 설치

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Python 3.14 기준으로 확인했다.

## 실행

```bash
.venv/bin/python main.py
```

## 테스트

```bash
.venv/bin/python -m pytest tests
```

GUI 테스트는 `QT_QPA_PLATFORM=offscreen`으로 화면 없이 실행된다.

## 구현 현황

| 기능 | 상태 |
|---|---|
| 메인 창 (메뉴, 툴바, 도구 패널, 하단 측정 제어 바) | 구현 |
| 페이지(탭) 추가·닫기·이동, 이름 바꾸기 (탭 더블클릭 / F2) | 구현 |
| 디스플레이 추가·닫기 (끌어다 놓기 또는 더블클릭, 2열, 분할선으로 크기 조절) | 구현 — 데이터 연결 없음 |
| 미터 (아날로그 게이지 위젯) | 위젯 구현 — 데이터 연결 없음 |
| 다크 모드 (보기 메뉴, 설정 기억), 탭 옆 + 버튼 | 구현 |
| 기록/정지 버튼 (Ctrl+R), 경과 시간, 샘플링 속도 선택 | UI만 — 실제 측정 없음 |
| 창 크기·도구 패널 위치 기억, 보기 메뉴에서 도구 패널 다시 열기 | 구현 |
| 장치 검색, 열기/저장, CSV 내보내기 | 미구현 (누르면 "미구현" 안내) |
| 데이터 엔진, 센서 드라이버 | 미구현 |
