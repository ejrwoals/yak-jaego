"""
routes/inventory.py
재고 관리 및 임계값 설정 API Blueprint

엔드포인트:
- GET  /api/search-inventory          - 약품 검색
- GET  /api/get-inventory/<code>      - 단일 약품 정보 조회
- POST /api/update-inventory          - 재고 수정
- GET  /api/drug-threshold/<code>     - 임계값 조회
- POST /api/drug-threshold/<code>     - 임계값 설정/수정
- DELETE /api/drug-threshold/<code>   - 임계값 삭제
- GET  /api/drug-thresholds           - 전체 임계값 목록
- GET  /api/drug-thresholds/stats     - 임계값 통계
"""

import math
import traceback

from flask import Blueprint, request, jsonify

import inventory_db
import drug_thresholds_db


inventory_bp = Blueprint('inventory', __name__)


@inventory_bp.route('/api/search-inventory', methods=['GET'])
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
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@inventory_bp.route('/api/get-inventory/<drug_code>', methods=['GET'])
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
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@inventory_bp.route('/api/update-inventory', methods=['POST'])
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
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ============================================================
# 개별 임계값 관리 API
# ============================================================

@inventory_bp.route('/api/drug-threshold/<drug_code>', methods=['GET'])
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


@inventory_bp.route('/api/drug-threshold/<drug_code>', methods=['POST'])
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
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@inventory_bp.route('/api/drug-threshold/<drug_code>', methods=['DELETE'])
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


@inventory_bp.route('/api/drug-thresholds', methods=['GET'])
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


@inventory_bp.route('/api/drug-thresholds/stats', methods=['GET'])
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
