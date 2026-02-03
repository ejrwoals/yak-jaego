"""
routes/drugs.py
약품 관리 API Blueprint

엔드포인트:
- GET  /drug/manage                        - 약품 관리 페이지
- GET  /api/drug-management/<code>         - 약품 통합 정보 조회
- POST /api/drug-management/<code>         - 약품 통합 정보 저장
- GET  /api/managed-drugs                  - 관리 약품 목록
- GET  /api/managed-drugs/stats            - 관리 약품 통계
- POST /api/drug/<code>/toggle-flag        - 특별관리 토글
- GET  /api/flagged-drugs                  - 특별관리 약품 목록
- POST /api/drug/<code>/calculate-buffer   - 버퍼 계산
- GET  /api/risk-levels                    - 리스크 레벨 목록
- POST /api/drug/<code>/rename             - 약품명 수정
"""

import traceback

from flask import Blueprint, render_template, request, jsonify

import inventory_db
import drug_thresholds_db
import drug_memos_db
import drug_flags_db
import drug_patient_map_db
import patients_db
import buffer_calculator


drugs_bp = Blueprint('drugs', __name__)


@drugs_bp.route('/drug/manage')
def drug_manage_page():
    """통합 약품 개별 관리 페이지"""
    return render_template('drug_manage.html')


@drugs_bp.route('/api/drug-management/<drug_code>', methods=['GET'])
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
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@drugs_bp.route('/api/drug-management/<drug_code>', methods=['POST'])
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
        patients_data = None
        if 'patients' in data:
            # 새 형식: [{'patient_id': int, 'dosage': int}, ...]
            patients_data = data['patients']
            result = drug_patient_map_db.set_patients_for_drug(drug_code, patients_data)
            results.append(('환자연결', result))
        elif 'patient_ids' in data:
            # 이전 형식: [patient_id, ...]
            patient_ids = data['patient_ids']
            result = drug_patient_map_db.set_patients_for_drug(drug_code, patient_ids)
            results.append(('환자연결', result))

        # 7. 환자가 있고 재고 임계값이 비어있으면 max(처방량)으로 자동 설정
        if patients_data and len(patients_data) > 0:
            # max(처방량) 계산
            max_dosage = max(p.get('dosage', 1) for p in patients_data)

            # 현재 임계값 확인 (요청에서 받은 값 또는 DB에서 조회)
            th = data.get('threshold', {})
            stock_th = th.get('stock')

            # 재고 임계값이 비어있거나 None이면 자동 설정
            if stock_th is None or stock_th == '':
                # 기존 런웨이 임계값 유지
                existing_th = drug_thresholds_db.get_threshold(drug_code)
                existing_runway = existing_th.get('런웨이_임계값') if existing_th else None

                result = drug_thresholds_db.upsert_threshold(
                    drug_code,
                    절대재고_임계값=max_dosage,
                    런웨이_임계값=existing_runway
                )
                results.append(('자동임계값', {'success': True, 'message': f'환자 최대 처방량({max_dosage}개) 기준으로 재고 임계값 자동 설정', 'auto_threshold': max_dosage}))

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
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@drugs_bp.route('/api/managed-drugs', methods=['GET'])
def get_managed_drugs():
    """설정이 있는 약품 목록 조회 (메모, 임계값, 플래그, 환자 중 하나라도 설정된 약품)"""
    try:
        # 각 DB에서 설정된 약품코드 수집
        drug_codes = set()
        drug_updated_at = {}  # 약품코드 -> 가장 최근 수정일시

        # 1. 메모가 있는 약품 (수정일시 추적)
        memos_with_details = drug_memos_db.get_all_memos_with_details()
        memos = {}
        for m in memos_with_details:
            code = m['약품코드']
            memos[code] = m['메모']
            drug_codes.add(code)
            ts = m.get('수정일시') or m.get('작성일시')
            if ts:
                if code not in drug_updated_at or ts > drug_updated_at[code]:
                    drug_updated_at[code] = ts

        # 2. 임계값이 설정된 약품 (수정일시 추적)
        thresholds_df = drug_thresholds_db.get_all_thresholds()
        if not thresholds_df.empty:
            drug_codes.update(thresholds_df['약품코드'].tolist())
            for _, row in thresholds_df.iterrows():
                code = row['약품코드']
                ts = row.get('수정일시') or row.get('생성일시')
                if ts:
                    if code not in drug_updated_at or ts > drug_updated_at[code]:
                        drug_updated_at[code] = ts

        # 3. 특별관리 플래그가 설정된 약품 (수정일시 추적)
        all_flags_with_ts = drug_flags_db.get_all_flags_with_timestamps()
        for code, data in all_flags_with_ts.items():
            if data['flag']:
                drug_codes.add(code)
                ts = data.get('updated_at')
                if ts:
                    if code not in drug_updated_at or ts > drug_updated_at[code]:
                        drug_updated_at[code] = ts

        # 4. 환자가 연결된 약품
        drugs_with_patients = drug_patient_map_db.get_all_drugs_with_patients()
        drug_codes.update(drugs_with_patients)

        # 약품 정보 조회 및 조합
        result = []
        all_flags = {code: data['flag'] for code, data in all_flags_with_ts.items()}
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
                'patients': patients,
                'updated_at': drug_updated_at.get(drug_code)
            })

        # 약품명 기준 정렬
        result.sort(key=lambda x: x['drug_name'])

        return jsonify({
            'status': 'success',
            'count': len(result),
            'data': result
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@drugs_bp.route('/api/managed-drugs/stats', methods=['GET'])
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


@drugs_bp.route('/api/drug/<drug_code>/toggle-flag', methods=['POST'])
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


@drugs_bp.route('/api/flagged-drugs', methods=['GET'])
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


@drugs_bp.route('/api/drug/<drug_code>/calculate-buffer', methods=['POST'])
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
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@drugs_bp.route('/api/risk-levels', methods=['GET'])
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


@drugs_bp.route('/api/drug/<drug_code>/rename', methods=['POST'])
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
