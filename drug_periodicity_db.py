#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
drug_periodicity_db.py
약품 주기성 지표 관리 SQLite DB 모듈

약품별 주기성(Periodicity) 정보 저장소
- peak_count: 피크 수
- avg_interval: 평균 피크 간격
- interval_cv: 피크 간격 변동계수
- height_cv: 피크 높이 변동계수
- acf_max: 자기상관 최대값 (lag 2~6)
- periodicity_score: 종합 주기성 점수
"""

import os
import sqlite3
import math
import json
from datetime import datetime

import paths
import drug_timeseries_db


DB_PATH = paths.get_db_path('drug_periodicity.sqlite3')
TABLE_NAME = 'drug_periodicity'


def get_connection():
    """데이터베이스 연결 반환"""
    conn = sqlite3.connect(DB_PATH)
    return conn


def init_db():
    """데이터베이스 및 테이블 초기화"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                약품코드 TEXT PRIMARY KEY,
                peak_count INTEGER,
                avg_interval REAL,
                interval_cv REAL,
                height_cv REAL,
                acf_max REAL,
                periodicity_score REAL,
                계산일시 TEXT
            )
        ''')

        # 주기성 점수로 정렬 인덱스
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_periodicity_score ON {TABLE_NAME}(periodicity_score DESC)')

        # 피크 수 인덱스 (제안 대상 필터링용)
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_peak_count ON {TABLE_NAME}(peak_count)')

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"drug_periodicity DB 초기화 실패: {e}")
        return False


def db_exists():
    """DB 파일 존재 여부 확인"""
    return os.path.exists(DB_PATH)


def upsert_periodicity(약품코드, metrics):
    """
    주기성 지표 저장/업데이트

    Args:
        약품코드 (str): 약품 코드
        metrics (dict): {
            'peak_count': int,
            'avg_interval': float,
            'interval_cv': float,
            'height_cv': float,
            'acf_max': float,
            'periodicity_score': float
        }

    Returns:
        dict: {'success': bool, 'message': str}
    """
    if not db_exists():
        init_db()

    try:
        conn = get_connection()
        cursor = conn.cursor()

        약품코드 = str(약품코드)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute(f'''
            INSERT OR REPLACE INTO {TABLE_NAME}
            (약품코드, peak_count, avg_interval, interval_cv, height_cv, acf_max, periodicity_score, 계산일시)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            약품코드,
            metrics.get('peak_count'),
            metrics.get('avg_interval'),
            metrics.get('interval_cv'),
            metrics.get('height_cv'),
            metrics.get('acf_max'),
            metrics.get('periodicity_score'),
            now
        ))

        conn.commit()
        conn.close()

        return {'success': True, 'message': '주기성 지표가 저장되었습니다.'}

    except Exception as e:
        print(f"주기성 지표 저장 실패: {e}")
        return {'success': False, 'message': str(e)}


def get_periodicity(약품코드):
    """
    단일 약품 주기성 지표 조회

    Args:
        약품코드 (str): 약품 코드

    Returns:
        dict 또는 None
    """
    if not db_exists():
        init_db()
        return None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 약품코드, peak_count, avg_interval, interval_cv, height_cv, acf_max, periodicity_score, 계산일시
            FROM {TABLE_NAME}
            WHERE 약품코드 = ?
        ''', (str(약품코드),))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                '약품코드': row[0],
                'peak_count': row[1],
                'avg_interval': row[2],
                'interval_cv': row[3],
                'height_cv': row[4],
                'acf_max': row[5],
                'periodicity_score': row[6],
                '계산일시': row[7]
            }
        return None

    except Exception as e:
        print(f"주기성 지표 조회 실패: {e}")
        return None


def get_all_periodicity():
    """
    전체 약품 주기성 지표 조회

    Returns:
        list[dict]
    """
    if not db_exists():
        init_db()
        return []

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 약품코드, peak_count, avg_interval, interval_cv, height_cv, acf_max, periodicity_score, 계산일시
            FROM {TABLE_NAME}
            ORDER BY periodicity_score DESC
        ''')

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                '약품코드': row[0],
                'peak_count': row[1],
                'avg_interval': row[2],
                'interval_cv': row[3],
                'height_cv': row[4],
                'acf_max': row[5],
                'periodicity_score': row[6],
                '계산일시': row[7]
            }
            for row in rows
        ]

    except Exception as e:
        print(f"전체 주기성 지표 조회 실패: {e}")
        return []


def normalize_feature(value, feature_name):
    """
    Feature 값 정규화 (0~1 범위로)

    Args:
        value: 원본 값
        feature_name: 피처 이름

    Returns:
        float: 정규화된 값 (0~1)
    """
    if value is None:
        return 0.5  # 기본값

    if feature_name == 'interval_cv':
        # 0 ~ 2+ → 0 ~ 1 (낮을수록 좋음, 반전)
        return max(0, 1 - min(1, value))
    elif feature_name == 'height_cv':
        # 0 ~ 2+ → 0 ~ 1 (낮을수록 좋음, 반전)
        return max(0, 1 - min(1, value))
    elif feature_name == 'acf_max':
        # -1 ~ 1 → 0 ~ 1
        return (value + 1) / 2
    elif feature_name == 'periodicity_score':
        # 0 ~ 100+ → 0 ~ 1
        return min(1, value / 50)
    elif feature_name == 'avg_interval':
        # 로그 변환으로 짧은 주기에서 더 세밀한 구분
        # 1개월: 0.0, 2개월: 0.39, 3개월: 0.61, 6개월+: 1.0
        max_interval = 6.0
        if value <= 1:
            return 0.0
        if value >= max_interval:
            return 1.0
        return math.log(value) / math.log(max_interval)
    elif feature_name == 'peak_count':
        # 0 ~ 15+ → 0 ~ 1 (피크 수 정규화)
        return min(1.0, value / 15.0)
    else:
        return value


def calculate_active_months_from_list(usage_list):
    """
    월별 사용량 리스트로부터 활동률 관련 정보를 계산 (첫 사용 시점부터)

    초기에 사용되지 않다가 나중에 사용되기 시작한 약품의 경우,
    첫 사용 시점부터 계산하여 실제 활동률을 더 정확하게 반영합니다.

    Args:
        usage_list (list[int]): 월별 사용량 리스트

    Returns:
        dict: {
            'active_months': int,    # 활성 월 수 (첫 사용 이후)
            'total_months': int,     # 전체 월 수 (첫 사용 이후)
            'ratio': float,          # 활동률 (0~1)
            'trailing_zeros': int    # 마지막 연속 0 개월 수 (단종 판정용)
        }
    """
    if not usage_list:
        return {'active_months': 0, 'total_months': 0, 'ratio': 0.5, 'trailing_zeros': 0}

    # 첫 사용 시점 찾기 (첫 번째 0이 아닌 값의 인덱스)
    first_usage_idx = None
    for i, usage in enumerate(usage_list):
        if usage > 0:
            first_usage_idx = i
            break

    # 마지막부터 연속 0 개수 계산 (단종 판정용)
    trailing_zeros = 0
    for u in reversed(usage_list):
        if u == 0:
            trailing_zeros += 1
        else:
            break

    if first_usage_idx is None:
        return {'active_months': 0, 'total_months': len(usage_list), 'ratio': 0.0, 'trailing_zeros': trailing_zeros}

    # 첫 사용 시점 이후부터 활동률 계산
    usage_from_first = usage_list[first_usage_idx:]
    total_months = len(usage_from_first)
    active_months = sum(1 for u in usage_from_first if u > 0)
    ratio = active_months / total_months if total_months > 0 else 0.5

    return {
        'active_months': active_months,
        'total_months': total_months,
        'ratio': ratio,
        'trailing_zeros': trailing_zeros
    }


def calculate_active_months_ratio(약품코드):
    """
    약품의 활성 월 비율 계산 (첫 사용 시점부터의 0이 아닌 달의 비율)

    Args:
        약품코드 (str): 약품 코드

    Returns:
        float: 활성 월 비율 (0~1)
    """
    try:
        processed = drug_timeseries_db.get_drug_by_code(약품코드)
        if not processed:
            return 0.5  # 기본값

        usage_json = processed.get('월별_조제수량_리스트', '[]')

        # JSON 파싱
        if isinstance(usage_json, str):
            usage_list = json.loads(usage_json)
        else:
            usage_list = usage_json

        return calculate_active_months_from_list(usage_list)['ratio']

    except Exception as e:
        print(f"활성 월 비율 계산 실패: {e}")
        return 0.5


def get_feature_vector(약품코드):
    """
    약품의 정규화된 Feature Vector 반환 (6차원)

    Args:
        약품코드 (str): 약품 코드

    Returns:
        list[float] 또는 None: [
            avg_interval_norm,      # 방문 주기 (로그 변환)
            interval_cv_norm,       # 간격 규칙성
            height_cv_norm,         # 사용량 일관성
            acf_max_norm,           # 자기상관
            peak_count_norm,        # 피크 밀도
            active_months_ratio     # 활동 비율
        ]
    """
    metrics = get_periodicity(약품코드)
    if not metrics:
        return None

    return [
        normalize_feature(metrics['avg_interval'], 'avg_interval'),
        normalize_feature(metrics['interval_cv'], 'interval_cv'),
        normalize_feature(metrics['height_cv'], 'height_cv'),
        normalize_feature(metrics['acf_max'], 'acf_max'),
        normalize_feature(metrics['peak_count'], 'peak_count'),
        calculate_active_months_ratio(약품코드)
    ]


def get_all_feature_vectors():
    """
    전체 약품의 Feature Vector 딕셔너리 반환 (6차원)

    Returns:
        dict: {약품코드: [avg_interval_norm, interval_cv_norm, height_cv_norm,
                         acf_max_norm, peak_count_norm, active_months_ratio], ...}
    """
    all_data = get_all_periodicity()

    result = {}
    for item in all_data:
        약품코드 = item['약품코드']
        result[약품코드] = [
            normalize_feature(item['avg_interval'], 'avg_interval'),
            normalize_feature(item['interval_cv'], 'interval_cv'),
            normalize_feature(item['height_cv'], 'height_cv'),
            normalize_feature(item['acf_max'], 'acf_max'),
            normalize_feature(item['peak_count'], 'peak_count'),
            calculate_active_months_ratio(약품코드)
        ]

    return result


def get_periodic_drugs(min_score=10.0, min_peaks=3):
    """
    주기성이 있는 약품 코드 목록 반환 (제안 대상 필터링용)

    Args:
        min_score (float): 최소 주기성 점수 (기본 10.0)
        min_peaks (int): 최소 피크 수 (기본 3)

    Returns:
        list[str]: 약품 코드 목록
    """
    if not db_exists():
        init_db()
        return []

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 약품코드
            FROM {TABLE_NAME}
            WHERE periodicity_score >= ? AND peak_count >= ?
            ORDER BY periodicity_score DESC
        ''', (min_score, min_peaks))

        drugs = [row[0] for row in cursor.fetchall()]
        conn.close()

        return drugs

    except Exception as e:
        print(f"주기적 약품 목록 조회 실패: {e}")
        return []


def get_new_drugs(max_peaks=2):
    """
    신규 약품 목록 반환 (피크가 적어 분석 어려운 약품)

    Args:
        max_peaks (int): 최대 피크 수 (기본 2)

    Returns:
        list[dict]: 약품 정보 목록
    """
    if not db_exists():
        init_db()
        return []

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT 약품코드, peak_count, periodicity_score
            FROM {TABLE_NAME}
            WHERE peak_count <= ?
            ORDER BY peak_count DESC, 약품코드
        ''', (max_peaks,))

        drugs = [
            {
                '약품코드': row[0],
                'peak_count': row[1],
                'periodicity_score': row[2]
            }
            for row in cursor.fetchall()
        ]
        conn.close()

        return drugs

    except Exception as e:
        print(f"신규 약품 목록 조회 실패: {e}")
        return []


def get_count():
    """전체 약품 수 반환"""
    if not db_exists():
        return 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'SELECT COUNT(*) FROM {TABLE_NAME}')
        count = cursor.fetchone()[0]
        conn.close()

        return count

    except Exception as e:
        print(f"약품 수 조회 실패: {e}")
        return 0


def clear_all():
    """모든 데이터 삭제 (DB 재생성 시 사용)"""
    if not db_exists():
        return {'success': True, 'message': '삭제할 데이터가 없습니다.'}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f'DELETE FROM {TABLE_NAME}')

        count = cursor.rowcount
        conn.commit()
        conn.close()

        return {'success': True, 'message': f'{count}개의 데이터가 삭제되었습니다.', 'count': count}

    except Exception as e:
        print(f"데이터 삭제 실패: {e}")
        return {'success': False, 'message': str(e)}


# 모듈 로드 시 DB 초기화
init_db()


if __name__ == '__main__':
    # 테스트 코드
    print("=== drug_periodicity_db 테스트 ===")

    # DB 초기화 확인
    print(f"DB 존재: {db_exists()}")

    # 테스트 데이터 저장
    test_metrics = {
        'peak_count': 5,
        'avg_interval': 2.8,
        'interval_cv': 0.302,
        'height_cv': 0.0,
        'acf_max': 0.239,
        'periodicity_score': 18.4
    }

    result = upsert_periodicity('TEST001', test_metrics)
    print(f"저장 결과: {result}")

    # 조회
    periodicity = get_periodicity('TEST001')
    print(f"조회 결과: {periodicity}")

    # Feature Vector
    fv = get_feature_vector('TEST001')
    print(f"Feature Vector: {fv}")

    # 전체 조회
    all_data = get_all_periodicity()
    print(f"전체 데이터 수: {len(all_data)}")

    # 주기적 약품
    periodic_drugs = get_periodic_drugs(min_score=10.0, min_peaks=3)
    print(f"주기적 약품 수: {len(periodic_drugs)}")

    # 삭제
    result = clear_all()
    print(f"삭제 결과: {result}")

    print("=== 테스트 완료 ===")
