#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
checked_items_db.py
확인 완료된 약품의 체크 상태를 저장/관리하는 SQLite DB 모듈

v3.7 변경: 카테고리 없이 약품코드만으로 관리
- 이유: MA 기간에 따라 약품의 카테고리가 달라질 수 있음
- 약품에 대한 체크 상태와 메모는 카테고리와 무관하게 유지
"""

import sqlite3
import os
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(__file__), 'checked_items.sqlite3')


def init_checked_items_db():
    """
    체크된 아이템을 저장할 DB 초기화

    테이블 스키마:
    - 약품코드: 약품의 고유 식별자 (PRIMARY KEY)
    - 체크여부: 체크 상태 (1: 체크됨, 0: 체크 안됨)
    - 체크일시: 마지막 체크/언체크 날짜 및 시간
    - 메모: 사용자가 작성한 메모 (선택사항)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 새 스키마로 테이블 생성 (기존 테이블이 있으면 마이그레이션)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checked_items_v2 (
            약품코드 TEXT PRIMARY KEY,
            체크여부 INTEGER DEFAULT 0,
            체크일시 TEXT,
            메모 TEXT DEFAULT ''
        )
    ''')

    # 기존 테이블이 있으면 데이터 마이그레이션
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='checked_items'")
    if cursor.fetchone():
        # 기존 스키마 확인 (체크여부 컬럼이 있는지)
        cursor.execute("PRAGMA table_info(checked_items)")
        columns = {col[1] for col in cursor.fetchall()}

        if '체크여부' in columns:
            # 새 스키마: 체크여부 값을 그대로 유지
            cursor.execute('''
                INSERT OR IGNORE INTO checked_items_v2 (약품코드, 체크여부, 체크일시, 메모)
                SELECT 약품코드, 체크여부, 체크일시, 메모 FROM checked_items
            ''')
        else:
            # 구 스키마 (카테고리 기반): 체크여부 = 1로 마이그레이션
            cursor.execute('''
                INSERT OR IGNORE INTO checked_items_v2 (약품코드, 체크여부, 체크일시, 메모)
                SELECT 약품코드, 1, 체크일시, 메모 FROM checked_items
            ''')
        # 기존 테이블 삭제
        cursor.execute('DROP TABLE checked_items')

    # 테이블 이름 변경 (v2 -> checked_items)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='checked_items_v2'")
    if cursor.fetchone():
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='checked_items'")
        if not cursor.fetchone():
            cursor.execute('ALTER TABLE checked_items_v2 RENAME TO checked_items')

    conn.commit()
    conn.close()


def add_checked_item(drug_code):
    """
    약품을 체크 완료 목록에 추가

    Args:
        drug_code (str): 약품코드
    """
    init_checked_items_db()  # DB가 없으면 생성

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 기존 메모 유지
    cursor.execute('SELECT 메모 FROM checked_items WHERE 약품코드 = ?', (drug_code,))
    result = cursor.fetchone()
    existing_memo = result[0] if result else ''

    cursor.execute('''
        INSERT OR REPLACE INTO checked_items (약품코드, 체크여부, 체크일시, 메모)
        VALUES (?, 1, ?, ?)
    ''', (drug_code, now, existing_memo))

    conn.commit()
    conn.close()


def remove_checked_item(drug_code):
    """
    약품을 체크 완료 목록에서 제거 (체크 해제)

    Args:
        drug_code (str): 약품코드
    """
    if not os.path.exists(DB_PATH):
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 체크 해제 (메모는 유지)
    cursor.execute('''
        UPDATE checked_items SET 체크여부 = 0, 체크일시 = ?
        WHERE 약품코드 = ?
    ''', (now, drug_code))

    conn.commit()
    conn.close()


def get_checked_items(category=None):
    """
    체크된 약품코드 목록 반환

    Args:
        category: 무시됨 (하위 호환성 유지용)

    Returns:
        set: 체크된 약품코드들의 집합
    """
    if not os.path.exists(DB_PATH):
        return set()

    init_checked_items_db()  # 마이그레이션 확인

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT 약품코드 FROM checked_items WHERE 체크여부 = 1')

    checked_codes = {row[0] for row in cursor.fetchall()}

    conn.close()
    return checked_codes


def get_all_checked_items():
    """
    모든 체크된 약품의 정보 반환

    Returns:
        set: 체크된 약품코드들의 집합
    """
    return get_checked_items()


def update_memo(drug_code, category_or_memo, memo=None):
    """
    약품의 메모 업데이트

    Args:
        drug_code (str): 약품코드
        category_or_memo: 메모 내용 또는 카테고리 (하위 호환성)
        memo (str, optional): 메모 내용 (category_or_memo가 카테고리인 경우)
    """
    init_checked_items_db()  # DB가 없으면 생성

    # 하위 호환성: update_memo(drug_code, category, memo) 형태로 호출된 경우
    if memo is not None:
        actual_memo = memo
    else:
        actual_memo = category_or_memo

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 기존 체크 상태 유지
    cursor.execute('SELECT 체크여부 FROM checked_items WHERE 약품코드 = ?', (drug_code,))
    result = cursor.fetchone()
    checked = result[0] if result else 0

    cursor.execute('''
        INSERT OR REPLACE INTO checked_items (약품코드, 체크여부, 체크일시, 메모)
        VALUES (?, ?, ?, ?)
    ''', (drug_code, checked, now, actual_memo))

    conn.commit()
    conn.close()


def get_memo(drug_code, category=None):
    """
    약품의 메모 조회

    Args:
        drug_code (str): 약품코드
        category: 무시됨 (하위 호환성 유지용)

    Returns:
        str: 메모 내용 (없으면 빈 문자열)
    """
    if not os.path.exists(DB_PATH):
        return ''

    init_checked_items_db()  # 마이그레이션 확인

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT 메모 FROM checked_items WHERE 약품코드 = ?', (drug_code,))

    result = cursor.fetchone()
    conn.close()

    return result[0] if result and result[0] else ''


def get_all_memos(category=None):
    """
    모든 메모 조회

    Args:
        category: 무시됨 (하위 호환성 유지용)

    Returns:
        dict: {약품코드: 메모내용}
    """
    if not os.path.exists(DB_PATH):
        return {}

    init_checked_items_db()  # 마이그레이션 확인

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT 약품코드, 메모 FROM checked_items
        WHERE 메모 IS NOT NULL AND 메모 != ''
    ''')

    memos = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()
    return memos


if __name__ == '__main__':
    # 테스트용
    init_checked_items_db()
    print("✅ checked_items.sqlite3 DB 생성/마이그레이션 완료")
