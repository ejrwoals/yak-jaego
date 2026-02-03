"""
routes 패키지

web_app.py의 Blueprint 분할을 위한 패키지입니다.
각 Blueprint는 관련된 API 엔드포인트들을 그룹화합니다.

구조:
- settings.py    : 사용자 설정 API (/api/settings)
- main.py        : 메인 페이지 및 워크플로우 페이지
- reports.py     : 보고서 생성/관리, 체크/메모
- inventory.py   : 재고 관리, 임계값 설정
- drugs.py       : 약품 관리, 플래그, 버퍼 계산
- patients.py    : 환자 관리, 약품-환자 연결
- suggestions.py : 환자-약품 매칭 제안
- data.py        : 데이터 파일 업로드/관리

사용법:
    from routes import register_blueprints
    register_blueprints(app)
"""

from flask import Flask


def register_blueprints(app: Flask):
    """
    모든 Blueprint를 앱에 등록

    Args:
        app: Flask 애플리케이션 인스턴스
    """
    from routes.settings import settings_bp
    from routes.main import main_bp
    from routes.reports import reports_bp
    from routes.inventory import inventory_bp
    from routes.drugs import drugs_bp
    from routes.patients import patients_bp
    from routes.suggestions import suggestions_bp
    from routes.data import data_bp

    app.register_blueprint(settings_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(drugs_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(suggestions_bp)
    app.register_blueprint(data_bp)
