"""
routes/reports.py
보고서 생성, 관리 및 체크/메모 API Blueprint

엔드포인트:
- POST /generate/simple_report       - 전문약/일반약 재고 보고서 생성
- POST /generate/volatility_report   - 고변동성 보고서 생성
- POST /api/calculate-order          - 주문 산출 보고서 생성
- GET  /api/list-reports/<type>      - 보고서 목록 조회
- GET  /reports/<path:filename>      - 보고서 파일 서빙
- POST /api/delete-report            - 보고서 삭제
- GET  /api/get_checked_items        - 체크된 항목 조회
- POST /api/toggle_checked_item      - 체크 토글
- POST /api/update_memo              - 메모 업데이트
- GET  /api/get_memo                 - 메모 조회
- GET  /api/memos                    - 전체 메모 목록
- DELETE /api/memo/<code>            - 메모 삭제
"""

import os
import traceback
from datetime import datetime

from flask import Blueprint, request, jsonify, send_file, current_app
import pandas as pd

import paths
import inventory_db
import drug_timeseries_db
import checked_items_db
import drug_memos_db
import drug_thresholds_db
import inventory_updater
from generate_single_ma_report import create_and_save_report as create_simple_report
from drug_order_calculator import generate_order_report_html
from utils import read_today_file, generate_month_list_from_metadata


reports_bp = Blueprint('reports', __name__)


# 허용된 파일 확장자
ALLOWED_EXTENSIONS = {'csv', 'xls', 'xlsx'}


def allowed_file(filename):
    """파일 확장자 검증"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@reports_bp.route('/generate/simple_report', methods=['POST'])
def generate_simple_report_route():
    """단순 재고 관리 보고서 생성 API (Single MA, 선택적 재고 파일 업로드 지원)"""
    temp_filepath = None
    inventory_result = None

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

        # 선택적 재고 파일 업로드 처리
        if 'inventoryFile' in request.files:
            file = request.files['inventoryFile']
            if file and file.filename != '':
                if not allowed_file(file.filename):
                    return jsonify({'status': 'error', 'message': '허용되지 않는 파일 형식입니다. (csv, xls, xlsx만 가능)'}), 400

                import uuid
                temp_filename = f"temp_inventory_{uuid.uuid4().hex[:8]}{os.path.splitext(file.filename)[1]}"
                temp_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], temp_filename)

                os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(temp_filepath)

                abs_temp_filepath = os.path.abspath(temp_filepath)
                print(f"📦 재고 분석 보고서 - {file.filename} 업로드 완료, 재고 업데이트 중...")

                inventory_result = inventory_updater.update_inventory_from_today_csv(abs_temp_filepath)

                if inventory_result is None:
                    return jsonify({'status': 'error', 'message': '재고 파일을 처리할 수 없습니다. 파일 형식을 확인해주세요.'}), 400

                print(f"✅ 재고 업데이트 완료: {inventory_result}")

        # 약품 유형 결정
        drug_type = '전문약' if mode == 'dispense' else '일반약'

        # drug_timeseries DB에서 데이터 로드
        df = drug_timeseries_db.get_processed_data(drug_type=drug_type)

        if df.empty:
            return jsonify({'status': 'error', 'message': f'{drug_type} 데이터가 없습니다.'}), 404

        # DB 메타데이터에서 월 정보 추출 (공통 유틸 함수 사용)
        months = generate_month_list_from_metadata()

        if not months:
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

        response_data = {
            'status': 'success',
            'report_url': f'/reports/{report_filename}',
            'report_filename': report_filename,
            'drug_type': drug_type,
            'drug_count': len(df),
            'ma_months': ma_months,
            'inventory_updated': inventory_result is not None
        }

        if inventory_result is not None:
            response_data['inventory_result'] = inventory_result

        return jsonify(response_data)

    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

    finally:
        if temp_filepath and os.path.exists(temp_filepath):
            os.remove(temp_filepath)
            print(f"🗑️  임시 파일 삭제: {temp_filepath}")


@reports_bp.route('/generate/volatility_report', methods=['POST'])
def generate_volatility_report_route():
    """고변동성 약품 보고서 생성 API"""
    try:
        mode = request.form.get('mode', 'dispense')
        threshold_high = float(request.form.get('threshold_high', 0.5))
        threshold_mid = float(request.form.get('threshold_mid', 0.3))
        analysis_period = int(request.form.get('analysis_period', 0))  # 0 = 전체 기간

        if mode not in ['dispense', 'sale']:
            return jsonify({'status': 'error', 'message': '잘못된 보고서 유형입니다.'}), 400

        if not (0 < threshold_mid < threshold_high < 1.5):
            return jsonify({'status': 'error', 'message': 'CV 임계값 설정이 올바르지 않습니다.'}), 400

        # 약품 유형 결정
        drug_type = '전문약' if mode == 'dispense' else '일반약'

        # drug_timeseries DB에서 데이터 로드
        df = drug_timeseries_db.get_processed_data(drug_type=drug_type)

        if df.empty:
            return jsonify({'status': 'error', 'message': f'{drug_type} 데이터가 없습니다.'}), 404

        # DB 메타데이터에서 월 정보 추출 (공통 유틸 함수 사용)
        months = generate_month_list_from_metadata()

        if not months:
            first_record = df.iloc[0]
            num_months = len(first_record['월별_조제수량_리스트'])
            months = [f"Month {i+1}" for i in range(num_months)]

        # 분석 기간 적용 (최근 N개월만 사용)
        if analysis_period > 0 and len(months) > analysis_period:
            months = months[-analysis_period:]

        # 보고서 생성
        from generate_volatility_report import create_and_save_report as create_volatility_report
        report_path = create_volatility_report(df, months, mode=mode,
                                                threshold_high=threshold_high,
                                                threshold_mid=threshold_mid,
                                                open_browser=False)

        report_filename = os.path.basename(report_path)

        return jsonify({
            'status': 'success',
            'report_url': f'/reports/{report_filename}',
            'report_filename': report_filename,
            'drug_type': drug_type,
            'drug_count': len(df)
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@reports_bp.route('/api/calculate-order', methods=['POST'])
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
        temp_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], temp_filename)

        # uploads 폴더가 없으면 생성
        os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)

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

        # drug_order_calculator의 merge_and_calculate 함수 재사용
        from drug_order_calculator import merge_and_calculate, load_processed_data

        # 시계열 데이터 로드 (drug_order_calculator와 동일한 방식)
        df_processed = load_processed_data()

        # today 파일에서 약품코드 추출
        today_codes = set(df_today['약품코드'].astype(str))

        # 현재 재고 로드 (today 파일 약품만 필터링)
        df_recent = inventory_db.get_all_inventory_as_df()
        df_recent_filtered = df_recent[df_recent['약품코드'].isin(today_codes)].copy()

        if df_recent_filtered.empty:
            return jsonify({'error': 'today 파일 약품에 대한 재고 데이터가 없습니다.'}), 404

        # 컬럼명을 merge_and_calculate가 기대하는 형태로 변환
        df_recent_filtered = df_recent_filtered.rename(columns={'현재_재고수량': '현재 재고수량'})

        # today 파일에서 조제수량/판매수량 정보 추출
        today_qty_info = {}
        if '조제수량' in df_today.columns or '판매수량' in df_today.columns:
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

        # merge_and_calculate 호출 (신규 약품 감지, 런웨이 계산 등 모든 로직 포함)
        df_merged = merge_and_calculate(df_recent_filtered, df_processed, today_qty_info)

        # 컬럼명을 web_app.py 스타일로 변환 (generate_order_report_html의 col_map과 매핑)
        df_merged = df_merged.rename(columns={
            '현재 재고수량': '현재_재고수량',
            '1년 이동평균': '1년_이동평균',
            '3개월 이동평균': '3개월_이동평균',
            '당일 소모수량': '당일_소모수량',
            '런웨이': '런웨이_1년평균',
            '3-MA 런웨이': '런웨이_3개월평균'
        })

        # HTML 보고서 생성
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_dir = paths.get_reports_path('order')
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

        # months 생성 (차트용) - 공통 유틸 함수 사용
        months = generate_month_list_from_metadata() or []

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

        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@reports_bp.route('/api/list-reports/<report_type>')
def list_reports(report_type):
    """보고서 목록 조회 API"""
    try:
        if report_type == 'timeseries':
            # 분석 보고서: inventory_reports + volatility_reports
            report_dirs = [
                (paths.get_reports_path('inventory'), ['inventory_report_', 'simple_report_']),
                (paths.get_reports_path('volatility'), ['volatility_report_'])
            ]
        elif report_type == 'order':
            report_dirs = [
                (paths.get_reports_path('order'), ['order_calculator_report_'])
            ]
        else:
            return jsonify({'error': '잘못된 보고서 유형입니다.'}), 400

        reports = []

        for report_dir, file_prefixes in report_dirs:
            # 디렉토리 확인
            if not os.path.exists(report_dir):
                continue

            # HTML 파일만 필터링 (여러 prefix 지원)
            files = [f for f in os.listdir(report_dir)
                    if any(f.startswith(prefix) for prefix in file_prefixes) and f.endswith('.html')]

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

                    # 보고서 스타일 구분
                    if filename.startswith('volatility_report_'):
                        report_info['report_style'] = '고변동성'
                        report_info['ma_months'] = 'CV분석'
                    elif filename.startswith('simple_report_'):
                        report_info['report_style'] = '재고관리'
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

        return jsonify({'reports': reports})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@reports_bp.route('/reports/<path:filename>')
def serve_report(filename):
    """보고서 파일 제공"""
    # 시계열 보고서 (inventory_reports 디렉토리)
    if filename.startswith('inventory_report_') or filename.startswith('simple_report_'):
        file_path = os.path.join(paths.BASE_PATH, 'inventory_reports', filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='text/html')

    # 고변동성 보고서 (volatility_reports 디렉토리)
    elif filename.startswith('volatility_report_'):
        file_path = os.path.join(paths.BASE_PATH, 'volatility_reports', filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='text/html')

    # 주문 보고서 (order_calc_reports 디렉토리)
    elif filename.startswith('order_calculator_report_'):
        file_path = os.path.join(paths.BASE_PATH, 'order_calc_reports', filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='text/html' if filename.endswith('.html') else 'text/csv')

    return "파일을 찾을 수 없습니다.", 404


@reports_bp.route('/api/delete-report', methods=['POST'])
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

        # 보고서 유형에 따라 디렉토리 및 유효 prefix 결정
        if report_type == 'timeseries':
            # timeseries: inventory + volatility 보고서 모두 포함
            report_dirs_map = {
                'inventory_report_': paths.get_reports_path('inventory'),
                'simple_report_': paths.get_reports_path('inventory'),
                'volatility_report_': paths.get_reports_path('volatility')
            }
        elif report_type == 'order':
            report_dirs_map = {
                'order_calculator_report_': paths.get_reports_path('order')
            }
        else:
            return jsonify({'error': '잘못된 보고서 유형입니다.'}), 400

        # 파일명 유효성 검증 및 해당 디렉토리 찾기
        report_dir = None
        for prefix, dir_path in report_dirs_map.items():
            if filename.startswith(prefix):
                report_dir = dir_path
                break

        if report_dir is None:
            return jsonify({'error': '허용되지 않는 파일입니다.'}), 400

        if not filename.endswith('.html'):
            return jsonify({'error': 'HTML 파일만 삭제할 수 있습니다.'}), 400

        # 파일 경로 생성
        file_path = os.path.join(report_dir, filename)

        print(f"🗑️  삭제 시도 경로: {file_path}")
        print(f"🗑️  파일 존재 여부: {os.path.exists(file_path)}")

        # 파일 존재 확인 및 삭제
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"✅ 보고서 삭제 완료: {filename}")

            # CSV 파일도 함께 삭제 (주문 보고서의 경우)
            if report_type == 'order':
                csv_filename = filename.replace('.html', '.csv')
                csv_path = os.path.join(report_dir, csv_filename)
                if os.path.exists(csv_path):
                    os.remove(csv_path)
                    print(f"✅ CSV 파일 삭제 완료: {csv_filename}")

            return jsonify({'success': True, 'message': '보고서가 삭제되었습니다.'})
        else:
            print(f"❌ 파일을 찾을 수 없음: {file_path}")
            return jsonify({'error': '파일을 찾을 수 없습니다.'}), 404

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================
# 체크 항목 관리 API
# ============================================================

@reports_bp.route('/api/get_checked_items', methods=['GET'])
def get_checked_items_api():
    """숨김 처리된 약품 목록 조회 API"""
    try:
        checked_items = checked_items_db.get_checked_items()
        return jsonify({'status': 'success', 'checked_items': list(checked_items)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@reports_bp.route('/api/toggle_checked_item', methods=['POST'])
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
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ============================================================
# 메모 관리 API
# ============================================================

@reports_bp.route('/api/update_memo', methods=['POST'])
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
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@reports_bp.route('/api/get_memo', methods=['GET'])
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
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@reports_bp.route('/api/memos', methods=['GET'])
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
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@reports_bp.route('/api/memo/<drug_code>', methods=['DELETE'])
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
