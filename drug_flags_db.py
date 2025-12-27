#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
drug_flags_db.py
약품 특별관리 플래그 SQLite DB 모듈

약품별 특별관리 표시 (별표) 저장소
"""

import os
import sqlite3
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(__file__), 'drug_flags.sqlite3')
TABLE_NAME = 'drug_flags'


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
                약품코드 TEXT PRIMARY KEY,
                특별관리 INTEGER DEFAULT 0,
                수정일시 TEXT
            )
        ''')

        # 특별관리 플래그가 1인 약품만 빠르게 조회하기 위한 인덱스
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_flag_special ON {TABLE_NAME}(특별관리)')

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"drug_flags DB 초기화 실패: {e}")
        return False


def db_exists():
    """DB 파일 존재 여부 확인"""
    return os.path.exists(DB_PATH)


def get_flag(약품코드):
    """
    약품의 특별관리 플래그 조회

    Args:
        약품코드 (str): 약품 코드

    Returns:
        bool: 특별관리 여부 (기본값 False)
    """
    if not db_exists():
        init_db()
        return False

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 특별관리 FROM {TABLE_NAME}
            WHERE 약품코드 = ?
        ''', (str(약품코드),))
        row = cursor.fetchone()
        conn.close()

        return bool(row[0]) if row else False
    except Exception as e:
        print(f"플래그 조회 실패: {e}")
        return False


def set_flag(약품코드, 특별관리):
    """
    약품의 특별관리 플래그 설정

    Args:
        약품코드 (str): 약품 코드
        특별관리 (bool): 특별관리 여부

    Returns:
        dict: {'success': bool, 'message': str}
    """
    if not db_exists():
        init_db()

    try:
        conn = get_connection()
        cursor = conn.cursor()

        약품코드 = str(약품코드)
        특별관리_값 = 1 if 특별관리 else 0
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # UPSERT
        cursor.execute(f'''
            INSERT INTO {TABLE_NAME} (약품코드, 특별관리, 수정일시)
            VALUES (?, ?, ?)
            ON CONFLICT(약품코드) DO UPDATE SET
                특별관리 = excluded.특별관리,
                수정일시 = excluded.수정일시
        ''', (약품코드, 특별관리_값, now))

        conn.commit()
        conn.close()

        status = '활성화' if 특별관리 else '비활성화'
        return {'success': True, 'message': f'특별관리가 {status}되었습니다.', 'flag': 특별관리}

    except Exception as e:
        print(f"플래그 설정 실패: {e}")
        return {'success': False, 'message': str(e)}


def toggle_flag(약품코드):
    """
    약품의 특별관리 플래그 토글

    Args:
        약품코드 (str): 약품 코드

    Returns:
        dict: {'success': bool, 'message': str, 'flag': bool}
    """
    current = get_flag(약품코드)
    new_flag = not current
    result = set_flag(약품코드, new_flag)
    result['flag'] = new_flag
    return result


def get_flagged_drugs():
    """
    특별관리 플래그가 활성화된 약품 목록 조회

    Returns:
        list: [약품코드, ...]
    """
    if not db_exists():
        init_db()
        return []

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 약품코드, 수정일시 FROM {TABLE_NAME}
            WHERE 특별관리 = 1
            ORDER BY 수정일시 DESC
        ''')

        drugs = [row[0] for row in cursor.fetchall()]
        conn.close()

        return drugs
    except Exception as e:
        print(f"특별관리 약품 목록 조회 실패: {e}")
        return []


def get_all_flags():
    """
    모든 플래그를 딕셔너리로 반환

    Returns:
        dict: {약품코드: bool, ...}
    """
    if not db_exists():
        init_db()
        return {}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'SELECT 약품코드, 특별관리 FROM {TABLE_NAME}')

        flags = {row[0]: bool(row[1]) for row in cursor.fetchall()}
        conn.close()

        return flags
    except Exception as e:
        print(f"전체 플래그 조회 실패: {e}")
        return {}


def get_flagged_count():
    """
    특별관리 플래그가 활성화된 약품 수 조회

    Returns:
        int: 특별관리 약품 수
    """
    if not db_exists():
        return 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT COUNT(*) FROM {TABLE_NAME}
            WHERE 특별관리 = 1
        ''')

        count = cursor.fetchone()[0]
        conn.close()

        return count
    except Exception as e:
        print(f"특별관리 약품 수 조회 실패: {e}")
        return 0


def delete_flag(약품코드):
    """
    약품의 플래그 레코드 삭제

    Args:
        약품코드 (str): 약품 코드

    Returns:
        dict: {'success': bool, 'message': str}
    """
    if not db_exists():
        return {'success': True, 'message': '삭제할 플래그가 없습니다.'}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'DELETE FROM {TABLE_NAME} WHERE 약품코드 = ?', (str(약품코드),))

        conn.commit()
        conn.close()

        return {'success': True, 'message': '플래그가 삭제되었습니다.'}

    except Exception as e:
        print(f"플래그 삭제 실패: {e}")
        return {'success': False, 'message': str(e)}


# 모듈 로드 시 DB 초기화
init_db()


if __name__ == '__main__':
    # 테스트 코드
    print("=== drug_flags_db 테스트 ===")

    # DB 초기화 확인
    print(f"DB 존재: {db_exists()}")

    # 테스트 플래그 설정
    result = set_flag('TEST001', True)
    print(f"플래그 설정 결과: {result}")

    # 조회
    flag = get_flag('TEST001')
    print(f"플래그 조회 결과: {flag}")

    # 토글
    result = toggle_flag('TEST001')
    print(f"토글 결과: {result}")

    # 다시 조회
    flag = get_flag('TEST001')
    print(f"플래그 조회 결과: {flag}")

    # 특별관리 약품 목록
    flagged = get_flagged_drugs()
    print(f"특별관리 약품: {flagged}")

    # 전체 플래그
    all_flags = get_all_flags()
    print(f"전체 플래그: {all_flags}")

    # 개수
    count = get_flagged_count()
    print(f"특별관리 약품 수: {count}")

    # 삭제
    result = delete_flag('TEST001')
    print(f"삭제 결과: {result}")

    print("=== 테스트 완료 ===")
