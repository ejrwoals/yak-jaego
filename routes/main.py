"""
routes/main.py
메인 페이지 및 워크플로우 페이지 Blueprint

엔드포인트:
- GET  /                    - 메인 페이지 (랜딩)
- GET  /workflow/simple     - 전문약 재고 관리 워크플로우
- GET  /workflow/order      - 주문 산출 워크플로우
- GET  /workflow/volatility - 고변동성 약품 워크플로우
"""

from flask import Blueprint, render_template, current_app

import inventory_db
import drug_timeseries_db
import user_settings_db


main_bp = Blueprint('main', __name__)


def check_database_ready():
    """두 개의 DB가 모두 준비되었는지 확인"""

    # recent_inventory.sqlite3 체크
    if not inventory_db.db_exists():
        return False, "recent_inventory.sqlite3가 없습니다."

    recent_count = inventory_db.get_inventory_count()
    if recent_count == 0:
        return False, "recent_inventory.sqlite3에 데이터가 없습니다."

    # drug_timeseries.sqlite3 체크
    if not drug_timeseries_db.db_exists():
        return False, "drug_timeseries.sqlite3가 없습니다."

    processed_stats = drug_timeseries_db.get_statistics()
    if processed_stats['total'] == 0:
        return False, "drug_timeseries.sqlite3에 데이터가 없습니다."

    # DB에 저장된 데이터 기간 정보 조회
    data_period = drug_timeseries_db.get_metadata()

    # 신규 약품 수 계산 (시계열 분석 불가능한 약품)
    new_drug_count = recent_count - processed_stats['total']

    return True, {
        'recent_count': recent_count,
        'processed_stats': processed_stats,
        'data_period': data_period,
        'new_drug_count': new_drug_count
    }


@main_bp.route('/')
def index():
    """랜딩 페이지"""
    # DB 상태 확인
    is_ready, result = check_database_ready()

    if not is_ready:
        return render_template('error.html',
                             error_message=result,
                             suggestion="먼저 DB를 초기화해주세요: python init_db.py")

    return render_template('index.html', db_stats=result, dev_mode=current_app.config['DEV_MODE'])


@main_bp.route('/workflow/simple')
def workflow_simple():
    """단순 재고 관리 보고서 워크플로우 페이지"""
    settings = user_settings_db.get_all_settings()
    return render_template('workflow_simple.html', dev_mode=current_app.config['DEV_MODE'], user_settings=settings)


@main_bp.route('/workflow/order')
def workflow_order():
    """주문 수량 산출 워크플로우 페이지"""
    settings = user_settings_db.get_all_settings()
    return render_template('workflow_order.html', user_settings=settings)


@main_bp.route('/workflow/volatility')
def workflow_volatility():
    """고변동성 약품 보고서 워크플로우 페이지"""
    return render_template('workflow_volatility.html')
