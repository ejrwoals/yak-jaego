#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Jaego - 약국 재고 관리 및 분석 시스템 (웹 버전)
Flask 기반 웹 애플리케이션

사용법: python web_app.py
"""

import os
import sys
import json
import webbrowser
from datetime import datetime
from threading import Timer

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
import pandas as pd

# 로컬 모듈 import
from generate_report import create_and_save_report
from drug_order_calculator import run as run_order_calculator
import inventory_db
import processed_inventory_db
import inventory_updater

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 한글 JSON 출력 지원


def check_database_ready():
    """두 개의 DB가 모두 준비되었는지 확인"""

    # recent_inventory.sqlite3 체크
    if not inventory_db.db_exists():
        return False, "recent_inventory.sqlite3가 없습니다."

    recent_count = inventory_db.get_inventory_count()
    if recent_count == 0:
        return False, "recent_inventory.sqlite3에 데이터가 없습니다."

    # processed_inventory.sqlite3 체크
    if not processed_inventory_db.db_exists():
        return False, "processed_inventory.sqlite3가 없습니다."

    processed_stats = processed_inventory_db.get_statistics()
    if processed_stats['total'] == 0:
        return False, "processed_inventory.sqlite3에 데이터가 없습니다."

    return True, {
        'recent_count': recent_count,
        'processed_stats': processed_stats
    }


@app.route('/')
def index():
    """랜딩 페이지"""
    # DB 상태 확인
    is_ready, result = check_database_ready()

    if not is_ready:
        return render_template('error.html',
                             error_message=result,
                             suggestion="먼저 DB를 초기화해주세요: python init_db.py")

    return render_template('index.html', db_stats=result)


@app.route('/workflow/timeseries')
def workflow_timeseries():
    """시계열 분석 워크플로우 선택 페이지"""
    return render_template('workflow_timeseries.html')


@app.route('/workflow/order')
def workflow_order():
    """주문 수량 산출 워크플로우 페이지"""
    return render_template('workflow_order.html')


@app.route('/api/generate-report', methods=['POST'])
def generate_report():
    """시계열 분석 보고서 생성 API"""
    try:
        data = request.get_json()
        report_type = data.get('report_type')  # 'dispense' 또는 'sale'

        if report_type not in ['dispense', 'sale']:
            return jsonify({'error': '잘못된 보고서 유형입니다.'}), 400

        # 약품 유형 결정
        drug_type = '전문약' if report_type == 'dispense' else '일반약'

        # processed_inventory DB에서 데이터 로드
        df = processed_inventory_db.get_processed_data(drug_type=drug_type)

        if df.empty:
            return jsonify({'error': f'{drug_type} 데이터가 없습니다.'}), 404

        # 월 정보 추출
        first_record = df.iloc[0]
        num_months = len(first_record['월별_조제수량_리스트'])

        # 연속된 월 생성
        today = datetime.now()
        months = []
        from datetime import timedelta
        for i in range(num_months):
            month_date = datetime(today.year, today.month, 1) - timedelta(days=30*(num_months-1-i))
            months.append(month_date.strftime('%Y-%m'))

        # HTML 보고서 생성 (브라우저 자동 열기 비활성화)
        report_path = create_and_save_report(df, months, mode=report_type, open_browser=False)

        # 파일명만 추출
        report_filename = os.path.basename(report_path)

        return jsonify({
            'success': True,
            'report_path': report_path,
            'report_filename': report_filename,
            'drug_type': drug_type,
            'drug_count': len(df)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/calculate-order', methods=['POST'])
def calculate_order():
    """주문 수량 산출 API"""
    try:
        # today.csv 존재 여부 확인
        if not os.path.exists('today.csv'):
            return jsonify({'error': 'today.csv 파일이 없습니다.'}), 404

        # today.csv가 있으면 재고 업데이트
        print("📦 today.csv 발견 - 재고 업데이트 중...")
        inventory_updater.update_inventory_from_today_csv()
        print("✅ 재고 업데이트 완료")

        # 시계열 데이터 로드
        df_processed = processed_inventory_db.get_processed_data()
        if df_processed.empty:
            return jsonify({'error': '시계열 통계 데이터가 없습니다.'}), 404

        # today.csv에서 약품코드 추출
        df_today = pd.read_csv('today.csv', encoding='utf-8-sig', dtype={'약품코드': str})
        today_codes = set(df_today['약품코드'].astype(str))

        # processed 데이터를 today.csv 약품만 필터링
        df_processed_filtered = df_processed[df_processed['약품코드'].isin(today_codes)].copy()

        if df_processed_filtered.empty:
            return jsonify({'error': 'today.csv 약품에 대한 시계열 데이터가 없습니다.'}), 404

        # 현재 재고 로드
        df_recent = inventory_db.get_all_inventory_as_df()

        # 데이터 병합
        df_merged = pd.merge(
            df_processed_filtered,
            df_recent[['약품코드', '현재_재고수량']],
            on='약품코드',
            how='left'
        )

        # 런웨이 계산
        df_merged['런웨이_1년평균'] = df_merged.apply(
            lambda row: row['현재_재고수량'] / row['1년_이동평균']
            if row['1년_이동평균'] > 0 else 999, axis=1
        )

        # 3개월 이동평균 마지막 값 추출
        df_merged['3개월_이동평균'] = df_merged['3개월_이동평균_리스트'].apply(
            lambda x: x[-1] if x and len(x) > 0 else 0
        )

        df_merged['런웨이_3개월평균'] = df_merged.apply(
            lambda row: row['현재_재고수량'] / row['3개월_이동평균']
            if row['3개월_이동평균'] > 0 else 999, axis=1
        )

        # 3-MA 런웨이 오름차순 정렬 (긴급한 약품 우선)
        df_merged = df_merged.sort_values('런웨이_3개월평균')

        # HTML 보고서 생성
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_dir = 'order_calc_reports'
        os.makedirs(report_dir, exist_ok=True)

        html_path = os.path.join(report_dir, f'order_calculator_report_{timestamp}.html')
        csv_path = os.path.join(report_dir, f'order_calculator_report_{timestamp}.csv')

        # HTML 생성
        html_content = generate_order_report_html(df_merged)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        # CSV 저장
        df_merged.to_csv(csv_path, index=False, encoding='utf-8-sig')

        return jsonify({
            'success': True,
            'html_path': html_path,
            'csv_path': csv_path,
            'html_filename': os.path.basename(html_path),
            'csv_filename': os.path.basename(csv_path),
            'drug_count': len(df_merged),
            'urgent_count': len(df_merged[df_merged['런웨이_1년평균'] < 1])
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def generate_order_report_html(df):
    """주문 계산 HTML 보고서 생성 (기존 drug_order_calculator.py 스타일)"""

    # 런웨이 < 1인 약품 개수 확인
    urgent_count = len(df[(df['런웨이_1년평균'] < 1) | (df['런웨이_3개월평균'] < 1)])

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
        runway = row['런웨이_1년평균']
        ma3_runway = row['런웨이_3개월평균']

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
                <td>{row['현재_재고수량']:.0f}</td>
                <td>{row['1년_이동평균']:.1f}</td>
                <td>{row['3개월_이동평균']:.1f}</td>
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
    return html


@app.route('/reports/<path:filename>')
def serve_report(filename):
    """보고서 파일 제공"""
    # 시계열 보고서 (inventory_reports 디렉토리)
    if filename.startswith('inventory_report_'):
        file_path = os.path.join(os.getcwd(), 'inventory_reports', filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='text/html')

    # 주문 보고서 (order_calc_reports 디렉토리)
    elif filename.startswith('order_calculator_report_'):
        file_path = os.path.join(os.getcwd(), 'order_calc_reports', filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='text/html' if filename.endswith('.html') else 'text/csv')

    return "파일을 찾을 수 없습니다.", 404


def open_browser():
    """브라우저 자동 열기"""
    webbrowser.open('http://127.0.0.1:5000/')


if __name__ == '__main__':
    # 브라우저 자동 열기 (1초 후)
    Timer(1, open_browser).start()

    # Flask 앱 실행
    print("\n" + "=" * 60)
    print("🏥 Jaego - 약국 재고 관리 시스템 (웹 버전)")
    print("=" * 60)
    print("\n📱 웹 브라우저가 자동으로 열립니다...")
    print("   URL: http://127.0.0.1:5000/")
    print("\n⚠️  종료하려면 Ctrl+C를 누르세요.")
    print("=" * 60 + "\n")

    app.run(debug=True, use_reloader=False)
