import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from datetime import datetime
import json
import inventory_db
import checked_items_db

def calculate_custom_ma(timeseries, n_months):
    """
    N개월 이동평균 계산

    Args:
        timeseries: 월별 데이터 리스트
        n_months: 이동평균 개월 수

    Returns:
        이동평균 리스트 (앞부분은 None)
    """
    ma_list = []
    for i in range(len(timeseries)):
        if i < n_months - 1:
            ma_list.append(None)
        else:
            window = timeseries[i - n_months + 1 : i + 1]
            ma_list.append(sum(window) / n_months)
    return ma_list

def create_sparkline_svg(timeseries_data, ma_data, ma_months):
    """
    경량 SVG 스파크라인 생성 (검정 점선 + 파란색 N-MA)
    """
    if not timeseries_data or all(v == 0 for v in timeseries_data):
        return '<svg width="120" height="40"></svg>'

    width = 120
    height = 40
    padding = 2

    # 데이터 정규화
    all_values = [v for v in timeseries_data if v > 0]
    if not all_values:
        return '<svg width="120" height="40"></svg>'

    max_val = max(all_values)
    min_val = min(all_values)
    value_range = max_val - min_val if max_val != min_val else 1

    def scale_y(value):
        """값을 SVG 좌표로 변환 (위아래 반전)"""
        normalized = (value - min_val) / value_range
        return height - padding - (normalized * (height - 2 * padding))

    def scale_x(index, total):
        """인덱스를 X 좌표로 변환"""
        return padding + (index / (total - 1)) * (width - 2 * padding) if total > 1 else width / 2

    # 실제 값 라인 (검정 점선)
    points = []
    for i, val in enumerate(timeseries_data):
        x = scale_x(i, len(timeseries_data))
        y = scale_y(val)
        points.append(f"{x:.2f},{y:.2f}")

    actual_line = f'<polyline points="{" ".join(points)}" fill="none" stroke="black" stroke-width="1" stroke-dasharray="2,2" />'

    # N개월 이동평균 라인 (파란색 실선)
    ma_line = ''
    if ma_data and any(v is not None for v in ma_data):
        ma_points = []
        for i, val in enumerate(ma_data):
            if val is not None:
                x = scale_x(i, len(ma_data))
                y = scale_y(val)
                ma_points.append(f"{x:.2f},{y:.2f}")

        if ma_points:
            ma_line = f'<polyline points="{" ".join(ma_points)}" fill="none" stroke="#4facfe" stroke-width="2" />'

    svg = f'<svg width="{width}" height="{height}" style="display:block;">{actual_line}{ma_line}</svg>'
    return svg

def create_chart_data_json(months, timeseries_data, ma_data, avg, drug_name, drug_code, ma_months, stock=0, runway='N/A'):
    """
    인라인 차트용 데이터를 JSON으로 변환
    """
    # numpy/pandas 타입을 Python native 타입으로 변환
    def convert_to_native(val):
        if hasattr(val, 'item'):  # numpy/pandas scalar
            return val.item()
        return val

    return json.dumps({
        'months': months,
        'timeseries': [convert_to_native(v) for v in timeseries_data],
        'ma': [convert_to_native(v) if v is not None else None for v in ma_data],
        'avg': convert_to_native(avg),
        'drug_name': str(drug_name),
        'drug_code': str(drug_code),
        'ma_months': ma_months,
        'stock': convert_to_native(stock),
        'latest_ma': convert_to_native(avg),
        'runway': runway
    }, ensure_ascii=False)

def generate_html_report(df, months, mode='dispense', ma_months=3):
    """
    DataFrame을 HTML 보고서로 생성 (Single MA 버전)
    months: 월 리스트 (예: ['2025-01', '2025-02', ...])
    mode: 'dispense' (전문약) 또는 'sale' (일반약)
    ma_months: 이동평균 개월 수
    """

    # 모드에 따른 제목 설정
    mode_titles = {
        'dispense': f'전문약 재고 관리 보고서 ({ma_months}개월 이동평균)',
        'sale': f'일반약 재고 관리 보고서 ({ma_months}개월 이동평균)'
    }
    report_title = mode_titles.get(mode, f'약품 재고 관리 보고서 ({ma_months}개월 이동평균)')

    # HTML 템플릿 시작
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{report_title}</title>
        <style>
            body {{
                font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, sans-serif;
                margin: 0;
                padding: 20px;
                background: #f5f5f5;
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
                font-size: 2.5em;
            }}
            .date {{
                text-align: left;
                color: #718096;
                margin-bottom: 10px;
            }}
            .summary-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }}
            .summary-card {{
                background: #f5f5f5;
                color: white;
                padding: 25px;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }}
            .summary-card h3 {{
                margin: 0 0 10px 0;
                font-size: 1em;
                opacity: 0.9;
            }}
            .summary-card .value {{
                font-size: 2em;
                font-weight: bold;
            }}
            .table-container {{
                margin: 30px 0;
                overflow-x: auto;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 14px;
            }}
            th {{
                background: #4a5568;
                color: white;
                padding: 12px;
                text-align: left;
                position: sticky;
                top: 0;
            }}
            th.runway-header {{
                background: #5a6570;
            }}
            td {{
                padding: 10px 12px;
                border-bottom: 1px solid #e2e8f0;
            }}
            td.runway-cell {{
                background: #f5f5f5;
            }}
            tr:hover {{
                background: rgba(247, 250, 252, 0.8);
            }}
            tr:hover td.runway-cell {{
                background: rgba(245, 245, 245, 0.9);
            }}
            .warning {{
                background: rgba(255, 245, 245, 0.7);
                color: #c53030;
            }}
            .warning td.runway-cell {{
                background: rgba(245, 245, 245, 0.9);
            }}
            .good {{
                background: #f0fff4;
                color: #22543d;
            }}
            .search-box {{
                margin: 20px 0;
                padding: 12px;
                width: 100%;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                font-size: 16px;
            }}
            .chart-container {{
                margin: 30px 0;
                padding: 20px;
                background: #f7fafc;
                border-radius: 10px;
            }}
            .nav-btn {{
                background: #4a5568;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
                transition: background 0.3s;
            }}
            .nav-btn:hover {{
                background: #2d3748;
            }}
            .nav-btn:disabled {{
                background: #cbd5e0;
                cursor: not-allowed;
            }}
            .modal {{
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                overflow: auto;
                background-color: rgba(0,0,0,0.7);
            }}
            .modal-content {{
                background-color: white;
                margin: 5% auto;
                padding: 30px;
                border-radius: 15px;
                width: 90%;
                max-width: 1200px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.5);
            }}
            .close-btn {{
                color: #aaa;
                float: right;
                font-size: 28px;
                font-weight: bold;
                cursor: pointer;
                line-height: 20px;
            }}
            .close-btn:hover {{
                color: #000;
            }}
            .clickable-row {{
                cursor: pointer;
            }}
            .clickable-row:hover {{
                background: #edf2f7 !important;
            }}
            .toggle-header {{
                cursor: pointer;
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 15px 20px;
                user-select: none;
                background: rgba(255, 255, 255, 0.5);
                border-radius: 10px;
                transition: background 0.3s ease;
            }}
            .toggle-header:hover {{
                background: rgba(230, 230, 250, 0.7);
            }}
            .toggle-icon {{
                font-size: 1.8em;
                font-weight: bold;
                transition: transform 0.3s ease;
                display: inline-block;
                color: #6b7280;
                min-width: 30px;
                text-align: center;
            }}
            .toggle-icon.collapsed {{
                transform: rotate(-90deg);
            }}
            .toggle-content {{
                max-height: 10000px;
                overflow: hidden;
                transition: max-height 0.3s ease, opacity 0.3s ease;
                opacity: 1;
            }}
            .toggle-content.collapsed {{
                max-height: 0;
                opacity: 0;
            }}
            .checked-row {{
                background: rgba(200, 200, 200, 0.3) !important;
                opacity: 0.6;
                color: #718096;
            }}
            .checked-row td {{
                color: #718096 !important;
            }}
            /* 인라인 차트용 클릭 가능 행 스타일 */
            .tab-clickable-row {{
                cursor: pointer;
                transition: background-color 0.2s;
            }}
            .tab-clickable-row:hover {{
                background-color: rgba(79, 172, 254, 0.1) !important;
            }}
            .tab-clickable-row.chart-expanded {{
                background-color: rgba(79, 172, 254, 0.15) !important;
                border-left: 3px solid #4facfe;
            }}
            .inline-chart-row {{
                background: #f8fafc;
            }}
            .inline-chart-row:hover {{
                background: #f8fafc !important;
            }}
            .memo-btn {{
                background: transparent;
                border: 2px solid #cbd5e0;
                padding: 4px 8px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                transition: all 0.2s;
                color: #718096;
            }}
            .memo-btn:hover {{
                border-color: #a0aec0;
                color: #4a5568;
            }}
            .memo-btn.has-memo {{
                border-color: #f6ad55;
                color: #f6ad55;
            }}
            .memo-btn.has-memo:hover {{
                border-color: #ed8936;
                color: #ed8936;
            }}
            .checkbox-memo-container {{
                display: flex;
                align-items: center;
                gap: 8px;
            }}

            /* 책갈피 사이드바 스타일 */
            .bookmark-sidebar {{
                position: fixed;
                right: 0;
                top: 50%;
                transform: translateY(-50%);
                z-index: 999;
                display: flex;
                flex-direction: column;
                gap: 15px;
                padding-right: 0;
            }}
            .bookmark-item {{
                position: relative;
                right: -140px;
                padding: 15px 20px;
                border-radius: 10px 0 0 10px;
                cursor: pointer;
                transition: right 0.3s ease, box-shadow 0.3s ease;
                box-shadow: -4px 4px 12px rgba(0, 0, 0, 0.3);
                min-width: 180px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                display: flex;
                flex-direction: column;
                gap: 5px;
                user-select: none;
            }}
            .bookmark-item:hover {{
                right: 0;
                box-shadow: -8px 8px 20px rgba(0, 0, 0, 0.4);
            }}
            .bookmark-item .bookmark-icon {{
                font-size: 1.3em;
                margin-bottom: 3px;
            }}
            .bookmark-item .bookmark-title {{
                font-size: 1.1em;
            }}
            .bookmark-item .bookmark-count {{
                font-size: 1.8em;
                font-weight: bold;
                text-align: center;
                margin-top: 5px;
            }}
            .bookmark-urgent {{
                background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%);
            }}
            .bookmark-low {{
                background: linear-gradient(135deg, #eab308 0%, #ca8a04 100%);
            }}
            .bookmark-high {{
                background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
            }}
            .bookmark-dead {{
                background: linear-gradient(135deg, #94a3b8 0%, #64748b 100%);
            }}

            /* 카테고리 모달 스타일 */
            .category-modal {{
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                overflow: auto;
                background-color: rgba(0,0,0,0.7);
                animation: fadeIn 0.3s ease;
            }}
            @keyframes fadeIn {{
                from {{ opacity: 0; }}
                to {{ opacity: 1; }}
            }}
            .category-modal-content {{
                background-color: white;
                margin: 3% auto;
                padding: 40px;
                border-radius: 20px;
                width: 90%;
                max-width: 1400px;
                max-height: 85vh;
                overflow-y: auto;
                box-shadow: 0 20px 60px rgba(0,0,0,0.5);
                animation: slideIn 0.3s ease;
            }}
            @keyframes slideIn {{
                from {{
                    transform: translateY(-50px);
                    opacity: 0;
                }}
                to {{
                    transform: translateY(0);
                    opacity: 1;
                }}
            }}
            .category-modal-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 30px;
                padding-bottom: 20px;
                border-bottom: 3px solid #e5e7eb;
            }}
            .category-modal-close {{
                color: #aaa;
                font-size: 36px;
                font-weight: bold;
                cursor: pointer;
                line-height: 30px;
                transition: color 0.2s;
            }}
            .category-modal-close:hover {{
                color: #000;
            }}
        </style>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    </head>
    <body>
        <div class="container">
            <h1>📊 {report_title}</h1>
            <div class="date">생성일: {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}</div>
            <div class="date">데이터 기간: {months[0][:4]}년 {months[0][5:]}월 ~ {months[-1][:4]}년 {months[-1][5:]}월 (총 {len(months)}개월)</div>
    """

    # 특수 케이스 약품 분류
    urgent_drugs, dead_stock_drugs = classify_drugs_by_special_cases(df, ma_months)

    # 런웨이 분석 차트 생성 + 부족/충분 약품 DataFrame
    runtime_analysis_low, runtime_analysis_high, low_count, high_count, low_drugs_df, high_drugs_df = analyze_runway(df, months, ma_months)

    # 전체 약품 수
    total_count = len(df)
    urgent_count = len(urgent_drugs) if not urgent_drugs.empty else 0
    dead_count = len(dead_stock_drugs) if not dead_stock_drugs.empty else 0

    # 통합 인디케이터 생성
    html_content += f"""
        <!-- 통합 재고 현황 인디케이터 -->
        <div style="margin: 30px 0; padding: 25px; background: white; border-radius: 15px; border: 2px solid #e5e7eb;">
            <h2 style="margin: 0 0 15px 0; color: #2d3748;">📊 재고 현황 분포</h2>
            <div style="display: flex; height: 40px; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.15); position: relative;">
                <div style="background: #dc2626; flex: {urgent_count}; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 13px; position: relative;" title="긴급: {urgent_count}개 ({urgent_count/total_count*100:.1f}%)">
                    {urgent_count if urgent_count > 0 else ''}
                </div>
                <div style="background: #eab308; flex: {low_count}; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 13px; position: relative;" title="부족: {low_count}개 ({low_count/total_count*100:.1f}%)">
                    {low_count if low_count > 0 else ''}
                </div>
                <div style="background: #22c55e; flex: {high_count}; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 13px; position: relative;" title="충분: {high_count}개 ({high_count/total_count*100:.1f}%)">
                    {high_count if high_count > 0 else ''}
                </div>
                <div style="background: #94a3b8; flex: {dead_count}; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 13px; position: relative;" title="악성재고: {dead_count}개 ({dead_count/total_count*100:.1f}%)">
                    {dead_count if dead_count > 0 else ''}
                </div>
            </div>
            <div style="display: flex; justify-content: space-between; margin-top: 15px; font-size: 13px; color: #4a5568;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="display: inline-block; width: 12px; height: 12px; background: #dc2626; border-radius: 2px;"></span>
                    <span>긴급: {urgent_count}개 ({urgent_count/total_count*100:.1f}%)</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="display: inline-block; width: 12px; height: 12px; background: #eab308; border-radius: 2px;"></span>
                    <span>부족: {low_count}개 ({low_count/total_count*100:.1f}%)</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="display: inline-block; width: 12px; height: 12px; background: #22c55e; border-radius: 2px;"></span>
                    <span>충분: {high_count}개 ({high_count/total_count*100:.1f}%)</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="display: inline-block; width: 12px; height: 12px; background: #94a3b8; border-radius: 2px;"></span>
                    <span>악성재고: {dead_count}개 ({dead_count/total_count*100:.1f}%)</span>
                </div>
            </div>
        </div>

        <!-- 책갈피 사이드바 -->
        <div class="bookmark-sidebar">
            <div class="bookmark-item bookmark-urgent" onclick="openCategoryModal('urgent-modal')">
                <div class="bookmark-icon">🔴</div>
                <div class="bookmark-title">긴급</div>
                <div class="bookmark-count">{urgent_count}</div>
            </div>
            <div class="bookmark-item bookmark-low" onclick="openCategoryModal('low-modal')">
                <div class="bookmark-icon">🟡</div>
                <div class="bookmark-title">부족</div>
                <div class="bookmark-count">{low_count}</div>
            </div>
            <div class="bookmark-item bookmark-high" onclick="openCategoryModal('high-modal')">
                <div class="bookmark-icon">🟢</div>
                <div class="bookmark-title">충분</div>
                <div class="bookmark-count">{high_count}</div>
            </div>
            <div class="bookmark-item bookmark-dead" onclick="openCategoryModal('dead-modal')">
                <div class="bookmark-icon">⚪</div>
                <div class="bookmark-title">악성재고</div>
                <div class="bookmark-count">{dead_count}</div>
            </div>
        </div>
    """

    # 모달 컨테이너 생성
    has_urgent = not urgent_drugs.empty
    has_low_runway = runtime_analysis_low is not None
    has_high_runway = runtime_analysis_high is not None
    has_dead_stock = not dead_stock_drugs.empty

    # 긴급 약품 모달
    if has_urgent:
        urgent_section_html = generate_urgent_drugs_section(urgent_drugs, ma_months, months)
        html_content += f"""
            <!-- 긴급 약품 모달 -->
            <div id="urgent-modal" class="category-modal">
                <div class="category-modal-content">
                    <div class="category-modal-header">
                        <h2 style="margin: 0; color: #dc2626; display: flex; align-items: center; gap: 10px;">
                            <span style="font-size: 1.5em;">🔴</span>
                            <span>긴급: 재고 0인 약품 ({ma_months}개월 내 사용이력 있음)</span>
                        </h2>
                        <span class="category-modal-close" onclick="closeCategoryModal('urgent-modal')">&times;</span>
                    </div>
                    {urgent_section_html}
                </div>
            </div>
        """

    # 재고 부족 약품 모달 (테이블 + 차트 토글)
    if has_low_runway:
        low_section_html = generate_low_stock_section(low_drugs_df, ma_months, months)
        html_content += f"""
            <!-- 재고 부족 약품 모달 -->
            <div id="low-modal" class="category-modal">
                <div class="category-modal-content">
                    <div class="category-modal-header">
                        <h2 style="margin: 0; color: #ca8a04; display: flex; align-items: center; gap: 10px;">
                            <span style="font-size: 1.5em;">🟡</span>
                            <span>재고 부족 약품 (런웨이 3개월 이하)</span>
                        </h2>
                        <div style="display: flex; align-items: center; gap: 15px;">
                            <button id="toggle-view-low" class="nav-btn" onclick="toggleLowView()">📊 막대 그래프 보기</button>
                            <span class="category-modal-close" onclick="closeCategoryModal('low-modal')">&times;</span>
                        </div>
                    </div>
                    <!-- 테이블 뷰 (기본) -->
                    <div id="table-view-low" style="display: block;">
                        {low_section_html}
                    </div>
                    <!-- 차트 뷰 (숨김) -->
                    <div id="chart-view-low" style="display: none;">
                        <div class="chart-container" style="background: white;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                                <div>
                                    <button onclick="changePage('low', -1)" id="prev-low" class="nav-btn">◀ 이전</button>
                                    <span id="page-info-low" style="margin: 0 20px;"></span>
                                    <button onclick="changePage('low', 1)" id="next-low" class="nav-btn">다음 ▶</button>
                                </div>
                            </div>
                            <div id="runway-chart-low"></div>
                        </div>
                    </div>
                </div>
            </div>
            <script>
                {runtime_analysis_low}

                // 부족 탭 뷰 토글
                var lowViewMode = 'table';
                function toggleLowView() {{
                    var tableView = document.getElementById('table-view-low');
                    var chartView = document.getElementById('chart-view-low');
                    var toggleBtn = document.getElementById('toggle-view-low');

                    if (lowViewMode === 'table') {{
                        tableView.style.display = 'none';
                        chartView.style.display = 'block';
                        toggleBtn.textContent = '📋 테이블 보기';
                        lowViewMode = 'chart';
                        // 차트 초기화 (처음 표시될 때)
                        if (typeof updateChartLow === 'function') {{
                            updateChartLow();
                        }}
                    }} else {{
                        tableView.style.display = 'block';
                        chartView.style.display = 'none';
                        toggleBtn.textContent = '📊 막대 그래프 보기';
                        lowViewMode = 'table';
                    }}
                }}
            </script>
        """

    # 재고 충분 약품 모달 (테이블 + 차트 토글)
    if has_high_runway:
        high_section_html = generate_high_stock_section(high_drugs_df, ma_months, months)
        html_content += f"""
            <!-- 재고 충분 약품 모달 -->
            <div id="high-modal" class="category-modal">
                <div class="category-modal-content">
                    <div class="category-modal-header">
                        <h2 style="margin: 0; color: #16a34a; display: flex; align-items: center; gap: 10px;">
                            <span style="font-size: 1.5em;">🟢</span>
                            <span>재고 충분 약품 (런웨이 3개월 초과)</span>
                        </h2>
                        <div style="display: flex; align-items: center; gap: 15px;">
                            <button id="toggle-view-high" class="nav-btn" onclick="toggleHighView()">📊 막대 그래프 보기</button>
                            <span class="category-modal-close" onclick="closeCategoryModal('high-modal')">&times;</span>
                        </div>
                    </div>
                    <!-- 테이블 뷰 (기본) -->
                    <div id="table-view-high" style="display: block;">
                        {high_section_html}
                    </div>
                    <!-- 차트 뷰 (숨김) -->
                    <div id="chart-view-high" style="display: none;">
                        <div class="chart-container" style="background: white;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                                <div>
                                    <button onclick="changePage('high', -1)" id="prev-high" class="nav-btn">◀ 이전</button>
                                    <span id="page-info-high" style="margin: 0 20px;"></span>
                                    <button onclick="changePage('high', 1)" id="next-high" class="nav-btn">다음 ▶</button>
                                </div>
                            </div>
                            <div id="runway-chart-high"></div>
                        </div>
                    </div>
                </div>
            </div>
            <script>
                {runtime_analysis_high}

                // 충분 탭 뷰 토글
                var highViewMode = 'table';
                function toggleHighView() {{
                    var tableView = document.getElementById('table-view-high');
                    var chartView = document.getElementById('chart-view-high');
                    var toggleBtn = document.getElementById('toggle-view-high');

                    if (highViewMode === 'table') {{
                        tableView.style.display = 'none';
                        chartView.style.display = 'block';
                        toggleBtn.textContent = '📋 테이블 보기';
                        highViewMode = 'chart';
                        // 차트 초기화 (처음 표시될 때)
                        if (typeof updateChartHigh === 'function') {{
                            updateChartHigh();
                        }}
                    }} else {{
                        tableView.style.display = 'block';
                        chartView.style.display = 'none';
                        toggleBtn.textContent = '📊 막대 그래프 보기';
                        highViewMode = 'table';
                    }}
                }}
            </script>
        """

    # 악성 재고 모달
    if has_dead_stock:
        dead_stock_section_html = generate_dead_stock_section(dead_stock_drugs, ma_months, months)
        html_content += f"""
            <!-- 악성 재고 모달 -->
            <div id="dead-modal" class="category-modal">
                <div class="category-modal-content">
                    <div class="category-modal-header">
                        <h2 style="margin: 0; color: #475569; display: flex; align-items: center; gap: 10px;">
                            <span style="font-size: 1.5em;">⚪</span>
                            <span>악성 재고 ({ma_months}개월간 미사용 약품)</span>
                        </h2>
                        <span class="category-modal-close" onclick="closeCategoryModal('dead-modal')">&times;</span>
                    </div>
                    {dead_stock_section_html}
                </div>
            </div>
        """

    # N개월 이동평균 계산 및 정렬 준비
    print(f"\n📊 약품 목록을 {ma_months}개월 이동평균 기준으로 정렬 중...")

    # 각 약품의 N개월 이동평균 계산
    ma_values = []
    for _, row in df.iterrows():
        timeseries = row['월별_조제수량_리스트']
        ma = calculate_custom_ma(timeseries, ma_months)

        # 최신 N-MA 값 추출
        latest_ma = None
        for val in reversed(ma):
            if val is not None:
                latest_ma = val
                break

        ma_values.append(latest_ma if latest_ma else 0)

    # DataFrame에 N-MA 컬럼 추가
    df_sorted = df.copy()
    df_sorted['_temp_n_ma'] = ma_values

    # N개월 이동평균 내림차순 정렬
    df_sorted = df_sorted.sort_values('_temp_n_ma', ascending=False)

    # 인덱스 재설정 (중요: 정렬 후 인덱스를 0부터 다시 매김)
    df_sorted = df_sorted.reset_index(drop=True)

    print(f"✅ 정렬 완료: 총 {len(df_sorted)}개 약품")

    # 테이블 생성 (기본 숨김, 검색 시에만 표시)
    html_content += f"""
            <h2>🔍 약품 검색</h2>
            <input type="text" class="search-box" id="searchInput" placeholder="약품명, 제약회사, 약품코드로 검색...">
            <p id="searchHint" style="color: #718096; font-size: 14px; margin: 10px 0 20px 0;">검색어를 입력하면 일치하는 약품이 표시됩니다.</p>

            <div class="table-container" id="searchTableContainer" style="display: none;">
                <table id="dataTable">
                    <thead>
                        <tr>
                            <th>약품명</th>
                            <th>제약회사</th>
                            <th>약품코드</th>
                            <th>재고수량</th>
                            <th>{ma_months}개월 이동평균</th>
                            <th class="runway-header">런웨이</th>
                            <th>트렌드</th>
                        </tr>
                    </thead>
                    <tbody>
    """

    # 데이터 행 추가 + 경량 스파크라인 생성
    for idx, row in df_sorted.iterrows():

        # 경량 SVG 스파크라인 생성
        timeseries = row['월별_조제수량_리스트']

        # N개월 이동평균 계산
        ma = calculate_custom_ma(timeseries, ma_months)
        sparkline_html = create_sparkline_svg(timeseries, ma, ma_months)

        # N개월 이동평균 (최신값)
        latest_ma = None
        for val in reversed(ma):
            if val is not None:
                latest_ma = val
                break

        # 런웨이 계산
        runway_display = "재고만 있음"  # 기본값 통일
        if latest_ma and latest_ma > 0:
            runway_months = row['최종_재고수량'] / latest_ma
            if runway_months >= 1:
                runway_display = f"{runway_months:.2f}개월"
            else:
                runway_days = runway_months * 30.417
                runway_display = f"{runway_days:.2f}일"

        # 런웨이 클래스 결정 (1개월 미만이면 경고)
        runway_class = get_runway_class(runway_display)

        # 인라인 차트용 데이터를 JSON으로 변환
        drug_code = str(row['약품코드'])
        chart_data_json = create_chart_data_json(
            months=months,
            timeseries_data=timeseries,
            ma_data=ma,
            avg=latest_ma if latest_ma else 0,
            drug_name=row['약품명'],
            drug_code=drug_code,
            ma_months=ma_months,
            stock=int(row['최종_재고수량']),
            runway=runway_display
        ).replace("'", "&#39;")

        # 약품명 30자 제한
        drug_name_display = row['약품명'] if row['약품명'] is not None else "정보없음"
        if len(drug_name_display) > 30:
            drug_name_display = drug_name_display[:30] + "..."

        # 제약회사 12자 제한
        company_display = row['제약회사'] if row['제약회사'] is not None else "정보없음"
        if len(company_display) > 12:
            company_display = company_display[:12] + "..."

        html_content += f"""
                        <tr class="{runway_class} clickable-row tab-clickable-row" data-drug-code="{drug_code}"
                            data-chart-data='{chart_data_json}'
                            onclick="toggleInlineChart(this, '{drug_code}')">
                            <td>{drug_name_display}</td>
                            <td>{company_display}</td>
                            <td>{drug_code}</td>
                            <td>{row['최종_재고수량']:,.0f}</td>
                            <td>{"N/A" if latest_ma is None else f"{latest_ma:.2f}"}</td>
                            <td class="runway-cell">{runway_display}</td>
                            <td>{sparkline_html}</td>
                        </tr>
        """

    # HTML 마무리
    html_content += """
                    </tbody>
                </table>
            </div>
        </div>

        <script>
            // 카테고리 모달 열기
            function openCategoryModal(modalId) {
                const modal = document.getElementById(modalId);
                if (modal) {
                    modal.style.display = 'block';
                    document.body.style.overflow = 'hidden'; // 배경 스크롤 방지
                }
            }

            // 카테고리 모달 닫기
            function closeCategoryModal(modalId) {
                const modal = document.getElementById(modalId);
                if (modal) {
                    modal.style.display = 'none';
                    document.body.style.overflow = 'auto'; // 배경 스크롤 복원
                }
            }

            // ESC 키로 모달 닫기
            document.addEventListener('keydown', function(event) {
                if (event.key === 'Escape') {
                    const modals = document.querySelectorAll('.category-modal');
                    modals.forEach(modal => {
                        if (modal.style.display === 'block') {
                            modal.style.display = 'none';
                        }
                    });
                    document.body.style.overflow = 'auto';
                }
            });

            // 모달 배경 클릭 시 닫기
            window.addEventListener('click', function(event) {
                if (event.target.classList.contains('category-modal')) {
                    event.target.style.display = 'none';
                    document.body.style.overflow = 'auto';
                }
            });

            // 토글 기능 (모달 내부용)
            function toggleSection(sectionId) {
                const section = document.getElementById(sectionId);
                const icon = document.getElementById('toggle-icon-' + sectionId);

                if (section && icon) {
                    section.classList.toggle('collapsed');
                    icon.classList.toggle('collapsed');
                }
            }

            // 긴급 약품 체크박스 핸들러
            function handleUrgentCheckbox(checkbox) {
                const drugCode = checkbox.getAttribute('data-drug-code');
                const isChecked = checkbox.checked;
                const row = checkbox.closest('tr');

                // 체크 상태에 따라 스타일 적용
                if (isChecked) {
                    row.classList.add('checked-row');
                } else {
                    row.classList.remove('checked-row');
                }

                // 서버에 체크 상태 저장
                fetch('/api/toggle_checked_item', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        drug_code: drugCode,
                        checked: isChecked
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        console.log('체크 상태 업데이트 완료:', drugCode);
                        // 테이블 정렬
                        sortUrgentTable();
                    } else {
                        console.error('체크 상태 업데이트 실패:', data.message);
                    }
                })
                .catch(error => {
                    console.error('API 요청 실패:', error);
                });
            }

            // 긴급 약품 테이블 정렬 (체크된 항목을 하단으로)
            function sortUrgentTable() {
                const table = document.getElementById('urgent-drugs-table');
                if (!table) return;

                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr.urgent-row'));

                // 체크 여부에 따라 정렬
                rows.sort((a, b) => {
                    const aChecked = a.classList.contains('checked-row');
                    const bChecked = b.classList.contains('checked-row');

                    if (aChecked && !bChecked) return 1;  // a를 뒤로
                    if (!aChecked && bChecked) return -1; // b를 뒤로
                    return 0; // 동일 그룹 내에서는 순서 유지
                });

                // 테이블 재구성
                rows.forEach(row => tbody.appendChild(row));
            }

            // 페이지 로드 시 테이블 정렬
            window.addEventListener('DOMContentLoaded', function() {
                sortUrgentTable();
                sortLowTable();
                sortHighTable();
                sortDeadTable();
            });

            // 부족 약품 체크박스 핸들러
            function handleLowCheckbox(checkbox) {
                const drugCode = checkbox.getAttribute('data-drug-code');
                const isChecked = checkbox.checked;
                const row = checkbox.closest('tr');

                if (isChecked) {
                    row.classList.add('checked-row');
                } else {
                    row.classList.remove('checked-row');
                }

                fetch('/api/toggle_checked_item', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        drug_code: drugCode,
                        checked: isChecked
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        sortLowTable();
                        // 같은 약품이 다른 탭에도 있을 수 있으므로 모든 탭 동기화
                        syncCheckboxState(drugCode, isChecked);
                    }
                })
                .catch(error => console.error('API 요청 실패:', error));
            }

            // 부족 약품 테이블 정렬
            function sortLowTable() {
                const table = document.getElementById('low-drugs-table');
                if (!table) return;

                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr.low-row'));

                rows.sort((a, b) => {
                    const aChecked = a.classList.contains('checked-row');
                    const bChecked = b.classList.contains('checked-row');
                    if (aChecked && !bChecked) return 1;
                    if (!aChecked && bChecked) return -1;
                    return 0;
                });

                rows.forEach(row => tbody.appendChild(row));
            }

            // 충분 약품 체크박스 핸들러
            function handleHighCheckbox(checkbox) {
                const drugCode = checkbox.getAttribute('data-drug-code');
                const isChecked = checkbox.checked;
                const row = checkbox.closest('tr');

                if (isChecked) {
                    row.classList.add('checked-row');
                } else {
                    row.classList.remove('checked-row');
                }

                fetch('/api/toggle_checked_item', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        drug_code: drugCode,
                        checked: isChecked
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        sortHighTable();
                        syncCheckboxState(drugCode, isChecked);
                    }
                })
                .catch(error => console.error('API 요청 실패:', error));
            }

            // 충분 약품 테이블 정렬
            function sortHighTable() {
                const table = document.getElementById('high-drugs-table');
                if (!table) return;

                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr.high-row'));

                rows.sort((a, b) => {
                    const aChecked = a.classList.contains('checked-row');
                    const bChecked = b.classList.contains('checked-row');
                    if (aChecked && !bChecked) return 1;
                    if (!aChecked && bChecked) return -1;
                    return 0;
                });

                rows.forEach(row => tbody.appendChild(row));
            }

            // 악성재고 약품 체크박스 핸들러
            function handleDeadCheckbox(checkbox) {
                const drugCode = checkbox.getAttribute('data-drug-code');
                const isChecked = checkbox.checked;
                const row = checkbox.closest('tr');

                if (isChecked) {
                    row.classList.add('checked-row');
                } else {
                    row.classList.remove('checked-row');
                }

                fetch('/api/toggle_checked_item', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        drug_code: drugCode,
                        checked: isChecked
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        sortDeadTable();
                        syncCheckboxState(drugCode, isChecked);
                    }
                })
                .catch(error => console.error('API 요청 실패:', error));
            }

            // 모든 탭에서 같은 약품의 체크 상태 동기화
            function syncCheckboxState(drugCode, isChecked) {
                // 모든 체크박스에서 같은 약품코드를 가진 것들 찾기
                const allCheckboxes = document.querySelectorAll(`input[type="checkbox"][data-drug-code="${drugCode}"]`);
                allCheckboxes.forEach(cb => {
                    if (cb.checked !== isChecked) {
                        cb.checked = isChecked;
                        const row = cb.closest('tr');
                        if (row) {
                            if (isChecked) {
                                row.classList.add('checked-row');
                            } else {
                                row.classList.remove('checked-row');
                            }
                        }
                    }
                });
            }

            // 악성재고 약품 테이블 정렬
            function sortDeadTable() {
                const table = document.getElementById('dead-drugs-table');
                if (!table) return;

                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr.dead-row'));

                rows.sort((a, b) => {
                    const aChecked = a.classList.contains('checked-row');
                    const bChecked = b.classList.contains('checked-row');
                    if (aChecked && !bChecked) return 1;
                    if (!aChecked && bChecked) return -1;
                    return 0;
                });

                rows.forEach(row => tbody.appendChild(row));
            }

            // 인라인 차트 닫기
            function closeInlineChart(drugCode) {
                event.stopPropagation();
                const chartRow = document.querySelector('.inline-chart-row');
                if (chartRow) chartRow.remove();
                const expandedRow = document.querySelector('tr[data-drug-code="' + drugCode + '"].chart-expanded');
                if (expandedRow) expandedRow.classList.remove('chart-expanded');
            }

            // 인라인 차트 토글 (탭 내 테이블용)
            var inlineChartCache = {};

            function toggleInlineChart(row, drugCode) {
                const existingChartRow = row.nextElementSibling;

                // 이미 차트가 열려있으면 닫기
                if (existingChartRow && existingChartRow.classList.contains('inline-chart-row')) {
                    existingChartRow.remove();
                    row.classList.remove('chart-expanded');
                    return;
                }

                // 다른 열린 차트들 닫기
                document.querySelectorAll('.inline-chart-row').forEach(el => el.remove());
                document.querySelectorAll('.chart-expanded').forEach(el => el.classList.remove('chart-expanded'));

                // 차트 데이터 가져오기
                const chartDataStr = row.getAttribute('data-chart-data');
                if (!chartDataStr) {
                    console.error('차트 데이터가 없습니다:', drugCode);
                    return;
                }

                const chartData = JSON.parse(chartDataStr);
                const colSpan = row.cells.length;

                // 차트 행 생성
                const chartRow = document.createElement('tr');
                chartRow.className = 'inline-chart-row';
                chartRow.innerHTML = `
                    <td colspan="${colSpan}" style="padding: 20px; background: #f8fafc; border-left: 4px solid #4facfe;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                            <h4 style="margin: 0; color: #2d3748;">${chartData.drug_name} (${chartData.drug_code}) 상세 트렌드</h4>
                            <button onclick="closeInlineChart('${drugCode}')"
                                    style="background: none; border: none; font-size: 20px; cursor: pointer; color: #718096;">&times;</button>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 15px;">
                            <div style="background: #e0e0e0; padding: 12px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 12px; color: #666;">재고수량</div>
                                <div style="font-size: 18px; font-weight: bold;">${chartData.stock.toLocaleString()}개</div>
                            </div>
                            <div style="background: #e0e0e0; padding: 12px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 12px; opacity: 0.9;">${chartData.ma_months}개월 이동평균</div>
                                <div style="font-size: 18px; font-weight: bold;">${chartData.latest_ma !== null ? chartData.latest_ma.toFixed(1) : 'N/A'}개</div>
                            </div>
                            <div style="background: #e0e0e0; padding: 12px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 12px; opacity: 0.9;">런웨이</div>
                                <div style="font-size: 18px; font-weight: bold;">${chartData.runway}</div>
                            </div>
                        </div>
                        <div id="inline-chart-${drugCode}" style="width: 100%; height: 350px;"></div>
                    </td>
                `;

                row.after(chartRow);
                row.classList.add('chart-expanded');

                // Plotly 차트 생성
                renderInlineChart(drugCode, chartData);
            }

            function renderInlineChart(drugCode, chartData) {
                const chartContainer = document.getElementById('inline-chart-' + drugCode);
                if (!chartContainer) return;

                const maClean = chartData.ma;

                // 최대값 찾기
                const maxValue = Math.max(...chartData.timeseries);
                const maxIndex = chartData.timeseries.indexOf(maxValue);
                const maxMonth = chartData.months[maxIndex];

                const traces = [
                    {
                        x: chartData.months,
                        y: chartData.timeseries,
                        mode: 'lines+markers',
                        name: '실제 조제수량',
                        line: {color: 'black', width: 2, dash: 'dot'},
                        marker: {size: 6, color: 'black'},
                        hovertemplate: '실제 조제수량: %{y:,.0f}개<extra></extra>'
                    },
                    {
                        x: chartData.months,
                        y: maClean,
                        mode: 'lines',
                        name: chartData.ma_months + '개월 이동평균',
                        line: {color: '#4facfe', width: 3},
                        hovertemplate: chartData.ma_months + '개월 이동평균: %{y:,.2f}개<extra></extra>'
                    }
                ];

                // 겨울철 배경 영역 생성
                const winterShapes = [];
                function isWinterMonth(month) {
                    const monthNum = parseInt(month.split('-')[1]);
                    return monthNum === 10 || monthNum === 11 || monthNum === 12 || monthNum === 1 || monthNum === 2;
                }

                let winterStart = null;
                for (let i = 0; i < chartData.months.length; i++) {
                    const isWinter = isWinterMonth(chartData.months[i]);
                    if (isWinter && winterStart === null) {
                        winterStart = i;
                    } else if (!isWinter && winterStart !== null) {
                        winterShapes.push({
                            type: 'rect', xref: 'x', yref: 'paper',
                            x0: chartData.months[winterStart], x1: chartData.months[i - 1],
                            y0: 0, y1: 1,
                            fillcolor: 'rgba(135, 206, 250, 0.2)', line: {width: 0}, layer: 'below'
                        });
                        winterStart = null;
                    }
                }
                if (winterStart !== null) {
                    winterShapes.push({
                        type: 'rect', xref: 'x', yref: 'paper',
                        x0: chartData.months[winterStart], x1: chartData.months[chartData.months.length - 1],
                        y0: 0, y1: 1,
                        fillcolor: 'rgba(135, 206, 250, 0.2)', line: {width: 0}, layer: 'below'
                    });
                }

                const layout = {
                    xaxis: { title: '월', type: 'category', showgrid: true, gridcolor: '#e2e8f0' },
                    yaxis: { title: '조제수량', showgrid: true, gridcolor: '#e2e8f0' },
                    height: 350,
                    margin: { t: 30, b: 50, l: 60, r: 30 },
                    hovermode: 'x unified',
                    plot_bgcolor: 'white',
                    paper_bgcolor: '#f8fafc',
                    font: {size: 11},
                    shapes: winterShapes,
                    annotations: maxValue > 0 ? [{
                        x: maxMonth, y: maxValue,
                        text: '최대: ' + maxValue.toFixed(0),
                        showarrow: true, arrowhead: 2, arrowsize: 1, arrowwidth: 2, arrowcolor: 'red',
                        ax: 0, ay: -30,
                        bgcolor: 'rgba(255,255,255,0.9)', bordercolor: 'red', borderwidth: 1, borderpad: 3,
                        font: {color: 'red', size: 10, weight: 'bold'}
                    }] : []
                };

                Plotly.newPlot(chartContainer, traces, layout, {displayModeBar: false, responsive: true});
            }

            // 범용 메모 모달 열기 (카테고리 없이 약품코드만 사용)
            function openMemoModalGeneric(drugCode) {
                const modal = document.getElementById('memo-modal-generic');
                const drugCodeElement = document.getElementById('memo-drug-code-generic');
                const textarea = document.getElementById('memo-textarea-generic');

                // 전역 메모 데이터에서 가져오기
                const memo = typeof drugMemos !== 'undefined' ? (drugMemos[drugCode] || '') : '';

                drugCodeElement.textContent = drugCode;
                textarea.value = memo;
                textarea.setAttribute('data-drug-code', drugCode);

                modal.style.display = 'block';
            }

            // 범용 메모 모달 닫기
            function closeMemoModalGeneric() {
                const modal = document.getElementById('memo-modal-generic');
                modal.style.display = 'none';
            }

            // 범용 메모 저장 (카테고리 없이)
            function saveMemoGeneric() {
                const textarea = document.getElementById('memo-textarea-generic');
                const drugCode = textarea.getAttribute('data-drug-code');
                const memo = textarea.value;

                fetch('/api/update_memo', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        drug_code: drugCode,
                        memo: memo
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        // 전역 메모 데이터 업데이트
                        if (typeof drugMemos !== 'undefined') {
                            if (memo) {
                                drugMemos[drugCode] = memo;
                            } else {
                                delete drugMemos[drugCode];
                            }
                        }

                        // 모든 탭에서 해당 약품의 메모 버튼 스타일 업데이트
                        syncMemoButtonState(drugCode, memo);

                        closeMemoModalGeneric();
                    } else {
                        alert('메모 저장에 실패했습니다.');
                    }
                })
                .catch(error => {
                    console.error('API 요청 실패:', error);
                    alert('메모 저장에 실패했습니다.');
                });
            }

            // 모든 탭에서 메모 버튼 상태 동기화
            function syncMemoButtonState(drugCode, memo) {
                const allMemoBtns = document.querySelectorAll(`button.memo-btn[data-drug-code="${drugCode}"]`);
                allMemoBtns.forEach(btn => {
                    if (memo) {
                        btn.classList.add('has-memo');
                        btn.title = memo.length > 50 ? memo.substring(0, 50) + '...' : memo;
                    } else {
                        btn.classList.remove('has-memo');
                        btn.title = '메모 추가';
                    }
                });
            }

            // 메모 모달 열기 (긴급 탭용 - 기존)
            function openMemoModal(drugCode) {
                const modal = document.getElementById('memo-modal');
                const drugCodeElement = document.getElementById('memo-drug-code');
                const textarea = document.getElementById('memo-textarea');

                drugCodeElement.textContent = drugCode;
                textarea.value = drugMemos[drugCode] || '';
                textarea.setAttribute('data-drug-code', drugCode);

                modal.style.display = 'block';
            }

            // 메모 모달 닫기
            function closeMemoModal() {
                const modal = document.getElementById('memo-modal');
                modal.style.display = 'none';
            }

            // 메모 저장 (카테고리 없이)
            function saveMemo() {
                const textarea = document.getElementById('memo-textarea');
                const drugCode = textarea.getAttribute('data-drug-code');
                const memo = textarea.value;

                // 서버에 메모 저장
                fetch('/api/update_memo', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        drug_code: drugCode,
                        memo: memo
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        console.log('메모 저장 완료:', drugCode);

                        // 메모 데이터 업데이트
                        if (memo) {
                            drugMemos[drugCode] = memo;
                        } else {
                            delete drugMemos[drugCode];
                        }

                        // 모든 탭에서 메모 버튼 상태 동기화
                        syncMemoButtonState(drugCode, memo);

                        closeMemoModal();
                    } else {
                        console.error('메모 저장 실패:', data.message);
                        alert('메모 저장에 실패했습니다: ' + data.message);
                    }
                })
                .catch(error => {
                    console.error('API 요청 실패:', error);
                    alert('메모 저장에 실패했습니다.');
                });
            }

            // 검색 기능 (검색어가 있을 때만 테이블 표시)
            document.getElementById('searchInput').addEventListener('keyup', function() {
                const searchValue = this.value.toLowerCase().trim();
                const tableContainer = document.getElementById('searchTableContainer');
                const searchHint = document.getElementById('searchHint');
                const rows = document.querySelectorAll('#dataTable tbody tr.clickable-row');

                if (searchValue === '') {
                    // 검색어가 없으면 테이블 숨김
                    tableContainer.style.display = 'none';
                    searchHint.style.display = 'block';
                } else {
                    // 검색어가 있으면 테이블 표시
                    tableContainer.style.display = 'block';
                    searchHint.style.display = 'none';

                    let visibleCount = 0;
                    rows.forEach(row => {
                        const text = row.textContent.toLowerCase();
                        if (text.includes(searchValue)) {
                            row.style.display = '';
                            visibleCount++;
                        } else {
                            row.style.display = 'none';
                        }
                    });

                    // 검색 결과가 없으면 메시지 표시
                    if (visibleCount === 0) {
                        searchHint.textContent = '검색 결과가 없습니다.';
                        searchHint.style.display = 'block';
                        tableContainer.style.display = 'none';
                    }
                }
            });

            // 검색어 초기화 시 힌트 복원
            document.getElementById('searchInput').addEventListener('input', function() {
                const searchHint = document.getElementById('searchHint');
                if (this.value.trim() === '') {
                    searchHint.textContent = '검색어를 입력하면 일치하는 약품이 표시됩니다.';
                }
            });

            // 모달 외부 클릭시 닫기 (메모 모달용)
            window.onclick = function(event) {
                if (event.target.classList.contains('modal')) {
                    event.target.style.display = 'none';
                }
            }
        </script>

        <!-- 범용 메모 모달 -->
        <div id="memo-modal-generic" class="modal">
            <div class="modal-content" style="max-width: 600px;">
                <span class="close-btn" onclick="closeMemoModalGeneric()">&times;</span>
                <h2 style="margin-bottom: 20px;">메모 작성</h2>
                <p style="color: #718096; margin-bottom: 10px;">약품코드: <strong id="memo-drug-code-generic"></strong></p>
                <textarea id="memo-textarea-generic"
                          style="width: 100%; height: 200px; padding: 10px; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 14px; font-family: inherit; resize: vertical;"
                          placeholder="메모를 입력하세요..."></textarea>
                <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px;">
                    <button onclick="closeMemoModalGeneric()" style="padding: 10px 20px; border: 2px solid #cbd5e0; background: white; border-radius: 5px; cursor: pointer; font-size: 14px;">취소</button>
                    <button onclick="saveMemoGeneric()" style="padding: 10px 20px; border: none; background: #4b5563; color: white; border-radius: 5px; cursor: pointer; font-size: 14px; font-weight: bold;">저장</button>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    return html_content

def get_runway_class(runway_display):
    """런웨이 값에 따라 CSS 클래스 결정 (1개월 미만이면 경고)"""
    if '일' in runway_display:
        try:
            days = float(runway_display.replace('일', ''))
            if days < 30:
                return 'warning'
        except:
            pass
    return ''

def classify_drugs_by_special_cases(df, ma_months):
    """특수 케이스 약품 분류

    Returns:
        urgent_drugs: 사용되고 있는데 재고가 0인 약품 (긴급)
        dead_stock_drugs: 사용되지 않는데 재고만 있는 약품 (악성 재고)
    """

    # 각 약품의 N개월 이동평균 계산
    ma_values = []
    for _, row in df.iterrows():
        timeseries = row['월별_조제수량_리스트']
        ma = calculate_custom_ma(timeseries, ma_months)
        latest_ma = None
        for val in reversed(ma):
            if val is not None:
                latest_ma = val
                break
        ma_values.append(latest_ma if latest_ma else 0)

    df_with_ma = df.copy()
    df_with_ma['N개월_이동평균'] = ma_values

    # Case 1: 긴급 - 사용되는데 재고 없음 (N개월 이동평균 > 0 AND 재고 = 0)
    urgent_drugs = df_with_ma[
        (df_with_ma['N개월_이동평균'] > 0) &
        (df_with_ma['최종_재고수량'] == 0)
    ].copy()

    # Case 2: 악성 재고 - 안 쓰이는데 재고만 있음 (N개월 이동평균 = 0 AND 재고 > 0)
    dead_stock_drugs = df_with_ma[
        (df_with_ma['N개월_이동평균'] == 0) &
        (df_with_ma['최종_재고수량'] > 0)
    ].copy()

    # 긴급 약품: 마지막 조제월 기준으로 정렬 (최신 사용이 위로)
    if not urgent_drugs.empty:
        # 마지막 조제 인덱스 계산 (월별_조제수량_리스트에서 마지막 0이 아닌 값의 인덱스)
        def get_last_use_index(row):
            timeseries = row['월별_조제수량_리스트']
            for i in range(len(timeseries) - 1, -1, -1):
                if timeseries[i] > 0:
                    return i  # 마지막 사용 인덱스 (클수록 최신)
            return -1  # 사용 기록 없음

        urgent_drugs['_last_use_index'] = urgent_drugs.apply(get_last_use_index, axis=1)
        urgent_drugs = urgent_drugs.sort_values('_last_use_index', ascending=False)  # 최신순
        urgent_drugs = urgent_drugs.drop(columns=['_last_use_index'])

    # 재고수량 기준 내림차순 정렬 (악성 재고 크기 순)
    if not dead_stock_drugs.empty:
        dead_stock_drugs = dead_stock_drugs.sort_values('최종_재고수량', ascending=False)

    return urgent_drugs, dead_stock_drugs

def generate_urgent_drugs_section(urgent_drugs, ma_months, months):
    """긴급 약품 섹션 HTML 생성 (테이블 형식 + 체크박스 + 메모 + 인라인 차트) - 모달용"""
    import json

    # DB에서 체크된 약품 코드 목록 가져오기 (카테고리 없이)
    checked_codes = checked_items_db.get_checked_items()

    # 메모 목록 가져오기 (카테고리 없이)
    memos = checked_items_db.get_all_memos()

    html = f"""
                    <div style="padding: 15px; background: #fff8f8; border-radius: 8px; margin-bottom: 15px;">
                        <p style="margin: 0; color: #c53030; font-weight: bold;">
                            ⚠️ 총 {len(urgent_drugs)}개 약품이 현재 사용되고 있으나 재고가 소진되었습니다. 즉시 주문이 필요합니다!
                        </p>
                    </div>
                    <div class="table-container">
                        <table id="urgent-drugs-table" style="font-size: 13px;">
                            <thead>
                                <tr>
                                    <th style="width: 50px;">확인</th>
                                    <th>약품명</th>
                                    <th>약품코드</th>
                                    <th>제약회사</th>
                                    <th>재고수량</th>
                                    <th>{ma_months}개월 이동평균</th>
                                    <th>런웨이</th>
                                    <th>마지막 조제월</th>
                                    <th>트렌드</th>
                                </tr>
                            </thead>
                            <tbody>
    """

    for _, row in urgent_drugs.iterrows():
        drug_code = str(row['약품코드'])
        is_checked = drug_code in checked_codes

        # N개월 이동평균 (최신값)
        latest_ma = row['N개월_이동평균']

        # 마지막 조제월 찾기 (월별_조제수량_리스트에서 마지막 0이 아닌 값의 인덱스)
        timeseries = row['월별_조제수량_리스트']
        last_use_month = "N/A"
        for i in range(len(timeseries) - 1, -1, -1):
            if timeseries[i] > 0:
                # i번째 월이 마지막 사용 월
                months_ago = len(timeseries) - 1 - i
                if months_ago == 0:
                    last_use_month = "이번 달"
                elif months_ago == 1:
                    last_use_month = "지난 달"
                else:
                    last_use_month = f"{months_ago}개월 전"
                break

        # 스파크라인 생성
        ma = calculate_custom_ma(timeseries, ma_months)
        sparkline_html = create_sparkline_svg(timeseries, ma, ma_months)

        # 약품명 30자 제한
        drug_name_display = row['약품명'] if row['약품명'] is not None else "정보없음"
        if len(drug_name_display) > 30:
            drug_name_display = drug_name_display[:30] + "..."

        # 제약회사 12자 제한
        company_display = row['제약회사'] if row['제약회사'] is not None else "정보없음"
        if len(company_display) > 12:
            company_display = company_display[:12] + "..."

        # 체크 상태에 따라 클래스 적용
        row_class = "checked-row" if is_checked else ""
        checked_attr = "checked" if is_checked else ""

        # 메모 가져오기
        memo = memos.get(drug_code, '')
        memo_escaped = memo.replace("'", "\\'").replace('"', '&quot;').replace('\n', '\\n')

        # 메모 버튼 스타일 (메모가 있으면 주황색)
        memo_btn_class = "has-memo" if memo else ""
        memo_preview = memo[:50] + '...' if len(memo) > 50 else memo

        # 인라인 차트용 데이터 생성
        chart_data = {
            'drug_name': row['약품명'] if row['약품명'] else "정보없음",
            'drug_code': drug_code,
            'timeseries': list(timeseries),
            'ma': list(ma),
            'months': months,
            'ma_months': ma_months,
            'stock': 0,
            'latest_ma': latest_ma,
            'runway': '재고 없음'
        }
        chart_data_json = json.dumps(chart_data, ensure_ascii=False).replace("'", "&#39;")

        html += f"""
                                <tr class="urgent-row tab-clickable-row {row_class}" data-drug-code="{drug_code}"
                                    data-chart-data='{chart_data_json}'
                                    onclick="toggleInlineChart(this, '{drug_code}')">
                                    <td style="text-align: center;" onclick="event.stopPropagation()">
                                        <div class="checkbox-memo-container">
                                            <input type="checkbox" class="urgent-checkbox" data-drug-code="{drug_code}" {checked_attr} onchange="handleUrgentCheckbox(this)">
                                            <button class="memo-btn {memo_btn_class}"
                                                    data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); openMemoModal('{drug_code}')"
                                                    title="{memo_preview if memo else '메모 추가'}">
                                                ✎
                                            </button>
                                        </div>
                                    </td>
                                    <td style="font-weight: bold;">{drug_name_display}</td>
                                    <td>{drug_code}</td>
                                    <td>{company_display}</td>
                                    <td style="color: #c53030; font-weight: bold;">0</td>
                                    <td style="color: #2d5016; font-weight: bold;">{latest_ma:.2f}</td>
                                    <td style="color: #c53030; font-style: italic;">재고 없음</td>
                                    <td>{last_use_month}</td>
                                    <td>{sparkline_html}</td>
                                </tr>
        """

    html += """
                            </tbody>
                        </table>
                    </div>

            <!-- 메모 모달 -->
            <div id="memo-modal" class="modal">
                <div class="modal-content" style="max-width: 600px;">
                    <span class="close-btn" onclick="closeMemoModal()">&times;</span>
                    <h2 style="margin-bottom: 20px;">📝 메모 작성</h2>
                    <p style="color: #718096; margin-bottom: 10px;">약품코드: <strong id="memo-drug-code"></strong></p>
                    <textarea id="memo-textarea"
                              style="width: 100%; height: 200px; padding: 10px; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 14px; font-family: inherit; resize: vertical;"
                              placeholder="메모를 입력하세요..."></textarea>
                    <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px;">
                        <button onclick="closeMemoModal()" style="padding: 10px 20px; border: 2px solid #cbd5e0; background: white; border-radius: 5px; cursor: pointer; font-size: 14px;">취소</button>
                        <button onclick="saveMemo()" style="padding: 10px 20px; border: none; background: #4b5563; color: white; border-radius: 5px; cursor: pointer; font-size: 14px; font-weight: bold;">저장</button>
                    </div>
                </div>
            </div>
    """

    # 메모 데이터를 JSON으로 변환하여 JavaScript에서 사용
    import json
    memos_json = json.dumps(memos, ensure_ascii=False)

    html += f"""
            <script>
                // 메모 데이터 (JavaScript 객체로 변환)
                const drugMemos = {memos_json};
            </script>
    """

    return html

def generate_low_stock_section(low_drugs_df, ma_months, months):
    """재고 부족 약품 섹션 HTML 생성 (테이블 형식 + 체크박스/메모 + 인라인 차트) - 모달용"""
    import json

    if low_drugs_df.empty:
        return ""

    # DB에서 체크된 약품 코드 목록 가져오기 (카테고리 없이)
    checked_codes = checked_items_db.get_checked_items()
    memos = checked_items_db.get_all_memos()

    html = f"""
                    <div style="padding: 15px; background: #fffbeb; border-radius: 8px; margin-bottom: 15px;">
                        <p style="margin: 0; color: #ca8a04; font-weight: bold;">
                            ⚠️ 총 {len(low_drugs_df)}개 약품의 런웨이가 3개월 이하입니다. 재고 보충을 고려하세요.
                        </p>
                    </div>
                    <div class="table-container">
                        <table id="low-drugs-table" style="font-size: 13px;">
                            <thead>
                                <tr>
                                    <th style="width: 50px;">확인</th>
                                    <th>약품명</th>
                                    <th>약품코드</th>
                                    <th>제약회사</th>
                                    <th>재고수량</th>
                                    <th>{ma_months}개월 이동평균</th>
                                    <th>런웨이</th>
                                    <th>트렌드</th>
                                </tr>
                            </thead>
                            <tbody>
    """

    for _, row in low_drugs_df.iterrows():
        drug_code = str(row['약품코드'])
        is_checked = drug_code in checked_codes

        # 런웨이 표시
        runway_months = row['런웨이_개월']
        if runway_months >= 1:
            runway_display = f"{runway_months:.2f}개월"
        else:
            runway_days = runway_months * 30.417
            runway_display = f"{runway_days:.2f}일"

        # 스파크라인 생성
        timeseries = row['월별_조제수량_리스트']
        ma = calculate_custom_ma(timeseries, ma_months)
        sparkline_html = create_sparkline_svg(timeseries, ma, ma_months)

        # 약품명 30자 제한
        drug_name_display = row['약품명'] if row['약품명'] is not None else "정보없음"
        if len(drug_name_display) > 30:
            drug_name_display = drug_name_display[:30] + "..."

        # 제약회사 12자 제한
        company_display = row['제약회사'] if row['제약회사'] is not None else "정보없음"
        if len(company_display) > 12:
            company_display = company_display[:12] + "..."

        # 체크 상태에 따라 클래스 적용
        row_class = "checked-row" if is_checked else ""
        checked_attr = "checked" if is_checked else ""

        # 메모 가져오기
        memo = memos.get(drug_code, '')
        memo_btn_class = "has-memo" if memo else ""
        memo_preview = memo[:50] + '...' if len(memo) > 50 else memo

        # 인라인 차트용 데이터 생성
        latest_ma = row['N개월_이동평균']
        chart_data = {
            'drug_name': row['약품명'] if row['약품명'] else "정보없음",
            'drug_code': drug_code,
            'timeseries': list(timeseries),
            'ma': list(ma),
            'months': months,
            'ma_months': ma_months,
            'stock': int(row['최종_재고수량']),
            'latest_ma': latest_ma,
            'runway': runway_display
        }
        chart_data_json = json.dumps(chart_data, ensure_ascii=False).replace("'", "&#39;")

        html += f"""
                                <tr class="low-row tab-clickable-row {row_class}" data-drug-code="{drug_code}"
                                    data-chart-data='{chart_data_json}'
                                    onclick="toggleInlineChart(this, '{drug_code}')">
                                    <td style="text-align: center;" onclick="event.stopPropagation()">
                                        <div class="checkbox-memo-container">
                                            <input type="checkbox" class="low-checkbox" data-drug-code="{drug_code}" {checked_attr} onchange="handleLowCheckbox(this)">
                                            <button class="memo-btn {memo_btn_class}"
                                                    data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); openMemoModalGeneric('{drug_code}')"
                                                    title="{memo_preview if memo else '메모 추가'}">
                                                ✎
                                            </button>
                                        </div>
                                    </td>
                                    <td style="font-weight: bold;">{drug_name_display}</td>
                                    <td>{drug_code}</td>
                                    <td>{company_display}</td>
                                    <td>{row['최종_재고수량']:,.0f}</td>
                                    <td>{row['N개월_이동평균']:.2f}</td>
                                    <td style="color: #ca8a04; font-weight: bold;">{runway_display}</td>
                                    <td>{sparkline_html}</td>
                                </tr>
        """

    html += """
                            </tbody>
                        </table>
                    </div>
    """

    # 메모 데이터를 JSON으로 변환
    import json
    memos_json = json.dumps(memos, ensure_ascii=False)

    html += f"""
            <script>
                // 부족 탭 메모 데이터
                var lowDrugMemos = {memos_json};
            </script>
    """

    return html

def generate_high_stock_section(high_drugs_df, ma_months, months):
    """재고 충분 약품 섹션 HTML 생성 (테이블 형식 + 체크박스/메모 + 인라인 차트) - 모달용"""
    import json

    if high_drugs_df.empty:
        return ""

    # DB에서 체크된 약품 코드 목록 가져오기 (카테고리 없이)
    checked_codes = checked_items_db.get_checked_items()
    memos = checked_items_db.get_all_memos()

    html = f"""
                    <div style="padding: 15px; background: #f0fdf4; border-radius: 8px; margin-bottom: 15px;">
                        <p style="margin: 0; color: #16a34a; font-weight: bold;">
                            ✅ 총 {len(high_drugs_df)}개 약품의 런웨이가 3개월을 초과합니다. 재고가 충분합니다.
                        </p>
                    </div>
                    <div class="table-container">
                        <table id="high-drugs-table" style="font-size: 13px;">
                            <thead>
                                <tr>
                                    <th style="width: 50px;">확인</th>
                                    <th>약품명</th>
                                    <th>약품코드</th>
                                    <th>제약회사</th>
                                    <th>재고수량</th>
                                    <th>{ma_months}개월 이동평균</th>
                                    <th>런웨이</th>
                                    <th>트렌드</th>
                                </tr>
                            </thead>
                            <tbody>
    """

    for _, row in high_drugs_df.iterrows():
        drug_code = str(row['약품코드'])
        is_checked = drug_code in checked_codes

        # 런웨이 표시
        runway_months = row['런웨이_개월']
        runway_display = f"{runway_months:.2f}개월"

        # 스파크라인 생성
        timeseries = row['월별_조제수량_리스트']
        ma = calculate_custom_ma(timeseries, ma_months)
        sparkline_html = create_sparkline_svg(timeseries, ma, ma_months)

        # 약품명 30자 제한
        drug_name_display = row['약품명'] if row['약품명'] is not None else "정보없음"
        if len(drug_name_display) > 30:
            drug_name_display = drug_name_display[:30] + "..."

        # 제약회사 12자 제한
        company_display = row['제약회사'] if row['제약회사'] is not None else "정보없음"
        if len(company_display) > 12:
            company_display = company_display[:12] + "..."

        # 체크 상태에 따라 클래스 적용
        row_class = "checked-row" if is_checked else ""
        checked_attr = "checked" if is_checked else ""

        # 메모 가져오기
        memo = memos.get(drug_code, '')
        memo_btn_class = "has-memo" if memo else ""
        memo_preview = memo[:50] + '...' if len(memo) > 50 else memo

        # 인라인 차트용 데이터 생성
        latest_ma = row['N개월_이동평균']
        chart_data = {
            'drug_name': row['약품명'] if row['약품명'] else "정보없음",
            'drug_code': drug_code,
            'timeseries': list(timeseries),
            'ma': list(ma),
            'months': months,
            'ma_months': ma_months,
            'stock': int(row['최종_재고수량']),
            'latest_ma': latest_ma,
            'runway': runway_display
        }
        chart_data_json = json.dumps(chart_data, ensure_ascii=False).replace("'", "&#39;")

        html += f"""
                                <tr class="high-row tab-clickable-row {row_class}" data-drug-code="{drug_code}"
                                    data-chart-data='{chart_data_json}'
                                    onclick="toggleInlineChart(this, '{drug_code}')">
                                    <td style="text-align: center;" onclick="event.stopPropagation()">
                                        <div class="checkbox-memo-container">
                                            <input type="checkbox" class="high-checkbox" data-drug-code="{drug_code}" {checked_attr} onchange="handleHighCheckbox(this)">
                                            <button class="memo-btn {memo_btn_class}"
                                                    data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); openMemoModalGeneric('{drug_code}')"
                                                    title="{memo_preview if memo else '메모 추가'}">
                                                ✎
                                            </button>
                                        </div>
                                    </td>
                                    <td style="font-weight: bold;">{drug_name_display}</td>
                                    <td>{drug_code}</td>
                                    <td>{company_display}</td>
                                    <td>{row['최종_재고수량']:,.0f}</td>
                                    <td>{row['N개월_이동평균']:.2f}</td>
                                    <td style="color: #16a34a; font-weight: bold;">{runway_display}</td>
                                    <td>{sparkline_html}</td>
                                </tr>
        """

    html += """
                            </tbody>
                        </table>
                    </div>
    """

    # 메모 데이터를 JSON으로 변환
    memos_json = json.dumps(memos, ensure_ascii=False)

    html += f"""
            <script>
                // 충분 탭 메모 데이터
                var highDrugMemos = {memos_json};
            </script>
    """

    return html

def generate_dead_stock_section(dead_stock_drugs, ma_months, months):
    """악성 재고 섹션 HTML 생성 (테이블 형식 + 체크박스/메모/스파크라인 + 인라인 차트) - 모달용"""
    import json

    total_dead_stock = dead_stock_drugs['최종_재고수량'].sum()

    # DB에서 체크된 약품 코드 목록 가져오기 (카테고리 없이)
    checked_codes = checked_items_db.get_checked_items()
    memos = checked_items_db.get_all_memos()

    html = f"""
                    <div style="padding: 15px; background: #edf2f7; border-radius: 8px; margin-bottom: 15px;">
                        <p style="margin: 0; color: #4a5568; font-weight: bold;">
                            📊 총 {len(dead_stock_drugs)}개 약품이 {ma_months}개월 동안 사용되지 않았으나 재고가 {total_dead_stock:,.0f}개 남아있습니다.
                        </p>
                        <p style="margin: 5px 0 0 0; color: #718096; font-size: 14px;">
                            💡 재고 정리 또는 반품을 고려해보세요.
                        </p>
                    </div>
                    <div class="table-container">
                        <table id="dead-drugs-table" style="font-size: 13px;">
                            <thead>
                                <tr>
                                    <th style="width: 50px;">확인</th>
                                    <th>약품명</th>
                                    <th>약품코드</th>
                                    <th>제약회사</th>
                                    <th>재고수량</th>
                                    <th>{ma_months}개월 이동평균</th>
                                    <th>런웨이</th>
                                    <th>트렌드</th>
                                </tr>
                            </thead>
                            <tbody>
    """

    for _, row in dead_stock_drugs.iterrows():
        drug_code = str(row['약품코드'])
        is_checked = drug_code in checked_codes

        # N개월 이동평균
        latest_ma = row['N개월_이동평균']

        # 스파크라인 생성
        timeseries = row['월별_조제수량_리스트']
        ma = calculate_custom_ma(timeseries, ma_months)
        sparkline_html = create_sparkline_svg(timeseries, ma, ma_months)

        # 약품명 30자 제한
        drug_name_display = row['약품명'] if row['약품명'] is not None else "정보없음"
        if len(drug_name_display) > 30:
            drug_name_display = drug_name_display[:30] + "..."

        # 제약회사 12자 제한
        company_display = row['제약회사'] if row['제약회사'] is not None else "정보없음"
        if len(company_display) > 12:
            company_display = company_display[:12] + "..."

        # 체크 상태에 따라 클래스 적용
        row_class = "checked-row" if is_checked else ""
        checked_attr = "checked" if is_checked else ""

        # 메모 가져오기
        memo = memos.get(drug_code, '')
        memo_btn_class = "has-memo" if memo else ""
        memo_preview = memo[:50] + '...' if len(memo) > 50 else memo

        # 인라인 차트용 데이터 생성
        chart_data = {
            'drug_name': row['약품명'] if row['약품명'] else "정보없음",
            'drug_code': drug_code,
            'timeseries': list(timeseries),
            'ma': list(ma),
            'months': months,
            'ma_months': ma_months,
            'stock': int(row['최종_재고수량']),
            'latest_ma': 0,
            'runway': '재고만 있음'
        }
        chart_data_json = json.dumps(chart_data, ensure_ascii=False).replace("'", "&#39;")

        html += f"""
                                <tr class="dead-row tab-clickable-row {row_class}" data-drug-code="{drug_code}" style="background: rgba(247, 250, 252, 0.7);"
                                    data-chart-data='{chart_data_json}'
                                    onclick="toggleInlineChart(this, '{drug_code}')">
                                    <td style="text-align: center;" onclick="event.stopPropagation()">
                                        <div class="checkbox-memo-container">
                                            <input type="checkbox" class="dead-checkbox" data-drug-code="{drug_code}" {checked_attr} onchange="handleDeadCheckbox(this)">
                                            <button class="memo-btn {memo_btn_class}"
                                                    data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); openMemoModalGeneric('{drug_code}')"
                                                    title="{memo_preview if memo else '메모 추가'}">
                                                ✎
                                            </button>
                                        </div>
                                    </td>
                                    <td style="font-weight: bold;">{drug_name_display}</td>
                                    <td>{drug_code}</td>
                                    <td>{company_display}</td>
                                    <td style="color: #2d5016; font-weight: bold;">{row['최종_재고수량']:,.0f}</td>
                                    <td style="color: #c53030;">0</td>
                                    <td style="color: #a0aec0; font-style: italic;">재고만 있음</td>
                                    <td>{sparkline_html}</td>
                                </tr>
        """

    html += """
                            </tbody>
                        </table>
                    </div>
    """

    # 메모 데이터를 JSON으로 변환
    memos_json = json.dumps(memos, ensure_ascii=False)

    html += f"""
            <script>
                // 악성재고 탭 메모 데이터
                var deadDrugMemos = {memos_json};
            </script>
    """

    return html

def analyze_runway(df, months, ma_months):
    """런웨이 분포 분석 차트 생성 (페이지네이션 지원) - N-MA 런웨이 기준

    Returns:
        tuple: (chart_js_low, chart_js_high, low_count, high_count, low_drugs_df, high_drugs_df)
    """
    try:
        # N-MA 런웨이를 숫자로 변환 (개월 단위)
        low_data = []  # 3개월 이하 (차트용)
        high_data = []  # 3개월 초과 (차트용)
        low_drugs_list = []  # 3개월 이하 (테이블용)
        high_drugs_list = []  # 3개월 초과 (테이블용)

        for idx, row in df.iterrows():
            # N개월 이동평균 계산
            timeseries = row['월별_조제수량_리스트']
            ma = calculate_custom_ma(timeseries, ma_months)

            latest_ma = None
            for val in reversed(ma):
                if val is not None:
                    latest_ma = val
                    break

            # N-MA 런웨이 계산
            ma_runway_months = None
            if latest_ma and latest_ma > 0:
                ma_runway_months = row['최종_재고수량'] / latest_ma

            if ma_runway_months and ma_runway_months > 0:
                # 데이터 구조: (N-MA런웨이(개월), 약품명, N개월평균)
                data_tuple = (
                    ma_runway_months,
                    row['약품명'],
                    latest_ma
                )

                # 테이블용 데이터 (전체 row 정보 + 계산된 값)
                drug_data = {
                    '약품코드': row['약품코드'],
                    '약품명': row['약품명'],
                    '제약회사': row['제약회사'],
                    '최종_재고수량': row['최종_재고수량'],
                    'N개월_이동평균': latest_ma,
                    '런웨이_개월': ma_runway_months,
                    '월별_조제수량_리스트': timeseries
                }

                if ma_runway_months <= 3:
                    low_data.append(data_tuple)
                    low_drugs_list.append(drug_data)
                else:
                    high_data.append(data_tuple)
                    high_drugs_list.append(drug_data)

        # DataFrame 생성
        import pandas as pd
        low_drugs_df = pd.DataFrame(low_drugs_list) if low_drugs_list else pd.DataFrame()
        high_drugs_df = pd.DataFrame(high_drugs_list) if high_drugs_list else pd.DataFrame()

        # 정렬: 부족은 런웨이 오름차순, 충분은 런웨이 내림차순
        if not low_drugs_df.empty:
            low_drugs_df = low_drugs_df.sort_values('런웨이_개월', ascending=True)
        if not high_drugs_df.empty:
            high_drugs_df = high_drugs_df.sort_values('런웨이_개월', ascending=False)

        chart_js_low = None
        chart_js_high = None
        low_count = len(low_data)
        high_count = len(high_data)

        # 하위 차트 (3개월 이하, 오름차순 정렬)
        if low_data:
            import json
            low_data_sorted = sorted(low_data)
            low_data_json = json.dumps(low_data_sorted)

            chart_js_low = f"""
                var lowData = {low_data_json};
                var currentPageLow = 0;
                var itemsPerPage = 30;

                function updateChartLow() {{
                    var start = currentPageLow * itemsPerPage;
                    var end = start + itemsPerPage;
                    var pageData = lowData.slice(start, end);

                    if (pageData.length === 0) return;

                    // 데이터 구조: [N-MA런웨이(개월), 약품명, N개월평균]
                    var values = pageData.map(function(item) {{ return item[0]; }});
                    var names = pageData.map(function(item) {{ return item[1]; }});
                    var maAvg = pageData.map(function(item) {{ return item[2]; }});

                    // 하위 그룹: 런웨이가 짧은 것이 위에 오도록 역순
                    values.reverse();
                    names.reverse();
                    maAvg.reverse();

                    // 커스텀 호버 텍스트 생성
                    var hoverTexts = [];
                    for (var i = 0; i < values.length; i++) {{
                        var maRunwayText = values[i] >= 1
                            ? values[i].toFixed(2) + '개월'
                            : (values[i] * 30.417).toFixed(2) + '일';

                        hoverTexts.push(
                            '런웨이: ' + maRunwayText + ' ({ma_months}개월 이동평균: ' + maAvg[i].toFixed(2) + ')'
                        );
                    }}

                    var data = [{{
                        x: values,
                        y: names,
                        type: 'bar',
                        orientation: 'h',
                        text: values,
                        texttemplate: '%{{text:.2f}}개월',
                        textposition: 'outside',
                        hovertext: hoverTexts,
                        hoverinfo: 'text',
                        marker: {{
                            color: values,
                            colorscale: [
                                [0, 'rgb(255, 0, 0)'],
                                [0.5, 'rgb(255, 255, 0)'],
                                [1, 'rgb(0, 255, 0)']
                            ],
                            cmin: 0,
                            cmax: 3
                        }},
                        width: 0.7
                    }}];

                    var layout = {{
                        xaxis: {{
                            title: '개월',
                            range: [0, Math.max(...values) * 1.3]
                        }},
                        yaxis: {{
                            title: '',
                            automargin: true,
                            tickfont: {{size: 10}}
                        }},
                        height: Math.min(1200, pageData.length * 25 + 100),
                        margin: {{
                            l: 350,
                            r: 100,
                            t: 40,
                            b: 60,
                            pad: 10
                        }},
                        bargap: 0.3
                    }};

                    Plotly.newPlot('runway-chart-low', data, layout, {{responsive: true}});

                    // 페이지 정보 업데이트
                    var totalPages = Math.ceil(lowData.length / itemsPerPage);
                    document.getElementById('page-info-low').textContent =
                        '페이지 ' + (currentPageLow + 1) + ' / ' + totalPages +
                        ' (총 ' + lowData.length + '개)';

                    // 버튼 상태 업데이트
                    document.getElementById('prev-low').disabled = (currentPageLow === 0);
                    document.getElementById('next-low').disabled = (currentPageLow >= totalPages - 1);
                }}

                updateChartLow();
            """

        # 상위 차트 (3개월 초과, 내림차순 정렬)
        if high_data:
            high_data_sorted = sorted(high_data, reverse=True)
            high_data_json = json.dumps(high_data_sorted)

            chart_js_high = f"""
                var highData = {high_data_json};
                var currentPageHigh = 0;
                var itemsPerPageHigh = 30;

                function updateChartHigh() {{
                    var start = currentPageHigh * itemsPerPageHigh;
                    var end = start + itemsPerPageHigh;
                    var pageData = highData.slice(start, end);

                    if (pageData.length === 0) return;

                    // 데이터 구조: [N-MA런웨이(개월), 약품명, N개월평균]
                    var values = pageData.map(function(item) {{ return item[0]; }});
                    var names = pageData.map(function(item) {{ return item[1]; }});
                    var maAvg = pageData.map(function(item) {{ return item[2]; }});

                    // 상위 그룹: 런웨이가 긴 것이 위에 오도록 역순
                    values.reverse();
                    names.reverse();
                    maAvg.reverse();

                    // 커스텀 호버 텍스트 생성
                    var hoverTexts = [];
                    for (var i = 0; i < values.length; i++) {{
                        var maRunwayText = values[i] >= 1
                            ? values[i].toFixed(2) + '개월'
                            : (values[i] * 30.417).toFixed(2) + '일';

                        hoverTexts.push(
                            '런웨이: ' + maRunwayText + ' ({ma_months}개월 이동평균: ' + maAvg[i].toFixed(2) + ')'
                        );
                    }}

                    var data = [{{
                        x: values,
                        y: names,
                        type: 'bar',
                        orientation: 'h',
                        text: values,
                        texttemplate: '%{{text:.2f}}개월',
                        textposition: 'outside',
                        hovertext: hoverTexts,
                        hoverinfo: 'text',
                        marker: {{
                            color: 'rgb(34, 197, 94)'
                        }},
                        width: 0.7
                    }}];

                    var layout = {{
                        xaxis: {{
                            title: '개월',
                            range: [0, Math.max(...values) * 1.1]
                        }},
                        yaxis: {{
                            title: '',
                            automargin: true,
                            tickfont: {{size: 10}}
                        }},
                        height: Math.min(1200, pageData.length * 25 + 100),
                        margin: {{
                            l: 350,
                            r: 100,
                            t: 40,
                            b: 60,
                            pad: 10
                        }},
                        bargap: 0.3
                    }};

                    Plotly.newPlot('runway-chart-high', data, layout, {{responsive: true}});

                    // 페이지 정보 업데이트
                    var totalPages = Math.ceil(highData.length / itemsPerPageHigh);
                    document.getElementById('page-info-high').textContent =
                        '페이지 ' + (currentPageHigh + 1) + ' / ' + totalPages +
                        ' (총 ' + highData.length + '개)';

                    // 버튼 상태 업데이트
                    document.getElementById('prev-high').disabled = (currentPageHigh === 0);
                    document.getElementById('next-high').disabled = (currentPageHigh >= totalPages - 1);
                }}

                updateChartHigh();

                // 페이지 변경 함수
                function changePage(type, direction) {{
                    if (type === 'low') {{
                        var totalPages = Math.ceil(lowData.length / itemsPerPage);
                        currentPageLow = Math.max(0, Math.min(currentPageLow + direction, totalPages - 1));
                        updateChartLow();
                    }} else {{
                        var totalPages = Math.ceil(highData.length / itemsPerPageHigh);
                        currentPageHigh = Math.max(0, Math.min(currentPageHigh + direction, totalPages - 1));
                        updateChartHigh();
                    }}
                }}
            """

        return chart_js_low, chart_js_high, low_count, high_count, low_drugs_df, high_drugs_df
    except Exception as e:
        print(f"Error in analyze_runway: {e}")
        import traceback
        traceback.print_exc()
    return None, None, 0, 0, pd.DataFrame(), pd.DataFrame()

def create_and_save_report(df, months, mode='dispense', ma_months=3, open_browser=True):
    """보고서를 생성하고 파일로 저장하는 함수

    Args:
        df: DataFrame (시계열 데이터 포함)
        months: 월 리스트
        mode: 'dispense' (전문약) 또는 'sale' (일반약)
        ma_months: 이동평균 개월 수
        open_browser: 브라우저에서 자동으로 열기 여부
    """
    print("\n=== 단순 보고서 생성 준비 ===")
    print(f"   이동평균 기간: {ma_months}개월")

    # 1. SQLite DB에서 최신 재고 데이터 가져오기
    if not inventory_db.db_exists():
        print("⚠️  recent_inventory.sqlite3 파일이 없습니다.")
        print("   기존 CSV의 재고수량을 사용합니다.")
        df_final = df.copy()
    else:
        print(f"✅ recent_inventory.sqlite3에서 최신 재고 데이터 로드 중...")
        inventory_df = inventory_db.get_all_inventory_as_df()

        if inventory_df.empty:
            print("⚠️  DB에 재고 데이터가 없습니다. 기존 CSV의 재고수량을 사용합니다.")
            df_final = df.copy()
        else:
            print(f"   {len(inventory_df)}개 약품의 재고 정보 로드 완료")

            # 2. 통계 데이터와 최신 재고 데이터 병합
            df_final = df.copy()

            # 약품코드를 str로 정규화
            df_final['약품코드'] = df_final['약품코드'].astype(str)
            inventory_df['약품코드'] = inventory_df['약품코드'].astype(str)

            # 병합 (최종_재고수량을 현재_재고수량으로 업데이트)
            df_final = df_final.merge(
                inventory_df[['약품코드', '현재_재고수량', '최종_업데이트일시']],
                on='약품코드',
                how='left'
            )

            # 최종_재고수량을 현재_재고수량으로 업데이트 (있는 경우)
            df_final['최종_재고수량'] = df_final['현재_재고수량'].fillna(df_final['최종_재고수량'])

            # 불필요한 컬럼 제거
            df_final = df_final.drop(columns=['현재_재고수량'], errors='ignore')

            # 최종 업데이트 일시 출력
            if '최종_업데이트일시' in df_final.columns:
                latest_update = df_final['최종_업데이트일시'].dropna().unique()
                if len(latest_update) > 0:
                    print(f"   📅 재고 최종 업데이트: {latest_update[0]}")
                df_final = df_final.drop(columns=['최종_업데이트일시'], errors='ignore')

    # 출력 디렉토리 생성
    output_dir = 'inventory_reports'
    os.makedirs(output_dir, exist_ok=True)

    # HTML 보고서 생성
    print("\n📝 HTML 보고서 생성 중...")
    html_content = generate_html_report(df_final, months, mode=mode, ma_months=ma_months)

    # 파일명에 모드 및 MA 개월 수 반영
    mode_suffix = 'dispense' if mode == 'dispense' else 'sale'
    filename = f'simple_report_{mode_suffix}_{ma_months}ma_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
    output_path = os.path.join(output_dir, filename)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"\n✅ 보고서가 생성되었습니다: {output_path}")

    # 브라우저에서 자동으로 열기
    if open_browser:
        import webbrowser
        webbrowser.open(f'file://{os.path.abspath(output_path)}')

    return output_path

def main():
    """메인 함수 - 직접 실행시에만 동작"""
    # CSV 파일 읽기
    csv_path = 'processed_inventory.csv'
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)

        # 사용자에게 이동평균 개월 수 물어보기
        while True:
            try:
                ma = int(input("이동평균 개월 수 (1-12): "))
                if 1 <= ma <= 12:
                    break
                else:
                    print("1에서 12 사이의 숫자를 입력해주세요.")
            except ValueError:
                print("올바른 숫자를 입력해주세요.")

        # 보고서 생성 및 저장
        months = []  # 실제로는 DB에서 로드해야 함
        create_and_save_report(df, months, ma_months=ma)

    else:
        print(f"❌ {csv_path} 파일을 찾을 수 없습니다.")
        print("먼저 init_db.py를 실행하여 DB 파일을 생성해주세요.")

if __name__ == "__main__":
    main()
