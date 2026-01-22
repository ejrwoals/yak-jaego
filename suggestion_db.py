#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
suggestion_db.py
약품 제안 건너뛰기 기록 관리 SQLite DB 모듈

사용자가 "건너뛰기"한 약품의 횟수 및 시간 기록
"""

import os
import sqlite3
from datetime import datetime

import paths


DB_PATH = paths.get_db_path('suggestion_skips.sqlite3')
TABLE_NAME = 'suggestion_skips'


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
                건너뛰기_횟수 INTEGER DEFAULT 1,
                마지막_건너뛰기일시 TEXT
            )
        ''')

        # 건너뛰기 횟수 인덱스
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_skip_count ON {TABLE_NAME}(건너뛰기_횟수)')

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"suggestion_skips DB 초기화 실패: {e}")
        return False


def db_exists():
    """DB 파일 존재 여부 확인"""
    return os.path.exists(DB_PATH)


def add_skip(약품코드):
    """
    건너뛰기 기록 추가 (횟수 증가)

    Args:
        약품코드 (str): 약품 코드

    Returns:
        dict: {'success': bool, 'message': str, 'skip_count': int}
    """
    if not db_exists():
        init_db()

    try:
        conn = get_connection()
        cursor = conn.cursor()

        약품코드 = str(약품코드)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 기존 기록 확인
        cursor.execute(f'''
            SELECT 건너뛰기_횟수 FROM {TABLE_NAME}
            WHERE 약품코드 = ?
        ''', (약품코드,))

        row = cursor.fetchone()

        if row:
            # 횟수 증가
            new_count = row[0] + 1
            cursor.execute(f'''
                UPDATE {TABLE_NAME}
                SET 건너뛰기_횟수 = ?, 마지막_건너뛰기일시 = ?
                WHERE 약품코드 = ?
            ''', (new_count, now, 약품코드))
        else:
            # 새 기록 생성
            new_count = 1
            cursor.execute(f'''
                INSERT INTO {TABLE_NAME} (약품코드, 건너뛰기_횟수, 마지막_건너뛰기일시)
                VALUES (?, ?, ?)
            ''', (약품코드, new_count, now))

        conn.commit()
        conn.close()

        return {
            'success': True,
            'message': f'건너뛰기 기록됨 ({new_count}회)',
            'skip_count': new_count
        }

    except Exception as e:
        print(f"건너뛰기 기록 실패: {e}")
        return {'success': False, 'message': str(e), 'skip_count': 0}


def get_skip_count(약품코드):
    """
    건너뛰기 횟수 조회

    Args:
        약품코드 (str): 약품 코드

    Returns:
        int: 건너뛰기 횟수 (없으면 0)
    """
    if not db_exists():
        return 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 건너뛰기_횟수 FROM {TABLE_NAME}
            WHERE 약품코드 = ?
        ''', (str(약품코드),))

        row = cursor.fetchone()
        conn.close()

        return row[0] if row else 0

    except Exception as e:
        print(f"건너뛰기 횟수 조회 실패: {e}")
        return 0


def get_all_skips():
    """
    전체 건너뛰기 횟수 딕셔너리 반환

    Returns:
        dict: {약품코드: 건너뛰기_횟수, ...}
    """
    if not db_exists():
        init_db()
        return {}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 약품코드, 건너뛰기_횟수 FROM {TABLE_NAME}
        ''')

        result = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        return result

    except Exception as e:
        print(f"전체 건너뛰기 조회 실패: {e}")
        return {}


def reset_skip(약품코드):
    """
    건너뛰기 기록 초기화 (환자 등록 시 호출)

    Args:
        약품코드 (str): 약품 코드

    Returns:
        dict: {'success': bool, 'message': str}
    """
    if not db_exists():
        return {'success': True, 'message': '초기화할 기록이 없습니다.'}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            DELETE FROM {TABLE_NAME}
            WHERE 약품코드 = ?
        ''', (str(약품코드),))

        conn.commit()
        conn.close()

        return {'success': True, 'message': '건너뛰기 기록이 초기화되었습니다.'}

    except Exception as e:
        print(f"건너뛰기 초기화 실패: {e}")
        return {'success': False, 'message': str(e)}


def get_skipped_drug_codes():
    """
    건너뛰기 기록이 있는 약품 코드 목록 반환

    Returns:
        list[str]: 약품 코드 목록
    """
    if not db_exists():
        return []

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 약품코드 FROM {TABLE_NAME}
            ORDER BY 건너뛰기_횟수 DESC
        ''')

        drugs = [row[0] for row in cursor.fetchall()]
        conn.close()

        return drugs

    except Exception as e:
        print(f"건너뛴 약품 목록 조회 실패: {e}")
        return []


def get_count():
    """전체 건너뛰기 기록 수 반환"""
    if not db_exists():
        return 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'SELECT COUNT(*) FROM {TABLE_NAME}')
        count = cursor.fetchone()[0]
        conn.close()

        return count

    except Exception as e:
        print(f"기록 수 조회 실패: {e}")
        return 0


def clear_all():
    """모든 건너뛰기 기록 삭제"""
    if not db_exists():
        return {'success': True, 'message': '삭제할 기록이 없습니다.'}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'DELETE FROM {TABLE_NAME}')

        count = cursor.rowcount
        conn.commit()
        conn.close()

        return {'success': True, 'message': f'{count}개의 기록이 삭제되었습니다.', 'count': count}

    except Exception as e:
        print(f"기록 삭제 실패: {e}")
        return {'success': False, 'message': str(e)}


# 모듈 로드 시 DB 초기화
init_db()


if __name__ == '__main__':
    # 테스트 코드
    print("=== suggestion_db 테스트 ===")

    # DB 초기화 확인
    print(f"DB 존재: {db_exists()}")

    # 건너뛰기 추가
    result = add_skip('TEST001')
    print(f"건너뛰기 1회: {result}")

    result = add_skip('TEST001')
    print(f"건너뛰기 2회: {result}")

    result = add_skip('TEST002')
    print(f"다른 약품 건너뛰기: {result}")

    # 횟수 조회
    count = get_skip_count('TEST001')
    print(f"TEST001 건너뛰기 횟수: {count}")

    # 전체 조회
    all_skips = get_all_skips()
    print(f"전체 건너뛰기: {all_skips}")

    # 초기화
    result = reset_skip('TEST001')
    print(f"TEST001 초기화: {result}")

    # 확인
    count = get_skip_count('TEST001')
    print(f"초기화 후 횟수: {count}")

    # 정리
    result = clear_all()
    print(f"전체 삭제: {result}")

    print("=== 테스트 완료 ===")
