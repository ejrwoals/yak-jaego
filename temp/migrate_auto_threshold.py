#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
일회성 마이그레이션 스크립트: 기존 환자-약품 연결에 대해 임계값 자동 설정

실행 후 삭제해도 됩니다.
"""

import drug_patient_map_db
import drug_thresholds_db


def migrate():
    # 환자가 연결된 모든 약품 조회
    all_drug_codes = drug_patient_map_db.get_all_drugs_with_patients()

    print(f"환자가 연결된 약품 수: {len(all_drug_codes)}개")
    print("-" * 50)

    updated = 0
    skipped = 0

    for drug_code in all_drug_codes:
        # 해당 약품에 연결된 환자들의 처방량 조회
        patients = drug_patient_map_db.get_patients_for_drug_with_dosage(drug_code)

        if not patients:
            continue

        # 최대 처방량 계산
        max_dosage = max(p.get('1회_처방량', 1) for p in patients)

        # 현재 임계값 확인
        current = drug_thresholds_db.get_threshold(drug_code)

        # 임계값이 없거나 최대 처방량보다 낮으면 설정
        if current is None or current.get('절대재고_임계값') is None:
            drug_thresholds_db.upsert_threshold(drug_code, 절대재고_임계값=max_dosage)
            print(f"[설정] {drug_code}: 임계값 {max_dosage}개 (신규)")
            updated += 1
        elif current.get('절대재고_임계값', 0) < max_dosage:
            drug_thresholds_db.upsert_threshold(
                drug_code,
                절대재고_임계값=max_dosage,
                런웨이_임계값=current.get('런웨이_임계값')
            )
            print(f"[갱신] {drug_code}: 임계값 {current.get('절대재고_임계값')} → {max_dosage}개")
            updated += 1
        else:
            print(f"[스킵] {drug_code}: 이미 충분한 임계값 ({current.get('절대재고_임계값')}개 >= {max_dosage}개)")
            skipped += 1

    print("-" * 50)
    print(f"완료! 설정/갱신: {updated}개, 스킵: {skipped}개")


if __name__ == '__main__':
    migrate()
