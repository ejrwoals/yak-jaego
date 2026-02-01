#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
user_settings_db.py
사용자 설정 SQLite DB 모듈

앱 전역 설정값 저장소
"""

import os
import sqlite3
from datetime import datetime

import paths


DB_PATH = paths.get_db_path('user_settings.sqlite3')
TABLE_NAME = 'user_settings'

# 기본값 정의
DEFAULT_SETTINGS = {
    'ma_months': 3,           # 이동평균 개월 수 (1-12)
    'threshold_low': 1,       # 런웨이 부족/충분 경계 (1-23)
    'threshold_high': 3,      # 런웨이 충분/과다 경계 (2-24)
    'runway_threshold': 1.0   # 강조 표시 기준 런웨이 (0.5-6)
}


def get_connection():
    """데이터베이스 연결 반환"""
    conn = sqlite3.connect(DB_PATH)
    return conn


def init_db():
    """데이터베이스 및 테이블 초기화"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                수정일시 TEXT
            )
        ''')

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"user_settings DB 초기화 실패: {e}")
        return False


def db_exists():
    """DB 파일 존재 여부 확인"""
    return os.path.exists(DB_PATH)


def get_setting(key):
    """
    개별 설정값 조회 (없으면 기본값 반환)

    Args:
        key (str): 설정 키

    Returns:
        설정값 (타입은 기본값에 따름)
    """
    if not db_exists():
        init_db()
        return DEFAULT_SETTINGS.get(key)

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT value FROM {TABLE_NAME}
            WHERE key = ?
        ''', (key,))
        row = cursor.fetchone()
        conn.close()

        if row:
            # 기본값의 타입에 맞게 변환
            default_value = DEFAULT_SETTINGS.get(key)
            if isinstance(default_value, int):
                return int(row[0])
            elif isinstance(default_value, float):
                return float(row[0])
            return row[0]

        return DEFAULT_SETTINGS.get(key)
    except Exception as e:
        print(f"설정 조회 실패: {e}")
        return DEFAULT_SETTINGS.get(key)


def get_all_settings():
    """
    모든 설정을 딕셔너리로 반환

    Returns:
        dict: 모든 설정값 (없는 키는 기본값 사용)
    """
    result = DEFAULT_SETTINGS.copy()

    if not db_exists():
        init_db()
        return result

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'SELECT key, value FROM {TABLE_NAME}')
        rows = cursor.fetchall()
        conn.close()

        for key, value in rows:
            if key in DEFAULT_SETTINGS:
                # 기본값의 타입에 맞게 변환
                default_value = DEFAULT_SETTINGS[key]
                if isinstance(default_value, int):
                    result[key] = int(value)
                elif isinstance(default_value, float):
                    result[key] = float(value)
                else:
                    result[key] = value

        return result
    except Exception as e:
        print(f"전체 설정 조회 실패: {e}")
        return result


def set_setting(key, value):
    """
    개별 설정값 저장 (UPSERT 패턴)

    Args:
        key (str): 설정 키
        value: 설정값

    Returns:
        dict: {'success': bool, 'message': str}
    """
    if not db_exists():
        init_db()

    try:
        conn = get_connection()
        cursor = conn.cursor()

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute(f'''
            INSERT INTO {TABLE_NAME} (key, value, 수정일시)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                수정일시 = excluded.수정일시
        ''', (key, str(value), now))

        conn.commit()
        conn.close()

        return {'success': True, 'message': f'{key} 설정이 저장되었습니다.'}

    except Exception as e:
        print(f"설정 저장 실패: {e}")
        return {'success': False, 'message': str(e)}


def set_all_settings(settings_dict):
    """
    여러 설정을 한번에 저장

    Args:
        settings_dict (dict): {key: value, ...}

    Returns:
        dict: {'success': bool, 'message': str}
    """
    if not db_exists():
        init_db()

    try:
        conn = get_connection()
        cursor = conn.cursor()

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for key, value in settings_dict.items():
            if key in DEFAULT_SETTINGS:
                cursor.execute(f'''
                    INSERT INTO {TABLE_NAME} (key, value, 수정일시)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        수정일시 = excluded.수정일시
                ''', (key, str(value), now))

        conn.commit()
        conn.close()

        return {'success': True, 'message': '설정이 저장되었습니다.'}

    except Exception as e:
        print(f"설정 저장 실패: {e}")
        return {'success': False, 'message': str(e)}


def reset_to_defaults():
    """
    모든 설정을 기본값으로 초기화

    Returns:
        dict: {'success': bool, 'message': str, 'settings': dict}
    """
    if not db_exists():
        init_db()

    try:
        conn = get_connection()
        cursor = conn.cursor()

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for key, value in DEFAULT_SETTINGS.items():
            cursor.execute(f'''
                INSERT INTO {TABLE_NAME} (key, value, 수정일시)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    수정일시 = excluded.수정일시
            ''', (key, str(value), now))

        conn.commit()
        conn.close()

        return {
            'success': True,
            'message': '기본값으로 복원되었습니다.',
            'settings': DEFAULT_SETTINGS.copy()
        }

    except Exception as e:
        print(f"기본값 복원 실패: {e}")
        return {'success': False, 'message': str(e)}


def delete_setting(key):
    """
    설정 삭제 (이후 조회 시 기본값 반환)

    Args:
        key (str): 설정 키

    Returns:
        dict: {'success': bool, 'message': str}
    """
    if not db_exists():
        return {'success': True, 'message': '삭제할 설정이 없습니다.'}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'DELETE FROM {TABLE_NAME} WHERE key = ?', (key,))

        conn.commit()
        conn.close()

        return {'success': True, 'message': '설정이 삭제되었습니다.'}

    except Exception as e:
        print(f"설정 삭제 실패: {e}")
        return {'success': False, 'message': str(e)}


# 모듈 로드 시 DB 초기화
init_db()


if __name__ == '__main__':
    # 테스트 코드
    print("=== user_settings_db 테스트 ===")

    # DB 초기화 확인
    print(f"DB 존재: {db_exists()}")

    # 기본 설정 조회
    all_settings = get_all_settings()
    print(f"전체 설정: {all_settings}")

    # 개별 설정 조회
    ma_months = get_setting('ma_months')
    print(f"이동평균 개월 수: {ma_months} (타입: {type(ma_months).__name__})")

    # 설정 변경
    result = set_setting('ma_months', 6)
    print(f"설정 변경 결과: {result}")

    # 변경 확인
    ma_months = get_setting('ma_months')
    print(f"변경된 이동평균 개월 수: {ma_months}")

    # 여러 설정 변경
    result = set_all_settings({
        'ma_months': 4,
        'threshold_low': 2,
        'threshold_high': 5,
        'runway_threshold': 1.5
    })
    print(f"여러 설정 변경 결과: {result}")

    # 변경 확인
    all_settings = get_all_settings()
    print(f"변경된 전체 설정: {all_settings}")

    # 기본값 복원
    result = reset_to_defaults()
    print(f"기본값 복원 결과: {result}")

    # 복원 확인
    all_settings = get_all_settings()
    print(f"복원된 전체 설정: {all_settings}")

    print("=== 테스트 완료 ===")
