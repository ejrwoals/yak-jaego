# PyInstaller 빌드 가이드

이 문서는 Jaego 프로젝트를 PyInstaller를 사용하여 Windows 실행 파일(.exe)로 빌드하는 방법을 설명합니다.

## 목차

1. [PyInstaller란?](#pyinstaller란)
2. [사전 준비](#사전-준비)
3. [빌드 방식 이해하기](#빌드-방식-이해하기)
4. [프로젝트 빌드 준비](#프로젝트-빌드-준비)
5. [spec 파일 작성](#spec-파일-작성)
6. [빌드 실행](#빌드-실행)
7. [빌드 결과물 확인](#빌드-결과물-확인)
8. [배포하기](#배포하기)
9. [문제 해결](#문제-해결)

---

## PyInstaller란?

PyInstaller는 Python 프로그램을 독립 실행형 실행 파일로 변환하는 도구입니다.

### 왜 필요한가요?

- **Python 미설치 환경에서 실행**: 사용자 PC에 Python이 없어도 실행 가능
- **간편한 배포**: 폴더 하나만 전달하면 바로 사용 가능
- **의존성 자동 포함**: pandas, flask 등 라이브러리가 모두 포함됨

### 작동 원리

```
Python 코드 + 라이브러리 + Python 인터프리터
              ↓ (PyInstaller)
        독립 실행형 .exe 파일
```

---

## 사전 준비

### 1. PyInstaller 설치

```bash
pip install pyinstaller
```

### 2. 설치 확인

```bash
pyinstaller --version
# 출력 예: 6.3.0
```

### 3. 프로젝트 의존성 확인

`requirements.txt`의 모든 패키지가 설치되어 있어야 합니다:

```bash
pip install -r requirements.txt
```

---

## 빌드 방식 이해하기

PyInstaller는 두 가지 빌드 방식을 제공합니다.

### 폴더 형태 (--onedir) ✅ 권장

```
dist/
└── Jaego/
    ├── Jaego.exe           # 실행 파일
    ├── python311.dll       # Python 런타임
    ├── _internal/          # 라이브러리들
    └── templates/          # 템플릿 파일
```

**장점:**
- 시작 속도가 빠름
- 업데이트 시 일부 파일만 교체 가능
- 디버깅이 쉬움

**단점:**
- 파일이 여러 개라 배포 시 zip 압축 필요

### 단일 파일 형태 (--onefile) ❌ 비권장

```
dist/
└── Jaego.exe              # 모든 것이 하나의 파일에 압축됨
```

**장점:**
- 파일 하나로 배포 가능

**단점:**
- **매 실행마다 임시 폴더에 압축 해제** (수 초 소요)
- **종료 시 임시 파일 삭제**
- 시작이 느림
- SQLite DB 등 데이터 파일 관리가 복잡함

> **이 프로젝트는 폴더 형태(--onedir)를 사용합니다.**
> Flask 웹앱이므로 빠른 시작이 중요하고, 외부 데이터 파일(data/, DB)이 많기 때문입니다.

---

## 프로젝트 빌드 준비

### 경로 처리 수정

PyInstaller로 빌드하면 파일 경로가 달라집니다. `web_app.py`에서 경로를 동적으로 처리해야 합니다.

#### 수정 전 (개발 환경 전용)

```python
# 현재 코드 - 개발 환경에서만 작동
TEMPLATE_FOLDER = 'templates'
DB_PATH = 'recent_inventory.sqlite3'
```

#### 수정 후 (개발 + 빌드 환경 모두 지원)

```python
import sys
import os

def get_base_path():
    """
    실행 환경에 따라 기본 경로를 반환합니다.

    - PyInstaller 빌드: exe 파일이 있는 폴더
    - 개발 환경: 스크립트 파일이 있는 폴더
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller로 빌드된 실행 파일
        return os.path.dirname(sys.executable)
    else:
        # 일반 Python 스크립트
        return os.path.dirname(os.path.abspath(__file__))

def get_bundle_path():
    """
    번들된 리소스(templates 등)의 경로를 반환합니다.

    - PyInstaller 빌드: _internal 폴더 내부
    - 개발 환경: 스크립트 파일이 있는 폴더
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller는 리소스를 _MEIPASS에 번들링
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.abspath(__file__))

# 경로 설정
BASE_PATH = get_base_path()
BUNDLE_PATH = get_bundle_path()

# 사용자 데이터 경로 (exe와 같은 위치)
DATA_PATH = os.path.join(BASE_PATH, 'data')
DB_PATH = os.path.join(BASE_PATH, 'recent_inventory.sqlite3')

# 번들 리소스 경로 (앱 내부에 포함됨)
TEMPLATE_PATH = os.path.join(BUNDLE_PATH, 'templates')
```

#### 경로 구분이 필요한 이유

| 경로 유형 | 설명 | 예시 |
|----------|------|------|
| **BASE_PATH** | exe 파일 위치, 사용자 데이터 저장 | data/, *.sqlite3 |
| **BUNDLE_PATH** | 앱에 포함된 리소스 | templates/ |

```
C:\Users\약사\재고관리\          ← BASE_PATH (exe 위치)
├── Jaego.exe
├── _internal\                   ← BUNDLE_PATH (번들 리소스)
│   └── templates\
├── data\                        ← 사용자 데이터 (BASE_PATH 하위)
└── *.sqlite3                    ← DB 파일 (BASE_PATH 하위)
```

---

## spec 파일 작성

spec 파일은 PyInstaller의 빌드 설정 파일입니다. 프로젝트 루트에 `jaego.spec` 파일을 생성합니다.

### jaego.spec

```python
# -*- mode: python ; coding: utf-8 -*-

# PyInstaller spec 파일
# 빌드 명령: pyinstaller jaego.spec

a = Analysis(
    ['web_app.py'],  # 메인 스크립트
    pathex=[],
    binaries=[],
    datas=[
        # (소스 경로, 번들 내 경로)
        ('templates', 'templates'),  # HTML 템플릿 포함

        # 주의: 아래 항목들은 포함하지 않음 (사용자 데이터)
        # - data/ 폴더: 월별 CSV/Excel 파일
        # - *.sqlite3: 데이터베이스 파일
    ],
    hiddenimports=[
        # Flask 관련
        'flask',
        'jinja2',
        'werkzeug',

        # 데이터 처리
        'pandas',
        'numpy',
        'scipy',
        'scipy.spatial.distance',  # cdist 함수

        # Excel 파일 처리
        'openpyxl',
        'xlrd',

        # 기타
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 불필요한 모듈 제외 (빌드 크기 감소)
        'tkinter',
        'matplotlib',
        'PIL',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Jaego',  # 실행 파일 이름
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # UPX 압축 사용 (크기 감소)
    console=True,  # True: 콘솔 창 표시, False: 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',  # 아이콘 파일 (선택사항)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Jaego',  # 출력 폴더 이름
)
```

### spec 파일 주요 설정 설명

| 설정 | 설명 |
|------|------|
| `Analysis(['web_app.py'])` | 메인 스크립트 지정 |
| `datas` | 함께 번들할 데이터 파일 (templates 등) |
| `hiddenimports` | PyInstaller가 자동 감지 못하는 모듈 |
| `excludes` | 제외할 모듈 (크기 최적화) |
| `console=True` | 콘솔 창 표시 여부 |
| `name='Jaego'` | 출력 파일/폴더 이름 |

---

## 빌드 실행

### 방법 1: spec 파일 사용 (권장)

```bash
# 프로젝트 루트에서 실행
pyinstaller jaego.spec
```

### 방법 2: 명령줄에서 직접 실행

```bash
pyinstaller --onedir \
    --name Jaego \
    --add-data "templates:templates" \
    --hidden-import flask \
    --hidden-import pandas \
    --hidden-import numpy \
    --hidden-import scipy \
    --hidden-import openpyxl \
    --console \
    web_app.py
```

> **참고**: Windows에서는 `--add-data` 구분자가 `;`입니다.
> ```bash
> --add-data "templates;templates"
> ```

### 빌드 과정

```
1. 의존성 분석 중...
2. PYZ 아카이브 생성 중...
3. EXE 빌드 중...
4. COLLECT 수집 중...

빌드 완료!
출력 위치: dist/Jaego/
```

---

## 빌드 결과물 확인

### 폴더 구조

```
dist/
└── Jaego/
    ├── Jaego.exe              # 메인 실행 파일
    ├── python311.dll          # Python 런타임
    ├── _internal/             # 내부 라이브러리
    │   ├── flask/
    │   ├── pandas/
    │   ├── numpy/
    │   ├── templates/         # 번들된 템플릿
    │   └── ...
    └── base_library.zip
```

### 테스트 실행

```bash
# 빌드된 exe 실행
cd dist/Jaego
./Jaego.exe

# 또는 더블클릭으로 실행
```

### 테스트 체크리스트

- [ ] 앱이 정상적으로 시작되는가?
- [ ] 웹 브라우저가 자동으로 열리는가?
- [ ] DB 초기화가 작동하는가?
- [ ] 보고서 생성이 작동하는가?
- [ ] 템플릿이 정상적으로 렌더링되는가?

---

## 배포하기

### 1. 배포용 폴더 구성

```
Jaego_v1.0/
├── Jaego/                     # dist/Jaego 폴더 복사
│   ├── Jaego.exe
│   └── _internal/
├── data/                      # 빈 폴더 또는 샘플 데이터
│   └── (사용자가 CSV/Excel 추가)
└── README.txt                 # 사용 설명서
```

### 2. README.txt 예시

```
=== Jaego 약국 재고 관리 시스템 ===

[시작하기]
1. Jaego 폴더의 Jaego.exe를 실행합니다.
2. 웹 브라우저가 자동으로 열립니다.
3. 최초 실행 시 "DB 초기화" 버튼을 클릭합니다.

[데이터 준비]
- data/ 폴더에 월별 재고 파일을 넣어주세요.
- 지원 형식: CSV, XLS, XLSX
- 파일명 예시: 2024-01.csv, 202402.xlsx

[문의]
이메일: example@email.com
```

### 3. 압축 및 배포

```bash
# zip으로 압축
# Windows: 우클릭 → 압축(zip)
# 또는 명령줄:
powershell Compress-Archive -Path Jaego_v1.0 -DestinationPath Jaego_v1.0.zip
```

---

## 문제 해결

### 1. ModuleNotFoundError: No module named 'xxx'

**원인**: PyInstaller가 해당 모듈을 자동 감지하지 못함

**해결**: spec 파일의 `hiddenimports`에 추가

```python
hiddenimports=[
    'xxx',  # 누락된 모듈 추가
],
```

### 2. 템플릿을 찾을 수 없음 (TemplateNotFound)

**원인**: templates 폴더가 번들에 포함되지 않았거나 경로가 잘못됨

**해결**:
1. spec 파일의 `datas`에 templates 포함 확인
2. Flask 앱에서 template_folder 경로 확인

```python
app = Flask(__name__, template_folder=TEMPLATE_PATH)
```

### 3. DB 파일이 생성되지 않음

**원인**: 경로가 임시 폴더(_MEIPASS)를 가리키고 있음

**해결**: DB 경로를 exe 파일 위치(BASE_PATH)로 설정

```python
DB_PATH = os.path.join(get_base_path(), 'recent_inventory.sqlite3')
```

### 4. 빌드 크기가 너무 큼

**원인**: 불필요한 라이브러리가 포함됨

**해결**: spec 파일의 `excludes`에 불필요한 모듈 추가

```python
excludes=[
    'tkinter',
    'matplotlib',
    'PIL',
    'pytest',
],
```

### 5. 콘솔 창을 숨기고 싶음

**해결**: spec 파일에서 `console=False` 설정

```python
exe = EXE(
    ...
    console=False,  # 콘솔 창 숨김
    ...
)
```

> **주의**: 개발/테스트 중에는 `console=True`로 두어 오류 메시지를 확인하세요.

### 6. Windows Defender가 exe를 차단함

**원인**: 서명되지 않은 exe 파일은 의심스러운 파일로 간주될 수 있음

**해결**:
- Windows Defender에서 예외 추가
- 또는 코드 서명 인증서 구매 후 서명 (배포용)

---

## 참고 자료

- [PyInstaller 공식 문서](https://pyinstaller.org/en/stable/)
- [PyInstaller GitHub](https://github.com/pyinstaller/pyinstaller)
- [Flask + PyInstaller 가이드](https://pyinstaller.org/en/stable/usage.html#using-spec-files)
