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


def check_required_files():
    """필수 파일 존재 여부 확인"""
    if not os.path.exists('processed_inventory_timeseries.csv'):
        print("❌ processed_inventory_timeseries.csv 파일이 존재하지 않습니다.")
        print("⚠️  먼저 워크플로우 1번 (시계열 분석)을 실행해주세요.")
        return False

    if not os.path.exists('today.csv'):
        print("❌ today.csv 파일이 존재하지 않습니다.")
        return False

    return True


def load_processed_data():
    """processed_inventory_timeseries.csv 로드"""
    print("🔍 Step 1: 시계열 분석 데이터 로드")
    print("-" * 30)

    df = pd.read_csv('processed_inventory_timeseries.csv', encoding='utf-8-sig')

    # 필요한 컬럼만 선택
    required_cols = ['약품코드', '약품명', '제약회사', '월별_조제수량_리스트', '3개월_이동평균_리스트']
    df = df[required_cols].copy()

    print(f"✅ {len(df)}개 약품의 시계열 데이터를 로드했습니다.")
    return df


def load_today_data():
    """today.csv 로드"""
    print("\n🔍 Step 2: 오늘의 재고 데이터 로드")
    print("-" * 30)

    df = pd.read_csv('today.csv', encoding='utf-8-sig')

    # 필요한 컬럼만 선택하고 재고수량 컬럼명 변경
    required_cols = ['약품명', '약품코드', '제약회사', '재고수량']
    df = df[required_cols].copy()
    df = df.rename(columns={'재고수량': '현재 재고수량'})

    # 약품코드가 NaN인 행 제거 (합계 행)
    df = df.dropna(subset=['약품코드'])

    # 재고수량 문자열을 숫자로 변환 (쉼표 제거)
    df['현재 재고수량'] = df['현재 재고수량'].astype(str).str.replace(',', '').astype(float)

    print(f"✅ {len(df)}개 약품의 오늘 재고 데이터를 로드했습니다.")
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

    # 월평균 조제수량과 3개월 이동평균 계산
    processed_df['월평균 조제수량'] = parse_list_column(processed_df['월별_조제수량_리스트'])
    processed_df['3개월 이동평균'] = parse_list_column(processed_df['3개월_이동평균_리스트'])

    # 약품코드를 기준으로 병합
    result_df = today_df.merge(
        processed_df[['약품코드', '월평균 조제수량', '3개월 이동평균']],
        on='약품코드',
        how='left'
    )

    # 런웨이 계산
    result_df['런웨이'] = result_df['현재 재고수량'] / result_df['월평균 조제수량']
    result_df['3-MA 런웨이'] = result_df['현재 재고수량'] / result_df['3개월 이동평균']

    # 무한대 값을 처리 (조제수량이 0인 경우)
    result_df['런웨이'] = result_df['런웨이'].replace([np.inf, -np.inf], 999)
    result_df['3-MA 런웨이'] = result_df['3-MA 런웨이'].replace([np.inf, -np.inf], 999)

    # NaN 값을 0으로 처리
    result_df['런웨이'] = result_df['런웨이'].fillna(0)
    result_df['3-MA 런웨이'] = result_df['3-MA 런웨이'].fillna(0)

    # 런웨이 기준 오름차순 정렬
    result_df = result_df.sort_values('런웨이', ascending=True)

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
        <p>긴급 주문 필요 (런웨이 < 1개월): <span class="urgent">{urgent_count}개</span></p>
    </div>

    <table>
        <thead>
            <tr>
                <th>약품명</th>
                <th>약품코드</th>
                <th>제약회사</th>
                <th>현재 재고수량</th>
                <th>월평균 조제수량</th>
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

        html += f"""
            <tr class="{row_class}">
                <td>{row['약품명']}</td>
                <td>{row['약품코드']}</td>
                <td>{row['제약회사']}</td>
                <td>{row['현재 재고수량']:.0f}</td>
                <td>{row['월평균 조제수량']:.1f}</td>
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
        today_df = load_today_data()

        # 병합 및 계산
        result_df = merge_and_calculate(today_df, processed_df)

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
