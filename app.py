#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Jaego - 약국 재고 관리 및 분석 시스템
메인 워크플로우 애플리케이션

보고서 생성 및 주문 수량 산출 기능을 제공합니다.
DB 초기화는 init_db.py를 사용하세요.

사용법: python app.py
"""

import os
import sys

# 로컬 모듈 import
from generate_report import create_and_save_report
from drug_order_calculator import run as run_order_calculator
import inventory_db
import processed_inventory_db


def check_database_ready():
    """두 개의 DB가 모두 준비되었는지 확인"""

    print("\n🔍 데이터베이스 확인 중...")
    print("-" * 60)

    # recent_inventory.sqlite3 체크
    if not inventory_db.db_exists():
        print("❌ recent_inventory.sqlite3가 없습니다.")
        print("\n💡 먼저 DB를 초기화해주세요:")
        print("   python init_db.py")
        return False

    recent_count = inventory_db.get_inventory_count()
    if recent_count == 0:
        print("❌ recent_inventory.sqlite3에 데이터가 없습니다.")
        print("\n💡 먼저 DB를 초기화해주세요:")
        print("   python init_db.py")
        return False

    # processed_inventory.sqlite3 체크
    if not processed_inventory_db.db_exists():
        print("❌ processed_inventory.sqlite3가 없습니다.")
        print("\n💡 먼저 DB를 초기화해주세요:")
        print("   python init_db.py")
        return False

    processed_stats = processed_inventory_db.get_statistics()
    if processed_stats['total'] == 0:
        print("❌ processed_inventory.sqlite3에 데이터가 없습니다.")
        print("\n💡 먼저 DB를 초기화해주세요:")
        print("   python init_db.py")
        return False

    # 성공
    print("✅ 데이터베이스 준비 완료")
    print(f"   - 최신 재고 (recent_inventory.sqlite3): {recent_count}개")
    print(f"   - 시계열 통계 (processed_inventory.sqlite3): {processed_stats['total']}개")

    # 약품유형별 통계
    if processed_stats['by_type']:
        for drug_type, count in processed_stats['by_type'].items():
            print(f"     * {drug_type}: {count}개")

    return True


def run_timeseries_analysis():
    """시계열 분석 워크플로우 - 보고서 생성만"""
    print("=" * 60)
    print("📊 재고 관리 보고서 생성")
    print("=" * 60)
    print()

    try:
        # Step 1: 보고서 유형 선택
        print("📌 보고서 유형을 선택하세요:")
        print("  1. 전문약 보고서")
        print("  2. 일반약 보고서")
        print()

        while True:
            choice = input("선택 (1 또는 2): ").strip()
            if choice in ['1', '2']:
                break
            print("❌ 1 또는 2를 입력해주세요.")

        # 처리할 모드 결정
        modes_to_process = []
        if choice == '1':
            modes_to_process = [('dispense', '전문약')]
        elif choice == '2':
            modes_to_process = [('sale', '일반약')]

        # Step 2: 각 모드별 보고서 생성
        report_paths = []

        for mode, mode_name in modes_to_process:
            print(f"\n{'='*60}")
            print(f"📋 {mode_name} 보고서 생성 중...")
            print(f"{'='*60}")

            # processed_inventory DB에서 데이터 로드
            df = processed_inventory_db.get_processed_data(drug_type=mode_name)

            if df.empty:
                print(f"⚠️  {mode_name} 데이터가 없습니다. 건너뜁니다.")
                continue

            print(f"✅ {mode_name} 데이터 로드 완료: {len(df)}개 약품")

            # 월 정보 추출 (월별_조제수량_리스트의 길이로 계산)
            # 실제 월 정보는 리스트 길이로 추정 (간단한 구현)
            first_record = df.iloc[0]
            num_months = len(first_record['월별_조제수량_리스트'])

            # 간단히 연속된 월 생성 (실제로는 DB에 월 정보도 저장하면 더 좋음)
            import datetime
            today = datetime.datetime.now()
            months = []
            for i in range(num_months):
                month_date = datetime.datetime(today.year, today.month, 1) - datetime.timedelta(days=30*(num_months-1-i))
                months.append(month_date.strftime('%Y-%m'))

            # HTML 보고서 생성
            report_path = create_and_save_report(
                df, months, mode=mode,
                open_browser=(mode==modes_to_process[0][0])
            )
            report_paths.append(report_path)
            print(f"✅ {mode_name} 보고서 생성 완료")

        # 완료 메시지
        print("\n" + "=" * 60)
        print("🎉 보고서 생성 완료!")
        print("=" * 60)
        for path in report_paths:
            print(f"📊 {path}")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 오류가 발생했습니다: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def run_order_calculation():
    """주문 수량 산출 워크플로우"""
    print("=" * 60)
    print("📦 약 주문 수량 산출 시스템")
    print("=" * 60)
    print()

    try:
        run_order_calculator()
    except KeyboardInterrupt:
        print("\n\n⚠️ 사용자에 의해 프로그램이 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 오류가 발생했습니다: {e}")
        sys.exit(1)


def show_menu():
    """워크플로우 선택 메뉴 출력"""
    print("\n" + "=" * 60)
    print("🏥 Jaego - 약국 재고 관리 시스템")
    print("=" * 60)
    print("\n사용 가능한 워크플로우:")
    print("  1. 재고 관리 보고서 생성 (시계열 분석)")
    print("  2. 약 주문 수량 산출")
    print("  0. 종료")
    print("\n" + "=" * 60)


def get_user_choice():
    """사용자 선택 입력 받기"""
    while True:
        try:
            choice = input("\n실행할 워크플로우 번호를 입력하세요: ").strip()
            if choice in ['0', '1', '2']:
                return choice
            else:
                print("❌ 잘못된 입력입니다. 0, 1, 2 중 하나를 입력해주세요.")
        except EOFError:
            print("\n\n⚠️ 입력이 중단되었습니다.")
            sys.exit(0)


def main():
    """메인 함수 - 워크플로우 선택 및 실행"""
    try:
        # DB 준비 상태 확인
        if not check_database_ready():
            sys.exit(1)

        # 메뉴 표시 및 선택
        show_menu()
        choice = get_user_choice()

        if choice == '0':
            print("\n👋 프로그램을 종료합니다.")
            sys.exit(0)
        elif choice == '1':
            run_timeseries_analysis()
        elif choice == '2':
            run_order_calculation()

    except KeyboardInterrupt:
        print("\n\n⚠️ 사용자에 의해 프로그램이 중단되었습니다.")
        sys.exit(0)


if __name__ == "__main__":
    main()
