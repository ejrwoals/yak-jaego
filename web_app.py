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
from generate_single_ma_report import create_and_save_report as create_simple_report
from drug_order_calculator import run as run_order_calculator
import inventory_db
import processed_inventory_db
import inventory_updater
import checked_items_db
from utils import read_today_file

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 한글 JSON 출력 지원
app.config['UPLOAD_FOLDER'] = 'uploads'  # 임시 업로드 폴더
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB 제한

# 허용된 파일 확장자
ALLOWED_EXTENSIONS = {'csv', 'xls', 'xlsx'}


def allowed_file(filename):
    """파일 확장자 검증"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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

    # DB에 저장된 데이터 기간 정보 조회
    data_period = processed_inventory_db.get_metadata()

    return True, {
        'recent_count': recent_count,
        'processed_stats': processed_stats,
        'data_period': data_period
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


@app.route('/workflow/simple')
def workflow_simple():
    """단순 재고 관리 보고서 워크플로우 페이지"""
    return render_template('workflow_simple.html')


@app.route('/workflow/order')
def workflow_order():
    """주문 수량 산출 워크플로우 페이지"""
    return render_template('workflow_order.html')


@app.route('/api/generate-report', methods=['POST'])
def generate_report():
    """시계열 분석 보고서 생성 API (상세 보고서 - Dual MA)"""
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

        # DB 메타데이터에서 월 정보 추출
        data_period = processed_inventory_db.get_metadata()

        if data_period:
            # 메타데이터에서 정확한 월 범위 가져오기
            start_month = data_period['start_month']
            end_month = data_period['end_month']
            total_months = data_period['total_months']

            # 시작 월부터 종료 월까지 연속된 월 생성
            from dateutil.relativedelta import relativedelta
            start_date = datetime.strptime(start_month, '%Y-%m')
            months = []
            for i in range(total_months):
                month_date = start_date + relativedelta(months=i)
                months.append(month_date.strftime('%Y-%m'))
        else:
            # 메타데이터가 없는 경우 (fallback)
            first_record = df.iloc[0]
            num_months = len(first_record['월별_조제수량_리스트'])
            months = [f"Month {i+1}" for i in range(num_months)]

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


@app.route('/generate/simple_report', methods=['POST'])
def generate_simple_report_route():
    """단순 재고 관리 보고서 생성 API (Single MA)"""
    try:
        mode = request.form.get('mode', 'dispense')
        ma_months = int(request.form.get('ma_months', 3))

        if mode not in ['dispense', 'sale']:
            return jsonify({'status': 'error', 'message': '잘못된 보고서 유형입니다.'}), 400

        if not (1 <= ma_months <= 12):
            return jsonify({'status': 'error', 'message': '이동평균 개월 수는 1~12 사이여야 합니다.'}), 400

        # 약품 유형 결정
        drug_type = '전문약' if mode == 'dispense' else '일반약'

        # processed_inventory DB에서 데이터 로드
        df = processed_inventory_db.get_processed_data(drug_type=drug_type)

        if df.empty:
            return jsonify({'status': 'error', 'message': f'{drug_type} 데이터가 없습니다.'}), 404

        # DB 메타데이터에서 월 정보 추출
        data_period = processed_inventory_db.get_metadata()

        if data_period:
            # 메타데이터에서 정확한 월 범위 가져오기
            start_month = data_period['start_month']
            end_month = data_period['end_month']
            total_months = data_period['total_months']

            # 시작 월부터 종료 월까지 연속된 월 생성
            from dateutil.relativedelta import relativedelta
            start_date = datetime.strptime(start_month, '%Y-%m')
            months = []
            for i in range(total_months):
                month_date = start_date + relativedelta(months=i)
                months.append(month_date.strftime('%Y-%m'))
        else:
            # 메타데이터가 없는 경우 (fallback)
            first_record = df.iloc[0]
            num_months = len(first_record['월별_조제수량_리스트'])
            months = [f"Month {i+1}" for i in range(num_months)]

        # HTML 보고서 생성 (브라우저 자동 열기 비활성화)
        report_path = create_simple_report(df, months, mode=mode, ma_months=ma_months, open_browser=False)

        # 파일명만 추출
        report_filename = os.path.basename(report_path)

        return jsonify({
            'status': 'success',
            'report_url': f'/reports/{report_filename}',
            'report_filename': report_filename,
            'drug_type': drug_type,
            'drug_count': len(df),
            'ma_months': ma_months
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/calculate-order', methods=['POST'])
def calculate_order():
    """주문 수량 산출 API (파일 업로드 지원)"""
    temp_filepath = None

    try:
        # 파일이 업로드 되었는지 확인
        if 'todayFile' not in request.files:
            return jsonify({'error': '파일이 업로드되지 않았습니다.'}), 400

        file = request.files['todayFile']

        # 파일이 실제로 선택되었는지 확인
        if file.filename == '':
            return jsonify({'error': '파일이 선택되지 않았습니다.'}), 400

        # 확장자 검증
        if not allowed_file(file.filename):
            return jsonify({'error': '허용되지 않는 파일 형식입니다. (csv, xls, xlsx만 가능)'}), 400

        # 임시 파일명 생성 (충돌 방지)
        import uuid
        temp_filename = f"temp_today_{uuid.uuid4().hex[:8]}{os.path.splitext(file.filename)[1]}"
        temp_filepath = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)

        # uploads 폴더가 없으면 생성
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        # 파일 저장
        file.save(temp_filepath)
        print(f"📦 {file.filename} 업로드 완료 - 재고 업데이트 중...")

        # 절대 경로로 변환
        abs_temp_filepath = os.path.abspath(temp_filepath)

        # 업로드된 파일 읽기
        df_today, today_filepath = read_today_file(abs_temp_filepath)

        if df_today is None:
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
            return jsonify({'error': '파일을 읽을 수 없습니다. 파일 형식을 확인해주세요.'}), 400

        # 재고 업데이트
        inventory_updater.update_inventory_from_today_csv(abs_temp_filepath)
        print("✅ 재고 업데이트 완료")

        # 시계열 데이터 로드
        df_processed = processed_inventory_db.get_processed_data()
        if df_processed.empty:
            return jsonify({'error': '시계열 통계 데이터가 없습니다.'}), 404

        # today 파일에서 약품코드 추출
        today_codes = set(df_today['약품코드'].astype(str))

        # processed 데이터를 today 파일 약품만 필터링
        df_processed_filtered = df_processed[df_processed['약품코드'].isin(today_codes)].copy()

        if df_processed_filtered.empty:
            return jsonify({'error': 'today 파일 약품에 대한 시계열 데이터가 없습니다.'}), 404

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

        # 처리 완료 후 임시 파일 삭제
        if temp_filepath and os.path.exists(temp_filepath):
            os.remove(temp_filepath)
            print(f"🗑️  임시 파일 삭제: {temp_filepath}")

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
        # 에러 발생 시에도 임시 파일 정리
        if temp_filepath and os.path.exists(temp_filepath):
            os.remove(temp_filepath)
            print(f"🗑️  임시 파일 삭제 (에러): {temp_filepath}")

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


@app.route('/api/list-reports/<report_type>')
def list_reports(report_type):
    """보고서 목록 조회 API"""
    try:
        if report_type == 'timeseries':
            report_dir = 'inventory_reports'
            # 단순 보고서와 상세 보고서 모두 포함
            file_prefixes = ['inventory_report_', 'simple_report_']
        elif report_type == 'order':
            report_dir = 'order_calc_reports'
            file_prefixes = ['order_calculator_report_']
        else:
            return jsonify({'error': '잘못된 보고서 유형입니다.'}), 400

        # 디렉토리 확인
        if not os.path.exists(report_dir):
            return jsonify({'reports': []})

        # HTML 파일만 필터링 (여러 prefix 지원)
        files = [f for f in os.listdir(report_dir)
                if any(f.startswith(prefix) for prefix in file_prefixes) and f.endswith('.html')]

        reports = []
        for filename in files:
            file_path = os.path.join(report_dir, filename)

            # 파일 정보 추출
            file_stat = os.stat(file_path)
            created_time = datetime.fromtimestamp(file_stat.st_mtime)

            # 파일명에서 정보 추출
            report_info = {
                'filename': filename,
                'created_at': created_time.strftime('%Y-%m-%d %H:%M:%S'),
                'timestamp': file_stat.st_mtime,
                'size': file_stat.st_size
            }

            # 시계열 보고서의 경우 전문약/일반약 및 보고서 유형 구분
            if report_type == 'timeseries':
                if 'dispense' in filename:
                    report_info['drug_type'] = '전문약'
                elif 'sale' in filename:
                    report_info['drug_type'] = '일반약'
                else:
                    report_info['drug_type'] = '미분류'

                # 단순/상세 보고서 구분
                if filename.startswith('simple_report_'):
                    report_info['report_style'] = '단순'
                    # 파일명에서 MA 개월 수 추출 (예: simple_report_dispense_3ma_20251119.html)
                    try:
                        ma_part = filename.split('_')[3]  # "3ma"
                        ma_months = ma_part.replace('ma', '')
                        report_info['ma_months'] = f'{ma_months}개월'
                    except:
                        report_info['ma_months'] = 'N/A'
                else:
                    report_info['report_style'] = '상세'
                    report_info['ma_months'] = '1년+3개월'

            reports.append(report_info)

        # 최신순 정렬
        reports.sort(key=lambda x: x['timestamp'], reverse=True)

        # 최대 10개만 반환 (드롭다운용)
        reports = reports[:10]

        return jsonify({'reports': reports})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/reports/<path:filename>')
def serve_report(filename):
    """보고서 파일 제공"""
    # 시계열 보고서 (inventory_reports 디렉토리)
    if filename.startswith('inventory_report_') or filename.startswith('simple_report_'):
        file_path = os.path.join(os.getcwd(), 'inventory_reports', filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='text/html')

    # 주문 보고서 (order_calc_reports 디렉토리)
    elif filename.startswith('order_calculator_report_'):
        file_path = os.path.join(os.getcwd(), 'order_calc_reports', filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='text/html' if filename.endswith('.html') else 'text/csv')

    return "파일을 찾을 수 없습니다.", 404


@app.route('/api/rebuild-db', methods=['POST'])
def rebuild_db():
    """DB 재생성 API (init_db.py 기능 실행)"""
    try:
        print("\n🔄 DB 재생성 요청 받음...")

        from read_csv import load_multiple_csv_files, merge_by_drug_code, calculate_statistics

        # Step 1: 월별 CSV 로드
        print("🔍 월별 CSV 파일 로드 중...")
        monthly_data = load_multiple_csv_files(directory='data')

        if not monthly_data:
            return jsonify({'error': 'CSV 파일을 로드할 수 없습니다.'}), 400

        # 기존 DB 삭제
        print("🗑️  기존 DB 삭제 중...")
        if inventory_db.db_exists():
            os.remove('recent_inventory.sqlite3')
        if processed_inventory_db.db_exists():
            os.remove('processed_inventory.sqlite3')

        # Step 2: DB 초기화
        print("💽 데이터베이스 초기화 중...")
        inventory_db.init_db()
        processed_inventory_db.init_db()

        # Step 3: 전문약 처리
        print("🔄 전문약 데이터 처리 중...")
        df_dispense, months = merge_by_drug_code(monthly_data, mode='dispense')
        df_dispense = calculate_statistics(df_dispense, months)

        # 통계 DB에 저장
        processed_inventory_db.upsert_processed_data(df_dispense, drug_type='전문약', show_summary=False)

        # 메타데이터 저장
        processed_inventory_db.save_metadata(months)

        # 재고 DB에 저장
        inventory_data = df_dispense[['약품코드', '약품명', '제약회사', '최종_재고수량']].copy()
        inventory_data.rename(columns={'최종_재고수량': '현재_재고수량'}, inplace=True)
        inventory_data['약품유형'] = '전문약'
        inventory_db.upsert_inventory(inventory_data, show_summary=False)

        # Step 4: 일반약 처리
        print("🔄 일반약 데이터 처리 중...")
        df_sale, months = merge_by_drug_code(monthly_data, mode='sale')
        df_sale = calculate_statistics(df_sale, months)

        # 통계 DB에 저장
        processed_inventory_db.upsert_processed_data(df_sale, drug_type='일반약', show_summary=False)

        # 재고 DB에 저장
        inventory_data = df_sale[['약품코드', '약품명', '제약회사', '최종_재고수량']].copy()
        inventory_data.rename(columns={'최종_재고수량': '현재_재고수량'}, inplace=True)
        inventory_data['약품유형'] = '일반약'
        inventory_db.upsert_inventory(inventory_data, show_summary=False)

        print("✅ DB 재생성 완료!")

        # 최종 통계
        recent_count = inventory_db.get_inventory_count()
        processed_stats = processed_inventory_db.get_statistics()
        data_period = processed_inventory_db.get_metadata()

        return jsonify({
            'success': True,
            'message': 'DB 재생성이 완료되었습니다.',
            'stats': {
                'recent_count': recent_count,
                'processed_stats': processed_stats,
                'data_period': data_period
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'DB 재생성 실패: {str(e)}'}), 500


@app.route('/api/get_checked_items', methods=['GET'])
def get_checked_items_api():
    """숨김 처리된 약품 목록 조회 API"""
    try:
        checked_items = checked_items_db.get_checked_items()
        return jsonify({'status': 'success', 'checked_items': list(checked_items)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/toggle_checked_item', methods=['POST'])
def toggle_checked_item():
    """체크 상태 업데이트 API (카테고리 없이 약품코드만 사용)"""
    try:
        data = request.get_json()
        drug_code = data.get('drug_code')
        is_checked = data.get('checked', False)

        if not drug_code:
            return jsonify({'status': 'error', 'message': '약품코드가 없습니다.'}), 400

        # 체크 상태에 따라 DB 업데이트 (카테고리 없이)
        if is_checked:
            checked_items_db.add_checked_item(drug_code)
        else:
            checked_items_db.remove_checked_item(drug_code)

        return jsonify({'status': 'success', 'message': '체크 상태가 업데이트되었습니다.'})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/update_memo', methods=['POST'])
def update_memo():
    """메모 업데이트 API (카테고리 없이 약품코드만 사용)"""
    try:
        data = request.get_json()
        drug_code = data.get('drug_code')
        memo = data.get('memo', '')

        if not drug_code:
            return jsonify({'status': 'error', 'message': '약품코드가 없습니다.'}), 400

        # 메모 업데이트 (카테고리 없이)
        checked_items_db.update_memo(drug_code, memo)

        return jsonify({'status': 'success', 'message': '메모가 저장되었습니다.'})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/get_memo', methods=['GET'])
def get_memo():
    """메모 조회 API (카테고리 없이 약품코드만 사용)"""
    try:
        drug_code = request.args.get('drug_code')

        if not drug_code:
            return jsonify({'status': 'error', 'message': '약품코드가 없습니다.'}), 400

        # 메모 조회 (카테고리 없이)
        memo = checked_items_db.get_memo(drug_code)

        return jsonify({'status': 'success', 'memo': memo})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    """Flask 앱 종료 API"""
    try:
        print("\n🛑 웹 애플리케이션 종료 요청 받음...")

        # Flask 종료 함수 호출
        shutdown_server = request.environ.get('werkzeug.server.shutdown')
        if shutdown_server is None:
            # Werkzeug 버전에 따라 다른 방법 사용
            import signal
            print("✅ 서버를 종료합니다...")
            os.kill(os.getpid(), signal.SIGINT)
        else:
            shutdown_server()

        return jsonify({'success': True, 'message': '서버가 종료됩니다...'})
    except Exception as e:
        print(f"⚠️  종료 중 오류 발생: {e}")
        return jsonify({'error': str(e)}), 500


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
