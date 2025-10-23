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


def generate_html_report(df):
    """HTML 보고서 생성"""
    print("\n📋 Step 4: HTML 보고서 생성")
    print("-" * 30)

    # 출력 디렉토리 생성
    output_dir = 'order_calc_reports'
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = os.path.join(output_dir, f'order_calculator_report_{timestamp}.html')

    # 런웨이 < 1인 약품 개수 확인
    urgent_count = len(df[(df['런웨이'] < 1) | (df['3-MA 런웨이'] < 1)])

    # 약품 유형별 개수
    dispense_count = len(df[df['약품유형'] == '전문약'])
    sale_count = len(df[df['약품유형'] == '일반약'])
    unclassified_count = len(df[df['약품유형'] == '미분류'])

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
        table {{
            width: 100%;
            border-collapse: collapse;
            background-color: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
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
    </style>
</head>
<body>
    <div class="header">
        <h1>📦 약 주문 수량 산출 보고서</h1>
        <p>생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <div class="summary">
        <h2>📊 요약</h2>
        <p>총 약품 수: <strong>{len(df)}개</strong></p>
        <p>  - 전문약: <strong>{dispense_count}개</strong> / 일반약: <strong>{sale_count}개</strong>{f' / 미분류: {unclassified_count}개' if unclassified_count > 0 else ''}</p>
        <p>긴급 주문 필요 (런웨이 < 1개월): <span class="urgent">{urgent_count}개</span></p>
    </div>

    <table>
        <thead>
            <tr>
                <th>약품명</th>
                <th>약품코드</th>
                <th>제약회사</th>
                <th>약품유형</th>
                <th>현재 재고수량</th>
                <th>1년 이동평균</th>
                <th>3개월 이동평균</th>
                <th>런웨이 (개월)</th>
                <th>3-MA 런웨이 (개월)</th>
            </tr>
        </thead>
        <tbody>
"""

    for _, row in df.iterrows():
        runway = row['런웨이']
        ma3_runway = row['3-MA 런웨이']

        # 런웨이 < 1인 경우 행 전체를 빨간색으로
        row_class = 'urgent-row' if (runway < 1 or ma3_runway < 1) else ''

        runway_class = 'urgent-cell' if runway < 1 else 'normal-cell'
        ma3_runway_class = 'urgent-cell' if ma3_runway < 1 else 'normal-cell'

        runway_display = f'{runway:.2f}' if runway < 999 else '재고만 있음'
        ma3_runway_display = f'{ma3_runway:.2f}' if ma3_runway < 999 else '재고만 있음'

        # 약품유형에 따라 배지 스타일 적용
        drug_type = row['약품유형']
        type_badge_color = '#3498db' if drug_type == '전문약' else '#e67e22' if drug_type == '일반약' else '#95a5a6'

        html += f"""
            <tr class="{row_class}">
                <td>{row['약품명']}</td>
                <td>{row['약품코드']}</td>
                <td>{row['제약회사']}</td>
                <td><span style="background-color: {type_badge_color}; color: white; padding: 3px 8px; border-radius: 4px; font-size: 12px;">{drug_type}</span></td>
                <td>{row['현재 재고수량']:.0f}</td>
                <td>{row['1년 이동평균']:.1f}</td>
                <td>{row['3개월 이동평균']:.1f}</td>
                <td class="{runway_class}">{runway_display}</td>
                <td class="{ma3_runway_class}">{ma3_runway_display}</td>
            </tr>
"""

    html += """
        </tbody>
    </table>
</body>
</html>
"""

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
