#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
checked_items_db.py
확인 완료된 약품의 체크 상태를 저장/관리하는 SQLite DB 모듈
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
    - 카테고리: '재고소진' 또는 '악성재고' (구분용)
    - 체크일시: 체크한 날짜 및 시간
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checked_items (
            약품코드 TEXT,
            카테고리 TEXT,
            체크일시 TEXT,
            PRIMARY KEY (약품코드, 카테고리)
        )
    ''')

    conn.commit()
    conn.close()
    print(f"✅ checked_items.sqlite3 초기화 완료: {DB_PATH}")


def add_checked_item(drug_code, category='재고소진'):
    """
    약품을 체크 완료 목록에 추가

    Args:
        drug_code (str): 약품코드
        category (str): '재고소진' 또는 '악성재고'
    """
    init_checked_items_db()  # DB가 없으면 생성

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute('''
        INSERT OR REPLACE INTO checked_items (약품코드, 카테고리, 체크일시)
        VALUES (?, ?, ?)
    ''', (drug_code, category, now))

    conn.commit()
    conn.close()


def remove_checked_item(drug_code, category='재고소진'):
    """
    약품을 체크 완료 목록에서 제거

    Args:
        drug_code (str): 약품코드
        category (str): '재고소진' 또는 '악성재고'
    """
    if not os.path.exists(DB_PATH):
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        DELETE FROM checked_items
        WHERE 약품코드 = ? AND 카테고리 = ?
    ''', (drug_code, category))

    conn.commit()
    conn.close()


def get_checked_items(category='재고소진'):
    """
    특정 카테고리의 체크된 약품코드 목록 반환

    Args:
        category (str): '재고소진' 또는 '악성재고'

    Returns:
        set: 체크된 약품코드들의 집합
    """
    if not os.path.exists(DB_PATH):
        return set()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT 약품코드 FROM checked_items
        WHERE 카테고리 = ?
    ''', (category,))

    checked_codes = {row[0] for row in cursor.fetchall()}

    conn.close()
    return checked_codes


def get_all_checked_items():
    """
    모든 체크된 약품의 정보 반환

    Returns:
        dict: {카테고리: set(약품코드들)}
    """
    if not os.path.exists(DB_PATH):
        return {}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT 약품코드, 카테고리 FROM checked_items')

    result = {}
    for row in cursor.fetchall():
        drug_code, category = row
        if category not in result:
            result[category] = set()
        result[category].add(drug_code)

    conn.close()
    return result


if __name__ == '__main__':
    # 테스트용
    init_checked_items_db()
    print("✅ checked_items.sqlite3 DB 생성 완료")
