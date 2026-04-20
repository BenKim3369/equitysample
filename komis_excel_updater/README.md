# KOMIS 엑셀 자동 업데이트 도구 (원클릭)

## 1) 이 도구가 하는 일
이 도구는 **KOMIS BaseMetals 월평균 가격**을 가져와서,
`★(매주금)_원자재가격.xlsx` 파일의 **Chart 시트 빈 가격 셀만** 채웁니다.

- 기존 값이 있는 셀은 절대 덮어쓰지 않습니다.
- Table 시트는 직접 수정하지 않습니다.
- 수식/차트/서식/병합/숨김 상태를 건드리지 않도록 `openpyxl` 방식으로 저장합니다.
- 결과 파일은 원본을 보존한 채 `output` 폴더에 새 파일로 저장됩니다.

---

## 2) 사용 전 준비
### 폴더 구성
아래처럼 같은 폴더에 두세요.

- `run_update.bat`
- `★(매주금)_원자재가격.xlsx` (또는 mapping.json 패턴에 맞는 파일)
- `src`, `config`, `requirements.txt`

> 권장: `komis_excel_updater` 폴더 전체를 하나의 작업 폴더로 사용

---

## 3) 실행 방법 (비개발자용)
1. `komis_excel_updater` 폴더를 엽니다.
2. `run_update.bat`를 **더블클릭**합니다.
3. 검은 창에서 설치/수집/업데이트 진행 메시지를 확인합니다.
4. 완료 후 `output` 폴더에서 새 엑셀 파일을 확인합니다.

---

## 4) 결과 파일 위치
- 업데이트된 엑셀: `output/★(매주금)_원자재가격_updated_YYYYMMDD_HHMMSS.xlsx`
- 작업 로그: `logs/update_log_YYYYMMDD_HHMMSS.csv`
- 수동 검토 로그: `logs/manual_review_YYYYMMDD_HHMMSS.csv`

---

## 5) Python이 설치되지 않은 경우
### 증상
- 배치 파일 실행 시 Python 관련 오류가 나옴

### 조치
1. Python 3.10 이상 설치 (Windows)
2. 설치 시 **"Add Python to PATH"** 체크
3. 다시 `run_update.bat` 더블클릭

---

## 6) 자주 발생하는 실패 원인
1. **엑셀 파일명 불일치**
   - `★(매주금)_원자재가격.xlsx` 파일이 없거나 이름이 다름
2. **엑셀 파일 열림/잠금 상태**
   - 업데이트 대상 파일이 엑셀에서 열려 있으면 저장 실패 가능
3. **KOMIS 페이지 구조 변경**
   - 자동 수집이 실패하면 로그의 `issue_type` 확인
4. **시계열 모호성(ambiguous)**
   - 광종/단위 후보가 여러 개면 자동 선택하지 않고 수동 검토로 남김
5. **인터넷/보안 정책 차단**
   - 사내망/프록시에서 KOMIS 접근 차단 시 실패

---

## 7) 안전 동작 원칙
- 빈 셀만 입력
- 비어있지 않은 셀 덮어쓰기 금지
- 단위 불명확하면 입력 금지
- 매칭 애매하면 수동 검토 로그로 분리
- 원본 파일은 직접 수정하지 않고 새 파일 저장

---

## 8) 로그 상태값 설명
`update_log_*.csv` 의 `status` 컬럼:
- `updated`: 정상 업데이트
- `skipped_existing`: 기존 값 있음
- `skipped_missing_source`: KOMIS 시계열 매칭 실패
- `skipped_ambiguous_series`: 후보가 여러 개라 자동 선택 보류
- `skipped_no_matching_month`: 해당 월 데이터 없음
- `error`: 예외/보호 조건으로 처리 중단

---

## 9) 유지보수 포인트 (담당자 참고)
- KOMIS 수집 로직은 `src/fetch_komis.py`에 격리되어 있어,
  사이트 구조 변경 시 이 파일만 우선 수정하면 됩니다.
- 엑셀 업데이트 로직은 `src/update_excel.py`에 분리되어 있어,
  수집 로직 변경이 엑셀 무결성에 영향을 주지 않도록 구성했습니다.
