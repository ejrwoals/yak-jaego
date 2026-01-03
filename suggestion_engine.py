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
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity

import drug_periodicity_db
import suggestion_db
import drug_patient_map_db
import patients_db
import processed_inventory_db
import inventory_db


# 상수
MIN_PATIENTS_FOR_ACTIVATION = 5  # 제안 기능 활성화에 필요한 최소 환자 수
MIN_PEAKS_FOR_SUGGESTION = 3     # 제안 대상 최소 피크 수
SKIP_PENALTY = 0.5               # 건너뛰기당 페널티
REGISTERED_PENALTY = 0.3         # 이미 등록된 약품당 페널티


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
            'required_count': int,
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
            'required_count': MIN_PATIENTS_FOR_ACTIVATION,
            'message': message
        }

    except Exception as e:
        print(f"활성화 상태 확인 실패: {e}")
        return {
            'active': False,
            'patient_count': 0,
            'patients_with_drugs': 0,
            'required_count': MIN_PATIENTS_FOR_ACTIVATION,
            'message': f'오류: {str(e)}'
        }


def get_registered_drug_codes():
    """
    환자에게 등록된 모든 약품 코드 목록 반환

    Returns:
        list[str]: 약품 코드 목록
    """
    return drug_patient_map_db.get_all_drugs_with_patients()


def calculate_centroid():
    """
    등록된 약품들의 평균 Feature Vector (centroid) 계산

    Returns:
        numpy.array 또는 None: [4] 크기의 평균 벡터
    """
    registered_codes = get_registered_drug_codes()

    if not registered_codes:
        return None

    vectors = []
    for code in registered_codes:
        fv = drug_periodicity_db.get_feature_vector(code)
        if fv:
            vectors.append(fv)

    if not vectors:
        return None

    # 평균 계산
    return np.mean(vectors, axis=0)


def cosine_sim(vec_a, vec_b):
    """
    코사인 유사도 계산

    Args:
        vec_a: 벡터 A
        vec_b: 벡터 B

    Returns:
        float: 유사도 (0 ~ 1)
    """
    if vec_a is None or vec_b is None:
        return 0.0

    vec_a = np.array(vec_a).reshape(1, -1)
    vec_b = np.array(vec_b).reshape(1, -1)

    return float(sklearn_cosine_similarity(vec_a, vec_b)[0][0])


def get_suggestion_candidates():
    """
    제안 후보 약품 목록 생성

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

    # centroid 계산
    centroid = calculate_centroid()

    candidates = []

    for 약품코드 in periodic_drugs:
        # Feature Vector 조회
        fv = drug_periodicity_db.get_feature_vector(약품코드)
        if not fv:
            continue

        # 유사도 계산
        if centroid is not None:
            similarity = cosine_sim(centroid, fv)
        else:
            # centroid가 없으면 주기성 점수로 대체
            periodicity = drug_periodicity_db.get_periodicity(약품코드)
            similarity = periodicity['periodicity_score'] / 100 if periodicity else 0

        # 이미 등록된 환자 수
        registered_count = drug_patient_map_db.get_patient_count_for_drug(약품코드)

        # 건너뛰기 횟수
        skip_count = skip_counts.get(약품코드, 0)

        # 페널티 적용
        registered_penalty = min(registered_count, 3) * REGISTERED_PENALTY / 3  # 최대 0.3
        skip_penalty = min(skip_count, 3) * SKIP_PENALTY / 3  # 최대 0.5

        adjusted_similarity = max(0, similarity - registered_penalty - skip_penalty)

        candidates.append({
            '약품코드': 약품코드,
            'similarity': similarity,
            'adjusted_similarity': adjusted_similarity,
            'registered_count': registered_count,
            'skip_count': skip_count,
            'is_registered': 약품코드 in registered_codes
        })

    # 정렬: 건너뛰기 안 한 것 → 미등록 → 유사도 높은 순
    candidates.sort(key=lambda x: (
        x['skip_count'],           # 건너뛰기 적은 순
        x['registered_count'],     # 등록 환자 적은 순
        -x['adjusted_similarity']  # 유사도 높은 순
    ))

    return candidates


def get_next_suggestion():
    """
    다음 제안 약품 1개 반환

    Returns:
        dict 또는 None: {
            'drug_code': str,
            'drug_name': str,
            'company': str,
            'drug_type': str,
            'similarity': float,
            'periodicity_score': float,
            'avg_interval': float,
            'current_stock': int,
            'monthly_usage': list[int],
            'skip_count': int,
            'registered_count': int,
            'remaining_count': int
        }
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
    periodicity = drug_periodicity_db.get_periodicity(약품코드)
    processed = processed_inventory_db.get_drug_by_code(약품코드)
    inventory = inventory_db.get_inventory(약품코드)

    # 약품명, 제약회사 조회
    drug_name = ''
    company = ''
    drug_type = ''

    if processed:
        drug_name = processed.get('약품명', '')
        company = processed.get('제약회사', '')
        drug_type = processed.get('약품유형', '')

    # 현재 재고
    current_stock = 0
    if inventory:
        current_stock = inventory.get('현재_재고수량', 0) or 0

    # 월별 사용량
    monthly_usage = []
    if processed:
        usage_json = processed.get('월별_조제수량_리스트', '[]')
        try:
            if isinstance(usage_json, str):
                monthly_usage = json.loads(usage_json)
            else:
                monthly_usage = usage_json
        except:
            monthly_usage = []

    return {
        'drug_code': 약품코드,
        'drug_name': drug_name,
        'company': company,
        'drug_type': drug_type,
        'similarity': round(best['similarity'] * 100, 1),  # 퍼센트로
        'periodicity_score': periodicity['periodicity_score'] if periodicity else 0,
        'avg_interval': periodicity['avg_interval'] if periodicity else None,
        'interval_cv': periodicity['interval_cv'] if periodicity else None,
        'height_cv': periodicity['height_cv'] if periodicity else None,
        'peak_count': periodicity['peak_count'] if periodicity else 0,
        'current_stock': current_stock,
        'monthly_usage': monthly_usage,
        'skip_count': best['skip_count'],
        'registered_count': best['registered_count'],
        'remaining_count': len(candidates) - 1
    }


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
        processed = processed_inventory_db.get_drug_by_code(약품코드)

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


def get_suggestion_stats():
    """
    제안 관련 통계 반환

    Returns:
        dict: {
            'total_periodic': int,       # 주기적 약품 총 수
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

    already_registered = len([d for d in periodic_drugs if d in registered_codes])
    skipped = len([d for d in periodic_drugs if skip_counts.get(d, 0) > 0])
    pending = len(periodic_drugs) - already_registered

    return {
        'total_periodic': len(periodic_drugs),
        'already_registered': already_registered,
        'pending': pending,
        'skipped': skipped,
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
