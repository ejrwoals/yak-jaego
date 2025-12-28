#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patients_db.py
환자 정보 관리 SQLite DB 모듈

약품과 환자 간의 연결을 위한 환자 정보 저장소
"""

import os
import sqlite3
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(__file__), 'patients.sqlite3')
TABLE_NAME = 'patients'


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
                환자ID INTEGER PRIMARY KEY AUTOINCREMENT,
                환자명 TEXT NOT NULL,
                주민번호_앞자리 TEXT,
                메모 TEXT,
                생성일시 TEXT,
                수정일시 TEXT
            )
        ''')

        # 환자명 + 주민번호 앞자리 조합으로 중복 방지 인덱스
        cursor.execute(f'''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_patient_unique
            ON {TABLE_NAME}(환자명, 주민번호_앞자리)
        ''')

        # 검색용 인덱스
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_patient_name ON {TABLE_NAME}(환자명)')

        # 기존 테이블에 방문주기_일 컬럼이 없으면 추가 (마이그레이션)
        cursor.execute(f"PRAGMA table_info({TABLE_NAME})")
        columns = [col[1] for col in cursor.fetchall()]
        if '방문주기_일' not in columns:
            cursor.execute(f'ALTER TABLE {TABLE_NAME} ADD COLUMN 방문주기_일 INTEGER')

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"patients DB 초기화 실패: {e}")
        return False


def db_exists():
    """DB 파일 존재 여부 확인"""
    return os.path.exists(DB_PATH)


def get_patient(환자ID):
    """
    단일 환자 조회

    Args:
        환자ID (int): 환자 ID

    Returns:
        dict: 환자 정보 (없으면 None)
    """
    if not db_exists():
        init_db()
        return None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 환자ID, 환자명, 주민번호_앞자리, 메모, 생성일시, 수정일시, 방문주기_일
            FROM {TABLE_NAME} WHERE 환자ID = ?
        ''', (환자ID,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                '환자ID': row[0],
                '환자명': row[1],
                '주민번호_앞자리': row[2],
                '메모': row[3],
                '생성일시': row[4],
                '수정일시': row[5],
                '방문주기_일': row[6]
            }
        return None
    except Exception as e:
        print(f"환자 조회 실패: {e}")
        return None


def get_all_patients():
    """
    전체 환자 목록 조회

    Returns:
        list: [{'환자ID': int, '환자명': str, ...}, ...]
    """
    if not db_exists():
        init_db()
        return []

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 환자ID, 환자명, 주민번호_앞자리, 메모, 생성일시, 수정일시, 방문주기_일
            FROM {TABLE_NAME}
            ORDER BY 환자명 ASC
        ''')

        patients = [
            {
                '환자ID': row[0],
                '환자명': row[1],
                '주민번호_앞자리': row[2],
                '메모': row[3],
                '생성일시': row[4],
                '수정일시': row[5],
                '방문주기_일': row[6]
            }
            for row in cursor.fetchall()
        ]
        conn.close()

        return patients
    except Exception as e:
        print(f"전체 환자 조회 실패: {e}")
        return []


def search_patients(keyword, limit=20):
    """
    환자 검색 (환자명으로 검색)

    Args:
        keyword (str): 검색어
        limit (int): 최대 반환 개수

    Returns:
        list: 검색 결과 리스트
    """
    if not db_exists():
        init_db()
        return []

    if not keyword or len(keyword) < 1:
        return []

    try:
        conn = get_connection()
        cursor = conn.cursor()

        search_pattern = f'%{keyword}%'
        cursor.execute(f'''
            SELECT 환자ID, 환자명, 주민번호_앞자리, 메모, 생성일시, 수정일시, 방문주기_일
            FROM {TABLE_NAME}
            WHERE 환자명 LIKE ?
            ORDER BY 환자명 ASC
            LIMIT ?
        ''', (search_pattern, limit))

        patients = [
            {
                '환자ID': row[0],
                '환자명': row[1],
                '주민번호_앞자리': row[2],
                '메모': row[3],
                '생성일시': row[4],
                '수정일시': row[5],
                '방문주기_일': row[6]
            }
            for row in cursor.fetchall()
        ]
        conn.close()

        return patients
    except Exception as e:
        print(f"환자 검색 실패: {e}")
        return []


def upsert_patient(환자명, 주민번호_앞자리=None, 메모=None, 환자ID=None, 방문주기_일=None):
    """
    환자 생성/수정

    Args:
        환자명 (str): 환자 이름 (필수)
        주민번호_앞자리 (str): 주민번호 앞 6자리 (선택)
        메모 (str): 환자 메모 (선택)
        환자ID (int): 수정 시 환자 ID (없으면 새로 생성)
        방문주기_일 (int): 환자의 평균 방문 주기 (일 단위, 선택)

    Returns:
        dict: {'success': bool, 'message': str, 'patient_id': int, 'action': 'create'|'update'}
    """
    if not db_exists():
        init_db()

    if not 환자명 or not 환자명.strip():
        return {'success': False, 'message': '환자명은 필수입니다.', 'patient_id': None, 'action': None}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        환자명 = 환자명.strip()
        주민번호_앞자리 = 주민번호_앞자리.strip() if 주민번호_앞자리 else None
        메모 = 메모.strip() if 메모 else None
        방문주기_일 = int(방문주기_일) if 방문주기_일 else None
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if 환자ID:
            # UPDATE
            cursor.execute(f'''
                UPDATE {TABLE_NAME}
                SET 환자명 = ?, 주민번호_앞자리 = ?, 메모 = ?, 방문주기_일 = ?, 수정일시 = ?
                WHERE 환자ID = ?
            ''', (환자명, 주민번호_앞자리, 메모, 방문주기_일, now, 환자ID))

            if cursor.rowcount > 0:
                conn.commit()
                conn.close()
                return {'success': True, 'message': f'{환자명} 환자 정보가 수정되었습니다.', 'patient_id': 환자ID, 'action': 'update'}
            else:
                conn.close()
                return {'success': False, 'message': '해당 환자를 찾을 수 없습니다.', 'patient_id': None, 'action': None}
        else:
            # INSERT
            cursor.execute(f'''
                INSERT INTO {TABLE_NAME} (환자명, 주민번호_앞자리, 메모, 방문주기_일, 생성일시, 수정일시)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (환자명, 주민번호_앞자리, 메모, 방문주기_일, now, now))

            patient_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return {'success': True, 'message': f'{환자명} 환자가 등록되었습니다.', 'patient_id': patient_id, 'action': 'create'}

    except sqlite3.IntegrityError:
        return {'success': False, 'message': '동일한 환자명과 주민번호 앞자리 조합이 이미 존재합니다.', 'patient_id': None, 'action': None}
    except Exception as e:
        print(f"환자 저장 실패: {e}")
        return {'success': False, 'message': str(e), 'patient_id': None, 'action': None}


def delete_patient(환자ID):
    """
    환자 삭제 (CASCADE: 연결된 약품 매핑도 함께 삭제)

    Args:
        환자ID (int): 환자 ID

    Returns:
        dict: {'success': bool, 'message': str}
    """
    if not db_exists():
        return {'success': True, 'message': '삭제할 환자가 없습니다.'}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 먼저 약품-환자 매핑 삭제 (CASCADE 효과)
        try:
            # drug_patient_map_db가 있으면 매핑 삭제
            import drug_patient_map_db
            drug_patient_map_db.unlink_all_for_patient(환자ID)
        except ImportError:
            pass  # 아직 모듈이 없는 경우 무시

        # 환자 삭제
        cursor.execute(f'DELETE FROM {TABLE_NAME} WHERE 환자ID = ?', (환자ID,))

        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            return {'success': True, 'message': '환자가 삭제되었습니다.'}
        else:
            conn.close()
            return {'success': False, 'message': '해당 환자를 찾을 수 없습니다.'}

    except Exception as e:
        print(f"환자 삭제 실패: {e}")
        return {'success': False, 'message': str(e)}


def get_patient_count():
    """
    전체 환자 수 조회

    Returns:
        int: 환자 수
    """
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
        print(f"환자 수 조회 실패: {e}")
        return 0


def get_patient_by_name_and_birth(환자명, 주민번호_앞자리):
    """
    환자명과 주민번호 앞자리로 환자 조회

    Args:
        환자명 (str): 환자 이름
        주민번호_앞자리 (str): 주민번호 앞 6자리

    Returns:
        dict: 환자 정보 (없으면 None)
    """
    if not db_exists():
        init_db()
        return None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 환자ID, 환자명, 주민번호_앞자리, 메모, 생성일시, 수정일시, 방문주기_일
            FROM {TABLE_NAME}
            WHERE 환자명 = ? AND (주민번호_앞자리 = ? OR (주민번호_앞자리 IS NULL AND ? IS NULL))
        ''', (환자명, 주민번호_앞자리, 주민번호_앞자리))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                '환자ID': row[0],
                '환자명': row[1],
                '주민번호_앞자리': row[2],
                '메모': row[3],
                '생성일시': row[4],
                '수정일시': row[5],
                '방문주기_일': row[6]
            }
        return None
    except Exception as e:
        print(f"환자 조회 실패: {e}")
        return None


# 모듈 로드 시 DB 초기화
init_db()


if __name__ == '__main__':
    # 테스트 코드
    print("=== patients_db 테스트 ===")

    # DB 초기화 확인
    print(f"DB 존재: {db_exists()}")

    # 테스트 환자 추가
    result = upsert_patient('홍길동', '900101', '테스트 환자입니다.')
    print(f"추가 결과: {result}")

    # 조회
    if result['patient_id']:
        patient = get_patient(result['patient_id'])
        print(f"조회 결과: {patient}")

    # 검색
    search_result = search_patients('홍')
    print(f"검색 결과: {search_result}")

    # 전체 조회
    all_patients = get_all_patients()
    print(f"전체 환자: {all_patients}")

    # 개수
    count = get_patient_count()
    print(f"환자 수: {count}")

    # 삭제
    if result['patient_id']:
        del_result = delete_patient(result['patient_id'])
        print(f"삭제 결과: {del_result}")

    print("=== 테스트 완료 ===")
