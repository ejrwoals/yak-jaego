# -*- mode: python ; coding: utf-8 -*-

"""
Jaego PyInstaller Spec 파일

빌드 명령: pyinstaller jaego.spec

Windows에서 빌드 시:
    1. 프로젝트 폴더에서 명령 프롬프트/PowerShell 열기
    2. 가상환경 활성화 (선택): .venv\Scripts\activate
    3. pyinstaller jaego.spec 실행
    4. dist/Jaego/ 폴더에 결과물 생성
"""

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# pandas, numpy 등의 숨겨진 모듈 수집
hidden_imports = [
    # Flask 관련
    'flask',
    'jinja2',
    'werkzeug',
    'werkzeug.serving',
    'werkzeug.debug',

    # 데이터 처리
    'pandas',
    'numpy',
    'scipy',
    'scipy.spatial',
    'scipy.spatial.distance',
    'scipy.signal',
    'scipy.stats',

    # Excel 파일 처리
    'openpyxl',
    'xlrd',

    # 날짜 처리
    'dateutil',
    'dateutil.relativedelta',

    # 기타
    'sqlite3',
    'json',
    'csv',

    # 로컬 모듈
    'paths',
    'read_csv',
    'inventory_db',
    'drug_timeseries_db',
    'checked_items_db',
    'drug_memos_db',
    'drug_patient_map_db',
    'patients_db',
    'suggestion_db',
    'drug_flags_db',
    'drug_thresholds_db',
    'drug_periodicity_db',
    'periodicity_calculator',
    'suggestion_engine',
    'buffer_calculator',
    'inventory_updater',
    'utils',
    'generate_single_ma_report',
    'generate_volatility_report',
    'drug_order_calculator',
]

a = Analysis(
    ['web_app.py'],  # 메인 스크립트
    pathex=[],
    binaries=[],
    datas=[
        # (소스 경로, 번들 내 경로)
        ('templates', 'templates'),  # HTML 템플릿 포함
        ('static', 'static'),        # CSS, JS 등 정적 파일 포함

        # 주의: 아래 항목들은 포함하지 않음 (사용자 데이터)
        # - data/ 폴더: 월별 CSV/Excel 파일
        # - *.sqlite3: 데이터베이스 파일
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 불필요한 모듈 제외 (빌드 크기 감소)
        'tkinter',
        'matplotlib',
        'PIL',
        'IPython',
        'notebook',
        'pytest',
        'sphinx',
    ],
    noarchive=False,
    optimize=0,
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
    console=False,  # True: 콘솔 창 표시 (디버깅용), False: 숨김 (배포용)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',  # 아이콘 파일 (선택사항, Windows용)
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
