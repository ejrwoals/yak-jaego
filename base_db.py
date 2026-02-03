#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
base_db.py
데이터베이스 모듈 공통 기능 제공

모든 *_db.py 모듈에서 반복되는 보일러플레이트 코드를 추상화합니다.
- get_connection()
- db_exists()
- init_db() (추상 메서드)

사용 예시:
    class MyDB(BaseDB):
        def __init__(self):
            super().__init__('my_data.sqlite3', 'my_table')

        def _create_tables(self, cursor):
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS my_table (
                    id INTEGER PRIMARY KEY,
                    name TEXT
                )
            ''')
"""

import sqlite3
import os
from abc import ABC, abstractmethod

import paths


class BaseDB(ABC):
    """
    데이터베이스 모듈의 기본 클래스

    공통 기능:
    - get_connection(): DB 연결 반환
    - db_exists(): DB 파일 존재 여부 확인
    - init_db(): DB 및 테이블 초기화 (서브클래스에서 구현)

    Attributes:
        db_name (str): 데이터베이스 파일명 (예: 'my_data.sqlite3')
        table_name (str): 주 테이블명
        db_path (str): 데이터베이스 전체 경로
    """

    def __init__(self, db_name, table_name=None):
        """
        Args:
            db_name (str): 데이터베이스 파일명 (예: 'my_data.sqlite3')
            table_name (str, optional): 주 테이블명
        """
        self.db_name = db_name
        self.table_name = table_name
        self.db_path = paths.get_db_path(db_name)

    def get_connection(self):
        """
        데이터베이스 연결 반환

        Returns:
            sqlite3.Connection: SQLite 연결 객체
        """
        return sqlite3.connect(self.db_path)

    def db_exists(self):
        """
        데이터베이스 파일 존재 여부 확인

        Returns:
            bool: DB 파일이 존재하면 True
        """
        return os.path.exists(self.db_path)

    def init_db(self):
        """
        데이터베이스 및 테이블 초기화

        Returns:
            bool: 초기화 성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # 서브클래스에서 테이블 생성 로직 구현
            self._create_tables(cursor)

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"❌ {self.db_name} 초기화 실패: {e}")
            return False

    @abstractmethod
    def _create_tables(self, cursor):
        """
        테이블 생성 SQL 실행 (서브클래스에서 구현)

        Args:
            cursor: SQLite 커서 객체
        """
        pass

    def ensure_initialized(self):
        """
        DB가 없으면 초기화, 있으면 스킵

        Returns:
            bool: 초기화 성공 여부
        """
        if not self.db_exists():
            return self.init_db()
        return True

    def execute_query(self, query, params=(), fetch_one=False, fetch_all=False):
        """
        쿼리 실행 헬퍼

        Args:
            query (str): SQL 쿼리
            params (tuple): 쿼리 파라미터
            fetch_one (bool): 단일 행 반환
            fetch_all (bool): 전체 행 반환

        Returns:
            조회 결과 또는 None
        """
        self.ensure_initialized()

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(query, params)

            if fetch_one:
                result = cursor.fetchone()
            elif fetch_all:
                result = cursor.fetchall()
            else:
                conn.commit()
                result = cursor.lastrowid

            return result

        finally:
            conn.close()

    def get_table_columns(self):
        """
        테이블의 컬럼 목록 반환

        Returns:
            list: 컬럼명 리스트
        """
        if not self.table_name:
            return []

        self.ensure_initialized()

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(f"PRAGMA table_info({self.table_name})")
        columns = [col[1] for col in cursor.fetchall()]

        conn.close()
        return columns

    def add_column_if_not_exists(self, column_name, column_type, default=None):
        """
        테이블에 컬럼이 없으면 추가 (마이그레이션용)

        Args:
            column_name (str): 추가할 컬럼명
            column_type (str): 컬럼 타입 (TEXT, INTEGER, REAL 등)
            default: 기본값

        Returns:
            bool: 컬럼 추가 여부
        """
        if not self.table_name:
            return False

        columns = self.get_table_columns()

        if column_name not in columns:
            default_clause = f" DEFAULT {default!r}" if default is not None else ""
            query = f"ALTER TABLE {self.table_name} ADD COLUMN {column_name} {column_type}{default_clause}"

            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query)
            conn.commit()
            conn.close()

            print(f"   🔄 {self.table_name}에 {column_name} 컬럼 추가됨")
            return True

        return False


# === 함수형 API 호환 헬퍼 ===
# 기존 모듈에서 점진적으로 마이그레이션할 수 있도록 함수형 헬퍼 제공

def create_db_helpers(db_name, table_name=None):
    """
    기존 함수형 API와 호환되는 헬퍼 함수들 생성

    사용 예시:
        # 기존 코드
        DB_PATH = paths.get_db_path('my_db.sqlite3')

        def get_connection():
            return sqlite3.connect(DB_PATH)

        def db_exists():
            return os.path.exists(DB_PATH)

        # 새 코드
        from base_db import create_db_helpers
        _helpers = create_db_helpers('my_db.sqlite3')
        get_connection = _helpers['get_connection']
        db_exists = _helpers['db_exists']
        DB_PATH = _helpers['db_path']

    Args:
        db_name (str): 데이터베이스 파일명
        table_name (str, optional): 테이블명

    Returns:
        dict: 헬퍼 함수들과 경로 정보
    """
    db_path = paths.get_db_path(db_name)

    def get_connection():
        return sqlite3.connect(db_path)

    def db_exists():
        return os.path.exists(db_path)

    return {
        'db_path': db_path,
        'get_connection': get_connection,
        'db_exists': db_exists,
    }
