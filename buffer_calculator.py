#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
buffer_calculator.py
포아송 이항분포 기반 최소 재고 버퍼 계산 모듈

N명의 환자가 각각 p_i = 1/방문주기_일 확률로 특정 일에 방문할 때,
동시에 k명 이상이 방문할 확률을 계산하고 허용 리스크 수준에 따라
필요한 최소 재고 버퍼를 산출합니다.
"""


# 허용 리스크 수준 정의
# threshold: P(X>=k) <= threshold 가 되는 첫 번째 k를 찾아 버퍼 계산
RISK_LEVELS = {
    'relaxed': {
        'name': '절약',
        'description': '흔한 동시 방문만 대비',
        'threshold': 0.03  # 3%
    },
    'normal': {
        'name': '보통',
        'description': '일반적인 동시 방문 대비',
        'threshold': 0.003  # 0.3%
    },
    'safe': {
        'name': '안전',
        'description': '드문 동시 방문까지 대비',
        'threshold': 0.0003  # 0.03%
    },
    'very_safe': {
        'name': '매우 안전',
        'description': '매우 드문 동시 방문까지 대비',
        'threshold': 0.00003  # 0.003%
    }
}


def calculate_visit_probabilities(patients_data):
    """
    각 환자의 일일 방문 확률 계산

    Args:
        patients_data: [{'환자ID': int, '방문주기_일': int, '1회_처방량': int}, ...]

    Returns:
        list: [(p_i, dosage_i), ...] 확률과 처방량 튜플 리스트
    """
    probabilities = []
    for patient in patients_data:
        visit_cycle = patient.get('방문주기_일') or 30  # 기본값 30일
        if visit_cycle > 0:
            p = 1.0 / visit_cycle
        else:
            p = 1.0 / 30  # 기본값
        dosage = patient.get('1회_처방량') or 1
        probabilities.append((p, dosage))
    return probabilities


def calculate_poisson_binomial_pmf(probs, k):
    """
    포아송 이항분포의 PMF 계산 (정확히 k명이 방문할 확률)

    동적 프로그래밍 방식으로 효율적으로 계산
    """
    n = len(probs)
    if k > n or k < 0:
        return 0.0

    # DP 테이블: dp[j] = 현재까지 정확히 j명 방문 확률
    dp = [0.0] * (n + 1)
    dp[0] = 1.0

    for p in probs:
        # 역순으로 업데이트하여 이전 값 보존
        for j in range(n, 0, -1):
            dp[j] = dp[j] * (1 - p) + dp[j - 1] * p
        dp[0] = dp[0] * (1 - p)

    return dp[k]


def calculate_tail_probability(probs, k):
    """
    k명 이상 동시 방문 확률 계산 (tail probability)
    P(X >= k) = 1 - P(X < k) = 1 - sum(P(X = i) for i in 0..k-1)
    """
    if k <= 0:
        return 1.0

    n = len(probs)
    if k > n:
        return 0.0

    # 전체 PMF 계산
    dp = [0.0] * (n + 1)
    dp[0] = 1.0

    for p in probs:
        for j in range(n, 0, -1):
            dp[j] = dp[j] * (1 - p) + dp[j - 1] * p
        dp[0] = dp[0] * (1 - p)

    # k명 미만 방문 확률 합
    cumulative = sum(dp[:k])
    return 1.0 - cumulative


def calculate_min_buffer(patients_data, risk_level='safe'):
    """
    최소 재고 버퍼 계산

    Args:
        patients_data: [{'환자ID': int, '환자명': str, '방문주기_일': int, '1회_처방량': int}, ...]
        risk_level: 'normal' | 'safe' | 'very_safe'

    Returns:
        dict: {
            'min_buffer': int,  # 최소 필요 버퍼
            'max_k': int,  # 동시 방문 대비 환자 수
            'risk_threshold': float,  # 허용 리스크 수준
            'actual_risk': float,  # 실제 리스크 (부족 확률)
            'patient_details': [...],  # 버퍼에 포함된 환자별 정보
            'explanation': str  # 결과 설명
        }
    """
    if not patients_data:
        return {
            'min_buffer': 0,
            'max_k': 0,
            'risk_threshold': 0,
            'actual_risk': 0,
            'patient_details': [],
            'all_patients': [],
            'explanation': '연결된 환자가 없습니다.',
            'risk_level_name': '',
            'risk_level_description': ''
        }

    risk_config = RISK_LEVELS.get(risk_level, RISK_LEVELS['safe'])
    threshold = risk_config['threshold']

    # 확률과 처방량 추출
    prob_dosage_pairs = calculate_visit_probabilities(patients_data)
    probs = [p for p, _ in prob_dosage_pairs]

    n = len(probs)

    # k명 이상 동시 방문 확률이 threshold 이하가 되는 최소 k 찾기
    # 즉, P(X >= k) <= threshold 인 최소 k
    # k=0부터 시작하여 P(X >= k) <= threshold 인 k를 찾음
    min_k = 0
    for k in range(n + 1):
        tail_prob = calculate_tail_probability(probs, k)
        if tail_prob <= threshold:
            min_k = k
            break
    else:
        # 모든 k에 대해 threshold를 초과하면 전체 환자 수
        min_k = n

    # 실제 리스크 계산 (min_k명 이상 동시 방문 확률)
    actual_risk = calculate_tail_probability(probs, min_k)

    # 상위 min_k개 처방량 합산 (처방량이 큰 순서로)
    # 처방량과 환자 정보를 함께 정렬
    sorted_patients = sorted(
        zip(patients_data, prob_dosage_pairs),
        key=lambda x: x[1][1],  # 처방량 기준 정렬
        reverse=True
    )

    buffer = 0
    included_patients = []
    for i, (patient, (p, dosage)) in enumerate(sorted_patients):
        if i < min_k:
            buffer += dosage
            included_patients.append({
                '환자명': patient.get('환자명', ''),
                '방문주기_일': patient.get('방문주기_일') or 30,
                '1회_처방량': dosage,
                '방문확률': round(p * 100, 2)  # 퍼센트로 표시
            })

    # 전체 환자 목록 (버퍼 계산에 포함 안 된 환자 포함)
    all_patients = []
    for i, (patient, (p, dosage)) in enumerate(sorted_patients):
        all_patients.append({
            '환자명': patient.get('환자명', ''),
            '방문주기_일': patient.get('방문주기_일') or 30,
            '1회_처방량': dosage,
            '방문확률': round(p * 100, 2),
            '버퍼포함': i < min_k
        })

    # 설명 생성
    # 실제 리스크를 보기 좋은 형식으로 변환
    if actual_risk >= 0.01:  # >= 1%
        risk_str = f"{actual_risk * 100:.1f}%"
    elif actual_risk >= 0.001:  # >= 0.1%
        risk_str = f"{actual_risk * 100:.2f}%"
    elif actual_risk >= 0.00001:  # >= 0.001%
        risk_str = f"{actual_risk * 100:.4f}%"
    elif actual_risk > 0:
        risk_str = "<0.001%"
    else:
        risk_str = "0%"

    # threshold를 보기 좋은 형식으로 변환
    if threshold >= 0.01:
        threshold_str = f"{threshold * 100:.1f}%"
    elif threshold >= 0.001:
        threshold_str = f"{threshold * 100:.2f}%"
    else:
        threshold_str = f"{threshold * 100:.3f}%"

    if min_k == 0:
        explanation = f"{n}명의 환자가 연결되어 있지만, 추가 버퍼가 필요하지 않습니다."
    elif min_k == 1:
        explanation = f"{n}명의 환자 중 1명이 방문할 가능성({risk_str})에 대비하여 최대 처방량 {buffer}개의 버퍼가 필요합니다."
    else:
        dosage_sum_str = ' + '.join([str(p['1회_처방량']) for p in included_patients])
        explanation = f"{n}명의 환자 중 {min_k}명이 같은 날 방문할 가능성({risk_str})에 대비하여 상위 {min_k}명의 처방량 합({dosage_sum_str} = {buffer}개)이 버퍼로 필요합니다."

    return {
        'min_buffer': buffer,
        'max_k': min_k,
        'risk_threshold': threshold,
        'actual_risk': actual_risk,
        'patient_details': included_patients,
        'all_patients': all_patients,
        'explanation': explanation,
        'risk_level_name': risk_config['name'],
        'risk_level_description': risk_config['description'],
        'total_patients': n
    }


def get_risk_levels():
    """
    사용 가능한 리스크 수준 목록 반환
    """
    return {
        key: {
            'name': val['name'],
            'description': val['description'],
            'threshold_percent': round(val['threshold'] * 100, 4)
        }
        for key, val in RISK_LEVELS.items()
    }


if __name__ == '__main__':
    # 테스트 코드
    print("=== buffer_calculator 테스트 ===\n")

    # 테스트 데이터: 4명의 환자
    test_patients = [
        {'환자ID': 1, '환자명': '홍길동', '방문주기_일': 30, '1회_처방량': 30},
        {'환자ID': 2, '환자명': '김철수', '방문주기_일': 30, '1회_처방량': 30},
        {'환자ID': 3, '환자명': '이영희', '방문주기_일': 60, '1회_처방량': 60},
        {'환자ID': 4, '환자명': '박민수', '방문주기_일': 90, '1회_처방량': 90},
    ]

    print("테스트 환자 데이터:")
    for p in test_patients:
        print(f"  - {p['환자명']}: {p['방문주기_일']}일 주기, {p['1회_처방량']}개/회")
    print()

    # 각 리스크 수준별 계산
    for risk_level in ['normal', 'safe', 'very_safe']:
        result = calculate_min_buffer(test_patients, risk_level)
        print(f"[{result['risk_level_name']}] ({result['risk_level_description']})")
        print(f"  최소 버퍼: {result['min_buffer']}개")
        print(f"  대비 환자 수: {result['max_k']}명")
        print(f"  실제 리스크: {result['actual_risk'] * 100:.4f}%")
        print(f"  설명: {result['explanation']}")
        if result['patient_details']:
            print(f"  포함 환자:")
            for p in result['patient_details']:
                print(f"    - {p['환자명']}: {p['1회_처방량']}개")
        print()

    print("=== 테스트 완료 ===")
