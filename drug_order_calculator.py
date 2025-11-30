#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
약 주문 수량 산출 시스템

재고 데이터를 기반으로 약품별 적정 주문 수량을 계산하는 모듈
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime
import webbrowser
import inventory_db
import processed_inventory_db


def check_required_files():
    """필수 파일 존재 여부 확인"""
    # processed_inventory DB 체크
    if not processed_inventory_db.db_exists():
        print("❌ processed_inventory.sqlite3가 없습니다.")
        print("💡 먼저 DB 초기화를 실행하세요: python init_db.py")
        return False

    stats = processed_inventory_db.get_statistics()
    if stats['total'] == 0:
        print("❌ processed_inventory.sqlite3에 데이터가 없습니다.")
        print("💡 먼저 DB 초기화를 실행하세요: python init_db.py")
        return False

    print(f"✅ 시계열 통계 데이터: {stats['total']}개")
    for drug_type, count in stats['by_type'].items():
        print(f"   - {drug_type}: {count}개")

    # recent_inventory DB 체크
    if not inventory_db.db_exists():
        print("❌ recent_inventory.sqlite3가 없습니다.")
        print("💡 먼저 DB 초기화를 실행하세요: python init_db.py")
        return False

    print(f"✅ 최신 재고 데이터 발견")

    return True


def load_processed_data():
    """전문약 및 일반약 데이터 로드 (processed_inventory DB에서)"""
    print("🔍 Step 1: 시계열 분석 데이터 로드")
    print("-" * 30)

    # DB에서 전체 데이터 로드 (약품유형 포함)
    df = processed_inventory_db.get_processed_data()  # 전체 조회

    if df.empty:
        print("❌ processed_inventory DB에 데이터가 없습니다.")
        return None

    # 필요한 컬럼만 선택 (1년_이동평균 추가)
    required_cols = ['약품코드', '약품명', '제약회사', '1년_이동평균', '월별_조제수량_리스트', '3개월_이동평균_리스트', '약품유형']
    df = df[required_cols].copy()

    print(f"✅ 총 {len(df)}개 약품의 시계열 데이터를 로드했습니다.")

    # 약품유형별 통계
    type_counts = df['약품유형'].value_counts()
    for drug_type, count in type_counts.items():
        print(f"   - {drug_type}: {count}개")

    return df


def load_recent_inventory():
    """
    SQLite DB에서 최신 재고 데이터 로드
    today.csv/xls/xlsx가 있으면 먼저 DB를 업데이트하고, 해당 파일에 있는 약품들만 필터링
    """
    print("\n🔍 Step 2: 최신 재고 데이터 로드")
    print("-" * 30)

    today_drug_codes = None
    today_filepath = None

    # today 파일(csv/xls/xlsx)이 있는지 확인
    from utils import read_today_file
    today_df_temp, today_filepath = read_today_file('today')

    if today_df_temp is not None and today_filepath:
        print(f"📂 {today_filepath} 발견 - DB 업데이트 중...")
        try:
            from inventory_updater import update_inventory_from_today_csv
            result = update_inventory_from_today_csv('today')
            if result:
                print(f"   ✅ DB 업데이트 완료 (업데이트: {result['updated']}건, 신규: {result['inserted']}건)")

            # today 파일에서 약품코드 추출
            from read_csv import normalize_drug_code
            if '약품코드' in today_df_temp.columns:
                today_df_temp['약품코드'] = today_df_temp['약품코드'].apply(normalize_drug_code)
                today_drug_codes = set(today_df_temp['약품코드'].dropna().unique())
                print(f"   📋 {os.path.basename(today_filepath)}에서 {len(today_drug_codes)}개 약품 발견 (오늘 나간 약품)")
        except Exception as e:
            print(f"   ⚠️  today 파일 처리 실패: {e}")
            print("   전체 DB 데이터를 사용합니다.")

    # SQLite DB에서 재고 데이터 로드
    print("📊 recent_inventory.sqlite3에서 재고 데이터 로드 중...")
    df = inventory_db.get_all_inventory_as_df()

    if df.empty:
        print("❌ DB에 재고 데이터가 없습니다.")
        return None

    # 필요한 컬럼만 선택하고 컬럼명 변경
    df = df[['약품코드', '약품명', '제약회사', '현재_재고수량']].copy()
    df = df.rename(columns={'현재_재고수량': '현재 재고수량'})

    # 약품코드가 NaN인 행 제거
    df = df.dropna(subset=['약품코드'])

    # today.csv가 있으면 해당 약품들만 필터링
    if today_drug_codes:
        original_count = len(df)
        df = df[df['약품코드'].isin(today_drug_codes)]
        print(f"✅ 오늘 나간 약품 {len(df)}개로 필터링 (전체 {original_count}개 중)")
    else:
        print(f"✅ {len(df)}개 약품의 최신 재고 데이터를 로드했습니다.")

    return df


def parse_list_column(series):
    """문자열로 저장된 리스트를 실제 리스트로 변환하고 평균 계산"""
    import re

    def parse_and_mean(x):
        try:
            # numpy 타입 표기를 제거 (np.int64(34) -> 34, np.float64(1.5) -> 1.5)
            cleaned = re.sub(r'np\.(int64|float64)\(([^)]+)\)', r'\2', str(x))

            # 문자열을 실제 리스트로 변환
            import ast
            parsed = ast.literal_eval(cleaned)

            # None이 아닌 숫자만 필터링
            numbers = [float(v) for v in parsed if v is not None]

            if len(numbers) == 0:
                return 0.0
            return np.mean(numbers)
        except Exception as e:
            print(f"파싱 오류: {e}, 원본 데이터: {x[:100]}")
            return 0.0

    return series.apply(parse_and_mean)


def merge_and_calculate(today_df, processed_df):
    """데이터 병합 및 런웨이 계산"""
    print("\n⚙️ Step 3: 데이터 병합 및 런웨이 계산")
    print("-" * 30)

    # 1년 이동평균과 3개월 이동평균 준비
    processed_df['1년 이동평균'] = processed_df['1년_이동평균']  # DB에서 이미 계산된 값 사용
    processed_df['3개월 이동평균'] = parse_list_column(processed_df['3개월_이동평균_리스트'])

    # 약품코드를 기준으로 병합 (약품유형 컬럼 포함)
    result_df = today_df.merge(
        processed_df[['약품코드', '1년 이동평균', '3개월 이동평균', '약품유형']],
        on='약품코드',
        how='left'
    )

    # 약품유형이 없는 경우 '미분류'로 표시
    result_df['약품유형'] = result_df['약품유형'].fillna('미분류')

    # 런웨이 계산 (1년 이동평균 기반)
    result_df['런웨이'] = result_df['현재 재고수량'] / result_df['1년 이동평균']
    result_df['3-MA 런웨이'] = result_df['현재 재고수량'] / result_df['3개월 이동평균']

    # 무한대 값을 처리 (조제수량이 0인 경우)
    result_df['런웨이'] = result_df['런웨이'].replace([np.inf, -np.inf], 999)
    result_df['3-MA 런웨이'] = result_df['3-MA 런웨이'].replace([np.inf, -np.inf], 999)

    # NaN 값을 0으로 처리
    result_df['런웨이'] = result_df['런웨이'].fillna(0)
    result_df['3-MA 런웨이'] = result_df['3-MA 런웨이'].fillna(0)

    # 3-MA 런웨이 기준 오름차순 정렬
    result_df = result_df.sort_values('3-MA 런웨이', ascending=True)

    print(f"✅ {len(result_df)}개 약품의 런웨이를 계산했습니다.")

    return result_df


def generate_table_rows(df, col_map=None):
    """테이블 행 HTML 생성

    Args:
        df: 데이터프레임
        col_map: 컬럼명 매핑 딕셔너리 (선택사항)
            기본값: {'runway': '런웨이', 'ma3_runway': '3-MA 런웨이',
                    'stock': '현재 재고수량', 'ma12': '1년 이동평균', 'ma3': '3개월 이동평균'}
    """
    # 기본 컬럼명 (drug_order_calculator.py 스타일)
    default_map = {
        'runway': '런웨이',
        'ma3_runway': '3-MA 런웨이',
        'stock': '현재 재고수량',
        'ma12': '1년 이동평균',
        'ma3': '3개월 이동평균'
    }
    cm = col_map if col_map else default_map

    rows = ""
    for _, row in df.iterrows():
        runway = row[cm['runway']]
        ma3_runway = row[cm['ma3_runway']]

        # 런웨이 < 1인 경우 행 전체를 빨간색으로
        row_class = 'urgent-row' if (runway < 1 or ma3_runway < 1) else ''

        runway_class = 'urgent-cell' if runway < 1 else 'normal-cell'
        ma3_runway_class = 'urgent-cell' if ma3_runway < 1 else 'normal-cell'

        runway_display = f'{runway:.2f}' if runway < 999 else '재고만 있음'
        ma3_runway_display = f'{ma3_runway:.2f}' if ma3_runway < 999 else '재고만 있음'

        rows += f"""
            <tr class="{row_class}">
                <td>{row['약품명']}</td>
                <td>{row['약품코드']}</td>
                <td>{row['제약회사']}</td>
                <td>{row[cm['stock']]:.0f}</td>
                <td>{row[cm['ma12']]:.1f}</td>
                <td>{row[cm['ma3']]:.1f}</td>
                <td class="{runway_class}">{runway_display}</td>
                <td class="{ma3_runway_class}">{ma3_runway_display}</td>
            </tr>
"""
    return rows


def generate_zero_stock_table_rows(df, col_map):
    """재고 0 이하 약품 테이블 행 HTML 생성 (약품유형 포함)"""
    cm = col_map
    rows = ""
    for _, row in df.iterrows():
        drug_type = row['약품유형']
        type_badge_color = '#3498db' if drug_type == '전문약' else '#e67e22' if drug_type == '일반약' else '#95a5a6'

        rows += f"""
            <tr>
                <td>{row['약품명']}</td>
                <td>{row['약품코드']}</td>
                <td>{row['제약회사']}</td>
                <td><span style="background-color: {type_badge_color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px;">{drug_type}</span></td>
                <td style="color: #c62828; font-weight: bold;">{row[cm['stock']]:.0f}</td>
                <td>{row[cm['ma12']]:.1f}</td>
                <td>{row[cm['ma3']]:.1f}</td>
            </tr>
"""
    return rows


def generate_order_report_html(df, col_map=None):
    """주문 보고서 HTML 생성 (재사용 가능한 함수)

    Args:
        df: 데이터프레임
        col_map: 컬럼명 매핑 딕셔너리 (선택사항)
            기본값: {'runway': '런웨이', 'ma3_runway': '3-MA 런웨이',
                    'stock': '현재 재고수량', 'ma12': '1년 이동평균', 'ma3': '3개월 이동평균'}

    Returns:
        str: HTML 문자열
    """
    # 기본 컬럼명 (drug_order_calculator.py 스타일)
    default_map = {
        'runway': '런웨이',
        'ma3_runway': '3-MA 런웨이',
        'stock': '현재 재고수량',
        'ma12': '1년 이동평균',
        'ma3': '3개월 이동평균'
    }
    cm = col_map if col_map else default_map

    # 재고 0 이하 약품 분리 (전문약/일반약 혼합), 재고 오름차순 정렬 (큰 마이너스가 위로)
    zero_stock_df = df[df[cm['stock']] <= 0].copy()
    zero_stock_df = zero_stock_df.sort_values(cm['stock'], ascending=True)
    zero_stock_count = len(zero_stock_df)

    # 재고 0 이하 약품은 탭 테이블에서 제외
    normal_df = df[df[cm['stock']] > 0].copy()

    # 약품 유형별 분리 (재고 > 0인 약품만)
    dispense_df = normal_df[normal_df['약품유형'] == '전문약'].copy()
    sale_df = normal_df[normal_df['약품유형'] == '일반약'].copy()
    unclassified_df = normal_df[normal_df['약품유형'] == '미분류'].copy()

    # 약품 유형별 개수
    dispense_count = len(dispense_df)
    sale_count = len(sale_df)
    unclassified_count = len(unclassified_df)

    # 긴급 주문 필요 약품 개수 (유형별, 재고 > 0인 약품 중)
    dispense_urgent = len(dispense_df[(dispense_df[cm['runway']] < 1) | (dispense_df[cm['ma3_runway']] < 1)])
    sale_urgent = len(sale_df[(sale_df[cm['runway']] < 1) | (sale_df[cm['ma3_runway']] < 1)])
    total_urgent = dispense_urgent + sale_urgent

    # 테이블 행 생성
    dispense_rows = generate_table_rows(dispense_df, cm)
    sale_rows = generate_table_rows(sale_df, cm)
    zero_stock_rows = generate_zero_stock_table_rows(zero_stock_df, cm) if zero_stock_count > 0 else ""

    # 재고 0 이하 경고 배너 HTML
    zero_stock_banner = f"""
    <div class="warning-banner" onclick="openZeroStockModal()">
        <span class="warning-icon">⚠️</span>
        <span class="warning-text">재고 부족/음수 경고: <strong>{zero_stock_count}개</strong> 약품의 재고가 0 이하입니다</span>
        <button class="warning-btn">확인하기</button>
    </div>
    """ if zero_stock_count > 0 else ""

    # 재고 0 이하 모달 HTML
    zero_stock_modal = f"""
    <div id="zeroStockModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>⚠️ 재고 부족/음수 약품 ({zero_stock_count}개)</h3>
                <span class="modal-close" onclick="closeZeroStockModal()">&times;</span>
            </div>
            <div class="modal-body">
                <p style="color: #666; margin-bottom: 15px;">재고가 0 이하인 약품입니다. 즉시 주문이 필요합니다.</p>
                <table>
                    <thead>
                        <tr>
                            <th>약품명</th>
                            <th>약품코드</th>
                            <th>제약회사</th>
                            <th>약품유형</th>
                            <th>현재 재고</th>
                            <th>1년 이동평균</th>
                            <th>3개월 이동평균</th>
                        </tr>
                    </thead>
                    <tbody>
                        {zero_stock_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    """ if zero_stock_count > 0 else ""

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>약 주문 수량 산출 보고서</title>
    <style>
        body {{
            font-family: 'Malgun Gothic', '맑은 고딕', Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background-color: #2c3e50;
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .summary {{
            background-color: #fff;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .urgent {{
            color: #e74c3c;
            font-weight: bold;
            font-size: 24px;
        }}

        /* 경고 배너 스타일 */
        .warning-banner {{
            background-color: #ffebee;
            border: 2px solid #ef5350;
            border-radius: 8px;
            padding: 12px 20px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .warning-banner:hover {{
            background-color: #ffcdd2;
        }}
        .warning-icon {{
            font-size: 20px;
            margin-right: 10px;
        }}
        .warning-text {{
            flex: 1;
            color: #c62828;
        }}
        .warning-btn {{
            background-color: #ef5350;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 500;
        }}
        .warning-btn:hover {{
            background-color: #e53935;
        }}

        /* 모달 스타일 */
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
        }}
        .modal-content {{
            background-color: #fff;
            margin: 3% auto;
            padding: 0;
            border-radius: 8px;
            width: 95%;
            max-width: 1400px;
            max-height: 90vh;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }}
        .modal-header {{
            background-color: #6c757d;
            color: white;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .modal-header h3 {{
            margin: 0;
        }}
        .modal-close {{
            font-size: 28px;
            cursor: pointer;
            color: white;
        }}
        .modal-close:hover {{
            color: #e9ecef;
        }}
        .modal-body {{
            padding: 20px;
            max-height: 80vh;
            overflow-y: auto;
        }}

        /* 탭 스타일 */
        .tab-container {{
            margin-bottom: 20px;
        }}
        .tab-buttons {{
            display: flex;
            gap: 0;
            border-bottom: 2px solid #dee2e6;
        }}
        .tab-btn {{
            padding: 12px 24px;
            border: none;
            background-color: #e9ecef;
            cursor: pointer;
            font-size: 15px;
            font-weight: 500;
            color: #495057;
            border-radius: 8px 8px 0 0;
            margin-right: 4px;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .tab-btn:hover {{
            background-color: #dee2e6;
        }}
        .tab-btn.active {{
            background-color: #fff;
            color: #2c3e50;
            border: 2px solid #dee2e6;
            border-bottom: 2px solid #fff;
            margin-bottom: -2px;
            font-weight: 600;
        }}
        .tab-btn .count {{
            background-color: #6c757d;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 13px;
        }}
        .tab-btn.active .count {{
            background-color: #2c3e50;
        }}
        .tab-btn .urgent-count {{
            background-color: #dc3545;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 13px;
        }}
        .tab-content {{
            display: none;
            background-color: #fff;
            border: 2px solid #dee2e6;
            border-top: none;
            border-radius: 0 0 8px 8px;
            padding: 20px;
        }}
        .tab-content.active {{
            display: block;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            background-color: white;
        }}
        th {{
            background-color: #34495e;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: bold;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }}
        tr:hover {{
            background-color: #f9f9f9;
        }}
        .urgent-row {{
            background-color: #ffebee !important;
            font-weight: bold;
        }}
        .urgent-cell {{
            color: #c62828;
            font-weight: bold;
        }}
        .normal-cell {{
            color: #2e7d32;
        }}
        .empty-message {{
            text-align: center;
            padding: 40px;
            color: #6c757d;
            font-size: 16px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📦 약 주문 수량 산출 보고서</h1>
        <p>생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    {zero_stock_banner}

    <div class="summary">
        <h2>📊 요약</h2>
        <p>총 약품 수: <strong>{len(df)}개</strong> (전문약: {len(df[df['약품유형'] == '전문약'])}개 / 일반약: {len(df[df['약품유형'] == '일반약'])}개{f' / 미분류: {len(df[df["약품유형"] == "미분류"])}개' if len(df[df['약품유형'] == '미분류']) > 0 else ''})</p>
        <p>긴급 주문 필요 (런웨이 < 1개월): <span class="urgent">{total_urgent}개</span> (전문약: {dispense_urgent}개 / 일반약: {sale_urgent}개){f' + 재고 0 이하: <span class="urgent">{zero_stock_count}개</span>' if zero_stock_count > 0 else ''}</p>
    </div>

    <div class="tab-container">
        <div class="tab-buttons">
            <button class="tab-btn active" onclick="switchTab('dispense')">
                💊 전문약
                <span class="count">{dispense_count}</span>
                {f'<span class="urgent-count">긴급 {dispense_urgent}</span>' if dispense_urgent > 0 else ''}
            </button>
            <button class="tab-btn" onclick="switchTab('sale')">
                💊 일반약
                <span class="count">{sale_count}</span>
                {f'<span class="urgent-count">긴급 {sale_urgent}</span>' if sale_urgent > 0 else ''}
            </button>
        </div>

        <div id="dispense-tab" class="tab-content active">
            {f'''<table>
                <thead>
                    <tr>
                        <th>약품명</th>
                        <th>약품코드</th>
                        <th>제약회사</th>
                        <th>현재 재고수량</th>
                        <th>1년 이동평균</th>
                        <th>3개월 이동평균</th>
                        <th>런웨이 (개월)</th>
                        <th>3-MA 런웨이 (개월)</th>
                    </tr>
                </thead>
                <tbody>
                    {dispense_rows}
                </tbody>
            </table>''' if dispense_count > 0 else '<div class="empty-message">오늘 나간 전문약이 없습니다.</div>'}
        </div>

        <div id="sale-tab" class="tab-content">
            {f'''<table>
                <thead>
                    <tr>
                        <th>약품명</th>
                        <th>약품코드</th>
                        <th>제약회사</th>
                        <th>현재 재고수량</th>
                        <th>1년 이동평균</th>
                        <th>3개월 이동평균</th>
                        <th>런웨이 (개월)</th>
                        <th>3-MA 런웨이 (개월)</th>
                    </tr>
                </thead>
                <tbody>
                    {sale_rows}
                </tbody>
            </table>''' if sale_count > 0 else '<div class="empty-message">오늘 나간 일반약이 없습니다.</div>'}
        </div>
    </div>

    {zero_stock_modal}

    <script>
        function switchTab(tabName) {{
            // 모든 탭 버튼 비활성화
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            // 모든 탭 컨텐츠 숨김
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

            // 선택된 탭 활성화
            if (tabName === 'dispense') {{
                document.querySelectorAll('.tab-btn')[0].classList.add('active');
                document.getElementById('dispense-tab').classList.add('active');
            }} else {{
                document.querySelectorAll('.tab-btn')[1].classList.add('active');
                document.getElementById('sale-tab').classList.add('active');
            }}
        }}

        // 재고 0 이하 모달 열기/닫기
        function openZeroStockModal() {{
            document.getElementById('zeroStockModal').style.display = 'block';
        }}
        function closeZeroStockModal() {{
            document.getElementById('zeroStockModal').style.display = 'none';
        }}
        // 모달 외부 클릭 시 닫기
        window.onclick = function(event) {{
            var modal = document.getElementById('zeroStockModal');
            if (event.target == modal) {{
                modal.style.display = 'none';
            }}
        }}
    </script>
</body>
</html>
"""
    return html


def generate_html_report(df):
    """HTML 보고서 생성 및 파일 저장 (CLI용 래퍼 함수)"""
    print("\n📋 Step 4: HTML 보고서 생성")
    print("-" * 30)

    # 출력 디렉토리 생성
    output_dir = 'order_calc_reports'
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = os.path.join(output_dir, f'order_calculator_report_{timestamp}.html')

    # HTML 생성 (재사용 가능한 함수 호출)
    html = generate_order_report_html(df)

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ HTML 보고서가 생성되었습니다: {filename}")

    # 브라우저에서 자동으로 열기
    webbrowser.open('file://' + os.path.abspath(filename))

    return filename


def save_csv_report(df):
    """CSV 보고서 저장"""
    # 출력 디렉토리 생성
    output_dir = 'order_calc_reports'
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = os.path.join(output_dir, f'order_calculator_report_{timestamp}.csv')

    df.to_csv(filename, index=False, encoding='utf-8-sig')
    print(f"✅ CSV 보고서가 저장되었습니다: {filename}")

    return filename


def run():
    """주문 수량 산출 시스템 메인 실행 함수"""
    try:
        # 필수 파일 확인
        if not check_required_files():
            return

        # 데이터 로드
        processed_df = load_processed_data()
        inventory_df = load_recent_inventory()

        if inventory_df is None:
            print("\n❌ 재고 데이터를 로드할 수 없습니다.")
            return

        # 병합 및 계산
        result_df = merge_and_calculate(inventory_df, processed_df)

        # 보고서 생성
        html_file = generate_html_report(result_df)
        csv_file = save_csv_report(result_df)

        # 완료 메시지
        print("\n🎉 주문 수량 산출이 완료되었습니다!")
        print("=" * 60)
        print(f"📊 HTML 보고서: {html_file}")
        print(f"📁 CSV 보고서: {csv_file}")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 오류가 발생했습니다: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    run()
