# 🏥 전국 응급의료기관 실시간 데이터 수집기

중앙응급의료센터 "내 손안의 응급실"에서 실시간으로 표출되는 전국 응급의료기관 데이터를 **1년간 자동 수집·저장**하는 프로젝트입니다.

## 수집 대상

| 항목 | 내용 |
|------|------|
| **기관 수** | 전국 417개 응급의료기관 (17개 시도) |
| **수집 주기** | 매 30분 |
| **데이터 필드** | 117개 (가용병상, 중환자실, 장비 가용 여부 등) |
| **데이터 소스** | 공공데이터포털 Open API (주) + mediboard API (보조) |

## 수집 데이터 항목 (주요)

- 응급실 가용병상 수 (음수 = 과밀)
- 수술실, 각종 중환자실 (내과/외과/신경/흉부/일반/신생/약물/화상/외상)
- CT, MRI, 조영촬영기, 인공호흡기, ECMO, CRRT 등 장비 가용 여부
- 소아 관련 (소아인공호흡기, 인큐베이터)
- 당직의 정보, 응급실 전화번호
- 체류환자 수, 총병상 수, 사용병상 수 등 (hvs 계열 필드)

## 프로젝트 구조

```
er-data-collector/
├── .github/workflows/
│   ├── collect.yml          # 매 30분 자동 수집
│   └── healthcheck.yml      # 매일 수집 상태 점검
├── scripts/
│   └── er_data_collector.py # 수집 스크립트
├── data/
│   ├── data_go_kr/          # 공공데이터포털 데이터
│   │   └── YYYY-MM/
│   │       └── data_go_kr_YYYY-MM-DD.csv
│   ├── mediboard/           # mediboard 데이터
│   │   └── YYYY-MM/
│   │       └── mediboard_YYYY-MM-DD.csv
│   └── latest/              # 최신 스냅샷 (JSON)
├── logs/
│   └── collection_log.csv   # 수집 이력
└── README.md
```

## 설정 방법

### 1. GitHub Secrets 등록

Repository → Settings → Secrets and variables → Actions → New repository secret:

| Secret 이름 | 값 |
|-------------|-----|
| `DATA_GO_KR_API_KEY` | 공공데이터포털에서 발급받은 인증키 (URL Encoding 된 키) |

### 2. 자동 수집 시작

Secrets 등록 후, GitHub Actions가 매 30분마다 자동으로 실행됩니다.
수동 실행: Actions 탭 → "응급실 데이터 수집" → Run workflow

### 3. 수집 상태 모니터링

- **매일 오전 9시 (KST)** 자동 점검
- 3시간 이상 수집 공백 발생 시 GitHub Issue 자동 생성
- `logs/collection_log.csv`에서 수집 이력 확인 가능

## 데이터 활용

### CSV 파일 구조 (data_go_kr)

| 컬럼 | 설명 | 예시 |
|------|------|------|
| collected_at | 수집 시각 | 2026-03-25 10:30:00 |
| region | 시도 | 서울특별시 |
| hpid | 기관코드 | A1100010 |
| dutyName | 기관명 | 삼성서울병원 |
| hvec | 응급실 가용병상 | -27 (음수=과밀) |
| hvidate | 데이터 입력일시 | 20260325103000 |
| ... | (117개 필드) | ... |

### 연간 데이터 규모 (예상)

- 일별: ~417기관 × 48회 = ~20,000행
- 월별: ~600,000행 (~30MB)
- 연간: ~7,300,000행 (~360MB)

## 데이터 소스

- **공공데이터포털**: https://www.data.go.kr/data/15000563/openapi.do
- **내 손안의 응급실**: https://mediboard.nemc.or.kr

## 라이선스

수집 데이터는 공공데이터 이용약관에 따릅니다.
