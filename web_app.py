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
from drug_order_calculator import run as run_order_calculator, generate_order_report_html
import inventory_db
import processed_inventory_db
import inventory_updater
import checked_items_db
import drug_thresholds_db
import drug_memos_db
import patients_db
import drug_patient_map_db
import drug_flags_db
import buffer_calculator
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
        threshold_low = int(request.form.get('threshold_low', 3))
        threshold_high = int(request.form.get('threshold_high', 12))

        if mode not in ['dispense', 'sale']:
            return jsonify({'status': 'error', 'message': '잘못된 보고서 유형입니다.'}), 400

        if not (1 <= ma_months <= 12):
            return jsonify({'status': 'error', 'message': '이동평균 개월 수는 1~12 사이여야 합니다.'}), 400

        if not (1 <= threshold_low < threshold_high <= 24):
            return jsonify({'status': 'error', 'message': '경계값 설정이 올바르지 않습니다.'}), 400

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
        report_path = create_simple_report(df, months, mode=mode, ma_months=ma_months,
                                           threshold_low=threshold_low, threshold_high=threshold_high,
                                           open_browser=False)

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
        # 런웨이 임계값 파라미터 추출 (기본값 1.0)
        runway_threshold = float(request.form.get('runway_threshold', 1.0))

        # 임계값 유효성 검사 (0.5 ~ 6개월)
        if not (0.5 <= runway_threshold <= 6):
            return jsonify({'error': '런웨이 임계값은 0.5~6 사이여야 합니다.'}), 400

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

        # today 파일에서 약품코드 추출
        today_codes = set(df_today['약품코드'].astype(str))

        # 현재 재고 로드 (today 파일 약품만 필터링)
        df_recent = inventory_db.get_all_inventory_as_df()
        df_recent_filtered = df_recent[df_recent['약품코드'].isin(today_codes)].copy()

        if df_recent_filtered.empty:
            return jsonify({'error': 'today 파일 약품에 대한 재고 데이터가 없습니다.'}), 404

        # 데이터 병합 (recent_inventory 기준 LEFT JOIN - 신규 약품 포함)
        df_merged = pd.merge(
            df_recent_filtered[['약품코드', '약품명', '제약회사', '현재_재고수량']],
            df_processed[['약품코드', '약품유형', '1년_이동평균', '3개월_이동평균_리스트', '월별_조제수량_리스트']],
            on='약품코드',
            how='left'
        )

        # 신규 약품 감지 (1년_이동평균이 NaN인 경우 = processed_inventory에 없는 약품)
        df_merged['신규약품'] = df_merged['1년_이동평균'].isna()

        # 약품유형이 없는 경우 기본값 '미분류'로 설정
        df_merged['약품유형'] = df_merged['약품유형'].fillna('미분류')

        # 신규 약품에 대해 today 파일의 조제수량/판매수량으로 약품유형 분류
        if df_merged['신규약품'].any() and ('조제수량' in df_today.columns or '판매수량' in df_today.columns):
            # today 파일에서 조제수량/판매수량 정보 추출
            today_qty_info = {}
            for _, row in df_today.iterrows():
                code = str(row['약품코드'])
                dispense = 0
                sale = 0
                if '조제수량' in df_today.columns:
                    val = row['조제수량']
                    if pd.notna(val):
                        try:
                            dispense = float(str(val).replace(',', '').replace('-', '0') or 0)
                        except:
                            dispense = 0
                if '판매수량' in df_today.columns:
                    val = row['판매수량']
                    if pd.notna(val):
                        try:
                            sale = float(str(val).replace(',', '').replace('-', '0') or 0)
                        except:
                            sale = 0
                today_qty_info[code] = {'조제수량': dispense, '판매수량': sale}

            # 신규 약품의 약품유형 분류
            for idx in df_merged[df_merged['신규약품'] & (df_merged['약품유형'] == '미분류')].index:
                drug_code = str(df_merged.at[idx, '약품코드'])
                if drug_code in today_qty_info:
                    info = today_qty_info[drug_code]
                    if info['조제수량'] > 0:
                        df_merged.at[idx, '약품유형'] = '전문약'
                    elif info['판매수량'] > 0:
                        df_merged.at[idx, '약품유형'] = '일반약'

        # 당일 소모 수량 컬럼 추가 (전문약: 조제수량, 일반약: 판매수량)
        df_merged['당일_소모수량'] = 0
        if '조제수량' in df_today.columns or '판매수량' in df_today.columns:
            for idx, row in df_merged.iterrows():
                drug_code = str(row['약품코드'])
                if drug_code in today_qty_info:
                    info = today_qty_info[drug_code]
                    drug_type = row['약품유형']
                    if drug_type == '전문약':
                        df_merged.at[idx, '당일_소모수량'] = info['조제수량']
                    elif drug_type == '일반약':
                        df_merged.at[idx, '당일_소모수량'] = info['판매수량']
                    else:
                        # 미분류: 조제수량이 있으면 조제수량, 아니면 판매수량
                        df_merged.at[idx, '당일_소모수량'] = info['조제수량'] if info['조제수량'] > 0 else info['판매수량']

        new_drug_count = df_merged['신규약품'].sum()
        if new_drug_count > 0:
            # 신규 약품 유형별 개수 계산
            new_drugs = df_merged[df_merged['신규약품']]
            new_dispense = len(new_drugs[new_drugs['약품유형'] == '전문약'])
            new_sale = len(new_drugs[new_drugs['약품유형'] == '일반약'])
            new_unclassified = len(new_drugs[new_drugs['약품유형'] == '미분류'])
            print(f"🆕 신규 약품 {new_drug_count}개 감지 (전문약: {new_dispense}, 일반약: {new_sale}, 미분류: {new_unclassified})")

        # 런웨이 계산 (신규 약품은 999로 처리)
        df_merged['런웨이_1년평균'] = df_merged.apply(
            lambda row: row['현재_재고수량'] / row['1년_이동평균']
            if pd.notna(row['1년_이동평균']) and row['1년_이동평균'] > 0 else 999, axis=1
        )

        # 3개월 이동평균 마지막 값 추출 (신규 약품은 0으로 처리)
        df_merged['3개월_이동평균'] = df_merged['3개월_이동평균_리스트'].apply(
            lambda x: x[-1] if isinstance(x, list) and len(x) > 0 else 0
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

        # HTML 생성 (web_app.py 컬럼명 매핑)
        col_map = {
            'runway': '런웨이_1년평균',
            'ma3_runway': '런웨이_3개월평균',
            'stock': '현재_재고수량',
            'ma12': '1년_이동평균',
            'ma3': '3개월_이동평균',
            'today_usage': '당일_소모수량'
        }

        # months 생성 (차트용)
        months = []
        data_period = processed_inventory_db.get_metadata()
        if data_period:
            from dateutil.relativedelta import relativedelta
            start_date = datetime.strptime(data_period['start_month'], '%Y-%m')
            for i in range(data_period['total_months']):
                month_date = start_date + relativedelta(months=i)
                months.append(month_date.strftime('%Y-%m'))

        # 오늘의 매출 합계 계산 (조제금액, 총 판매금액)
        # 마지막 행은 합계 행이므로 제외
        today_sales = {'조제금액': 0, '판매금액': 0}
        df_valid = df_today.iloc[:-1]
        if '조제금액' in df_valid.columns:
            try:
                dispense_amounts = df_valid['조제금액'].apply(
                    lambda x: float(str(x).replace(',', '').replace('-', '0') or 0) if pd.notna(x) else 0
                )
                today_sales['조제금액'] = int(dispense_amounts.sum())
            except:
                today_sales['조제금액'] = 0
        if '총 판매금액' in df_valid.columns:
            try:
                sale_amounts = df_valid['총 판매금액'].apply(
                    lambda x: float(str(x).replace(',', '').replace('-', '0') or 0) if pd.notna(x) else 0
                )
                today_sales['판매금액'] = int(sale_amounts.sum())
            except:
                today_sales['판매금액'] = 0

        html_content = generate_order_report_html(df_merged, col_map, months=months, runway_threshold=runway_threshold, today_sales=today_sales)
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
            'urgent_count': len(df_merged[(df_merged['런웨이_1년평균'] < runway_threshold) | (df_merged['런웨이_3개월평균'] < runway_threshold)]),
            'runway_threshold': runway_threshold
        })

    except Exception as e:
        # 에러 발생 시에도 임시 파일 정리
        if temp_filepath and os.path.exists(temp_filepath):
            os.remove(temp_filepath)
            print(f"🗑️  임시 파일 삭제 (에러): {temp_filepath}")

        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


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

        # 전체 반환 (제한 없음)

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
    """통합 메모 업데이트 API (drug_memos_db 사용)"""
    try:
        data = request.get_json()
        drug_code = data.get('drug_code')
        memo = data.get('memo', '')

        if not drug_code:
            return jsonify({'status': 'error', 'message': '약품코드가 없습니다.'}), 400

        # 통합 메모 DB 사용
        if memo:
            drug_memos_db.upsert_memo(drug_code, memo)
        else:
            drug_memos_db.delete_memo(drug_code)

        return jsonify({'status': 'success', 'message': '메모가 저장되었습니다.'})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/get_memo', methods=['GET'])
def get_memo():
    """통합 메모 조회 API (drug_memos_db 사용)"""
    try:
        drug_code = request.args.get('drug_code')

        if not drug_code:
            return jsonify({'status': 'error', 'message': '약품코드가 없습니다.'}), 400

        # 통합 메모 DB 사용
        memo = drug_memos_db.get_memo(drug_code)

        return jsonify({'status': 'success', 'memo': memo})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/delete-report', methods=['POST'])
def delete_report():
    """보고서 파일 삭제 API"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        report_type = data.get('report_type')

        print(f"🗑️  삭제 요청 받음: filename={filename}, type={report_type}")

        if not filename or not report_type:
            return jsonify({'error': '파일명 또는 보고서 유형이 없습니다.'}), 400

        # 보안: 파일명에 경로 탐색 문자가 없는지 확인
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'error': '잘못된 파일명입니다.'}), 400

        # 보고서 유형에 따라 디렉토리 결정
        if report_type == 'timeseries':
            report_dir = 'inventory_reports'
            valid_prefixes = ['inventory_report_', 'simple_report_']
        elif report_type == 'order':
            report_dir = 'order_calc_reports'
            valid_prefixes = ['order_calculator_report_']
        else:
            return jsonify({'error': '잘못된 보고서 유형입니다.'}), 400

        # 파일명 유효성 검증
        if not any(filename.startswith(prefix) for prefix in valid_prefixes):
            return jsonify({'error': '허용되지 않는 파일입니다.'}), 400

        if not filename.endswith('.html'):
            return jsonify({'error': 'HTML 파일만 삭제할 수 있습니다.'}), 400

        # 파일 경로 생성 (스크립트 위치 기준)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, report_dir, filename)

        print(f"🗑️  삭제 시도 경로: {file_path}")
        print(f"🗑️  파일 존재 여부: {os.path.exists(file_path)}")

        # 파일 존재 확인 및 삭제
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"✅ 보고서 삭제 완료: {filename}")

            # CSV 파일도 함께 삭제 (주문 보고서의 경우)
            if report_type == 'order':
                csv_filename = filename.replace('.html', '.csv')
                csv_path = os.path.join(base_dir, report_dir, csv_filename)
                if os.path.exists(csv_path):
                    os.remove(csv_path)
                    print(f"✅ CSV 파일 삭제 완료: {csv_filename}")

            return jsonify({'success': True, 'message': '보고서가 삭제되었습니다.'})
        else:
            print(f"❌ 파일을 찾을 수 없음: {file_path}")
            return jsonify({'error': '파일을 찾을 수 없습니다.'}), 404

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================
# 재고 수정 관련 API
# ============================================================

@app.route('/api/search-inventory', methods=['GET'])
def search_inventory_api():
    """약품 검색 API"""
    try:
        keyword = request.args.get('q', '').strip()

        if not keyword or len(keyword) < 2:
            return jsonify({'status': 'error', 'message': '검색어는 2글자 이상 입력해주세요.'}), 400

        results = inventory_db.search_inventory(keyword, limit=50)

        return jsonify({
            'status': 'success',
            'count': len(results),
            'results': results
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/get-inventory/<drug_code>', methods=['GET'])
def get_inventory_api(drug_code):
    """단일 약품 정보 조회 API"""
    try:
        result = inventory_db.get_inventory(drug_code)

        if result:
            return jsonify({
                'status': 'success',
                'data': result
            })
        else:
            return jsonify({'status': 'error', 'message': '해당 약품을 찾을 수 없습니다.'}), 404

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/update-inventory', methods=['POST'])
def update_inventory_api():
    """단일 약품 재고 수정 API"""
    try:
        data = request.get_json()
        drug_code = data.get('drug_code')
        new_stock = data.get('new_stock')

        # 유효성 검사
        if not drug_code:
            return jsonify({'status': 'error', 'message': '약품코드가 없습니다.'}), 400

        if new_stock is None:
            return jsonify({'status': 'error', 'message': '재고수량이 없습니다.'}), 400

        try:
            new_stock = float(new_stock)
            # 음수 재고 허용 (시스템 정책)
        except ValueError:
            return jsonify({'status': 'error', 'message': '유효하지 않은 재고수량입니다.'}), 400

        # 재고 업데이트
        result = inventory_db.update_single_inventory(drug_code, new_stock)

        if result['success']:
            print(f"✅ 재고 수정: {drug_code} ({result['previous_stock']} → {result['new_stock']})")
            return jsonify({
                'status': 'success',
                'message': result['message'],
                'previous_stock': result['previous_stock'],
                'new_stock': result['new_stock']
            })
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 404

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ============================================================
# 개별 임계값 관리 API
# ============================================================

@app.route('/api/drug-threshold/<drug_code>', methods=['GET'])
def get_drug_threshold(drug_code):
    """단일 약품 임계값 조회"""
    try:
        threshold = drug_thresholds_db.get_threshold(drug_code)
        return jsonify({
            'status': 'success',
            'data': threshold  # None이면 설정 없음
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/drug-threshold/<drug_code>', methods=['POST'])
def set_drug_threshold(drug_code):
    """단일 약품 임계값 설정/수정"""
    try:
        data = request.get_json()

        stock_threshold = data.get('stock_threshold')
        runway_threshold = data.get('runway_threshold')
        memo = data.get('memo')

        # 타입 변환 (빈 문자열 처리)
        if stock_threshold == '' or stock_threshold is None:
            stock_threshold = None
        else:
            stock_threshold = int(stock_threshold)

        if runway_threshold == '' or runway_threshold is None:
            runway_threshold = None
        else:
            runway_threshold = float(runway_threshold)

        # 둘 다 없으면 에러
        if stock_threshold is None and runway_threshold is None:
            return jsonify({
                'status': 'error',
                'message': '절대재고 임계값 또는 런웨이 임계값 중 하나 이상을 설정해야 합니다.'
            }), 400

        result = drug_thresholds_db.upsert_threshold(
            drug_code,
            절대재고_임계값=stock_threshold,
            런웨이_임계값=runway_threshold,
            메모=memo
        )

        if result['success']:
            return jsonify({
                'status': 'success',
                'message': result['message'],
                'action': result['action']
            })
        else:
            return jsonify({
                'status': 'error',
                'message': result['message']
            }), 500

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/drug-threshold/<drug_code>', methods=['DELETE'])
def delete_drug_threshold(drug_code):
    """단일 약품 임계값 삭제"""
    try:
        result = drug_thresholds_db.delete_threshold(drug_code)

        if result['success']:
            return jsonify({
                'status': 'success',
                'message': result['message']
            })
        else:
            return jsonify({
                'status': 'error',
                'message': result['message']
            }), 404

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/drug-thresholds', methods=['GET'])
def get_all_drug_thresholds():
    """전체 임계값 목록 조회"""
    try:
        df = drug_thresholds_db.get_all_thresholds()

        if df.empty:
            return jsonify({
                'status': 'success',
                'count': 0,
                'data': []
            })

        # DataFrame을 딕셔너리 리스트로 변환
        data = df.to_dict(orient='records')

        # NaN을 None으로 변환 (JSON 직렬화 호환) + 약품명 추가
        import math
        for record in data:
            for key, value in list(record.items()):
                if isinstance(value, float) and math.isnan(value):
                    record[key] = None

            # 약품명 조회 (inventory_db에서)
            drug_info = inventory_db.get_inventory(record['약품코드'])
            record['약품명'] = drug_info.get('약품명', '-') if drug_info else '-'

        return jsonify({
            'status': 'success',
            'count': len(data),
            'data': data
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/drug-thresholds/stats', methods=['GET'])
def get_threshold_stats():
    """임계값 통계 조회"""
    try:
        stats = drug_thresholds_db.get_statistics()
        return jsonify({
            'status': 'success',
            'data': stats
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ============================================================
# 메모 관리 (v3.13)
# ============================================================

@app.route('/api/memos', methods=['GET'])
def get_all_memos_api():
    """전체 메모 목록 조회 (약품명, 재고, 임계값 정보 포함)"""
    try:
        # 1. 메모 목록 조회 (수정일시 내림차순)
        memos = drug_memos_db.get_all_memos_with_details()

        # 2. 각 메모에 추가 정보 붙이기
        enriched_memos = []
        for memo in memos:
            drug_code = memo['약품코드']

            # 약품 정보 조회 (약품명, 현재 재고)
            drug_info = inventory_db.get_inventory(drug_code)
            drug_name = drug_info.get('약품명', '알 수 없음') if drug_info else '알 수 없음'
            current_stock = drug_info.get('현재재고') if drug_info else None

            # 임계값 정보 조회
            threshold = drug_thresholds_db.get_threshold(drug_code)

            enriched_memos.append({
                'drug_code': drug_code,
                'drug_name': drug_name,
                'memo': memo['메모'],
                'created_at': memo['작성일시'],
                'updated_at': memo['수정일시'],
                'current_stock': current_stock,
                'threshold': {
                    'stock': threshold.get('절대재고_임계값') if threshold else None,
                    'runway': threshold.get('런웨이_임계값') if threshold else None
                } if threshold else None
            })

        return jsonify({
            'status': 'success',
            'count': len(enriched_memos),
            'memos': enriched_memos
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/memo/<drug_code>', methods=['DELETE'])
def delete_memo_api(drug_code):
    """메모 삭제"""
    try:
        result = drug_memos_db.delete_memo(drug_code)

        if result['success']:
            return jsonify({
                'status': 'success',
                'message': result['message']
            })
        else:
            return jsonify({
                'status': 'error',
                'message': result['message']
            }), 500

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ============================================================
# 통합 약품 개별 관리 (v3.14)
# ============================================================

@app.route('/drug/manage')
def drug_manage_page():
    """통합 약품 개별 관리 페이지"""
    return render_template('drug_manage.html')


@app.route('/api/drug-management/<drug_code>', methods=['GET'])
def get_drug_management(drug_code):
    """약품의 통합 정보 조회 (재고, 임계값, 메모, 플래그, 환자)"""
    try:
        # 1. 기본 약품 정보
        drug_info = inventory_db.get_inventory(drug_code)
        if not drug_info:
            return jsonify({'status': 'error', 'message': '해당 약품을 찾을 수 없습니다.'}), 404

        # 2. 임계값 정보
        threshold = drug_thresholds_db.get_threshold(drug_code)

        # 3. 메모 정보
        memo = drug_memos_db.get_memo(drug_code)

        # 4. 특별관리 플래그
        special_flag = drug_flags_db.get_flag(drug_code)

        # 5. 연결된 환자 목록
        patients = drug_patient_map_db.get_patients_for_drug(drug_code)

        return jsonify({
            'status': 'success',
            'data': {
                'drug_code': drug_code,
                'drug_name': drug_info.get('약품명', ''),
                'company': drug_info.get('제약회사', ''),
                'drug_type': drug_info.get('약품유형', '미분류'),
                'current_stock': drug_info.get('현재_재고수량', 0),
                'last_updated': drug_info.get('최종_업데이트일시', ''),
                'threshold': {
                    'stock': threshold.get('절대재고_임계값') if threshold else None,
                    'runway': threshold.get('런웨이_임계값') if threshold else None,
                    'active': threshold.get('활성화', True) if threshold else False
                } if threshold else None,
                'memo': memo,
                'special_flag': special_flag,
                'patients': patients
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/drug-management/<drug_code>', methods=['POST'])
def save_drug_management(drug_code):
    """약품 통합 정보 저장"""
    try:
        data = request.get_json()

        results = []

        # 1. 약품명 수정
        if 'drug_name' in data and data['drug_name']:
            result = inventory_db.update_drug_name(drug_code, data['drug_name'])
            results.append(('약품명', result))

        # 2. 재고 수정
        if 'stock' in data and data['stock'] is not None:
            result = inventory_db.update_single_inventory(drug_code, float(data['stock']))
            results.append(('재고', result))

        # 3. 임계값 설정
        if 'threshold' in data:
            th = data['threshold']
            stock_th = th.get('stock')
            runway_th = th.get('runway')

            # 빈 문자열 처리
            if stock_th == '':
                stock_th = None
            if runway_th == '':
                runway_th = None

            if stock_th is not None or runway_th is not None:
                result = drug_thresholds_db.upsert_threshold(
                    drug_code,
                    절대재고_임계값=int(stock_th) if stock_th is not None else None,
                    런웨이_임계값=float(runway_th) if runway_th is not None else None
                )
                results.append(('임계값', result))
            else:
                # 둘 다 없으면 임계값 삭제
                drug_thresholds_db.delete_threshold(drug_code)
                results.append(('임계값', {'success': True, 'message': '임계값이 삭제되었습니다.'}))

        # 4. 메모 저장
        if 'memo' in data:
            memo = data['memo']
            if memo:
                result = drug_memos_db.upsert_memo(drug_code, memo)
            else:
                result = drug_memos_db.delete_memo(drug_code)
            results.append(('메모', result))

        # 5. 특별관리 플래그
        if 'special_flag' in data:
            result = drug_flags_db.set_flag(drug_code, data['special_flag'])
            results.append(('특별관리', result))

        # 6. 환자 연결 (전체 교체 방식)
        # 새 형식: patients (처방량 포함) 또는 이전 형식: patient_ids (호환성)
        if 'patients' in data:
            # 새 형식: [{'patient_id': int, 'dosage': int}, ...]
            patients = data['patients']
            result = drug_patient_map_db.set_patients_for_drug(drug_code, patients)
            results.append(('환자연결', result))
        elif 'patient_ids' in data:
            # 이전 형식: [patient_id, ...]
            patient_ids = data['patient_ids']
            result = drug_patient_map_db.set_patients_for_drug(drug_code, patient_ids)
            results.append(('환자연결', result))

        # 결과 요약
        failed = [r for r in results if not r[1].get('success', False)]
        if failed:
            return jsonify({
                'status': 'partial',
                'message': f'{len(results) - len(failed)}개 성공, {len(failed)}개 실패',
                'details': {r[0]: r[1] for r in results}
            })

        return jsonify({
            'status': 'success',
            'message': '모든 설정이 저장되었습니다.',
            'details': {r[0]: r[1] for r in results}
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/managed-drugs', methods=['GET'])
def get_managed_drugs():
    """설정이 있는 약품 목록 조회 (메모, 임계값, 플래그, 환자 중 하나라도 설정된 약품)"""
    try:
        # 각 DB에서 설정된 약품코드 수집
        drug_codes = set()

        # 1. 메모가 있는 약품
        memos = drug_memos_db.get_all_memos()
        drug_codes.update(memos.keys())

        # 2. 임계값이 설정된 약품
        thresholds_df = drug_thresholds_db.get_all_thresholds()
        if not thresholds_df.empty:
            drug_codes.update(thresholds_df['약품코드'].tolist())

        # 3. 특별관리 플래그가 설정된 약품
        flagged = drug_flags_db.get_flagged_drugs()
        drug_codes.update(flagged)

        # 4. 환자가 연결된 약품
        drugs_with_patients = drug_patient_map_db.get_all_drugs_with_patients()
        drug_codes.update(drugs_with_patients)

        # 약품 정보 조회 및 조합
        result = []
        all_flags = drug_flags_db.get_all_flags()
        all_mappings = drug_patient_map_db.get_all_mappings_dict()

        for drug_code in drug_codes:
            drug_info = inventory_db.get_inventory(drug_code)
            if not drug_info:
                continue

            threshold = drug_thresholds_db.get_threshold(drug_code)
            memo = memos.get(drug_code, '')
            flag = all_flags.get(drug_code, False)
            patient_ids = all_mappings.get(drug_code, [])

            # 환자 정보 조회
            patients = []
            for pid in patient_ids:
                patient = patients_db.get_patient(pid)
                if patient:
                    patients.append({
                        '환자ID': patient['환자ID'],
                        '환자명': patient['환자명'],
                        '주민번호_앞자리': patient['주민번호_앞자리']
                    })

            result.append({
                'drug_code': drug_code,
                'drug_name': drug_info.get('약품명', ''),
                'company': drug_info.get('제약회사', ''),
                'current_stock': drug_info.get('현재_재고수량', 0),
                'has_threshold': threshold is not None,
                'threshold': {
                    'stock': threshold.get('절대재고_임계값') if threshold else None,
                    'runway': threshold.get('런웨이_임계값') if threshold else None
                } if threshold else None,
                'has_memo': bool(memo),
                'memo_preview': memo[:50] + '...' if len(memo) > 50 else memo,
                'special_flag': flag,
                'patients': patients
            })

        # 약품명 기준 정렬
        result.sort(key=lambda x: x['drug_name'])

        return jsonify({
            'status': 'success',
            'count': len(result),
            'data': result
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/managed-drugs/stats', methods=['GET'])
def get_managed_drugs_stats():
    """관리 약품 통계 조회"""
    try:
        memo_count = drug_memos_db.get_memo_count()
        threshold_stats = drug_thresholds_db.get_statistics()
        flagged_count = drug_flags_db.get_flagged_count()
        drugs_with_patients = len(drug_patient_map_db.get_all_drugs_with_patients())
        patient_count = patients_db.get_patient_count()

        return jsonify({
            'status': 'success',
            'data': {
                'memo_count': memo_count,
                'threshold_count': threshold_stats.get('total', 0),
                'flagged_count': flagged_count,
                'drugs_with_patients': drugs_with_patients,
                'patient_count': patient_count
            }
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ============================================================
# 환자 관리 API (v3.14)
# ============================================================

@app.route('/api/patients', methods=['GET'])
def get_all_patients():
    """전체 환자 목록 조회"""
    try:
        patients = patients_db.get_all_patients()
        return jsonify({
            'status': 'success',
            'count': len(patients),
            'data': patients
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/patient', methods=['POST'])
def create_patient():
    """환자 생성"""
    try:
        data = request.get_json()
        환자명 = data.get('name', '').strip()
        주민번호_앞자리 = data.get('birth', '').strip() if data.get('birth') else None
        메모 = data.get('memo', '').strip() if data.get('memo') else None
        방문주기_일 = data.get('visit_cycle')

        if 방문주기_일:
            try:
                방문주기_일 = int(방문주기_일)
            except (ValueError, TypeError):
                방문주기_일 = None

        if not 환자명:
            return jsonify({'status': 'error', 'message': '환자명은 필수입니다.'}), 400

        if not 주민번호_앞자리:
            return jsonify({'status': 'error', 'message': '주민번호 앞자리는 필수입니다.'}), 400

        result = patients_db.upsert_patient(환자명, 주민번호_앞자리, 메모, 방문주기_일=방문주기_일)

        if result['success']:
            return jsonify({
                'status': 'success',
                'message': result['message'],
                'patient_id': result['patient_id']
            })
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 400

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/patient/<int:patient_id>', methods=['GET'])
def get_patient(patient_id):
    """단일 환자 조회"""
    try:
        patient = patients_db.get_patient(patient_id)
        if patient:
            return jsonify({
                'status': 'success',
                'data': patient
            })
        else:
            return jsonify({'status': 'error', 'message': '해당 환자를 찾을 수 없습니다.'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/patient/<int:patient_id>', methods=['PUT'])
def update_patient(patient_id):
    """환자 수정"""
    try:
        data = request.get_json()
        환자명 = data.get('name', '').strip()
        주민번호_앞자리 = data.get('birth', '').strip() if data.get('birth') else None
        메모 = data.get('memo', '').strip() if data.get('memo') else None
        방문주기_일 = data.get('visit_cycle')

        if 방문주기_일:
            try:
                방문주기_일 = int(방문주기_일)
            except (ValueError, TypeError):
                방문주기_일 = None

        if not 환자명:
            return jsonify({'status': 'error', 'message': '환자명은 필수입니다.'}), 400

        if not 주민번호_앞자리:
            return jsonify({'status': 'error', 'message': '주민번호 앞자리는 필수입니다.'}), 400

        result = patients_db.upsert_patient(환자명, 주민번호_앞자리, 메모, 환자ID=patient_id, 방문주기_일=방문주기_일)

        if result['success']:
            return jsonify({
                'status': 'success',
                'message': result['message']
            })
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 400

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/patient/<int:patient_id>', methods=['DELETE'])
def delete_patient(patient_id):
    """환자 삭제 (CASCADE: 연결된 약품 매핑도 삭제)"""
    try:
        result = patients_db.delete_patient(patient_id)

        if result['success']:
            return jsonify({
                'status': 'success',
                'message': result['message']
            })
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 404

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/search-patients', methods=['GET'])
def search_patients():
    """환자 검색"""
    try:
        keyword = request.args.get('q', '').strip()

        if not keyword:
            return jsonify({'status': 'success', 'data': []})

        patients = patients_db.search_patients(keyword, limit=20)

        return jsonify({
            'status': 'success',
            'count': len(patients),
            'data': patients
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ============================================================
# 약품-환자 매핑 API (v3.14)
# ============================================================

@app.route('/api/drug/<drug_code>/patients', methods=['GET'])
def get_drug_patients(drug_code):
    """약품에 연결된 환자 목록 조회"""
    try:
        patients = drug_patient_map_db.get_patients_for_drug(drug_code)
        return jsonify({
            'status': 'success',
            'count': len(patients),
            'data': patients
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/drug/<drug_code>/patient/<int:patient_id>', methods=['POST'])
def link_drug_patient(drug_code, patient_id):
    """약품과 환자 연결"""
    try:
        result = drug_patient_map_db.link_patient(drug_code, patient_id)

        if result['success']:
            return jsonify({
                'status': 'success',
                'message': result['message']
            })
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 400

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/drug/<drug_code>/patient/<int:patient_id>', methods=['DELETE'])
def unlink_drug_patient(drug_code, patient_id):
    """약품과 환자 연결 해제"""
    try:
        result = drug_patient_map_db.unlink_patient(drug_code, patient_id)

        if result['success']:
            return jsonify({
                'status': 'success',
                'message': result['message']
            })
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 404

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ============================================================
# 환자 관리 페이지 (v3.16)
# ============================================================

@app.route('/patient/manage')
def patient_manage_page():
    """환자 관리 페이지"""
    return render_template('patient_manage.html')


@app.route('/api/patients-with-drugs', methods=['GET'])
def get_patients_with_drugs():
    """환자 목록 + 약품 수 + 부족 상태 조회"""
    try:
        patients = patients_db.get_all_patients()

        result = []
        for patient in patients:
            patient_id = patient['환자ID']

            # 연결된 약품 목록 조회 (처방량 포함)
            drugs = drug_patient_map_db.get_drugs_for_patient_with_dosage(patient_id)
            drug_count = len(drugs)

            # 각 약품의 재고 상태 확인
            shortage_count = 0
            exact_count = 0
            for drug in drugs:
                drug_code = drug['약품코드']
                dosage = drug.get('1회_처방량', 1)

                # 재고 조회
                inventory = inventory_db.get_inventory(drug_code)
                if inventory:
                    current_stock = inventory.get('현재_재고수량', 0)
                    if current_stock < dosage:
                        shortage_count += 1
                    elif current_stock == dosage:
                        exact_count += 1

            result.append({
                'patient_id': patient_id,
                'patient_name': patient['환자명'],
                'birth': patient.get('주민번호_앞자리', ''),
                'memo': patient.get('메모', ''),
                'visit_cycle': patient.get('방문주기_일'),
                'drug_count': drug_count,
                'shortage_count': shortage_count,
                'exact_count': exact_count,
                'has_shortage': shortage_count > 0,
                'has_exact': exact_count > 0
            })

        # 정렬: 부족 약품 있는 환자 우선, 그 다음 부족 개수 내림차순
        result.sort(key=lambda x: (-int(x['has_shortage']), -x['shortage_count'], x['patient_name']))

        return jsonify({
            'status': 'success',
            'count': len(result),
            'data': result
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/patient/<int:patient_id>/drugs-with-stock', methods=['GET'])
def get_patient_drugs_with_stock(patient_id):
    """환자별 약품 상세 (재고 포함)"""
    try:
        # 환자 확인
        patient = patients_db.get_patient(patient_id)
        if not patient:
            return jsonify({'status': 'error', 'message': '환자를 찾을 수 없습니다.'}), 404

        # 연결된 약품 목록 조회 (처방량 포함)
        drugs = drug_patient_map_db.get_drugs_for_patient_with_dosage(patient_id)

        result = []
        for drug_mapping in drugs:
            drug_code = drug_mapping['약품코드']
            dosage = drug_mapping.get('1회_처방량', 1)

            # 재고 정보 조회
            inventory = inventory_db.get_inventory(drug_code)
            if not inventory:
                continue

            current_stock = inventory.get('현재_재고수량', 0)

            # 상태 판단: 부족 < 딱맞음 = 충분 >
            if current_stock < dosage:
                status = 'shortage'
            elif current_stock == dosage:
                status = 'exact'
            else:
                status = 'sufficient'

            result.append({
                'drug_code': drug_code,
                'drug_name': inventory.get('약품명', ''),
                'company': inventory.get('제약회사', ''),
                'dosage': dosage,
                'current_stock': current_stock,
                'status': status,
                'linked_at': drug_mapping.get('연결일시', '')
            })

        # 재고 상태 순서로 정렬 (부족 > 딱맞음 > 충분)
        status_order = {'shortage': 0, 'exact': 1, 'sufficient': 2}
        result.sort(key=lambda x: status_order.get(x['status'], 3))

        return jsonify({
            'status': 'success',
            'patient': {
                'id': patient_id,
                'name': patient['환자명'],
                'birth': patient.get('주민번호_앞자리', ''),
                'memo': patient.get('메모', ''),
                'visit_cycle': patient.get('방문주기_일')
            },
            'drug_count': len(result),
            'shortage_count': len([d for d in result if d['status'] == 'shortage']),
            'exact_count': len([d for d in result if d['status'] == 'exact']),
            'drugs': result
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/patient/<int:patient_id>/link-drug', methods=['POST'])
def link_drug_to_patient(patient_id):
    """환자에 약품 연결 추가"""
    try:
        data = request.get_json()
        drug_code = data.get('drug_code')
        dosage = data.get('dosage', 1)

        if not drug_code:
            return jsonify({'status': 'error', 'message': '약품코드가 필요합니다.'}), 400

        # 환자 확인
        patient = patients_db.get_patient(patient_id)
        if not patient:
            return jsonify({'status': 'error', 'message': '환자를 찾을 수 없습니다.'}), 404

        # 약품 확인
        inventory = inventory_db.get_inventory(drug_code)
        if not inventory:
            return jsonify({'status': 'error', 'message': '약품을 찾을 수 없습니다.'}), 404

        # 연결
        result = drug_patient_map_db.link_patient(drug_code, patient_id, dosage)

        if result['success']:
            return jsonify({
                'status': 'success',
                'message': result['message']
            })
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/patient/<int:patient_id>/unlink-drug/<drug_code>', methods=['DELETE'])
def unlink_drug_from_patient(patient_id, drug_code):
    """환자와 약품 연결 해제"""
    try:
        result = drug_patient_map_db.unlink_patient(drug_code, patient_id)

        if result['success']:
            return jsonify({
                'status': 'success',
                'message': result['message']
            })
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 404
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ============================================================
# 특별관리 플래그 API (v3.14)
# ============================================================

@app.route('/api/drug/<drug_code>/toggle-flag', methods=['POST'])
def toggle_drug_flag(drug_code):
    """특별관리 플래그 토글"""
    try:
        result = drug_flags_db.toggle_flag(drug_code)

        if result['success']:
            return jsonify({
                'status': 'success',
                'message': result['message'],
                'flag': result['flag']
            })
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 500

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/flagged-drugs', methods=['GET'])
def get_flagged_drugs():
    """특별관리 약품 목록 조회"""
    try:
        drug_codes = drug_flags_db.get_flagged_drugs()

        # 약품 정보와 함께 반환
        result = []
        for drug_code in drug_codes:
            drug_info = inventory_db.get_inventory(drug_code)
            if drug_info:
                result.append({
                    'drug_code': drug_code,
                    'drug_name': drug_info.get('약품명', ''),
                    'company': drug_info.get('제약회사', ''),
                    'current_stock': drug_info.get('현재_재고수량', 0)
                })

        return jsonify({
            'status': 'success',
            'count': len(result),
            'data': result
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ============================================================
# 최소 재고 버퍼 계산 API (v3.15)
# ============================================================

@app.route('/api/drug/<drug_code>/calculate-buffer', methods=['POST'])
def calculate_drug_buffer(drug_code):
    """약품의 최소 재고 버퍼 계산"""
    try:
        data = request.get_json() or {}
        risk_level = data.get('risk_level', 'safe')

        # 클라이언트에서 patients 데이터를 보내면 그것을 사용 (아직 저장 전인 경우)
        # 그렇지 않으면 DB에서 조회
        if 'patients' in data and data['patients']:
            # 클라이언트 데이터 사용 (아직 저장 전인 환자 정보)
            patients_data = []
            for p in data['patients']:
                patient_info = patients_db.get_patient(p.get('patient_id'))
                if patient_info:
                    patients_data.append({
                        '환자ID': patient_info['환자ID'],
                        '환자명': patient_info.get('환자명', ''),
                        '방문주기_일': p.get('visit_cycle') or patient_info.get('방문주기_일') or 30,
                        '1회_처방량': p.get('dosage') or 1
                    })
        else:
            # DB에서 조회
            patients_data = drug_patient_map_db.get_patients_for_drug_with_dosage(drug_code)

        # 버퍼 계산
        result = buffer_calculator.calculate_min_buffer(patients_data, risk_level)

        return jsonify({
            'status': 'success',
            'data': result
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/risk-levels', methods=['GET'])
def get_risk_levels():
    """사용 가능한 리스크 수준 목록 조회"""
    try:
        levels = buffer_calculator.get_risk_levels()
        return jsonify({
            'status': 'success',
            'data': levels
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ============================================================
# 약품명 수정 API (v3.14)
# ============================================================

@app.route('/api/drug/<drug_code>/rename', methods=['POST'])
def rename_drug(drug_code):
    """약품명 수정"""
    try:
        data = request.get_json()
        new_name = data.get('name', '').strip()

        if not new_name:
            return jsonify({'status': 'error', 'message': '약품명은 필수입니다.'}), 400

        result = inventory_db.update_drug_name(drug_code, new_name)

        if result['success']:
            return jsonify({
                'status': 'success',
                'message': result['message'],
                'previous_name': result.get('previous_name'),
                'new_name': result.get('new_name')
            })
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 400

    except Exception as e:
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
