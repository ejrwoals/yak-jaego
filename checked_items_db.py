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

import paths


DB_PATH = paths.get_db_path('checked_items.sqlite3')


def init_checked_items_db():
    """
    체크된 아이템을 저장할 DB 초기화

    테이블 스키마:
    - 약품코드: 약품의 고유 식별자 (PRIMARY KEY)
    - 체크여부: 체크 상태 (1: 체크됨, 0: 체크 안됨)
    - 체크일시: 마지막 체크/언체크 날짜 및 시간
    - 메모: 사용자가 작성한 메모 (선택사항)
    - 처리상태: 대기중/처리중/완료/보류
    - 처리유형: 반품/폐기/사용자 정의
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 기존 checked_items 테이블 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='checked_items'")
    has_checked_items = cursor.fetchone() is not None

    if has_checked_items:
        # 기존 스키마 확인
        cursor.execute("PRAGMA table_info(checked_items)")
        columns = {col[1] for col in cursor.fetchall()}

        if '체크여부' not in columns:
            # 구 스키마 (카테고리 기반) → 새 테이블로 마이그레이션
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS checked_items_new (
                    약품코드 TEXT PRIMARY KEY,
                    체크여부 INTEGER DEFAULT 0,
                    체크일시 TEXT,
                    메모 TEXT DEFAULT '',
                    처리상태 TEXT DEFAULT '대기중',
                    처리유형 TEXT DEFAULT ''
                )
            ''')
            cursor.execute('''
                INSERT OR IGNORE INTO checked_items_new (약품코드, 체크여부, 체크일시, 메모)
                SELECT 약품코드, 1, 체크일시, 메모 FROM checked_items
            ''')
            cursor.execute('DROP TABLE checked_items')
            cursor.execute('ALTER TABLE checked_items_new RENAME TO checked_items')
        else:
            # 새 스키마: 누락된 컬럼만 추가 (데이터 보존)
            if '처리상태' not in columns:
                cursor.execute("ALTER TABLE checked_items ADD COLUMN 처리상태 TEXT DEFAULT '대기중'")
            if '처리유형' not in columns:
                cursor.execute("ALTER TABLE checked_items ADD COLUMN 처리유형 TEXT DEFAULT ''")
    else:
        # 테이블이 없음 — 잔존 _v2 테이블이 있으면 정리
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='checked_items_v2'")
        if cursor.fetchone():
            cursor.execute('ALTER TABLE checked_items_v2 RENAME TO checked_items')
            # 누락 컬럼 추가
            cursor.execute("PRAGMA table_info(checked_items)")
            columns = {col[1] for col in cursor.fetchall()}
            if '처리유형' not in columns:
                cursor.execute("ALTER TABLE checked_items ADD COLUMN 처리유형 TEXT DEFAULT ''")
        else:
            # 완전히 새로 생성
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS checked_items (
                    약품코드 TEXT PRIMARY KEY,
                    체크여부 INTEGER DEFAULT 0,
                    체크일시 TEXT,
                    메모 TEXT DEFAULT '',
                    처리상태 TEXT DEFAULT '대기중',
                    처리유형 TEXT DEFAULT ''
                )
            ''')

    # 처리유형 마스터 테이블 생성
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processing_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            유형명 TEXT UNIQUE NOT NULL,
            순서 INTEGER DEFAULT 0,
            is_default INTEGER DEFAULT 0
        )
    ''')

    # 기본 처리유형 삽입 (없으면)
    cursor.execute("SELECT COUNT(*) FROM processing_types")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            'INSERT OR IGNORE INTO processing_types (유형명, 순서, is_default) VALUES (?, ?, ?)',
            [('반품', 0, 1), ('폐기', 1, 1)]
        )

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

    # 기존 메모, 처리상태, 처리유형 유지
    cursor.execute('SELECT 메모, 처리상태, 처리유형 FROM checked_items WHERE 약품코드 = ?', (drug_code,))
    result = cursor.fetchone()
    existing_memo = result[0] if result else ''
    existing_status = result[1] if result else '대기중'
    existing_type = result[2] if result else ''

    cursor.execute('''
        INSERT OR REPLACE INTO checked_items (약품코드, 체크여부, 체크일시, 메모, 처리상태, 처리유형)
        VALUES (?, 1, ?, ?, ?, ?)
    ''', (drug_code, now, existing_memo, existing_status, existing_type))

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


def get_checked_items_with_status():
    """
    체크된 약품코드와 처리상태를 함께 반환

    Returns:
        dict: {약품코드: 처리상태} (체크여부=1인 것만)
    """
    if not os.path.exists(DB_PATH):
        return {}

    init_checked_items_db()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT 약품코드, 처리상태 FROM checked_items WHERE 체크여부 = 1')

    result = {row[0]: (row[1] or '대기중') for row in cursor.fetchall()}

    conn.close()
    return result


def get_trash_items():
    """
    휴지통 약품 전체 목록 반환 (처리상태, 처리유형 포함)

    Returns:
        list[dict]: [{약품코드, 체크일시, 처리상태, 처리유형}, ...]
    """
    if not os.path.exists(DB_PATH):
        return []

    init_checked_items_db()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT 약품코드, 체크일시, 처리상태, 처리유형
        FROM checked_items WHERE 체크여부 = 1
        ORDER BY 체크일시 DESC
    ''')

    items = []
    for row in cursor.fetchall():
        items.append({
            '약품코드': row[0],
            '체크일시': row[1],
            '처리상태': row[2] or '대기중',
            '처리유형': row[3] or ''
        })

    conn.close()
    return items


def update_process_status(drug_code, status):
    """처리상태 변경"""
    if not os.path.exists(DB_PATH):
        return False

    init_checked_items_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        UPDATE checked_items SET 처리상태 = ?, 체크일시 = ?
        WHERE 약품코드 = ? AND 체크여부 = 1
    ''', (status, now, drug_code))

    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def update_process_type(drug_code, type_name):
    """처리유형 변경"""
    if not os.path.exists(DB_PATH):
        return False

    init_checked_items_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE checked_items SET 처리유형 = ?
        WHERE 약품코드 = ? AND 체크여부 = 1
    ''', (type_name, drug_code))

    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def get_processing_types():
    """등록된 처리유형 목록 반환"""
    if not os.path.exists(DB_PATH):
        return [{'유형명': '반품', 'is_default': True}, {'유형명': '폐기', 'is_default': True}]

    init_checked_items_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT 유형명, is_default FROM processing_types ORDER BY 순서')
    types = [{'유형명': row[0], 'is_default': bool(row[1])} for row in cursor.fetchall()]

    conn.close()
    return types


def add_processing_type(name):
    """커스텀 처리유형 추가"""
    init_checked_items_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 최대 순서값 + 1
    cursor.execute('SELECT MAX(순서) FROM processing_types')
    max_order = cursor.fetchone()[0] or 0

    try:
        cursor.execute(
            'INSERT INTO processing_types (유형명, 순서, is_default) VALUES (?, ?, 0)',
            (name, max_order + 1)
        )
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False

    conn.close()
    return success


def remove_processing_type(name):
    """커스텀 처리유형 삭제 (기본 유형은 삭제 불가)"""
    if not os.path.exists(DB_PATH):
        return False

    init_checked_items_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('DELETE FROM processing_types WHERE 유형명 = ? AND is_default = 0', (name,))
    deleted = cursor.rowcount > 0

    if deleted:
        # 해당 유형을 사용 중인 약품의 처리유형을 비움
        cursor.execute("UPDATE checked_items SET 처리유형 = '' WHERE 처리유형 = ?", (name,))

    conn.commit()
    conn.close()
    return deleted


def update_memo(drug_code, category_or_memo, memo=None):
    """
    약품의 메모 업데이트 (통합 메모 DB로 위임)

    Args:
        drug_code (str): 약품코드
        category_or_memo: 메모 내용 또는 카테고리 (하위 호환성)
        memo (str, optional): 메모 내용 (category_or_memo가 카테고리인 경우)
    """
    import drug_memos_db

    # 하위 호환성: update_memo(drug_code, category, memo) 형태로 호출된 경우
    if memo is not None:
        actual_memo = memo
    else:
        actual_memo = category_or_memo

    # 통합 메모 DB 사용
    if actual_memo:
        drug_memos_db.upsert_memo(drug_code, actual_memo)
    else:
        drug_memos_db.delete_memo(drug_code)


def get_memo(drug_code, category=None):
    """
    약품의 메모 조회 (통합 메모 DB로 위임)

    Args:
        drug_code (str): 약품코드
        category: 무시됨 (하위 호환성 유지용)

    Returns:
        str: 메모 내용 (없으면 빈 문자열)
    """
    import drug_memos_db
    return drug_memos_db.get_memo(drug_code)


def get_all_memos(category=None):
    """
    모든 메모 조회 (통합 메모 DB로 위임)

    Args:
        category: 무시됨 (하위 호환성 유지용)

    Returns:
        dict: {약품코드: 메모내용}
    """
    import drug_memos_db
    return drug_memos_db.get_all_memos()


if __name__ == '__main__':
    # 테스트용
    init_checked_items_db()
    print("✅ checked_items.sqlite3 DB 생성/마이그레이션 완료")
