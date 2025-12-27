# Python 의존성 관리 가이드 (uv + pyproject.toml)

## Quick Reference (복사-붙여넣기용)

```bash
# 새 패키지 설치
uv add 패키지명

# 개발용 패키지 설치 (pytest, black 등)
uv add --dev 패키지명

# 패키지 삭제
uv remove 패키지명

# 의존성 동기화 (clone 후 또는 uv.lock 변경 후)
uv sync

# 가상환경 활성화
source .venv/bin/activate

# 현재 설치된 패키지 확인
uv pip list

# requirements.txt 동기화 (레거시 호환용)
uv export --no-hashes > requirements.txt
```

---

## 1. 초기 설정 (최초 1회)

### 1.1 pyproject.toml 생성

프로젝트 루트에 `pyproject.toml` 파일 생성:

```toml
[project]
name = "jaego"
version = "3.14.0"
description = "약국 재고 관리 시스템"
requires-python = ">=3.11"

dependencies = [
    "flask>=3.0.0",
    "pandas>=2.2.2",
    "openpyxl>=3.1.5",
    "plotly>=5.18.0",
    "python-calamine>=0.5.4",
]

[tool.uv]
dev-dependencies = []
```

### 1.2 uv.lock 생성 및 패키지 설치

```bash
uv sync
```

이 명령어 하나로:
- `uv.lock` 파일 자동 생성
- `.venv` 가상환경 생성 (없으면)
- 모든 의존성 설치

### 1.3 .gitignore 업데이트

```gitignore
# 가상환경 (반드시 제외)
.venv/
```

> **참고**: `requirements.txt`는 Git에 포함합니다 (레거시 호환용).

---

## 2. 일상적인 의존성 관리

### 2.1 새 패키지 추가

```bash
# 프로덕션 의존성
uv add requests

# 개발용 의존성 (테스트, 린터 등)
uv add --dev pytest black
```

`uv add` 실행 시 자동으로:
1. `pyproject.toml`에 패키지 추가
2. `uv.lock` 업데이트
3. 패키지 설치

### 2.2 패키지 삭제

```bash
uv remove requests
```

### 2.3 패키지 업그레이드

```bash
# 특정 패키지 업그레이드
uv add pandas --upgrade

# 모든 패키지 업그레이드 (주의해서 사용)
uv lock --upgrade
uv sync
```

---

## 3. Git 버전 관리

### 3.1 GitHub에 올려야 하는 파일

| 파일 | 올림 여부 | 이유 |
|------|----------|------|
| `pyproject.toml` | **O** | 직접 의존성 정의 |
| `uv.lock` | **O** | 정확한 버전 잠금 (재현 가능한 빌드) |
| `requirements.txt` | **O** | uv 없는 환경 호환 (레거시) |
| `.venv/` | **X** | 로컬 가상환경 (용량 큼, OS별 다름) |

### 3.2 의존성 변경 후 커밋 과정

```bash
# 1. 패키지 추가/삭제/업그레이드
uv add 새패키지

# 2. requirements.txt 동기화 (레거시 호환)
uv export --no-hashes > requirements.txt

# 3. 변경된 파일 확인
git status
# 변경됨: pyproject.toml, uv.lock, requirements.txt

# 4. 스테이징 및 커밋
git add pyproject.toml uv.lock requirements.txt
git commit -m "deps: add 새패키지 for 기능설명"

# 5. 푸시
git push
```

### 3.3 커밋 메시지 컨벤션 (권장)

```
deps: add requests for API calls
deps: remove unused pandas dependency
deps: upgrade flask to 3.1.0
deps: update all dependencies
```

---

## 4. 다른 개발자의 환경 세팅

### 4.1 프로젝트 클론 후 세팅 (uv 설치됨)

```bash
# 1. 저장소 클론
git clone https://github.com/username/jaego.git
cd jaego

# 2. 의존성 설치 (가상환경 자동 생성)
uv sync

# 3. 가상환경 활성화
source .venv/bin/activate

# 4. 앱 실행
python app.py
```

**단 2개 명령어**로 환경 세팅 완료!

### 4.2 uv가 설치 안 된 경우

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 또는 pip으로 설치
pip install uv
```

### 4.3 uv 없이 세팅하는 방법 (레거시)

저장소에 `requirements.txt`가 포함되어 있으므로 기존 pip 방식으로도 설치 가능:

```bash
# 1. 저장소 클론
git clone https://github.com/username/jaego.git
cd jaego

# 2. 가상환경 생성
python -m venv .venv

# 3. 가상환경 활성화
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 4. 의존성 설치
pip install -r requirements.txt

# 5. 앱 실행
python app.py
```

---

## 5. 자주 발생하는 상황

### 5.1 다른 사람이 의존성을 변경했을 때

```bash
git pull
uv sync  # 변경된 uv.lock 기반으로 동기화
```

### 5.2 의존성 충돌 발생 시

```bash
# lock 파일 재생성
uv lock

# 그래도 안 되면 캐시 정리 후 재시도
uv cache clean
uv lock
```

### 5.3 가상환경 초기화 (문제 발생 시)

```bash
rm -rf .venv
uv sync
```

---

## 6. 파일 구조 요약

```
jaego/
├── pyproject.toml    # 직접 의존성 (5개) - Git에 포함
├── uv.lock           # 전체 의존성 잠금 - Git에 포함
├── requirements.txt  # 레거시 호환용 (uv export로 생성) - Git에 포함
├── .venv/            # 가상환경 - Git에서 제외
├── .gitignore        # .venv/ 포함 필수
└── ...
```

---

## 7. requirements.txt에서 마이그레이션

기존 requirements.txt만 있는 프로젝트에서 전환하는 경우:

```bash
# 1. pyproject.toml 생성 (위의 1.1 참고)
#    - 직접 의존성만 추가 (간접 의존성은 제외)

# 2. uv.lock 생성 및 설치
uv sync

# 3. requirements.txt를 uv 기반으로 재생성 (레거시 호환 유지)
uv export --no-hashes > requirements.txt

# 4. 정상 작동 확인
python app.py
```

> **참고**: requirements.txt는 삭제하지 않고 유지합니다.
> uv가 없는 환경에서도 `pip install -r requirements.txt`로 설치할 수 있도록 하기 위함입니다.

---

## 참고 링크

- [uv 공식 문서](https://docs.astral.sh/uv/)
- [pyproject.toml 스펙 (PEP 621)](https://peps.python.org/pep-0621/)
