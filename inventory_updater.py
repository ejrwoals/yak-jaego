"""
재고 업데이트 모듈

today.csv 파일을 이용하여 recent_inventory.sqlite3 데이터베이스를 업데이트합니다.
"""

import pandas as pd
import os
import sys
import inventory_db
from utils import normalize_drug_codes_in_df, validate_columns


def update_inventory_from_today_csv(today_csv_path='today.csv'):
    """
    today.csv를 읽어서 recent_inventory.sqlite3를 업데이트

    Args:
        today_csv_path (str): today.csv 파일 경로

    Returns:
        dict: 업데이트 결과 {'updated': int, 'inserted': int, 'failed': int}
    """
    print(f"\n=== today.csv로 재고 업데이트 ===")

    # 1. today.csv 파일 확인
    if not os.path.exists(today_csv_path):
        print(f"⚠️  {today_csv_path} 파일이 없습니다. 업데이트를 건너뜁니다.")
        return None

    # 2. today.csv 읽기
    print(f"📂 {today_csv_path} 파일 읽는 중...")
    try:
        # 여러 인코딩 시도
        df = None
        for encoding in ['utf-8', 'cp949', 'euc-kr']:
            try:
                df = pd.read_csv(today_csv_path, encoding=encoding)
                print(f"   ✅ 파일 읽기 성공 ({encoding} 인코딩)")
                break
            except:
                continue

        if df is None:
            print(f"   ❌ 파일을 읽을 수 없습니다.")
            return None

        print(f"   총 {len(df)}개 행 로드")

    except Exception as e:
        print(f"❌ 파일 읽기 실패: {e}")
        return None

    # 3. 필수 컬럼 확인
    print("\n📋 컬럼 검증 중...")
    required_columns = ['약품코드', '약품명', '제약회사', '재고수량']
    is_valid, missing = validate_columns(df, required_columns, 'today.csv')

    if not is_valid:
        print(f"\n💡 해결 방법:")
        print(f"   1. today.csv에 다음 컬럼이 있는지 확인: {required_columns}")
        print(f"   2. 컬럼명의 철자와 띄어쓰기가 정확한지 확인")
        print(f"\n현재 today.csv의 컬럼:")
        print(f"   {list(df.columns)}")
        return None

    # 4. 약품코드 정규화
    print("\n🔧 약품코드 정규화 중...")
    df = normalize_drug_codes_in_df(df, code_column='약품코드')

    # 5. 컬럼명 통일 (재고수량 → 현재_재고수량)
    df_update = df[['약품코드', '약품명', '제약회사', '재고수량']].copy()
    df_update.rename(columns={'재고수량': '현재_재고수량'}, inplace=True)

    # 6. 재고수량 데이터 정제 (숫자로 변환)
    print("🧹 재고수량 데이터 정제 중...")
    df_update['현재_재고수량'] = df_update['현재_재고수량'].astype(str).str.replace(',', '').replace('-', '0')
    df_update['현재_재고수량'] = pd.to_numeric(df_update['현재_재고수량'], errors='coerce').fillna(0)

    # NaN 값이 있는 행 제거
    original_count = len(df_update)
    df_update = df_update.dropna(subset=['약품코드', '약품명', '제약회사'])
    filtered_count = original_count - len(df_update)

    if filtered_count > 0:
        print(f"   ⚠️  필수 정보가 누락된 {filtered_count}개 행 제외")

    print(f"   ✅ {len(df_update)}개 약품 데이터 준비 완료")

    # 7. DB에 UPSERT
    print("\n💾 데이터베이스 업데이트 중...")
    result = inventory_db.upsert_inventory(df_update, show_summary=True)

    return result


def main():
    """메인 함수"""
    print("\n" + "="*50)
    print("재고 업데이트 프로그램")
    print("="*50)

    # 1. DB 존재 여부 확인
    if not inventory_db.db_exists():
        print("\n❌ recent_inventory.sqlite3가 없습니다.")
        print("💡 먼저 DB를 초기화해주세요:")
        print("   python init_db.py")
        sys.exit(1)

    print(f"\n✅ recent_inventory.sqlite3 발견")
    print(f"   현재 등록된 품목 수: {inventory_db.get_inventory_count()}개")

    # 2. today.csv로 업데이트
    result = update_inventory_from_today_csv('today.csv')

    if result:
        print("\n" + "="*50)
        print("✅ 재고 업데이트 완료!")
        print("="*50)
        print(f"\n최종 품목 수: {inventory_db.get_inventory_count()}개")
        print("\n💡 이제 python app.py를 실행하여 보고서를 생성할 수 있습니다.")
    else:
        print("\n⚠️  재고 업데이트를 수행하지 않았습니다.")


if __name__ == '__main__':
    main()
