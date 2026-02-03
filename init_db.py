#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
재고 데이터베이스 초기화 스크립트 (관리자용)

다음 두 개의 데이터베이스를 생성합니다:
1. recent_inventory.sqlite3 - 최신 재고 현황
2. drug_timeseries.sqlite3 - 시계열 통계 데이터

사용법: python init_db.py
"""

import sys
from db_initializer import rebuild_database, get_existing_db_info
import inventory_db
import drug_timeseries_db


def main():
    print("=" * 60)
    print("📊 재고 데이터베이스 초기화")
    print("=" * 60)
    print()

    # 기존 DB 확인
    db_info = get_existing_db_info()

    if db_info['has_recent_db'] or db_info['has_processed_db']:
        print("⚠️  기존 데이터베이스가 발견되었습니다:")
        if db_info['has_recent_db']:
            print(f"   - recent_inventory.sqlite3 (재고: {db_info['recent_count']}개)")
        if db_info['has_processed_db']:
            stats = db_info['processed_stats']
            print(f"   - drug_timeseries.sqlite3 (통계: {stats['total']}개)")

        print()
        overwrite = input("❓ 기존 DB를 덮어쓰시겠습니까? (y/n): ").strip().lower()

        if overwrite != 'y':
            print("\n❌ 초기화를 취소했습니다.")
            sys.exit(0)

    # DB 재생성 실행
    print("\n🔄 DB 재생성을 시작합니다...")
    print("-" * 60)

    result = rebuild_database(
        delete_existing=True,
        include_periodicity=True,
        show_summary=True
    )

    if not result['success']:
        print(f"\n❌ DB 재생성 실패: {result.get('error', '알 수 없는 오류')}")
        sys.exit(1)

    # 최종 통계 출력
    print("\n" + "=" * 60)
    print("✅ 데이터베이스 초기화 완료!")
    print("=" * 60)

    stats = result['stats']
    months = result['months']

    print("\n📊 recent_inventory.sqlite3 (최신 재고):")
    print(f"   총 {stats['recent_count']}개 약품")
    df_recent = inventory_db.get_all_inventory_as_df()
    if '약품유형' in df_recent.columns:
        type_counts = df_recent['약품유형'].value_counts()
        for drug_type, count in type_counts.items():
            print(f"   - {drug_type}: {count}개")

    print("\n📊 drug_timeseries.sqlite3 (시계열 통계):")
    processed_stats = stats['processed_stats']
    print(f"   총 {processed_stats['total']}개 약품")
    for drug_type, count in processed_stats['by_type'].items():
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
