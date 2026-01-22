"""
경로 관리 모듈 (PyInstaller 빌드 지원)

PyInstaller로 빌드된 환경과 개발 환경 모두에서 올바른 경로를 제공합니다.

사용법:
    from paths import get_base_path, get_bundle_path, get_db_path

    # DB 파일 경로 (exe와 같은 위치)
    db_path = get_db_path('recent_inventory.sqlite3')

    # 데이터 폴더 경로
    data_path = get_data_path()

    # 번들 리소스 경로 (templates 등)
    template_path = get_bundle_path('templates')
"""

import sys
import os


def is_frozen():
    """PyInstaller로 빌드된 환경인지 확인"""
    return getattr(sys, 'frozen', False)


def get_base_path():
    """
    기본 경로 반환 (사용자 데이터, DB 파일 위치)

    - PyInstaller 빌드: exe 파일이 있는 폴더
    - 개발 환경: 스크립트 파일이 있는 폴더

    Returns:
        str: 기본 경로
    """
    if is_frozen():
        # PyInstaller로 빌드된 실행 파일의 디렉토리
        return os.path.dirname(sys.executable)
    else:
        # 개발 환경: 이 파일(paths.py)이 있는 디렉토리
        return os.path.dirname(os.path.abspath(__file__))


def get_bundle_path(subpath=''):
    """
    번들된 리소스 경로 반환 (templates, static 등 앱 내부 파일)

    - PyInstaller 빌드: _MEIPASS 임시 폴더 (또는 _internal)
    - 개발 환경: 스크립트 파일이 있는 폴더

    Args:
        subpath: 하위 경로 (예: 'templates')

    Returns:
        str: 번들 리소스 경로
    """
    if is_frozen():
        # PyInstaller는 번들 리소스를 _MEIPASS에 압축 해제
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    if subpath:
        return os.path.join(base, subpath)
    return base


def get_db_path(db_filename):
    """
    데이터베이스 파일 경로 반환

    DB 파일은 번들에 포함되지 않고, exe 파일과 같은 위치에 생성됩니다.

    Args:
        db_filename: DB 파일명 (예: 'recent_inventory.sqlite3')

    Returns:
        str: DB 파일 전체 경로
    """
    return os.path.join(get_base_path(), db_filename)


def get_data_path():
    """
    data 폴더 경로 반환 (월별 CSV/Excel 파일 저장 위치)

    Returns:
        str: data 폴더 경로
    """
    return os.path.join(get_base_path(), 'data')


def get_reports_path(report_type):
    """
    보고서 저장 폴더 경로 반환

    Args:
        report_type: 보고서 유형 ('inventory', 'order', 'volatility')

    Returns:
        str: 보고서 폴더 경로
    """
    folder_map = {
        'inventory': 'inventory_reports',
        'order': 'order_calc_reports',
        'volatility': 'volatility_reports'
    }
    folder_name = folder_map.get(report_type, report_type)
    return os.path.join(get_base_path(), folder_name)


def get_uploads_path():
    """
    업로드 폴더 경로 반환

    Returns:
        str: uploads 폴더 경로
    """
    return os.path.join(get_base_path(), 'uploads')


# 편의를 위한 상수들 (모듈 로드 시 한 번만 계산)
BASE_PATH = get_base_path()
BUNDLE_PATH = get_bundle_path()
DATA_PATH = get_data_path()
UPLOADS_PATH = get_uploads_path()


# 디버깅용: 현재 경로 정보 출력
if __name__ == '__main__':
    print("=" * 50)
    print("경로 정보 (PyInstaller 빌드 지원)")
    print("=" * 50)
    print(f"빌드 환경: {'PyInstaller' if is_frozen() else '개발 환경'}")
    print(f"BASE_PATH: {BASE_PATH}")
    print(f"BUNDLE_PATH: {BUNDLE_PATH}")
    print(f"DATA_PATH: {DATA_PATH}")
    print(f"UPLOADS_PATH: {UPLOADS_PATH}")
    print(f"DB 예시: {get_db_path('recent_inventory.sqlite3')}")
    print(f"템플릿: {get_bundle_path('templates')}")
    print("=" * 50)
