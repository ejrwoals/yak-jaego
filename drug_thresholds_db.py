#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
개별 약품 임계값 관리 DB 모듈

약품별로 개별 임계값(절대 재고 / 런웨이)을 설정하고 관리하는 모듈.
글로벌 임계값과 별도로 특정 약품에 대한 맞춤 강조 표시 기준을 제공.
"""

import os
import sqlite3
import pandas as pd
from datetime import datetime


DB_PATH = 'drug_thresholds.sqlite3'
TABLE_NAME = 'drug_thresholds'
HISTORY_TABLE = 'threshold_history'


def get_connection():
    """데이터베이스 연결 반환"""
    conn = sqlite3.connect(DB_PATH)
    return conn


def init_db():
    """데이터베이스 및 테이블 초기화"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 메인 테이블: drug_thresholds
        # 메모는 v3.13부터 drug_memos.sqlite3에서 통합 관리
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                약품코드 TEXT PRIMARY KEY,
                절대재고_임계값 INTEGER DEFAULT NULL,
                런웨이_임계값 REAL DEFAULT NULL,
                활성화 INTEGER DEFAULT 1,
                생성일시 TEXT,
                수정일시 TEXT
            )
        ''')

        # 히스토리 테이블: threshold_history (감사 로그)
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                약품코드 TEXT NOT NULL,
                변경유형 TEXT NOT NULL,
                이전_절대재고 INTEGER,
                이후_절대재고 INTEGER,
                이전_런웨이 REAL,
                이후_런웨이 REAL,
                변경일시 TEXT NOT NULL
            )
        ''')

        # 인덱스 생성
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_threshold_drug_code ON {TABLE_NAME}(약품코드)')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_history_drug_code ON {HISTORY_TABLE}(약품코드)')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_history_date ON {HISTORY_TABLE}(변경일시)')

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ drug_thresholds DB 초기화 실패: {e}")
        return False


def db_exists():
    """DB 파일 존재 여부 확인"""
    return os.path.exists(DB_PATH)


def get_threshold(약품코드):
    """
    단일 약품의 임계값 조회

    Returns:
        dict | None: 설정이 있으면 딕셔너리, 없으면 None
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 약품코드, 절대재고_임계값, 런웨이_임계값, 활성화, 생성일시, 수정일시
            FROM {TABLE_NAME}
            WHERE 약품코드 = ?
        ''', (str(약품코드),))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                '약품코드': row[0],
                '절대재고_임계값': row[1],
                '런웨이_임계값': row[2],
                '활성화': bool(row[3]),
                '생성일시': row[4],
                '수정일시': row[5]
            }
        return None
    except Exception as e:
        print(f"임계값 조회 실패: {e}")
        return None


def get_all_thresholds():
    """
    전체 임계값 설정 목록 조회 (DataFrame)

    Returns:
        pd.DataFrame: 전체 설정 목록
    """
    try:
        conn = get_connection()
        df = pd.read_sql_query(f'SELECT * FROM {TABLE_NAME}', conn)
        conn.close()
        return df
    except Exception as e:
        print(f"❌ 전체 임계값 조회 실패: {e}")
        return pd.DataFrame()


def get_threshold_dict():
    """
    전체 임계값을 {약품코드: 설정} 딕셔너리로 반환 (빠른 조회용)
    환자 이름 목록도 함께 포함

    Returns:
        dict: {약품코드: {'절대재고_임계값': N, '런웨이_임계값': M, '환자목록': [...], ...}}
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 약품코드, 절대재고_임계값, 런웨이_임계값, 활성화
            FROM {TABLE_NAME}
            WHERE 활성화 = 1
        ''')

        rows = cursor.fetchall()
        conn.close()

        # 환자 정보 가져오기
        drug_patients = {}
        try:
            import drug_patient_map_db
            for row in rows:
                drug_code = row[0]
                patients = drug_patient_map_db.get_patients_for_drug(drug_code)
                drug_patients[drug_code] = [p.get('환자명', '') for p in patients if p.get('환자명')]
        except ImportError:
            pass

        result = {}
        for row in rows:
            drug_code = row[0]
            result[drug_code] = {
                '절대재고_임계값': row[1],
                '런웨이_임계값': row[2],
                '활성화': bool(row[3]),
                '환자목록': drug_patients.get(drug_code, [])
            }
        return result
    except Exception as e:
        print(f"임계값 딕셔너리 조회 실패: {e}")
        return {}


def get_threshold_count():
    """활성화된 임계값 설정 개수 조회"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f'SELECT COUNT(*) FROM {TABLE_NAME} WHERE 활성화 = 1')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print(f"❌ 임계값 개수 조회 실패: {e}")
        return 0


def _record_history(cursor, 약품코드, 변경유형, 이전_절대재고=None, 이후_절대재고=None,
                    이전_런웨이=None, 이후_런웨이=None):
    """히스토리 기록 (내부 함수)"""
    cursor.execute(f'''
        INSERT INTO {HISTORY_TABLE}
        (약품코드, 변경유형, 이전_절대재고, 이후_절대재고, 이전_런웨이, 이후_런웨이, 변경일시)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        str(약품코드),
        변경유형,
        이전_절대재고,
        이후_절대재고,
        이전_런웨이,
        이후_런웨이,
        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ))


def upsert_threshold(약품코드, 절대재고_임계값=None, 런웨이_임계값=None, 메모=None):
    """
    임계값 생성/수정 (히스토리 기록 포함)

    Args:
        약품코드: 약품 코드
        절대재고_임계값: 재고가 이 값 이하면 강조 (None이면 미사용)
        런웨이_임계값: 런웨이가 이 값 미만이면 강조 (None이면 미사용)
        메모: [DEPRECATED] 무시됨 - 통합 메모 시스템(drug_memos_db) 사용

    Returns:
        dict: {'success': bool, 'message': str, 'action': 'create'|'update'}
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        약품코드 = str(약품코드)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 기존 데이터 확인
        cursor.execute(f'SELECT 절대재고_임계값, 런웨이_임계값 FROM {TABLE_NAME} WHERE 약품코드 = ?',
                      (약품코드,))
        existing = cursor.fetchone()

        if existing:
            # UPDATE
            이전_절대재고, 이전_런웨이 = existing

            cursor.execute(f'''
                UPDATE {TABLE_NAME}
                SET 절대재고_임계값 = ?, 런웨이_임계값 = ?, 활성화 = 1, 수정일시 = ?
                WHERE 약품코드 = ?
            ''', (절대재고_임계값, 런웨이_임계값, now, 약품코드))

            _record_history(cursor, 약품코드, 'UPDATE',
                           이전_절대재고, 절대재고_임계값,
                           이전_런웨이, 런웨이_임계값)

            action = 'update'
            message = f'{약품코드} 임계값이 수정되었습니다.'
        else:
            # INSERT
            cursor.execute(f'''
                INSERT INTO {TABLE_NAME}
                (약품코드, 절대재고_임계값, 런웨이_임계값, 활성화, 생성일시, 수정일시)
                VALUES (?, ?, ?, 1, ?, ?)
            ''', (약품코드, 절대재고_임계값, 런웨이_임계값, now, now))

            _record_history(cursor, 약품코드, 'CREATE',
                           None, 절대재고_임계값,
                           None, 런웨이_임계값)

            action = 'create'
            message = f'{약품코드} 임계값이 설정되었습니다.'

        conn.commit()
        conn.close()

        return {'success': True, 'message': message, 'action': action}

    except Exception as e:
        print(f"임계값 저장 실패: {e}")
        return {'success': False, 'message': str(e), 'action': None}


def delete_threshold(약품코드):
    """
    임계값 삭제 (히스토리 기록 포함)

    Returns:
        dict: {'success': bool, 'message': str}
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        약품코드 = str(약품코드)

        # 기존 데이터 확인
        cursor.execute(f'SELECT 절대재고_임계값, 런웨이_임계값 FROM {TABLE_NAME} WHERE 약품코드 = ?',
                      (약품코드,))
        existing = cursor.fetchone()

        if not existing:
            conn.close()
            return {'success': False, 'message': f'{약품코드}에 설정된 임계값이 없습니다.'}

        이전_절대재고, 이전_런웨이 = existing

        # DELETE
        cursor.execute(f'DELETE FROM {TABLE_NAME} WHERE 약품코드 = ?', (약품코드,))

        _record_history(cursor, 약품코드, 'DELETE',
                       이전_절대재고, None,
                       이전_런웨이, None)

        conn.commit()
        conn.close()

        return {'success': True, 'message': f'{약품코드} 임계값이 삭제되었습니다.'}

    except Exception as e:
        print(f"❌ 임계값 삭제 실패: {e}")
        return {'success': False, 'message': str(e)}


def is_triggered(약품코드, 현재재고, 런웨이값, custom_thresholds=None):
    """
    개별 임계값 OR 조건 체크

    Args:
        약품코드: 약품 코드
        현재재고: 현재 재고 수량
        런웨이값: 현재 런웨이 (개월)
        custom_thresholds: 미리 로드된 임계값 딕셔너리 (성능 최적화용)

    Returns:
        dict: {
            'triggered': bool,
            'reason': str | None,  # 'stock', 'runway', 'both', None
            'threshold': dict | None  # 적용된 임계값 설정
        }
    """
    약품코드 = str(약품코드)

    # custom_thresholds가 없으면 DB에서 조회
    if custom_thresholds is None:
        threshold = get_threshold(약품코드)
        if not threshold or not threshold.get('활성화', False):
            return {'triggered': False, 'reason': None, 'threshold': None}
    else:
        if 약품코드 not in custom_thresholds:
            return {'triggered': False, 'reason': None, 'threshold': None}
        threshold = custom_thresholds[약품코드]

    stock_trigger = False
    runway_trigger = False

    # 절대 재고 임계값 체크
    if threshold.get('절대재고_임계값') is not None:
        if 현재재고 <= threshold['절대재고_임계값']:
            stock_trigger = True

    # 런웨이 임계값 체크
    if threshold.get('런웨이_임계값') is not None:
        if 런웨이값 < threshold['런웨이_임계값']:
            runway_trigger = True

    # 결과 반환
    if stock_trigger and runway_trigger:
        return {'triggered': True, 'reason': 'both', 'threshold': threshold}
    elif stock_trigger:
        return {'triggered': True, 'reason': 'stock', 'threshold': threshold}
    elif runway_trigger:
        return {'triggered': True, 'reason': 'runway', 'threshold': threshold}
    else:
        return {'triggered': False, 'reason': None, 'threshold': threshold}


def get_statistics():
    """통계 정보 조회"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'SELECT COUNT(*) FROM {TABLE_NAME}')
        total = cursor.fetchone()[0]

        cursor.execute(f'SELECT COUNT(*) FROM {TABLE_NAME} WHERE 활성화 = 1')
        active = cursor.fetchone()[0]

        cursor.execute(f'SELECT COUNT(*) FROM {TABLE_NAME} WHERE 절대재고_임계값 IS NOT NULL')
        with_stock = cursor.fetchone()[0]

        cursor.execute(f'SELECT COUNT(*) FROM {TABLE_NAME} WHERE 런웨이_임계값 IS NOT NULL')
        with_runway = cursor.fetchone()[0]

        conn.close()

        return {
            'total': total,
            'active': active,
            'with_stock_threshold': with_stock,
            'with_runway_threshold': with_runway
        }
    except Exception as e:
        print(f"❌ 통계 조회 실패: {e}")
        return {'total': 0, 'active': 0, 'with_stock_threshold': 0, 'with_runway_threshold': 0}


# 모듈 로드 시 DB 초기화
init_db()


if __name__ == '__main__':
    # 테스트 코드
    print("=== drug_thresholds_db 테스트 ===")

    # DB 초기화 확인
    print(f"DB 존재: {db_exists()}")

    # 테스트 데이터 추가
    result = upsert_threshold('TEST001', 절대재고_임계값=50, 런웨이_임계값=2.0, 메모='테스트 약품')
    print(f"추가 결과: {result}")

    # 조회
    threshold = get_threshold('TEST001')
    print(f"조회 결과: {threshold}")

    # is_triggered 테스트
    triggered = is_triggered('TEST001', 현재재고=30, 런웨이값=1.5)
    print(f"트리거 결과: {triggered}")

    # 수정
    result = upsert_threshold('TEST001', 절대재고_임계값=100, 런웨이_임계값=3.0, 메모='수정된 테스트')
    print(f"수정 결과: {result}")

    # 통계
    stats = get_statistics()
    print(f"통계: {stats}")

    # 삭제
    result = delete_threshold('TEST001')
    print(f"삭제 결과: {result}")

    print("=== 테스트 완료 ===")
