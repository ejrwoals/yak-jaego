#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
재고 데이터베이스 초기화 스크립트 (관리자용)

다음 두 개의 데이터베이스를 생성합니다:
1. recent_inventory.sqlite3 - 최신 재고 현황
2. drug_timeseries.sqlite3 - 시계열 통계 데이터

사용법: python init_db.py
"""

import os
import sys
from read_csv import load_multiple_csv_files, merge_by_drug_code, calculate_statistics
import inventory_db
import drug_timeseries_db
import periodicity_calculator
import drug_periodicity_db
import paths


def main():
    print("=" * 60)
    print("📊 재고 데이터베이스 초기화")
    print("=" * 60)
    print()

    # 기존 DB 확인
    has_recent_db = inventory_db.db_exists()
    has_processed_db = drug_timeseries_db.db_exists()

    if has_recent_db or has_processed_db:
        print("⚠️  기존 데이터베이스가 발견되었습니다:")
        if has_recent_db:
            count = inventory_db.get_inventory_count()
            print(f"   - recent_inventory.sqlite3 (재고: {count}개)")
        if has_processed_db:
            stats = drug_timeseries_db.get_statistics()
            print(f"   - drug_timeseries.sqlite3 (통계: {stats['total']}개)")

        print()
        overwrite = input("❓ 기존 DB를 덮어쓰시겠습니까? (y/n): ").strip().lower()

        if overwrite != 'y':
            print("\n❌ 초기화를 취소했습니다.")
            sys.exit(0)

        print("\n🗑️  기존 DB 삭제 중...")
        if has_recent_db:
            os.remove(paths.get_db_path('recent_inventory.sqlite3'))
            print("   ✅ recent_inventory.sqlite3 삭제 완료")
        if has_processed_db:
            os.remove(paths.get_db_path('drug_timeseries.sqlite3'))
            print("   ✅ drug_timeseries.sqlite3 삭제 완료")
        print()

    # Step 1: 월별 CSV 로드
    print("🔍 Step 1: 월별 CSV 파일 로드")
    print("-" * 60)
    monthly_data = load_multiple_csv_files()  # paths.DATA_PATH 사용

    if not monthly_data:
        print("❌ CSV 파일을 로드할 수 없습니다.")
        sys.exit(1)

    # Step 2: DB 초기화
    print("\n💽 Step 2: 데이터베이스 초기화")
    print("-" * 60)
    inventory_db.init_db()
    drug_timeseries_db.init_db()

    # Step 3: 일반약 처리 (먼저 처리)
    # 전문약 중 일부가 일반약으로도 판매되는 경우가 있음 (예: 뮤테란)
    # 이 경우 전문약으로 분류하는 것이 맞으므로, 일반약을 먼저 처리하고 전문약이 덮어쓰도록 함
    print("\n🔄 Step 3: 일반약 데이터 처리")
    print("-" * 60)
    print("   데이터 통합 및 통계 계산 중...")
    df_sale, months = merge_by_drug_code(monthly_data, mode='sale')
    df_sale = calculate_statistics(df_sale, months)
    print(f"   ✅ 일반약 {len(df_sale)}개 처리 완료")

    # 통계 DB에 저장
    print("   💾 drug_timeseries.sqlite3에 저장 중...")
    drug_timeseries_db.upsert_processed_data(df_sale, drug_type='일반약')

    # 메타데이터 저장 (첫 번째 처리 시에만)
    drug_timeseries_db.save_metadata(months)

    # 재고 DB에 저장
    print("   💾 recent_inventory.sqlite3에 저장 중...")
    inventory_data = df_sale[['약품코드', '약품명', '제약회사', '최종_재고수량']].copy()
    inventory_data.rename(columns={'최종_재고수량': '현재_재고수량'}, inplace=True)
    inventory_data['약품유형'] = '일반약'
    inventory_db.upsert_inventory(inventory_data, show_summary=True)

    # Step 4: 전문약 처리 (나중에 처리하여 덮어씀)
    # 조제수량과 판매수량이 모두 있는 약품은 전문약으로 최종 분류됨
    print("\n🔄 Step 4: 전문약 데이터 처리")
    print("-" * 60)
    print("   데이터 통합 및 통계 계산 중...")
    df_dispense, months = merge_by_drug_code(monthly_data, mode='dispense')
    df_dispense = calculate_statistics(df_dispense, months)
    print(f"   ✅ 전문약 {len(df_dispense)}개 처리 완료")

    # 통계 DB에 저장
    print("   💾 drug_timeseries.sqlite3에 저장 중...")
    drug_timeseries_db.upsert_processed_data(df_dispense, drug_type='전문약')

    # 재고 DB에 저장 (최종_재고수량만)
    print("   💾 recent_inventory.sqlite3에 저장 중...")
    inventory_data = df_dispense[['약품코드', '약품명', '제약회사', '최종_재고수량']].copy()
    inventory_data.rename(columns={'최종_재고수량': '현재_재고수량'}, inplace=True)
    inventory_data['약품유형'] = '전문약'
    inventory_db.upsert_inventory(inventory_data, show_summary=True)

    # Step 4.5: 주기성 지표 계산
    print("\n🔄 Step 4.5: 주기성 지표 계산")
    print("-" * 60)
    print("   기존 주기성 데이터 초기화 중...")
    drug_periodicity_db.clear_all()
    result = periodicity_calculator.calculate_all_periodicity(show_progress=True)
    print(f"   ✅ 주기성 계산 완료: {result['calculated']}/{result['total']}개")

    # Step 5: 최종 통계 출력
    print("\n" + "=" * 60)
    print("✅ 데이터베이스 초기화 완료!")
    print("=" * 60)

    print("\n📊 recent_inventory.sqlite3 (최신 재고):")
    print(f"   총 {inventory_db.get_inventory_count()}개 약품")
    df_recent = inventory_db.get_all_inventory_as_df()
    if '약품유형' in df_recent.columns:
        type_counts = df_recent['약품유형'].value_counts()
        for drug_type, count in type_counts.items():
            print(f"   - {drug_type}: {count}개")

    print("\n📊 drug_timeseries.sqlite3 (시계열 통계):")
    stats = drug_timeseries_db.get_statistics()
    print(f"   총 {stats['total']}개 약품")
    for drug_type, count in stats['by_type'].items():
        print(f"   - {drug_type}: {count}개")

    print(f"\n📅 분석 기간: {months[0]} ~ {months[-1]} ({len(months)}개월)")

    print("\n" + "=" * 60)
    print("🎉 이제 다음 명령어를 실행할 수 있습니다:")
    print("   python web_app.py              # 보고서 생성 및 주문 산출")
    print("   python inventory_updater.py # today.csv로 재고 업데이트")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자에 의해 프로그램이 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 오류가 발생했습니다: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
