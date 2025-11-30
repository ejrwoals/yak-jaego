"""
시계열 통계 데이터베이스 관리 모듈

processed_inventory.sqlite3 데이터베이스를 관리합니다.
월평균, 3개월 이동평균, 런웨이 등 시계열 통계 데이터를 저장합니다.
"""

import sqlite3
import pandas as pd
from datetime import datetime
import os
import json
import numpy as np


DB_PATH = 'processed_inventory.sqlite3'
TABLE_NAME = 'processed_inventory'


def convert_to_python_types(data):
    """
    numpy 타입을 Python 기본 타입으로 변환 (JSON 직렬화를 위해)

    Args:
        data: 변환할 데이터 (list, numpy 타입 등)

    Returns:
        Python 기본 타입으로 변환된 데이터
    """
    if isinstance(data, list):
        return [convert_to_python_types(item) for item in data]
    elif isinstance(data, (np.integer, np.int64, np.int32)):
        return int(data)
    elif isinstance(data, (np.floating, np.float64, np.float32)):
        return float(data)
    elif pd.isna(data):
        return None
    else:
        return data


def get_connection():
    """데이터베이스 연결 반환"""
    conn = sqlite3.connect(DB_PATH)
    return conn


def init_db():
    """
    데이터베이스 및 테이블 초기화

    Returns:
        bool: 초기화 성공 여부
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 메인 테이블 생성
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                약품코드 TEXT PRIMARY KEY,
                약품명 TEXT,
                제약회사 TEXT,
                약품유형 TEXT,
                "1년_이동평균" REAL,
                최종_재고수량 REAL,
                런웨이 TEXT,
                월별_조제수량_리스트 TEXT,
                "3개월_이동평균_리스트" TEXT,
                최종_업데이트일시 TEXT
            )
        ''')

        # 메타데이터 테이블 생성 (데이터 기간 정보 저장)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # 기존 테이블에 약품유형 컬럼이 없으면 추가 (마이그레이션)
        cursor.execute(f"PRAGMA table_info({TABLE_NAME})")
        columns = [col[1] for col in cursor.fetchall()]
        if '약품유형' not in columns:
            print("   🔄 기존 테이블에 약품유형 컬럼 추가 중...")
            cursor.execute(f'ALTER TABLE {TABLE_NAME} ADD COLUMN 약품유형 TEXT DEFAULT "미분류"')
            print("   ✅ 약품유형 컬럼 추가 완료")

        # 인덱스 생성 (성능 최적화)
        cursor.execute(f'''
            CREATE INDEX IF NOT EXISTS idx_drug_code
            ON {TABLE_NAME}(약품코드)
        ''')

        cursor.execute(f'''
            CREATE INDEX IF NOT EXISTS idx_drug_type
            ON {TABLE_NAME}(약품유형)
        ''')

        conn.commit()
        conn.close()

        print(f"✅ 데이터베이스 초기화 완료: {DB_PATH}")
        return True

    except Exception as e:
        print(f"❌ 데이터베이스 초기화 실패: {e}")
        return False


def upsert_processed_data(df, drug_type, show_summary=True):
    """
    통계 데이터 INSERT 또는 UPDATE (UPSERT)

    Args:
        df (pd.DataFrame): 통계 DataFrame (merge_by_drug_code + calculate_statistics 결과)
        drug_type (str): '전문약' 또는 '일반약'
        show_summary (bool): 결과 요약 출력 여부

    Returns:
        dict: 업데이트 결과 {'updated': int, 'inserted': int}
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 기존 약품코드 조회
        cursor.execute(f'SELECT 약품코드 FROM {TABLE_NAME}')
        existing_codes = set(row[0] for row in cursor.fetchall())

        updated = 0
        inserted = 0
        update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for _, row in df.iterrows():
            try:
                약품코드 = str(row['약품코드'])
                약품명 = row['약품명']
                제약회사 = row['제약회사']
                일년_이동평균 = float(row['1년_이동평균'])
                최종_재고수량 = float(row['최종_재고수량'])
                런웨이 = row['런웨이']

                # 리스트를 JSON 문자열로 변환 (numpy 타입을 Python 기본 타입으로 변환)
                월별_조제수량_리스트 = json.dumps(convert_to_python_types(row['월별_조제수량_리스트']))
                이동평균_리스트 = json.dumps(convert_to_python_types(row['3개월_이동평균_리스트']))

                cursor.execute(f'''
                    INSERT OR REPLACE INTO {TABLE_NAME}
                    (약품코드, 약품명, 제약회사, 약품유형, "1년_이동평균", 최종_재고수량,
                     런웨이, 월별_조제수량_리스트, "3개월_이동평균_리스트", 최종_업데이트일시)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (약품코드, 약품명, 제약회사, drug_type, 일년_이동평균, 최종_재고수량,
                      런웨이, 월별_조제수량_리스트, 이동평균_리스트, update_time))

                if 약품코드 in existing_codes:
                    updated += 1
                else:
                    inserted += 1

            except Exception as e:
                print(f"⚠️  행 처리 실패 (약품코드: {row.get('약품코드', 'N/A')}): {e}")

        conn.commit()
        conn.close()

        if show_summary:
            print(f"📊 {drug_type} 통계 데이터 저장:")
            print(f"   - 업데이트: {updated}건")
            print(f"   - 신규 추가: {inserted}건")

        return {'updated': updated, 'inserted': inserted}

    except Exception as e:
        print(f"❌ 통계 데이터 UPSERT 실패: {e}")
        return {'updated': 0, 'inserted': 0}


def get_processed_data(drug_type=None):
    """
    통계 데이터 조회

    Args:
        drug_type (str, optional): '전문약', '일반약', None(전체)

    Returns:
        pd.DataFrame: 통계 데이터프레임
    """
    try:
        conn = get_connection()

        if drug_type:
            query = f"SELECT * FROM {TABLE_NAME} WHERE 약품유형 = ?"
            df = pd.read_sql_query(query, conn, params=(drug_type,))
        else:
            query = f"SELECT * FROM {TABLE_NAME}"
            df = pd.read_sql_query(query, conn)

        conn.close()

        # JSON 문자열을 Python 리스트로 변환
        if not df.empty:
            df['월별_조제수량_리스트'] = df['월별_조제수량_리스트'].apply(json.loads)
            df['3개월_이동평균_리스트'] = df['3개월_이동평균_리스트'].apply(json.loads)

        return df

    except Exception as e:
        print(f"❌ 통계 데이터 조회 실패: {e}")
        return pd.DataFrame()


def get_statistics():
    """
    DB 통계 반환

    Returns:
        dict: {'total': int, 'by_type': {'전문약': int, '일반약': int}}
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 총 개수
        cursor.execute(f'SELECT COUNT(*) FROM {TABLE_NAME}')
        total = cursor.fetchone()[0]

        # 약품유형별 개수
        cursor.execute(f'SELECT 약품유형, COUNT(*) FROM {TABLE_NAME} GROUP BY 약품유형')
        type_counts = dict(cursor.fetchall())

        conn.close()

        return {'total': total, 'by_type': type_counts}

    except Exception as e:
        print(f"❌ 통계 조회 실패: {e}")
        return {'total': 0, 'by_type': {}}


def save_metadata(months):
    """
    데이터 기간 메타데이터를 DB에 저장

    Args:
        months (list): 월 리스트 (예: ['2023-10', '2023-11', ...])
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        if months and len(months) > 0:
            start_month = months[0]
            end_month = months[-1]
            total_months = len(months)

            cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                         ("start_month", start_month))
            cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                         ("end_month", end_month))
            cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                         ("total_months", str(total_months)))

            conn.commit()
            print(f"   📅 데이터 기간 메타데이터 저장: {start_month} ~ {end_month} ({total_months}개월)")

        conn.close()

    except Exception as e:
        print(f"⚠️  메타데이터 저장 실패: {e}")


def get_metadata():
    """
    데이터 기간 메타데이터 조회

    Returns:
        dict: {'start_month': str, 'end_month': str, 'total_months': int} 또는 None
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # metadata 테이블이 존재하는지 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'")
        if not cursor.fetchone():
            conn.close()
            return None

        cursor.execute("SELECT key, value FROM metadata WHERE key IN ('start_month', 'end_month', 'total_months')")
        rows = cursor.fetchall()

        conn.close()

        if not rows:
            return None

        metadata = dict(rows)

        if 'start_month' in metadata and 'end_month' in metadata and 'total_months' in metadata:
            return {
                'start_month': metadata['start_month'],
                'end_month': metadata['end_month'],
                'total_months': int(metadata['total_months'])
            }

        return None

    except Exception as e:
        print(f"⚠️  메타데이터 조회 실패: {e}")
        return None


def update_drug_names(df, show_summary=True):
    """
    약품명과 제약회사만 업데이트 (시계열 통계는 유지)

    recent_inventory 업데이트 시 processed_inventory의 약품명/제약회사도
    동기화하기 위해 사용합니다.

    Args:
        df (pd.DataFrame): 업데이트할 데이터 (필수 컬럼: 약품코드, 약품명, 제약회사)
        show_summary (bool): 결과 요약 출력 여부

    Returns:
        dict: 업데이트 결과 {'updated': int, 'not_found': int}
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        updated = 0
        not_found = 0

        for _, row in df.iterrows():
            약품코드 = str(row['약품코드'])
            약품명 = row['약품명']
            제약회사 = row['제약회사']

            # 해당 약품코드가 존재하는 경우에만 업데이트
            cursor.execute(f'''
                UPDATE {TABLE_NAME}
                SET 약품명 = ?, 제약회사 = ?
                WHERE 약품코드 = ?
            ''', (약품명, 제약회사, 약품코드))

            if cursor.rowcount > 0:
                updated += 1
            else:
                not_found += 1

        conn.commit()
        conn.close()

        if show_summary and updated > 0:
            print(f"📊 processed_inventory 약품명 동기화:")
            print(f"   - 업데이트: {updated}건")
            if not_found > 0:
                print(f"   - 미존재 (신규 약품): {not_found}건")

        return {'updated': updated, 'not_found': not_found}

    except Exception as e:
        print(f"❌ 약품명 업데이트 실패: {e}")
        return {'updated': 0, 'not_found': 0}


def db_exists():
    """
    데이터베이스 파일 존재 여부 확인

    Returns:
        bool: 존재 여부
    """
    return os.path.exists(DB_PATH)


def clear_db():
    """DB 파일 삭제 (초기화)"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"🗑️  {DB_PATH} 삭제 완료")


if __name__ == '__main__':
    # 테스트 코드
    print("=== processed_inventory_db.py 테스트 ===\n")

    # 1. DB 초기화
    print("1. DB 초기화 테스트")
    init_db()

    # 2. 샘플 데이터 생성
    print("\n2. 샘플 데이터 삽입 테스트")
    sample_data = pd.DataFrame({
        '약품코드': ['A001', 'A002'],
        '약품명': ['타이레놀', '게보린'],
        '제약회사': ['한국존슨앤드존슨', '삼일제약'],
        '1년_이동평균': [105.2, 52.1],
        '최종_재고수량': [500, 200],
        '런웨이': ['4.75개월', '3.84개월'],
        '월별_조제수량_리스트': [[100, 95, 105], [50, 48, 52]],
        '3개월_이동평균_리스트': [[None, None, 100], [None, None, 50]]
    })
    upsert_processed_data(sample_data, drug_type='전문약')

    # 3. 데이터 조회
    print("\n3. 데이터 조회 테스트")
    df = get_processed_data(drug_type='전문약')
    print(df[['약품코드', '약품명', '약품유형', '1년_이동평균']])

    # 4. 통계 조회
    print("\n4. 통계 조회 테스트")
    stats = get_statistics()
    print(f"   총 {stats['total']}개")
    for drug_type, count in stats['by_type'].items():
        print(f"   - {drug_type}: {count}개")

    print("\n✅ 테스트 완료!")
