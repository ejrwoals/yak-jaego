"""
routes/suggestions.py
환자-약품 매칭 제안 API Blueprint

엔드포인트:
- GET  /patient/suggest              - 제안 페이지
- GET  /api/suggestion/status        - 제안 기능 활성화 상태
- GET  /api/suggestion/next          - 다음 제안 약품
- POST /api/suggestion/register      - 제안 약품 환자에 등록
- POST /api/suggestion/skip          - 제안 건너뛰기
- GET  /api/suggestion/new-drugs     - 신규 약품 목록
- GET  /api/suggestion/stats         - 제안 통계
- GET  /api/suggestion/skipped       - 건너뛴 약품 목록
- POST /api/suggestion/skipped/clear - 건너뛴 목록 전체 삭제
- GET  /api/suggestion/drug/<code>   - 약품별 제안 상세
"""

import traceback

from flask import Blueprint, render_template, request, jsonify

import suggestion_engine
import suggestion_db


suggestions_bp = Blueprint('suggestions', __name__)


@suggestions_bp.route('/patient/suggest')
def patient_suggest_page():
    """환자-약품 매칭 제안 페이지"""
    return render_template('patient_suggest.html')


@suggestions_bp.route('/api/suggestion/status', methods=['GET'])
def get_suggestion_status():
    """제안 기능 활성화 상태 조회"""
    try:
        result = suggestion_engine.get_activation_status()
        return jsonify({'status': 'success', 'data': result})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@suggestions_bp.route('/api/suggestion/next', methods=['GET'])
def get_next_suggestion():
    """다음 제안 약품 조회"""
    try:
        suggestion = suggestion_engine.get_next_suggestion()
        if suggestion:
            return jsonify({'status': 'success', 'data': suggestion})
        else:
            return jsonify({
                'status': 'success',
                'data': None,
                'message': '제안할 약품이 없습니다.'
            })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@suggestions_bp.route('/api/suggestion/register', methods=['POST'])
def register_suggestion():
    """제안된 약품을 환자에게 등록"""
    try:
        data = request.get_json()
        drug_code = data.get('drug_code')
        patient_id = data.get('patient_id')
        dosage = data.get('dosage', 1)

        if not drug_code:
            return jsonify({'status': 'error', 'message': '약품코드가 없습니다.'}), 400
        if not patient_id:
            return jsonify({'status': 'error', 'message': '환자ID가 없습니다.'}), 400

        result = suggestion_engine.register_drug_for_suggestion(drug_code, patient_id, dosage)

        if result['success']:
            return jsonify({'status': 'success', 'message': result['message']})
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 400

    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@suggestions_bp.route('/api/suggestion/skip', methods=['POST'])
def skip_suggestion():
    """제안 건너뛰기"""
    try:
        data = request.get_json()
        drug_code = data.get('drug_code')

        if not drug_code:
            return jsonify({'status': 'error', 'message': '약품코드가 없습니다.'}), 400

        result = suggestion_engine.skip_suggestion(drug_code)

        if result['success']:
            return jsonify({
                'status': 'success',
                'message': result['message'],
                'skip_count': result['skip_count']
            })
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 500

    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@suggestions_bp.route('/api/suggestion/new-drugs', methods=['GET'])
def get_new_drugs():
    """신규 약품 목록 (주기성 분석 불가)"""
    try:
        drugs = suggestion_engine.get_new_drugs_list()
        return jsonify({
            'status': 'success',
            'count': len(drugs),
            'data': drugs
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@suggestions_bp.route('/api/suggestion/stats', methods=['GET'])
def get_suggestion_stats():
    """제안 관련 통계 조회"""
    try:
        stats = suggestion_engine.get_suggestion_stats()
        return jsonify({'status': 'success', 'data': stats})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@suggestions_bp.route('/api/suggestion/skipped', methods=['GET'])
def get_skipped_drugs():
    """건너뛴 약품 목록 조회"""
    try:
        drugs = suggestion_engine.get_skipped_drugs_list()
        return jsonify({
            'status': 'success',
            'data': drugs,
            'count': len(drugs)
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@suggestions_bp.route('/api/suggestion/skipped/clear', methods=['POST'])
def clear_skipped_drugs():
    """건너뛴 약품 목록 전체 삭제"""
    try:
        result = suggestion_db.clear_all()
        if result['success']:
            return jsonify({
                'status': 'success',
                'message': result['message'],
                'count': result.get('count', 0)
            })
        else:
            return jsonify({'status': 'error', 'message': result['message']}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@suggestions_bp.route('/api/suggestion/drug/<drug_code>', methods=['GET'])
def get_drug_suggestion(drug_code):
    """특정 약품의 제안 상세 정보 조회"""
    try:
        suggestion = suggestion_engine.get_drug_suggestion(drug_code)
        if suggestion:
            return jsonify({'status': 'success', 'data': suggestion})
        else:
            return jsonify({'status': 'error', 'message': '약품을 찾을 수 없습니다.'}), 404
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500
