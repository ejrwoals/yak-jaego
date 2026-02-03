"""
routes 패키지

web_app.py의 Blueprint 분할을 위한 패키지입니다.
각 Blueprint는 관련된 API 엔드포인트들을 그룹화합니다.

구조:
- settings.py: 사용자 설정 API (/api/settings)
- (추후 추가 예정) reports.py, inventory.py, drugs.py, patients.py 등

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

    app.register_blueprint(settings_bp)

    # 추후 Blueprint 추가 시 여기에 등록
    # from routes.reports import reports_bp
    # app.register_blueprint(reports_bp)
