#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
suggestion_engine.py
약품 추천 엔진 모듈

등록된 약품들의 Feature Vector를 기반으로
유사한 주기성 패턴의 약품을 추천하는 엔진
"""

import json
import numpy as np
from scipy.spatial.distance import cdist

import drug_periodicity_db
import suggestion_db
import drug_patient_map_db
import patients_db
import drug_timeseries_db
import inventory_db


# 상수
MIN_PATIENTS_FOR_ACTIVATION = 5  # 제안 기능 활성화에 필요한 최소 환자 수
MIN_PEAKS_FOR_SUGGESTION = 3     # 제안 대상 최소 피크 수
DEFAULT_K = 3                    # KNN의 K값
MAX_MONTHLY_USAGE = 200          # 월평균 사용량 임계값 (이 이상이면 추천 제외)
DISCONTINUED_MONTHS_THRESHOLD = 9  # 단종 판정 임계값 (최근 N개월 연속 미사용 시 제외)

# Feature 가중치 (6차원)
# 순서: avg_interval, interval_cv, height_cv, acf_max, peak_count, active_months_ratio
FEATURE_WEIGHTS = np.array([
    2.0,   # avg_interval_norm: 방문 주기 (최우선)
    1.5,   # interval_cv_norm: 규칙성
    1.0,   # height_cv_norm: 사용량 일관성
    0.8,   # acf_max_norm: 자기상관
    0.5,   # peak_count_norm: 피크 밀도
    0.5,   # active_months_ratio: 활동 비율
])


def get_activation_status():
    """
    제안 기능 활성화 상태 확인

    활성화 조건:
    - "약품이 등록된" 환자 5명 이상

    Returns:
        dict: {
            'active': bool,
            'patient_count': int,
            'patients_with_drugs': int,
            'drugs_with_patients': int,
            'required_count': int,
            'required_drugs': int,
            'message': str
        }
    """
    try:
        # 전체 환자 수
        all_patients = patients_db.get_all_patients()
        patient_count = len(all_patients)

        # 약품이 등록된 환자 수
        patients_with_drugs = 0
        for patient in all_patients:
            drugs = drug_patient_map_db.get_drugs_for_patient(patient['환자ID'])
            if drugs:
                patients_with_drugs += 1

        # 환자가 등록된 약품 수
        drugs_with_patients = len(drug_patient_map_db.get_all_drugs_with_patients())

        is_active = patients_with_drugs >= MIN_PATIENTS_FOR_ACTIVATION

        if is_active:
            message = f'제안 기능이 활성화되었습니다. ({patients_with_drugs}명의 환자에게 약품이 등록됨)'
        else:
            remaining = MIN_PATIENTS_FOR_ACTIVATION - patients_with_drugs
            message = f'약품이 등록된 환자가 {remaining}명 더 필요합니다. (현재 {patients_with_drugs}명)'

        return {
            'active': is_active,
            'patient_count': patient_count,
            'patients_with_drugs': patients_with_drugs,
            'drugs_with_patients': drugs_with_patients,
            'required_count': MIN_PATIENTS_FOR_ACTIVATION,
            'required_drugs': DEFAULT_K,
            'message': message
        }

    except Exception as e:
        print(f"활성화 상태 확인 실패: {e}")
        return {
            'active': False,
            'patient_count': 0,
            'patients_with_drugs': 0,
            'drugs_with_patients': 0,
            'required_count': MIN_PATIENTS_FOR_ACTIVATION,
            'required_drugs': DEFAULT_K,
            'message': f'오류: {str(e)}'
        }


def get_registered_drug_codes():
    """
    환자에게 등록된 모든 약품 코드 목록 반환

    Returns:
        list[str]: 약품 코드 목록
    """
    return drug_patient_map_db.get_all_drugs_with_patients()


def weighted_euclidean_knn(candidate_vectors, registered_vectors, k=DEFAULT_K):
    """
    Weighted Euclidean Distance + KNN 기반 유사도 계산

    Args:
        candidate_vectors: (N, 6) 후보 약품 Feature Matrix
        registered_vectors: (M, 6) 등록 약품 Feature Matrix
        k: KNN의 K값 (기본 3)

    Returns:
        numpy.array: (N,) 각 후보의 유사도 점수 (0~1)
    """
    if len(registered_vectors) == 0:
        return np.zeros(len(candidate_vectors))

    # numpy 배열로 변환
    candidate_vectors = np.array(candidate_vectors)
    registered_vectors = np.array(registered_vectors)

    # 가중치 적용 (sqrt를 곱해서 거리 계산에 제곱이 들어가면 원래 가중치가 됨)
    weights = np.sqrt(FEATURE_WEIGHTS)
    weighted_candidates = candidate_vectors * weights
    weighted_registered = registered_vectors * weights

    # 거리 행렬 계산 (N x M)
    distances = cdist(weighted_candidates, weighted_registered, 'euclidean')

    # KNN: 가장 가까운 K개의 평균 거리
    k = min(k, distances.shape[1])
    sorted_distances = np.sort(distances, axis=1)
    knn_distances = np.mean(sorted_distances[:, :k], axis=1)

    # 거리 → 유사도 변환 (0~1)
    similarities = 1 / (1 + knn_distances)

    return similarities


def get_registered_feature_vectors():
    """
    등록된 약품들의 Feature Vector 목록 반환

    Returns:
        list[list[float]]: Feature Vector 목록 (6차원)
    """
    registered_codes = get_registered_drug_codes()

    if not registered_codes:
        return []

    vectors = []
    for code in registered_codes:
        fv = drug_periodicity_db.get_feature_vector(code)
        if fv:
            vectors.append(fv)

    return vectors


def get_nearest_k_drugs(candidate_code, k=DEFAULT_K):
    """
    후보 약품과 가장 가까운 K개의 등록 약품 반환

    Args:
        candidate_code (str): 후보 약품 코드
        k (int): 반환할 약품 수

    Returns:
        list[dict]: 가장 가까운 K개 등록 약품 정보
            [{
                'drug_code': str,
                'drug_name': str,
                'avg_interval': float,
                'distance': float
            }, ...]
    """
    # 후보 약품의 Feature Vector
    candidate_fv = drug_periodicity_db.get_feature_vector(candidate_code)
    if not candidate_fv:
        return []

    # 등록된 약품들의 정보
    registered_codes = get_registered_drug_codes()
    if not registered_codes:
        return []

    # 각 등록 약품과의 거리 계산
    candidate_fv = np.array(candidate_fv)
    weights = np.sqrt(FEATURE_WEIGHTS)
    weighted_candidate = candidate_fv * weights

    distances_info = []
    for code in registered_codes:
        fv = drug_periodicity_db.get_feature_vector(code)
        if fv:
            weighted_fv = np.array(fv) * weights
            distance = np.linalg.norm(weighted_candidate - weighted_fv)

            # 약품 정보 조회
            processed = drug_timeseries_db.get_drug_by_code(code)
            periodicity = drug_periodicity_db.get_periodicity(code)

            drug_name = processed.get('약품명', '') if processed else code
            avg_interval = periodicity['avg_interval'] if periodicity else None

            distances_info.append({
                'drug_code': code,
                'drug_name': drug_name,
                'avg_interval': avg_interval,
                'distance': float(distance)
            })

    # 거리 순으로 정렬하여 K개 반환
    distances_info.sort(key=lambda x: x['distance'])
    return distances_info[:k]


def get_suggestion_candidates():
    """
    제안 후보 약품 목록 생성 (KNN 기반)

    Returns:
        list[dict]: 후보 약품 정보 목록
    """
    # 주기성이 있는 약품 목록 (피크 >= 3)
    periodic_drugs = drug_periodicity_db.get_periodic_drugs(min_score=0, min_peaks=MIN_PEAKS_FOR_SUGGESTION)

    if not periodic_drugs:
        return []

    # 이미 등록된 약품 목록
    registered_codes = set(get_registered_drug_codes())

    # 건너뛰기 기록
    skip_counts = suggestion_db.get_all_skips()

    # 등록된 약품들의 Feature Vector
    registered_vectors = get_registered_feature_vectors()

    # 후보 약품들의 Feature Vector 수집
    # 월평균 사용량이 높은 약품은 제외 (정규분포로 근사 가능한 수준)
    candidate_codes = []
    candidate_vectors = []

    for 약품코드 in periodic_drugs:
        # 약품 정보 조회
        processed = drug_timeseries_db.get_drug_by_code(약품코드)
        if not processed:
            continue

        # 전문약만 추천 대상 (일반약 제외)
        drug_type = processed.get('약품유형', '')
        if drug_type != '전문약':
            continue

        # 월평균 사용량 확인 (임계값 이상이면 제외)
        monthly_avg = processed.get('1년_이동평균', 0) or 0
        if monthly_avg >= MAX_MONTHLY_USAGE:
            continue  # 월평균 사용량이 높으면 추천 대상에서 제외

        # avg_interval == 1인 약품 제외 (매달 사용되는 약품은 개별 환자 등록 불필요)
        periodicity = drug_periodicity_db.get_periodicity(약품코드)
        if periodicity and periodicity['avg_interval'] == 1.0:
            continue

        # 건너뛴 약품 제외 (건너뛴 약품 목록에서 별도 확인 가능)
        if skip_counts.get(약품코드, 0) > 0:
            continue

        # 단종 약품 제외 (최근 N개월 연속 미사용)
        usage_json = processed.get('월별_조제수량_리스트', '[]')
        try:
            usage_list = json.loads(usage_json) if isinstance(usage_json, str) else usage_json
            activity_info = drug_periodicity_db.calculate_active_months_from_list(usage_list)
            if activity_info['trailing_zeros'] >= DISCONTINUED_MONTHS_THRESHOLD:
                continue  # 단종 약품 제외
        except:
            pass

        fv = drug_periodicity_db.get_feature_vector(약품코드)
        if fv:
            candidate_codes.append(약품코드)
            candidate_vectors.append(fv)

    if not candidate_codes:
        return []

    # KNN 기반 유사도 계산
    if registered_vectors:
        similarities = weighted_euclidean_knn(candidate_vectors, registered_vectors)
    else:
        # 등록된 약품이 없으면 주기성 점수로 대체
        similarities = np.zeros(len(candidate_codes))
        for i, code in enumerate(candidate_codes):
            periodicity = drug_periodicity_db.get_periodicity(code)
            if periodicity and periodicity['periodicity_score']:
                similarities[i] = periodicity['periodicity_score'] / 100

    # 결과 구성
    candidates = []
    for i, 약품코드 in enumerate(candidate_codes):
        # 이미 등록된 환자 수
        registered_count = drug_patient_map_db.get_patient_count_for_drug(약품코드)

        # 건너뛰기 횟수
        skip_count = skip_counts.get(약품코드, 0)

        candidates.append({
            '약품코드': 약품코드,
            'similarity': float(similarities[i]),
            'registered_count': registered_count,
            'skip_count': skip_count,
            'is_registered': 약품코드 in registered_codes
        })

    # 정렬: 건너뛰기 안 한 것 → 미등록 → 유사도 높은 순
    # (skip_count, registered_count는 UI 편의성을 위한 정렬)
    candidates.sort(key=lambda x: (
        x['skip_count'],           # 건너뛰기 적은 순 (피로감 방지)
        x['registered_count'],     # 등록 환자 적은 순
        -x['similarity']           # 유사도 높은 순 (KNN 기반)
    ))

    return candidates


def _get_drug_suggestion_detail(약품코드):
    """
    약품의 제안 상세 정보를 조회하는 내부 헬퍼 함수

    Args:
        약품코드 (str): 약품 코드

    Returns:
        dict 또는 None: 약품 상세 정보
    """
    # DB 조회
    periodicity = drug_periodicity_db.get_periodicity(약품코드)
    processed = drug_timeseries_db.get_drug_by_code(약품코드)
    inventory = inventory_db.get_inventory(약품코드)

    if not processed:
        return None

    # 기본 정보
    drug_name = processed.get('약품명', '')
    company = processed.get('제약회사', '')
    drug_type = processed.get('약품유형', '')
    monthly_avg = processed.get('1년_이동평균', 0) or 0

    # 현재 재고
    current_stock = 0
    if inventory:
        current_stock = inventory.get('현재_재고수량', 0) or 0

    # 월별 사용량 파싱
    monthly_usage = []
    usage_json = processed.get('월별_조제수량_리스트', '[]')
    try:
        if isinstance(usage_json, str):
            monthly_usage = json.loads(usage_json)
        else:
            monthly_usage = usage_json
    except:
        monthly_usage = []

    # 평균 피크 높이 계산 (0이 아닌 값들의 평균)
    non_zero_usage = [v for v in monthly_usage if v > 0]
    avg_peak_height = sum(non_zero_usage) / len(non_zero_usage) if non_zero_usage else 0

    # 활동률 계산 (첫 사용 시점부터)
    activity_info = drug_periodicity_db.calculate_active_months_from_list(monthly_usage)

    # 가장 가까운 K개 등록 약품
    nearest_k_drugs = get_nearest_k_drugs(약품코드)

    return {
        'drug_code': 약품코드,
        'drug_name': drug_name,
        'company': company,
        'drug_type': drug_type,
        'avg_interval': periodicity['avg_interval'] if periodicity else None,
        'interval_cv': periodicity['interval_cv'] if periodicity else None,
        'avg_peak_height': round(avg_peak_height, 1),
        'height_cv': periodicity['height_cv'] if periodicity else None,
        'active_months': activity_info['active_months'],
        'total_months': activity_info['total_months'],
        'monthly_avg': round(monthly_avg, 1),
        'current_stock': current_stock,
        'monthly_usage': monthly_usage,
        'nearest_k_drugs': nearest_k_drugs
    }


def get_next_suggestion():
    """
    다음 제안 약품 1개 반환

    Returns:
        dict 또는 None: 제안 정보
    """
    # 활성화 상태 확인
    status = get_activation_status()
    if not status['active']:
        return None

    # 후보 목록
    candidates = get_suggestion_candidates()
    if not candidates:
        return None

    # 첫 번째 후보 선택
    best = candidates[0]
    약품코드 = best['약품코드']

    # 상세 정보 조회
    detail = _get_drug_suggestion_detail(약품코드)
    if not detail:
        return None

    # 후보 정보 추가
    detail['similarity'] = round(best['similarity'] * 100, 1)
    detail['skip_count'] = best['skip_count']
    detail['registered_count'] = best['registered_count']
    detail['remaining_count'] = len(candidates) - 1

    return detail


def register_drug_for_suggestion(약품코드, 환자ID, 처방량=1):
    """
    제안 결과로 약품-환자 등록

    Args:
        약품코드 (str): 약품 코드
        환자ID (int): 환자 ID
        처방량 (int): 1회 처방량 (기본 1)

    Returns:
        dict: {'success': bool, 'message': str}
    """
    try:
        # drug_patient_map에 연결
        result = drug_patient_map_db.link_patient(약품코드, 환자ID, 처방량)

        if result['success']:
            # 건너뛰기 기록 초기화
            suggestion_db.reset_skip(약품코드)

        return result

    except Exception as e:
        print(f"제안 등록 실패: {e}")
        return {'success': False, 'message': str(e)}


def skip_suggestion(약품코드):
    """
    제안 건너뛰기

    Args:
        약품코드 (str): 약품 코드

    Returns:
        dict: {'success': bool, 'message': str, 'skip_count': int}
    """
    return suggestion_db.add_skip(약품코드)


def get_new_drugs_list():
    """
    신규 약품 목록 반환 (피크 < 3으로 분석 어려운 약품)

    Returns:
        list[dict]: 약품 정보 목록
    """
    new_drugs = drug_periodicity_db.get_new_drugs(max_peaks=MIN_PEAKS_FOR_SUGGESTION - 1)

    # 상세 정보 추가
    result = []
    for drug in new_drugs:
        약품코드 = drug['약품코드']

        # processed에서 약품명, 제약회사 조회
        processed = drug_timeseries_db.get_drug_by_code(약품코드)

        if processed:
            result.append({
                'drug_code': 약품코드,
                'drug_name': processed.get('약품명', ''),
                'company': processed.get('제약회사', ''),
                'drug_type': processed.get('약품유형', ''),
                'peak_count': drug['peak_count'],
                'periodicity_score': drug['periodicity_score']
            })

    return result


def get_skipped_drugs_list():
    """
    건너뛴 약품 목록 반환

    Returns:
        list[dict]: 약품 정보 목록
    """
    skip_counts = suggestion_db.get_all_skips()

    if not skip_counts:
        return []

    result = []
    for 약품코드, skip_count in skip_counts.items():
        # processed에서 약품명, 제약회사 조회
        processed = drug_timeseries_db.get_drug_by_code(약품코드)

        if processed:
            result.append({
                'drug_code': 약품코드,
                'drug_name': processed.get('약품명', ''),
                'company': processed.get('제약회사', ''),
                'skip_count': skip_count
            })

    # 건너뛰기 횟수 순으로 정렬 (적은 순)
    result.sort(key=lambda x: x['skip_count'])

    return result


def get_drug_suggestion(약품코드):
    """
    특정 약품의 제안 상세 정보 반환 (get_next_suggestion과 동일 형태)

    Args:
        약품코드 (str): 약품 코드

    Returns:
        dict 또는 None: 제안 정보
    """
    # 상세 정보 조회
    detail = _get_drug_suggestion_detail(약품코드)
    if not detail:
        return None

    # KNN 기반 유사도 계산
    registered_vectors = get_registered_feature_vectors()
    fv = drug_periodicity_db.get_feature_vector(약품코드)
    if registered_vectors and fv:
        similarities = weighted_euclidean_knn([fv], registered_vectors)
        similarity = float(similarities[0])
    else:
        periodicity = drug_periodicity_db.get_periodicity(약품코드)
        similarity = periodicity['periodicity_score'] / 100 if periodicity else 0

    # 추가 정보
    detail['similarity'] = round(similarity * 100, 1)
    detail['skip_count'] = suggestion_db.get_skip_count(약품코드)
    detail['registered_count'] = drug_patient_map_db.get_patient_count_for_drug(약품코드)
    detail['remaining_count'] = 0  # 개별 조회 시에는 의미 없음

    return detail


def get_suggestion_stats():
    """
    제안 관련 통계 반환

    Returns:
        dict: {
            'total_periodic': int,       # 주기적 약품 총 수 (전문약만)
            'already_registered': int,   # 이미 등록된 약품 수
            'pending': int,              # 미등록 약품 수
            'skipped': int,              # 건너뛴 약품 수
            'new_drugs': int             # 신규 약품 수 (피크 부족)
        }
    """
    periodic_drugs = drug_periodicity_db.get_periodic_drugs(min_score=0, min_peaks=MIN_PEAKS_FOR_SUGGESTION)
    registered_codes = set(get_registered_drug_codes())
    skip_counts = suggestion_db.get_all_skips()
    new_drugs = drug_periodicity_db.get_new_drugs(max_peaks=MIN_PEAKS_FOR_SUGGESTION - 1)

    # 전문약만 필터링 (get_suggestion_candidates와 동일한 기준)
    filtered_periodic_drugs = []
    skipped_count = 0
    for 약품코드 in periodic_drugs:
        processed = drug_timeseries_db.get_drug_by_code(약품코드)
        if not processed:
            continue
        # 전문약만
        if processed.get('약품유형', '') != '전문약':
            continue
        # 월평균 사용량 임계값 초과 제외
        monthly_avg = processed.get('1년_이동평균', 0) or 0
        if monthly_avg >= MAX_MONTHLY_USAGE:
            continue
        # avg_interval == 1 제외
        periodicity = drug_periodicity_db.get_periodicity(약품코드)
        if periodicity and periodicity['avg_interval'] == 1.0:
            continue
        # 건너뛴 약품은 분모에서 제외 (gamification 효과)
        if skip_counts.get(약품코드, 0) > 0:
            skipped_count += 1
            continue
        # 단종 약품 제외 (최근 N개월 연속 미사용)
        usage_json = processed.get('월별_조제수량_리스트', '[]')
        try:
            usage_list = json.loads(usage_json) if isinstance(usage_json, str) else usage_json
            activity_info = drug_periodicity_db.calculate_active_months_from_list(usage_list)
            if activity_info['trailing_zeros'] >= DISCONTINUED_MONTHS_THRESHOLD:
                continue  # 단종 약품 제외
        except:
            pass
        filtered_periodic_drugs.append(약품코드)

    already_registered = len([d for d in filtered_periodic_drugs if d in registered_codes])
    pending = len(filtered_periodic_drugs) - already_registered

    return {
        'total_periodic': len(filtered_periodic_drugs),
        'already_registered': already_registered,
        'pending': pending,
        'skipped': skipped_count,
        'new_drugs': len(new_drugs)
    }


if __name__ == '__main__':
    # 테스트 코드
    print("=== suggestion_engine 테스트 ===")

    # 활성화 상태
    status = get_activation_status()
    print(f"\n활성화 상태: {status}")

    # 통계
    stats = get_suggestion_stats()
    print(f"\n제안 통계: {stats}")

    # 다음 제안
    if status['active']:
        suggestion = get_next_suggestion()
        if suggestion:
            print(f"\n다음 제안:")
            print(f"  약품: {suggestion['drug_name']}")
            print(f"  유사도: {suggestion['similarity']}%")
            print(f"  주기성 점수: {suggestion['periodicity_score']}")
        else:
            print("\n제안할 약품이 없습니다.")
    else:
        print(f"\n제안 기능 비활성: {status['message']}")

    # 신규 약품
    new_drugs = get_new_drugs_list()
    print(f"\n신규 약품 수: {len(new_drugs)}")

    print("\n=== 테스트 완료 ===")
