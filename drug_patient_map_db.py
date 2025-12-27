#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
drug_patient_map_db.py
약품-환자 매핑 관리 SQLite DB 모듈

약품과 환자 간의 Many-to-Many 관계 저장소
"""

import os
import sqlite3
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(__file__), 'drug_patient_map.sqlite3')
TABLE_NAME = 'drug_patient_map'


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
                약품코드 TEXT NOT NULL,
                환자ID INTEGER NOT NULL,
                생성일시 TEXT,
                PRIMARY KEY (약품코드, 환자ID)
            )
        ''')

        # 약품코드 기준 인덱스
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_map_drug ON {TABLE_NAME}(약품코드)')

        # 환자ID 기준 인덱스
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_map_patient ON {TABLE_NAME}(환자ID)')

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"drug_patient_map DB 초기화 실패: {e}")
        return False


def db_exists():
    """DB 파일 존재 여부 확인"""
    return os.path.exists(DB_PATH)


def get_patients_for_drug(약품코드):
    """
    특정 약품에 연결된 환자 목록 조회

    Args:
        약품코드 (str): 약품 코드

    Returns:
        list: [{'환자ID': int, '환자명': str, '주민번호_앞자리': str, ...}, ...]
    """
    if not db_exists():
        init_db()
        return []

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # patients 테이블과 조인하여 환자 정보도 함께 조회
        cursor.execute(f'''
            SELECT m.환자ID, m.생성일시
            FROM {TABLE_NAME} m
            WHERE m.약품코드 = ?
            ORDER BY m.생성일시 DESC
        ''', (str(약품코드),))

        mappings = cursor.fetchall()
        conn.close()

        # patients_db에서 환자 정보 가져오기
        result = []
        try:
            import patients_db
            for mapping in mappings:
                patient = patients_db.get_patient(mapping[0])
                if patient:
                    patient['연결일시'] = mapping[1]
                    result.append(patient)
        except ImportError:
            # patients_db 모듈이 없는 경우 ID만 반환
            result = [{'환자ID': m[0], '연결일시': m[1]} for m in mappings]

        return result
    except Exception as e:
        print(f"약품-환자 매핑 조회 실패: {e}")
        return []


def get_drugs_for_patient(환자ID):
    """
    특정 환자에 연결된 약품 목록 조회

    Args:
        환자ID (int): 환자 ID

    Returns:
        list: [{'약품코드': str, '생성일시': str}, ...]
    """
    if not db_exists():
        init_db()
        return []

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 약품코드, 생성일시
            FROM {TABLE_NAME}
            WHERE 환자ID = ?
            ORDER BY 생성일시 DESC
        ''', (환자ID,))

        drugs = [
            {'약품코드': row[0], '연결일시': row[1]}
            for row in cursor.fetchall()
        ]
        conn.close()

        return drugs
    except Exception as e:
        print(f"환자-약품 매핑 조회 실패: {e}")
        return []


def link_patient(약품코드, 환자ID):
    """
    약품과 환자 연결

    Args:
        약품코드 (str): 약품 코드
        환자ID (int): 환자 ID

    Returns:
        dict: {'success': bool, 'message': str}
    """
    if not db_exists():
        init_db()

    try:
        conn = get_connection()
        cursor = conn.cursor()

        약품코드 = str(약품코드)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 이미 연결되어 있는지 확인
        cursor.execute(f'''
            SELECT 1 FROM {TABLE_NAME}
            WHERE 약품코드 = ? AND 환자ID = ?
        ''', (약품코드, 환자ID))

        if cursor.fetchone():
            conn.close()
            return {'success': False, 'message': '이미 연결되어 있습니다.'}

        # 연결 추가
        cursor.execute(f'''
            INSERT INTO {TABLE_NAME} (약품코드, 환자ID, 생성일시)
            VALUES (?, ?, ?)
        ''', (약품코드, 환자ID, now))

        conn.commit()
        conn.close()

        return {'success': True, 'message': '환자가 연결되었습니다.'}

    except Exception as e:
        print(f"약품-환자 연결 실패: {e}")
        return {'success': False, 'message': str(e)}


def unlink_patient(약품코드, 환자ID):
    """
    약품과 환자 연결 해제

    Args:
        약품코드 (str): 약품 코드
        환자ID (int): 환자 ID

    Returns:
        dict: {'success': bool, 'message': str}
    """
    if not db_exists():
        return {'success': True, 'message': '연결이 존재하지 않습니다.'}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        약품코드 = str(약품코드)

        cursor.execute(f'''
            DELETE FROM {TABLE_NAME}
            WHERE 약품코드 = ? AND 환자ID = ?
        ''', (약품코드, 환자ID))

        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            return {'success': True, 'message': '연결이 해제되었습니다.'}
        else:
            conn.close()
            return {'success': False, 'message': '해당 연결을 찾을 수 없습니다.'}

    except Exception as e:
        print(f"약품-환자 연결 해제 실패: {e}")
        return {'success': False, 'message': str(e)}


def unlink_all_for_drug(약품코드):
    """
    특정 약품의 모든 환자 연결 해제

    Args:
        약품코드 (str): 약품 코드

    Returns:
        dict: {'success': bool, 'message': str, 'count': int}
    """
    if not db_exists():
        return {'success': True, 'message': '연결이 없습니다.', 'count': 0}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        약품코드 = str(약품코드)

        cursor.execute(f'DELETE FROM {TABLE_NAME} WHERE 약품코드 = ?', (약품코드,))

        count = cursor.rowcount
        conn.commit()
        conn.close()

        return {'success': True, 'message': f'{count}개의 연결이 해제되었습니다.', 'count': count}

    except Exception as e:
        print(f"약품-환자 전체 연결 해제 실패: {e}")
        return {'success': False, 'message': str(e), 'count': 0}


def unlink_all_for_patient(환자ID):
    """
    특정 환자의 모든 약품 연결 해제 (환자 삭제 시 CASCADE 용)

    Args:
        환자ID (int): 환자 ID

    Returns:
        dict: {'success': bool, 'message': str, 'count': int}
    """
    if not db_exists():
        return {'success': True, 'message': '연결이 없습니다.', 'count': 0}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'DELETE FROM {TABLE_NAME} WHERE 환자ID = ?', (환자ID,))

        count = cursor.rowcount
        conn.commit()
        conn.close()

        return {'success': True, 'message': f'{count}개의 연결이 해제되었습니다.', 'count': count}

    except Exception as e:
        print(f"환자-약품 전체 연결 해제 실패: {e}")
        return {'success': False, 'message': str(e), 'count': 0}


def set_patients_for_drug(약품코드, 환자ID_리스트):
    """
    약품의 환자 연결을 전체 교체

    Args:
        약품코드 (str): 약품 코드
        환자ID_리스트 (list): 연결할 환자 ID 리스트

    Returns:
        dict: {'success': bool, 'message': str}
    """
    if not db_exists():
        init_db()

    try:
        conn = get_connection()
        cursor = conn.cursor()

        약품코드 = str(약품코드)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 기존 연결 모두 삭제
        cursor.execute(f'DELETE FROM {TABLE_NAME} WHERE 약품코드 = ?', (약품코드,))

        # 새 연결 추가
        for 환자ID in 환자ID_리스트:
            cursor.execute(f'''
                INSERT INTO {TABLE_NAME} (약품코드, 환자ID, 생성일시)
                VALUES (?, ?, ?)
            ''', (약품코드, 환자ID, now))

        conn.commit()
        conn.close()

        return {'success': True, 'message': f'{len(환자ID_리스트)}명의 환자가 연결되었습니다.'}

    except Exception as e:
        print(f"약품-환자 연결 설정 실패: {e}")
        return {'success': False, 'message': str(e)}


def get_all_drugs_with_patients():
    """
    환자가 연결된 모든 약품코드 목록 조회

    Returns:
        list: [약품코드, ...]
    """
    if not db_exists():
        init_db()
        return []

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'SELECT DISTINCT 약품코드 FROM {TABLE_NAME}')

        drugs = [row[0] for row in cursor.fetchall()]
        conn.close()

        return drugs
    except Exception as e:
        print(f"환자 연결 약품 목록 조회 실패: {e}")
        return []


def get_patient_count_for_drug(약품코드):
    """
    특정 약품에 연결된 환자 수 조회

    Args:
        약품코드 (str): 약품 코드

    Returns:
        int: 환자 수
    """
    if not db_exists():
        return 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT COUNT(*) FROM {TABLE_NAME}
            WHERE 약품코드 = ?
        ''', (str(약품코드),))

        count = cursor.fetchone()[0]
        conn.close()

        return count
    except Exception as e:
        print(f"환자 수 조회 실패: {e}")
        return 0


def get_all_mappings_dict():
    """
    전체 매핑을 딕셔너리로 반환 (약품코드 → 환자ID 리스트)

    Returns:
        dict: {약품코드: [환자ID, ...], ...}
    """
    if not db_exists():
        init_db()
        return {}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'SELECT 약품코드, 환자ID FROM {TABLE_NAME}')

        result = {}
        for row in cursor.fetchall():
            약품코드 = row[0]
            환자ID = row[1]
            if 약품코드 not in result:
                result[약품코드] = []
            result[약품코드].append(환자ID)

        conn.close()

        return result
    except Exception as e:
        print(f"전체 매핑 조회 실패: {e}")
        return {}


# 모듈 로드 시 DB 초기화
init_db()


if __name__ == '__main__':
    # 테스트 코드
    print("=== drug_patient_map_db 테스트 ===")

    # DB 초기화 확인
    print(f"DB 존재: {db_exists()}")

    # 테스트 연결 추가
    result = link_patient('TEST001', 1)
    print(f"연결 추가 결과: {result}")

    result = link_patient('TEST001', 2)
    print(f"연결 추가 결과: {result}")

    # 약품에 연결된 환자 조회
    patients = get_patients_for_drug('TEST001')
    print(f"약품 환자 목록: {patients}")

    # 환자에 연결된 약품 조회
    drugs = get_drugs_for_patient(1)
    print(f"환자 약품 목록: {drugs}")

    # 환자 수
    count = get_patient_count_for_drug('TEST001')
    print(f"환자 수: {count}")

    # 연결 해제
    result = unlink_patient('TEST001', 1)
    print(f"연결 해제 결과: {result}")

    # 전체 연결 해제
    result = unlink_all_for_drug('TEST001')
    print(f"전체 연결 해제 결과: {result}")

    print("=== 테스트 완료 ===")
