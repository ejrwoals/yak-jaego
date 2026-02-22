from html import escape as html_escape
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from datetime import datetime
import json
import paths
import inventory_db
import checked_items_db
import drug_memos_db
import drug_thresholds_db

def get_usage_period_info(timeseries):
    """
    시계열 데이터에서 첫 사용 시점과 사용 기간 정보를 반환

    Returns:
        tuple: (first_usage_idx, usage_months)
        - first_usage_idx: 첫 사용 시점 인덱스 (None이면 사용 이력 없음)
        - usage_months: 첫 사용 시점부터 현재까지의 개월 수
    """
    first_usage_idx = None
    for i, val in enumerate(timeseries):
        if val is not None and val > 0:
            first_usage_idx = i
            break

    if first_usage_idx is None:
        return None, 0

    usage_months = len(timeseries) - first_usage_idx
    return first_usage_idx, usage_months


def get_corrected_ma(timeseries, n_months):
    """
    보정된 N개월 이동평균의 최신값을 반환

    신규 약품(사용 기간 < n_months)의 경우:
    - 실제 사용 기간으로 나눠서 계산

    Returns:
        tuple: (latest_ma, usage_months, is_corrected)
        - latest_ma: 보정된 최신 이동평균
        - usage_months: 첫 사용 시점부터 현재까지의 개월 수
        - is_corrected: 보정이 적용되었는지 여부
    """
    first_usage_idx, usage_months = get_usage_period_info(timeseries)

    # 사용 이력이 없으면
    if first_usage_idx is None:
        return None, 0, False

    # 신규 약품: 사용 기간 < n_months
    is_corrected = usage_months < n_months

    if is_corrected:
        # 첫 사용 시점부터 끝까지의 평균
        window = timeseries[first_usage_idx:]
        latest_ma = sum(window) / len(window)
    else:
        # 기존 방식: 최근 n_months의 평균
        window = timeseries[-n_months:]
        latest_ma = sum(window) / n_months

    return latest_ma, usage_months, is_corrected


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

    # 실제 값 라인 (회색 점선)
    points = []
    for i, val in enumerate(timeseries_data):
        x = scale_x(i, len(timeseries_data))
        y = scale_y(val)
        points.append(f"{x:.2f},{y:.2f}")

    actual_line = f'<polyline points="{" ".join(points)}" fill="none" stroke="#a1a1aa" stroke-width="1" stroke-dasharray="2,2" />'

    # N개월 이동평균 라인 (브랜드 색상 실선)
    ma_line = ''
    if ma_data and any(v is not None for v in ma_data):
        ma_points = []
        for i, val in enumerate(ma_data):
            if val is not None:
                x = scale_x(i, len(ma_data))
                y = scale_y(val)
                ma_points.append(f"{x:.2f},{y:.2f}")

        if ma_points:
            ma_line = f'<polyline points="{" ".join(ma_points)}" fill="none" stroke="#475569" stroke-width="2" />'

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

def generate_html_report(df, months, mode='dispense', ma_months=3, threshold_low=3, threshold_high=12):
    """
    DataFrame을 HTML 보고서로 생성 (Single MA 버전)
    months: 월 리스트 (예: ['2025-01', '2025-02', ...])
    mode: 'dispense' (전문약) 또는 'sale' (일반약)
    ma_months: 이동평균 개월 수
    threshold_low: 부족/충분 경계 (개월)
    threshold_high: 충분/과다 경계 (개월)
    """

    # 모드에 따른 제목 설정
    mode_titles = {
        'dispense': f'전문약 재고 관리 보고서 ({ma_months}개월 이동평균)',
        'sale': f'일반약 재고 관리 보고서 ({ma_months}개월 이동평균)'
    }
    report_title = mode_titles.get(mode, f'약품 재고 관리 보고서 ({ma_months}개월 이동평균)')

    # 개별 임계값 데이터 로드
    custom_thresholds = drug_thresholds_db.get_threshold_dict()

    # HTML 템플릿 시작
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{report_title}</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
        <style>
            /* ===== Design Tokens from design-principles.md ===== */
            :root {{
                /* 브랜드 Primary - 차분하고 모던한 슬레이트 블루 */
                --brand-primary: #475569;
                --brand-primary-dark: #334155;
                --brand-primary-light: #64748b;
                --brand-primary-subtle: #f1f5f9;

                /* 시맨틱 색상 */
                --color-success: #10b981;
                --color-success-dark: #059669;
                --color-success-light: #d1fae5;
                --color-danger: #ef4444;
                --color-danger-dark: #dc2626;
                --color-danger-light: #fee2e2;
                --color-warning: #f59e0b;
                --color-warning-dark: #d97706;
                --color-warning-light: #fef3c7;
                --color-info: #3b82f6;
                --color-info-dark: #2563eb;
                --color-info-light: #dbeafe;

                /* 재고 상태 색상 */
                --status-shortage: #ef4444;
                --status-shortage-bg: #fef2f2;
                --status-sufficient: #22c55e;
                --status-sufficient-bg: #f0fdf4;
                --status-excess: #3b82f6;
                --status-excess-bg: #eff6ff;

                /* 텍스트 계층 */
                --text-primary: #18181b;
                --text-secondary: #52525b;
                --text-muted: #a1a1aa;
                --text-disabled: #d4d4d8;

                /* 배경 계층 */
                --bg-page: #fafafa;
                --bg-surface: #ffffff;
                --bg-subtle: #f4f4f5;
                --bg-hover: #e4e4e7;

                /* 테두리 */
                --border-default: #e4e4e7;
                --border-strong: #d4d4d8;
                --border-subtle: #f4f4f5;

                /* 간격 */
                --space-1: 0.25rem;
                --space-2: 0.5rem;
                --space-3: 0.75rem;
                --space-4: 1rem;
                --space-5: 1.25rem;
                --space-6: 1.5rem;
                --space-8: 2rem;

                /* 그림자 */
                --shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.05);
                --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06);
                --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.1), 0 2px 4px rgba(0, 0, 0, 0.06);
                --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.1), 0 4px 6px rgba(0, 0, 0, 0.05);
                --shadow-xl: 0 20px 25px rgba(0, 0, 0, 0.1), 0 10px 10px rgba(0, 0, 0, 0.04);

                /* 모서리 곡률 */
                --radius-sm: 4px;
                --radius-md: 6px;
                --radius-lg: 8px;
                --radius-xl: 12px;

                /* 트랜지션 */
                --duration-fast: 100ms;
                --duration-normal: 200ms;
                --ease-out: cubic-bezier(0, 0, 0.2, 1);
            }}

            /* ===== Base Styles ===== */
            body {{
                font-family: 'Pretendard', 'Noto Sans KR', -apple-system, BlinkMacSystemFont, sans-serif;
                margin: 0;
                padding: var(--space-6);
                background: var(--bg-page);
                min-height: 100vh;
                color: var(--text-primary);
                line-height: 1.5;
            }}

            .container {{
                max-width: 1400px;
                margin: 0 auto;
                background: var(--bg-surface);
                border-radius: var(--radius-xl);
                box-shadow: var(--shadow-lg);
                padding: var(--space-8);
                border: 1px solid var(--border-subtle);
            }}

            h1 {{
                color: var(--text-primary);
                text-align: center;
                margin-bottom: var(--space-3);
                font-size: 1.875rem;
                font-weight: 700;
                letter-spacing: -0.025em;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
            }}

            h2 {{
                color: var(--text-primary);
                font-size: 1.25rem;
                font-weight: 600;
                margin: var(--space-6) 0 var(--space-4) 0;
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }}

            .date {{
                text-align: left;
                color: var(--text-muted);
                margin-bottom: var(--space-2);
                font-size: 0.875rem;
            }}

            /* ===== Icon Styles ===== */
            .icon {{
                width: 20px;
                height: 20px;
                stroke-width: 2;
                stroke-linecap: round;
                stroke-linejoin: round;
                flex-shrink: 0;
            }}
            .icon-sm {{ width: 16px; height: 16px; }}
            .icon-lg {{ width: 24px; height: 24px; }}
            .icon-xl {{ width: 32px; height: 32px; }}

            /* ===== Summary Cards (Unused but kept for compatibility) ===== */
            .summary-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: var(--space-5);
                margin: var(--space-6) 0;
            }}

            .summary-card {{
                background: var(--bg-subtle);
                padding: var(--space-6);
                border-radius: var(--radius-lg);
                box-shadow: var(--shadow-xs);
                border: 1px solid var(--border-subtle);
            }}

            .summary-card h3 {{
                margin: 0 0 var(--space-2) 0;
                font-size: 0.875rem;
                color: var(--text-muted);
                font-weight: 500;
            }}

            .summary-card .value {{
                font-size: 1.5rem;
                font-weight: 700;
                color: var(--text-primary);
            }}

            /* ===== Table Styles ===== */
            .table-container {{
                margin: var(--space-6) 0;
                overflow-x: auto;
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-default);
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 0.875rem;
            }}

            th {{
                background: var(--brand-primary);
                color: white;
                padding: var(--space-3) var(--space-4);
                text-align: left;
                position: sticky;
                top: 0;
                font-weight: 600;
                font-size: 0.75rem;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }}

            th.runway-header {{
                background: var(--brand-primary-light);
            }}

            td {{
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--border-default);
                color: var(--text-secondary);
            }}

            td.runway-cell {{
                background: var(--bg-subtle);
                font-weight: 600;
            }}

            tr:hover {{
                background: var(--bg-hover);
            }}

            tr:hover td.runway-cell {{
                background: var(--border-default);
            }}

            .warning {{
                background: var(--color-danger-light);
            }}

            .warning td {{
                color: var(--color-danger-dark);
            }}

            .warning td.runway-cell {{
                background: rgba(254, 226, 226, 0.7);
            }}

            .good {{
                background: var(--color-success-light);
            }}

            .good td {{
                color: var(--color-success-dark);
            }}

            /* ===== Search Box ===== */
            .search-box {{
                margin: var(--space-4) 0;
                padding: var(--space-3) var(--space-4);
                width: 100%;
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md);
                font-size: 1rem;
                color: var(--text-primary);
                background: var(--bg-surface);
                transition: border-color var(--duration-fast) var(--ease-out),
                            box-shadow var(--duration-fast) var(--ease-out);
                box-sizing: border-box;
            }}

            .search-box:hover {{
                border-color: var(--border-strong);
            }}

            .search-box:focus {{
                outline: none;
                border-color: var(--brand-primary);
                box-shadow: 0 0 0 3px var(--brand-primary-subtle);
            }}

            .search-box::placeholder {{
                color: var(--text-muted);
            }}

            /* ===== Chart Container ===== */
            .chart-container {{
                margin: var(--space-6) 0;
                padding: var(--space-5);
                background: var(--bg-subtle);
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-subtle);
            }}

            /* ===== Buttons ===== */
            .nav-btn {{
                background: var(--brand-primary);
                color: white;
                border: none;
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-md);
                cursor: pointer;
                font-size: 0.875rem;
                font-weight: 600;
                transition: all var(--duration-fast) var(--ease-out);
            }}

            .nav-btn:hover {{
                background: var(--brand-primary-dark);
                transform: translateY(-1px);
                box-shadow: var(--shadow-sm);
            }}

            .nav-btn:active {{
                transform: translateY(0);
            }}

            .nav-btn:disabled {{
                background: var(--text-disabled);
                cursor: not-allowed;
                transform: none;
            }}

            /* ===== Modal Styles ===== */
            .modal {{
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                overflow: auto;
                background-color: rgba(0, 0, 0, 0.5);
                animation: fadeIn var(--duration-normal) var(--ease-out);
            }}

            .modal-content {{
                background-color: var(--bg-surface);
                margin: 5% auto;
                padding: var(--space-6);
                border-radius: var(--radius-xl);
                width: 90%;
                max-width: 1200px;
                box-shadow: var(--shadow-xl);
                animation: scaleIn 300ms cubic-bezier(0.34, 1.56, 0.64, 1);
            }}

            @keyframes scaleIn {{
                from {{
                    opacity: 0;
                    transform: scale(0.95);
                }}
                to {{
                    opacity: 1;
                    transform: scale(1);
                }}
            }}

            .close-btn {{
                color: var(--text-muted);
                float: right;
                font-size: 1.5rem;
                font-weight: bold;
                cursor: pointer;
                line-height: 1;
                transition: color var(--duration-fast) var(--ease-out);
            }}

            .close-btn:hover {{
                color: var(--text-primary);
            }}

            /* ===== Clickable Row Styles ===== */
            .clickable-row {{
                cursor: pointer;
            }}

            .clickable-row:hover {{
                background: var(--bg-hover) !important;
            }}

            /* ===== Toggle Section Styles ===== */
            .toggle-header {{
                cursor: pointer;
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: var(--space-4) var(--space-5);
                user-select: none;
                background: var(--bg-subtle);
                border-radius: var(--radius-lg);
                transition: background var(--duration-normal) var(--ease-out);
            }}

            .toggle-header:hover {{
                background: var(--bg-hover);
            }}

            .toggle-icon {{
                font-size: 1.25rem;
                font-weight: bold;
                transition: transform var(--duration-normal) var(--ease-out);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-muted);
                width: 24px;
                height: 24px;
            }}

            .toggle-icon.collapsed {{
                transform: rotate(-90deg);
            }}

            .toggle-content {{
                max-height: 10000px;
                overflow: hidden;
                transition: max-height var(--duration-normal) var(--ease-out),
                            opacity var(--duration-normal) var(--ease-out);
                opacity: 1;
            }}

            .toggle-content.collapsed {{
                max-height: 0;
                opacity: 0;
            }}

            /* ===== Checked Row ===== */
            .checked-row {{
                background: var(--bg-subtle) !important;
                opacity: 0.6;
            }}

            .checked-row td {{
                color: var(--text-muted) !important;
            }}

            /* ===== Inline Chart Row Styles ===== */
            .tab-clickable-row {{
                cursor: pointer;
                transition: background-color var(--duration-fast) var(--ease-out);
            }}

            .tab-clickable-row:hover {{
                background-color: var(--brand-primary-subtle) !important;
            }}

            .tab-clickable-row.chart-expanded {{
                background-color: var(--brand-primary-subtle) !important;
                border-left: 3px solid var(--brand-primary);
            }}

            .inline-chart-row {{
                background: var(--bg-subtle);
            }}

            .inline-chart-row:hover {{
                background: var(--bg-subtle) !important;
            }}

            /* ===== Memo Button ===== */
            .memo-btn {{
                background: transparent;
                border: 1px solid var(--border-default);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
                cursor: pointer;
                font-size: 0.875rem;
                transition: all var(--duration-fast) var(--ease-out);
                color: var(--text-muted);
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }}

            .memo-btn:hover {{
                border-color: var(--brand-primary);
                color: var(--brand-primary);
            }}

            .memo-btn.has-memo {{
                border-color: var(--color-warning);
                color: var(--color-warning);
                background: var(--color-warning-light);
            }}

            .memo-btn.has-memo:hover {{
                border-color: var(--color-warning-dark);
                color: var(--color-warning-dark);
            }}

            /* ===== Threshold Indicator ===== */
            .threshold-indicator {{
                margin-right: var(--space-2);
                cursor: pointer;
                opacity: 0.7;
                display: inline-flex;
                align-items: center;
                transition: opacity var(--duration-fast) var(--ease-out);
            }}

            .threshold-indicator:hover {{
                opacity: 1;
            }}

            /* ===== New Drug Tag ===== */
            .new-drug-tag {{
                display: inline-flex;
                align-items: center;
                gap: 3px;
                background: var(--color-info);
                color: white;
                font-size: 0.625rem;
                padding: 2px 6px;
                border-radius: var(--radius-sm);
                margin-left: var(--space-2);
                font-weight: 500;
                vertical-align: middle;
            }}

            .new-drug-tag .help-icon {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 14px;
                height: 14px;
                background: rgba(255,255,255,0.3);
                border-radius: 50%;
                font-size: 9px;
                cursor: pointer;
                transition: background var(--duration-fast) var(--ease-out);
            }}

            .new-drug-tag .help-icon:hover {{
                background: rgba(255,255,255,0.5);
            }}

            /* ===== Threshold Tooltip ===== */
            .threshold-tooltip-floating {{
                position: fixed;
                background: var(--brand-primary-dark);
                color: white;
                padding: var(--space-3) var(--space-4);
                border-radius: var(--radius-lg);
                font-size: 0.75rem;
                white-space: pre-line;
                font-weight: normal;
                line-height: 1.5;
                box-shadow: var(--shadow-lg);
                z-index: 9999;
                pointer-events: none;
            }}

            /* ===== Checkbox Memo Container ===== */
            .checkbox-memo-container {{
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }}

            /* ===== Visibility Button ===== */
            .visibility-btn {{
                background: none;
                border: 1px solid var(--border-default);
                border-radius: var(--radius-sm);
                padding: var(--space-1) var(--space-2);
                cursor: pointer;
                transition: all var(--duration-fast) var(--ease-out);
                color: var(--text-secondary);
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }}

            .visibility-btn:hover {{
                border-color: var(--brand-primary);
                background: var(--brand-primary-subtle);
            }}

            .visibility-btn.hidden {{
                color: var(--text-muted);
                border-color: var(--border-subtle);
                background: var(--bg-subtle);
            }}

            .visibility-btn.hidden:hover {{
                color: var(--color-success-dark, #276749);
                border-color: var(--color-success, #48bb78);
                background: var(--color-success-subtle, #f0fff4);
            }}

            /* ===== Process Status Badge ===== */
            .process-status-badge {{
                display: inline-block;
                padding: 2px 8px;
                border-radius: var(--radius-sm);
                font-size: 0.75rem;
                font-weight: 600;
                background: var(--color-warning-subtle, #fffbeb);
                color: var(--color-warning-dark, #92400e);
                border: 1px solid var(--color-warning, #f59e0b);
            }}
            .process-status-badge.status-처리중 {{
                background: var(--color-info-subtle, #eff6ff);
                color: var(--color-info-dark, #1e40af);
                border-color: var(--color-info, #3b82f6);
            }}
            .process-status-badge.status-완료 {{
                background: var(--color-success-subtle, #f0fdf4);
                color: var(--color-success-dark, #166534);
                border-color: var(--color-success, #22c55e);
            }}
            .process-status-badge.status-보류 {{
                background: var(--bg-surface, #f9fafb);
                color: var(--text-muted, #6b7280);
                border-color: var(--border-default, #e5e7eb);
            }}

            /* ===== Hidden Row ===== */
            .hidden-row {{
                background: var(--bg-subtle) !important;
                opacity: 0.6;
            }}

            .hidden-row td {{
                color: var(--text-muted) !important;
            }}

            .hidden-row .visibility-btn {{
                color: var(--text-muted);
            }}

            /* ===== Bookmark Sidebar ===== */
            .bookmark-sidebar {{
                position: fixed;
                right: 0;
                top: 50%;
                transform: translateY(-50%);
                z-index: 900;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }}

            .bookmark-item {{
                position: relative;
                right: -130px;
                padding: var(--space-3) var(--space-4);
                border-radius: var(--radius-lg) 0 0 var(--radius-lg);
                cursor: pointer;
                transition: right var(--duration-normal) var(--ease-out),
                            box-shadow var(--duration-normal) var(--ease-out);
                box-shadow: var(--shadow-md);
                min-width: 140px;
                color: white;
                font-weight: 600;
                font-size: 0.875rem;
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-1);
                user-select: none;
            }}

            .bookmark-item:hover {{
                right: 0;
                box-shadow: var(--shadow-lg);
            }}

            .bookmark-item .bookmark-icon {{
                display: flex;
                align-items: center;
                justify-content: center;
                width: 12px;
                height: 12px;
                border-radius: 50%;
                background: rgba(255, 255, 255, 0.9);
            }}

            .bookmark-item .bookmark-title {{
                font-size: 0.875rem;
                font-weight: 500;
            }}

            .bookmark-item .bookmark-count {{
                font-size: 1.5rem;
                font-weight: 700;
                text-align: center;
            }}

            .bookmark-urgent {{
                background: var(--color-danger);
            }}
            .bookmark-urgent .bookmark-icon {{
                background: var(--color-danger-dark);
            }}

            .bookmark-low {{
                background: var(--color-warning);
            }}
            .bookmark-low .bookmark-icon {{
                background: var(--color-warning-dark);
            }}

            .bookmark-high {{
                background: var(--color-success);
            }}
            .bookmark-high .bookmark-icon {{
                background: var(--color-success-dark);
            }}

            .bookmark-excess {{
                background: var(--color-info);
            }}
            .bookmark-excess .bookmark-icon {{
                background: var(--color-info-dark);
            }}

            .bookmark-dead {{
                background: var(--text-muted);
            }}
            .bookmark-dead .bookmark-icon {{
                background: var(--text-secondary);
            }}

            /* ===== Category Modal ===== */
            .category-modal {{
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                overflow: auto;
                background-color: rgba(0, 0, 0, 0.5);
                animation: fadeIn var(--duration-normal) var(--ease-out);
            }}

            @keyframes fadeIn {{
                from {{ opacity: 0; }}
                to {{ opacity: 1; }}
            }}

            .category-modal-content {{
                background-color: var(--bg-surface);
                margin: 3% auto;
                padding: var(--space-8);
                border-radius: var(--radius-xl);
                width: 90%;
                max-width: 1400px;
                max-height: 85vh;
                overflow-y: auto;
                box-shadow: var(--shadow-xl);
                animation: slideUp 300ms cubic-bezier(0.34, 1.56, 0.64, 1);
            }}

            @keyframes slideUp {{
                from {{
                    transform: translateY(20px);
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
                margin-bottom: var(--space-6);
                padding-bottom: var(--space-5);
                border-bottom: 1px solid var(--border-default);
            }}

            .category-modal-header h2 {{
                margin: 0;
                font-size: 1.25rem;
            }}

            .category-modal-close {{
                color: var(--text-muted);
                font-size: 1.75rem;
                font-weight: bold;
                cursor: pointer;
                line-height: 1;
                transition: color var(--duration-fast) var(--ease-out);
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
            }}

            .category-modal-close:hover {{
                color: var(--text-primary);
                background: var(--bg-hover);
            }}

            /* ===== Alert Banner ===== */
            .alert-banner {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-4) var(--space-5);
                border-radius: var(--radius-lg);
                margin: var(--space-5) 0;
                border: 1px solid;
                position: relative;
                z-index: 950;
            }}

            .alert-banner-danger {{
                background: var(--color-danger-light);
                border-color: var(--color-danger);
            }}

            .alert-banner-warning {{
                background: var(--color-warning-light);
                border-color: var(--color-warning);
            }}

            /* ===== Status Distribution Bar ===== */
            .status-distribution {{
                margin: var(--space-6) 0;
                padding: var(--space-6);
                background: var(--bg-surface);
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-default);
            }}

            .status-distribution h2 {{
                margin: 0 0 var(--space-4) 0;
            }}

            .status-distribution-header {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-4);
            }}

            .status-distribution-header h2 {{
                margin: 0;
            }}

            .trash-shortcut-btn {{
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: var(--space-1) var(--space-3);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-sm);
                background: var(--bg-surface);
                color: var(--text-muted);
                font-size: 0.8rem;
                cursor: pointer;
                transition: all var(--duration-fast) var(--ease-out);
            }}

            .trash-shortcut-btn:hover {{
                border-color: var(--text-muted);
                background: var(--bg-subtle);
                color: var(--text-secondary);
            }}

            .distribution-bar {{
                display: flex;
                height: 40px;
                border-radius: var(--radius-md);
                overflow: hidden;
                box-shadow: var(--shadow-xs);
            }}

            .distribution-bar > div {{
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: 600;
                font-size: 0.875rem;
                transition: flex var(--duration-normal) var(--ease-out), opacity var(--duration-fast) var(--ease-out);
                cursor: pointer;
            }}

            .distribution-bar > div:hover {{
                opacity: 0.85;
            }}

            .distribution-legend {{
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-4);
                margin-top: var(--space-4);
                font-size: 0.875rem;
                color: var(--text-secondary);
            }}

            .legend-item {{
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }}

            .legend-dot {{
                width: 12px;
                height: 12px;
                border-radius: 2px;
            }}

            /* ===== Action Button (for banner) ===== */
            .btn-action {{
                padding: var(--space-2) var(--space-4);
                border: none;
                border-radius: var(--radius-md);
                cursor: pointer;
                font-weight: 600;
                font-size: 0.875rem;
                transition: all var(--duration-fast) var(--ease-out);
            }}

            .btn-action-danger {{
                background: var(--color-danger);
                color: white;
            }}

            .btn-action-danger:hover {{
                background: var(--color-danger-dark);
            }}
        </style>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    </head>
    <body>
        <div class="container">
            <h1>
                <svg class="icon icon-lg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" x2="18" y1="20" y2="10"/><line x1="12" x2="12" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="14"/>
                </svg>
                {report_title}
            </h1>
            <div class="date">생성일: {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}</div>
            <div class="date">데이터 기간: {months[0][:4]}년 {months[0][5:]}월 ~ {months[-1][:4]}년 {months[-1][5:]}월 (총 {len(months)}개월)</div>
    """

    # 특수 케이스 약품 분류
    urgent_drugs, dead_stock_drugs, negative_stock_drugs = classify_drugs_by_special_cases(df, ma_months)

    # 런웨이 분석 차트 생성 + 부족/충분/과다 약품 DataFrame
    _, _, _, low_count, high_count, excess_count, low_drugs_df, high_drugs_df, excess_drugs_df = analyze_runway(df, months, ma_months, threshold_low, threshold_high)

    # 전체 약품 수
    total_count = len(df)
    urgent_count = len(urgent_drugs) if not urgent_drugs.empty else 0
    dead_count = len(dead_stock_drugs) if not dead_stock_drugs.empty else 0
    negative_count = len(negative_stock_drugs) if not negative_stock_drugs.empty else 0

    # 숨김 처리된 약품 수 (체크된 항목)
    checked_items = checked_items_db.get_checked_items()
    checked_items_status = checked_items_db.get_checked_items_with_status()
    hidden_count = len(checked_items)
    pending_count = sum(1 for s in checked_items_status.values() if s == '대기중')

    # 음수 재고 경고 배너 (음수 재고가 있을 때만 표시)
    if negative_count > 0:
        html_content += f"""
        <!-- 음수 재고 경고 배너 -->
        <div id="negative-stock-banner" class="alert-banner alert-banner-danger">
            <div style="display: flex; align-items: center; gap: var(--space-3);">
                <svg class="icon icon-lg" viewBox="0 0 24 24" fill="none" stroke="var(--color-danger)" stroke-width="2">
                    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/>
                </svg>
                <div>
                    <span style="font-weight: 600; color: var(--color-danger-dark);">음수 재고 경고:</span>
                    <span style="color: var(--color-danger-dark); margin-left: var(--space-1);">{negative_count}개 약품의 재고가 음수입니다</span>
                </div>
            </div>
            <button onclick="openCategoryModal('negative-modal')" class="btn-action btn-action-danger">
                확인하기
            </button>
        </div>
        """

    # 통합 인디케이터 생성
    html_content += f"""
        <!-- 통합 재고 현황 인디케이터 -->
        <div class="status-distribution">
            <div class="status-distribution-header">
                <h2>
                    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" x2="18" y1="20" y2="10"/><line x1="12" x2="12" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="14"/>
                    </svg>
                    재고 현황 분포
                </h2>
                <button class="trash-shortcut-btn" onclick="openCategoryModal('hidden-modal')" title="휴지통 열기">
                    <svg style="width: 14px; height: 14px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
                    </svg>
                    휴지통 <span id="trash-shortcut-count">{pending_count}</span>
                </button>
            </div>
            <div id="proportion-graph" class="distribution-bar" data-total="{total_count}">
                <div id="proportion-bar-urgent" style="background: var(--color-danger); flex: {urgent_count};" title="긴급: {urgent_count}개 ({urgent_count/total_count*100:.1f}%)" onclick="openCategoryModal('urgent-modal')">
                    {urgent_count if urgent_count > 0 else ''}
                </div>
                <div id="proportion-bar-low" style="background: var(--color-warning); flex: {low_count};" title="부족: {low_count}개 ({low_count/total_count*100:.1f}%)" onclick="openCategoryModal('low-modal')">
                    {low_count if low_count > 0 else ''}
                </div>
                <div id="proportion-bar-high" style="background: var(--color-success); flex: {high_count};" title="충분: {high_count}개 ({high_count/total_count*100:.1f}%)" onclick="openCategoryModal('high-modal')">
                    {high_count if high_count > 0 else ''}
                </div>
                <div id="proportion-bar-excess" style="background: var(--color-info); flex: {excess_count};" title="과다: {excess_count}개 ({excess_count/total_count*100:.1f}%)" onclick="openCategoryModal('excess-modal')">
                    {excess_count if excess_count > 0 else ''}
                </div>
                <div id="proportion-bar-dead" style="background: var(--text-muted); flex: {dead_count};" title="악성재고: {dead_count}개 ({dead_count/total_count*100:.1f}%)" onclick="openCategoryModal('dead-modal')">
                    {dead_count if dead_count > 0 else ''}
                </div>
            </div>
            <div class="distribution-legend">
                <div class="legend-item">
                    <span class="legend-dot" style="background: var(--color-danger);"></span>
                    <span id="proportion-label-urgent">긴급: {urgent_count}개 ({urgent_count/total_count*100:.1f}%)</span>
                </div>
                <div class="legend-item">
                    <span class="legend-dot" style="background: var(--color-warning);"></span>
                    <span id="proportion-label-low">부족: {low_count}개 ({low_count/total_count*100:.1f}%)</span>
                </div>
                <div class="legend-item">
                    <span class="legend-dot" style="background: var(--color-success);"></span>
                    <span id="proportion-label-high">충분: {high_count}개 ({high_count/total_count*100:.1f}%)</span>
                </div>
                <div class="legend-item">
                    <span class="legend-dot" style="background: var(--color-info);"></span>
                    <span id="proportion-label-excess">과다: {excess_count}개 ({excess_count/total_count*100:.1f}%)</span>
                </div>
                <div class="legend-item">
                    <span class="legend-dot" style="background: var(--text-muted);"></span>
                    <span id="proportion-label-dead">악성재고: {dead_count}개 ({dead_count/total_count*100:.1f}%)</span>
                </div>
            </div>
        </div>

        <!-- 책갈피 사이드바 -->
        <div class="bookmark-sidebar">
            <div class="bookmark-item bookmark-urgent" onclick="openCategoryModal('urgent-modal')">
                <div class="bookmark-icon"></div>
                <div class="bookmark-title">긴급</div>
                <div class="bookmark-count">{urgent_count}</div>
            </div>
            <div class="bookmark-item bookmark-low" onclick="openCategoryModal('low-modal')">
                <div class="bookmark-icon"></div>
                <div class="bookmark-title">부족</div>
                <div class="bookmark-count">{low_count}</div>
            </div>
            <div class="bookmark-item bookmark-high" onclick="openCategoryModal('high-modal')">
                <div class="bookmark-icon"></div>
                <div class="bookmark-title">충분</div>
                <div class="bookmark-count">{high_count}</div>
            </div>
            <div class="bookmark-item bookmark-excess" onclick="openCategoryModal('excess-modal')">
                <div class="bookmark-icon"></div>
                <div class="bookmark-title">과다</div>
                <div class="bookmark-count">{excess_count}</div>
            </div>
            <div class="bookmark-item bookmark-dead" onclick="openCategoryModal('dead-modal')">
                <div class="bookmark-icon"></div>
                <div class="bookmark-title">악성재고</div>
                <div class="bookmark-count">{dead_count}</div>
            </div>
            <div class="bookmark-item bookmark-hidden" onclick="openCategoryModal('hidden-modal')" style="background: var(--bg-surface); border: 1px solid var(--border-default); color: var(--text-muted);">
                <div class="bookmark-icon" style="background: var(--border-default);"></div>
                <div class="bookmark-title">휴지통</div>
                <div class="bookmark-count">{hidden_count}</div>
            </div>
        </div>
    """

    # 모달 컨테이너 생성
    has_urgent = not urgent_drugs.empty
    has_low_runway = low_count > 0
    has_high_runway = high_count > 0
    has_excess_runway = excess_count > 0
    has_dead_stock = not dead_stock_drugs.empty

    # 긴급 약품 모달
    if has_urgent:
        urgent_section_html = generate_urgent_drugs_section(urgent_drugs, ma_months, months)
        html_content += f"""
            <!-- 긴급 약품 모달 -->
            <div id="urgent-modal" class="category-modal">
                <div class="category-modal-content">
                    <div class="category-modal-header">
                        <h2 style="color: var(--color-danger);">
                            <svg class="icon icon-lg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>
                            </svg>
                            긴급: 재고 0인 약품 ({ma_months}개월 내 사용이력 있음)
                        </h2>
                        <span class="category-modal-close" onclick="closeCategoryModal('urgent-modal')">&times;</span>
                    </div>
                    {urgent_section_html}
                </div>
            </div>
        """

    # 재고 부족 약품 모달 (테이블 + 차트 토글)
    if has_low_runway:
        low_section_html = generate_low_stock_section(low_drugs_df, ma_months, months, threshold_low)
        html_content += f"""
            <!-- 재고 부족 약품 모달 -->
            <div id="low-modal" class="category-modal">
                <div class="category-modal-content">
                    <div class="category-modal-header">
                        <h2 style="color: var(--color-warning-dark);">
                            <svg class="icon icon-lg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/>
                            </svg>
                            재고 부족 약품 (런웨이 {threshold_low}개월 이하)
                        </h2>
                        <span class="category-modal-close" onclick="closeCategoryModal('low-modal')">&times;</span>
                    </div>
                    {low_section_html}
                </div>
            </div>
        """

    # 재고 충분 약품 모달 (테이블 + 차트 토글)
    if has_high_runway:
        high_section_html = generate_high_stock_section(high_drugs_df, ma_months, months, threshold_low, threshold_high)
        html_content += f"""
            <!-- 재고 충분 약품 모달 -->
            <div id="high-modal" class="category-modal">
                <div class="category-modal-content">
                    <div class="category-modal-header">
                        <h2 style="color: var(--color-success-dark);">
                            <svg class="icon icon-lg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
                            </svg>
                            재고 충분 약품 (런웨이 {threshold_low}~{threshold_high}개월)
                        </h2>
                        <span class="category-modal-close" onclick="closeCategoryModal('high-modal')">&times;</span>
                    </div>
                    {high_section_html}
                </div>
            </div>
        """

    # 과다 재고 모달 (런웨이 threshold_high 초과)
    if has_excess_runway:
        excess_section_html = generate_excess_stock_section(excess_drugs_df, ma_months, months, threshold_high)
        html_content += f"""
            <!-- 과다 재고 약품 모달 -->
            <div id="excess-modal" class="category-modal">
                <div class="category-modal-content">
                    <div class="category-modal-header">
                        <h2 style="color: var(--color-info-dark);">
                            <svg class="icon icon-lg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="16" y2="12"/><line x1="12" x2="12.01" y1="8" y2="8"/>
                            </svg>
                            과다 재고 약품 (런웨이 {threshold_high}개월 초과)
                        </h2>
                        <span class="category-modal-close" onclick="closeCategoryModal('excess-modal')">&times;</span>
                    </div>
                    {excess_section_html}
                </div>
            </div>
        """

    # 악성 재고 모달
    if has_dead_stock:
        dead_stock_section_html = generate_dead_stock_section(dead_stock_drugs, ma_months, months)
        html_content += f"""
            <!-- 악성 재고 모달 -->
            <div id="dead-modal" class="category-modal">
                <div class="category-modal-content">
                    <div class="category-modal-header">
                        <h2 style="color: var(--text-secondary);">
                            <svg class="icon icon-lg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.29 7 12 12 20.71 7"/><line x1="12" x2="12" y1="22" y2="12"/>
                            </svg>
                            악성 재고 ({ma_months}개월간 미사용 약품)
                        </h2>
                        <span class="category-modal-close" onclick="closeCategoryModal('dead-modal')">&times;</span>
                    </div>
                    {dead_stock_section_html}
                </div>
            </div>
        """

    # 음수 재고 모달
    has_negative_stock = not negative_stock_drugs.empty
    if has_negative_stock:
        negative_stock_section_html = generate_negative_stock_section(negative_stock_drugs, ma_months, months)
        html_content += f"""
            <!-- 음수 재고 모달 -->
            <div id="negative-modal" class="category-modal">
                <div class="category-modal-content">
                    <div class="category-modal-header">
                        <h2 style="color: var(--color-danger);">
                            <svg class="icon icon-lg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/>
                            </svg>
                            음수 재고 약품
                        </h2>
                        <span class="category-modal-close" onclick="closeCategoryModal('negative-modal')">&times;</span>
                    </div>
                    {negative_stock_section_html}
                </div>
            </div>
        """

    # 숨김 약품 모달 (항상 생성)
    hidden_section_html = generate_hidden_drugs_section(df, ma_months, months)
    html_content += f"""
        <!-- 숨김 약품 모달 -->
        <div id="hidden-modal" class="category-modal">
            <div class="category-modal-content">
                <div class="category-modal-header">
                    <h2 style="color: var(--text-secondary);">
                        <svg class="icon icon-lg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
                        </svg>
                        휴지통
                    </h2>
                    <span class="category-modal-close" onclick="closeCategoryModal('hidden-modal')">&times;</span>
                </div>
                {hidden_section_html}
            </div>
        </div>
    """

    # N개월 이동평균 계산 및 정렬 준비
    print(f"\n📊 약품 목록을 {ma_months}개월 이동평균 기준으로 정렬 중...")

    # 각 약품의 N개월 이동평균 계산 (보정 버전)
    ma_values = []
    for _, row in df.iterrows():
        timeseries = row['월별_조제수량_리스트']
        latest_ma, _, _ = get_corrected_ma(timeseries, ma_months)
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
            <h2>
                <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="11" cy="11" r="8"/><line x1="21" x2="16.65" y1="21" y2="16.65"/>
                </svg>
                약품 검색
            </h2>
            <input type="text" class="search-box" id="searchInput" placeholder="약품명, 제약회사, 약품코드로 검색...">
            <p id="searchHint" style="color: #718096; font-size: 14px; margin: 10px 0 20px 0;">검색어를 입력하면 일치하는 약품이 표시됩니다.</p>

            <div class="table-container" id="searchTableContainer" style="display: none;">
                <table id="dataTable">
                    <thead>
                        <tr>
                            <th style="width: 80px;">휴지통</th>
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

    # 메인 테이블용 체크 상태 및 메모 로드
    main_checked_codes = checked_items_db.get_checked_items()
    main_memos = drug_memos_db.get_all_memos()

    # 데이터 행 추가 + 경량 스파크라인 생성
    for idx, row in df_sorted.iterrows():

        # 경량 SVG 스파크라인 생성
        timeseries = row['월별_조제수량_리스트']

        # N개월 이동평균 계산 (스파크라인용 - 기존 방식)
        ma = calculate_custom_ma(timeseries, ma_months)
        sparkline_html = create_sparkline_svg(timeseries, ma, ma_months)

        # 보정된 N개월 이동평균 (신규 약품 보정)
        latest_ma, usage_months, is_corrected = get_corrected_ma(timeseries, ma_months)

        # 신규 약품 태그 (사용 기간 < 선택 기간)
        drug_code = str(row['약품코드'])
        new_drug_tag = ""
        if is_corrected and usage_months > 0:
            new_drug_tag = f'<span class="new-drug-tag">신규<span class="help-icon" onclick="event.stopPropagation(); openNewDrugInfoModal(\'{drug_code}\', {usage_months}, {ma_months})">?</span></span>'

        # 런웨이 계산 (보정된 MA 사용)
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
        chart_data_json = html_escape(create_chart_data_json(
            months=months,
            timeseries_data=timeseries,
            ma_data=ma,
            avg=latest_ma if latest_ma else 0,
            drug_name=row['약품명'],
            drug_code=drug_code,
            ma_months=ma_months,
            stock=int(row['최종_재고수량']),
            runway=runway_display
        ))

        # 약품명 30자 제한
        drug_name_display = row['약품명'] if row['약품명'] is not None else "정보없음"
        if len(drug_name_display) > 30:
            drug_name_display = drug_name_display[:30] + "..."

        # 제약회사 12자 제한
        company_display = row['제약회사'] if row['제약회사'] is not None else "정보없음"
        if len(company_display) > 12:
            company_display = company_display[:12] + "..."

        # 개별 임계값 아이콘 (설정된 경우에만)
        threshold_icon = ""
        if drug_code in custom_thresholds:
            th = custom_thresholds[drug_code]
            tooltip_parts = []
            if th.get('절대재고_임계값') is not None:
                tooltip_parts.append(f"<span style='color:#a0aec0'>📦 개별 설정된 최소 안전 재고 수준:</span> <span style='color:#90cdf4'>{html_escape(str(th['절대재고_임계값']))}개</span>")
            if th.get('런웨이_임계값') is not None:
                tooltip_parts.append(f"<span style='color:#a0aec0'>📅 개별 설정된 최소 안전 런웨이:</span> <span style='color:#90cdf4'>{html_escape(str(th['런웨이_임계값']))}개월</span>")
            if th.get('환자목록'):
                patient_names = html_escape(', '.join(th['환자목록']))
                tooltip_parts.append(f"<span style='color:#a0aec0'>👤 복용 환자:</span> <span style='color:#90cdf4'>{patient_names}</span>")
            if tooltip_parts:
                tooltip_text = '<br>'.join(tooltip_parts)
                threshold_icon = f'<span class="threshold-indicator" data-tooltip="{tooltip_text}" onclick="event.stopPropagation(); showThresholdTooltip(event, this)"><svg class="icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg></span>'

        # 숨김 상태 확인
        is_hidden = drug_code in main_checked_codes
        hidden_class = "hidden" if is_hidden else ""
        hidden_icon = '<i class="bi bi-arrow-counterclockwise"></i>' if is_hidden else '<i class="bi bi-trash"></i>'
        hidden_title = "복원하기" if is_hidden else "휴지통에 넣기"

        # 메모 확인
        memo = main_memos.get(drug_code, "")
        memo_btn_class = "has-memo" if memo else ""
        memo_preview = html_escape(memo[:20] + "..." if len(memo) > 20 else memo) if memo else ""

        html_content += f"""
                        <tr class="{runway_class} clickable-row tab-clickable-row" data-drug-code="{drug_code}"
                            data-chart-data='{chart_data_json}'
                            onclick="toggleInlineChart(this, '{drug_code}')">
                            <td style="text-align: center;" onclick="event.stopPropagation()">
                                <div class="checkbox-memo-container">
                                    <button class="visibility-btn {hidden_class}" data-drug-code="{drug_code}"
                                            onclick="event.stopPropagation(); toggleVisibility(this, '{drug_code}')"
                                            title="{hidden_title}">{hidden_icon}</button>
                                    <button class="memo-btn {memo_btn_class}"
                                            data-drug-code="{drug_code}"
                                            onclick="event.stopPropagation(); openMemoModalGeneric('{drug_code}')"
                                            title="{memo_preview if memo else '메모 추가'}">
                                        ✎
                                    </button>
                                </div>
                            </td>
                            <td>{threshold_icon}{drug_name_display}</td>
                            <td>{company_display}</td>
                            <td>{drug_code}</td>
                            <td>{row['최종_재고수량']:,.0f}</td>
                            <td>{"N/A" if latest_ma is None else f"{latest_ma:.2f}"}{new_drug_tag}</td>
                            <td class="runway-cell">{runway_display}</td>
                            <td>{sparkline_html}</td>
                        </tr>
        """

    # HTML 마무리
    # 메모 데이터를 JSON으로 변환
    main_memos_json = json.dumps(main_memos, ensure_ascii=False)

    html_content += """
                    </tbody>
                </table>
            </div>
        </div>

        <script>
            // 전역 메모 데이터 (window 객체에 저장하여 중복 선언 방지)
            window.drugMemos = window.drugMemos || """ + main_memos_json + """;

            // 개별 임계값 툴팁 관련 변수
            var floatingTooltip = null;
            var activeIndicator = null;

            // 개별 임계값 툴팁 표시
            function showThresholdTooltip(event, element) {
                // 같은 요소 클릭 시 토글
                if (activeIndicator === element && floatingTooltip) {
                    hideThresholdTooltip();
                    return;
                }

                // 기존 툴팁 제거
                hideThresholdTooltip();

                // 새 툴팁 생성
                var tooltipText = element.getAttribute('data-tooltip');
                floatingTooltip = document.createElement('div');
                floatingTooltip.className = 'threshold-tooltip-floating';
                floatingTooltip.innerHTML = tooltipText;
                document.body.appendChild(floatingTooltip);

                // 위치 계산 (아이콘 아래에 표시)
                var rect = element.getBoundingClientRect();
                floatingTooltip.style.left = rect.left + 'px';
                floatingTooltip.style.top = (rect.bottom + 8) + 'px';

                activeIndicator = element;
            }

            function hideThresholdTooltip() {
                if (floatingTooltip) {
                    floatingTooltip.remove();
                    floatingTooltip = null;
                }
                activeIndicator = null;
            }

            // 다른 곳 클릭 시 툴팁 숨김
            document.addEventListener('click', function(event) {
                if (activeIndicator && !event.target.classList.contains('threshold-indicator')) {
                    hideThresholdTooltip();
                }
            });

            // 스크롤 시 툴팁 닫기
            window.addEventListener('scroll', hideThresholdTooltip, true);

            // 책갈피 호버 시 z-index 조정
            document.querySelectorAll('.bookmark-item').forEach(item => {
                item.addEventListener('mouseenter', function() {
                    document.querySelector('.bookmark-sidebar').style.zIndex = '1000';
                });
                item.addEventListener('mouseleave', function() {
                    document.querySelector('.bookmark-sidebar').style.zIndex = '900';
                });
            });

            // 카테고리 모달 열기
            function openCategoryModal(modalId) {
                const modal = document.getElementById(modalId);
                if (modal) {
                    modal.style.display = 'block';
                    document.body.style.overflow = 'hidden'; // 배경 스크롤 방지
                    // 숨김 상태 다시 적용
                    applyHiddenState(modalId);
                }
            }

            // 모달 열 때 숨김 상태 적용 및 정렬
            function applyHiddenState(modalId) {
                const modal = document.getElementById(modalId);
                if (!modal) return;

                // 숨김 상태에 따라 hidden-row 클래스 적용
                modal.querySelectorAll('.visibility-btn').forEach(btn => {
                    const row = btn.closest('tr');
                    if (row) {
                        if (btn.classList.contains('hidden')) {
                            row.classList.add('hidden-row');
                        } else {
                            row.classList.remove('hidden-row');
                        }
                    }
                });

                // 테이블 정렬 (숨김 항목 하단으로)
                const tbody = modal.querySelector('tbody');
                if (tbody) {
                    sortTableByHiddenState(tbody);
                }

                // 숨김 탭인 경우 빈 메시지 업데이트
                if (modalId === 'hidden-modal') {
                    const hiddenCount = modal.querySelectorAll('.visibility-btn.hidden').length;
                    updateHiddenEmptyMessage(hiddenCount);
                }
            }

            // 카테고리 모달 닫기
            function closeCategoryModal(modalId) {
                const modal = document.getElementById(modalId);
                if (modal) {
                    // 모달 내의 모든 인라인 차트 제거
                    modal.querySelectorAll('.inline-chart-row').forEach(el => el.remove());
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
                            // 모달 내의 모든 인라인 차트 제거
                            modal.querySelectorAll('.inline-chart-row').forEach(el => el.remove());
                            modal.style.display = 'none';
                        }
                    });
                    document.body.style.overflow = 'auto';
                }
            });

            // 모달 배경 클릭 시 닫기
            window.addEventListener('click', function(event) {
                if (event.target.classList.contains('category-modal')) {
                    // 모달 내의 모든 인라인 차트 제거
                    event.target.querySelectorAll('.inline-chart-row').forEach(el => el.remove());
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

            // 숨김 토글 핸들러 (통합)
            function toggleVisibility(btn, drugCode) {
                const row = btn.closest('tr');
                const isCurrentlyHidden = btn.classList.contains('hidden');
                const newHiddenState = !isCurrentlyHidden;

                // 서버에 숨김 상태 저장
                fetch('/api/toggle_checked_item', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        drug_code: drugCode,
                        checked: newHiddenState
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        // 모든 탭에서 같은 약품의 상태 동기화
                        syncVisibilityState(drugCode, newHiddenState);
                        // 숨김 탭 카운트 업데이트
                        updateHiddenCount();
                    }
                })
                .catch(error => console.error('API 요청 실패:', error));
            }

            // 모든 탭에서 같은 약품의 숨김 상태 동기화
            function syncVisibilityState(drugCode, isHidden) {
                // 모든 숨김 버튼에서 같은 약품코드를 가진 것들 찾기
                const allButtons = document.querySelectorAll(`.visibility-btn[data-drug-code="${drugCode}"]`);

                allButtons.forEach(btn => {
                    const row = btn.closest('tr');
                    const isInHiddenTable = row && row.closest('#hidden-drugs-table');

                    if (isHidden) {
                        btn.classList.add('hidden');
                        btn.innerHTML = '<i class="bi bi-arrow-counterclockwise"></i>';
                        btn.title = '복원하기';
                        if (row) {
                            if (isInHiddenTable) {
                                // 휴지통 탭: 보이게
                                row.style.display = '';
                            } else {
                                // 다른 탭: 회색 스타일 + 하단 정렬
                                row.classList.add('hidden-row');
                            }
                        }
                    } else {
                        btn.classList.remove('hidden');
                        btn.innerHTML = '<i class="bi bi-trash"></i>';
                        btn.title = '휴지통에 넣기';
                        if (row) {
                            if (isInHiddenTable) {
                                // 숨김 탭: 숨기기
                                row.style.display = 'none';
                            } else {
                                // 다른 탭: 회색 스타일 제거
                                row.classList.remove('hidden-row');
                            }
                        }
                    }
                    // 다른 탭의 테이블만 재정렬 (숨김 항목을 하단으로)
                    if (row && !isInHiddenTable) {
                        const tbody = row.closest('tbody');
                        if (tbody) {
                            sortTableByHiddenState(tbody);
                        }
                    }
                });
                // 빈 메시지 업데이트
                updateHiddenEmptyMessage();
                // 탭 카운트 및 그래프 업데이트
                updateProportionGraph();
            }

            // 테이블 정렬: 숨김 처리된 행을 하단으로 이동
            function sortTableByHiddenState(tbody) {
                const rows = Array.from(tbody.querySelectorAll('tr:not(.inline-chart-row)'));
                rows.sort((a, b) => {
                    const aHidden = a.classList.contains('hidden-row') ? 1 : 0;
                    const bHidden = b.classList.contains('hidden-row') ? 1 : 0;
                    return aHidden - bHidden;
                });
                rows.forEach(row => tbody.appendChild(row));
            }

            // 각 탭별 카운트 업데이트 (숨김 처리 안된 항목만 카운트)
            function updateTabCounts() {
                const counts = {
                    urgent: 0,
                    low: 0,
                    high: 0,
                    excess: 0,
                    dead: 0
                };

                // 긴급 탭 카운트
                const urgentTable = document.querySelector('#urgent-modal tbody');
                if (urgentTable) {
                    counts.urgent = urgentTable.querySelectorAll('tr:not(.hidden-row):not(.inline-chart-row)').length;
                }

                // 부족 탭 카운트
                const lowTable = document.querySelector('#low-modal tbody');
                if (lowTable) {
                    counts.low = lowTable.querySelectorAll('tr:not(.hidden-row):not(.inline-chart-row)').length;
                }

                // 충분 탭 카운트
                const highTable = document.querySelector('#high-modal tbody');
                if (highTable) {
                    counts.high = highTable.querySelectorAll('tr:not(.hidden-row):not(.inline-chart-row)').length;
                }

                // 과다 탭 카운트
                const excessTable = document.querySelector('#excess-modal tbody');
                if (excessTable) {
                    counts.excess = excessTable.querySelectorAll('tr:not(.hidden-row):not(.inline-chart-row)').length;
                }

                // 악성재고 탭 카운트
                const deadTable = document.querySelector('#dead-modal tbody');
                if (deadTable) {
                    counts.dead = deadTable.querySelectorAll('tr:not(.hidden-row):not(.inline-chart-row)').length;
                }

                // 사이드바 카운트 업데이트
                const urgentCountEl = document.querySelector('.bookmark-urgent .bookmark-count');
                const lowCountEl = document.querySelector('.bookmark-low .bookmark-count');
                const highCountEl = document.querySelector('.bookmark-high .bookmark-count');
                const excessCountEl = document.querySelector('.bookmark-excess .bookmark-count');
                const deadCountEl = document.querySelector('.bookmark-dead .bookmark-count');

                if (urgentCountEl) urgentCountEl.textContent = counts.urgent;
                if (lowCountEl) lowCountEl.textContent = counts.low;
                if (highCountEl) highCountEl.textContent = counts.high;
                if (excessCountEl) excessCountEl.textContent = counts.excess;
                if (deadCountEl) deadCountEl.textContent = counts.dead;

                return counts;
            }

            // Proportion 그래프 업데이트
            function updateProportionGraph() {
                const counts = updateTabCounts();
                const total = counts.urgent + counts.low + counts.high + counts.excess + counts.dead;

                if (total === 0) return;

                // 바 업데이트
                const urgentBar = document.getElementById('proportion-bar-urgent');
                const lowBar = document.getElementById('proportion-bar-low');
                const highBar = document.getElementById('proportion-bar-high');
                const excessBar = document.getElementById('proportion-bar-excess');
                const deadBar = document.getElementById('proportion-bar-dead');

                if (urgentBar) {
                    urgentBar.style.flex = counts.urgent;
                    urgentBar.textContent = counts.urgent > 0 ? counts.urgent : '';
                    urgentBar.title = `긴급: ${counts.urgent}개 (${(counts.urgent/total*100).toFixed(1)}%)`;
                }
                if (lowBar) {
                    lowBar.style.flex = counts.low;
                    lowBar.textContent = counts.low > 0 ? counts.low : '';
                    lowBar.title = `부족: ${counts.low}개 (${(counts.low/total*100).toFixed(1)}%)`;
                }
                if (highBar) {
                    highBar.style.flex = counts.high;
                    highBar.textContent = counts.high > 0 ? counts.high : '';
                    highBar.title = `충분: ${counts.high}개 (${(counts.high/total*100).toFixed(1)}%)`;
                }
                if (excessBar) {
                    excessBar.style.flex = counts.excess;
                    excessBar.textContent = counts.excess > 0 ? counts.excess : '';
                    excessBar.title = `과다: ${counts.excess}개 (${(counts.excess/total*100).toFixed(1)}%)`;
                }
                if (deadBar) {
                    deadBar.style.flex = counts.dead;
                    deadBar.textContent = counts.dead > 0 ? counts.dead : '';
                    deadBar.title = `악성재고: ${counts.dead}개 (${(counts.dead/total*100).toFixed(1)}%)`;
                }

                // 레이블 업데이트
                const urgentLabel = document.getElementById('proportion-label-urgent');
                const lowLabel = document.getElementById('proportion-label-low');
                const highLabel = document.getElementById('proportion-label-high');
                const excessLabel = document.getElementById('proportion-label-excess');
                const deadLabel = document.getElementById('proportion-label-dead');

                if (urgentLabel) urgentLabel.textContent = `긴급: ${counts.urgent}개 (${(counts.urgent/total*100).toFixed(1)}%)`;
                if (lowLabel) lowLabel.textContent = `부족: ${counts.low}개 (${(counts.low/total*100).toFixed(1)}%)`;
                if (highLabel) highLabel.textContent = `충분: ${counts.high}개 (${(counts.high/total*100).toFixed(1)}%)`;
                if (excessLabel) excessLabel.textContent = `과다: ${counts.excess}개 (${(counts.excess/total*100).toFixed(1)}%)`;
                if (deadLabel) deadLabel.textContent = `악성재고: ${counts.dead}개 (${(counts.dead/total*100).toFixed(1)}%)`;
            }

            // 숨김 탭 카운트 업데이트 (hidden 클래스가 있는 버튼 수 기준)
            function updateHiddenCount() {
                // 모든 탭에서 숨김 처리된 약품코드 수집 (중복 제거)
                const hiddenDrugCodes = new Set();
                document.querySelectorAll('.visibility-btn.hidden').forEach(btn => {
                    const drugCode = btn.getAttribute('data-drug-code');
                    if (drugCode) {
                        hiddenDrugCodes.add(drugCode);
                    }
                });
                const countEl = document.querySelector('.bookmark-hidden .bookmark-count');
                if (countEl) {
                    countEl.textContent = hiddenDrugCodes.size;
                }
                const shortcutCountEl = document.getElementById('trash-shortcut-count');
                if (shortcutCountEl) {
                    // 대기중 상태인 항목만 카운트
                    let pendingCount = 0;
                    const hiddenTable = document.getElementById('hidden-drugs-table');
                    if (hiddenTable) {
                        hiddenTable.querySelectorAll('tbody tr').forEach(row => {
                            if (row.style.display !== 'none') {
                                const badge = row.querySelector('.process-status-badge');
                                if (badge && badge.textContent.trim() === '대기중') {
                                    pendingCount++;
                                }
                            }
                        });
                    }
                    shortcutCountEl.textContent = pendingCount;
                }
                // 빈 메시지 표시/숨김 업데이트
                updateHiddenEmptyMessage(hiddenDrugCodes.size);
            }

            // 숨김 탭 빈 메시지 표시/숨김
            function updateHiddenEmptyMessage(count) {
                // count가 없으면 숨김 탭에서 보이는 행 수로 계산
                if (count === undefined) {
                    const hiddenTable = document.getElementById('hidden-drugs-table');
                    if (hiddenTable) {
                        const visibleRows = hiddenTable.querySelectorAll('tbody tr:not([style*="display: none"])');
                        count = visibleRows.length;
                    } else {
                        count = 0;
                    }
                }
                const emptyMsg = document.getElementById('hidden-empty-message');
                const table = document.getElementById('hidden-drugs-table');
                if (emptyMsg && table) {
                    if (count === 0) {
                        emptyMsg.style.display = 'block';
                        table.style.display = 'none';
                    } else {
                        emptyMsg.style.display = 'none';
                        table.style.display = 'table';
                    }
                }
            }

            // 페이지 로드 시 최신 숨김 목록을 API에서 가져와서 적용
            window.addEventListener('DOMContentLoaded', function() {
                // API에서 최신 숨김 목록 가져오기
                fetch('/api/get_checked_items')
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') {
                            const checkedItems = new Set(data.checked_items);

                            // 모든 visibility 버튼에 대해 최신 상태 적용
                            document.querySelectorAll('.visibility-btn').forEach(btn => {
                                const drugCode = btn.getAttribute('data-drug-code');
                                const row = btn.closest('tr');
                                const isInHiddenTable = row && row.closest('#hidden-drugs-table');

                                if (checkedItems.has(drugCode)) {
                                    // 휴지통에 넣은 상태
                                    btn.classList.add('hidden');
                                    btn.innerHTML = '<i class="bi bi-arrow-counterclockwise"></i>';
                                    btn.title = '복원하기';
                                    if (row) {
                                        if (isInHiddenTable) {
                                            row.style.display = '';
                                        } else {
                                            row.classList.add('hidden-row');
                                        }
                                    }
                                } else {
                                    // 휴지통에 넣지 않은 상태
                                    btn.classList.remove('hidden');
                                    btn.innerHTML = '<i class="bi bi-trash"></i>';
                                    btn.title = '휴지통에 넣기';
                                    if (row) {
                                        if (isInHiddenTable) {
                                            row.style.display = 'none';
                                        } else {
                                            row.classList.remove('hidden-row');
                                        }
                                    }
                                }
                            });

                            // 모든 테이블 정렬 (숨김 항목 하단으로)
                            document.querySelectorAll('table tbody').forEach(tbody => {
                                sortTableByHiddenState(tbody);
                            });
                            updateHiddenCount();
                            updateProportionGraph();
                        }
                    })
                    .catch(error => {
                        console.error('숨김 목록 로드 실패:', error);
                        // 폴백: HTML에 있는 상태 그대로 사용
                        document.querySelectorAll('.visibility-btn.hidden').forEach(btn => {
                            const row = btn.closest('tr');
                            if (row) {
                                row.classList.add('hidden-row');
                            }
                        });
                        document.querySelectorAll('table tbody').forEach(tbody => {
                            sortTableByHiddenState(tbody);
                        });
                        updateHiddenCount();
                        updateProportionGraph();
                    });
            });

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
                    <td colspan="${colSpan}" style="padding: var(--space-5); background: var(--bg-subtle); border-left: 3px solid var(--brand-primary);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-4);">
                            <h4 style="margin: 0; color: var(--text-primary); font-size: 1rem; font-weight: 600;">${chartData.drug_name} (${chartData.drug_code}) 상세 트렌드</h4>
                            <button onclick="closeInlineChart('${drugCode}')"
                                    style="background: none; border: none; font-size: 1.25rem; cursor: pointer; color: var(--text-muted); padding: var(--space-1); border-radius: var(--radius-sm); transition: all var(--duration-fast) var(--ease-out);"
                                    onmouseover="this.style.background='var(--bg-hover)'; this.style.color='var(--text-primary)'"
                                    onmouseout="this.style.background='none'; this.style.color='var(--text-muted)'">&times;</button>
                        </div>
                        <div style="display: flex; gap: var(--space-3); margin-bottom: var(--space-4);">
                            <div style="flex: 1; background: var(--bg-surface); border: 1px solid var(--border-default); border-radius: var(--radius-md); padding: var(--space-3); text-align: center;">
                                <div style="font-size: 0.6875rem; color: var(--text-muted); margin-bottom: var(--space-1); text-transform: uppercase; letter-spacing: 0.05em;">재고수량</div>
                                <div style="font-size: 1.125rem; font-weight: 600; color: ${chartData.stock <= 0 ? 'var(--color-danger)' : 'var(--text-primary)'};">${chartData.stock.toLocaleString()}<span style="font-size: 0.75rem; color: var(--text-muted);">개</span></div>
                            </div>
                            <div style="flex: 1; background: var(--bg-surface); border: 1px solid var(--border-default); border-radius: var(--radius-md); padding: var(--space-3); text-align: center;">
                                <div style="font-size: 0.6875rem; color: var(--text-muted); margin-bottom: var(--space-1); text-transform: uppercase; letter-spacing: 0.05em;">${chartData.ma_months}개월 이동평균</div>
                                <div style="font-size: 1.125rem; font-weight: 600; color: var(--text-primary);">${chartData.latest_ma !== null ? chartData.latest_ma.toFixed(1) : 'N/A'}<span style="font-size: 0.75rem; color: var(--text-muted);">/월</span></div>
                            </div>
                            <div style="flex: 1; background: var(--bg-surface); border: 1px solid var(--brand-primary); border-radius: var(--radius-md); padding: var(--space-3); text-align: center;">
                                <div style="font-size: 0.6875rem; color: var(--brand-primary); margin-bottom: var(--space-1); text-transform: uppercase; letter-spacing: 0.05em;">런웨이</div>
                                <div style="font-size: 1.125rem; font-weight: 600; color: ${chartData.latest_ma > 0 && chartData.stock / chartData.latest_ma < 1 ? 'var(--color-danger)' : 'var(--text-primary)'};">${chartData.runway}</div>
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

                // 현재 재고 수평선 데이터
                const currentStock = chartData.stock || 0;
                const stockLine = chartData.months.map(() => currentStock);

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
                        line: {color: '#52525b', width: 2, dash: 'dot'},
                        marker: {size: 6, color: '#52525b'},
                        hovertemplate: '실제 조제수량: %{y:,.0f}개<extra></extra>'
                    },
                    {
                        x: chartData.months,
                        y: maClean,
                        mode: 'lines',
                        name: chartData.ma_months + '개월 이동평균',
                        line: {color: '#475569', width: 3},
                        hovertemplate: chartData.ma_months + '개월 이동평균: %{y:,.2f}개<extra></extra>'
                    },
                    {
                        x: chartData.months,
                        y: stockLine,
                        mode: 'lines',
                        name: '현재 재고',
                        line: {color: '#ef4444', width: 2, dash: 'dash'},
                        hovertemplate: '현재 재고: %{y:,.0f}개<extra></extra>'
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

                // annotations 생성
                const annotations = [];
                if (maxValue > 0) {
                    annotations.push({
                        x: maxMonth, y: maxValue,
                        text: '최대: ' + maxValue.toFixed(0),
                        showarrow: true, arrowhead: 2, arrowsize: 1, arrowwidth: 2, arrowcolor: '#ef4444',
                        ax: 0, ay: -30,
                        bgcolor: 'rgba(255,255,255,0.95)', bordercolor: '#ef4444', borderwidth: 1, borderpad: 3,
                        font: {color: '#ef4444', size: 10, weight: 'bold'}
                    });
                }
                // 현재 재고 annotation
                annotations.push({
                    x: chartData.months[chartData.months.length - 1],
                    y: currentStock,
                    text: '현재 재고: ' + currentStock.toLocaleString(),
                    showarrow: false,
                    xanchor: 'left',
                    xshift: 10,
                    font: {color: '#ef4444', size: 10}
                });

                const layout = {
                    xaxis: { title: '월', type: 'category', showgrid: true, gridcolor: '#e4e4e7' },
                    yaxis: { title: '조제수량', showgrid: true, gridcolor: '#e4e4e7' },
                    height: 350,
                    margin: { t: 30, b: 50, l: 60, r: 100 },
                    hovermode: 'x unified',
                    plot_bgcolor: '#ffffff',
                    paper_bgcolor: '#f4f4f5',
                    font: {size: 11, color: '#52525b'},
                    shapes: winterShapes,
                    annotations: annotations
                };

                Plotly.newPlot(chartContainer, traces, layout, {displayModeBar: false, responsive: true});
            }

            // 범용 메모 모달 열기 (카테고리 없이 약품코드만 사용)
            function openMemoModalGeneric(drugCode) {
                const modal = document.getElementById('memo-modal-generic');
                const drugCodeElement = document.getElementById('memo-drug-code-generic');
                const textarea = document.getElementById('memo-textarea-generic');

                // 전역 메모 데이터에서 가져오기 (window 객체 또는 지역 변수)
                const memos = window.drugMemos || (typeof drugMemos !== 'undefined' ? drugMemos : {});
                const memo = memos[drugCode] || '';

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
                        // 전역 메모 데이터 업데이트 (window 객체 및 지역 변수 모두)
                        if (window.drugMemos) {
                            if (memo) {
                                window.drugMemos[drugCode] = memo;
                            } else {
                                delete window.drugMemos[drugCode];
                            }
                        }
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

            // 신규 약품 정보 모달 열기
            function openNewDrugInfoModal(drugCode, usageMonths, maMonths) {
                const modal = document.getElementById('new-drug-info-modal');
                document.getElementById('new-drug-info-code').textContent = drugCode;
                document.getElementById('new-drug-info-usage').textContent = usageMonths;
                document.getElementById('new-drug-info-ma').textContent = maMonths;
                modal.style.display = 'block';
            }

            // 신규 약품 정보 모달 닫기
            function closeNewDrugInfoModal() {
                document.getElementById('new-drug-info-modal').style.display = 'none';
            }
        </script>

        <!-- 신규 약품 정보 모달 -->
        <div id="new-drug-info-modal" class="modal" onclick="if(event.target === this) closeNewDrugInfoModal()">
            <div class="modal-content" style="max-width: 500px; text-align: center;">
                <span class="close-btn" onclick="closeNewDrugInfoModal()">&times;</span>
                <div style="margin-bottom: var(--space-4); display: flex; justify-content: center;">
                    <svg class="icon-xl" style="width: 48px; height: 48px; color: var(--color-info);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" x2="18" y1="20" y2="10"/><line x1="12" x2="12" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="14"/>
                    </svg>
                </div>
                <h2 style="margin-bottom: var(--space-5); color: var(--color-info);">신규 약품 안내</h2>
                <div style="background: var(--color-info-light); border-radius: var(--radius-lg); padding: var(--space-5); margin-bottom: var(--space-5); text-align: left;">
                    <p style="margin: 0 0 var(--space-3) 0; color: var(--color-info-dark); font-weight: 600;">
                        이 약품은 사용 기간이 <span id="new-drug-info-ma" style="color: var(--color-danger);"></span>개월 미만입니다.
                    </p>
                    <p style="margin: 0 0 var(--space-3) 0; color: var(--color-info-dark);">
                        약품코드: <strong id="new-drug-info-code"></strong>
                    </p>
                    <p style="margin: 0; color: var(--color-info-dark);">
                        실제 사용 기간: <strong><span id="new-drug-info-usage"></span>개월</strong>
                    </p>
                </div>
                <div style="background: var(--color-warning-light); border-radius: var(--radius-lg); padding: var(--space-4); text-align: left; display: flex; gap: var(--space-3); align-items: flex-start;">
                    <svg class="icon" style="flex-shrink: 0; color: var(--color-warning-dark);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="16" y2="12"/><line x1="12" x2="12.01" y1="8" y2="8"/>
                    </svg>
                    <p style="margin: 0; color: var(--color-warning-dark); font-size: 0.8125rem;">
                        <strong>보정된 이동평균</strong>: 데이터가 부족하여 실제 사용 기간으로 나눈 값입니다. 데이터가 더 쌓이면 정확한 이동평균이 계산됩니다.
                    </p>
                </div>
                <button onclick="closeNewDrugInfoModal()" class="nav-btn" style="margin-top: var(--space-5); padding: var(--space-3) var(--space-6);">
                    확인
                </button>
            </div>
        </div>

        <!-- 범용 메모 모달 -->
        <div id="memo-modal-generic" class="modal">
            <div class="modal-content" style="max-width: 600px;">
                <span class="close-btn" onclick="closeMemoModalGeneric()">&times;</span>
                <h2 style="margin-bottom: var(--space-5); display: flex; align-items: center; gap: var(--space-2);">
                    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/>
                    </svg>
                    메모 작성
                </h2>
                <p style="color: var(--text-muted); margin-bottom: var(--space-3); font-size: 0.875rem;">약품코드: <strong style="color: var(--text-primary);" id="memo-drug-code-generic"></strong></p>
                <textarea id="memo-textarea-generic"
                          style="width: 100%; height: 200px; padding: var(--space-3); border: 1px solid var(--border-default); border-radius: var(--radius-md); font-size: 0.875rem; font-family: inherit; resize: vertical; color: var(--text-primary); box-sizing: border-box;"
                          placeholder="메모를 입력하세요..."></textarea>
                <div style="display: flex; justify-content: flex-end; gap: var(--space-3); margin-top: var(--space-5);">
                    <button onclick="closeMemoModalGeneric()" style="padding: var(--space-2) var(--space-4); border: 1px solid var(--border-default); background: var(--bg-surface); border-radius: var(--radius-md); cursor: pointer; font-size: 0.875rem; color: var(--text-secondary); transition: all var(--duration-fast) var(--ease-out);">취소</button>
                    <button onclick="saveMemoGeneric()" class="nav-btn">저장</button>
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
        negative_stock_drugs: 재고가 음수인 약품 (음수 재고)
    """

    # 각 약품의 N개월 이동평균 계산 (보정 버전)
    ma_values = []
    usage_months_list = []
    is_corrected_list = []
    for _, row in df.iterrows():
        timeseries = row['월별_조제수량_리스트']
        latest_ma, usage_months, is_corrected = get_corrected_ma(timeseries, ma_months)
        ma_values.append(latest_ma if latest_ma else 0)
        usage_months_list.append(usage_months)
        is_corrected_list.append(is_corrected)

    df_with_ma = df.copy()
    df_with_ma['N개월_이동평균'] = ma_values
    df_with_ma['사용기간'] = usage_months_list
    df_with_ma['신규여부'] = is_corrected_list

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

    # Case 3: 음수 재고 - 재고가 음수인 약품 (이동평균 무관)
    negative_stock_drugs = df_with_ma[
        df_with_ma['최종_재고수량'] < 0
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

    # 음수 재고: 재고수량 기준 오름차순 정렬 (가장 심각한 음수가 위로)
    if not negative_stock_drugs.empty:
        negative_stock_drugs = negative_stock_drugs.sort_values('최종_재고수량', ascending=True)

    return urgent_drugs, dead_stock_drugs, negative_stock_drugs

def generate_urgent_drugs_section(urgent_drugs, ma_months, months):
    """긴급 약품 섹션 HTML 생성 (테이블 형식 + 체크박스 + 메모 + 인라인 차트) - 모달용"""
    import json

    # DB에서 체크된 약품 코드 목록 가져오기 (카테고리 없이)
    checked_codes = checked_items_db.get_checked_items()

    # 메모 목록 가져오기 (카테고리 없이)
    memos = drug_memos_db.get_all_memos()

    # 개별 임계값 로드
    custom_thresholds = drug_thresholds_db.get_threshold_dict()

    html = f"""
                    <div style="padding: var(--space-4); background: var(--color-danger-light); border-radius: var(--radius-lg); margin-bottom: var(--space-4); display: flex; align-items: center; gap: var(--space-3);">
                        <svg class="icon" style="color: var(--color-danger); flex-shrink: 0;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/>
                        </svg>
                        <p style="margin: 0; color: var(--color-danger-dark); font-weight: 600;">
                            총 {len(urgent_drugs)}개 약품이 현재 사용되고 있으나 재고가 소진되었습니다. 즉시 주문이 필요합니다!
                        </p>
                    </div>
                    <div class="table-container">
                        <table id="urgent-drugs-table">
                            <thead>
                                <tr>
                                    <th style="width: 50px;">휴지통</th>
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

        # 메모 가져오기
        memo = memos.get(drug_code, '')
        memo_escaped = memo.replace("'", "\\'").replace('"', '&quot;').replace('\n', '\\n')

        # 메모 버튼 스타일 (메모가 있으면 주황색)
        memo_btn_class = "has-memo" if memo else ""
        memo_preview = memo[:50] + '...' if len(memo) > 50 else memo

        # 개별 임계값 아이콘 (설정된 경우에만)
        threshold_icon = ""
        if drug_code in custom_thresholds:
            th = custom_thresholds[drug_code]
            tooltip_parts = []
            if th.get('절대재고_임계값') is not None:
                tooltip_parts.append(f"<span style='color:#a0aec0'>📦 개별 설정된 최소 안전 재고 수준:</span> <span style='color:#90cdf4'>{html_escape(str(th['절대재고_임계값']))}개</span>")
            if th.get('런웨이_임계값') is not None:
                tooltip_parts.append(f"<span style='color:#a0aec0'>📅 개별 설정된 최소 안전 런웨이:</span> <span style='color:#90cdf4'>{html_escape(str(th['런웨이_임계값']))}개월</span>")
            if th.get('환자목록'):
                patient_names = html_escape(', '.join(th['환자목록']))
                tooltip_parts.append(f"<span style='color:#a0aec0'>👤 복용 환자:</span> <span style='color:#90cdf4'>{patient_names}</span>")
            if tooltip_parts:
                tooltip_text = '<br>'.join(tooltip_parts)
                threshold_icon = f'<span class="threshold-indicator" data-tooltip="{tooltip_text}" onclick="event.stopPropagation(); showThresholdTooltip(event, this)"><svg class="icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg></span>'

        # 신규 약품 태그 (데이터에 포함된 경우)
        new_drug_tag = ""
        if row.get('신규여부', False) and row.get('사용기간', 0) > 0:
            usage_months_val = row['사용기간']
            new_drug_tag = f'<span class="new-drug-tag">신규<span class="help-icon" onclick="event.stopPropagation(); openNewDrugInfoModal(\'{drug_code}\', {usage_months_val}, {ma_months})">?</span></span>'

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
        chart_data_json = html_escape(json.dumps(chart_data, ensure_ascii=False))

        # 숨김 버튼 상태
        hidden_class = "hidden" if is_checked else ""
        hidden_icon = '<i class="bi bi-arrow-counterclockwise"></i>' if is_checked else '<i class="bi bi-trash"></i>'
        hidden_title = "복원하기" if is_checked else "휴지통에 넣기"

        html += f"""
                                <tr class="urgent-row tab-clickable-row" data-drug-code="{drug_code}"
                                    data-chart-data='{chart_data_json}'
                                    onclick="toggleInlineChart(this, '{drug_code}')">
                                    <td style="text-align: center;" onclick="event.stopPropagation()">
                                        <div class="checkbox-memo-container">
                                            <button class="visibility-btn {hidden_class}" data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); toggleVisibility(this, '{drug_code}')"
                                                    title="{hidden_title}">{hidden_icon}</button>
                                            <button class="memo-btn {memo_btn_class}"
                                                    data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); openMemoModal('{drug_code}')"
                                                    title="{memo_preview if memo else '메모 추가'}">
                                                ✎
                                            </button>
                                        </div>
                                    </td>
                                    <td style="font-weight: bold;">{threshold_icon}{drug_name_display}</td>
                                    <td>{drug_code}</td>
                                    <td>{company_display}</td>
                                    <td style="color: #c53030; font-weight: bold;">0</td>
                                    <td style="color: #2d5016; font-weight: bold;">{latest_ma:.2f}{new_drug_tag}</td>
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
                              style="width: 100%; height: 200px; padding: 10px; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 14px; font-family: inherit; resize: vertical; box-sizing: border-box;"
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

def generate_low_stock_section(low_drugs_df, ma_months, months, threshold_low=3):
    """재고 부족 약품 섹션 HTML 생성 (테이블 형식 + 체크박스/메모 + 인라인 차트) - 모달용"""
    import json

    if low_drugs_df.empty:
        return ""

    # DB에서 체크된 약품 코드 목록 가져오기 (카테고리 없이)
    checked_codes = checked_items_db.get_checked_items()
    memos = drug_memos_db.get_all_memos()
    custom_thresholds = drug_thresholds_db.get_threshold_dict()

    html = f"""
                    <div style="padding: var(--space-4); background: var(--color-warning-light); border-radius: var(--radius-lg); margin-bottom: var(--space-4); display: flex; align-items: center; gap: var(--space-3);">
                        <svg class="icon" style="color: var(--color-warning-dark); flex-shrink: 0;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/>
                        </svg>
                        <p style="margin: 0; color: var(--color-warning-dark); font-weight: 600;">
                            총 {len(low_drugs_df)}개 약품의 런웨이가 {threshold_low}개월 이하입니다. 재고 보충을 고려하세요.
                        </p>
                    </div>
                    <div class="table-container">
                        <table id="low-drugs-table">
                            <thead>
                                <tr>
                                    <th style="width: 50px;">휴지통</th>
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

        # 메모 가져오기
        memo = memos.get(drug_code, '')
        memo_btn_class = "has-memo" if memo else ""
        memo_preview = memo[:50] + '...' if len(memo) > 50 else memo

        # 개별 임계값 아이콘 (설정된 경우에만)
        threshold_icon = ""
        if drug_code in custom_thresholds:
            th = custom_thresholds[drug_code]
            tooltip_parts = []
            if th.get('절대재고_임계값') is not None:
                tooltip_parts.append(f"<span style='color:#a0aec0'>📦 개별 설정된 최소 안전 재고 수준:</span> <span style='color:#90cdf4'>{html_escape(str(th['절대재고_임계값']))}개</span>")
            if th.get('런웨이_임계값') is not None:
                tooltip_parts.append(f"<span style='color:#a0aec0'>📅 개별 설정된 최소 안전 런웨이:</span> <span style='color:#90cdf4'>{html_escape(str(th['런웨이_임계값']))}개월</span>")
            if th.get('환자목록'):
                patient_names = html_escape(', '.join(th['환자목록']))
                tooltip_parts.append(f"<span style='color:#a0aec0'>👤 복용 환자:</span> <span style='color:#90cdf4'>{patient_names}</span>")
            if tooltip_parts:
                tooltip_text = '<br>'.join(tooltip_parts)
                threshold_icon = f'<span class="threshold-indicator" data-tooltip="{tooltip_text}" onclick="event.stopPropagation(); showThresholdTooltip(event, this)"><svg class="icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg></span>'

        # 숨김 버튼 상태
        hidden_class = "hidden" if is_checked else ""
        hidden_icon = '<i class="bi bi-arrow-counterclockwise"></i>' if is_checked else '<i class="bi bi-trash"></i>'
        hidden_title = "복원하기" if is_checked else "휴지통에 넣기"

        # 신규 약품 태그 (데이터에 포함된 경우)
        new_drug_tag = ""
        if row.get('신규여부', False) and row.get('사용기간', 0) > 0:
            usage_months_val = row['사용기간']
            new_drug_tag = f'<span class="new-drug-tag">신규<span class="help-icon" onclick="event.stopPropagation(); openNewDrugInfoModal(\'{drug_code}\', {usage_months_val}, {ma_months})">?</span></span>'

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
        chart_data_json = html_escape(json.dumps(chart_data, ensure_ascii=False))

        html += f"""
                                <tr class="low-row tab-clickable-row" data-drug-code="{drug_code}"
                                    data-chart-data='{chart_data_json}'
                                    onclick="toggleInlineChart(this, '{drug_code}')">
                                    <td style="text-align: center;" onclick="event.stopPropagation()">
                                        <div class="checkbox-memo-container">
                                            <button class="visibility-btn {hidden_class}" data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); toggleVisibility(this, '{drug_code}')"
                                                    title="{hidden_title}">{hidden_icon}</button>
                                            <button class="memo-btn {memo_btn_class}"
                                                    data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); openMemoModalGeneric('{drug_code}')"
                                                    title="{memo_preview if memo else '메모 추가'}">
                                                ✎
                                            </button>
                                        </div>
                                    </td>
                                    <td style="font-weight: bold;">{threshold_icon}{drug_name_display}</td>
                                    <td>{drug_code}</td>
                                    <td>{company_display}</td>
                                    <td>{row['최종_재고수량']:,.0f}</td>
                                    <td>{row['N개월_이동평균']:.2f}{new_drug_tag}</td>
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

def generate_high_stock_section(high_drugs_df, ma_months, months, threshold_low=3, threshold_high=12):
    """재고 충분 약품 섹션 HTML 생성 (테이블 형식 + 체크박스/메모 + 인라인 차트) - 모달용"""
    import json

    if high_drugs_df.empty:
        return ""

    # DB에서 체크된 약품 코드 목록 가져오기 (카테고리 없이)
    checked_codes = checked_items_db.get_checked_items()
    memos = drug_memos_db.get_all_memos()
    custom_thresholds = drug_thresholds_db.get_threshold_dict()

    html = f"""
                    <div style="padding: var(--space-4); background: var(--color-success-light); border-radius: var(--radius-lg); margin-bottom: var(--space-4); display: flex; align-items: center; gap: var(--space-3);">
                        <svg class="icon" style="color: var(--color-success-dark); flex-shrink: 0;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
                        </svg>
                        <p style="margin: 0; color: var(--color-success-dark); font-weight: 600;">
                            총 {len(high_drugs_df)}개 약품의 런웨이가 {threshold_low}~{threshold_high}개월입니다. 재고가 충분합니다.
                        </p>
                    </div>
                    <div class="table-container">
                        <table id="high-drugs-table">
                            <thead>
                                <tr>
                                    <th style="width: 50px;">휴지통</th>
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

        # 메모 가져오기
        memo = memos.get(drug_code, '')
        memo_btn_class = "has-memo" if memo else ""
        memo_preview = memo[:50] + '...' if len(memo) > 50 else memo

        # 개별 임계값 아이콘 (설정된 경우에만)
        threshold_icon = ""
        if drug_code in custom_thresholds:
            th = custom_thresholds[drug_code]
            tooltip_parts = []
            if th.get('절대재고_임계값') is not None:
                tooltip_parts.append(f"<span style='color:#a0aec0'>📦 개별 설정된 최소 안전 재고 수준:</span> <span style='color:#90cdf4'>{html_escape(str(th['절대재고_임계값']))}개</span>")
            if th.get('런웨이_임계값') is not None:
                tooltip_parts.append(f"<span style='color:#a0aec0'>📅 개별 설정된 최소 안전 런웨이:</span> <span style='color:#90cdf4'>{html_escape(str(th['런웨이_임계값']))}개월</span>")
            if th.get('환자목록'):
                patient_names = html_escape(', '.join(th['환자목록']))
                tooltip_parts.append(f"<span style='color:#a0aec0'>👤 복용 환자:</span> <span style='color:#90cdf4'>{patient_names}</span>")
            if tooltip_parts:
                tooltip_text = '<br>'.join(tooltip_parts)
                threshold_icon = f'<span class="threshold-indicator" data-tooltip="{tooltip_text}" onclick="event.stopPropagation(); showThresholdTooltip(event, this)"><svg class="icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg></span>'

        # 숨김 버튼 상태
        hidden_class = "hidden" if is_checked else ""
        hidden_icon = '<i class="bi bi-arrow-counterclockwise"></i>' if is_checked else '<i class="bi bi-trash"></i>'
        hidden_title = "복원하기" if is_checked else "휴지통에 넣기"

        # 신규 약품 태그 (데이터에 포함된 경우)
        new_drug_tag = ""
        if row.get('신규여부', False) and row.get('사용기간', 0) > 0:
            usage_months_val = row['사용기간']
            new_drug_tag = f'<span class="new-drug-tag">신규<span class="help-icon" onclick="event.stopPropagation(); openNewDrugInfoModal(\'{drug_code}\', {usage_months_val}, {ma_months})">?</span></span>'

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
        chart_data_json = html_escape(json.dumps(chart_data, ensure_ascii=False))

        html += f"""
                                <tr class="high-row tab-clickable-row" data-drug-code="{drug_code}"
                                    data-chart-data='{chart_data_json}'
                                    onclick="toggleInlineChart(this, '{drug_code}')">
                                    <td style="text-align: center;" onclick="event.stopPropagation()">
                                        <div class="checkbox-memo-container">
                                            <button class="visibility-btn {hidden_class}" data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); toggleVisibility(this, '{drug_code}')"
                                                    title="{hidden_title}">{hidden_icon}</button>
                                            <button class="memo-btn {memo_btn_class}"
                                                    data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); openMemoModalGeneric('{drug_code}')"
                                                    title="{memo_preview if memo else '메모 추가'}">
                                                ✎
                                            </button>
                                        </div>
                                    </td>
                                    <td style="font-weight: bold;">{threshold_icon}{drug_name_display}</td>
                                    <td>{drug_code}</td>
                                    <td>{company_display}</td>
                                    <td>{row['최종_재고수량']:,.0f}</td>
                                    <td>{row['N개월_이동평균']:.2f}{new_drug_tag}</td>
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


def generate_excess_stock_section(excess_drugs_df, ma_months, months, threshold_high=12):
    """과다 재고 약품 섹션 HTML 생성 (테이블 형식 + 체크박스/메모 + 인라인 차트) - 모달용

    런웨이가 threshold_high개월을 초과하는 약품들 (유효기간 만료 위험)
    """
    import json

    if excess_drugs_df.empty:
        return ""

    # DB에서 체크된 약품 코드 목록 가져오기 (카테고리 없이)
    checked_codes = checked_items_db.get_checked_items()
    memos = drug_memos_db.get_all_memos()
    custom_thresholds = drug_thresholds_db.get_threshold_dict()

    html = f"""
                    <div style="padding: var(--space-4); background: var(--color-info-light); border-radius: var(--radius-lg); margin-bottom: var(--space-4);">
                        <div style="display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-2);">
                            <svg class="icon" style="color: var(--color-info-dark); flex-shrink: 0;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.29 7 12 12 20.71 7"/><line x1="12" x2="12" y1="22" y2="12"/>
                            </svg>
                            <p style="margin: 0; color: var(--color-info-dark); font-weight: 600;">
                                총 {len(excess_drugs_df)}개 약품의 런웨이가 {threshold_high}개월을 초과합니다.
                            </p>
                        </div>
                        <p style="margin: 0 0 0 30px; color: var(--color-info); font-size: 0.875rem;">
                            재고 소진에 {threshold_high}개월 이상 걸리므로, 유효기간 만료 전에 사용하지 못할 수 있습니다. 재고 조정을 고려해보세요.
                        </p>
                    </div>
                    <div class="table-container">
                        <table id="excess-drugs-table">
                            <thead>
                                <tr>
                                    <th style="width: 50px;">휴지통</th>
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

    for _, row in excess_drugs_df.iterrows():
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

        # 메모 가져오기
        memo = memos.get(drug_code, '')
        memo_btn_class = "has-memo" if memo else ""
        memo_preview = memo[:50] + '...' if len(memo) > 50 else memo

        # 개별 임계값 아이콘 (설정된 경우에만)
        threshold_icon = ""
        if drug_code in custom_thresholds:
            th = custom_thresholds[drug_code]
            tooltip_parts = []
            if th.get('절대재고_임계값') is not None:
                tooltip_parts.append(f"<span style='color:#a0aec0'>📦 개별 설정된 최소 안전 재고 수준:</span> <span style='color:#90cdf4'>{html_escape(str(th['절대재고_임계값']))}개</span>")
            if th.get('런웨이_임계값') is not None:
                tooltip_parts.append(f"<span style='color:#a0aec0'>📅 개별 설정된 최소 안전 런웨이:</span> <span style='color:#90cdf4'>{html_escape(str(th['런웨이_임계값']))}개월</span>")
            if th.get('환자목록'):
                patient_names = html_escape(', '.join(th['환자목록']))
                tooltip_parts.append(f"<span style='color:#a0aec0'>👤 복용 환자:</span> <span style='color:#90cdf4'>{patient_names}</span>")
            if tooltip_parts:
                tooltip_text = '<br>'.join(tooltip_parts)
                threshold_icon = f'<span class="threshold-indicator" data-tooltip="{tooltip_text}" onclick="event.stopPropagation(); showThresholdTooltip(event, this)"><svg class="icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg></span>'

        # 숨김 버튼 상태
        hidden_class = "hidden" if is_checked else ""
        hidden_icon = '<i class="bi bi-arrow-counterclockwise"></i>' if is_checked else '<i class="bi bi-trash"></i>'
        hidden_title = "복원하기" if is_checked else "휴지통에 넣기"

        # 신규 약품 태그 (데이터에 포함된 경우)
        new_drug_tag = ""
        if row.get('신규여부', False) and row.get('사용기간', 0) > 0:
            usage_months_val = row['사용기간']
            new_drug_tag = f'<span class="new-drug-tag">신규<span class="help-icon" onclick="event.stopPropagation(); openNewDrugInfoModal(\'{drug_code}\', {usage_months_val}, {ma_months})">?</span></span>'

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
        chart_data_json = html_escape(json.dumps(chart_data, ensure_ascii=False))

        html += f"""
                                <tr class="excess-row tab-clickable-row" data-drug-code="{drug_code}"
                                    data-chart-data='{chart_data_json}'
                                    onclick="toggleInlineChart(this, '{drug_code}')">
                                    <td style="text-align: center;" onclick="event.stopPropagation()">
                                        <div class="checkbox-memo-container">
                                            <button class="visibility-btn {hidden_class}" data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); toggleVisibility(this, '{drug_code}')"
                                                    title="{hidden_title}">{hidden_icon}</button>
                                            <button class="memo-btn {memo_btn_class}"
                                                    data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); openMemoModalGeneric('{drug_code}')"
                                                    title="{memo_preview if memo else '메모 추가'}">
                                                ✎
                                            </button>
                                        </div>
                                    </td>
                                    <td style="font-weight: bold;">{threshold_icon}{drug_name_display}</td>
                                    <td>{drug_code}</td>
                                    <td>{company_display}</td>
                                    <td>{row['최종_재고수량']:,.0f}</td>
                                    <td>{row['N개월_이동평균']:.2f}{new_drug_tag}</td>
                                    <td style="color: #2563eb; font-weight: bold;">{runway_display}</td>
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
                // 과다 탭 메모 데이터
                var excessDrugMemos = {memos_json};
            </script>
    """

    return html


def generate_dead_stock_section(dead_stock_drugs, ma_months, months):
    """악성 재고 섹션 HTML 생성 (테이블 형식 + 체크박스/메모/스파크라인 + 인라인 차트) - 모달용"""
    import json

    total_dead_stock = dead_stock_drugs['최종_재고수량'].sum()

    # DB에서 체크된 약품 코드 목록 가져오기 (카테고리 없이)
    checked_codes = checked_items_db.get_checked_items()
    memos = drug_memos_db.get_all_memos()
    custom_thresholds = drug_thresholds_db.get_threshold_dict()

    html = f"""
                    <div style="padding: var(--space-4); background: var(--bg-subtle); border-radius: var(--radius-lg); margin-bottom: var(--space-4);">
                        <div style="display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-2);">
                            <svg class="icon" style="color: var(--text-secondary); flex-shrink: 0;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.29 7 12 12 20.71 7"/><line x1="12" x2="12" y1="22" y2="12"/>
                            </svg>
                            <p style="margin: 0; color: var(--text-secondary); font-weight: 600;">
                                총 {len(dead_stock_drugs)}개 약품이 {ma_months}개월 동안 사용되지 않았으나 재고가 {total_dead_stock:,.0f}개 남아있습니다.
                            </p>
                        </div>
                        <p style="margin: 0 0 0 30px; color: var(--text-muted); font-size: 0.875rem;">
                            재고 정리 또는 반품을 고려해보세요.
                        </p>
                    </div>
                    <div class="table-container">
                        <table id="dead-drugs-table">
                            <thead>
                                <tr>
                                    <th style="width: 50px;">휴지통</th>
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

        # 메모 가져오기
        memo = memos.get(drug_code, '')
        memo_btn_class = "has-memo" if memo else ""
        memo_preview = memo[:50] + '...' if len(memo) > 50 else memo

        # 개별 임계값 아이콘 (설정된 경우에만)
        threshold_icon = ""
        if drug_code in custom_thresholds:
            th = custom_thresholds[drug_code]
            tooltip_parts = []
            if th.get('절대재고_임계값') is not None:
                tooltip_parts.append(f"<span style='color:#a0aec0'>📦 개별 설정된 최소 안전 재고 수준:</span> <span style='color:#90cdf4'>{html_escape(str(th['절대재고_임계값']))}개</span>")
            if th.get('런웨이_임계값') is not None:
                tooltip_parts.append(f"<span style='color:#a0aec0'>📅 개별 설정된 최소 안전 런웨이:</span> <span style='color:#90cdf4'>{html_escape(str(th['런웨이_임계값']))}개월</span>")
            if th.get('환자목록'):
                patient_names = html_escape(', '.join(th['환자목록']))
                tooltip_parts.append(f"<span style='color:#a0aec0'>👤 복용 환자:</span> <span style='color:#90cdf4'>{patient_names}</span>")
            if tooltip_parts:
                tooltip_text = '<br>'.join(tooltip_parts)
                threshold_icon = f'<span class="threshold-indicator" data-tooltip="{tooltip_text}" onclick="event.stopPropagation(); showThresholdTooltip(event, this)"><svg class="icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg></span>'

        # 숨김 버튼 상태
        hidden_class = "hidden" if is_checked else ""
        hidden_icon = '<i class="bi bi-arrow-counterclockwise"></i>' if is_checked else '<i class="bi bi-trash"></i>'
        hidden_title = "복원하기" if is_checked else "휴지통에 넣기"

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
        chart_data_json = html_escape(json.dumps(chart_data, ensure_ascii=False))

        html += f"""
                                <tr class="dead-row tab-clickable-row" data-drug-code="{drug_code}" style="background: rgba(247, 250, 252, 0.7);"
                                    data-chart-data='{chart_data_json}'
                                    onclick="toggleInlineChart(this, '{drug_code}')">
                                    <td style="text-align: center;" onclick="event.stopPropagation()">
                                        <div class="checkbox-memo-container">
                                            <button class="visibility-btn {hidden_class}" data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); toggleVisibility(this, '{drug_code}')"
                                                    title="{hidden_title}">{hidden_icon}</button>
                                            <button class="memo-btn {memo_btn_class}"
                                                    data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); openMemoModalGeneric('{drug_code}')"
                                                    title="{memo_preview if memo else '메모 추가'}">
                                                ✎
                                            </button>
                                        </div>
                                    </td>
                                    <td style="font-weight: bold;">{threshold_icon}{drug_name_display}</td>
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


def generate_negative_stock_section(negative_stock_drugs, ma_months, months):
    """음수 재고 섹션 HTML 생성 (테이블 형식 + 스파크라인 + 인라인 차트) - 모달용"""
    import json

    total_negative_stock = negative_stock_drugs['최종_재고수량'].sum()

    # DB에서 체크된 약품 코드 목록 가져오기
    checked_codes = checked_items_db.get_checked_items()
    memos = drug_memos_db.get_all_memos()

    html = f"""
                    <div style="padding: var(--space-4); background: var(--color-danger-light); border-radius: var(--radius-lg); margin-bottom: var(--space-4);">
                        <div style="display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-2);">
                            <svg class="icon" style="color: var(--color-danger); flex-shrink: 0;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/>
                            </svg>
                            <p style="margin: 0; color: var(--color-danger-dark); font-weight: 600;">
                                총 {len(negative_stock_drugs)}개 약품의 재고가 음수입니다. (총 {total_negative_stock:,.0f}개)
                            </p>
                        </div>
                        <p style="margin: 0 0 0 30px; color: var(--color-danger); font-size: 0.875rem;">
                            음수 재고는 실제 재고보다 더 많이 출고된 상태를 의미합니다. 재고 실사 또는 데이터 확인이 필요합니다.
                        </p>
                    </div>
                    <div class="table-container">
                        <table id="negative-drugs-table">
                            <thead>
                                <tr>
                                    <th style="width: 50px;">휴지통</th>
                                    <th>약품명</th>
                                    <th>약품코드</th>
                                    <th>제약회사</th>
                                    <th>재고수량</th>
                                    <th>{ma_months}개월 이동평균</th>
                                    <th>비고</th>
                                    <th>트렌드</th>
                                </tr>
                            </thead>
                            <tbody>
    """

    for _, row in negative_stock_drugs.iterrows():
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

        # 메모 가져오기
        memo = memos.get(drug_code, '')
        memo_btn_class = "has-memo" if memo else ""
        memo_preview = memo[:50] + '...' if len(memo) > 50 else memo

        # 숨김 버튼 상태
        hidden_class = "hidden" if is_checked else ""
        hidden_icon = '<i class="bi bi-arrow-counterclockwise"></i>' if is_checked else '<i class="bi bi-trash"></i>'
        hidden_title = "복원하기" if is_checked else "휴지통에 넣기"

        # 비고 (사용 중인지 여부)
        usage_note = "사용 중" if latest_ma > 0 else "미사용"
        usage_color = "#059669" if latest_ma > 0 else "#6b7280"

        # 인라인 차트용 데이터 생성
        chart_data = {
            'drug_name': row['약품명'] if row['약품명'] else "정보없음",
            'drug_code': drug_code,
            'timeseries': list(timeseries),
            'ma': list(ma),
            'months': months,
            'ma_months': ma_months,
            'stock': int(row['최종_재고수량']),
            'latest_ma': float(latest_ma) if latest_ma else 0,
            'runway': '음수 재고'
        }
        chart_data_json = html_escape(json.dumps(chart_data, ensure_ascii=False))

        html += f"""
                                <tr class="negative-row tab-clickable-row" data-drug-code="{drug_code}" style="background: rgba(254, 242, 242, 0.7);"
                                    data-chart-data='{chart_data_json}'
                                    onclick="toggleInlineChart(this, '{drug_code}')">
                                    <td style="text-align: center;" onclick="event.stopPropagation()">
                                        <div class="checkbox-memo-container">
                                            <button class="visibility-btn {hidden_class}" data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); toggleVisibility(this, '{drug_code}')"
                                                    title="{hidden_title}">{hidden_icon}</button>
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
                                    <td style="color: #dc2626; font-weight: bold;">{row['최종_재고수량']:,.0f}</td>
                                    <td>{latest_ma:.2f}</td>
                                    <td style="color: {usage_color}; font-weight: 500;">{usage_note}</td>
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
                // 음수재고 탭 메모 데이터
                var negativeDrugMemos = {memos_json};
            </script>
    """

    return html


def generate_hidden_drugs_section(df, ma_months, months):
    """숨김 처리된 약품 섹션 HTML 생성 - 모달용

    모든 약품을 포함하고, JavaScript로 숨김 상태에 따라 표시/숨김 처리
    """

    # 체크된 항목(숨김 처리된 항목) 가져오기
    checked_items = checked_items_db.get_checked_items()
    checked_items_status = checked_items_db.get_checked_items_with_status()
    memos = drug_memos_db.get_all_memos()
    custom_thresholds = drug_thresholds_db.get_threshold_dict()

    html = f"""
                    <div id="hidden-empty-message" style="padding: var(--space-8); text-align: center; color: var(--text-muted); display: none;">
                        <svg class="icon-xl" style="width: 48px; height: 48px; margin: 0 auto var(--space-4);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
                        </svg>
                        <p style="font-size: 1.125rem; margin-bottom: var(--space-2);">휴지통이 비어있습니다.</p>
                        <p style="font-size: 0.875rem;">각 탭에서 휴지통 버튼을 클릭하여 약품을 정리할 수 있습니다.</p>
                    </div>
                    <div class="table-container" style="max-height: 70vh; overflow-y: auto;">
                        <table id="hidden-drugs-table">
                            <thead>
                                <tr>
                                    <th style="width: 50px;">휴지통</th>
                                    <th style="width: 80px;">처리 상태</th>
                                    <th>약품명</th>
                                    <th>약품코드</th>
                                    <th>제약회사</th>
                                    <th>재고수량</th>
                                    <th>{ma_months}개월 이동평균</th>
                                    <th>런웨이</th>
                                    <th style="width: 100px;">트렌드</th>
                                </tr>
                            </thead>
                            <tbody>
    """

    # 모든 약품을 포함 (숨김 처리 안된 것은 display:none으로 숨김)
    for _, row in df.iterrows():
        drug_code = str(row['약품코드'])

        # 숨김 상태 확인
        is_hidden = drug_code in checked_items
        row_display_style = "" if is_hidden else "display: none;"
        hidden_btn_class = "hidden" if is_hidden else ""
        hidden_icon = '<i class="bi bi-arrow-counterclockwise"></i>' if is_hidden else '<i class="bi bi-trash"></i>'
        hidden_title = "복원하기" if is_hidden else "휴지통에 넣기"

        # 처리 상태
        process_status = checked_items_status.get(drug_code, '대기중')

        # 약품명 30자 제한
        drug_name = row['약품명'] if row['약품명'] else "정보없음"
        drug_name_display = drug_name[:30] + "..." if len(drug_name) > 30 else drug_name

        # 제약회사 12자 제한
        company_display = row['제약회사'] if row['제약회사'] is not None else "정보없음"
        if len(company_display) > 12:
            company_display = company_display[:12] + "..."

        # 메모 가져오기
        memo = memos.get(drug_code, '')
        memo_btn_class = "has-memo" if memo else ""
        memo_preview = memo[:50] + '...' if len(memo) > 50 else memo

        # N개월 이동평균 계산
        timeseries = row['월별_조제수량_리스트']
        ma = calculate_custom_ma(timeseries, ma_months)
        latest_ma = None
        for val in reversed(ma):
            if val is not None:
                latest_ma = val
                break
        latest_ma = latest_ma if latest_ma else 0

        # 스파크라인 생성
        sparkline_html = create_sparkline_svg(timeseries, ma, ma_months)

        # 런웨이 계산
        stock = row['최종_재고수량']
        if latest_ma > 0:
            runway_months = stock / latest_ma
            if runway_months < 1:
                runway_days = runway_months * 30
                runway_display = f"{runway_days:.0f}일"
            else:
                runway_display = f"{runway_months:.1f}개월"
        else:
            runway_display = "N/A"

        # 인라인 차트용 데이터 생성
        chart_data = {
            'drug_name': row['약품명'] if row['약품명'] else "정보없음",
            'drug_code': drug_code,
            'timeseries': list(timeseries),
            'ma': list(ma),
            'months': months,
            'ma_months': ma_months,
            'stock': int(stock),
            'latest_ma': latest_ma,
            'runway': runway_display
        }
        chart_data_json = html_escape(json.dumps(chart_data, ensure_ascii=False))

        # 개별 임계값 아이콘 (설정된 경우에만)
        threshold_icon = ""
        if drug_code in custom_thresholds:
            th = custom_thresholds[drug_code]
            tooltip_parts = []
            if th.get('절대재고_임계값') is not None:
                tooltip_parts.append(f"<span style='color:#a0aec0'>📦 개별 설정된 최소 안전 재고 수준:</span> <span style='color:#90cdf4'>{html_escape(str(th['절대재고_임계값']))}개</span>")
            if th.get('런웨이_임계값') is not None:
                tooltip_parts.append(f"<span style='color:#a0aec0'>📅 개별 설정된 최소 안전 런웨이:</span> <span style='color:#90cdf4'>{html_escape(str(th['런웨이_임계값']))}개월</span>")
            if th.get('환자목록'):
                patient_names = html_escape(', '.join(th['환자목록']))
                tooltip_parts.append(f"<span style='color:#a0aec0'>👤 복용 환자:</span> <span style='color:#90cdf4'>{patient_names}</span>")
            if tooltip_parts:
                tooltip_text = '<br>'.join(tooltip_parts)
                threshold_icon = f'<span class="threshold-indicator" data-tooltip="{tooltip_text}" onclick="event.stopPropagation(); showThresholdTooltip(event, this)"><svg class="icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg></span>'

        html += f"""
                                <tr class="hidden-row-item tab-clickable-row" data-drug-code="{drug_code}"
                                    data-chart-data='{chart_data_json}' style="{row_display_style}"
                                    onclick="toggleInlineChart(this, '{drug_code}')">
                                    <td style="text-align: center;" onclick="event.stopPropagation()">
                                        <div class="checkbox-memo-container">
                                            <button class="visibility-btn {hidden_btn_class}" data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); toggleVisibility(this, '{drug_code}')"
                                                    title="{hidden_title}">{hidden_icon}</button>
                                            <button class="memo-btn {memo_btn_class}"
                                                    data-drug-code="{drug_code}"
                                                    onclick="event.stopPropagation(); openMemoModalGeneric('{drug_code}')"
                                                    title="{memo_preview if memo else '메모 추가'}">
                                                ✎
                                            </button>
                                        </div>
                                    </td>
                                    <td style="text-align: center;"><span class="process-status-badge status-{process_status}">{process_status}</span></td>
                                    <td style="font-weight: bold;">{threshold_icon}{drug_name_display}</td>
                                    <td>{drug_code}</td>
                                    <td>{company_display}</td>
                                    <td>{stock:,.0f}</td>
                                    <td>{latest_ma:.2f}</td>
                                    <td>{runway_display}</td>
                                    <td>{sparkline_html}</td>
                                </tr>
        """

    html += """
                            </tbody>
                        </table>
                    </div>
    """

    return html


def analyze_runway(df, months, ma_months, threshold_low=3, threshold_high=12):
    """런웨이 분석 및 약품 분류 - N-MA 런웨이 기준

    Args:
        df: 약품 데이터 DataFrame
        months: 월 리스트
        ma_months: 이동평균 개월 수
        threshold_low: 부족/충분 경계 (개월)
        threshold_high: 충분/과다 경계 (개월)

    Returns:
        tuple: (None, None, None, low_count, high_count, excess_count, low_drugs_df, high_drugs_df, excess_drugs_df)
               - 앞 3개 값(chart_js)은 더 이상 사용되지 않음 (하위 호환성을 위해 유지)
    """
    try:
        # N-MA 런웨이를 숫자로 변환 (개월 단위)
        low_data = []  # threshold_low 이하 (차트용) - 부족
        high_data = []  # threshold_low 초과 ~ threshold_high 이하 (차트용) - 충분
        excess_data = []  # threshold_high 초과 (차트용) - 과다
        low_drugs_list = []  # threshold_low 이하 (테이블용) - 부족
        high_drugs_list = []  # threshold_low 초과 ~ threshold_high 이하 (테이블용) - 충분
        excess_drugs_list = []  # threshold_high 초과 (테이블용) - 과다

        for idx, row in df.iterrows():
            # N개월 이동평균 계산 (보정 버전)
            timeseries = row['월별_조제수량_리스트']
            latest_ma, usage_months, is_corrected = get_corrected_ma(timeseries, ma_months)

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

                # 테이블용 데이터 (전체 row 정보 + 계산된 값 + 신규 정보)
                drug_data = {
                    '약품코드': row['약품코드'],
                    '약품명': row['약품명'],
                    '제약회사': row['제약회사'],
                    '최종_재고수량': row['최종_재고수량'],
                    'N개월_이동평균': latest_ma,
                    '런웨이_개월': ma_runway_months,
                    '월별_조제수량_리스트': timeseries,
                    '사용기간': usage_months,
                    '신규여부': is_corrected
                }

                if ma_runway_months <= threshold_low:
                    # 부족: 런웨이 threshold_low 이하
                    low_data.append(data_tuple)
                    low_drugs_list.append(drug_data)
                elif ma_runway_months <= threshold_high:
                    # 충분: 런웨이 threshold_low 초과 ~ threshold_high 이하
                    high_data.append(data_tuple)
                    high_drugs_list.append(drug_data)
                else:
                    # 과다: 런웨이 threshold_high 초과
                    excess_data.append(data_tuple)
                    excess_drugs_list.append(drug_data)

        # DataFrame 생성
        import pandas as pd
        low_drugs_df = pd.DataFrame(low_drugs_list) if low_drugs_list else pd.DataFrame()
        high_drugs_df = pd.DataFrame(high_drugs_list) if high_drugs_list else pd.DataFrame()
        excess_drugs_df = pd.DataFrame(excess_drugs_list) if excess_drugs_list else pd.DataFrame()

        # 정렬: 부족/충분은 런웨이 오름차순, 과다는 런웨이 내림차순
        if not low_drugs_df.empty:
            low_drugs_df = low_drugs_df.sort_values('런웨이_개월', ascending=True)
        if not high_drugs_df.empty:
            high_drugs_df = high_drugs_df.sort_values('런웨이_개월', ascending=True)
        if not excess_drugs_df.empty:
            excess_drugs_df = excess_drugs_df.sort_values('런웨이_개월', ascending=False)

        chart_js_low = None
        chart_js_high = None
        chart_js_excess = None
        low_count = len(low_data)
        high_count = len(high_data)
        excess_count = len(excess_data)

        return chart_js_low, chart_js_high, chart_js_excess, low_count, high_count, excess_count, low_drugs_df, high_drugs_df, excess_drugs_df
    except Exception as e:
        print(f"Error in analyze_runway: {e}")
        import traceback
        traceback.print_exc()
    return None, None, None, 0, 0, 0, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

def create_and_save_report(df, months, mode='dispense', ma_months=3, threshold_low=3, threshold_high=12, open_browser=True):
    """보고서를 생성하고 파일로 저장하는 함수

    Args:
        df: DataFrame (시계열 데이터 포함)
        months: 월 리스트
        mode: 'dispense' (전문약) 또는 'sale' (일반약)
        ma_months: 이동평균 개월 수
        threshold_low: 부족/충분 경계 (개월)
        threshold_high: 충분/과다 경계 (개월)
        open_browser: 브라우저에서 자동으로 열기 여부
    """
    print("\n=== 단순 보고서 생성 준비 ===")
    print(f"   이동평균 기간: {ma_months}개월")
    print(f"   런웨이 경계값: 부족≤{threshold_low} < 충분≤{threshold_high} < 과다")

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
    output_dir = paths.get_reports_path('inventory')
    os.makedirs(output_dir, exist_ok=True)

    # HTML 보고서 생성
    print("\n📝 HTML 보고서 생성 중...")
    html_content = generate_html_report(df_final, months, mode=mode, ma_months=ma_months,
                                        threshold_low=threshold_low, threshold_high=threshold_high)

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
