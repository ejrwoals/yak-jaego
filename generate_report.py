import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from datetime import datetime
import json

def create_sparkline_svg(timeseries_data, ma3_data):
    """
    경량 SVG 스파크라인 생성 (검정 점선 + 주황색 3개월 이동평균)
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

    # 3개월 이동평균 라인 (주황색 실선)
    ma3_line = ''
    if ma3_data and any(v is not None for v in ma3_data):
        ma3_points = []
        for i, val in enumerate(ma3_data):
            if val is not None:
                x = scale_x(i, len(ma3_data))
                y = scale_y(val)
                ma3_points.append(f"{x:.2f},{y:.2f}")

        if ma3_points:
            ma3_line = f'<polyline points="{" ".join(ma3_points)}" fill="none" stroke="orange" stroke-width="2" />'

    svg = f'<svg width="{width}" height="{height}" style="display:block;">{actual_line}{ma3_line}</svg>'
    return svg

def create_chart_data_json(months, timeseries_data, ma3_data, avg, drug_name, drug_code):
    """
    모달 차트용 데이터를 JSON으로 변환
    """
    # numpy/pandas 타입을 Python native 타입으로 변환
    def convert_to_native(val):
        if hasattr(val, 'item'):  # numpy/pandas scalar
            return val.item()
        return val

    return json.dumps({
        'months': months,
        'timeseries': [convert_to_native(v) for v in timeseries_data],
        'ma3': [convert_to_native(v) if v is not None else None for v in ma3_data],
        'avg': convert_to_native(avg),
        'drug_name': str(drug_name),
        'drug_code': str(drug_code)
    })

def generate_html_report(df, months):
    """
    DataFrame을 HTML 보고서로 생성
    months: 월 리스트 (예: ['2025-01', '2025-02', ...])
    """
    
    # HTML 템플릿 시작
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>재고 관리 보고서</title>
        <style>
            body {{
                font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
                text-align: center;
                color: #718096;
                margin-bottom: 30px;
            }}
            .summary-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }}
            .summary-card {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
        </style>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    </head>
    <body>
        <div class="container">
            <h1>📊 약품 재고 관리 보고서</h1>
            <div class="date">생성일: {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}</div>
            
            <div class="summary-grid">
                <div class="summary-card">
                    <h3>총 약품 수</h3>
                    <div class="value">{len(df):,}개</div>
                </div>
                <div class="summary-card">
                    <h3>데이터 기간</h3>
                    <div class="value">{len(months)}개월</div>
                </div>
                <div class="summary-card">
                    <h3>총 재고 수량</h3>
                    <div class="value">{df['최종_재고수량'].sum():,.0f}개</div>
                </div>
                <div class="summary-card">
                    <h3>월평균 총 조제량</h3>
                    <div class="value">{df['월평균_조제수량'].sum():,.0f}개</div>
                </div>
            </div>
    """
    
    # 런웨이 분석 차트 생성
    runtime_analysis_low, runtime_analysis_high = analyze_runway(df)
    if runtime_analysis_low:
        html_content += f"""
            <div class="chart-container">
                <h2>⚠️ 재고 부족 약품 (런웨이 3개월 이하)</h2>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <div>
                        <button onclick="changePage('low', -1)" id="prev-low" class="nav-btn">◀ 이전</button>
                        <span id="page-info-low" style="margin: 0 20px;"></span>
                        <button onclick="changePage('low', 1)" id="next-low" class="nav-btn">다음 ▶</button>
                    </div>
                </div>
                <div id="runway-chart-low"></div>
            </div>
            <script>
                {runtime_analysis_low}
            </script>
        """
    
    if runtime_analysis_high:
        html_content += f"""
            <div class="chart-container">
                <h2>✅ 재고 충분 약품 (런웨이 3개월 초과)</h2>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <div>
                        <button onclick="changePage('high', -1)" id="prev-high" class="nav-btn">◀ 이전</button>
                        <span id="page-info-high" style="margin: 0 20px;"></span>
                        <button onclick="changePage('high', 1)" id="next-high" class="nav-btn">다음 ▶</button>
                    </div>
                </div>
                <div id="runway-chart-high"></div>
            </div>
            <script>
                {runtime_analysis_high}
            </script>
        """
    
    # 테이블 생성
    html_content += """
            <h2>📋 약품 목록</h2>
            <input type="text" class="search-box" id="searchInput" placeholder="약품명, 제약회사, 약품코드로 검색...">

            <div class="table-container">
                <table id="dataTable">
                    <thead>
                        <tr>
                            <th>약품명</th>
                            <th>제약회사</th>
                            <th>약품코드</th>
                            <th>재고수량</th>
                            <th>월평균 조제수량</th>
                            <th class="runway-header">런웨이</th>
                            <th>3개월 이동평균</th>
                            <th class="runway-header">3-MA 런웨이</th>
                            <th>트렌드</th>
                        </tr>
                    </thead>
                    <tbody>
    """

    # 월평균 조제수량 기준 내림차순 정렬
    df_sorted = df.sort_values('월평균_조제수량', ascending=False).reset_index(drop=True)

    # 데이터 행 추가 + 경량 스파크라인 생성
    for idx, row in df_sorted.iterrows():
        runway_class = get_runway_class(row['런웨이'])

        # 경량 SVG 스파크라인 생성
        timeseries = row['월별_조제수량_리스트']
        ma3 = row['3개월_이동평균_리스트']
        sparkline_html = create_sparkline_svg(timeseries, ma3)

        # 3개월 이동평균 (최신값)
        latest_ma3 = None
        for val in reversed(ma3):
            if val is not None:
                latest_ma3 = val
                break

        # 3-MA 런웨이 계산
        ma3_runway_display = "N/A"
        if latest_ma3 and latest_ma3 > 0:
            ma3_runway_months = row['최종_재고수량'] / latest_ma3
            if ma3_runway_months >= 1:
                ma3_runway_display = f"{ma3_runway_months:.2f}개월"
            else:
                ma3_runway_days = ma3_runway_months * 30.417
                ma3_runway_display = f"{ma3_runway_days:.2f}일"

        # 차트 데이터를 JSON으로 변환 (모달에서 사용)
        chart_data_json = create_chart_data_json(
            months=months,
            timeseries_data=timeseries,
            ma3_data=ma3,
            avg=row['월평균_조제수량'],
            drug_name=row['약품명'],
            drug_code=str(row['약품코드'])
        )

        modal_id = f"modal_{idx}"

        # 약품명 30자 제한
        drug_name_display = row['약품명']
        if len(drug_name_display) > 30:
            drug_name_display = drug_name_display[:30] + "..."

        # 제약회사 12자 제한
        company_display = row['제약회사']
        if len(company_display) > 12:
            company_display = company_display[:12] + "..."

        html_content += f"""
                        <tr class="{runway_class} clickable-row" onclick="openModalWithChart('{modal_id}', {idx})" data-chart-data='{chart_data_json}'>
                            <td>{drug_name_display}</td>
                            <td>{company_display}</td>
                            <td>{row['약품코드']}</td>
                            <td>{row['최종_재고수량']:,.0f}</td>
                            <td>{row['월평균_조제수량']:.2f}</td>
                            <td class="runway-cell">{row['런웨이']}</td>
                            <td>{"N/A" if latest_ma3 is None else f"{latest_ma3:.2f}"}</td>
                            <td class="runway-cell">{ma3_runway_display}</td>
                            <td>{sparkline_html}</td>
                        </tr>
        """

        # 3개월 이동평균 (최신값)
        ma3_list = row['3개월_이동평균_리스트']
        latest_ma3 = None
        for val in reversed(ma3_list):
            if val is not None:
                latest_ma3 = val
                break

        # 3-MA 런웨이 계산
        ma3_runway = "N/A"
        if latest_ma3 and latest_ma3 > 0:
            ma3_runway_months = row['최종_재고수량'] / latest_ma3
            if ma3_runway_months >= 1:
                ma3_runway = f"{ma3_runway_months:.2f}개월"
            else:
                ma3_runway_days = ma3_runway_months * 30.417
                ma3_runway = f"{ma3_runway_days:.2f}일"

        # 빈 모달 컨테이너 (차트는 클릭시 동적 생성)
        html_content += f"""
                        <div id="{modal_id}" class="modal">
                            <div class="modal-content">
                                <span class="close-btn" onclick="closeModal('{modal_id}')">&times;</span>
                                <h2 style="margin-bottom: 20px;">{row['약품명']} ({row['약품코드']})</h2>
                                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 30px;">
                                    <div style="background: linear-gradient(135deg, #e0e0e0 0%, #d0d0d0 100%); color: #2d3748; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                                        <h4 style="margin: 0 0 10px 0; font-size: 0.9em; opacity: 0.8;">재고수량</h4>
                                        <div style="font-size: 1.8em; font-weight: bold;">{row['최종_재고수량']:,.0f}개</div>
                                    </div>
                                    <div style="background: linear-gradient(135deg, #e0e0e0 0%, #d0d0d0 100%); color: #2d3748; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                                        <h4 style="margin: 0 0 10px 0; font-size: 0.9em; opacity: 0.8;">월평균 조제수량</h4>
                                        <div style="font-size: 1.8em; font-weight: bold;">{row['월평균_조제수량']:.1f}개</div>
                                    </div>
                                    <div style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                                        <h4 style="margin: 0 0 10px 0; font-size: 0.9em; opacity: 0.9;">런웨이</h4>
                                        <div style="font-size: 1.8em; font-weight: bold;">{row['런웨이']}</div>
                                    </div>
                                    <div style="background: linear-gradient(135deg, #e0e0e0 0%, #d0d0d0 100%); color: #2d3748; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                                        <h4 style="margin: 0 0 10px 0; font-size: 0.9em; opacity: 0.8;">3개월 이동평균</h4>
                                        <div style="font-size: 1.8em; font-weight: bold;">{"N/A" if latest_ma3 is None else f"{latest_ma3:.1f}개"}</div>
                                    </div>
                                    <div style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                                        <h4 style="margin: 0 0 10px 0; font-size: 0.9em; opacity: 0.9;">3-MA 런웨이</h4>
                                        <div style="font-size: 1.8em; font-weight: bold;">{ma3_runway}</div>
                                    </div>
                                </div>
                                <div id="chart-container-{idx}" style="width:100%;height:500px;"></div>
                            </div>
                        </div>
        """
    
    # HTML 마무리
    html_content += """
                    </tbody>
                </table>
            </div>
        </div>
        
        <script>
            // 검색 기능
            document.getElementById('searchInput').addEventListener('keyup', function() {
                const searchValue = this.value.toLowerCase();
                const rows = document.querySelectorAll('#dataTable tbody tr.clickable-row');

                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    row.style.display = text.includes(searchValue) ? '' : 'none';
                });
            });

            // 차트 캐시 (한번 생성한 차트는 재사용)
            const chartCache = {};

            // 모달 열기 + Plotly 차트 동적 생성
            function openModalWithChart(modalId, rowIndex) {
                const modal = document.getElementById(modalId);
                const chartContainer = document.getElementById('chart-container-' + rowIndex);

                // 모달 표시
                modal.style.display = 'block';

                // 이미 차트가 생성되었으면 재사용
                if (chartCache[rowIndex]) {
                    return;
                }

                // 차트 데이터 가져오기
                const rows = document.querySelectorAll('#dataTable tbody tr.clickable-row');
                const row = rows[rowIndex];
                const chartData = JSON.parse(row.getAttribute('data-chart-data'));

                // Plotly 차트 생성
                // null은 그대로 유지 (처음 2개월은 표시 안 함)
                const ma3Clean = chartData.ma3;

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
                        marker: {size: 8, color: 'black'}
                    },
                    {
                        x: chartData.months,
                        y: ma3Clean,
                        mode: 'lines',
                        name: '3개월 이동평균',
                        line: {color: 'orange', width: 3}
                    }
                ];

                const layout = {
                    title: chartData.drug_name + ' (' + chartData.drug_code + ') 월별 조제수량 추이',
                    xaxis: {
                        title: '월',
                        showgrid: true,
                        gridwidth: 1,
                        gridcolor: 'lightgray'
                    },
                    yaxis: {
                        title: '조제수량',
                        showgrid: true,
                        gridwidth: 1,
                        gridcolor: 'lightgray'
                    },
                    height: 500,
                    hovermode: 'x unified',
                    plot_bgcolor: 'white',
                    paper_bgcolor: 'white',
                    font: {size: 12},
                    shapes: [{
                        type: 'line',
                        x0: chartData.months[0],
                        x1: chartData.months[chartData.months.length - 1],
                        y0: chartData.avg,
                        y1: chartData.avg,
                        line: {
                            color: 'green',
                            width: 2,
                            dash: 'dash'
                        }
                    }],
                    annotations: [
                        {
                            x: chartData.months[chartData.months.length - 1],
                            y: chartData.avg,
                            text: '평균: ' + chartData.avg.toFixed(1),
                            showarrow: false,
                            xanchor: 'left',
                            xshift: 10
                        },
                        {
                            x: maxMonth,
                            y: maxValue,
                            text: '최대: ' + maxValue.toFixed(0),
                            showarrow: true,
                            arrowhead: 2,
                            arrowsize: 1,
                            arrowwidth: 2,
                            arrowcolor: 'red',
                            ax: 0,
                            ay: -40,
                            bgcolor: 'rgba(255, 255, 255, 0.9)',
                            bordercolor: 'red',
                            borderwidth: 2,
                            borderpad: 4,
                            font: {color: 'red', size: 12, weight: 'bold'}
                        }
                    ]
                };

                Plotly.newPlot(chartContainer, traces, layout, {displayModeBar: true});

                // 차트 캐시에 저장
                chartCache[rowIndex] = true;
            }

            function closeModal(modalId) {
                document.getElementById(modalId).style.display = 'none';
            }

            // 모달 외부 클릭시 닫기
            window.onclick = function(event) {
                if (event.target.classList.contains('modal')) {
                    event.target.style.display = 'none';
                }
            }
        </script>
    </body>
    </html>
    """
    
    return html_content

def get_runway_class(runway):
    """런웨이 값에 따라 CSS 클래스 결정"""
    if '일' in runway:
        # 30일 미만이면 경고
        try:
            days = float(runway.replace('일', ''))
            if days < 30:
                return 'warning'
        except:
            pass
    return ''

def analyze_runway(df):
    """런웨이 분포 분석 차트 생성 (페이지네이션 지원)"""
    try:
        # 런웨이를 숫자로 변환 (개월 단위)
        low_data = []  # 3개월 이하
        high_data = []  # 3개월 초과
        
        for _, row in df.iterrows():
            runway = row['런웨이']
            months = None
            
            if '개월' in runway:
                months = float(runway.replace('개월', ''))
            elif '일' in runway:
                days = float(runway.replace('일', ''))
                months = days / 30.417
            
            if months and months > 0:
                if months <= 3:
                    low_data.append((months, row['약품명']))
                else:
                    high_data.append((months, row['약품명']))
        
        chart_js_low = None
        chart_js_high = None
        
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
                    
                    var values = pageData.map(function(item) {{ return item[0]; }});
                    var names = pageData.map(function(item) {{ return item[1]; }});
                    
                    // 하위 그룹: 런웨이가 짧은 것이 위에 오도록 역순
                    values.reverse();
                    names.reverse();
                    
                    var data = [{{
                        x: values,
                        y: names,
                        type: 'bar',
                        orientation: 'h',
                        text: values,
                        texttemplate: '%{{text:.2f}}개월',
                        textposition: 'outside',
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
                    
                    var values = pageData.map(function(item) {{ return item[0]; }});
                    var names = pageData.map(function(item) {{ return item[1]; }});
                    
                    // 상위 그룹: 런웨이가 긴 것이 위에 오도록 역순
                    values.reverse();
                    names.reverse();
                    
                    var data = [{{
                        x: values,
                        y: names,
                        type: 'bar',
                        orientation: 'h',
                        text: values,
                        texttemplate: '%{{text:.2f}}개월',
                        textposition: 'outside',
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
        
        return chart_js_low, chart_js_high
    except Exception as e:
        print(f"Error in analyze_runway: {e}")
        pass
    return None, None

def create_and_save_report(df, months, open_browser=True):
    """보고서를 생성하고 파일로 저장하는 함수

    Args:
        df: DataFrame (시계열 데이터 포함)
        months: 월 리스트 또는 개월 수 (하위 호환성)
        open_browser: 브라우저에서 자동으로 열기 여부
    """
    # HTML 보고서 생성
    html_content = generate_html_report(df, months)

    # 파일로 저장
    output_path = f'inventory_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
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

        # 사용자에게 데이터 기간 물어보기
        while True:
            try:
                m = int(input("보고서를 생성할 데이터 기간(개월): "))
                if m > 0:
                    break
            except ValueError:
                print("올바른 숫자를 입력해주세요.")

        # 보고서 생성 및 저장
        create_and_save_report(df, m)

    else:
        print(f"❌ {csv_path} 파일을 찾을 수 없습니다.")
        print("먼저 read_excel.py를 실행하여 CSV 파일을 생성해주세요.")

if __name__ == "__main__":
    main()