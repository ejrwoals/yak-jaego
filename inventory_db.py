"""
재고 데이터베이스 관리 모듈

recent_inventory.sqlite3 데이터베이스를 관리하는 전담 모듈입니다.
가장 최신의 재고 현황을 SQLite DB에 저장하고 관리합니다.
"""

import sqlite3
import pandas as pd
from datetime import datetime
import os


DB_PATH = 'recent_inventory.sqlite3'
TABLE_NAME = 'recent_inventory'


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

        # 테이블 생성
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                약품코드 TEXT PRIMARY KEY,
                약품명 TEXT,
                제약회사 TEXT,
                약품유형 TEXT,
                현재_재고수량 REAL,
                최종_업데이트일시 TEXT
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

        conn.commit()
        conn.close()

        print(f"✅ 데이터베이스 초기화 완료: {DB_PATH}")
        return True

    except Exception as e:
        print(f"❌ 데이터베이스 초기화 실패: {e}")
        return False


def get_inventory(약품코드=None):
    """
    재고 조회

    Args:
        약품코드 (str, optional): 특정 약품코드. None이면 전체 조회

    Returns:
        list of dict or dict: 재고 정보
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        if 약품코드:
            cursor.execute(f'''
                SELECT * FROM {TABLE_NAME}
                WHERE 약품코드 = ?
            ''', (약품코드,))
            row = cursor.fetchone()
            conn.close()

            if row:
                return {
                    '약품코드': row[0],
                    '약품명': row[1],
                    '제약회사': row[2],
                    '약품유형': row[3],
                    '현재_재고수량': row[4],
                    '최종_업데이트일시': row[5]
                }
            return None
        else:
            cursor.execute(f'SELECT * FROM {TABLE_NAME}')
            rows = cursor.fetchall()
            conn.close()

            result = []
            for row in rows:
                result.append({
                    '약품코드': row[0],
                    '약품명': row[1],
                    '제약회사': row[2],
                    '약품유형': row[3],
                    '현재_재고수량': row[4],
                    '최종_업데이트일시': row[5]
                })
            return result

    except Exception as e:
        print(f"❌ 재고 조회 실패: {e}")
        return None


def get_all_inventory_as_df():
    """
    전체 재고를 DataFrame으로 반환

    Returns:
        pd.DataFrame: 재고 데이터프레임
    """
    try:
        conn = get_connection()
        df = pd.read_sql_query(f'SELECT * FROM {TABLE_NAME}', conn)
        conn.close()
        return df

    except Exception as e:
        print(f"❌ 재고 DataFrame 조회 실패: {e}")
        return pd.DataFrame()


def upsert_inventory(df, show_summary=True):
    """
    재고 INSERT 또는 UPDATE (UPSERT)

    Args:
        df (pd.DataFrame): 재고 데이터 (필수 컬럼: 약품코드, 약품명, 제약회사, 재고수량 or 현재_재고수량)
        show_summary (bool): 결과 요약 출력 여부

    Returns:
        dict: 업데이트 결과 {'updated': int, 'inserted': int, 'failed': int}
    """
    try:
        # 컬럼명 정규화
        df = df.copy()
        if '재고수량' in df.columns and '현재_재고수량' not in df.columns:
            df['현재_재고수량'] = df['재고수량']

        # 필수 컬럼 확인
        required_cols = ['약품코드', '약품명', '제약회사', '현재_재고수량']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"필수 컬럼 누락: {missing_cols}")

        # 약품유형이 없으면 "미분류"로 설정
        if '약품유형' not in df.columns:
            df['약품유형'] = '미분류'

        # 현재 시각
        update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        df['최종_업데이트일시'] = update_time

        conn = get_connection()
        cursor = conn.cursor()

        # 기존 약품코드 조회
        cursor.execute(f'SELECT 약품코드 FROM {TABLE_NAME}')
        existing_codes = set(row[0] for row in cursor.fetchall())

        updated = 0
        inserted = 0
        failed = 0

        # UPSERT 수행
        for _, row in df.iterrows():
            try:
                약품코드 = str(row['약품코드'])
                약품명 = row['약품명']
                제약회사 = row['제약회사']
                약품유형 = row.get('약품유형', '미분류')
                현재_재고수량 = float(row['현재_재고수량']) if pd.notna(row['현재_재고수량']) else 0.0

                cursor.execute(f'''
                    INSERT OR REPLACE INTO {TABLE_NAME}
                    (약품코드, 약품명, 제약회사, 약품유형, 현재_재고수량, 최종_업데이트일시)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (약품코드, 약품명, 제약회사, 약품유형, 현재_재고수량, update_time))

                if 약품코드 in existing_codes:
                    updated += 1
                else:
                    inserted += 1

            except Exception as e:
                failed += 1
                print(f"⚠️  행 처리 실패 (약품코드: {row.get('약품코드', 'N/A')}): {e}")

        conn.commit()
        conn.close()

        result = {
            'updated': updated,
            'inserted': inserted,
            'failed': failed
        }

        if show_summary:
            print(f"\n📊 재고 업데이트 결과:")
            print(f"   - 업데이트: {updated}건")
            print(f"   - 신규 추가: {inserted}건")
            if failed > 0:
                print(f"   - 실패: {failed}건")

        return result

    except Exception as e:
        print(f"❌ 재고 UPSERT 실패: {e}")
        return {'updated': 0, 'inserted': 0, 'failed': 0}


def get_inventory_count():
    """
    현재 DB에 저장된 총 품목 수 반환

    Returns:
        int: 품목 수
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f'SELECT COUNT(*) FROM {TABLE_NAME}')
        count = cursor.fetchone()[0]
        conn.close()
        return count

    except Exception as e:
        print(f"❌ 품목 수 조회 실패: {e}")
        return 0


def db_exists():
    """
    데이터베이스 파일 존재 여부 확인

    Returns:
        bool: 존재 여부
    """
    return os.path.exists(DB_PATH)


def update_single_inventory(약품코드, 재고수량):
    """
    단일 약품의 재고수량만 업데이트

    Args:
        약품코드 (str): 업데이트할 약품의 코드
        재고수량 (float): 새로운 재고수량 (음수 허용)

    Returns:
        dict: {
            'success': bool,
            'message': str,
            'previous_stock': float (성공 시),
            'new_stock': float (성공 시)
        }
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 기존 데이터 확인
        cursor.execute(f'''
            SELECT 현재_재고수량 FROM {TABLE_NAME}
            WHERE 약품코드 = ?
        ''', (str(약품코드),))

        row = cursor.fetchone()
        if not row:
            conn.close()
            return {'success': False, 'message': '해당 약품을 찾을 수 없습니다.'}

        previous_stock = row[0]
        update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 재고수량 업데이트
        cursor.execute(f'''
            UPDATE {TABLE_NAME}
            SET 현재_재고수량 = ?, 최종_업데이트일시 = ?
            WHERE 약품코드 = ?
        ''', (float(재고수량), update_time, str(약품코드)))

        conn.commit()
        conn.close()

        return {
            'success': True,
            'message': '재고가 성공적으로 업데이트되었습니다.',
            'previous_stock': previous_stock,
            'new_stock': float(재고수량)
        }

    except Exception as e:
        print(f"❌ 재고 업데이트 실패: {e}")
        return {'success': False, 'message': str(e)}


def search_inventory(keyword, limit=50):
    """
    약품 검색 (약품명, 약품코드, 제약회사로 검색)

    Args:
        keyword (str): 검색어
        limit (int): 최대 결과 수

    Returns:
        list of dict: 검색 결과
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        search_pattern = f'%{keyword}%'

        cursor.execute(f'''
            SELECT 약품코드, 약품명, 제약회사, 약품유형, 현재_재고수량, 최종_업데이트일시
            FROM {TABLE_NAME}
            WHERE 약품코드 LIKE ? OR 약품명 LIKE ? OR 제약회사 LIKE ?
            LIMIT ?
        ''', (search_pattern, search_pattern, search_pattern, limit))

        rows = cursor.fetchall()
        conn.close()

        result = []
        for row in rows:
            result.append({
                '약품코드': row[0],
                '약품명': row[1],
                '제약회사': row[2],
                '약품유형': row[3],
                '현재_재고수량': row[4],
                '최종_업데이트일시': row[5]
            })

        return result

    except Exception as e:
        print(f"❌ 약품 검색 실패: {e}")
        return []


if __name__ == '__main__':
    # 테스트 코드
    print("=== inventory_db.py 테스트 ===\n")

    # 1. DB 초기화
    print("1. DB 초기화 테스트")
    init_db()

    # 2. 샘플 데이터 삽입
    print("\n2. 샘플 데이터 삽입 테스트")
    sample_data = pd.DataFrame({
        '약품코드': ['A001', 'A002', 'A003'],
        '약품명': ['타이레놀', '게보린', '판피린'],
        '제약회사': ['한국존슨앤드존슨', '삼일제약', '동아제약'],
        '재고수량': [100, 50, 75]
    })
    upsert_inventory(sample_data)

    # 3. 전체 조회
    print("\n3. 전체 재고 조회 테스트")
    all_inventory = get_all_inventory_as_df()
    print(all_inventory)

    # 4. 특정 약품 조회
    print("\n4. 특정 약품 조회 테스트 (약품코드: A001)")
    single = get_inventory('A001')
    print(single)

    # 5. 품목 수 조회
    print(f"\n5. 총 품목 수: {get_inventory_count()}개")

    print("\n✅ 테스트 완료!")
