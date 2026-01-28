#!/usr/bin/env python3
"""
주기성 분석 테스트 스크립트
- 각 약품별로 여러 주기성 지표 계산
- 정렬 가능한 HTML 테이블 생성
"""

import sqlite3
import json
import numpy as np
from datetime import datetime
import os

def autocorr(x, lag):
    """자기상관 계산"""
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
    """사용량 > threshold인 인덱스와 값 반환"""
    peaks = [(i, v) for i, v in enumerate(usage_list) if v > threshold]
    return peaks

def calculate_interval_cv(peaks):
    """피크 간격의 변동계수 계산"""
    if len(peaks) < 2:
        return None
    indices = [p[0] for p in peaks]
    intervals = [indices[i+1] - indices[i] for i in range(len(indices)-1)]
    if len(intervals) == 0:
        return None
    mean_interval = np.mean(intervals)
    if mean_interval == 0:
        return None
    return np.std(intervals) / mean_interval

def calculate_height_cv(peaks):
    """피크 높이의 변동계수 계산"""
    if len(peaks) < 2:
        return None
    values = [p[1] for p in peaks]
    mean_val = np.mean(values)
    if mean_val == 0:
        return None
    std_val = np.std(values)
    if std_val == 0:
        return 0.0  # 모든 값이 동일하면 CV = 0
    return std_val / mean_val

def calculate_acf_max(usage_list, min_lag=2, max_lag=6):
    """lag 2~6 범위에서 최대 자기상관값"""
    acf_values = []
    for lag in range(min_lag, max_lag + 1):
        acf_values.append(autocorr(usage_list, lag))
    return max(acf_values) if acf_values else 0

def calculate_dominant_period(usage_list):
    """FFT로 지배적 주기 탐지"""
    x = np.array(usage_list, dtype=float)
    n = len(x)
    if n < 4:
        return None, 0

    # FFT 수행
    fft_result = np.fft.fft(x)
    power = np.abs(fft_result[:n//2])**2

    # DC 성분(index 0) 제외
    if len(power) < 2:
        return None, 0

    power[0] = 0

    # 지배적 주파수 찾기
    dominant_idx = np.argmax(power)
    if dominant_idx == 0:
        return None, 0

    dominant_period = n / dominant_idx if dominant_idx > 0 else None
    total_power = np.sum(power)
    dominant_ratio = power[dominant_idx] / total_power if total_power > 0 else 0

    return dominant_period, dominant_ratio

def calculate_periodicity_score(usage_list):
    """종합 주기성 점수 계산"""
    peaks = find_peaks(usage_list)

    if len(peaks) < 3:
        return {
            'peak_count': len(peaks),
            'interval_cv': None,
            'height_cv': None,
            'acf_max': None,
            'dominant_period': None,
            'fft_ratio': None,
            'periodicity_score': None,
            'avg_interval': None
        }

    interval_cv = calculate_interval_cv(peaks)
    height_cv = calculate_height_cv(peaks)
    acf_max = calculate_acf_max(usage_list)
    dominant_period, fft_ratio = calculate_dominant_period(usage_list)

    # 평균 간격 계산
    indices = [p[0] for p in peaks]
    intervals = [indices[i+1] - indices[i] for i in range(len(indices)-1)]
    avg_interval = np.mean(intervals) if intervals else None

    # 종합 점수 계산 (높을수록 주기적)
    if interval_cv is not None and height_cv is not None and acf_max is not None:
        # acf_max가 음수일 수 있으므로 0과 max 취함
        acf_factor = max(0, acf_max)
        # CV가 낮을수록 좋으므로 역수 형태로
        interval_factor = 1 / (1 + interval_cv)
        height_factor = 1 / (1 + height_cv)
        periodicity_score = 100 * acf_factor * interval_factor * height_factor
    else:
        periodicity_score = None

    return {
        'peak_count': len(peaks),
        'interval_cv': interval_cv,
        'height_cv': height_cv,
        'acf_max': acf_max,
        'dominant_period': dominant_period,
        'fft_ratio': fft_ratio,
        'periodicity_score': periodicity_score,
        'avg_interval': avg_interval
    }

def generate_sparkline_svg(usage_list, width=120, height=30):
    """스파크라인 SVG 생성"""
    if not usage_list or max(usage_list) == 0:
        return f'<svg width="{width}" height="{height}"></svg>'

    max_val = max(usage_list)
    n = len(usage_list)

    points = []
    for i, v in enumerate(usage_list):
        x = (i / (n - 1)) * (width - 4) + 2 if n > 1 else width / 2
        y = height - 2 - (v / max_val) * (height - 4) if max_val > 0 else height / 2
        points.append(f"{x},{y}")

    path = "M" + " L".join(points)

    return f'''<svg width="{width}" height="{height}" style="vertical-align: middle;">
        <path d="{path}" fill="none" stroke="#3b82f6" stroke-width="1.5"/>
    </svg>'''

def load_data():
    """DB에서 데이터 로드"""
    conn = sqlite3.connect('drug_timeseries.sqlite3')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT 약품코드, 약품명, 제약회사, 약품유형, 월별_조제수량_리스트, 최종_재고수량
        FROM drug_timeseries
    ''')

    rows = cursor.fetchall()
    conn.close()

    return rows

def generate_html_report(data):
    """HTML 보고서 생성"""

    html = '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>주기성 분석 테스트</title>
    <style>
        * {
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }
        .container {
            max-width: 1600px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            padding: 24px;
        }
        h1 {
            margin: 0 0 8px 0;
            color: #1f2937;
        }
        .subtitle {
            color: #6b7280;
            margin-bottom: 20px;
        }
        .filters {
            display: flex;
            gap: 16px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: center;
        }
        .filter-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .filter-group label {
            font-size: 14px;
            color: #4b5563;
        }
        input[type="text"], input[type="number"], select {
            padding: 8px 12px;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            font-size: 14px;
        }
        input[type="text"] {
            width: 200px;
        }
        .stats-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: #f9fafb;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }
        .stat-card .value {
            font-size: 24px;
            font-weight: 600;
            color: #1f2937;
        }
        .stat-card .label {
            font-size: 12px;
            color: #6b7280;
            margin-top: 4px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }
        th {
            background: #f9fafb;
            padding: 12px 8px;
            text-align: left;
            border-bottom: 2px solid #e5e7eb;
            cursor: pointer;
            user-select: none;
            white-space: nowrap;
        }
        th:hover {
            background: #f3f4f6;
        }
        th .sort-icon {
            margin-left: 4px;
            color: #9ca3af;
        }
        th.sorted-asc .sort-icon::after {
            content: "▲";
            color: #3b82f6;
        }
        th.sorted-desc .sort-icon::after {
            content: "▼";
            color: #3b82f6;
        }
        th:not(.sorted-asc):not(.sorted-desc) .sort-icon::after {
            content: "⇅";
        }
        td {
            padding: 10px 8px;
            border-bottom: 1px solid #e5e7eb;
            vertical-align: middle;
        }
        tr:hover {
            background: #f9fafb;
        }
        .drug-name {
            max-width: 250px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .company {
            max-width: 120px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            color: #6b7280;
            font-size: 12px;
        }
        .number {
            text-align: right;
            font-variant-numeric: tabular-nums;
        }
        .score-high {
            background: #dcfce7;
            color: #166534;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: 500;
        }
        .score-mid {
            background: #fef9c3;
            color: #854d0e;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: 500;
        }
        .score-low {
            background: #fee2e2;
            color: #991b1b;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: 500;
        }
        .na {
            color: #9ca3af;
        }
        .hidden {
            display: none;
        }
        .legend {
            margin-top: 20px;
            padding: 16px;
            background: #f9fafb;
            border-radius: 8px;
        }
        .legend h3 {
            margin: 0 0 12px 0;
            font-size: 14px;
            color: #1f2937;
        }
        .legend-item {
            margin-bottom: 8px;
            font-size: 13px;
            color: #4b5563;
        }
        .legend-item strong {
            color: #1f2937;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>주기성 분석 테스트</h1>
        <p class="subtitle">간헐적 사용 약품의 주기적 패턴 탐지를 위한 지표 비교</p>

        <div class="filters">
            <div class="filter-group">
                <label>검색:</label>
                <input type="text" id="search" placeholder="약품명, 제약회사, 약품코드">
            </div>
            <div class="filter-group">
                <label>최소 피크 수:</label>
                <input type="number" id="minPeaks" value="3" min="1" max="26" style="width:70px">
            </div>
            <div class="filter-group">
                <label>약품유형:</label>
                <select id="drugType">
                    <option value="">전체</option>
                    <option value="전문약">전문약</option>
                    <option value="일반약">일반약</option>
                </select>
            </div>
            <div class="filter-group">
                <label>주기성 점수:</label>
                <select id="scoreFilter">
                    <option value="">전체</option>
                    <option value="high">높음 (≥30)</option>
                    <option value="mid">중간 (10~30)</option>
                    <option value="low">낮음 (<10)</option>
                </select>
            </div>
        </div>

        <div class="stats-cards">
            <div class="stat-card">
                <div class="value" id="totalCount">0</div>
                <div class="label">전체 약품</div>
            </div>
            <div class="stat-card">
                <div class="value" id="filteredCount">0</div>
                <div class="label">필터된 약품</div>
            </div>
            <div class="stat-card">
                <div class="value" id="highScoreCount">0</div>
                <div class="label">주기성 높음</div>
            </div>
            <div class="stat-card">
                <div class="value" id="midScoreCount">0</div>
                <div class="label">주기성 중간</div>
            </div>
            <div class="stat-card">
                <div class="value" id="lowScoreCount">0</div>
                <div class="label">주기성 낮음</div>
            </div>
        </div>

        <table id="dataTable">
            <thead>
                <tr>
                    <th data-col="drug_code">약품코드<span class="sort-icon"></span></th>
                    <th data-col="drug_name">약품명<span class="sort-icon"></span></th>
                    <th data-col="company">제약회사<span class="sort-icon"></span></th>
                    <th data-col="drug_type">유형<span class="sort-icon"></span></th>
                    <th data-col="sparkline">사용량 추이</th>
                    <th data-col="peak_count" class="number">피크수<span class="sort-icon"></span></th>
                    <th data-col="avg_interval" class="number">평균간격<span class="sort-icon"></span></th>
                    <th data-col="interval_cv" class="number">간격CV<span class="sort-icon"></span></th>
                    <th data-col="height_cv" class="number">높이CV<span class="sort-icon"></span></th>
                    <th data-col="acf_max" class="number">ACF최대<span class="sort-icon"></span></th>
                    <th data-col="dominant_period" class="number">FFT주기<span class="sort-icon"></span></th>
                    <th data-col="fft_ratio" class="number">FFT비율<span class="sort-icon"></span></th>
                    <th data-col="periodicity_score" class="number">주기성점수<span class="sort-icon"></span></th>
                </tr>
            </thead>
            <tbody>
'''

    # 테이블 행 생성
    for item in data:
        score = item['periodicity_score']
        score_class = ''
        score_display = '-'

        if score is not None:
            if score >= 30:
                score_class = 'score-high'
            elif score >= 10:
                score_class = 'score-mid'
            else:
                score_class = 'score-low'
            score_display = f'{score:.1f}'

        def format_val(val, decimals=2):
            if val is None:
                return '<span class="na">-</span>'
            return f'{val:.{decimals}f}'

        html += f'''                <tr data-peak-count="{item['peak_count']}"
                    data-drug-type="{item['drug_type']}"
                    data-score="{score if score is not None else ''}"
                    data-search="{item['drug_code']} {item['drug_name']} {item['company']}">
                    <td>{item['drug_code']}</td>
                    <td class="drug-name" title="{item['drug_name']}">{item['drug_name']}</td>
                    <td class="company" title="{item['company']}">{item['company']}</td>
                    <td>{item['drug_type']}</td>
                    <td>{item['sparkline']}</td>
                    <td class="number">{item['peak_count']}</td>
                    <td class="number">{format_val(item['avg_interval'], 1)}</td>
                    <td class="number">{format_val(item['interval_cv'])}</td>
                    <td class="number">{format_val(item['height_cv'])}</td>
                    <td class="number">{format_val(item['acf_max'])}</td>
                    <td class="number">{format_val(item['dominant_period'], 1)}</td>
                    <td class="number">{format_val(item['fft_ratio'])}</td>
                    <td class="number"><span class="{score_class}">{score_display}</span></td>
                </tr>
'''

    html += '''            </tbody>
        </table>

        <div class="legend">
            <h3>지표 설명</h3>
            <div class="legend-item"><strong>피크수:</strong> 사용량 > 0인 달의 개수</div>
            <div class="legend-item"><strong>평균간격:</strong> 피크 간 평균 간격 (개월)</div>
            <div class="legend-item"><strong>간격CV:</strong> 피크 간격의 변동계수 (낮을수록 규칙적)</div>
            <div class="legend-item"><strong>높이CV:</strong> 피크 높이의 변동계수 (낮을수록 같은 환자일 가능성)</div>
            <div class="legend-item"><strong>ACF최대:</strong> 자기상관 최대값 (lag 2~6, 높을수록 주기적)</div>
            <div class="legend-item"><strong>FFT주기:</strong> 푸리에 변환으로 탐지된 지배적 주기 (개월)</div>
            <div class="legend-item"><strong>FFT비율:</strong> 지배적 주파수의 파워 비율 (높을수록 명확한 주기)</div>
            <div class="legend-item"><strong>주기성점수:</strong> 종합 점수 = 100 × ACF × (1/(1+간격CV)) × (1/(1+높이CV))</div>
        </div>
    </div>

    <script>
        const table = document.getElementById('dataTable');
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const headers = table.querySelectorAll('th');

        let currentSort = { col: null, asc: true };

        // 정렬 함수
        function sortTable(col) {
            const isNumeric = ['peak_count', 'avg_interval', 'interval_cv', 'height_cv',
                              'acf_max', 'dominant_period', 'fft_ratio', 'periodicity_score'].includes(col);

            if (currentSort.col === col) {
                currentSort.asc = !currentSort.asc;
            } else {
                currentSort.col = col;
                currentSort.asc = true;
            }

            // 헤더 스타일 업데이트
            headers.forEach(h => {
                h.classList.remove('sorted-asc', 'sorted-desc');
                if (h.dataset.col === col) {
                    h.classList.add(currentSort.asc ? 'sorted-asc' : 'sorted-desc');
                }
            });

            const colIndex = Array.from(headers).findIndex(h => h.dataset.col === col);

            rows.sort((a, b) => {
                let aVal = a.cells[colIndex].textContent.trim();
                let bVal = b.cells[colIndex].textContent.trim();

                if (aVal === '-') aVal = isNumeric ? (currentSort.asc ? Infinity : -Infinity) : '';
                if (bVal === '-') bVal = isNumeric ? (currentSort.asc ? Infinity : -Infinity) : '';

                if (isNumeric) {
                    aVal = parseFloat(aVal) || 0;
                    bVal = parseFloat(bVal) || 0;
                    return currentSort.asc ? aVal - bVal : bVal - aVal;
                } else {
                    return currentSort.asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
                }
            });

            rows.forEach(row => tbody.appendChild(row));
        }

        // 헤더 클릭 이벤트
        headers.forEach(th => {
            if (th.dataset.col && th.dataset.col !== 'sparkline') {
                th.addEventListener('click', () => sortTable(th.dataset.col));
            }
        });

        // 필터 함수
        function applyFilters() {
            const search = document.getElementById('search').value.toLowerCase();
            const minPeaks = parseInt(document.getElementById('minPeaks').value) || 0;
            const drugType = document.getElementById('drugType').value;
            const scoreFilter = document.getElementById('scoreFilter').value;

            let filteredCount = 0;
            let highCount = 0;
            let midCount = 0;
            let lowCount = 0;

            rows.forEach(row => {
                const peakCount = parseInt(row.dataset.peakCount) || 0;
                const rowDrugType = row.dataset.drugType;
                const score = row.dataset.score ? parseFloat(row.dataset.score) : null;
                const searchText = row.dataset.search.toLowerCase();

                let show = true;

                // 검색 필터
                if (search && !searchText.includes(search)) show = false;

                // 피크 수 필터
                if (peakCount < minPeaks) show = false;

                // 약품유형 필터
                if (drugType && rowDrugType !== drugType) show = false;

                // 점수 필터
                if (scoreFilter) {
                    if (score === null) {
                        show = false;
                    } else if (scoreFilter === 'high' && score < 30) {
                        show = false;
                    } else if (scoreFilter === 'mid' && (score < 10 || score >= 30)) {
                        show = false;
                    } else if (scoreFilter === 'low' && score >= 10) {
                        show = false;
                    }
                }

                row.classList.toggle('hidden', !show);

                if (show) {
                    filteredCount++;
                    if (score !== null) {
                        if (score >= 30) highCount++;
                        else if (score >= 10) midCount++;
                        else lowCount++;
                    }
                }
            });

            document.getElementById('filteredCount').textContent = filteredCount;
            document.getElementById('highScoreCount').textContent = highCount;
            document.getElementById('midScoreCount').textContent = midCount;
            document.getElementById('lowScoreCount').textContent = lowCount;
        }

        // 필터 이벤트 바인딩
        document.getElementById('search').addEventListener('input', applyFilters);
        document.getElementById('minPeaks').addEventListener('change', applyFilters);
        document.getElementById('drugType').addEventListener('change', applyFilters);
        document.getElementById('scoreFilter').addEventListener('change', applyFilters);

        // 초기화
        document.getElementById('totalCount').textContent = rows.length;
        applyFilters();

        // 기본 정렬: 주기성 점수 내림차순
        sortTable('periodicity_score');
        sortTable('periodicity_score'); // 두 번 호출해서 내림차순으로
    </script>
</body>
</html>
'''

    return html

def main():
    print("데이터 로드 중...")
    rows = load_data()
    print(f"총 {len(rows)}개 약품 로드됨")

    print("주기성 지표 계산 중...")
    data = []

    for row in rows:
        drug_code, drug_name, company, drug_type, usage_json, current_stock = row

        try:
            usage_list = json.loads(usage_json) if usage_json else []
        except:
            usage_list = []

        if not usage_list:
            continue

        metrics = calculate_periodicity_score(usage_list)

        data.append({
            'drug_code': drug_code,
            'drug_name': drug_name,
            'company': company or '',
            'drug_type': drug_type or '',
            'sparkline': generate_sparkline_svg(usage_list),
            'current_stock': current_stock,
            **metrics
        })

    print(f"{len(data)}개 약품 분석 완료")

    # HTML 생성
    html = generate_html_report(data)

    # 파일 저장
    os.makedirs('periodicity_reports', exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filepath = f'periodicity_reports/periodicity_test_{timestamp}.html'

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n보고서 생성 완료: {filepath}")

    # 브라우저에서 열기
    import webbrowser
    webbrowser.open(f'file://{os.path.abspath(filepath)}')

if __name__ == '__main__':
    main()
