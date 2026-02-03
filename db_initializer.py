#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
데이터베이스 초기화 공통 모듈

init_db.py (CLI)와 web_app.py (Web API) 모두에서 사용하는
DB 재생성 핵심 로직을 제공합니다.

중복 구현을 방지하고 일관된 동작을 보장합니다.
"""

import os
from read_csv import load_multiple_csv_files, merge_by_drug_code, calculate_statistics
import inventory_db
import drug_timeseries_db
import periodicity_calculator
import drug_periodicity_db
import paths


def rebuild_database(
    data_path=None,
    delete_existing=True,
    include_periodicity=True,
    show_summary=True,
    on_progress=None
):
    """
    DB 재생성 핵심 로직

    Args:
        data_path: CSV 파일 경로 (None이면 기본 경로 사용)
        delete_existing: 기존 DB 삭제 여부
        include_periodicity: 주기성 계산 포함 여부
        show_summary: 저장 시 요약 출력 여부
        on_progress: 진행 상황 콜백 함수 (message: str) -> None

    Returns:
        dict: {
            'success': bool,
            'months': list,  # 분석 기간 월 리스트
            'stats': {
                'recent_count': int,
                'processed_stats': dict,
                'data_period': dict
            },
            'error': str (실패 시)
        }
    """
    def log(message):
        """진행 상황 로깅"""
        if on_progress:
            on_progress(message)
        print(message)

    try:
        # Step 1: 기존 DB 삭제
        if delete_existing:
            log("🗑️  기존 DB 삭제 중...")
            if inventory_db.db_exists():
                os.remove(paths.get_db_path('recent_inventory.sqlite3'))
            if drug_timeseries_db.db_exists():
                os.remove(paths.get_db_path('drug_timeseries.sqlite3'))

        # Step 2: CSV 파일 로드
        log("🔍 CSV 파일 로드 중...")
        if data_path:
            original_path = paths.DATA_PATH
            paths.DATA_PATH = data_path

        monthly_data = load_multiple_csv_files()

        if data_path:
            paths.DATA_PATH = original_path

        if not monthly_data:
            return {
                'success': False,
                'error': 'CSV 파일을 로드할 수 없습니다.'
            }

        # Step 3: DB 초기화
        log("💽 데이터베이스 초기화 중...")
        inventory_db.init_db()
        drug_timeseries_db.init_db()

        # Step 4: 일반약 처리 (먼저 처리)
        # 전문약 중 일부가 일반약으로도 판매되는 경우가 있음 (예: 뮤테란)
        # 이 경우 전문약으로 분류하는 것이 맞으므로, 일반약을 먼저 처리하고 전문약이 덮어쓰도록 함
        log("🔄 일반약 데이터 처리 중...")
        df_sale, months = merge_by_drug_code(monthly_data, mode='sale')
        df_sale = calculate_statistics(df_sale, months)

        # 통계 DB에 저장
        drug_timeseries_db.upsert_processed_data(df_sale, drug_type='일반약', show_summary=show_summary)

        # 메타데이터 저장 (첫 번째 처리 시에만)
        drug_timeseries_db.save_metadata(months)

        # 재고 DB에 저장
        inventory_data = df_sale[['약품코드', '약품명', '제약회사', '최종_재고수량']].copy()
        inventory_data.rename(columns={'최종_재고수량': '현재_재고수량'}, inplace=True)
        inventory_data['약품유형'] = '일반약'
        inventory_db.upsert_inventory(inventory_data, show_summary=show_summary)

        # Step 5: 전문약 처리 (나중에 처리하여 덮어씀)
        # 조제수량과 판매수량이 모두 있는 약품은 전문약으로 최종 분류됨
        log("🔄 전문약 데이터 처리 중...")
        df_dispense, months = merge_by_drug_code(monthly_data, mode='dispense')
        df_dispense = calculate_statistics(df_dispense, months)

        # 통계 DB에 저장
        drug_timeseries_db.upsert_processed_data(df_dispense, drug_type='전문약', show_summary=show_summary)

        # 재고 DB에 저장
        inventory_data = df_dispense[['약품코드', '약품명', '제약회사', '최종_재고수량']].copy()
        inventory_data.rename(columns={'최종_재고수량': '현재_재고수량'}, inplace=True)
        inventory_data['약품유형'] = '전문약'
        inventory_db.upsert_inventory(inventory_data, show_summary=show_summary)

        # Step 6: 주기성 지표 계산 (옵션)
        if include_periodicity:
            log("🔄 주기성 지표 계산 중...")
            drug_periodicity_db.clear_all()
            periodicity_calculator.calculate_all_periodicity(show_progress=show_summary)

        # 최종 통계 수집
        log("✅ DB 재생성 완료!")

        recent_count = inventory_db.get_inventory_count()
        processed_stats = drug_timeseries_db.get_statistics()
        data_period = drug_timeseries_db.get_metadata()

        return {
            'success': True,
            'months': months,
            'stats': {
                'recent_count': recent_count,
                'processed_stats': processed_stats,
                'data_period': data_period
            }
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }


def get_existing_db_info():
    """
    기존 DB 정보 조회

    Returns:
        dict: {
            'has_recent_db': bool,
            'has_processed_db': bool,
            'recent_count': int or None,
            'processed_stats': dict or None
        }
    """
    has_recent_db = inventory_db.db_exists()
    has_processed_db = drug_timeseries_db.db_exists()

    result = {
        'has_recent_db': has_recent_db,
        'has_processed_db': has_processed_db,
        'recent_count': None,
        'processed_stats': None
    }

    if has_recent_db:
        result['recent_count'] = inventory_db.get_inventory_count()

    if has_processed_db:
        result['processed_stats'] = drug_timeseries_db.get_statistics()

    return result
