"""
고변동성 약품 보고서 생성 모듈
CV (Coefficient of Variation) 기반 변동성 분석
"""
from html import escape as html_escape
import pandas as pd
import numpy as np
import os
from datetime import datetime
import json

# 기존 모듈에서 재사용
from generate_single_ma_report import (
    create_sparkline_svg,
    create_chart_data_json,
    calculate_custom_ma
)
import inventory_db
import checked_items_db
import drug_memos_db


def calculate_cv(timeseries_data):
    """
    변동계수(CV) 계산
    CV = 표준편차 / 평균

    Args:
        timeseries_data: 월별 사용량 리스트

    Returns:
        float: CV 값 (0~1+ 범위), 계산 불가 시 None
    """
    if not timeseries_data or len(timeseries_data) < 2:
        return None

    # None을 0으로 변환하여 모든 달을 포함 (0인 달도 변동성에 영향)
    valid_data = [v if v is not None else 0 for v in timeseries_data]

    mean = np.mean(valid_data)
    if mean == 0:
        return None  # 전체 기간 사용량이 0인 경우

    std = np.std(valid_data)
    return std / mean


def classify_by_volatility(cv, threshold_high=0.5, threshold_mid=0.3):
    """
    CV 값으로 변동성 그룹 분류

    Returns:
        str: 'high', 'mid', 'low', 또는 'unknown'
    """
    if cv is None:
        return 'unknown'

    if cv > threshold_high:
        return 'high'
    elif cv >= threshold_mid:
        return 'mid'
    else:
        return 'low'


# 단발성 약품 필터링 기준
MIN_APPEARANCE_RATE = 0.2  # 가중 등장률 20% 미만
RECENT_MONTHS_SAFETY = 2   # 최근 N개월 내 등장 시 안전 장치


def get_appearance_rate(timeseries_data):
    """
    등장률 계산: 0이 아닌 달 수 / 전체 기간

    Args:
        timeseries_data: 월별 사용량 리스트

    Returns:
        float: 등장률 (0~1)
    """
    if not timeseries_data:
        return 0
    valid_data = [v if v is not None else 0 for v in timeseries_data]
    non_zero_count = sum(1 for v in valid_data if v > 0)
    return non_zero_count / len(valid_data)


def get_weighted_appearance_rate(timeseries_data):
    """
    가중 등장률 계산: 최근 달에 더 높은 가중치 부여

    가중치: 선형 감소 (가장 최근 = 1.0, 가장 오래된 = 0.1)
    가중 등장률 = Σ(등장여부 × 가중치) / Σ(가중치)

    Args:
        timeseries_data: 월별 사용량 리스트 (시간순, 오래된 것부터)

    Returns:
        float: 가중 등장률 (0~1)
    """
    if not timeseries_data:
        return 0

    n = len(timeseries_data)
    valid_data = [v if v is not None else 0 for v in timeseries_data]

    # 선형 가중치: 가장 오래된 달 = 0.1, 가장 최근 달 = 1.0
    weights = [0.1 + 0.9 * (i / (n - 1)) if n > 1 else 1.0 for i in range(n)]

    weighted_sum = sum(w for v, w in zip(valid_data, weights) if v > 0)
    total_weight = sum(weights)

    return weighted_sum / total_weight if total_weight > 0 else 0


def is_recently_appeared(timeseries_data, recent_months=RECENT_MONTHS_SAFETY):
    """
    최근 N개월 내에 등장했는지 확인 (안전 장치)

    Args:
        timeseries_data: 월별 사용량 리스트 (시간순)
        recent_months: 확인할 최근 개월 수

    Returns:
        bool: 최근 N개월 내 등장 여부
    """
    if not timeseries_data:
        return False

    recent_data = timeseries_data[-recent_months:]
    return any(v and v > 0 for v in recent_data)


def classify_drug(timeseries_data):
    """
    약품 분류: regular(정규), sporadic(단발성), new(신규)

    분류 기준:
    - 가중 등장률 ≥ 20% → regular (정규)
    - 가중 등장률 < 20% + 최근 2개월 내 등장 → new (신규)
    - 가중 등장률 < 20% + 최근 2개월 내 등장 없음 → sporadic (단발성)

    Returns:
        str: 'regular', 'sporadic', 'new'
    """
    weighted_rate = get_weighted_appearance_rate(timeseries_data)

    # 가중 등장률이 충분하면 정규
    if weighted_rate >= MIN_APPEARANCE_RATE:
        return 'regular'

    # 가중 등장률이 낮지만 최근 등장했으면 신규
    if is_recently_appeared(timeseries_data, RECENT_MONTHS_SAFETY):
        return 'new'

    # 둘 다 아니면 단발성
    return 'sporadic'


def get_usage_stats(timeseries_data):
    """
    사용량 통계 계산

    Returns:
        dict: min, max, mean 값
    """
    valid_data = [v for v in timeseries_data if v is not None and v > 0]

    if not valid_data:
        return {'min': 0, 'max': 0, 'mean': 0}

    return {
        'min': min(valid_data),
        'max': max(valid_data),
        'mean': np.mean(valid_data)
    }


def generate_html_report(df, months, mode='dispense', threshold_high=0.5, threshold_mid=0.3):
    """
    고변동성 약품 보고서 HTML 생성

    Args:
        df: DataFrame (월별_조제수량_리스트 또는 월별_판매수량_리스트 컬럼 필요)
        months: 월 리스트
        mode: 'dispense' (전문약) 또는 'sale' (일반약)
        threshold_high: 고/중변동성 경계 (기본 0.5)
        threshold_mid: 중/저변동성 경계 (기본 0.3)
    """
    # 모드에 따른 설정
    # 참고: DB에는 월별_조제수량_리스트 컬럼만 존재 (전문약/일반약 모두 동일 컬럼 사용)
    if mode == 'dispense':
        report_title = '전문약 고변동성 약품 보고서'
        quantity_col = '월별_조제수량_리스트'
        quantity_label = '조제수량'
    else:
        report_title = '일반약 고변동성 약품 보고서'
        quantity_col = '월별_조제수량_리스트'  # 일반약도 동일 컬럼 사용
        quantity_label = '판매수량'

    # CV 및 통계 계산
    drugs_data = []
    for idx, row in df.iterrows():
        timeseries = row.get(quantity_col, [])
        if not isinstance(timeseries, list):
            try:
                timeseries = json.loads(timeseries) if isinstance(timeseries, str) else []
            except:
                timeseries = []

        # 분석 기간에 맞게 timeseries 슬라이싱 (최근 N개월만 사용)
        if len(timeseries) > len(months):
            timeseries = timeseries[-len(months):]

        # 분석 기간 내 사용 이력이 전혀 없는 약품은 제외
        if sum(timeseries) == 0:
            continue

        cv = calculate_cv(timeseries)
        stats = get_usage_stats(timeseries)
        volatility_group = classify_by_volatility(cv, threshold_high, threshold_mid)

        # 3개월 이동평균 계산
        ma_data = calculate_custom_ma(timeseries, 3)

        drugs_data.append({
            'drug_code': str(row.get('약품코드', '')),
            'drug_name': str(row.get('약품명', '')),
            'company': str(row.get('제약회사', '')),
            'cv': cv,
            'cv_percent': round(cv * 100, 1) if cv is not None else None,
            'mean_usage': round(stats['mean'], 1),
            'min_usage': round(stats['min'], 1),
            'max_usage': round(stats['max'], 1),
            'stock': row.get('최종_재고수량', 0) or row.get('현재_재고수량', 0) or 0,
            'volatility_group': volatility_group,
            'timeseries': timeseries,
            'ma_data': ma_data
        })

    # CV 기준 내림차순 정렬 (None은 맨 뒤)
    drugs_data.sort(key=lambda x: (x['cv'] is None, -(x['cv'] or 0)))

    # 등장률 계산 및 3분류 (정규/단발성/신규)
    for drug in drugs_data:
        drug['appearance_rate'] = get_appearance_rate(drug['timeseries'])
        drug['weighted_appearance_rate'] = get_weighted_appearance_rate(drug['timeseries'])
        # 등장 횟수 계산
        drug['appearance_count'] = sum(1 for v in drug['timeseries'] if v and v > 0)
        # 약품 분류 (regular/sporadic/new)
        drug['drug_category'] = classify_drug(drug['timeseries'])

    # 3가지 카테고리로 분류
    sporadic_drugs = [d for d in drugs_data if d['drug_category'] == 'sporadic']
    new_drugs = [d for d in drugs_data if d['drug_category'] == 'new']
    regular_drugs = [d for d in drugs_data if d['drug_category'] == 'regular']
    sporadic_count = len(sporadic_drugs)
    new_drugs_count = len(new_drugs)

    # 그룹별 카운트 (정규 약품만)
    high_count = sum(1 for d in regular_drugs if d['volatility_group'] == 'high')
    mid_count = sum(1 for d in regular_drugs if d['volatility_group'] == 'mid')
    low_count = sum(1 for d in regular_drugs if d['volatility_group'] == 'low')
    unknown_count = sum(1 for d in regular_drugs if d['volatility_group'] == 'unknown')

    # 산점도 데이터 생성 (정규 약품만)
    scatter_data = [d for d in regular_drugs if d['cv'] is not None and d['mean_usage'] > 0]
    scatter_json = json.dumps([{
        'drug_code': d['drug_code'],
        'drug_name': d['drug_name'],
        'mean_usage': d['mean_usage'],
        'cv': round(d['cv'], 3),
        'group': d['volatility_group']
    } for d in scatter_data], ensure_ascii=False)

    # 메모 데이터 로드
    all_memos = drug_memos_db.get_all_memos()

    # HTML 생성
    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{report_title}</title>
    <script src="https://cdn.plot.ly/plotly-2.18.2.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #f5f5f5;
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
        }}
        h1 {{
            color: #2d3748;
            text-align: center;
            margin-bottom: 10px;
            font-size: 2.2em;
        }}
        .subtitle {{
            text-align: center;
            color: #718096;
            margin-bottom: 30px;
        }}
        .threshold-info {{
            text-align: center;
            background: #f7fafc;
            padding: 12px 20px;
            border-radius: 10px;
            margin-bottom: 25px;
            color: #4a5568;
            font-size: 0.95em;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }}
        .summary-card {{
            padding: 25px;
            border-radius: 15px;
            text-align: center;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .summary-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        }}
        .summary-card.high {{
            background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
            border: 2px solid #f87171;
        }}
        .summary-card.mid {{
            background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
            border: 2px solid #fbbf24;
        }}
        .summary-card.low {{
            background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
            border: 2px solid #34d399;
        }}
        .summary-card h3 {{
            font-size: 1em;
            margin-bottom: 10px;
            color: #374151;
        }}
        .summary-card .value {{
            font-size: 2.5em;
            font-weight: bold;
        }}
        .summary-card.high .value {{ color: #dc2626; }}
        .summary-card.mid .value {{ color: #d97706; }}
        .summary-card.low .value {{ color: #059669; }}
        .summary-card .unit {{
            font-size: 0.9em;
            color: #6b7280;
        }}

        /* 산점도 */
        .scatter-container {{
            margin: 30px 0;
            background: #f8fafc;
            border-radius: 15px;
            padding: 20px;
        }}
        .scatter-title {{
            font-size: 1.2em;
            color: #2d3748;
            margin-bottom: 15px;
            text-align: center;
        }}
        #scatter-chart {{
            width: 100%;
            height: 400px;
        }}

        /* 테이블 */
        .table-container {{
            margin: 30px 0;
            overflow-x: auto;
        }}
        .search-box {{
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e2e8f0;
            border-radius: 10px;
            font-size: 1em;
            margin-bottom: 15px;
        }}
        .search-box:focus {{
            outline: none;
            border-color: #4facfe;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        th {{
            background: #4a5568;
            color: white;
            padding: 12px 8px;
            text-align: left;
            position: sticky;
            top: 0;
            z-index: 10;
        }}
        td {{
            padding: 10px 8px;
            border-bottom: 1px solid #e2e8f0;
        }}
        tr.clickable-row {{
            cursor: pointer;
            transition: background-color 0.2s;
        }}
        tr.clickable-row:hover {{
            background-color: rgba(79, 172, 254, 0.1) !important;
        }}
        tr.high-cv {{
            background-color: rgba(254, 226, 226, 0.5);
        }}
        tr.mid-cv {{
            background-color: rgba(254, 243, 199, 0.5);
        }}
        tr.low-cv {{
            background-color: rgba(209, 250, 229, 0.3);
        }}
        tr.unknown-cv {{
            background-color: #f9fafb;
        }}
        .cv-cell {{
            font-weight: bold;
        }}
        .cv-cell.high {{ color: #dc2626; }}
        .cv-cell.mid {{ color: #d97706; }}
        .cv-cell.low {{ color: #059669; }}
        .cv-cell.unknown {{ color: #9ca3af; }}
        .range-cell {{
            font-size: 0.9em;
            color: #6b7280;
        }}

        /* 인라인 차트 */
        .inline-chart-row {{
            background: #f8fafc !important;
            border-left: 4px solid #4facfe;
        }}
        .inline-chart-row td {{
            padding: 20px;
        }}
        .inline-chart-container {{
            display: flex;
            gap: 20px;
            align-items: flex-start;
        }}
        .stats-cards {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 15px;
        }}
        .stat-card {{
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 12px 16px;
            min-width: 120px;
        }}
        .stat-card .label {{
            font-size: 0.8em;
            color: #718096;
            margin-bottom: 4px;
        }}
        .stat-card .value {{
            font-size: 1.3em;
            font-weight: bold;
            color: #2d3748;
        }}

        /* 메모 버튼 */
        .memo-btn {{
            background: none;
            border: none;
            cursor: pointer;
            font-size: 1.1em;
            padding: 4px 6px;
            border-radius: 4px;
            transition: background-color 0.2s;
        }}
        .memo-btn:hover {{
            background-color: #f3f4f6;
        }}
        .memo-btn.has-memo {{
            color: #f59e0b;
        }}

        /* 사이드바 책갈피 */
        .alert-sidebar {{
            position: fixed;
            right: 0;
            top: 120px;
            z-index: 999;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}
        .alert-bookmark {{
            position: relative;
            right: -120px;
            padding: 12px 16px;
            border-radius: 12px 0 0 12px;
            cursor: pointer;
            transition: right 0.3s ease, box-shadow 0.3s ease, transform 0.2s ease;
            min-width: 160px;
            font-weight: 600;
            display: flex;
            flex-direction: column;
            gap: 4px;
            user-select: none;
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-right: none;
        }}
        .alert-bookmark:hover {{
            right: 0;
            transform: scale(1.02);
        }}
        .alert-bookmark.sporadic {{
            background: linear-gradient(135deg, rgba(139, 92, 246, 0.75) 0%, rgba(91, 33, 182, 0.85) 100%);
            box-shadow: -4px 4px 20px rgba(91, 33, 182, 0.3);
            color: white;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
        }}
        .alert-bookmark.sporadic:hover {{
            box-shadow: -6px 6px 24px rgba(91, 33, 182, 0.4);
        }}
        .alert-bookmark.new-drug {{
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.75) 0%, rgba(5, 150, 105, 0.85) 100%);
            box-shadow: -4px 4px 20px rgba(5, 150, 105, 0.3);
            color: white;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
        }}
        .alert-bookmark.new-drug:hover {{
            box-shadow: -6px 6px 24px rgba(5, 150, 105, 0.4);
        }}
        .alert-icon {{
            font-size: 1.5em;
        }}
        .alert-title {{
            font-size: 0.9em;
            opacity: 0.9;
        }}
        .alert-count {{
            font-size: 1.4em;
            font-weight: bold;
        }}

        /* 모달 */
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
        }}
        .modal-content {{
            background-color: #fff;
            margin: 3% auto;
            padding: 0;
            border-radius: 12px;
            width: 95%;
            max-width: 1200px;
            max-height: 90vh;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }}
        .modal-header {{
            background-color: #8b5cf6;
            color: white;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .modal-header h3 {{
            margin: 0;
            font-size: 1.3em;
        }}
        .modal-close {{
            font-size: 28px;
            cursor: pointer;
            color: white;
            line-height: 1;
        }}
        .modal-close:hover {{
            opacity: 0.8;
        }}
        .modal-body {{
            padding: 20px;
            max-height: 80vh;
            overflow-y: auto;
        }}
        .modal-info {{
            color: #666;
            margin-bottom: 15px;
            font-size: 0.95em;
        }}
        .modal-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        .modal-table th {{
            background: #4a5568;
            color: white;
            padding: 10px 8px;
            text-align: left;
        }}
        .modal-table td {{
            padding: 8px;
            border-bottom: 1px solid #e2e8f0;
        }}
        .modal-table tr.clickable-row {{
            cursor: pointer;
            transition: background-color 0.2s;
        }}
        .modal-table tr.clickable-row:hover {{
            background-color: rgba(139, 92, 246, 0.1) !important;
        }}
        .modal-table .inline-chart-row {{
            background: #f8fafc !important;
            border-left: 4px solid #8b5cf6;
        }}
        .modal-table .inline-chart-row td {{
            padding: 20px;
        }}

        /* 툴팁 */
        .help-icon {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 16px;
            height: 16px;
            background: rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            font-size: 11px;
            cursor: help;
            margin-left: 4px;
            position: relative;
        }}
        .help-icon:hover .tooltip {{
            display: block;
        }}
        .tooltip {{
            display: none;
            position: absolute;
            bottom: 100%;
            left: 50%;
            transform: translateX(-50%);
            background: #1a202c;
            color: white;
            padding: 10px 12px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: normal;
            white-space: nowrap;
            z-index: 1001;
            margin-bottom: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            text-align: left;
            line-height: 1.5;
        }}
        .tooltip::after {{
            content: '';
            position: absolute;
            top: 100%;
            left: 50%;
            transform: translateX(-50%);
            border: 6px solid transparent;
            border-top-color: #1a202c;
        }}

        /* 반응형 */
        @media (max-width: 768px) {{
            .summary-grid {{
                grid-template-columns: 1fr;
            }}
            .container {{
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{report_title}</h1>
        <p class="subtitle">분석 기간: {months[0]} ~ {months[-1]} ({len(months)}개월) &nbsp;|&nbsp; 생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

        <div class="threshold-info">
            CV 임계값 설정 &nbsp;|&nbsp;
            🔴 고변동성: CV &gt; {threshold_high} &nbsp;|&nbsp;
            🟡 중변동성: {threshold_mid} ≤ CV ≤ {threshold_high} &nbsp;|&nbsp;
            🟢 저변동성: CV &lt; {threshold_mid}
        </div>

        <!-- 요약 카드 -->
        <div class="summary-grid">
            <div class="summary-card high" onclick="filterTable('high')">
                <h3>🔴 고변동성</h3>
                <div class="value">{high_count}</div>
                <div class="unit">개</div>
            </div>
            <div class="summary-card mid" onclick="filterTable('mid')">
                <h3>🟡 중변동성</h3>
                <div class="value">{mid_count}</div>
                <div class="unit">개</div>
            </div>
            <div class="summary-card low" onclick="filterTable('low')">
                <h3>🟢 저변동성</h3>
                <div class="value">{low_count}</div>
                <div class="unit">개</div>
            </div>
        </div>

        <!-- 산점도 -->
        <div class="scatter-container">
            <h3 class="scatter-title">📊 약품별 사용량 변동성 분포</h3>
            <div id="scatter-chart"></div>
        </div>

        <!-- 테이블 -->
        <div class="table-container">
            <input type="text" class="search-box" id="searchInput"
                   placeholder="약품명, 제약회사, 약품코드로 검색..."
                   oninput="searchTable()">

            <table id="volatility-table">
                <thead>
                    <tr>
                        <th style="width: 50px;">메모</th>
                        <th>약품명</th>
                        <th>제약회사</th>
                        <th>CV (%)</th>
                        <th>평균 {quantity_label}</th>
                        <th>현재 재고</th>
                        <th>{quantity_label} 범위</th>
                        <th>트렌드</th>
                    </tr>
                </thead>
                <tbody>
"""

    # 테이블 행 생성 (정규 약품만)
    for drug in regular_drugs:
        cv_display = f"{drug['cv_percent']}%" if drug['cv_percent'] is not None else 'N/A'
        cv_class = drug['volatility_group']
        row_class = f"{cv_class}-cv"

        # 스파크라인 생성
        sparkline = create_sparkline_svg(drug['timeseries'], drug['ma_data'], 3)

        # 차트 데이터 JSON
        chart_data = create_chart_data_json(
            months,
            drug['timeseries'],
            drug['ma_data'],
            drug['mean_usage'],
            drug['drug_name'],
            drug['drug_code'],
            3,
            drug['stock'],
            'N/A'
        )

        # 메모 여부
        has_memo = drug['drug_code'] in all_memos
        memo_class = 'has-memo' if has_memo else ''

        # 범위 표시
        range_display = f"{drug['min_usage']:.0f} ~ {drug['max_usage']:.0f}"

        html_content += f"""
                    <tr class="clickable-row {row_class}"
                        data-drug-code="{html_escape(drug['drug_code'])}"
                        data-group="{cv_class}"
                        data-chart-data='{html_escape(chart_data)}'
                        data-cv="{drug['cv'] or 0}"
                        data-mean="{drug['mean_usage']}"
                        data-weighted-rate="{drug['weighted_appearance_rate']}"
                        onclick="toggleInlineChart(this, '{html_escape(drug['drug_code'])}')">
                        <td style="text-align: center;">
                            <button class="memo-btn {memo_class}" onclick="event.stopPropagation(); openMemo('{html_escape(drug['drug_code'])}')">
                                ✎
                            </button>
                        </td>
                        <td>{html_escape(drug['drug_name'])}</td>
                        <td>{html_escape(drug['company'])}</td>
                        <td class="cv-cell {cv_class}">{cv_display}</td>
                        <td>{drug['mean_usage']:.1f}</td>
                        <td>{drug['stock']:.0f}</td>
                        <td class="range-cell">{range_display}</td>
                        <td>{sparkline}</td>
                    </tr>
"""

    # 단발성 약품 테이블 행 생성 (메인 테이블과 동일한 구조)
    sporadic_rows = ""
    for drug in sporadic_drugs:
        cv_display = f"{drug['cv_percent']}%" if drug['cv_percent'] is not None else 'N/A'
        range_display = f"{drug['min_usage']:.0f} ~ {drug['max_usage']:.0f}"

        # 스파크라인 생성
        sparkline = create_sparkline_svg(drug['timeseries'], drug['ma_data'], 3)

        # 차트 데이터 JSON (인라인 차트용)
        chart_data = create_chart_data_json(
            months,
            drug['timeseries'],
            drug['ma_data'],
            drug['mean_usage'],
            drug['drug_name'],
            drug['drug_code'],
            3,
            drug['stock'],
            'N/A'
        )

        weighted_rate_display = f"{drug['weighted_appearance_rate'] * 100:.1f}%"
        sporadic_rows += f"""
                        <tr class="clickable-row"
                            data-drug-code="{html_escape(drug['drug_code'])}"
                            data-chart-data='{html_escape(chart_data)}'
                            data-cv="{drug['cv'] or 0}"
                            data-mean="{drug['mean_usage']}"
                            data-weighted-rate="{drug['weighted_appearance_rate']}"
                            onclick="toggleSporadicInlineChart(this, '{html_escape(drug['drug_code'])}')">
                            <td>{html_escape(drug['drug_name'])}</td>
                            <td>{html_escape(drug['company'])}</td>
                            <td style="text-align: right;">{cv_display}</td>
                            <td style="text-align: right;">{drug['mean_usage']:.1f}</td>
                            <td class="range-cell">{range_display}</td>
                            <td style="text-align: center;">{weighted_rate_display}</td>
                            <td>{sparkline}</td>
                        </tr>
"""

    # 신규 약품 테이블 행 생성 (단발성과 동일한 구조)
    new_drugs_rows = ""
    for drug in new_drugs:
        cv_display = f"{drug['cv_percent']}%" if drug['cv_percent'] is not None else 'N/A'
        range_display = f"{drug['min_usage']:.0f} ~ {drug['max_usage']:.0f}"

        # 스파크라인 생성
        sparkline = create_sparkline_svg(drug['timeseries'], drug['ma_data'], 3)

        # 차트 데이터 JSON (인라인 차트용)
        chart_data = create_chart_data_json(
            months,
            drug['timeseries'],
            drug['ma_data'],
            drug['mean_usage'],
            drug['drug_name'],
            drug['drug_code'],
            3,
            drug['stock'],
            'N/A'
        )

        weighted_rate_display = f"{drug['weighted_appearance_rate'] * 100:.1f}%"
        new_drugs_rows += f"""
                        <tr class="clickable-row"
                            data-drug-code="{html_escape(drug['drug_code'])}"
                            data-chart-data='{html_escape(chart_data)}'
                            data-cv="{drug['cv'] or 0}"
                            data-mean="{drug['mean_usage']}"
                            data-weighted-rate="{drug['weighted_appearance_rate']}"
                            onclick="toggleNewDrugsInlineChart(this, '{html_escape(drug['drug_code'])}')">
                            <td>{html_escape(drug['drug_name'])}</td>
                            <td>{html_escape(drug['company'])}</td>
                            <td style="text-align: right;">{cv_display}</td>
                            <td style="text-align: right;">{drug['mean_usage']:.1f}</td>
                            <td class="range-cell">{range_display}</td>
                            <td style="text-align: center;">{weighted_rate_display}</td>
                            <td>{sparkline}</td>
                        </tr>
"""

    # 사이드바 책갈피 HTML (단발성 + 신규 약품)
    sporadic_bookmark_item = f"""
        <div class="alert-bookmark sporadic" onclick="openSporadicModal()">
            <span class="alert-icon">📌</span>
            <span class="alert-title">단발성 약품</span>
            <span class="alert-count">{sporadic_count}개</span>
        </div>
""" if sporadic_count > 0 else ""

    new_drugs_bookmark_item = f"""
        <div class="alert-bookmark new-drug" onclick="openNewDrugsModal()">
            <span class="alert-icon">🆕</span>
            <span class="alert-title">신규 약품</span>
            <span class="alert-count">{new_drugs_count}개</span>
        </div>
""" if new_drugs_count > 0 else ""

    sidebar_bookmark = f"""
    <div class="alert-sidebar">
        {sporadic_bookmark_item}
        {new_drugs_bookmark_item}
    </div>
""" if sporadic_count > 0 or new_drugs_count > 0 else ""

    # 단발성 약품 모달 HTML
    total_months = len(months) if months else 0
    sporadic_modal = f"""
    <div id="sporadicModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>📌 단발성 약품 ({sporadic_count}개)</h3>
                <span class="modal-close" onclick="closeSporadicModal()">&times;</span>
            </div>
            <div class="modal-body">
                <p class="modal-info">
                    가중 등장률 20% 미만 &amp; 최근 {RECENT_MONTHS_SAFETY}개월 내 등장 없음 - 변동성 분석 대상에서 제외된 약품입니다.<br>
                    <small style="color: #888;">※ 가중 등장률: 최근 달에 높은 가중치 부여 (최근=1.0, 과거=0.1)</small>
                </p>
                <table class="modal-table" id="sporadic-table">
                    <thead>
                        <tr>
                            <th>약품명</th>
                            <th>제약회사</th>
                            <th style="text-align: right;">CV (%)</th>
                            <th style="text-align: right;">평균 {quantity_label}</th>
                            <th>{quantity_label} 범위</th>
                            <th style="text-align: center;">
                                가중 등장률
                                <span class="help-icon">?<span class="tooltip">최근 달에 높은 가중치 부여<br>최근 = 1.0, 과거 = 0.1<br>선형 감소 방식</span></span>
                            </th>
                            <th>트렌드</th>
                        </tr>
                    </thead>
                    <tbody>
                        {sporadic_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
""" if sporadic_count > 0 else ""

    # 신규 약품 모달 HTML
    new_drugs_modal = f"""
    <div id="newDrugsModal" class="modal">
        <div class="modal-content">
            <div class="modal-header" style="background-color: #10b981;">
                <h3>🆕 신규 약품 ({new_drugs_count}개)</h3>
                <span class="modal-close" onclick="closeNewDrugsModal()">&times;</span>
            </div>
            <div class="modal-body">
                <p class="modal-info">
                    가중 등장률 20% 미만이지만 최근 {RECENT_MONTHS_SAFETY}개월 내 사용이 시작된 약품입니다.<br>
                    <small style="color: #888;">※ 변동성 분석 대상에서는 제외되지만, 최근 도입된 약품으로 별도 관리됩니다.</small>
                </p>
                <table class="modal-table" id="new-drugs-table">
                    <thead>
                        <tr>
                            <th>약품명</th>
                            <th>제약회사</th>
                            <th style="text-align: right;">CV (%)</th>
                            <th style="text-align: right;">평균 {quantity_label}</th>
                            <th>{quantity_label} 범위</th>
                            <th style="text-align: center;">
                                가중 등장률
                                <span class="help-icon">?<span class="tooltip">최근 달에 높은 가중치 부여<br>최근 = 1.0, 과거 = 0.1<br>선형 감소 방식</span></span>
                            </th>
                            <th>트렌드</th>
                        </tr>
                    </thead>
                    <tbody>
                        {new_drugs_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
""" if new_drugs_count > 0 else ""

    html_content += f"""
                </tbody>
            </table>
        </div>
    </div>

    {sidebar_bookmark}
    {sporadic_modal}
    {new_drugs_modal}

    <script>
        // 산점도 데이터
        const scatterData = {scatter_json};
        const thresholdHigh = {threshold_high};
        const thresholdMid = {threshold_mid};

        // 산점도 생성
        function createScatterPlot() {{
            const highGroup = scatterData.filter(d => d.group === 'high');
            const midGroup = scatterData.filter(d => d.group === 'mid');
            const lowGroup = scatterData.filter(d => d.group === 'low');

            const traces = [
                {{
                    x: highGroup.map(d => d.mean_usage),
                    y: highGroup.map(d => d.cv),
                    text: highGroup.map(d => d.drug_name),
                    mode: 'markers',
                    name: '고변동성',
                    marker: {{ color: '#dc2626', size: 10, opacity: 0.7 }},
                    hovertemplate: '<b>%{{text}}</b><br>평균: %{{x:.1f}}<br>CV: %{{y:.2f}}<extra></extra>'
                }},
                {{
                    x: midGroup.map(d => d.mean_usage),
                    y: midGroup.map(d => d.cv),
                    text: midGroup.map(d => d.drug_name),
                    mode: 'markers',
                    name: '중변동성',
                    marker: {{ color: '#d97706', size: 10, opacity: 0.7 }},
                    hovertemplate: '<b>%{{text}}</b><br>평균: %{{x:.1f}}<br>CV: %{{y:.2f}}<extra></extra>'
                }},
                {{
                    x: lowGroup.map(d => d.mean_usage),
                    y: lowGroup.map(d => d.cv),
                    text: lowGroup.map(d => d.drug_name),
                    mode: 'markers',
                    name: '저변동성',
                    marker: {{ color: '#059669', size: 10, opacity: 0.7 }},
                    hovertemplate: '<b>%{{text}}</b><br>평균: %{{x:.1f}}<br>CV: %{{y:.2f}}<extra></extra>'
                }}
            ];

            const maxCV = Math.max(...scatterData.map(d => d.cv)) * 1.1;

            const layout = {{
                xaxis: {{
                    title: '평균 월 사용량',
                    type: 'log',
                    gridcolor: '#e5e7eb'
                }},
                yaxis: {{
                    title: 'CV (변동계수)',
                    range: [0, maxCV],
                    gridcolor: '#e5e7eb'
                }},
                shapes: [
                    {{
                        type: 'line',
                        xref: 'paper', x0: 0, x1: 1,
                        yref: 'y', y0: thresholdHigh, y1: thresholdHigh,
                        line: {{ color: '#dc2626', width: 2, dash: 'dash' }}
                    }},
                    {{
                        type: 'line',
                        xref: 'paper', x0: 0, x1: 1,
                        yref: 'y', y0: thresholdMid, y1: thresholdMid,
                        line: {{ color: '#d97706', width: 2, dash: 'dash' }}
                    }}
                ],
                annotations: [
                    {{
                        x: 1.02, xref: 'paper',
                        y: thresholdHigh, yref: 'y',
                        text: '고/중 경계',
                        showarrow: false,
                        font: {{ size: 11, color: '#dc2626' }}
                    }},
                    {{
                        x: 1.02, xref: 'paper',
                        y: thresholdMid, yref: 'y',
                        text: '중/저 경계',
                        showarrow: false,
                        font: {{ size: 11, color: '#d97706' }}
                    }}
                ],
                hovermode: 'closest',
                showlegend: true,
                legend: {{ x: 0, y: 1.15, orientation: 'h' }},
                margin: {{ t: 50, r: 80 }},
                plot_bgcolor: '#fafafa'
            }};

            Plotly.newPlot('scatter-chart', traces, layout, {{responsive: true}});
        }}

        createScatterPlot();

        // 테이블 검색
        function searchTable() {{
            const query = document.getElementById('searchInput').value.toLowerCase();
            const rows = document.querySelectorAll('#volatility-table tbody tr.clickable-row');

            rows.forEach(row => {{
                const text = row.textContent.toLowerCase();
                const drugCode = row.dataset.drugCode.toLowerCase();
                const match = text.includes(query) || drugCode.includes(query);
                row.style.display = match ? '' : 'none';
            }});
        }}

        // 그룹별 필터
        let currentFilter = null;
        function filterTable(group) {{
            const rows = document.querySelectorAll('#volatility-table tbody tr.clickable-row');

            if (currentFilter === group) {{
                // 같은 그룹 클릭 시 필터 해제
                rows.forEach(row => row.style.display = '');
                currentFilter = null;
            }} else {{
                rows.forEach(row => {{
                    row.style.display = row.dataset.group === group ? '' : 'none';
                }});
                currentFilter = group;
            }}
        }}

        // 인라인 차트 토글
        function toggleInlineChart(row, drugCode) {{
            // 기존 차트 행 닫기
            const existingChart = document.querySelector('.inline-chart-row');
            if (existingChart) {{
                const prevRow = existingChart.previousElementSibling;
                if (prevRow) prevRow.classList.remove('expanded');
                existingChart.remove();

                // 같은 행 클릭 시 닫기만
                if (prevRow && prevRow.dataset.drugCode === drugCode) {{
                    return;
                }}
            }}

            row.classList.add('expanded');

            const chartData = JSON.parse(row.dataset.chartData);
            const cv = parseFloat(row.dataset.cv);
            const mean = parseFloat(row.dataset.mean);
            const weightedRate = parseFloat(row.dataset.weightedRate);

            const chartRow = document.createElement('tr');
            chartRow.className = 'inline-chart-row';
            chartRow.innerHTML = `
                <td colspan="8">
                    <div class="stats-cards">
                        <div class="stat-card">
                            <div class="label">CV (변동계수)</div>
                            <div class="value">${{(cv * 100).toFixed(1)}}%</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">가중 등장률</div>
                            <div class="value">${{(weightedRate * 100).toFixed(1)}}%</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">평균 사용량</div>
                            <div class="value">${{mean.toFixed(1)}}</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">현재 재고</div>
                            <div class="value">${{chartData.stock}}</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">3개월 이동평균</div>
                            <div class="value">${{chartData.latest_ma ? chartData.latest_ma.toFixed(1) : 'N/A'}}</div>
                        </div>
                    </div>
                    <div id="inline-chart-${{drugCode}}" style="width: 100%; height: 300px;"></div>
                </td>
            `;

            row.after(chartRow);

            // Plotly 차트 렌더링
            renderInlineChart(drugCode, chartData);
        }}

        function renderInlineChart(drugCode, chartData) {{
            const traces = [
                {{
                    x: chartData.months,
                    y: chartData.timeseries,
                    mode: 'lines+markers',
                    name: '실제 사용량',
                    line: {{ color: 'black', width: 2, dash: 'dot' }},
                    marker: {{ size: 6, color: 'black' }}
                }},
                {{
                    x: chartData.months,
                    y: chartData.ma.filter(v => v !== null),
                    mode: 'lines',
                    name: '3개월 이동평균',
                    line: {{ color: '#4facfe', width: 3 }}
                }}
            ];

            // 현재 재고 수평선 추가
            if (chartData.stock > 0) {{
                traces.push({{
                    x: chartData.months,
                    y: Array(chartData.months.length).fill(chartData.stock),
                    mode: 'lines',
                    name: '현재 재고',
                    line: {{ color: '#e53e3e', width: 2, dash: 'dash' }}
                }});
            }}

            const layout = {{
                title: chartData.drug_name,
                xaxis: {{ title: '월', tickangle: -45 }},
                yaxis: {{ title: '수량' }},
                showlegend: true,
                legend: {{ x: 0, y: 1.15, orientation: 'h' }},
                margin: {{ t: 60, b: 80 }},
                hovermode: 'x unified'
            }};

            Plotly.newPlot(`inline-chart-${{drugCode}}`, traces, layout, {{responsive: true}});
        }}

        // 메모 열기 (실제 구현은 modal 필요)
        function openMemo(drugCode) {{
            alert('메모 기능은 약품 관리 페이지에서 이용하세요.\\n약품코드: ' + drugCode);
        }}

        // 단발성 약품 모달 열기/닫기
        function openSporadicModal() {{
            document.getElementById('sporadicModal').style.display = 'block';
        }}

        function closeSporadicModal() {{
            document.getElementById('sporadicModal').style.display = 'none';
        }}

        // 단발성 모달 인라인 차트 토글
        function toggleSporadicInlineChart(row, drugCode) {{
            // 기존 차트 행 닫기
            const existingChart = document.querySelector('#sporadic-table .inline-chart-row');
            if (existingChart) {{
                const prevRow = existingChart.previousElementSibling;
                if (prevRow) prevRow.classList.remove('expanded');
                existingChart.remove();

                // 같은 행 클릭 시 닫기만
                if (prevRow && prevRow.dataset.drugCode === drugCode) {{
                    return;
                }}
            }}

            row.classList.add('expanded');

            const chartData = JSON.parse(row.dataset.chartData);
            const cv = parseFloat(row.dataset.cv);
            const mean = parseFloat(row.dataset.mean);
            const weightedRate = parseFloat(row.dataset.weightedRate);

            const chartRow = document.createElement('tr');
            chartRow.className = 'inline-chart-row';
            chartRow.innerHTML = `
                <td colspan="7">
                    <div class="stats-cards">
                        <div class="stat-card">
                            <div class="label">CV (변동계수)</div>
                            <div class="value">${{(cv * 100).toFixed(1)}}%</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">가중 등장률</div>
                            <div class="value">${{(weightedRate * 100).toFixed(1)}}%</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">평균 사용량</div>
                            <div class="value">${{mean.toFixed(1)}}</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">현재 재고</div>
                            <div class="value">${{chartData.stock}}</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">3개월 이동평균</div>
                            <div class="value">${{chartData.latest_ma ? chartData.latest_ma.toFixed(1) : 'N/A'}}</div>
                        </div>
                    </div>
                    <div id="sporadic-inline-chart-${{drugCode}}" style="width: 100%; height: 300px;"></div>
                </td>
            `;

            row.after(chartRow);

            // Plotly 차트 렌더링
            renderSporadicInlineChart(drugCode, chartData);
        }}

        function renderSporadicInlineChart(drugCode, chartData) {{
            const traces = [
                {{
                    x: chartData.months,
                    y: chartData.timeseries,
                    mode: 'lines+markers',
                    name: '실제 사용량',
                    line: {{ color: 'black', width: 2, dash: 'dot' }},
                    marker: {{ size: 6, color: 'black' }}
                }},
                {{
                    x: chartData.months,
                    y: chartData.ma.filter(v => v !== null),
                    mode: 'lines',
                    name: '3개월 이동평균',
                    line: {{ color: '#8b5cf6', width: 3 }}
                }}
            ];

            // 현재 재고 수평선 추가
            if (chartData.stock > 0) {{
                traces.push({{
                    x: chartData.months,
                    y: Array(chartData.months.length).fill(chartData.stock),
                    mode: 'lines',
                    name: '현재 재고',
                    line: {{ color: '#e53e3e', width: 2, dash: 'dash' }}
                }});
            }}

            const layout = {{
                title: chartData.drug_name,
                xaxis: {{ title: '월', tickangle: -45 }},
                yaxis: {{ title: '수량' }},
                showlegend: true,
                legend: {{ x: 0, y: 1.15, orientation: 'h' }},
                margin: {{ t: 60, b: 80 }},
                hovermode: 'x unified'
            }};

            Plotly.newPlot(`sporadic-inline-chart-${{drugCode}}`, traces, layout, {{responsive: true}});
        }}

        // 신규 약품 모달 열기/닫기
        function openNewDrugsModal() {{
            document.getElementById('newDrugsModal').style.display = 'block';
        }}

        function closeNewDrugsModal() {{
            document.getElementById('newDrugsModal').style.display = 'none';
        }}

        // 신규 약품 모달 인라인 차트 토글
        function toggleNewDrugsInlineChart(row, drugCode) {{
            // 기존 차트 행 닫기
            const existingChart = document.querySelector('#new-drugs-table .inline-chart-row');
            if (existingChart) {{
                const prevRow = existingChart.previousElementSibling;
                if (prevRow) prevRow.classList.remove('expanded');
                existingChart.remove();

                // 같은 행 클릭 시 닫기만
                if (prevRow && prevRow.dataset.drugCode === drugCode) {{
                    return;
                }}
            }}

            row.classList.add('expanded');

            const chartData = JSON.parse(row.dataset.chartData);
            const cv = parseFloat(row.dataset.cv);
            const mean = parseFloat(row.dataset.mean);
            const weightedRate = parseFloat(row.dataset.weightedRate);

            const chartRow = document.createElement('tr');
            chartRow.className = 'inline-chart-row';
            chartRow.innerHTML = `
                <td colspan="7">
                    <div class="stats-cards">
                        <div class="stat-card">
                            <div class="label">CV (변동계수)</div>
                            <div class="value">${{(cv * 100).toFixed(1)}}%</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">가중 등장률</div>
                            <div class="value">${{(weightedRate * 100).toFixed(1)}}%</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">평균 사용량</div>
                            <div class="value">${{mean.toFixed(1)}}</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">현재 재고</div>
                            <div class="value">${{chartData.stock}}</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">3개월 이동평균</div>
                            <div class="value">${{chartData.latest_ma ? chartData.latest_ma.toFixed(1) : 'N/A'}}</div>
                        </div>
                    </div>
                    <div id="new-drugs-inline-chart-${{drugCode}}" style="width: 100%; height: 300px;"></div>
                </td>
            `;

            row.after(chartRow);

            // Plotly 차트 렌더링
            renderNewDrugsInlineChart(drugCode, chartData);
        }}

        function renderNewDrugsInlineChart(drugCode, chartData) {{
            const traces = [
                {{
                    x: chartData.months,
                    y: chartData.timeseries,
                    mode: 'lines+markers',
                    name: '실제 사용량',
                    line: {{ color: 'black', width: 2, dash: 'dot' }},
                    marker: {{ size: 6, color: 'black' }}
                }},
                {{
                    x: chartData.months,
                    y: chartData.ma.filter(v => v !== null),
                    mode: 'lines',
                    name: '3개월 이동평균',
                    line: {{ color: '#10b981', width: 3 }}
                }}
            ];

            // 현재 재고 수평선 추가
            if (chartData.stock > 0) {{
                traces.push({{
                    x: chartData.months,
                    y: Array(chartData.months.length).fill(chartData.stock),
                    mode: 'lines',
                    name: '현재 재고',
                    line: {{ color: '#e53e3e', width: 2, dash: 'dash' }}
                }});
            }}

            const layout = {{
                title: chartData.drug_name,
                xaxis: {{ title: '월', tickangle: -45 }},
                yaxis: {{ title: '수량' }},
                showlegend: true,
                legend: {{ x: 0, y: 1.15, orientation: 'h' }},
                margin: {{ t: 60, b: 80 }},
                hovermode: 'x unified'
            }};

            Plotly.newPlot(`new-drugs-inline-chart-${{drugCode}}`, traces, layout, {{responsive: true}});
        }}

        // 모달 외부 클릭 시 닫기
        window.onclick = function(event) {{
            var sporadicModal = document.getElementById('sporadicModal');
            var newDrugsModal = document.getElementById('newDrugsModal');
            if (event.target == sporadicModal) {{
                sporadicModal.style.display = 'none';
            }}
            if (event.target == newDrugsModal) {{
                newDrugsModal.style.display = 'none';
            }}
        }}
    </script>
</body>
</html>
"""

    return html_content


def create_and_save_report(df, months, mode='dispense', threshold_high=0.5, threshold_mid=0.3, open_browser=True):
    """
    보고서 생성 및 파일 저장

    Returns:
        str: 저장된 파일 경로
    """
    # 보고서 폴더 생성
    report_dir = 'volatility_reports'
    os.makedirs(report_dir, exist_ok=True)

    # HTML 생성
    html_content = generate_html_report(df, months, mode, threshold_high, threshold_mid)

    # 파일명 생성
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"volatility_report_{mode}_{timestamp}.html"
    filepath = os.path.join(report_dir, filename)

    # 파일 저장
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"보고서 저장: {filepath}")

    # 브라우저에서 열기
    if open_browser:
        import webbrowser
        webbrowser.open(f'file://{os.path.abspath(filepath)}')

    return filepath


if __name__ == '__main__':
    # 테스트용
    import processed_inventory_db

    df = processed_inventory_db.get_processed_data(drug_type='전문약')
    metadata = processed_inventory_db.get_metadata()

    # 월 리스트 생성
    from datetime import datetime
    start = datetime.strptime(metadata['start_month'], '%Y-%m')
    end = datetime.strptime(metadata['end_month'], '%Y-%m')

    months = []
    current = start
    while current <= end:
        months.append(current.strftime('%Y-%m'))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    create_and_save_report(df, months, mode='dispense', threshold_high=0.5, threshold_mid=0.3)
