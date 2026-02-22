#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Jaego - 약국 재고 관리 및 분석 시스템 (웹 버전)
Flask 기반 웹 애플리케이션

사용법: python web_app.py

아키텍처:
- web_app.py: 앱 설정, 시스템 라우트 (heartbeat, shutdown, rebuild-db)
- routes/: 비즈니스 로직 라우트 (Blueprint 패턴)
  - main.py: 메인 페이지, 워크플로우 페이지
  - reports.py: 보고서 생성/관리, 체크/메모
  - inventory.py: 재고 관리, 임계값 설정
  - drugs.py: 약품 관리, 플래그, 버퍼 계산
  - patients.py: 환자 관리, 약품-환자 연결
  - suggestions.py: 환자-약품 매칭 제안
  - data.py: 데이터 파일 업로드/관리
  - settings.py: 사용자 설정 API
"""

import os
import time
import threading
import traceback
import webbrowser
from datetime import datetime
from threading import Timer

from flask import Flask, request, jsonify

# 경로 관리 모듈 (PyInstaller 빌드 지원)
import paths


# =============================================================================
# Flask 앱 설정
# =============================================================================

app = Flask(__name__,
            template_folder=paths.get_bundle_path('templates'),
            static_folder=paths.get_bundle_path('static'))

# Blueprint 등록
from routes import register_blueprints
register_blueprints(app)

app.config['JSON_AS_ASCII'] = False  # 한글 JSON 출력 지원
app.config['UPLOAD_FOLDER'] = paths.UPLOADS_PATH  # 임시 업로드 폴더
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB 제한
app.config['VERSION'] = os.getenv('APP_VERSION', str(int(datetime.now().timestamp())))  # 캐시 버스팅용 버전
app.config['DEV_MODE'] = not paths.is_frozen()  # 개발 모드 플래그 (PyInstaller 빌드가 아닌 경우)


# =============================================================================
# 브라우저 연결 감지 및 자동 종료 (PyInstaller 빌드용)
# =============================================================================

# 마지막 heartbeat 시간 (전역 변수)
_last_heartbeat = time.time()
_heartbeat_lock = threading.Lock()
_shutdown_requested = False
_long_operation_in_progress = False  # 오래 걸리는 작업 진행 중 (auto-shutdown 방지)

# Heartbeat 설정
HEARTBEAT_INTERVAL = 10  # 클라이언트가 10초마다 heartbeat 전송
HEARTBEAT_TIMEOUT = 120  # 120초(2분) 동안 heartbeat 없으면 서버 종료


# =============================================================================
# 시스템 API 라우트
# =============================================================================

@app.route('/api/rebuild-db', methods=['POST'])
def rebuild_db():
    """DB 재생성 API (db_initializer 모듈 사용)"""
    global _long_operation_in_progress
    try:
        _long_operation_in_progress = True  # auto-shutdown 방지
        print("\n🔄 DB 재생성 요청 받음...")

        from db_initializer import rebuild_database

        # db_initializer의 공통 로직 사용
        result = rebuild_database(
            delete_existing=True,
            include_periodicity=True,
            show_summary=False
        )

        if not result['success']:
            return jsonify({'error': result.get('error', 'DB 재생성 실패')}), 500

        stats = result['stats']
        new_drug_count = stats['recent_count'] - stats['processed_stats']['total']

        return jsonify({
            'success': True,
            'message': 'DB 재생성이 완료되었습니다.',
            'stats': {
                'recent_count': stats['recent_count'],
                'processed_stats': stats['processed_stats'],
                'data_period': stats['data_period'],
                'new_drug_count': new_drug_count
            }
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'DB 재생성 실패: {str(e)}'}), 500
    finally:
        _long_operation_in_progress = False  # auto-shutdown 재활성화


@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    """브라우저 연결 상태 확인용 heartbeat"""
    global _last_heartbeat
    with _heartbeat_lock:
        _last_heartbeat = time.time()
    return jsonify({'status': 'ok'})


@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    """Flask 앱 종료 API"""
    global _shutdown_requested
    try:
        print("\n🛑 웹 애플리케이션 종료 요청 받음...")
        _shutdown_requested = True

        # Flask 종료 함수 호출
        shutdown_server = request.environ.get('werkzeug.server.shutdown')
        if shutdown_server is None:
            # Werkzeug 버전에 따라 다른 방법 사용
            import signal
            print("✅ 서버를 종료합니다...")
            os.kill(os.getpid(), signal.SIGINT)
        else:
            shutdown_server()

        return jsonify({'success': True, 'message': '서버가 종료됩니다...'})
    except Exception as e:
        print(f"⚠️  종료 중 오류 발생: {e}")
        return jsonify({'error': str(e)}), 500


# =============================================================================
# 자동 종료 감지 스레드
# =============================================================================

def check_heartbeat_timeout():
    """브라우저 종료 감지 (주기적 heartbeat 기반)"""
    global _shutdown_requested
    while not _shutdown_requested:
        time.sleep(1)  # 1초마다 체크

        with _heartbeat_lock:
            elapsed = time.time() - _last_heartbeat
            is_long_op = _long_operation_in_progress

        # 오래 걸리는 작업 중에는 auto-shutdown 방지
        if is_long_op:
            continue

        # heartbeat 없이 HEARTBEAT_TIMEOUT(2분) 경과 시 종료
        if elapsed > HEARTBEAT_TIMEOUT:
            print(f"\n🚪 브라우저 종료 감지 ({HEARTBEAT_TIMEOUT}초 동안 heartbeat 없음)")
            print("🛑 서버를 자동 종료합니다...")
            _shutdown_requested = True
            import signal
            os.kill(os.getpid(), signal.SIGINT)
            break


def open_browser():
    """브라우저 자동 열기"""
    webbrowser.open('http://127.0.0.1:5000/')


# =============================================================================
# 메인 엔트리포인트
# =============================================================================

if __name__ == '__main__':
    # 브라우저 자동 열기 (1초 후)
    Timer(1, open_browser).start()

    # 브라우저 종료 감지 (주기적 heartbeat 기반)
    heartbeat_thread = threading.Thread(target=check_heartbeat_timeout, daemon=True)
    heartbeat_thread.start()

    # Flask 앱 실행
    print("\n" + "=" * 60)
    print("🏥 Jaego - 약국 재고 관리 시스템 (웹 버전)")
    print("=" * 60)
    print("\n📱 웹 브라우저가 자동으로 열립니다...")
    print("   URL: http://127.0.0.1:5000/")
    print("\n⚠️  브라우저를 닫으면 자동으로 종료됩니다.")
    print("=" * 60 + "\n")

    app.run(debug=False if paths.is_frozen() else True, use_reloader=False)
