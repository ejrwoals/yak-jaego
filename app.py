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
from read_csv import select_file_from_directory, read_csv_file, process_inventory_data
from generate_report import create_and_save_report


def main():
    """메인 워크플로우 함수"""
    print("=" * 60)
    print("📊 Jaego - 약국 재고 관리 및 분석 시스템")
    print("=" * 60)
    print()

    try:
        # Step 1: CSV 파일 선택
        print("🔍 Step 1: CSV 파일 선택")
        print("-" * 30)
        file_path = select_file_from_directory()

        if not file_path:
            print("❌ CSV 파일이 선택되지 않았습니다. 프로그램을 종료합니다.")
            sys.exit(1)

        # Step 2: 파일 읽기
        print("\n📁 Step 2: CSV 파일 읽기")
        print("-" * 30)
        df_all = read_csv_file(file_path)

        # Step 3: 데이터 기간 입력
        print("\n📅 Step 3: 데이터 기간 설정")
        print("-" * 30)
        while True:
            try:
                m = int(input("총 몇개월 간의 데이터입니까? "))
                if m > 0:
                    break
                else:
                    print("양수를 입력해주세요.")
            except ValueError:
                print("올바른 숫자를 입력해주세요.")

        # Step 4: 데이터 처리
        print(f"\n⚙️ Step 4: 데이터 처리 및 분석 ({m}개월 기준)")
        print("-" * 30)
        df, m = process_inventory_data(df_all, m)

        if df is None:
            print("❌ 데이터 처리에 실패했습니다.")
            sys.exit(1)

        # Step 5: CSV 저장 (자동으로 저장)
        print("\n💾 Step 5: 처리된 데이터 저장")
        print("-" * 30)
        output_file = 'processed_inventory.csv'
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"✅ 처리된 데이터가 {output_file}에 저장되었습니다.")

        # Step 6: HTML 보고서 생성
        print("\n📋 Step 6: HTML 보고서 생성")
        print("-" * 30)
        report_path = create_and_save_report(df, m, open_browser=True)

        # 완료 메시지
        print("\n🎉 모든 작업이 완료되었습니다!")
        print("=" * 60)
        print(f"📁 처리된 데이터: {output_file}")
        print(f"📊 생성된 보고서: {report_path}")
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