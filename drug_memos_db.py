#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
drug_memos_db.py
통합 메모 관리 SQLite DB 모듈

inventory_reports와 order_calc_reports에서 공통으로 사용하는 메모 저장소
"""

import os
import sqlite3
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(__file__), 'drug_memos.sqlite3')
TABLE_NAME = 'drug_memos'


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
                메모 TEXT,
                작성일시 TEXT,
                수정일시 TEXT
            )
        ''')

        # 인덱스 생성
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_memo_drug_code ON {TABLE_NAME}(약품코드)')

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"drug_memos DB 초기화 실패: {e}")
        return False


def db_exists():
    """DB 파일 존재 여부 확인"""
    return os.path.exists(DB_PATH)


def get_memo(약품코드):
    """
    단일 약품의 메모 조회

    Args:
        약품코드 (str): 약품 코드

    Returns:
        str: 메모 내용 (없으면 빈 문자열)
    """
    if not db_exists():
        init_db()
        return ''

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'SELECT 메모 FROM {TABLE_NAME} WHERE 약품코드 = ?', (str(약품코드),))
        row = cursor.fetchone()
        conn.close()

        return row[0] if row and row[0] else ''
    except Exception as e:
        print(f"메모 조회 실패: {e}")
        return ''


def get_all_memos():
    """
    전체 메모 조회

    Returns:
        dict: {약품코드: 메모내용}
    """
    if not db_exists():
        init_db()
        return {}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 약품코드, 메모 FROM {TABLE_NAME}
            WHERE 메모 IS NOT NULL AND 메모 != ''
        ''')

        memos = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        return memos
    except Exception as e:
        print(f"전체 메모 조회 실패: {e}")
        return {}


def get_all_memos_with_details():
    """
    전체 메모 목록을 수정일시 내림차순으로 반환 (메모 관리 페이지용)

    Returns:
        list: [{'약품코드': str, '메모': str, '작성일시': str, '수정일시': str}, ...]
    """
    if not db_exists():
        init_db()
        return []

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 약품코드, 메모, 작성일시, 수정일시 FROM {TABLE_NAME}
            WHERE 메모 IS NOT NULL AND 메모 != ''
            ORDER BY 수정일시 DESC
        ''')

        memos = [
            {
                '약품코드': row[0],
                '메모': row[1],
                '작성일시': row[2],
                '수정일시': row[3]
            }
            for row in cursor.fetchall()
        ]
        conn.close()

        return memos
    except Exception as e:
        print(f"메모 상세 목록 조회 실패: {e}")
        return []


def get_memos_for_codes(약품코드_리스트):
    """
    여러 약품의 메모 조회 (성능 최적화용)

    Args:
        약품코드_리스트 (list): 약품코드 리스트

    Returns:
        dict: {약품코드: 메모내용}
    """
    if not 약품코드_리스트:
        return {}

    if not db_exists():
        init_db()
        return {}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        placeholders = ','.join(['?' for _ in 약품코드_리스트])
        cursor.execute(f'''
            SELECT 약품코드, 메모 FROM {TABLE_NAME}
            WHERE 약품코드 IN ({placeholders})
            AND 메모 IS NOT NULL AND 메모 != ''
        ''', [str(code) for code in 약품코드_리스트])

        memos = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        return memos
    except Exception as e:
        print(f"메모 일괄 조회 실패: {e}")
        return {}


def upsert_memo(약품코드, 메모):
    """
    메모 생성/수정

    Args:
        약품코드 (str): 약품 코드
        메모 (str): 메모 내용

    Returns:
        dict: {'success': bool, 'message': str, 'action': 'create'|'update'}
    """
    if not db_exists():
        init_db()

    try:
        conn = get_connection()
        cursor = conn.cursor()

        약품코드 = str(약품코드)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 기존 데이터 확인
        cursor.execute(f'SELECT 약품코드 FROM {TABLE_NAME} WHERE 약품코드 = ?', (약품코드,))
        existing = cursor.fetchone()

        if existing:
            # UPDATE
            cursor.execute(f'''
                UPDATE {TABLE_NAME}
                SET 메모 = ?, 수정일시 = ?
                WHERE 약품코드 = ?
            ''', (메모, now, 약품코드))
            action = 'update'
            message = f'{약품코드} 메모가 수정되었습니다.'
        else:
            # INSERT
            cursor.execute(f'''
                INSERT INTO {TABLE_NAME} (약품코드, 메모, 작성일시, 수정일시)
                VALUES (?, ?, ?, ?)
            ''', (약품코드, 메모, now, now))
            action = 'create'
            message = f'{약품코드} 메모가 저장되었습니다.'

        conn.commit()
        conn.close()

        return {'success': True, 'message': message, 'action': action}

    except Exception as e:
        print(f"메모 저장 실패: {e}")
        return {'success': False, 'message': str(e), 'action': None}


def delete_memo(약품코드):
    """
    메모 삭제

    Args:
        약품코드 (str): 약품 코드

    Returns:
        dict: {'success': bool, 'message': str}
    """
    if not db_exists():
        return {'success': True, 'message': '삭제할 메모가 없습니다.'}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        약품코드 = str(약품코드)

        cursor.execute(f'DELETE FROM {TABLE_NAME} WHERE 약품코드 = ?', (약품코드,))

        conn.commit()
        conn.close()

        return {'success': True, 'message': f'{약품코드} 메모가 삭제되었습니다.'}

    except Exception as e:
        print(f"메모 삭제 실패: {e}")
        return {'success': False, 'message': str(e)}


def has_memo(약품코드):
    """
    메모 존재 여부 확인

    Args:
        약품코드 (str): 약품 코드

    Returns:
        bool: 메모가 있으면 True
    """
    memo = get_memo(약품코드)
    return bool(memo)


def get_memo_count():
    """
    메모가 있는 약품 수 조회

    Returns:
        int: 메모가 있는 약품 수
    """
    if not db_exists():
        return 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT COUNT(*) FROM {TABLE_NAME}
            WHERE 메모 IS NOT NULL AND 메모 != ''
        ''')

        count = cursor.fetchone()[0]
        conn.close()

        return count
    except Exception as e:
        print(f"메모 개수 조회 실패: {e}")
        return 0


# 모듈 로드 시 DB 초기화
init_db()


if __name__ == '__main__':
    # 테스트 코드
    print("=== drug_memos_db 테스트 ===")

    # DB 초기화 확인
    print(f"DB 존재: {db_exists()}")

    # 테스트 데이터 추가
    result = upsert_memo('TEST001', '테스트 메모입니다.')
    print(f"추가 결과: {result}")

    # 조회
    memo = get_memo('TEST001')
    print(f"조회 결과: {memo}")

    # 수정
    result = upsert_memo('TEST001', '수정된 메모입니다.')
    print(f"수정 결과: {result}")

    # 전체 조회
    all_memos = get_all_memos()
    print(f"전체 메모: {all_memos}")

    # 개수
    count = get_memo_count()
    print(f"메모 개수: {count}")

    # 삭제
    result = delete_memo('TEST001')
    print(f"삭제 결과: {result}")

    print("=== 테스트 완료 ===")
