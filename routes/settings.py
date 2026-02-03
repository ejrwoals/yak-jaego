"""
routes/settings.py
사용자 설정 관련 API Blueprint

엔드포인트:
- GET  /api/settings       - 설정 조회
- POST /api/settings       - 설정 저장
- POST /api/settings/reset - 설정 초기화
"""

from flask import Blueprint, request, jsonify

import user_settings_db


settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/api/settings', methods=['GET'])
def get_settings():
    """사용자 설정 조회 API"""
    try:
        settings = user_settings_db.get_all_settings()
        return jsonify({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@settings_bp.route('/api/settings', methods=['POST'])
def save_settings():
    """사용자 설정 저장 API"""
    try:
        data = request.get_json()

        # 유효성 검사
        ma_months = int(data.get('ma_months', 3))
        threshold_low = int(data.get('threshold_low', 1))
        threshold_high = int(data.get('threshold_high', 3))
        runway_threshold = float(data.get('runway_threshold', 1.0))

        # 범위 검사
        if not (1 <= ma_months <= 12):
            return jsonify({'success': False, 'message': '이동평균 개월 수는 1~12 사이여야 합니다.'}), 400
        if not (1 <= threshold_low < threshold_high <= 24):
            return jsonify({'success': False, 'message': '런웨이 경계값 설정이 올바르지 않습니다.'}), 400
        if not (0.5 <= runway_threshold <= 6):
            return jsonify({'success': False, 'message': '강조 표시 기준은 0.5~6 사이여야 합니다.'}), 400

        # 저장
        result = user_settings_db.set_all_settings({
            'ma_months': ma_months,
            'threshold_low': threshold_low,
            'threshold_high': threshold_high,
            'runway_threshold': runway_threshold
        })

        if result['success']:
            return jsonify({'success': True, 'message': '설정이 저장되었습니다.'})
        else:
            return jsonify({'success': False, 'message': result['message']}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@settings_bp.route('/api/settings/reset', methods=['POST'])
def reset_settings():
    """설정을 기본값으로 복원하는 API"""
    try:
        result = user_settings_db.reset_to_defaults()
        if result['success']:
            return jsonify({
                'success': True,
                'settings': result['settings'],
                'message': '기본값으로 복원되었습니다.'
            })
        else:
            return jsonify({'success': False, 'message': result['message']}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
