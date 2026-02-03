# Jaego 프로젝트 아키텍처 리팩토링

## 개요

이 문서는 Jaego 프로젝트의 아키텍처 리팩토링 작업을 설명합니다.
코드 중복 제거, 단일 책임 원칙 적용, 모듈화를 통해 유지보수성과 확장성을 개선했습니다.

---

## 1. 왜 리팩토링이 필요했는가?

### 문제 1: 거대한 단일 파일 (God Object)

**이전 상태:**
- `web_app.py`가 2,590줄로 모든 API 라우트를 포함
- 79개의 라우트가 하나의 파일에 밀집
- 관련 없는 기능들이 섞여 있어 코드 탐색이 어려움

**발생한 문제:**
- 새 기능 추가 시 파일 전체를 훑어야 함
- 버그 수정 시 영향 범위 파악이 어려움
- 여러 개발자가 동시에 작업할 때 충돌 발생

### 문제 2: 비즈니스 로직 중복

**이전 상태:**
- DB 초기화 로직이 `init_db.py`와 `web_app.py`에 각각 구현
- 월 리스트 생성 로직이 3곳에서 중복
- 약품코드 정규화가 4곳에서 반복

**발생한 문제:**
- 뮤테란(651600300) 약품 분류 오류: `init_db.py`에서는 전문약으로 분류되지만 `web_app.py`에서는 일반약으로 분류되는 버그
- 한 곳만 수정하면 다른 곳이 업데이트되지 않는 동기화 문제

### 문제 3: DB 모듈 보일러플레이트

**이전 상태:**
- 11개의 `*_db.py` 파일마다 동일한 패턴 반복:
  - `DB_PATH`, `get_connection()`, `db_exists()`, `init_db()`
- 50-80줄의 보일러플레이트 코드가 각 파일에 존재

---

## 2. 아키텍처 변경

### 2.1 웹 레이어: Blueprint 패턴

**이전:**
```
web_app.py (2,590줄)
└── 79개 라우트 전부 포함
```

**이후:**
```
web_app.py (216줄)
├── Flask 앱 설정
├── Blueprint 등록
└── 시스템 라우트 (heartbeat, shutdown, rebuild-db)

routes/
├── __init__.py       - Blueprint 등록 함수
├── main.py           - 메인 페이지, 워크플로우 (4개 라우트)
├── reports.py        - 보고서 생성/관리 (12개 라우트)
├── inventory.py      - 재고/임계값 (8개 라우트)
├── drugs.py          - 약품 관리 (10개 라우트)
├── patients.py       - 환자 관리 (14개 라우트)
├── suggestions.py    - 매칭 제안 (10개 라우트)
├── data.py           - 파일 업로드 (7개 라우트)
└── settings.py       - 사용자 설정 (3개 라우트)
```

**장점:**
- 각 Blueprint가 단일 도메인 책임
- 파일당 200-400줄로 가독성 향상
- 관련 코드가 한 파일에 모여 탐색 용이

### 2.2 비즈니스 로직 레이어: 공통 모듈 추출

**이전:**
```
init_db.py
└── DB 초기화 로직 (150줄)

web_app.py
└── 동일 로직 복사 (110줄)
```

**이후:**
```
db_initializer.py
└── rebuild_database() - 단일 진입점

init_db.py
└── rebuild_database() 호출

web_app.py
└── rebuild_database() 호출
```

**장점:**
- 단일 진입점으로 일관된 동작 보장
- 버그 수정 시 한 곳만 수정하면 됨
- 전문약/일반약 처리 순서가 항상 동일

### 2.3 데이터 레이어: BaseDB 추상화

**이전:**
```python
# 모든 *_db.py 파일마다 반복
DB_PATH = paths.get_db_path('xxx.sqlite3')

def get_connection():
    return sqlite3.connect(DB_PATH)

def db_exists():
    return os.path.exists(DB_PATH)
```

**이후:**
```python
# base_db.py
def create_db_helpers(db_name, table_name=None):
    db_path = paths.get_db_path(db_name)
    return {
        'db_path': db_path,
        'get_connection': lambda: sqlite3.connect(db_path),
        'db_exists': lambda: os.path.exists(db_path),
    }

# 각 *_db.py 파일에서
from base_db import create_db_helpers
_helpers = create_db_helpers('drug_flags.sqlite3')
DB_PATH = _helpers['db_path']
get_connection = _helpers['get_connection']
db_exists = _helpers['db_exists']
```

**장점:**
- 보일러플레이트 50-80줄 → 5줄로 감소
- DB 연결 로직 변경 시 한 곳만 수정
- 점진적 마이그레이션 가능

---

## 3. Blueprint 구조 상세

### routes/main.py
메인 페이지와 워크플로우 페이지 렌더링을 담당합니다.

| 라우트 | 설명 |
|--------|------|
| `GET /` | 메인 페이지 (랜딩) |
| `GET /workflow/simple` | 전문약 재고 관리 워크플로우 |
| `GET /workflow/order` | 주문 산출 워크플로우 |
| `GET /workflow/volatility` | 고변동성 약품 워크플로우 |

### routes/reports.py
보고서 생성, 조회, 삭제 및 체크/메모 기능을 담당합니다.

| 카테고리 | 주요 기능 |
|----------|----------|
| 보고서 생성 | 전문약, 변동성, 주문 산출 보고서 |
| 보고서 관리 | 목록 조회, 파일 서빙, 삭제 |
| 체크/메모 | 약품별 체크 상태, 메모 관리 |

### routes/inventory.py
재고 관리와 임계값 설정을 담당합니다.

| 카테고리 | 주요 기능 |
|----------|----------|
| 재고 | 검색, 조회, 수정 |
| 임계값 | 조회, 설정, 삭제, 통계 |

### routes/drugs.py
약품 통합 관리를 담당합니다.

| 카테고리 | 주요 기능 |
|----------|----------|
| 약품 정보 | 통합 조회, 저장 |
| 관리 약품 | 목록, 통계 |
| 플래그 | 특별관리 토글, 목록 |
| 버퍼 계산 | 최소 재고 버퍼 산출 |

### routes/patients.py
환자 관리와 약품-환자 연결을 담당합니다.

| 카테고리 | 주요 기능 |
|----------|----------|
| 환자 CRUD | 생성, 조회, 수정, 삭제 |
| 검색 | 환자 검색 |
| 매핑 | 약품-환자 연결/해제 |

### routes/suggestions.py
신규 약품 환자 추천 기능을 담당합니다.

| 카테고리 | 주요 기능 |
|----------|----------|
| 제안 | 다음 제안, 등록, 스킵 |
| 목록 | 신규 약품, 건너뛴 약품 |
| 통계 | 제안 현황 |

### routes/data.py
데이터 파일 업로드와 관리를 담당합니다.

| 카테고리 | 주요 기능 |
|----------|----------|
| 업로드 | 파일 업로드, 검증 |
| 관리 | 목록, 삭제, 미리보기 |

### routes/settings.py
사용자 설정 관리를 담당합니다.

| 라우트 | 설명 |
|--------|------|
| `GET /api/settings` | 설정 조회 |
| `POST /api/settings` | 설정 저장 |
| `POST /api/settings/reset` | 기본값 복원 |

---

## 4. 주요 공통 모듈

### db_initializer.py
DB 초기화/재생성의 단일 진입점입니다.

```python
def rebuild_database(
    data_path=None,           # CSV 파일 경로
    delete_existing=True,     # 기존 DB 삭제 여부
    include_periodicity=True, # 주기성 계산 포함
    show_summary=True         # 요약 출력
) -> dict:
    """
    Returns:
        {
            'success': bool,
            'stats': {
                'recent_count': int,
                'processed_stats': dict,
                'data_period': dict
            }
        }
    """
```

### utils.py
공통 유틸리티 함수를 제공합니다.

```python
def generate_month_list_from_metadata():
    """
    DB 메타데이터에서 월 리스트 생성
    Returns: ['2023-10', '2023-11', ...] 또는 None
    """
```

### base_db.py
DB 모듈의 보일러플레이트를 추상화합니다.

```python
def create_db_helpers(db_name, table_name=None):
    """
    Returns: {
        'db_path': str,
        'get_connection': callable,
        'db_exists': callable
    }
    """
```

---

## 5. 파일 크기 비교

| 파일 | 리팩토링 전 | 리팩토링 후 | 감소율 |
|------|-------------|-------------|--------|
| web_app.py | 2,590줄 | 216줄 | 92% |
| 전체 라우트 코드 | 1파일 | 8파일 | - |
| 평균 파일 크기 | 2,590줄 | 250줄 | - |

---

## 6. 검증 완료 항목

| 항목 | 상태 |
|------|------|
| `python init_db.py` 정상 실행 | ✅ |
| 뮤테란(651600300) 전문약 분류 | ✅ |
| 모든 워크플로우 페이지 접근 | ✅ |
| 보고서 생성/조회/삭제 | ✅ |
| 환자/약품 관리 기능 | ✅ |
| 데이터 파일 업로드 | ✅ |
