"""
routes/data.py
데이터 파일 업로드 및 관리 API Blueprint

엔드포인트:
- GET  /data/manage                    - 데이터 관리 페이지
- GET  /api/data-files                 - 파일 목록 조회
- POST /api/check-data-file            - 파일 존재/월 정보 확인 (업로드 전 검사)
- POST /api/upload-data-file           - 파일 업로드
- POST /api/delete-data-file           - 파일 삭제
- GET  /api/preview-data-file/<name>   - 파일 미리보기
- GET  /api/validate-data-file/<name>  - 파일 유효성 검사
"""

import os
import traceback
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify
import pandas as pd

import paths
import drug_timeseries_db
from read_csv import extract_month_from_file
from routes.main import check_database_ready


data_bp = Blueprint('data', __name__)


# 허용된 파일 확장자
ALLOWED_EXTENSIONS = {'csv', 'xls', 'xlsx'}


def allowed_file(filename):
    """파일 확장자 검증"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@data_bp.route('/data/manage')
def data_manage():
    """데이터 파일 관리 페이지"""
    # DB 상태 확인
    is_ready, result = check_database_ready()
    db_stats = result if is_ready else None
    return render_template('data_manage.html', db_stats=db_stats)


@data_bp.route('/api/data-files')
def list_data_files():
    """data/ 폴더의 파일 목록 조회"""
    try:
        data_path = paths.DATA_PATH

        # data/ 폴더가 없으면 빈 목록 반환
        if not os.path.exists(data_path):
            return jsonify({
                'files': [],
                'total_count': 0,
                'period': None
            })

        # CSV, XLS, XLSX 파일 목록 수집
        actual_files = []
        for filename in os.listdir(data_path):
            if filename.endswith(('.csv', '.xls', '.xlsx')):
                actual_files.append(filename)

        # DB 메타데이터와 실제 파일 동기화 (self-healing)
        drug_timeseries_db.sync_data_files(actual_files, extract_month_from_file)

        # DB에서 파일 메타데이터 조회
        file_metadata = drug_timeseries_db.get_data_files_metadata()

        files = []
        for filename in actual_files:
            file_path = os.path.join(data_path, filename)
            stat = os.stat(file_path)

            # DB 메타데이터에서 월 정보 및 업로드 일시 조회
            if filename in file_metadata:
                month = file_metadata[filename]['month']
                uploaded_at = file_metadata[filename].get('uploaded_at')
            else:
                month = extract_month_from_file(filename)
                uploaded_at = None

            # 파일 크기 포맷팅
            size_bytes = stat.st_size
            if size_bytes < 1024:
                size_display = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                size_display = f"{size_bytes / 1024:.1f} KB"
            else:
                size_display = f"{size_bytes / (1024 * 1024):.1f} MB"

            files.append({
                'filename': filename,
                'month': month,
                'size_bytes': size_bytes,
                'size_display': size_display,
                'file_modified_at': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'uploaded_at': uploaded_at
            })

        # 월 기준 내림차순 정렬 (최신이 위로)
        files.sort(key=lambda x: x['month'] or '', reverse=True)

        # 파일 기간 정보 계산
        file_months = [f['month'] for f in files if f['month']]
        period = None
        if file_months:
            sorted_months = sorted(file_months)
            period = {
                'start': sorted_months[0],
                'end': sorted_months[-1],
                'months': len(file_months)
            }

        # DB 월 목록 조회
        db_months = []
        db_metadata = drug_timeseries_db.get_metadata()
        if db_metadata and 'month_list' in db_metadata:
            db_months = db_metadata['month_list']

        return jsonify({
            'files': files,
            'total_count': len(files),
            'period': period,
            'file_months': sorted(file_months) if file_months else [],
            'db_months': db_months
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@data_bp.route('/api/check-data-file', methods=['POST'])
def check_data_file():
    """데이터 파일 존재 여부 및 월 정보 확인 (업로드 전 사전 검사)"""
    try:
        data = request.get_json()
        filename = data.get('filename', '')

        if not filename:
            return jsonify({'error': '파일명이 없습니다.'}), 400

        if not allowed_file(filename):
            return jsonify({'error': '허용되지 않는 파일 형식입니다. (CSV, XLS, XLSX만 가능)'}), 400

        # 파일명에서 월 정보 추출
        month = extract_month_from_file(filename)
        if not month:
            # error 필드 없이 valid: false만 반환 → 프론트엔드에서 월 선택 모달 표시
            return jsonify({
                'valid': False,
                'filename': filename
            })

        # 동일 파일 존재 여부 확인
        file_path = os.path.join(paths.DATA_PATH, filename)
        exists = os.path.exists(file_path)

        # 동일 월 다른 파일 존재 여부 확인
        same_month_files = []
        if os.path.exists(paths.DATA_PATH):
            for f in os.listdir(paths.DATA_PATH):
                if f != filename and allowed_file(f):
                    f_month = extract_month_from_file(f)
                    if f_month == month:
                        same_month_files.append(f)

        return jsonify({
            'valid': True,
            'filename': filename,
            'month': month,
            'exists': exists,
            'same_month_files': same_month_files
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@data_bp.route('/api/upload-data-file', methods=['POST'])
def upload_data_file():
    """데이터 파일 업로드 - 원본 파일명 유지, 메타데이터 DB 저장"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': '파일이 없습니다.'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '파일이 선택되지 않았습니다.'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': '허용되지 않는 파일 형식입니다. (CSV, XLS, XLSX만 가능)'}), 400

        # 사용자가 직접 지정한 월이 있는지 확인
        custom_month = request.form.get('month', '').strip()

        if custom_month:
            # 사용자 지정 월 사용
            import re
            if not re.match(r'^\d{4}-\d{2}$', custom_month):
                return jsonify({'error': '월 형식이 올바르지 않습니다. (예: 2025-01)'}), 400
            month = custom_month
        else:
            # 파일명에서 월 정보 추출
            month = extract_month_from_file(file.filename)
            if not month:
                return jsonify({'error': '파일명에서 날짜를 추출할 수 없습니다. (예: 2025-01.xls, 202501.csv)'}), 400

        # data/ 폴더 생성 (없으면)
        data_path = paths.DATA_PATH
        if not os.path.exists(data_path):
            os.makedirs(data_path)

        # 파일명 결정
        original_filename = file.filename
        _, ext = os.path.splitext(original_filename)

        # 사용자가 월을 직접 지정한 경우: 파일명을 YYYY-MM.확장자로 표준화
        # (이후 로직에서 파일명으로 날짜 추출 가능하도록)
        if custom_month:
            save_filename = f"{month}{ext}"
        else:
            save_filename = original_filename

        file_path = os.path.join(data_path, save_filename)

        # 동일 파일명이 존재하는 경우 처리
        is_replacement = False
        if os.path.exists(file_path):
            # 같은 월 데이터인지 확인
            existing_metadata = drug_timeseries_db.get_data_files_metadata()
            if save_filename in existing_metadata and existing_metadata[save_filename]['month'] == month:
                # 같은 월 데이터 교체
                is_replacement = True
            else:
                # 다른 월 데이터 - 중복 파일명 처리
                name_without_ext, ext = os.path.splitext(original_filename)
                counter = 1
                while os.path.exists(file_path):
                    save_filename = f"{name_without_ext}_{counter}{ext}"
                    file_path = os.path.join(data_path, save_filename)
                    counter += 1

        # 파일 저장
        file.save(file_path)

        # DB에 메타데이터 저장
        drug_timeseries_db.add_data_file(save_filename, month)

        action = '교체' if is_replacement else '업로드'
        manual_note = ' (수동 지정)' if custom_month else ''
        print(f"📁 데이터 파일 {action} 완료: {save_filename}{manual_note}")

        return jsonify({
            'success': True,
            'filename': save_filename,
            'original_filename': original_filename,
            'month': month,
            'is_replacement': is_replacement,
            'is_manual': bool(custom_month),
            'message': f'{save_filename} 파일이 {action}되었습니다.'
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@data_bp.route('/api/delete-data-file', methods=['POST'])
def delete_data_file():
    """데이터 파일 삭제"""
    try:
        data = request.get_json()
        filename = data.get('filename')

        if not filename:
            return jsonify({'error': '파일명이 없습니다.'}), 400

        # 보안: 경로 탐색 방지
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'error': '잘못된 파일명입니다.'}), 400

        # 확장자 검증
        if not allowed_file(filename):
            return jsonify({'error': '허용되지 않는 파일 형식입니다.'}), 400

        file_path = os.path.join(paths.DATA_PATH, filename)

        if not os.path.exists(file_path):
            return jsonify({'error': '파일을 찾을 수 없습니다.'}), 404

        os.remove(file_path)

        # DB에서 메타데이터도 삭제
        drug_timeseries_db.remove_data_file(filename)

        print(f"🗑️  데이터 파일 삭제 완료: {filename}")

        return jsonify({
            'success': True,
            'message': f'{filename} 파일이 삭제되었습니다.'
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@data_bp.route('/api/preview-data-file/<filename>')
def preview_data_file(filename):
    """데이터 파일 미리보기 (최대 10행)"""
    try:
        # 보안: 경로 탐색 방지
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'error': '잘못된 파일명입니다.'}), 400

        if not allowed_file(filename):
            return jsonify({'error': '허용되지 않는 파일 형식입니다.'}), 400

        file_path = os.path.join(paths.DATA_PATH, filename)

        if not os.path.exists(file_path):
            return jsonify({'error': '파일을 찾을 수 없습니다.'}), 404

        # 파일 읽기
        if filename.endswith('.csv'):
            # CSV: 인코딩 시도
            df = None
            for encoding in ['utf-8', 'cp949', 'euc-kr']:
                try:
                    df = pd.read_csv(file_path, encoding=encoding, dtype={'약품코드': str})
                    break
                except:
                    continue
            if df is None:
                return jsonify({'error': '파일을 읽을 수 없습니다.'}), 400
        else:
            # Excel 파일
            try:
                if filename.endswith('.xls'):
                    df = pd.read_excel(file_path, engine='calamine', dtype={'약품코드': str})
                else:
                    df = pd.read_excel(file_path, engine='openpyxl', dtype={'약품코드': str})
            except:
                df = pd.read_excel(file_path, dtype={'약품코드': str})

        # 전체 행 수
        total_rows = len(df)

        # 미리보기 (최대 10행)
        preview_df = df.head(10)

        # 컬럼명과 데이터 추출
        columns = preview_df.columns.tolist()
        rows = preview_df.fillna('').values.tolist()

        return jsonify({
            'success': True,
            'columns': columns,
            'rows': rows,
            'total_rows': total_rows,
            'preview_rows': len(rows)
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@data_bp.route('/api/validate-data-file/<filename>')
def validate_data_file(filename):
    """데이터 파일 유효성 검증"""
    try:
        # 보안: 경로 탐색 방지
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'error': '잘못된 파일명입니다.'}), 400

        if not allowed_file(filename):
            return jsonify({'error': '허용되지 않는 파일 형식입니다.'}), 400

        file_path = os.path.join(paths.DATA_PATH, filename)

        if not os.path.exists(file_path):
            return jsonify({'error': '파일을 찾을 수 없습니다.'}), 404

        # 월 정보 확인: DB 메타데이터 우선, 없으면 파일명에서 추출
        file_metadata = drug_timeseries_db.get_data_files_metadata()
        if filename in file_metadata:
            month = file_metadata[filename]['month']
        else:
            month = extract_month_from_file(filename)

        # 파일 읽기 시도
        df = None
        read_error = None

        if filename.endswith('.csv'):
            for encoding in ['utf-8', 'cp949', 'euc-kr']:
                try:
                    df = pd.read_csv(file_path, encoding=encoding, nrows=100, dtype={'약품코드': str})
                    break
                except Exception as e:
                    read_error = str(e)
        else:
            try:
                if filename.endswith('.xls'):
                    df = pd.read_excel(file_path, engine='calamine', nrows=100, dtype={'약품코드': str})
                else:
                    df = pd.read_excel(file_path, engine='openpyxl', nrows=100, dtype={'약품코드': str})
            except Exception as e:
                read_error = str(e)

        if df is None:
            return jsonify({
                'valid': False,
                'month': month,
                'error': f'파일을 읽을 수 없습니다: {read_error}',
                'required_columns': [],
                'present_columns': [],
                'missing_columns': [],
                'row_count': 0,
                'warnings': ['파일 읽기 실패']
            })

        # 필수 컬럼 검증
        required_columns = ['약품코드', '약품명', '재고수량']
        present_columns = df.columns.tolist()
        missing_columns = [col for col in required_columns if col not in present_columns]

        # 경고 메시지 생성
        warnings = []
        if missing_columns:
            warnings.append(f"필수 컬럼 누락: {', '.join(missing_columns)}")

        if month is None:
            warnings.append("파일명에서 날짜를 추출할 수 없습니다")

        # 전체 행 수 (100행만 읽었으므로 실제 행 수 확인 필요)
        if filename.endswith('.csv'):
            for encoding in ['utf-8', 'cp949', 'euc-kr']:
                try:
                    full_df = pd.read_csv(file_path, encoding=encoding, dtype={'약품코드': str})
                    row_count = len(full_df)
                    break
                except:
                    row_count = len(df)
        else:
            try:
                if filename.endswith('.xls'):
                    full_df = pd.read_excel(file_path, engine='calamine', dtype={'약품코드': str})
                else:
                    full_df = pd.read_excel(file_path, engine='openpyxl', dtype={'약품코드': str})
                row_count = len(full_df)
            except:
                row_count = len(df)

        return jsonify({
            'valid': len(missing_columns) == 0 and month is not None,
            'month': month,
            'required_columns': required_columns,
            'present_columns': present_columns,
            'missing_columns': missing_columns,
            'row_count': row_count,
            'warnings': warnings
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
