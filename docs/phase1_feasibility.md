# OpenPASCO — Phase 0 조사 결과 및 Phase 1 실행 계획

작성일: 2026-11-18 · 상태: 웹 조사만 완료, **실제 장비 검증 0건**

## 1. 현재 개발 환경 (실측)

| 항목 | 결과 |
|---|---|
| Python | 3.14.4 (PASCO 공식 라이브러리 요구사항 `>=3.14` 충족) |
| Bluetooth | Realtek `0bda:5852` 내장 어댑터 있음 (BLE 지원 여부는 `bluetoothctl show`로 확인 필요) |
| 연결된 PASCO 장비 | **없음** (`lsusb`에 VID `0945` 없음, BT 기기 목록에도 없음) |
| Capstone 샘플 파일 | **없음** (작업 폴더 비어 있음) |

## 2. 장비 계열별 조사 결과

| 계열 | 연결 방식 | 공개 정보 | Linux 가능성 | 판정 |
|---|---|---|---|---|
| **Wireless 센서** (PS-32xx 등), //code.Node, //control.Node, Smart Cart | BLE 4.0+ | PASCO 공식 Python 라이브러리 `pasco` (소스 공개, bleak 기반) | **높음** — bleak은 Linux(BlueZ) 공식 지원. 단 PASCO는 "Linux (Raspberry Pi)"만 명시, Ubuntu 데스크톱 미검증 | 조사 중 → 1순위 |
| **AirLink** (PS-3200, PASPORT→BLE) | BLE | 라이브러리에 "TODO: AirLink" 흔적만 있음 | 중간 — BLE 경로는 같으나 프로토콜 미완성 | 조사 중 |
| **550 Universal Interface** (UI-5001) | USB + Bluetooth | SPARKvue 웹에서 "PS550"으로 BLE 페어링된다는 공식 문서 / 반면 호환표에는 "Classic 2.X"로 표기 — **서로 모순** | 불명 — 실기기 확인 필요 | 조사 중 |
| **PASPORT USB** (PS-2100A USB Link, Xplorer GLX 등) | USB | 프로토콜 비공개. VID `0x0945`(PASCO Scientific), PID `0002`=USBLink, `0003`=Xplorer, `0006`=GLX — **제3자 드라이버 사이트 출처, 미검증** | 낮음~중간 — USB 트래픽 캡처 기반 분석 필요 | 미지원 |
| **850 Universal Interface** (UI-5000) | USB | Capstone 전용, 공개 문서·오픈 드라이버 없음 | 낮음 | 미지원 |
| **ScienceWorkshop** (750 등 레거시) | 750: USB/SCSI 계열 인터페이스 경유 | 공개 정보 없음 | 매우 낮음 | 미지원 |
| PS-3500 BLE 어댑터 | USB BLE 동글 | 일반 BLE 어댑터. Bluetooth Classic 제품(PS-2011 등)은 미지원 | 높음 (Linux 커널 드라이버로 동작할 가능성 큼, 미검증) | 조사 중 |

### 2.1 PASCO 공식 Python 라이브러리 (`pasco`) 상세

- 소스: https://github.com/PASCOscientific/pasco_python · 예제: https://github.com/PASCOscientific/pasco_python_examples
- 버전 0.3.66 (master), 의존성 `bleak==3.0.2`, `requires-python >=3.14`
- API: `PASCOBLEDevice.scan()`, `connect()`, `connect_by_id('ddd-ddd')`, `get_sensor_list()`, `get_measurement_list()`, `read_data()` — **1회성 폴링 위주**, 문서화된 연속 스트리밍/샘플링 주기 API 없음 (내부 notify 처리는 존재, 미확인)
- 센서 정의: `datasheets.py`에 XML 데이터시트(측정 항목, 공장 보정값 `FactoryCal`) 포함
- BLE UUID 규칙: `4a5c000{service}-000{char}-0000-0000-5c1e741f1c00` (char 2=명령 송신, 3=명령 수신, 5=ACK)

**⚠ 라이선스 문제 (중요)**: 이 라이브러리는 오픈소스가 아니다. PASCO "END USER LICENSE AGREEMENT FOR SOURCE CODE" — **개인·비상업·교육 용도로만 사용 허가**. 따라서:
- OpenPASCO에 코드를 **복사·포함하면 안 된다** (원칙 9).
- 사용자가 직접 설치하는 **선택적 의존성(백엔드)** 으로 호출하는 것은 비상업·교육 목적이면 허용 범위로 보인다.
- 장기적으로 자체 BLE 드라이버를 쓰려면 실제 장비의 GATT 트래픽을 직접 관찰해 독립 구현해야 한다. 라이브러리 소스를 보고 재작성하는 것은 법적으로 회색지대이므로 피한다.
- OpenPASCO를 공개 배포할 계획이라면 라이선스 검토가 먼저 필요하다.

### 2.2 USB 장비 (PASPORT / 850 / 550-USB)

- 공개 프로토콜·SDK·오픈소스 드라이버를 찾지 못했다.
- 유일한 경로: Windows에서 Capstone이 장비와 통신하는 USB 트래픽을 캡처(Wireshark + USBPcap)하거나, Linux에서 VM 패스스루 + `usbmon`으로 캡처한 뒤 분석.
- 한국 저작권법 제101조의4는 **호환성 확보 목적**의 프로그램 코드 역분석을 제한적으로 허용한다. 트래픽 관찰은 소프트웨어 디컴파일보다 안전하지만, 진행 전 학교/기관 차원 확인을 권장한다.
- Capstone 바이너리·펌웨어 디컴파일은 하지 않는다.

### 2.3 Capstone 파일(.cap) 형식

- 공식 명세 없음. 제3자 사이트는 "독점 형식"이라고만 기술(미검증).
- 실제 `.cap` 파일을 확보해 `file`, ZIP 여부, 헤더 덤프부터 확인해야 한다. 추측 구현 금지 원칙에 따라 샘플 확보 전까지 보류.

## 3. 종합 평가

| 목표 | 실현 가능성 | 근거 |
|---|---|---|
| GUI·그래프·분석·CSV (센서 무관 부분) | **높음** | 표준 Python 스택으로 구현 가능, 하드웨어와 독립 |
| Wireless(BLE) 센서 데이터 수집 | **높음** (Ubuntu 실측 전) | 공식 라이브러리 + bleak |
| PASPORT USB / 550 USB | **불확실** | 프로토콜 비공개, 트래픽 분석 필요, 수 주~수 개월 |
| 850 / ScienceWorkshop | **낮음** | 정보 전무, 장비 확보도 필요 |
| .cap 호환 | **불명** | 샘플 파일 없음 |

**권장 전략**
1. 하드웨어 계층은 `Driver` 인터페이스(검색·연결·측정 목록·스트림) 하나로 추상화하고, 첫 구현으로 **가상(시뮬레이션) 센서 드라이버**를 만든다 → GUI·분석 개발이 장비 유무에 막히지 않는다.
2. 실제 장비는 **Wireless(BLE)부터** 지원한다. 1차는 공식 `pasco` 라이브러리를 선택적 백엔드로 감싸고, 스트리밍 성능이 부족하면 자체 BLE 드라이버를 검토한다.
3. USB 계열은 Phase 1에서 디스크립터 수집까지만 하고, 트래픽 분석은 별도 연구 과제로 분리한다.

## 4. Phase 1 실행 계획

각 작업은 결과물(문서/스크립트)과 완료 기준이 있다. **1.1이 나머지 전체의 선행 조건이다.**

| # | 작업 | 결과물 | 완료 기준 |
|---|---|---|---|
| 1.1 | 보유 장비 목록 확정 (모델명·품번) | `docs/hardware/inventory.md` | 사용 가능한 실제 장비 목록 |
| 1.2 | BT 어댑터 BLE 확인: `bluetoothctl show`, `btmgmt info` | inventory에 기록 | LE 지원 여부 확인 |
| 1.3 | Wireless 센서 1종으로 공식 `pasco` 라이브러리 스모크 테스트 (venv, scan → connect → read 10회) | `tools/ble_smoke_test.py`, 결과 로그 | Ubuntu에서 실제 값 수신 성공/실패 보고 |
| 1.4 | 자체 bleak GATT 덤프 도구 (서비스/특성 목록만, 라이브러리 코드 미사용) | `tools/ble_gatt_dump.py`, `docs/hardware/<모델>.md` | 장비별 GATT 구조 문서화 |
| 1.5 | 최대 샘플링 속도 측정 (notify 기반 연속 수신 가능 여부) | 측정 결과 문서 | 실시간 그래프에 필요한 속도 충족 여부 판단 |
| 1.6 | USB 장비가 있으면: `lsusb -v -d 0945:`, `usb-devices`, `dmesg` 수집 → 클래스(HID/CDC/vendor) 판별, udev 권한 규칙 초안 | `docs/hardware/<모델>.md`, `udev/99-pasco.rules` | VID/PID·인터페이스 클래스 실측 확인 |
| 1.7 | 550 실기기가 있으면 BLE 광고 여부 확인 (모순 해소) | 문서 | BLE/Classic 판정 |
| 1.8 | Capstone `.cap` 샘플 2~3개 확보 후 구조 1차 분석 | `docs/capstone_format.md` | 컨테이너 형식 확인 (ZIP/XML/바이너리) |
| 1.9 | 지원 현황표 작성 | `docs/hardware_support.md` | 모든 장비가 4단계 상태 중 하나로 분류 |

Phase 1 종료 후 결정 사항: Phase 4 드라이버 우선순위, 자체 BLE 구현 여부, USB 트래픽 분석 착수 여부.

Phase 2(GUI·데이터 엔진)는 1.3~1.5와 **병렬 착수 가능**하다 (가상 센서 드라이버 사용).

## 5. 사용자에게 필요한 정보

1. 실제로 보유/사용 가능한 PASCO 장비 모델명 (가장 중요)
2. Capstone `.cap` 실험 파일 샘플
3. Windows/macOS PC에서 Capstone 사용 가능 여부 (USB 트래픽 캡처용)
4. OpenPASCO 배포 범위 (개인/학교 내부 vs 공개 오픈소스) — `pasco` 라이브러리 라이선스 판단에 필요

## 출처

- [PASCO Python 다운로드 페이지](https://pasco.com/downloads/python)
- [pasco_python GitHub](https://github.com/PASCOscientific/pasco_python) · [examples](https://github.com/PASCOscientific/pasco_python_examples) · [PyPI](https://pypi.org/project/pasco/)
- [PASCO 인터페이스 비교](https://pasco.com/products/guides/interface-comparison) · [호환성 표](https://pasco.com/compatibility)
- [SPARKvue 센서 연결 도움말](https://help.pasco.com/sparkvue/how-do-i/set-up-data-collection/connect-a-sensor)
- [PS-3500 제품 페이지](https://pasco.com/product/ps-3500)
- [USBLink VID/PID (제3자)](https://www.drivermax.com/Pasco-USBLink-PASCO-Scientific-USB-VID-0945-PID-0002-1_0_0_0-2008-08-14-1069190-driver.htm)
- [850 Universal Interface](https://www.pasco.com/850/)
- [.cap 확장자 (제3자)](https://fileinfo.com/extension/cap)
