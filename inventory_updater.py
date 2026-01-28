"""
재고 업데이트 모듈

today.csv, today.xls, today.xlsx 파일을 이용하여 recent_inventory.sqlite3 데이터베이스를 업데이트합니다.
"""

import pandas as pd
import os
import sys
import inventory_db
import drug_timeseries_db
from utils import normalize_drug_codes_in_df, validate_columns, read_today_file


def update_inventory_from_today_csv(today_csv_path='today.csv'):
    """
    today.csv/xls/xlsx를 읽어서 recent_inventory.sqlite3를 업데이트

    파일명이 'today.csv'로 지정되어 있어도 today.xls, today.xlsx도 자동으로 인식합니다.
    절대 경로가 주어지면 해당 파일을 직접 읽습니다.

    Args:
        today_csv_path (str): today 파일 경로 (확장자 포함/미포함 모두 가능) 또는 절대 경로

    Returns:
        dict: 업데이트 결과 {'updated': int, 'inserted': int, 'failed': int}
    """
    print(f"\n=== today 파일로 재고 업데이트 ===")

    # 1. today 파일 읽기 (CSV, XLS, XLSX 자동 감지)
    # 절대 경로인 경우 그대로 전달, 아니면 base_name만 추출
    if os.path.isabs(today_csv_path):
        path_to_use = today_csv_path
    else:
        # 확장자가 있는 경우 제거하여 base_name만 추출
        path_to_use = os.path.splitext(today_csv_path)[0]

    df, filepath = read_today_file(path_to_use)

    if df is None:
        print(f"⚠️  today 파일을 찾을 수 없습니다. 업데이트를 건너뜁니다.")
        return None

    print(f"   총 {len(df)}개 행 로드")

    # 2. 필수 컬럼 확인
    print("\n📋 컬럼 검증 중...")
    required_columns = ['약품코드', '약품명', '제약회사', '재고수량']
    is_valid, missing = validate_columns(df, required_columns, os.path.basename(filepath))

    if not is_valid:
        print(f"\n💡 해결 방법:")
        print(f"   1. today 파일에 다음 컬럼이 있는지 확인: {required_columns}")
        print(f"   2. 컬럼명의 철자와 띄어쓰기가 정확한지 확인")
        print(f"\n현재 파일의 컬럼:")
        print(f"   {list(df.columns)}")
        return None

    # 3. 약품코드 정규화
    print("\n🔧 약품코드 정규화 중...")
    df = normalize_drug_codes_in_df(df, code_column='약품코드')

    # 4. 컬럼명 통일 (재고수량 → 현재_재고수량)
    df_update = df[['약품코드', '약품명', '제약회사', '재고수량']].copy()
    df_update.rename(columns={'재고수량': '현재_재고수량'}, inplace=True)

    # 5. 재고수량 데이터 정제 (숫자로 변환)
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

    # 6. DB에 UPSERT
    print("\n💾 데이터베이스 업데이트 중...")
    result = inventory_db.upsert_inventory(df_update, show_summary=True)

    # 7. drug_timeseries DB의 약품명/제약회사도 동기화
    if drug_timeseries_db.db_exists():
        drug_timeseries_db.update_drug_names(df_update, show_summary=True)

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
        print("\n💡 이제 python web_app.py를 실행하여 보고서를 생성할 수 있습니다.")
    else:
        print("\n⚠️  재고 업데이트를 수행하지 않았습니다.")


if __name__ == '__main__':
    main()
