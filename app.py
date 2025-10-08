#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Jaego - 약국 재고 관리 및 분석 시스템
메인 워크플로우 애플리케이션

이 파일은 read_excel.py와 generate_report.py의 기능을 통합하여
하나의 명령어로 전체 워크플로우를 실행할 수 있게 합니다.

사용법: python app.py
"""

import os
import sys

# 로컬 모듈 import
from read_csv import load_multiple_csv_files, merge_by_drug_code, calculate_statistics
from generate_report import create_and_save_report


def main():
    """메인 워크플로우 함수"""
    print("=" * 60)
    print("📊 Jaego - 약국 재고 관리 및 분석 시스템 (시계열 분석)")
    print("=" * 60)
    print()

    try:
        # Step 1: 월별 CSV 파일들 자동 로드
        print("🔍 Step 1: 월별 CSV 파일 자동 로드")
        print("-" * 30)
        monthly_data = load_multiple_csv_files(directory='data')

        if not monthly_data:
            print("❌ CSV 파일을 로드할 수 없습니다. 프로그램을 종료합니다.")
            sys.exit(1)

        # Step 2: 약품코드 기준으로 데이터 통합
        print("\n🔗 Step 2: 약품코드 기준으로 데이터 통합")
        print("-" * 30)
        df, months = merge_by_drug_code(monthly_data)

        if df is None or df.empty:
            print("❌ 데이터 통합에 실패했습니다.")
            sys.exit(1)

        # Step 3: 통계 계산 (월평균, 3개월 이동평균, 런웨이)
        print("\n⚙️ Step 3: 통계 계산")
        print("-" * 30)
        df = calculate_statistics(df, months)

        # Step 4: CSV 저장 (자동으로 저장)
        print("\n💾 Step 4: 처리된 데이터 저장")
        print("-" * 30)
        output_file = 'processed_inventory_timeseries.csv'

        # 리스트 컬럼을 문자열로 변환하여 저장
        df_to_save = df.copy()
        df_to_save['월별_조제수량_리스트'] = df_to_save['월별_조제수량_리스트'].apply(str)
        df_to_save['3개월_이동평균_리스트'] = df_to_save['3개월_이동평균_리스트'].apply(str)
        df_to_save.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"✅ 처리된 데이터가 {output_file}에 저장되었습니다.")

        # Step 5: HTML 보고서 생성
        print("\n📋 Step 5: HTML 보고서 생성")
        print("-" * 30)
        report_path = create_and_save_report(df, months, open_browser=True)

        # 완료 메시지
        print("\n🎉 모든 작업이 완료되었습니다!")
        print("=" * 60)
        print(f"📁 처리된 데이터: {output_file}")
        print(f"📊 생성된 보고서: {report_path}")
        print(f"📅 분석 기간: {months[0]} ~ {months[-1]} ({len(months)}개월)")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\n⚠️ 사용자에 의해 프로그램이 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 오류가 발생했습니다: {e}")
        print("\n문제가 지속되면 다음을 확인해보세요:")
        print("1. 파일이 올바른 형식인지 확인")
        print("2. data/ 폴더에 파일이 있는지 확인")
        print("3. 필요한 Python 패키지가 설치되어 있는지 확인")
        sys.exit(1)


if __name__ == "__main__":
    main()