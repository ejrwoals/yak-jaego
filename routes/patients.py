"""
routes/patients.py
환자 관리 API Blueprint

엔드포인트:
- GET  /api/patients                              - 전체 환자 목록
- POST /api/patient                               - 환자 생성
- GET  /api/patient/<id>                          - 환자 조회
- PUT  /api/patient/<id>                          - 환자 수정
- DELETE /api/patient/<id>                        - 환자 삭제
- GET  /api/search-patients                       - 환자 검색
- GET  /api/drug/<code>/patients                  - 약품별 환자 목록
- POST /api/drug/<code>/patient/<id>              - 약품-환자 연결
- DELETE /api/drug/<code>/patient/<id>            - 약품-환자 연결 해제
- GET  /patient/manage                            - 환자 관리 페이지
- GET  /api/patients-with-drugs                   - 환자+약품 수+부족상태 목록
- GET  /api/patient/<id>/drugs-with-stock         - 환자별 약품+재고 상세
- POST /api/patient/<id>/link-drug                - 환자에 약품 연결
- DELETE /api/patient/<id>/unlink-drug/<code>     - 환자-약품 연결 해제
"""

import traceback

from flask import Blueprint, render_template, request, jsonify

import patients_db
import drug_patient_map_db
import inventory_db
import drug_thresholds_db


patients_bp = Blueprint('patients', __name__)


@patients_bp.route('/api/patients', methods=['GET'])
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


@patients_bp.route('/api/patient', methods=['POST'])
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


@patients_bp.route('/api/patient/<int:patient_id>', methods=['GET'])
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


@patients_bp.route('/api/patient/<int:patient_id>', methods=['PUT'])
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


@patients_bp.route('/api/patient/<int:patient_id>', methods=['DELETE'])
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


@patients_bp.route('/api/search-patients', methods=['GET'])
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
# 약품-환자 매핑 API
# ============================================================

@patients_bp.route('/api/drug/<drug_code>/patients', methods=['GET'])
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


@patients_bp.route('/api/drug/<drug_code>/patient/<int:patient_id>', methods=['POST'])
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


@patients_bp.route('/api/drug/<drug_code>/patient/<int:patient_id>', methods=['DELETE'])
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
# 환자 관리 페이지
# ============================================================

@patients_bp.route('/patient/manage')
def patient_manage_page():
    """환자 관리 페이지"""
    return render_template('patient_manage.html')


@patients_bp.route('/api/patients-with-drugs', methods=['GET'])
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
                'has_exact': exact_count > 0,
                'created_at': patient.get('생성일시'),
                'updated_at': patient.get('수정일시') or patient.get('생성일시')
            })

        # 정렬: 부족 약품 있는 환자 우선, 그 다음 부족 개수 내림차순
        result.sort(key=lambda x: (-int(x['has_shortage']), -x['shortage_count'], x['patient_name']))

        return jsonify({
            'status': 'success',
            'count': len(result),
            'data': result
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@patients_bp.route('/api/patient/<int:patient_id>/drugs-with-stock', methods=['GET'])
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
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@patients_bp.route('/api/patient/<int:patient_id>/link-drug', methods=['POST'])
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
            # 자동 임계값 설정: 연결된 환자들의 최대 처방량으로 임계값 자동 설정
            try:
                patients_with_dosage = drug_patient_map_db.get_patients_for_drug_with_dosage(drug_code)
                if patients_with_dosage:
                    max_dosage = max(p.get('1회_처방량', 1) for p in patients_with_dosage)
                    current_threshold = drug_thresholds_db.get_threshold(drug_code)

                    # 임계값이 없거나 최대 처방량보다 낮으면 자동 설정
                    if current_threshold is None or current_threshold.get('절대재고_임계값') is None:
                        drug_thresholds_db.upsert_threshold(drug_code, 절대재고_임계값=max_dosage)
                    elif current_threshold.get('절대재고_임계값', 0) < max_dosage:
                        # 기존 런웨이 임계값 유지하면서 재고 임계값만 업데이트
                        drug_thresholds_db.upsert_threshold(
                            drug_code,
                            절대재고_임계값=max_dosage,
                            런웨이_임계값=current_threshold.get('런웨이_임계값')
                        )
            except Exception as threshold_error:
                # 임계값 자동 설정 실패해도 연결은 성공으로 처리
                print(f"자동 임계값 설정 실패 (무시됨): {threshold_error}")

            return jsonify({
                'status': 'success',
                'message': result['message']
            })
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@patients_bp.route('/api/patient/<int:patient_id>/unlink-drug/<drug_code>', methods=['DELETE'])
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
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500
