#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
periodicity_calculator.py
약품 주기성 지표 계산 모듈

월별 사용량 데이터를 분석하여 주기성 지표를 계산하고 DB에 저장
- interval_cv: 피크 간격 변동계수
- height_cv: 피크 높이 변동계수
- acf_max: 자기상관 최대값 (lag 2~6)
- periodicity_score: 종합 주기성 점수
"""

import json
import numpy as np

import drug_periodicity_db
import drug_timeseries_db


def autocorr(x, lag):
    """
    자기상관 계산

    Args:
        x: 시계열 데이터 (list 또는 array)
        lag: 지연 값

    Returns:
        float: 자기상관 값 (-1 ~ 1)
    """
    n = len(x)
    if lag >= n:
        return 0

    x = np.array(x, dtype=float)
    mean = np.mean(x)
    var = np.var(x)

    if var == 0:
        return 0

    x_centered = x - mean
    return np.sum(x_centered[:n-lag] * x_centered[lag:]) / (n * var)


def find_peaks(usage_list, threshold=0):
    """
    피크 탐지 (사용량 > threshold인 달)

    Args:
        usage_list: 월별 사용량 리스트
        threshold: 피크 판정 기준값 (기본 0)

    Returns:
        list[tuple]: [(index, value), ...]
    """
    return [(i, v) for i, v in enumerate(usage_list) if v > threshold]


def calculate_interval_cv(peaks):
    """
    피크 간격의 변동계수 계산

    Args:
        peaks: 피크 리스트 [(index, value), ...]

    Returns:
        float 또는 None: 변동계수 (낮을수록 규칙적)
    """
    if len(peaks) < 2:
        return None

    indices = [p[0] for p in peaks]
    intervals = [indices[i+1] - indices[i] for i in range(len(indices)-1)]

    if len(intervals) == 0:
        return None

    mean_interval = np.mean(intervals)
    if mean_interval == 0:
        return None

    return float(np.std(intervals) / mean_interval)


def calculate_height_cv(peaks):
    """
    피크 높이의 변동계수 계산

    Args:
        peaks: 피크 리스트 [(index, value), ...]

    Returns:
        float 또는 None: 변동계수 (낮을수록 같은 환자일 가능성)
    """
    if len(peaks) < 2:
        return None

    values = [p[1] for p in peaks]
    mean_val = np.mean(values)

    if mean_val == 0:
        return None

    std_val = np.std(values)
    if std_val == 0:
        return 0.0  # 모든 값이 동일하면 CV = 0

    return float(std_val / mean_val)


def calculate_acf_max(usage_list, min_lag=2, max_lag=6):
    """
    자기상관 최대값 계산 (lag 2~6 범위)

    Args:
        usage_list: 월별 사용량 리스트
        min_lag: 최소 지연 값 (기본 2)
        max_lag: 최대 지연 값 (기본 6)

    Returns:
        float: ACF 최대값 (-1 ~ 1)
    """
    acf_values = []
    for lag in range(min_lag, max_lag + 1):
        acf_values.append(autocorr(usage_list, lag))

    return float(max(acf_values)) if acf_values else 0.0


def calculate_avg_interval(peaks):
    """
    평균 피크 간격 계산

    Args:
        peaks: 피크 리스트 [(index, value), ...]

    Returns:
        float 또는 None: 평균 간격 (개월)
    """
    if len(peaks) < 2:
        return None

    indices = [p[0] for p in peaks]
    intervals = [indices[i+1] - indices[i] for i in range(len(indices)-1)]

    if len(intervals) == 0:
        return None

    return float(np.mean(intervals))


def calculate_periodicity_metrics(usage_list):
    """
    단일 약품의 모든 주기성 지표 계산

    Args:
        usage_list: 월별 사용량 리스트

    Returns:
        dict: {
            'peak_count': int,
            'avg_interval': float | None,
            'interval_cv': float | None,
            'height_cv': float | None,
            'acf_max': float | None,
            'periodicity_score': float | None
        }
    """
    peaks = find_peaks(usage_list)

    if len(peaks) < 3:
        # 피크가 3개 미만이면 분석 불가
        return {
            'peak_count': len(peaks),
            'avg_interval': None,
            'interval_cv': None,
            'height_cv': None,
            'acf_max': None,
            'periodicity_score': None
        }

    interval_cv = calculate_interval_cv(peaks)
    height_cv = calculate_height_cv(peaks)
    acf_max = calculate_acf_max(usage_list)
    avg_interval = calculate_avg_interval(peaks)

    # 종합 주기성 점수 계산
    # 높을수록 주기적 패턴
    if interval_cv is not None and height_cv is not None and acf_max is not None:
        # ACF가 음수일 수 있으므로 0과 max 취함
        acf_factor = max(0, acf_max)
        # CV가 낮을수록 좋으므로 역수 형태로
        interval_factor = 1 / (1 + interval_cv)
        height_factor = 1 / (1 + height_cv)
        periodicity_score = float(100 * acf_factor * interval_factor * height_factor)
    else:
        periodicity_score = None

    return {
        'peak_count': len(peaks),
        'avg_interval': avg_interval,
        'interval_cv': interval_cv,
        'height_cv': height_cv,
        'acf_max': acf_max,
        'periodicity_score': periodicity_score
    }


def calculate_all_periodicity(show_progress=True):
    """
    전체 약품의 주기성 지표 계산 및 DB 저장

    Args:
        show_progress: 진행 상황 출력 여부 (기본 True)

    Returns:
        dict: {'total': int, 'calculated': int, 'skipped': int}
    """
    # drug_timeseries에서 전체 약품 로드 (DataFrame 반환)
    df = drug_timeseries_db.get_processed_data()

    if df.empty:
        print("   ⚠️  drug_timeseries에 데이터가 없습니다.")
        return {'total': 0, 'calculated': 0, 'skipped': 0}

    total = len(df)
    calculated = 0
    skipped = 0

    if show_progress:
        print(f"   총 {total}개 약품 분석 중...")

    for i, (_, row) in enumerate(df.iterrows()):
        약품코드 = row['약품코드']

        # 월별 사용량 데이터 (get_processed_data에서 이미 리스트로 변환됨)
        usage_list = row.get('월별_조제수량_리스트', [])
        if usage_list is None:
            usage_list = []

        if not usage_list:
            skipped += 1
            continue

        # 주기성 지표 계산
        metrics = calculate_periodicity_metrics(usage_list)

        # DB에 저장
        result = drug_periodicity_db.upsert_periodicity(약품코드, metrics)
        if result['success']:
            calculated += 1
        else:
            skipped += 1

        # 진행 상황 출력 (100개마다)
        if show_progress and (i + 1) % 100 == 0:
            print(f"   {i + 1}/{total} 완료...")

    if show_progress:
        print(f"   계산 완료: {calculated}/{total}개, 건너뜀: {skipped}개")

    return {
        'total': total,
        'calculated': calculated,
        'skipped': skipped
    }


def recalculate_for_drug(약품코드):
    """
    특정 약품만 재계산

    Args:
        약품코드 (str): 약품 코드

    Returns:
        dict 또는 None: 계산된 metrics
    """
    # drug_timeseries에서 약품 데이터 조회
    drug_data = drug_timeseries_db.get_drug_by_code(약품코드)

    if not drug_data:
        print(f"   ⚠️  {약품코드} 데이터를 찾을 수 없습니다.")
        return None

    # 월별 사용량 데이터 파싱
    usage_json = drug_data.get('월별_조제수량_리스트', '[]')
    try:
        if isinstance(usage_json, str):
            usage_list = json.loads(usage_json)
        else:
            usage_list = usage_json
    except (json.JSONDecodeError, TypeError):
        usage_list = []

    if not usage_list:
        return None

    # 주기성 지표 계산
    metrics = calculate_periodicity_metrics(usage_list)

    # DB에 저장
    drug_periodicity_db.upsert_periodicity(약품코드, metrics)

    return metrics


if __name__ == '__main__':
    # 테스트 코드
    print("=== periodicity_calculator 테스트 ===")

    # 샘플 데이터로 테스트
    # 크레젯정 패턴 (주기적)
    periodic_data = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 90, 0, 90, 0, 0, 90, 0, 0, 0, 90, 0, 90, 0, 0, 0]
    metrics = calculate_periodicity_metrics(periodic_data)
    print(f"\n주기적 패턴:")
    print(f"  피크 수: {metrics['peak_count']}")
    print(f"  평균 간격: {metrics['avg_interval']}")
    print(f"  간격 CV: {metrics['interval_cv']}")
    print(f"  높이 CV: {metrics['height_cv']}")
    print(f"  ACF 최대: {metrics['acf_max']}")
    print(f"  주기성 점수: {metrics['periodicity_score']}")

    # 싸이러스정 패턴 (불규칙)
    irregular_data = [90, 0, 0, 60, 0, 0, 108, 72, 0, 0, 0, 60, 0, 0, 14, 0, 60, 68, 0, 0, 0, 0, 14, 11, 14, 0]
    metrics = calculate_periodicity_metrics(irregular_data)
    print(f"\n불규칙 패턴:")
    print(f"  피크 수: {metrics['peak_count']}")
    print(f"  평균 간격: {metrics['avg_interval']}")
    print(f"  간격 CV: {metrics['interval_cv']}")
    print(f"  높이 CV: {metrics['height_cv']}")
    print(f"  ACF 최대: {metrics['acf_max']}")
    print(f"  주기성 점수: {metrics['periodicity_score']}")

    print("\n=== 테스트 완료 ===")
