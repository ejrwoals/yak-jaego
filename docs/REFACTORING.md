# Jaego 프로젝트 리팩토링 계획

## 개요

동일한 비즈니스 로직이 여러 곳에 중복 구현되어 있어 유지보수가 어렵고 버그 발생 위험이 높음.
이 문서는 중복 코드를 제거하고 단일 책임 원칙을 적용하기 위한 리팩토링 계획을 정리함.

**컨텍스트 윈도우 초기화 시에도 이 문서를 참조하여 일관성 있게 작업을 이어나갈 것.**

---

## 1. 발견된 중복 문제 목록

### 1.1 [완료] DB 초기화 로직 중복

| 위치 | 설명 | 상태 |
|------|------|------|
| `init_db.py` | CLI용 DB 초기화 | ✅ 수정됨 |
| `web_app.py` rebuild_db | Web UI용 DB 재생성 API | ✅ 수정됨 |

**해결:** `db_initializer.py` 모듈 생성, 두 곳에서 공통 함수 사용

---

### 1.2 [완료] months 생성 로직 3곳 중복

| 위치 | 상태 |
|------|------|
| `web_app.py` generate_simple_report | ✅ 수정됨 |
| `web_app.py` generate_volatility_report | ✅ 수정됨 |
| `web_app.py` calculate_order | ✅ 수정됨 |

**해결:** `utils.py`에 `generate_month_list_from_metadata()` 함수 추가

---

### 1.3 [완료] 약품코드 정규화 반복

| 위치 | 라인 | 상태 |
|------|------|------|
| `read_csv.py` load_multiple_csv_files | 184 | ✅ 수정됨 (파일 로드 시 1회만) |
| `read_csv.py` merge_by_drug_code | 4곳 | ✅ 중복 제거됨 |

**해결:** 파일 로드 시 1회만 정규화, 이후 처리에서 중복 정규화 제거

---

### 1.4 [진행 중] DB 모듈 보일러플레이트 (11개 파일)

모든 `*_db.py` 파일에서 동일한 패턴:
- `get_connection()`
- `init_db()`
- `db_exists()`

**해결:** `base_db.py` 생성 완료, 점진적 마이그레이션 진행

| 파일 | 상태 |
|------|------|
| `drug_flags_db.py` | ✅ 적용 완료 |
| 나머지 10개 | 대기 (점진적 마이그레이션 가능) |

---

### 1.5 [완료] traceback import 반복

| 위치 | 상태 |
|------|------|
| `web_app.py` 상단 | ✅ 1회만 import |
| `web_app.py` 함수 내부 37곳 | ✅ 중복 제거됨 |

**해결:** 파일 상단에 1회만 import, 함수 내부 중복 import 제거

---

## 2. 리팩토링 계획

### Phase 1: 긴급 수정 ✅ 완료

#### Task 1.1: DB 초기화 로직 통합 ✅

**생성/수정 파일:**
- `db_initializer.py` ✅ 신규 생성
- `init_db.py` ✅ 수정 완료
- `web_app.py` rebuild_db ✅ 수정 완료

**핵심 함수:**
```python
# db_initializer.py
def rebuild_database(data_path=None, include_periodicity=True, on_progress=None):
    """DB 재생성 핵심 로직 - init_db.py와 web_app.py 모두 이 함수 사용"""
```

---

#### Task 1.2: months 생성 유틸 함수 추출 ✅

**생성/수정 파일:**
- `utils.py` ✅ 함수 추가
- `web_app.py` 3곳 ✅ 수정 완료

**핵심 함수:**
```python
# utils.py
def generate_month_list_from_metadata():
    """DB 메타데이터에서 월 리스트 생성"""
```

---

### Phase 2: 코드 정리 ✅ 완료

#### Task 2.1: read_csv.py 정규화 최적화 ✅

**목표:** 약품코드 정규화를 1회만 수행

**수정 파일:**
- `read_csv.py` ✅ 수정 완료

**핵심 변경:**
- `load_multiple_csv_files()`에서 파일 로드 시 1회만 정규화
- `merge_by_drug_code()`에서 중복 정규화 코드 4곳 제거

---

#### Task 2.2: 에러 처리 표준화 ✅

**목표:** traceback import 중복 제거

**수정 파일:**
- `web_app.py` ✅ 수정 완료

**핵심 변경:**
- 파일 상단에 `import traceback` 1회만 추가
- 함수 내부 37곳의 `import traceback` 제거

---

### Phase 3: 구조 개선 ✅ 기반 완료 (점진적 마이그레이션 진행 중)

#### Task 3.1: DB 모듈 BaseDB 추상화 ✅

**목표:** 중복 보일러플레이트 제거

**생성 파일:**
- `base_db.py` ✅ 생성 완료

**제공 기능:**
- `BaseDB` 추상 클래스 (클래스 기반 DB 모듈용)
- `create_db_helpers()` 함수 (기존 함수형 API 호환)

**적용 예시:**
- `drug_flags_db.py` ✅ 리팩토링 완료
- 나머지 10개 DB 모듈 점진적 마이그레이션 가능

---

#### Task 3.2: web_app.py Blueprint 분할 ✅ 기반 완료

**목표:** 2800줄 → 파일당 300줄 이하

**생성 파일:**
```
routes/
├── __init__.py      ✅ Blueprint 등록 함수
└── settings.py      ✅ 설정 API (3개 라우트)
```

**web_app.py 변경:**
- Blueprint 등록 코드 추가 ✅
- settings API 라우트 제거 (routes/settings.py로 이동) ✅

**향후 분할 계획:**
```
routes/
├── main.py          (index, workflow)
├── reports.py       (보고서 생성)
├── inventory.py     (재고 관리)
├── drugs.py         (약품 관리)
├── patients.py      (환자 관리)
├── suggestions.py   (추천)
└── data.py          (데이터 파일 관리)
```

---

## 3. 작업 체크리스트

### Phase 1 (즉시) ✅ 완료
- [x] Task 1.1: db_initializer.py 생성
- [x] Task 1.1: init_db.py 수정 (db_initializer 사용)
- [x] Task 1.1: web_app.py rebuild_db 수정 (db_initializer 사용)
- [x] Task 1.2: utils.py에 generate_month_list_from_metadata 추가
- [x] Task 1.2: web_app.py 3곳 수정 (months 생성 유틸 사용)

### Phase 2 (1주 내) ✅ 완료
- [x] Task 2.1: read_csv.py 정규화 최적화
- [x] Task 2.2: web_app.py traceback import 정리

### Phase 3 (2-3주) ✅ 기반 완료
- [x] Task 3.1: base_db.py 생성 + drug_flags_db.py 예시 적용
- [x] Task 3.2: routes/ 패키지 생성 + settings Blueprint 분리
- [ ] (선택) 나머지 DB 모듈 점진적 마이그레이션
- [ ] (선택) 나머지 API Blueprint 분리

---

## 4. 검증 방법

### Task 1.1 검증 ✅ 완료
1. `python init_db.py` 실행 → DB 정상 생성 확인 ✅
2. Web UI에서 "DB 재생성" 버튼 클릭 → 동일 결과 확인 (동일 코드 사용)
3. 뮤테란(651600300) 약품 분류 확인 → "전문약" ✅

### Task 1.2 검증
1. 전문약 보고서 생성 → 정상 동작
2. 변동성 보고서 생성 → 정상 동작
3. 주문 산출 → 정상 동작

### Task 2.1, 2.2 검증 ✅ 완료
1. `python init_db.py` 실행 → DB 정상 생성 확인 ✅
2. 뮤테란(651600300) 약품 분류 확인 → "전문약" ✅

### Task 3.1, 3.2 검증 ✅ 완료
1. `python drug_flags_db.py` 테스트 실행 → 정상 동작 ✅
2. `web_app.py` import 확인 → Blueprint 정상 등록 ✅
3. `/api/settings` 라우트 확인 → settings Blueprint에서 제공 ✅

---

## 5. 주의사항

- 각 Task 완료 후 반드시 테스트
- 기존 동작이 변경되지 않도록 주의
- 커밋은 Task 단위로 분리

---

## 6. 세션 이력

| 날짜 | 작업 내용 |
|------|----------|
| 2026-02-03 | 중복 코드 분석 완료, 계획 문서 작성 |
| 2026-02-03 | Phase 1 완료: db_initializer.py 생성, months 유틸 함수 추가 |
| 2026-02-03 | Phase 2 완료: read_csv.py 정규화 최적화, traceback import 정리 |
| 2026-02-03 | Phase 3 기반 완료: base_db.py 생성, routes/ Blueprint 패키지 생성 |
