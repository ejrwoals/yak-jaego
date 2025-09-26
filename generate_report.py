import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from datetime import datetime

def generate_html_report(df, m):
    """
    DataFrame을 HTML 보고서로 생성
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
            td {{
                padding: 10px 12px;
                border-bottom: 1px solid #e2e8f0;
            }}
            tr:hover {{
                background: #f7fafc;
            }}
            .warning {{
                background: #fff5f5;
                color: #c53030;
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
                    <div class="value">{m}개월</div>
                </div>
                <div class="summary-card">
                    <h3>총 재고 수량</h3>
                    <div class="value">{df['재고수량'].sum():,.0f}개</div>
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
                            <th>런웨이</th>
                        </tr>
                    </thead>
                    <tbody>
    """
    
    # 데이터 행 추가
    for _, row in df.iterrows():
        runway_class = get_runway_class(row['런웨이'])
        html_content += f"""
                        <tr class="{runway_class}">
                            <td>{row['약품명']}</td>
                            <td>{row['제약회사']}</td>
                            <td>{row['약품코드']}</td>
                            <td>{row['재고수량']:,.0f}</td>
                            <td>{row['월평균_조제수량']:.2f}</td>
                            <td>{row['런웨이']}</td>
                        </tr>
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
                const rows = document.querySelectorAll('#dataTable tbody tr');
                
                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    row.style.display = text.includes(searchValue) ? '' : 'none';
                });
            });
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

def create_and_save_report(df, m, open_browser=True):
    """보고서를 생성하고 파일로 저장하는 함수"""
    # HTML 보고서 생성
    html_content = generate_html_report(df, m)

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