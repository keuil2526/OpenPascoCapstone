# OpenPASCO

Ubuntu Linux용 PASCO 센서 데이터 수집·분석 프로그램 (개발 중, 개인·비상업·교육 목적).

조사 결과와 Phase 1 계획: [docs/phase1_feasibility.md](docs/phase1_feasibility.md)

## 설치 (Ubuntu .deb)

Ubuntu 26.04(Python 3.14)에서 확인했다. 의존 패키지(PySide6, pyqtgraph, numpy, scipy)는 Ubuntu 저장소에서 자동으로 설치된다.

```bash
./packaging/build-deb.sh
sudo apt install ./dist/openpasco_0.1.0_all.deb
```

설치 후 앱 메뉴의 OpenPASCO 또는 터미널의 `openpasco`로 실행한다. 제거는 `sudo apt remove openpasco`.
`.deb`에는 PASCO 공식 BLE 라이브러리가 없다. 무선 센서를 쓰려면 아래 "설치 (사용자)"의 `./install.sh --with-pasco`를 사용한다.

## 설치 (사용자, pip 가상환경)

Python 3.14 이상이 필요하다 (3.14에서만 테스트했다). sudo는 필요 없다.

```bash
./install.sh
```

전용 가상환경(`~/.local/share/openpasco/venv`)에 설치하고, 앱 메뉴에 OpenPASCO 항목과 `~/.local/bin/openpasco` 명령을 만든다.
실행은 앱 메뉴에서 OpenPASCO를 열거나 터미널에서 `openpasco`를 입력한다.

```bash
./uninstall.sh
```

제거해도 실험 파일과 앱 설정(`~/.config/OpenPASCO`)은 남는다.

창이 뜨지 않고 Qt 플러그인 오류(`xcb` 등)가 나오면 시스템 라이브러리를 설치한다.

```bash
sudo apt install libxcb-cursor0 libxkbcommon-x11-0
```

## 설치 (개발)

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m openpasco
```

## PASCO 무선 센서 (선택)

공식 라이브러리는 개인·비상업·교육 목적 라이선스라 포함하지 않았다. 직접 설치한다.

```bash
./install.sh --with-pasco                  # 사용자 설치
.venv/bin/pip install -e ".[pasco]"        # 개발 환경
```

설치하면 "장치 검색"이 블루투스 센서도 찾는다(약 5초, 백그라운드 실행). 설치하지 않으면 가상 센서만 보이고 상태 표시줄에 안내가 뜬다.
측정은 1회 읽기를 반복하는 방식이라 샘플링 속도는 블루투스 응답 속도에 제한되고, 시간은 PC가 받은 시각이다.

## 테스트

```bash
.venv/bin/python -m pytest
```

GUI 테스트는 `QT_QPA_PLATFORM=offscreen`으로 화면 없이 실행된다.

## 구현 현황

| 기능 | 상태 |
|---|---|
| Capstone 배치를 참고한 화면: 왼쪽 도구(하드웨어 설정·데이터 요약·계산기), 오른쪽 디스플레이 패널, 흰 페이지, 하단 제어 바(기록·타이머·샘플링 속도·기록 조건·마지막 런 삭제) | 구현 (아이콘과 그림은 직접 그림) |
| 페이지(탭) 추가·닫기·이동, 이름 바꾸기 (탭 더블클릭 / F2) | 구현 |
| 디스플레이 추가·닫기 (끌어다 놓기 또는 더블클릭, 2열, 분할선으로 크기 조절) | 구현 |
| 그래프/테이블/숫자/미터 실시간 표시, 디스플레이별 측정값 선택 | 구현 (테이블·숫자·미터는 최신 런) |
| 그래프 "이전 런 겹쳐보기" (런별 색, 범례; 분석은 최신 런만) | 구현 |
| 가상 센서 (운동: 위치·속도, 온도) — 장치 검색 시 표시, 체크로 사용 여부 선택 | 구현 |
| 데이터 엔진: 런(Run) 단위 기록, 센서 스레드→GUI 안전 전달 | 구현 |
| 실험 저장·열기 (`.opasco` = SQLite: 런 데이터, 페이지·디스플레이 배치, 샘플링 속도, 측정값 정보) | 구현 — 센서 없이도 열림 |
| CSV 내보내기 (런 선택, 엑셀용 UTF-8 BOM) | 구현 |
| 저장하지 않은 변경 확인 (제목 앞 ●, 새 실험·열기·가져오기·종료 시 저장/버리기/취소) | 구현 |
| Capstone `.cap` 파일 가져오기 (읽기 전용: 런·측정값·시계열) | 구현 — 샘플 44개로 확인, 단위·그래프 설정·사용자 입력 표는 미지원 |
| 계산 측정값: `[속도] ** 2 * 0.5` 같은 수식 (사칙·거듭제곱·삼각/지수/로그 함수, 시간 `t`), 다른 센서는 시간 보간, 저장·열기에 포함 | 구현 (측정 메뉴의 계산 삭제, CSV 내보내기에 계산 열 포함) |
| 그래프 분석: 구간 선택, 통계, 선형·2차·사인·지수 피팅(R², 오차), 미분, 적분 | 구현 (그래프 위 선택 상자) |
| 다크 모드 (보기 메뉴, 설정 기억), 탭 옆 + 버튼 | 구현 |
| 기록/정지 버튼 (Ctrl+R), 경과 시간, 샘플링 속도 선택 (1–1000 Hz) | 구현 (가상 센서) |
| PASCO 무선(BLE) 센서: 공식 `pasco` 라이브러리를 선택 설치해 검색·연결·폴링 측정 | **미검증** — 가짜 장치로만 테스트, 실제 센서 없음. 이 PC에서는 BlueZ 검색이 `InProgress` 오류로 실패 (아래 참고) |
| PASCO USB 인터페이스 (PASPORT, 550 USB, 850) | 미구현 (프로토콜 비공개) |
| 창 크기·도구 패널 위치 기억, 보기 메뉴에서 도구 패널 다시 열기 | 구현 |
