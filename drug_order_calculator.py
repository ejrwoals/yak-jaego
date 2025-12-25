#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
약 주문 수량 산출 시스템

재고 데이터를 기반으로 약품별 적정 주문 수량을 계산하는 모듈
"""

import os
from html import escape as html_escape
import pandas as pd
import numpy as np
from datetime import datetime
import webbrowser
import inventory_db
import processed_inventory_db
import drug_thresholds_db


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

    # 약품코드를 기준으로 병합 (약품유형 컬럼 + 시계열 데이터 포함)
    result_df = today_df.merge(
        processed_df[['약품코드', '1년 이동평균', '3개월 이동평균', '약품유형',
                      '월별_조제수량_리스트', '3개월_이동평균_리스트']],
        on='약품코드',
        how='left'
    )

    # 신규 약품 감지 (1년 이동평균이 NaN인 경우 = processed_inventory에 없는 약품)
    result_df['신규약품'] = result_df['1년 이동평균'].isna()
    new_drug_count = result_df['신규약품'].sum()
    if new_drug_count > 0:
        print(f"🆕 신규 약품 {new_drug_count}개 감지 (시계열 데이터 없음)")

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


def generate_table_rows(df, col_map=None, months=None, runway_threshold=1.0, custom_thresholds=None):
    """테이블 행 HTML 생성 (인라인 차트 지원)

    Args:
        df: 데이터프레임
        col_map: 컬럼명 매핑 딕셔너리 (선택사항)
            기본값: {'runway': '런웨이', 'ma3_runway': '3-MA 런웨이',
                    'stock': '현재 재고수량', 'ma12': '1년 이동평균', 'ma3': '3개월 이동평균'}
        months: 월 리스트 (차트용)
        runway_threshold: 긴급 주문 기준 런웨이 (개월), 기본값 1.0
        custom_thresholds: 개별 임계값 딕셔너리 {약품코드: {...}}
    """
    import json
    import ast
    import re

    # 기본 컬럼명 (drug_order_calculator.py 스타일)
    default_map = {
        'runway': '런웨이',
        'ma3_runway': '3-MA 런웨이',
        'stock': '현재 재고수량',
        'ma12': '1년 이동평균',
        'ma3': '3개월 이동평균'
    }
    cm = col_map if col_map else default_map

    def parse_list_string(x):
        """문자열로 저장된 리스트를 실제 리스트로 변환"""
        if isinstance(x, list):
            return x
        if pd.isna(x):
            return []
        try:
            # numpy 타입 표기를 제거
            cleaned = re.sub(r'np\.(int64|float64)\(([^)]+)\)', r'\2', str(x))
            return ast.literal_eval(cleaned)
        except:
            return []

    rows = ""
    for _, row in df.iterrows():
        runway = row[cm['runway']]
        ma3_runway = row[cm['ma3_runway']]
        stock = row[cm['stock']]
        drug_code = str(row['약품코드'])

        # 글로벌 임계값 기준 (런웨이가 임계값 미만)
        is_urgent = runway < runway_threshold or ma3_runway < runway_threshold
        row_class = 'urgent-row clickable-row' if is_urgent else 'clickable-row'

        runway_class = 'urgent-cell' if runway < runway_threshold else 'normal-cell'
        ma3_runway_class = 'urgent-cell' if ma3_runway < runway_threshold else 'normal-cell'

        runway_display = f'{runway:.2f}' if runway < 999 else '재고만 있음'
        ma3_runway_display = f'{ma3_runway:.2f}' if ma3_runway < 999 else '재고만 있음'

        # 트렌드 아이콘 계산 (3개월 평균 vs 1년 평균, ±15% 임계값)
        ma12_val = float(row[cm['ma12']]) if not pd.isna(row[cm['ma12']]) else 0
        ma3_val = float(row[cm['ma3']]) if not pd.isna(row[cm['ma3']]) else 0

        if ma12_val == 0 and ma3_val > 0:
            trend_icon = '📈'  # 신규 사용 시작
            trend_class = 'trend-up'
        elif ma12_val > 0 and ma3_val == 0:
            trend_icon = '📉'  # 사용 중단
            trend_class = 'trend-down'
        elif ma12_val == 0 and ma3_val == 0:
            trend_icon = '➖'  # 둘 다 0
            trend_class = 'trend-stable'
        else:
            ratio = ma3_val / ma12_val
            if ratio > 1.15:
                trend_icon = '📈'  # 상승 (15% 초과)
                trend_class = 'trend-up'
            elif ratio < 0.85:
                trend_icon = '📉'  # 하락 (15% 미만)
                trend_class = 'trend-down'
            else:
                trend_icon = '➖'  # 유지 (±15% 이내)
                trend_class = 'trend-stable'

        # 인라인 차트용 데이터 생성
        timeseries = parse_list_string(row.get('월별_조제수량_리스트', []))
        ma3_list = parse_list_string(row.get('3개월_이동평균_리스트', []))

        chart_data = {
            'drug_name': row['약품명'] if row['약품명'] else "정보없음",
            'drug_code': drug_code,
            'timeseries': timeseries,
            'ma3_list': ma3_list,
            'months': months if months else [],
            'stock': float(row[cm['stock']]),
            'ma12': float(row[cm['ma12']]) if not pd.isna(row[cm['ma12']]) else 0,
            'ma3': float(row[cm['ma3']]) if not pd.isna(row[cm['ma3']]) else 0,
            'runway': runway_display,
            'ma3_runway': ma3_runway_display
        }
        chart_data_json = html_escape(json.dumps(chart_data, ensure_ascii=False))

        # 약품명 표시
        drug_name_display = row['약품명'] if row['약품명'] else "정보없음"

        # 개별 임계값 아이콘 (설정된 경우에만)
        threshold_icon = ""
        if custom_thresholds and drug_code in custom_thresholds:
            th = custom_thresholds[drug_code]
            tooltip_parts = []
            if th.get('절대재고_임계값') is not None:
                tooltip_parts.append(f"재고 임계값: {th['절대재고_임계값']}개 이하")
            if th.get('런웨이_임계값') is not None:
                tooltip_parts.append(f"런웨이 임계값: {th['런웨이_임계값']}개월 미만")
            if th.get('메모'):
                tooltip_parts.append(f"메모: {th['메모']}")
            tooltip_text = html_escape(' | '.join(tooltip_parts))
            threshold_icon = f'<span class="threshold-indicator" title="{tooltip_text}">⚙️</span>'

        rows += f"""
            <tr class="{row_class}" data-drug-code="{drug_code}"
                data-chart-data='{chart_data_json}'
                onclick="toggleInlineChart(this, '{drug_code}')"
                title="클릭하여 상세 차트 및 주문량 계산기 보기">
                <td title="{html_escape(str(row['약품명']))}">{threshold_icon}{drug_name_display}</td>
                <td>{row['약품코드']}</td>
                <td title="{html_escape(str(row['제약회사']))}">{row['제약회사']}</td>
                <td>{row[cm['stock']]:.0f}</td>
                <td>{row[cm['ma12']]:.1f}</td>
                <td>{row[cm['ma3']]:.1f}</td>
                <td class="{runway_class}">{runway_display}</td>
                <td class="{ma3_runway_class}">{ma3_runway_display}</td>
                <td class="{trend_class}" style="text-align: center; font-size: 16px;">{trend_icon}</td>
            </tr>
"""
    return rows


def generate_zero_stock_table_rows(df, col_map):
    """음수 재고 약품 테이블 행 HTML 생성 (약품유형 포함)"""
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
                <td style="color: #c62828; font-weight: bold;">{row[cm['stock']]:.0f}</td>
                <td><span style="background-color: {type_badge_color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px;">{drug_type}</span></td>
                <td>{row[cm['ma12']]:.1f}</td>
                <td>{row[cm['ma3']]:.1f}</td>
            </tr>
"""
    return rows


def generate_new_drugs_table_rows(df, col_map):
    """신규 약품 테이블 행 HTML 생성"""
    cm = col_map
    rows = ""
    for _, row in df.iterrows():
        stock = row[cm['stock']] if cm['stock'] in row else 0
        drug_type = row.get('약품유형', '미분류')
        type_badge_color = '#3498db' if drug_type == '전문약' else '#e67e22' if drug_type == '일반약' else '#95a5a6'
        rows += f"""
            <tr>
                <td>{row['약품명']}</td>
                <td>{row['약품코드']}</td>
                <td>{row['제약회사']}</td>
                <td style="text-align: right;">{stock:.0f}</td>
                <td><span style="background-color: {type_badge_color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px;">{drug_type}</span></td>
            </tr>
"""
    return rows


def generate_order_report_html(df, col_map=None, months=None, runway_threshold=1.0):
    """주문 보고서 HTML 생성 (재사용 가능한 함수)

    Args:
        df: 데이터프레임
        col_map: 컬럼명 매핑 딕셔너리 (선택사항)
            기본값: {'runway': '런웨이', 'ma3_runway': '3-MA 런웨이',
                    'stock': '현재 재고수량', 'ma12': '1년 이동평균', 'ma3': '3개월 이동평균'}
        months: 월 리스트 (차트용)
        runway_threshold: 긴급 주문 기준 런웨이 (개월), 기본값 1.0

    Returns:
        str: HTML 문자열
    """
    import drug_thresholds_db

    # 기본 컬럼명 (drug_order_calculator.py 스타일)
    default_map = {
        'runway': '런웨이',
        'ma3_runway': '3-MA 런웨이',
        'stock': '현재 재고수량',
        'ma12': '1년 이동평균',
        'ma3': '3개월 이동평균'
    }
    cm = col_map if col_map else default_map

    # 개별 임계값 로드
    custom_thresholds = drug_thresholds_db.get_threshold_dict()
    custom_threshold_count = len(custom_thresholds)

    # months가 없으면 빈 리스트
    if months is None:
        months = []

    # 신규 약품 분리 (시계열 데이터가 없는 약품) - 먼저 분리
    new_drugs_df = df[df['신규약품'] == True].copy() if '신규약품' in df.columns else pd.DataFrame()

    # 음수 재고 약품 분리 (신규 약품 제외 - 신규 약품은 이동평균이 없어서 별도 처리)
    zero_stock_df = df[df[cm['stock']] < 0].copy()
    if '신규약품' in zero_stock_df.columns:
        zero_stock_df = zero_stock_df[zero_stock_df['신규약품'] == False]
    zero_stock_df = zero_stock_df.sort_values(cm['stock'], ascending=True)
    zero_stock_count = len(zero_stock_df)
    new_drugs_count = len(new_drugs_df)
    if new_drugs_count > 0:
        new_drugs_df = new_drugs_df.sort_values('약품명', ascending=True)

    # 음수 재고 및 신규 약품 제외한 정상 약품
    normal_df = df[df[cm['stock']] >= 0].copy()
    if '신규약품' in normal_df.columns:
        normal_df = normal_df[normal_df['신규약품'] == False]

    # 약품 유형별 분리 (재고 >= 0이고 신규 약품이 아닌 약품만, 음수 재고/신규 약품은 모달에서 별도 표시)
    dispense_df = normal_df[normal_df['약품유형'] == '전문약'].copy()
    sale_df = normal_df[normal_df['약품유형'] == '일반약'].copy()
    unclassified_df = normal_df[normal_df['약품유형'] == '미분류'].copy()

    # 약품 유형별 개수
    dispense_count = len(dispense_df)
    sale_count = len(sale_df)
    unclassified_count = len(unclassified_df)

    # 긴급 주문 필요 약품 개수 (유형별, 재고 > 0인 약품 중)
    dispense_urgent = len(dispense_df[(dispense_df[cm['runway']] < runway_threshold) | (dispense_df[cm['ma3_runway']] < runway_threshold)])
    sale_urgent = len(sale_df[(sale_df[cm['runway']] < runway_threshold) | (sale_df[cm['ma3_runway']] < runway_threshold)])
    total_urgent = dispense_urgent + sale_urgent

    # 긴급 약품 우선 정렬 (글로벌 임계값 기준만)
    def is_urgent_check(row):
        runway = row[cm['runway']]
        ma3_runway = row[cm['ma3_runway']]

        # 글로벌 임계값 체크
        if runway < runway_threshold or ma3_runway < runway_threshold:
            return True

        return False

    # 긴급 여부 컬럼 추가 및 정렬 (긴급 약품 먼저, 그 다음 런웨이 오름차순)
    if len(dispense_df) > 0:
        dispense_df['_is_urgent'] = dispense_df.apply(is_urgent_check, axis=1)
        dispense_df = dispense_df.sort_values(['_is_urgent', cm['ma3_runway']], ascending=[False, True])

    if len(sale_df) > 0:
        sale_df['_is_urgent'] = sale_df.apply(is_urgent_check, axis=1)
        sale_df = sale_df.sort_values(['_is_urgent', cm['ma3_runway']], ascending=[False, True])

    # 테이블 행 생성 (months, runway_threshold, custom_thresholds 전달)
    dispense_rows = generate_table_rows(dispense_df, cm, months, runway_threshold, custom_thresholds)
    sale_rows = generate_table_rows(sale_df, cm, months, runway_threshold, custom_thresholds)
    zero_stock_rows = generate_zero_stock_table_rows(zero_stock_df, cm) if zero_stock_count > 0 else ""
    new_drugs_rows = generate_new_drugs_table_rows(new_drugs_df, cm) if new_drugs_count > 0 else ""

    # 음수 재고 경고 책갈피 HTML
    zero_stock_bookmark = f"""
        <div class="alert-bookmark warning" onclick="openZeroStockModal()">
            <span class="alert-icon">⚠️</span>
            <span class="alert-title">음수 재고</span>
            <span class="alert-count">{zero_stock_count}개</span>
        </div>
    """ if zero_stock_count > 0 else ""

    # 음수 재고 모달 HTML
    zero_stock_modal = f"""
    <div id="zeroStockModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>⚠️ 음수 재고 약품 ({zero_stock_count}개)</h3>
                <span class="modal-close" onclick="closeZeroStockModal()">&times;</span>
            </div>
            <div class="modal-body">
                <p style="color: #666; margin-bottom: 15px;">재고가 0 미만인 약품입니다. 즉시 주문이 필요합니다.</p>
                <table class="modal-table-zero-stock">
                    <thead>
                        <tr>
                            <th>약품명</th>
                            <th>약품코드</th>
                            <th>제약회사</th>
                            <th>현재 재고</th>
                            <th>약품유형</th>
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

    # 신규 약품 알림 책갈피 HTML
    new_drugs_bookmark = f"""
        <div class="alert-bookmark info" onclick="openNewDrugsModal()">
            <span class="alert-icon">🆕</span>
            <span class="alert-title">신규 약품</span>
            <span class="alert-count">{new_drugs_count}개</span>
        </div>
    """ if new_drugs_count > 0 else ""

    # 신규 약품 모달 HTML
    new_drugs_modal = f"""
    <div id="newDrugsModal" class="modal">
        <div class="modal-content">
            <div class="modal-header" style="background-color: #3498db;">
                <h3>🆕 신규 약품 ({new_drugs_count}개)</h3>
                <span class="modal-close" onclick="closeNewDrugsModal()">&times;</span>
            </div>
            <div class="modal-body">
                <p style="color: #666; margin-bottom: 15px;">시계열 데이터가 없는 신규 약품입니다. 다음 달 데이터 수집 후 런웨이 계산이 가능합니다.</p>
                <table class="modal-table-new-drugs">
                    <thead>
                        <tr>
                            <th>약품명</th>
                            <th>약품코드</th>
                            <th>제약회사</th>
                            <th>현재 재고</th>
                            <th>약품유형</th>
                        </tr>
                    </thead>
                    <tbody>
                        {new_drugs_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    """ if new_drugs_count > 0 else ""

    # 개별 임계값 설정 약품 목록 생성 (상태 분류 포함)
    def get_threshold_status(stock, stock_th, runway, runway_th):
        """
        상태 분류:
        - urgent: 재고 ≤ 임계값 × 50% 또는 런웨이 ≤ 임계값 × 50%
        - warning: 재고 ≤ 임계값 또는 런웨이 < 임계값
        - safe: 그 외
        """
        # 재고 임계값 체크
        if stock_th is not None:
            if stock <= stock_th * 0.5:
                return 'urgent'
            elif stock <= stock_th:
                return 'warning'

        # 런웨이 임계값 체크 (재고 임계값이 없거나 안전한 경우)
        if runway_th is not None:
            if runway <= runway_th * 0.5:
                return 'urgent'
            elif runway < runway_th:
                return 'warning'

        return 'safe'

    custom_threshold_drugs = []
    for _, row in df.iterrows():
        drug_code = str(row['약품코드'])
        if drug_code in custom_thresholds:
            ct = custom_thresholds[drug_code]
            stock = row[cm['stock']]
            stock_th = ct.get('절대재고_임계값')
            runway_th = ct.get('런웨이_임계값')

            # 런웨이 값 가져오기 (숫자로 변환)
            runway_val = row[cm['runway']]
            if isinstance(runway_val, str):
                try:
                    runway_val = float(runway_val.replace('개월', '').strip())
                except:
                    runway_val = 999
            runway_val = float(runway_val) if not pd.isna(runway_val) else 999

            # 상태 분류
            status = get_threshold_status(stock, stock_th, runway_val, runway_th)

            # 비율 계산 (재고 기준 또는 런웨이 기준)
            if stock_th is not None and stock_th > 0:
                ratio = (stock / stock_th) * 100
                ratio_type = 'stock'
            elif runway_th is not None and runway_th > 0:
                ratio = (runway_val / runway_th) * 100
                ratio_type = 'runway'
            else:
                ratio = 100
                ratio_type = 'none'

            # 주문 권장량 (재고 임계값 기준)
            order_qty = max(0, int(stock_th - stock)) if stock_th is not None else None

            # 3개월 이동평균 가져오기
            ma3_val = row[cm['ma3']] if not pd.isna(row[cm['ma3']]) else 0
            ma3_val = float(ma3_val)

            # 런웨이 기준 필요 수량 계산
            if runway_th is not None and runway_val < runway_th:
                runway_gap = runway_th - runway_val  # 부족한 개월 수
                runway_order_qty = int(runway_gap * ma3_val) if ma3_val > 0 else None
            else:
                runway_gap = None
                runway_order_qty = None

            custom_threshold_drugs.append({
                'code': drug_code,
                'name': row['약품명'],
                'company': row.get('제약회사', '-'),
                'stock': stock,
                'drug_type': row.get('약품유형', '미분류'),
                'stock_threshold': stock_th,
                'runway_threshold': runway_th,
                'memo': ct.get('메모', ''),
                'runway': runway_val,
                'status': status,
                'ratio': min(ratio, 200),  # 최대 200%로 제한
                'ratio_type': ratio_type,
                'order_qty': order_qty,
                'ma3': ma3_val,
                'runway_gap': runway_gap,
                'runway_order_qty': runway_order_qty
            })

    # 오늘 파일에 있는 약품 중 개별 임계값 설정된 약품 수로 업데이트
    custom_threshold_count = len(custom_threshold_drugs)

    # 상태별 분류
    urgent_drugs = [d for d in custom_threshold_drugs if d['status'] == 'urgent']
    warning_drugs = [d for d in custom_threshold_drugs if d['status'] == 'warning']
    safe_drugs = [d for d in custom_threshold_drugs if d['status'] == 'safe']
    attention_drugs = urgent_drugs + warning_drugs
    attention_count = len(attention_drugs)
    safe_count = len(safe_drugs)

    # 상태 카드 HTML 생성 함수
    def generate_status_card(drug):
        """개별 상태 카드 HTML 생성 - 임계값 유형별 레이아웃"""
        status = drug['status']
        status_class = status

        # 약품명 (최대 18자)
        name = drug['name'][:18] + '...' if len(drug['name']) > 18 else drug['name']

        # 임계값 유형 판단
        has_stock_th = drug['stock_threshold'] is not None
        has_runway_th = drug['runway_threshold'] is not None

        ratio = drug['ratio']

        # 메인 정보 생성 (유형별)
        if has_stock_th and has_runway_th:
            # 둘 다 설정된 경우: 두 줄로 표시, 프로그레스 바 없음
            stock_ratio = (drug['stock'] / drug['stock_threshold']) * 100 if drug['stock_threshold'] > 0 else 100
            runway_ratio = (drug['runway'] / drug['runway_threshold']) * 100 if drug['runway_threshold'] > 0 else 100
            main_html = f'''
                <div class="ct-card-row">
                    <span class="ct-row-icon">📦</span>
                    <span class="ct-row-label">현재고:</span>
                    <span class="ct-row-value">{drug['stock']:.0f}</span>
                    <span class="ct-row-sep">/</span>
                    <span class="ct-row-label">목표:</span>
                    <span class="ct-row-value">{drug['stock_threshold']}개</span>
                    <span class="ct-row-ratio">({stock_ratio:.0f}%)</span>
                </div>
                <div class="ct-card-row">
                    <span class="ct-row-icon">⏱️</span>
                    <span class="ct-row-label">런웨이:</span>
                    <span class="ct-row-value">{drug['runway']:.1f}</span>
                    <span class="ct-row-sep">/</span>
                    <span class="ct-row-label">목표:</span>
                    <span class="ct-row-value">{drug['runway_threshold']}개월</span>
                    <span class="ct-row-ratio">({runway_ratio:.0f}%)</span>
                </div>
            '''
            # 액션: 재고 기준 우선
            if drug['order_qty'] and drug['order_qty'] > 0:
                action_text = f"→ <strong>{drug['order_qty']}개</strong> 주문 권장"
            else:
                action_text = "✅ 재고 충분"
            show_progress = False

        elif has_stock_th:
            # 재고 임계값만
            main_html = f'''
                <div class="ct-card-main">
                    <span class="ct-main-icon">📦</span>
                    <span class="ct-main-label">현재고:</span>
                    <span class="ct-main-value">{drug['stock']:.0f}</span>
                    <span class="ct-main-sep">/</span>
                    <span class="ct-main-label">목표:</span>
                    <span class="ct-main-value">{drug['stock_threshold']}개</span>
                </div>
            '''
            if drug['order_qty'] and drug['order_qty'] > 0:
                action_text = f"→ <strong>{drug['order_qty']}개</strong> 주문 권장"
            else:
                action_text = "✅ 재고 충분"
            show_progress = True

        elif has_runway_th:
            # 런웨이 임계값만
            main_html = f'''
                <div class="ct-card-main">
                    <span class="ct-main-icon">⏱️</span>
                    <span class="ct-main-label">런웨이:</span>
                    <span class="ct-main-value">{drug['runway']:.1f}</span>
                    <span class="ct-main-sep">/</span>
                    <span class="ct-main-label">목표:</span>
                    <span class="ct-main-value">{drug['runway_threshold']}개월</span>
                </div>
            '''
            # 런웨이 기준 액션 가이드 (수량 포함)
            if drug.get('runway_gap') and drug.get('runway_order_qty'):
                action_text = f"→ <strong>{drug['runway_gap']:.1f}개월분({drug['runway_order_qty']}개)</strong> 추가 확보 필요"
            elif drug.get('runway_gap'):
                action_text = f"→ <strong>{drug['runway_gap']:.1f}개월분</strong> 추가 확보 필요"
            else:
                action_text = "✅ 런웨이 충분"
            show_progress = True

        else:
            # 임계값 없음 (예외)
            main_html = f'<div class="ct-card-main">{drug["stock"]:.0f}개</div>'
            action_text = "-"
            show_progress = False

        # 프로그레스 바 (단일 색상)
        progress_html = ""
        if show_progress:
            progress_html = f'''
                <div class="ct-card-progress">
                    <div class="ct-progress-bar">
                        <div class="ct-progress-fill" style="width: {min(ratio, 100)}%;"></div>
                    </div>
                    <span class="ct-progress-text">{ratio:.0f}%</span>
                </div>
            '''

        # 메모 표시 (있는 경우)
        memo_html = ""
        if drug.get('memo'):
            memo_text = drug['memo'][:30] + '...' if len(drug['memo']) > 30 else drug['memo']
            memo_html = f'<div class="ct-card-memo" title="{drug["memo"]}">📝 {memo_text}</div>'

        return f"""
            <div class="ct-status-card {status_class}">
                <div class="ct-card-name" title="{drug['name']}">{name}</div>
                {main_html}
                {progress_html}
                <div class="ct-card-action">{action_text}</div>
                {memo_html}
            </div>
        """

    # 상태 카드 HTML 생성
    attention_cards_html = ''.join([generate_status_card(d) for d in attention_drugs])
    safe_cards_html = ''.join([generate_status_card(d) for d in safe_drugs])

    # 테이블 행 HTML 생성
    custom_threshold_rows = ""
    for drug in custom_threshold_drugs:
        stock_th = f"{drug['stock_threshold']}개 이하" if drug['stock_threshold'] is not None else "-"
        runway_th = f"{drug['runway_threshold']}개월 미만" if drug['runway_threshold'] is not None else "-"
        drug_type = drug['drug_type']
        type_badge_color = '#3498db' if drug_type == '전문약' else '#e67e22' if drug_type == '일반약' else '#95a5a6'

        # 상태에 따른 행 스타일
        status_row_class = f"status-{drug['status']}"

        custom_threshold_rows += f"""
            <tr data-threshold-drug-code="{drug['code']}" class="{status_row_class}">
                <td>{drug['name']}</td>
                <td>{drug['code']}</td>
                <td>{drug['company']}</td>
                <td style="text-align: right;">{drug['stock']:.0f}</td>
                <td><span style="background-color: {type_badge_color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px;">{drug_type}</span></td>
                <td style="text-align: center;">{stock_th}</td>
                <td style="text-align: center;">{runway_th}</td>
                <td>{drug['memo'] or '-'}</td>
            </tr>
"""

    # 개별 설정 책갈피 HTML (주의 필요 개수 표시)
    bookmark_count_text = f"{attention_count}개 주의" if attention_count > 0 else f"{custom_threshold_count}개"
    custom_threshold_bookmark = f"""
        <div class="alert-bookmark custom" onclick="openCustomThresholdModal()">
            <span class="alert-icon">⚙️</span>
            <span class="alert-title">개별 설정</span>
            <span class="alert-count">{bookmark_count_text}</span>
        </div>
    """ if custom_threshold_count > 0 else ""

    # 상태 카드 섹션 HTML
    status_cards_section = ""
    if attention_count > 0 or safe_count > 0:
        status_cards_section = f"""
            <div class="ct-status-section">
                <!-- 주의 필요 섹션 -->
                {"" if attention_count == 0 else f'''
                <div class="ct-attention-header">
                    <span class="ct-attention-icon">⚠️</span>
                    <span class="ct-attention-title">주의 필요</span>
                    <span class="ct-attention-count">({attention_count}개)</span>
                </div>
                <div class="ct-cards-container">
                    {attention_cards_html}
                </div>
                '''}

                <!-- 안전 섹션 (접기/펼치기) -->
                {"" if safe_count == 0 else f'''
                <div class="ct-safe-section">
                    <div class="ct-safe-header" onclick="toggleSafeCards()">
                        <span class="ct-safe-icon">✅</span>
                        <span class="ct-safe-title">안전</span>
                        <span class="ct-safe-count">({safe_count}개)</span>
                        <span class="ct-safe-toggle" id="safeToggleIcon">▼</span>
                    </div>
                    <div class="ct-safe-cards" id="safeCardsContainer" style="display: none;">
                        {safe_cards_html}
                    </div>
                </div>
                '''}
            </div>
        """

    # 개별 설정 모달 HTML (상태 카드 섹션 + 테이블)
    custom_threshold_modal = f"""
    <div id="customThresholdModal" class="modal">
        <div class="modal-content" style="max-width: 1200px;">
            <div class="modal-header" style="background-color: #805ad5;">
                <h3>⚙️ 개별 임계값 설정 약품 (<span id="customThresholdModalCount">{custom_threshold_count}</span>개)</h3>
                <span class="modal-close" onclick="closeCustomThresholdModal()">&times;</span>
            </div>
            <div class="modal-body">
                {status_cards_section}

                <!-- 전체 목록 테이블 -->
                <div class="ct-table-section">
                    <div class="ct-table-header">📋 전체 목록</div>
                    <table class="modal-table-threshold">
                        <thead>
                            <tr>
                                <th>약품명</th>
                                <th>약품코드</th>
                                <th>제약회사</th>
                                <th>현재 재고</th>
                                <th>약품유형</th>
                                <th>재고 임계값</th>
                                <th>런웨이 임계값</th>
                                <th>메모</th>
                            </tr>
                        </thead>
                        <tbody id="customThresholdTbody">
                            {custom_threshold_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    """ if custom_threshold_count > 0 else ""

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
        /* 요약 대시보드 스타일 */
        .summary-dashboard {{
            background-color: #fff;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .summary-dashboard h2 {{
            margin: 0 0 20px 0;
            color: #2d3748;
            font-size: 18px;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 12px;
        }}
        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 20px;
        }}
        .summary-card {{
            background: linear-gradient(135deg, #f7fafc 0%, #edf2f7 100%);
            border-radius: 10px;
            padding: 16px;
            text-align: center;
            border: 1px solid #e2e8f0;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .summary-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        .summary-card .icon {{
            font-size: 24px;
            margin-bottom: 8px;
        }}
        .summary-card .label {{
            font-size: 12px;
            color: #718096;
            margin-bottom: 4px;
        }}
        .summary-card .value {{
            font-size: 32px;
            font-weight: bold;
            color: #2d3748;
        }}
        .summary-card .unit {{
            font-size: 14px;
            color: #718096;
            font-weight: normal;
        }}
        .summary-card.dispense {{
            border-left: 4px solid #3182ce;
        }}
        .summary-card.sale {{
            border-left: 4px solid #38a169;
        }}
        .summary-card.total {{
            border-left: 4px solid #805ad5;
        }}
        .urgent-section {{
            background: linear-gradient(135deg, #f7fafc 0%, #edf2f7 100%);
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 16px 20px;
            margin-bottom: 16px;
        }}
        .urgent-section h3 {{
            margin: 0 0 12px 0;
            color: #4a5568;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .urgent-cards {{
            display: flex;
            gap: 16px;
            flex-wrap: wrap;
        }}
        .urgent-card {{
            background: white;
            border-radius: 8px;
            padding: 12px 20px;
            display: flex;
            align-items: center;
            gap: 12px;
            border: 1px solid #e2e8f0;
        }}
        .urgent-card .dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #718096;
        }}
        .urgent-card .type {{
            font-size: 13px;
            color: #718096;
        }}
        .urgent-card .count {{
            font-size: 20px;
            font-weight: bold;
            color: #2d3748;
        }}
        .urgent-card.total-urgent {{
            background: #4a5568;
            border-color: #4a5568;
        }}
        .urgent-card.total-urgent .type,
        .urgent-card.total-urgent .count {{
            color: white;
        }}
        .urgent-card.total-urgent .dot {{
            background: white;
        }}
        .negative-stock-alert {{
            background: linear-gradient(135deg, #fffaf0 0%, #feebc8 100%);
            border: 1px solid #ed8936;
            border-radius: 8px;
            padding: 12px 20px;
            display: flex;
            align-items: center;
            gap: 12px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .negative-stock-alert:hover {{
            background: linear-gradient(135deg, #feebc8 0%, #fbd38d 100%);
        }}
        .negative-stock-alert .icon {{
            font-size: 20px;
        }}
        .negative-stock-alert .text {{
            flex: 1;
            font-size: 14px;
            color: #c05621;
        }}
        .negative-stock-alert .count {{
            font-size: 24px;
            font-weight: bold;
            color: #c05621;
        }}

        /* 알림 사이드바 (책갈피 스타일) */
        .alert-sidebar {{
            position: fixed;
            right: 0;
            top: 120px;
            z-index: 999;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}
        .alert-bookmark {{
            position: relative;
            right: -120px;
            padding: 12px 16px;
            border-radius: 12px 0 0 12px;
            cursor: pointer;
            transition: right 0.3s ease, box-shadow 0.3s ease, transform 0.2s ease;
            min-width: 160px;
            font-weight: 600;
            display: flex;
            flex-direction: column;
            gap: 4px;
            user-select: none;
            /* Glassmorphism */
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-right: none;
        }}
        .alert-bookmark:hover {{
            right: 0;
            transform: scale(1.02);
        }}
        .alert-bookmark .alert-icon {{
            font-size: 1.2em;
        }}
        .alert-bookmark .alert-title {{
            font-size: 0.85em;
            opacity: 0.85;
        }}
        .alert-bookmark .alert-count {{
            font-size: 1.5em;
            font-weight: bold;
        }}
        .alert-bookmark.warning {{
            background: linear-gradient(135deg, rgba(239, 83, 80, 0.75) 0%, rgba(198, 40, 40, 0.85) 100%);
            box-shadow: -4px 4px 20px rgba(198, 40, 40, 0.3);
            color: white;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
        }}
        .alert-bookmark.warning:hover {{
            box-shadow: -6px 6px 24px rgba(198, 40, 40, 0.4);
        }}
        .alert-bookmark.info {{
            background: linear-gradient(135deg, rgba(66, 165, 245, 0.75) 0%, rgba(21, 101, 192, 0.85) 100%);
            box-shadow: -4px 4px 20px rgba(21, 101, 192, 0.3);
            color: white;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
        }}
        .alert-bookmark.info:hover {{
            box-shadow: -6px 6px 24px rgba(21, 101, 192, 0.4);
        }}
        .alert-bookmark.custom {{
            background: linear-gradient(135deg, rgba(128, 90, 213, 0.75) 0%, rgba(91, 33, 182, 0.85) 100%);
            box-shadow: -4px 4px 20px rgba(91, 33, 182, 0.3);
            color: white;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
        }}
        .alert-bookmark.custom:hover {{
            box-shadow: -6px 6px 24px rgba(91, 33, 182, 0.4);
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
        /* 모달 테이블 공통 스타일 */
        .modal-body table {{
            table-layout: auto;
            width: 100%;
        }}
        /* 음수 재고 모달 (7컬럼): 약품명, 약품코드, 제약회사, 현재재고, 약품유형, 1년MA, 3개월MA */
        .modal-table-zero-stock th:nth-child(1),
        .modal-table-zero-stock td:nth-child(1) {{ width: 30%; }}  /* 약품명 */
        .modal-table-zero-stock th:nth-child(2),
        .modal-table-zero-stock td:nth-child(2) {{ width: 10%; white-space: nowrap; }}  /* 약품코드 */
        .modal-table-zero-stock th:nth-child(3),
        .modal-table-zero-stock td:nth-child(3) {{ width: 12%; }}  /* 제약회사 */
        .modal-table-zero-stock th:nth-child(4),
        .modal-table-zero-stock td:nth-child(4) {{ width: 10%; white-space: nowrap; text-align: right; }}  /* 현재 재고 */
        .modal-table-zero-stock th:nth-child(5),
        .modal-table-zero-stock td:nth-child(5) {{ width: 8%; white-space: nowrap; }}  /* 약품유형 */
        .modal-table-zero-stock th:nth-child(6),
        .modal-table-zero-stock td:nth-child(6) {{ width: 15%; white-space: nowrap; text-align: right; }}  /* 1년 이동평균 */
        .modal-table-zero-stock th:nth-child(7),
        .modal-table-zero-stock td:nth-child(7) {{ width: 15%; white-space: nowrap; text-align: right; }}  /* 3개월 이동평균 */
        /* 신규 약품 모달 (5컬럼): 약품명, 약품코드, 제약회사, 현재재고, 약품유형 */
        .modal-table-new-drugs th:nth-child(1),
        .modal-table-new-drugs td:nth-child(1) {{ width: 40%; }}  /* 약품명 */
        .modal-table-new-drugs th:nth-child(2),
        .modal-table-new-drugs td:nth-child(2) {{ width: 15%; white-space: nowrap; }}  /* 약품코드 */
        .modal-table-new-drugs th:nth-child(3),
        .modal-table-new-drugs td:nth-child(3) {{ width: 18%; }}  /* 제약회사 */
        .modal-table-new-drugs th:nth-child(4),
        .modal-table-new-drugs td:nth-child(4) {{ width: 12%; white-space: nowrap; text-align: right; }}  /* 현재 재고 */
        .modal-table-new-drugs th:nth-child(5),
        .modal-table-new-drugs td:nth-child(5) {{ width: 10%; white-space: nowrap; }}  /* 약품유형 */
        /* 개별 임계값 모달 (8컬럼): 약품명, 약품코드, 제약회사, 현재재고, 약품유형, 재고임계값, 런웨이임계값, 메모 */
        .modal-table-threshold th:nth-child(1),
        .modal-table-threshold td:nth-child(1) {{ width: 22%; }}  /* 약품명 */
        .modal-table-threshold th:nth-child(2),
        .modal-table-threshold td:nth-child(2) {{ width: 10%; white-space: nowrap; }}  /* 약품코드 */
        .modal-table-threshold th:nth-child(3),
        .modal-table-threshold td:nth-child(3) {{ width: 10%; }}  /* 제약회사 */
        .modal-table-threshold th:nth-child(4),
        .modal-table-threshold td:nth-child(4) {{ width: 8%; white-space: nowrap; text-align: right; }}  /* 현재 재고 */
        .modal-table-threshold th:nth-child(5),
        .modal-table-threshold td:nth-child(5) {{ width: 8%; white-space: nowrap; }}  /* 약품유형 */
        .modal-table-threshold th:nth-child(6),
        .modal-table-threshold td:nth-child(6) {{ width: 12%; white-space: nowrap; text-align: center; }}  /* 재고 임계값 */
        .modal-table-threshold th:nth-child(7),
        .modal-table-threshold td:nth-child(7) {{ width: 14%; white-space: nowrap; text-align: center; }}  /* 런웨이 임계값 */
        .modal-table-threshold th:nth-child(8),
        .modal-table-threshold td:nth-child(8) {{ width: 16%; word-break: break-word; }}  /* 메모 */

        /* 상태 카드 섹션 스타일 */
        .ct-status-section {{
            margin-bottom: 24px;
            padding-bottom: 20px;
            border-bottom: 1px solid #e2e8f0;
        }}
        .ct-attention-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 14px;
            font-size: 15px;
            font-weight: 600;
            color: #c53030;
        }}
        .ct-attention-icon {{
            font-size: 18px;
        }}
        .ct-attention-count {{
            background: #fed7d7;
            color: #c53030;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }}
        .ct-cards-container {{
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
            margin-bottom: 16px;
        }}
        /* 개별 상태 카드 - 단순화된 디자인 */
        .ct-status-card {{
            width: 317px;
            background: #ffffff;
            border-radius: 10px;
            padding: 14px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }}
        .ct-status-card:hover {{
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        /* 좌측 테두리만 상태 색상 */
        .ct-status-card.urgent {{ border-left: 4px solid #e53e3e; }}
        .ct-status-card.warning {{ border-left: 4px solid #dd6b20; }}
        .ct-status-card.safe {{ border-left: 4px solid #38a169; }}

        /* 약품명 */
        .ct-card-name {{
            font-size: 14px;
            font-weight: 600;
            color: #1a202c;
            margin-bottom: 12px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        /* 메인 정보 (단일 행) */
        .ct-card-main {{
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 4px;
            font-size: 14px;
            color: #4a5568;
            margin-bottom: 10px;
        }}
        .ct-main-icon {{ font-size: 14px; }}
        .ct-main-label {{ color: #718096; font-size: 12px; }}
        .ct-main-value {{ font-weight: 600; color: #2d3748; }}
        .ct-main-sep {{ color: #a0aec0; }}

        /* 메인 정보 (복수 행 - 둘 다 설정) */
        .ct-card-row {{
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 3px;
            font-size: 12px;
            color: #4a5568;
            margin-bottom: 6px;
        }}
        .ct-row-icon {{ font-size: 12px; }}
        .ct-row-label {{ color: #718096; }}
        .ct-row-value {{ font-weight: 600; color: #2d3748; }}
        .ct-row-sep {{ color: #a0aec0; }}
        .ct-row-ratio {{ color: #a0aec0; font-size: 11px; }}

        /* 메모 표시 */
        .ct-card-memo {{
            font-size: 11px;
            color: #718096;
            margin-top: 8px;
            padding: 6px 8px;
            background: #f7fafc;
            border-radius: 4px;
            border-left: 2px solid #cbd5e0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        /* 프로그레스 바 - 단일 색상 */
        .ct-card-progress {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 12px;
        }}
        .ct-progress-bar {{
            flex: 1;
            height: 6px;
            background: #e2e8f0;
            border-radius: 3px;
            overflow: hidden;
        }}
        .ct-progress-fill {{
            height: 100%;
            background: #4299e1;  /* 단일 파란색 */
            border-radius: 3px;
        }}
        .ct-progress-text {{
            font-size: 12px;
            color: #718096;
            min-width: 35px;
        }}

        /* 액션 가이드 */
        .ct-card-action {{
            font-size: 14px;
            color: #1a202c;
            font-weight: 400;
            padding: 10px 12px;
            margin-top: 10px;
            background: #fffbeb;
            border-radius: 6px;
            border-left: 3px solid #d69e2e;
        }}
        .ct-card-action strong {{
            font-weight: 700;
            color: #b7791f;
        }}
        /* 안전 섹션 (접기/펼치기) */
        .ct-safe-section {{
            margin-top: 20px;
        }}
        .ct-safe-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 12px 16px;
            background: #f7fafc;
            border: 1px solid #e2e8f0;
            border-left: 4px solid #38a169;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 14px;
        }}
        .ct-safe-header:hover {{
            background: #edf2f7;
        }}
        .ct-safe-icon {{
            font-size: 16px;
        }}
        .ct-safe-title {{
            font-weight: 600;
            color: #276749;
        }}
        .ct-safe-count {{
            color: #38a169;
            font-weight: 500;
        }}
        .ct-safe-toggle {{
            margin-left: auto;
            color: #38a169;
            transition: transform 0.3s;
            font-size: 12px;
        }}
        .ct-safe-toggle.expanded {{
            transform: rotate(180deg);
        }}
        .ct-safe-cards {{
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
            padding: 16px 0;
        }}
        /* 테이블 섹션 */
        .ct-table-section {{
            margin-top: 24px;
        }}
        .ct-table-header {{
            font-size: 15px;
            font-weight: 600;
            color: #4a5568;
            margin-bottom: 14px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e2e8f0;
        }}
        /* 테이블 상태 행 스타일 */
        .modal-table-threshold tr.status-urgent {{
            background-color: rgba(229, 62, 62, 0.08);
        }}
        .modal-table-threshold tr.status-warning {{
            background-color: rgba(221, 107, 32, 0.08);
        }}
        .modal-table-threshold tr.status-safe {{
            background-color: rgba(56, 161, 105, 0.05);
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
            background-color: #dd6b20;
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
            table-layout: fixed;
        }}
        th {{
            background-color: #34495e;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: bold;
        }}
        /* 컬럼 너비 지정 */
        th:nth-child(1), td:nth-child(1) {{ width: 40%; }}  /* 약품명 */
        th:nth-child(2), td:nth-child(2) {{ width: 7%; }}   /* 약품코드 */
        th:nth-child(3), td:nth-child(3) {{ width: 9%; }}   /* 제약회사 */
        th:nth-child(4), td:nth-child(4) {{ width: 5%; }}   /* 현재 재고 */
        th:nth-child(5), td:nth-child(5) {{ width: 6%; }}   /* 1년 평균 */
        th:nth-child(6), td:nth-child(6) {{ width: 7%; }}   /* 3개월 평균 */
        th:nth-child(7), td:nth-child(7) {{ width: 7%; }}   /* 런웨이 */
        th:nth-child(8), td:nth-child(8) {{ width: 7%; }}   /* 3-MA 런웨이 */
        th:nth-child(9), td:nth-child(9) {{ width: 5%; }}   /* 트렌드 */
        td {{
            padding: 10px;
            border-bottom: 1px solid #ddd;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        tr:hover {{
            background-color: #f9f9f9;
        }}
        .urgent-row {{
            background-color: #fffbeb !important;
        }}
        .urgent-cell {{
            color: #c05621;
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

        /* 인라인 차트용 클릭 가능 행 스타일 */
        .clickable-row {{
            cursor: pointer;
            transition: background-color 0.2s;
        }}
        .clickable-row:hover {{
            background-color: #edf2f7 !important;
        }}

        /* 개별 임계값 표시 아이콘 */
        .threshold-indicator {{
            margin-right: 6px;
            cursor: help;
            font-size: 14px;
            opacity: 0.8;
        }}
        .threshold-indicator:hover {{
            opacity: 1;
        }}

        /* 트렌드 아이콘 스타일 */
        .trend-up {{
            color: #e53e3e;
        }}
        .trend-down {{
            color: #3182ce;
        }}
        .trend-stable {{
            color: #718096;
        }}
        .clickable-row.chart-expanded {{
            background-color: rgba(79, 172, 254, 0.15) !important;
            border-left: 3px solid #4facfe;
        }}
        .inline-chart-row {{
            background: #f8fafc;
        }}
        .inline-chart-row:hover {{
            background: #f8fafc !important;
        }}

        /* 주문량 계산기 스타일 */
        .order-calculator {{
            background: #fff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        }}
        .order-calculator h4 {{
            margin: 0 0 12px 0;
            color: #2d3748;
            font-size: 14px;
        }}
        .runway-buttons {{
            display: flex;
            gap: 8px;
            margin-bottom: 16px;
        }}
        .runway-btn {{
            padding: 8px 16px;
            border: 2px solid #e2e8f0;
            background: #fff;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            transition: all 0.2s;
        }}
        .runway-btn:hover {{
            border-color: #4facfe;
            background: #f0f9ff;
        }}
        .runway-btn.active {{
            border-color: #4facfe;
            background: #4facfe;
            color: white;
        }}
        .order-result {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        .order-result-item {{
            background: #f7fafc;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 12px;
            text-align: center;
        }}
        .order-result-item .label {{
            font-size: 12px;
            color: #718096;
            margin-bottom: 4px;
        }}
        .order-result-item .ma-value {{
            font-size: 11px;
            color: #a0aec0;
            margin-bottom: 8px;
        }}
        .order-result-item .value {{
            font-size: 20px;
            font-weight: bold;
            color: #2d3748;
        }}
        .order-context-header {{
            font-size: 14px;
            color: #4a5568;
            margin-bottom: 16px;
            padding: 10px 12px;
            background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
            border-radius: 6px;
            border-left: 3px solid #4facfe;
        }}
        .order-context-header .emoji {{
            margin-right: 6px;
        }}
        .order-context-header .months {{
            font-weight: bold;
            color: #2563eb;
        }}
        /* 단일 프로그레스바 스타일 (목표 마커 포함) */
        .runway-progress-single {{
            margin: 8px 0;
        }}
        .runway-progress-labels {{
            font-size: 11px;
            color: #718096;
            margin-bottom: 4px;
            display: flex;
            justify-content: space-between;
        }}
        .runway-progress-labels .current-label {{
            color: #2d3748;
            font-weight: 600;
        }}
        .runway-progress-labels .target-label {{
            color: #718096;
        }}
        .progress-bar-wrapper {{
            position: relative;
            width: 100%;
            height: 16px;
            background: #e2e8f0;
            border-radius: 8px;
            overflow: hidden;
        }}
        .progress-bar-fill {{
            height: 100%;
            border-radius: 8px;
            transition: width 0.3s ease, background 0.3s ease;
        }}
        .progress-bar-fill.shortage {{
            background: linear-gradient(90deg, #f56565 0%, #fc8181 100%);
        }}
        .progress-bar-fill.sufficient {{
            background: linear-gradient(90deg, #48bb78 0%, #68d391 100%);
        }}
        .target-marker {{
            position: absolute;
            top: -2px;
            bottom: -2px;
            width: 3px;
            background: #2d3748;
            border-radius: 2px;
            z-index: 2;
        }}
        .target-marker::after {{
            content: '▼';
            position: absolute;
            top: -14px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 8px;
            color: #2d3748;
        }}
        .order-value {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            margin-top: 8px;
            font-size: 16px;
            font-weight: bold;
            color: #2d3748;
        }}
        .order-value.no-order {{
            color: #38a169;
        }}
        .order-value .arrow {{
            color: #4facfe;
        }}
        .current-stock-note {{
            font-size: 12px;
            color: #718096;
            margin-top: 12px;
        }}
    </style>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
</head>
<body>
    <div class="header">
        <h1>📦 약 주문 수량 산출 보고서</h1>
        <p>생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 강조 기준: 런웨이 {runway_threshold}개월 미만</p>
    </div>

    <div class="alert-sidebar">
        {zero_stock_bookmark}
        {new_drugs_bookmark}
        {custom_threshold_bookmark}
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
                        <th>트렌드</th>
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
                        <th>트렌드</th>
                    </tr>
                </thead>
                <tbody>
                    {sale_rows}
                </tbody>
            </table>''' if sale_count > 0 else '<div class="empty-message">오늘 나간 일반약이 없습니다.</div>'}
        </div>
    </div>

    {zero_stock_modal}
    {new_drugs_modal}
    {custom_threshold_modal}

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

        // 신규 약품 모달 열기/닫기
        function openNewDrugsModal() {{
            document.getElementById('newDrugsModal').style.display = 'block';
        }}
        function closeNewDrugsModal() {{
            document.getElementById('newDrugsModal').style.display = 'none';
        }}

        // 개별 설정 모달 열기/닫기
        function openCustomThresholdModal() {{
            document.getElementById('customThresholdModal').style.display = 'block';
        }}
        function closeCustomThresholdModal() {{
            document.getElementById('customThresholdModal').style.display = 'none';
        }}

        // 안전 카드 접기/펼치기
        function toggleSafeCards() {{
            const container = document.getElementById('safeCardsContainer');
            const toggleIcon = document.getElementById('safeToggleIcon');
            if (!container || !toggleIcon) return;

            if (container.style.display === 'none') {{
                container.style.display = 'flex';
                toggleIcon.classList.add('expanded');
                toggleIcon.textContent = '▲';
            }} else {{
                container.style.display = 'none';
                toggleIcon.classList.remove('expanded');
                toggleIcon.textContent = '▼';
            }}
        }}

        // 모달 외부 클릭 시 닫기
        window.onclick = function(event) {{
            var zeroModal = document.getElementById('zeroStockModal');
            var newDrugsModal = document.getElementById('newDrugsModal');
            var customModal = document.getElementById('customThresholdModal');
            if (event.target == zeroModal) {{
                zeroModal.style.display = 'none';
            }}
            if (event.target == newDrugsModal) {{
                newDrugsModal.style.display = 'none';
            }}
            if (event.target == customModal) {{
                customModal.style.display = 'none';
            }}
        }}

        // ========== 인라인 차트 기능 ==========

        // 현재 열린 차트의 drugCode 저장
        var currentChartDrugCode = null;

        // 인라인 차트 닫기
        function closeInlineChart(drugCode) {{
            event.stopPropagation();
            const chartRow = document.querySelector('.inline-chart-row');
            if (chartRow) chartRow.remove();
            const expandedRow = document.querySelector('tr[data-drug-code="' + drugCode + '"].chart-expanded');
            if (expandedRow) expandedRow.classList.remove('chart-expanded');
            currentChartDrugCode = null;
        }}

        // 인라인 차트 토글
        function toggleInlineChart(row, drugCode) {{
            const existingChartRow = row.nextElementSibling;

            // 이미 차트가 열려있으면 닫기
            if (existingChartRow && existingChartRow.classList.contains('inline-chart-row')) {{
                existingChartRow.remove();
                row.classList.remove('chart-expanded');
                currentChartDrugCode = null;
                return;
            }}

            // 다른 열린 차트들 닫기
            document.querySelectorAll('.inline-chart-row').forEach(el => el.remove());
            document.querySelectorAll('.chart-expanded').forEach(el => el.classList.remove('chart-expanded'));

            // 차트 데이터 가져오기
            const chartDataStr = row.getAttribute('data-chart-data');
            if (!chartDataStr) {{
                console.error('차트 데이터가 없습니다:', drugCode);
                return;
            }}

            const chartData = JSON.parse(chartDataStr);
            currentChartDrugCode = drugCode;
            const colSpan = row.cells.length;

            // 차트 행 생성
            const chartRow = document.createElement('tr');
            chartRow.className = 'inline-chart-row';
            chartRow.innerHTML = `
                <td colspan="${{colSpan}}" style="padding: 20px; background: #f8fafc; border-left: 4px solid #4facfe; position: relative;">
                    <button onclick="closeInlineChart('${{drugCode}}')"
                            style="position: absolute; top: 10px; right: 15px; background: none; border: none; font-size: 24px; cursor: pointer; color: #718096; z-index: 10;">&times;</button>

                    <!-- 좌측(60%): 차트 / 우측(40%): 주문량계산기 -->
                    <div style="display: flex; gap: 20px; align-items: stretch;">
                        <!-- 좌측 섹션: 트렌드 차트 -->
                        <div style="flex: 6; min-width: 0;">
                            <div id="inline-chart-${{drugCode}}" style="width: 100%; height: 320px;"></div>
                        </div>

                        <!-- 주문량 계산기 (40%) -->
                        <div class="order-calculator" style="flex: 4; margin-bottom: 0;">
                            <h4>📦 주문량 계산기</h4>
                            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap;">
                                <div class="runway-buttons" style="margin-bottom: 0;">
                                    <button class="runway-btn" onclick="calculateOrder(1, '${{drugCode}}')">1개월</button>
                                    <button class="runway-btn" onclick="calculateOrder(2, '${{drugCode}}')">2개월</button>
                                    <button class="runway-btn active" onclick="calculateOrder(3, '${{drugCode}}')">3개월</button>
                                </div>
                                <div class="order-context-header" id="order-context-${{drugCode}}" style="margin: 0; flex: 1;">
                                    <span class="emoji">💡</span><span class="months">3개월</span>치 재고를 확보하려면:
                                </div>
                            </div>
                            <div class="order-result">
                                <!-- 3개월 평균 기준 (위) -->
                                <div class="order-result-item">
                                    <div class="label">3개월 평균 기준 <span style="color:#a0aec0;">(${{chartData.ma3.toFixed(1)}}개/월)</span></div>
                                    <div class="runway-progress-single">
                                        <div class="runway-progress-labels">
                                            <span class="current-label" id="runway-ma3-current-${{drugCode}}">현재 0.00개월</span>
                                            <span class="target-label" id="runway-ma3-target-${{drugCode}}">목표 3개월</span>
                                        </div>
                                        <div class="progress-bar-wrapper">
                                            <div class="progress-bar-fill shortage" id="progress-ma3-fill-${{drugCode}}" style="width: 0%;"></div>
                                            <div class="target-marker" id="marker-ma3-${{drugCode}}" style="left: 50%;"></div>
                                        </div>
                                    </div>
                                    <div class="order-value" id="order-value-ma3-${{drugCode}}">
                                        <span class="arrow">👉</span>
                                        <span id="order-ma3-${{drugCode}}">-</span>
                                        <span style="font-size:13px; font-weight:normal; color:#718096;">주문 필요</span>
                                    </div>
                                </div>
                                <!-- 1년 평균 기준 (아래) -->
                                <div class="order-result-item">
                                    <div class="label">1년 평균 기준 <span style="color:#a0aec0;">(${{chartData.ma12.toFixed(1)}}개/월)</span></div>
                                    <div class="runway-progress-single">
                                        <div class="runway-progress-labels">
                                            <span class="current-label" id="runway-ma12-current-${{drugCode}}">현재 0.00개월</span>
                                            <span class="target-label" id="runway-ma12-target-${{drugCode}}">목표 3개월</span>
                                        </div>
                                        <div class="progress-bar-wrapper">
                                            <div class="progress-bar-fill shortage" id="progress-ma12-fill-${{drugCode}}" style="width: 0%;"></div>
                                            <div class="target-marker" id="marker-ma12-${{drugCode}}" style="left: 50%;"></div>
                                        </div>
                                    </div>
                                    <div class="order-value" id="order-value-ma12-${{drugCode}}">
                                        <span class="arrow">👉</span>
                                        <span id="order-ma12-${{drugCode}}">-</span>
                                        <span style="font-size:13px; font-weight:normal; color:#718096;">주문 필요</span>
                                    </div>
                                </div>
                            </div>
                            <div class="current-stock-note">* 현재 재고: ${{chartData.stock.toLocaleString()}}개</div>
                        </div>
                    </div>

                </td>
            `;

            row.after(chartRow);
            row.classList.add('chart-expanded');

            // 차트 렌더링
            renderInlineChart(drugCode, chartData);

            // 기본 3개월 주문량 계산
            calculateOrder(3, drugCode);
        }}

        // 주문량 계산
        function calculateOrder(targetMonths, drugCode) {{
            // 버튼 상태 업데이트 - inline-chart-row 내의 버튼만 선택
            const chartRow = document.querySelector('.inline-chart-row');
            if (chartRow) {{
                const buttons = chartRow.querySelectorAll('.runway-btn');
                buttons.forEach(btn => {{
                    btn.classList.remove('active');
                    if (btn.textContent.trim() === targetMonths + '개월') {{
                        btn.classList.add('active');
                    }}
                }});
            }}

            // 차트 데이터 가져오기
            const row = document.querySelector(`tr[data-drug-code="${{drugCode}}"]`);
            const chartData = JSON.parse(row.getAttribute('data-chart-data'));

            const stock = chartData.stock;
            const ma12 = chartData.ma12;
            const ma3 = chartData.ma3;

            // 현재 런웨이 계산
            const currentRunwayMa12 = ma12 > 0 ? stock / ma12 : 0;
            const currentRunwayMa3 = ma3 > 0 ? stock / ma3 : 0;

            // 주문량 계산: (목표 런웨이 × 월 평균) - 현재 재고
            const orderMa12 = Math.max(0, Math.ceil((targetMonths * ma12) - stock));
            const orderMa3 = Math.max(0, Math.ceil((targetMonths * ma3) - stock));

            // 컨텍스트 헤더 업데이트
            const contextHeader = document.getElementById(`order-context-${{drugCode}}`);
            if (contextHeader) {{
                contextHeader.innerHTML = `<span class="emoji">💡</span><span class="months">${{targetMonths}}개월</span>치 재고를 확보하려면:`;
            }}

            // 단일 프로그레스바 업데이트 함수
            function updateSingleProgressBar(prefix, currentRunway, targetRunway, orderQty) {{
                // 최대 표시 범위: 목표의 2배 (overflow 방지)
                const maxDisplay = targetRunway * 2;

                // 현재 런웨이 퍼센트 (최대 100%로 제한)
                const fillPercent = Math.min((currentRunway / maxDisplay) * 100, 100);

                // 목표 마커 위치 (항상 50% = maxDisplay의 절반)
                const markerPercent = 50;

                // 부족/충분 상태 판단
                const isSufficient = currentRunway >= targetRunway;

                // 라벨 업데이트
                document.getElementById(`runway-${{prefix}}-current-${{drugCode}}`).textContent =
                    `현재 ${{currentRunway.toFixed(2)}}개월`;
                document.getElementById(`runway-${{prefix}}-target-${{drugCode}}`).textContent =
                    `목표 ${{targetRunway}}개월`;

                // 프로그레스바 채우기
                const fillEl = document.getElementById(`progress-${{prefix}}-fill-${{drugCode}}`);
                fillEl.style.width = fillPercent + '%';
                fillEl.classList.remove('shortage', 'sufficient');
                fillEl.classList.add(isSufficient ? 'sufficient' : 'shortage');

                // 목표 마커 위치
                document.getElementById(`marker-${{prefix}}-${{drugCode}}`).style.left = markerPercent + '%';

                // 주문량 결과 업데이트
                const orderValueEl = document.getElementById(`order-value-${{prefix}}-${{drugCode}}`);
                const orderTextEl = document.getElementById(`order-${{prefix}}-${{drugCode}}`);

                if (orderQty > 0) {{
                    orderValueEl.classList.remove('no-order');
                    orderValueEl.innerHTML = `
                        <span class="arrow">👉</span>
                        <span>${{orderQty.toLocaleString()}}개</span>
                        <span style="font-size:13px; font-weight:normal; color:#718096;">주문 필요</span>
                    `;
                }} else {{
                    orderValueEl.classList.add('no-order');
                    const surplus = Math.round((currentRunway - targetRunway) * 10) / 10;
                    orderValueEl.innerHTML = `
                        <span>✅</span>
                        <span>주문 불필요</span>
                        <span style="font-size:13px; font-weight:normal;">(+${{surplus.toFixed(1)}}개월 여유)</span>
                    `;
                }}
            }}

            // 3개월 평균 기준 업데이트
            updateSingleProgressBar('ma3', currentRunwayMa3, targetMonths, orderMa3);

            // 1년 평균 기준 업데이트
            updateSingleProgressBar('ma12', currentRunwayMa12, targetMonths, orderMa12);
        }}

        // 차트 렌더링
        function renderInlineChart(drugCode, chartData) {{
            const chartContainer = document.getElementById('inline-chart-' + drugCode);
            if (!chartContainer) return;

            // 데이터 준비
            const months = chartData.months || [];
            const timeseries = chartData.timeseries || [];
            const ma3List = chartData.ma3_list || [];
            const currentStock = chartData.stock;

            if (months.length === 0 || timeseries.length === 0) {{
                chartContainer.innerHTML = '<div style="text-align: center; padding: 40px; color: #718096;">차트 데이터가 없습니다.</div>';
                return;
            }}

            // 현재 재고 수평선 데이터
            const stockLine = months.map(() => currentStock);

            const traces = [
                {{
                    x: months,
                    y: timeseries,
                    mode: 'lines+markers',
                    name: '실제 조제수량',
                    line: {{color: '#2d3748', width: 2, dash: 'dot'}},
                    marker: {{size: 5, color: '#2d3748'}},
                    hovertemplate: '조제수량: %{{y:,.0f}}개<extra></extra>'
                }},
                {{
                    x: months,
                    y: ma3List,
                    mode: 'lines',
                    name: '3개월 이동평균',
                    line: {{color: '#4facfe', width: 3}},
                    hovertemplate: '3개월 평균: %{{y:,.1f}}개<extra></extra>'
                }},
                {{
                    x: months,
                    y: stockLine,
                    mode: 'lines',
                    name: '현재 재고',
                    line: {{color: '#e53e3e', width: 2, dash: 'dash'}},
                    hovertemplate: '현재 재고: %{{y:,.0f}}개<extra></extra>'
                }}
            ];

            // 겨울철 배경 영역 생성
            const winterShapes = [];
            function isWinterMonth(month) {{
                const monthNum = parseInt(month.split('-')[1]);
                return monthNum === 10 || monthNum === 11 || monthNum === 12 || monthNum === 1 || monthNum === 2;
            }}

            let winterStart = null;
            for (let i = 0; i < months.length; i++) {{
                const isWinter = isWinterMonth(months[i]);
                if (isWinter && winterStart === null) {{
                    winterStart = i;
                }} else if (!isWinter && winterStart !== null) {{
                    winterShapes.push({{
                        type: 'rect', xref: 'x', yref: 'paper',
                        x0: months[winterStart], x1: months[i - 1],
                        y0: 0, y1: 1,
                        fillcolor: 'rgba(135, 206, 250, 0.2)', line: {{width: 0}}, layer: 'below'
                    }});
                    winterStart = null;
                }}
            }}
            if (winterStart !== null) {{
                winterShapes.push({{
                    type: 'rect', xref: 'x', yref: 'paper',
                    x0: months[winterStart], x1: months[months.length - 1],
                    y0: 0, y1: 1,
                    fillcolor: 'rgba(135, 206, 250, 0.2)', line: {{width: 0}}, layer: 'below'
                }});
            }}

            const layout = {{
                xaxis: {{ title: '월', type: 'category', showgrid: true, gridcolor: '#e2e8f0' }},
                yaxis: {{ title: '조제수량', showgrid: true, gridcolor: '#e2e8f0' }},
                height: 300,
                margin: {{ t: 20, b: 50, l: 60, r: 30 }},
                hovermode: 'x unified',
                plot_bgcolor: 'white',
                paper_bgcolor: '#f8fafc',
                font: {{size: 11}},
                shapes: winterShapes,
                legend: {{
                    orientation: 'h',
                    yanchor: 'bottom',
                    y: 1.02,
                    xanchor: 'right',
                    x: 1
                }}
            }};

            Plotly.newPlot(chartContainer, traces, layout, {{displayModeBar: false, responsive: true}});
        }}

        // ========== 페이지 로드 시 최신 임계값 동기화 (책갈피만 업데이트) ==========
        window.addEventListener('DOMContentLoaded', function() {{
            fetch('/api/drug-thresholds')
                .then(response => response.json())
                .then(data => {{
                    if (data.status === 'success') {{
                        // 책갈피 카운트 업데이트
                        const countEl = document.querySelector('.alert-bookmark.custom .alert-count');
                        if (countEl) {{
                            countEl.textContent = data.count + '개';
                        }}

                        // 책갈피 표시/숨김
                        const bookmark = document.querySelector('.alert-bookmark.custom');
                        if (bookmark) {{
                            bookmark.style.display = data.count > 0 ? 'flex' : 'none';
                        }}
                    }}
                }})
                .catch(error => {{
                    console.error('임계값 동기화 실패:', error);
                }});
        }});
    </script>
</body>
</html>
"""
    return html


def generate_html_report(df, months=None):
    """HTML 보고서 생성 및 파일 저장 (CLI용 래퍼 함수)"""
    print("\n📋 Step 4: HTML 보고서 생성")
    print("-" * 30)

    # 출력 디렉토리 생성
    output_dir = 'order_calc_reports'
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = os.path.join(output_dir, f'order_calculator_report_{timestamp}.html')

    # HTML 생성 (재사용 가능한 함수 호출)
    html = generate_order_report_html(df, months=months)

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

        # months 생성 (차트용)
        months = []
        data_period = processed_inventory_db.get_metadata()
        if data_period:
            from dateutil.relativedelta import relativedelta
            start_date = datetime.strptime(data_period['start_month'], '%Y-%m')
            for i in range(data_period['total_months']):
                month_date = start_date + relativedelta(months=i)
                months.append(month_date.strftime('%Y-%m'))

        # 보고서 생성
        html_file = generate_html_report(result_df, months=months)
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
