# Capstone `.cap` 파일 형식 (실측 기반 메모)

공식 명세가 없으므로 **샘플 파일 44개**(사용자 실험 파일과 Wine에 설치된 Capstone의 QuickStart 템플릿, Capstone 버전 1.11 ~ 2.13)를 직접 분석해 얻은 결과다. 확인하지 못한 부분은 "미확인"으로 표시했다.
구현: [storage/capstone_import.py](../storage/capstone_import.py) (읽기 전용 가져오기만 지원, `.cap` 쓰기는 지원하지 않음).

## 컨테이너

- ZIP 파일. 멤버: `main.xml`(실험 구성, 수백 KB)과 `data/Z_<hex>_<n>.tmp`(측정값 바이너리).
- `main.xml` 루트는 `<DSProExperiment>`이고 `<Header Version="...">`에 Capstone 버전이 있다.

## 측정값 위치 (확인됨)

```
DataSource  LongName="Force"  (측정값 이름; BaseUnit/DefaultUnit = 숫자 코드)
 └ DataSet  DataGroupNumber="3"   ← 런 번호
    └ DataSegmentElement
       ├ DependentStorageElement   StorageType="0"  FileName="data\Z_....tmp"  DataCacheDataSize  DataOffsetValue
       └ IndependentStorageElement StorageType="1"  CacheDataCount=N  IntervalCacheStartValue=t0  IntervalCacheInterval=dt
```

- 시간 축: `t[i] = t0 + dt * i` (i = 0..N-1).
- 값: 데이터 파일 앞쪽 `N`개 레코드. 레코드 = **12바이트, little-endian: `uint32` 유효 플래그 + `float64` 값**. 파일의 나머지는 0으로 채워져 있다(예: 96개 값 → 파일 28800바이트).
- 파일 경로 구분자가 `\`인 파일과 `/`인 파일이 섞여 있다.

### 검증 근거

- 이 방식을 가능한 모든 `StorageType 0/1` 세그먼트 **406개**에 적용했을 때, 앞쪽 `N`개 플래그가 전부 1이었고 `DataOffsetValue`는 전부 0이었다.
- 같은 실험의 위치(Position) 데이터를 차분한 값과 속도(Velocity) 값이 일치했다(최대 오차 0.057, 속도 범위 0.64 — 센서 속도와 유한차분의 차이로 설명 가능). 값 해석이 맞다는 간접 증거다.

## 아직 지원하지 않는 부분

| 항목 | 상태 |
|---|---|
| `StorageType 7` / 독립변수 `StorageType 4` (사용자가 직접 입력한 표, 샘플 53개 중 26개는 5~7개 값을 가짐) | 레이아웃 미확인 — 건너뛰고 개수만 보고 |
| 단위 | Capstone은 `BaseUnit`/`DefaultUnit`을 숫자 코드로 저장한다(예: Force=1536). 코드→단위 표를 검증할 방법이 없어 **단위는 비워 둔다** |
| 시작 시각 | 파일에서 검증된 시작 시각을 찾지 못해 파일 수정 시각을 사용 |
| 그래프·페이지 배치, 계산식, 사용자 정의 변수, 이미지/영상 | 미분석 |
| `.cap` 저장 | 미지원 (Capstone이 읽을 수 있는 파일을 만들 수 없다) |

## 안전

- 가져오기는 ZIP을 디스크에 풀지 않고 메모리에서 필요한 멤버만 읽는다(경로 조작 불가).
- 멤버 크기 상한(XML 200 MB, 데이터 512 MB)과 선언된 개수 검증이 있어, 조작된 파일이 메모리를 과도하게 쓰지 못한다.
