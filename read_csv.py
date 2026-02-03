import pandas as pd
import os
import sys
import re
from datetime import datetime
import inventory_db
from utils import normalize_drug_code
import paths

def select_file_from_directory(directory=None):
    """디렉토리에서 파일을 선택하는 함수"""
    if directory is None:
        directory = paths.DATA_PATH
    if not os.path.exists(directory):
        print(f"'{directory}' 디렉토리가 존재하지 않습니다.")
        return None

    files = [f for f in os.listdir(directory) if f.endswith('.csv')]

    if not files:
        print(f"'{directory}' 디렉토리에 CSV 파일이 없습니다.")
        return None

    print(f"\n'{directory}' 디렉토리의 파일 목록:")
    for i, file in enumerate(files, 1):
        print(f"{i}. {file}")

    while True:
        try:
            choice = int(input(f"\n파일을 선택하세요 (1-{len(files)}): "))
            if 1 <= choice <= len(files):
                selected_file = os.path.join(directory, files[choice - 1])
                print(f"선택된 파일: {selected_file}")
                return selected_file
            else:
                print(f"1부터 {len(files)} 사이의 숫자를 입력해주세요.")
        except ValueError:
            print("올바른 숫자를 입력해주세요.")
        except KeyboardInterrupt:
            print("\n프로그램을 종료합니다.")
            sys.exit()


def read_csv_file(file_path):
    """CSV 파일을 읽는 함수"""
    print(f"파일 읽는 중: {file_path}")

    # 파일 크기 확인
    file_size = os.path.getsize(file_path)
    print(f"파일 크기: {file_size:,} bytes")

    # CSV 파일 읽기 시도 (여러 인코딩으로)
    try:
        print("CSV 파일 읽기 시도 (UTF-8 인코딩)...")
        df_all = pd.read_csv(file_path, encoding='utf-8')
        print("✅ CSV 파일 읽기 성공!")
        return df_all
    except Exception as e:
        print(f"⚠️ UTF-8 읽기 실패: {str(e)[:50]}...")

    try:
        print("CSV 파일 읽기 시도 (CP949 인코딩)...")
        df_all = pd.read_csv(file_path, encoding='cp949')
        print("✅ CSV 파일 읽기 성공! (CP949 인코딩)")
        return df_all
    except Exception as e:
        print(f"❌ CP949 읽기도 실패: {str(e)[:50]}...")

    try:
        print("CSV 파일 읽기 시도 (EUC-KR 인코딩)...")
        df_all = pd.read_csv(file_path, encoding='euc-kr')
        print("✅ CSV 파일 읽기 성공! (EUC-KR 인코딩)")
        return df_all
    except Exception as e:
        print(f"❌ EUC-KR 읽기도 실패: {str(e)[:50]}...")

    # 모든 인코딩 실패시
    print("\n❌ CSV 파일을 읽을 수 없습니다.")
    print("💡 가능한 해결방법:")
    print("1. 파일이 올바른 CSV 형식인지 확인")
    print("2. Excel에서 'CSV(UTF-8)(*.csv)' 형식으로 다시 저장")

    # 다른 파일 선택 옵션 제공
    retry = input("\n다른 파일을 선택하시겠습니까? (y/n): ")
    if retry.lower() == 'y':
        new_file = select_file_from_directory()
        if new_file and new_file != file_path:
            return read_csv_file(new_file)

    raise Exception("CSV 파일을 읽을 수 없습니다")

def extract_month_from_file(filename):
    """파일명에서 날짜 정보 추출 (예: 2025-01.csv, 202501.csv, 2025_01.csv, 25_01.csv 등)"""
    # 4자리 연도 패턴 (우선 매칭)
    patterns_4digit = [
        r'(\d{4})[-_]?(\d{2})',  # 2025-01, 202501, 2025_01
        r'(\d{4})년\s*(\d{1,2})월',  # 2025년 1월
    ]

    for pattern in patterns_4digit:
        match = re.search(pattern, filename)
        if match:
            year, month = match.groups()
            return f"{year}-{month.zfill(2)}"

    # 2자리 연도 패턴 (4자리 매칭 실패 시)
    patterns_2digit = [
        r'(\d{2})[-_](\d{2})',  # 25-01, 25_01
        r'(\d{2})년\s*(\d{1,2})월',  # 25년 1월
    ]

    for pattern in patterns_2digit:
        match = re.search(pattern, filename)
        if match:
            year_2digit, month = match.groups()
            year_int = int(year_2digit)
            # 00-49 → 2000-2049, 50-99 → 1950-1999
            if year_int < 50:
                year = 2000 + year_int
            else:
                year = 1900 + year_int
            return f"{year}-{month.zfill(2)}"

    return None

def load_multiple_csv_files(directory=None):
    """여러 월별 데이터 파일을 읽어 월별 데이터로 구성 (CSV, XLS, XLSX 지원)"""
    if directory is None:
        directory = paths.DATA_PATH
    if not os.path.exists(directory):
        print(f"'{directory}' 디렉토리가 존재하지 않습니다.")
        return None

    # CSV, XLS, XLSX 파일 모두 검색
    files = sorted([f for f in os.listdir(directory)
                   if f.endswith(('.csv', '.xls', '.xlsx'))])

    if not files:
        print(f"'{directory}' 디렉토리에 데이터 파일이 없습니다 (CSV, XLS, XLSX).")
        return None

    print(f"\n'{directory}' 디렉토리에서 {len(files)}개의 데이터 파일을 발견했습니다.")

    monthly_data = {}

    for file in files:
        month = extract_month_from_file(file)
        if month:
            file_path = os.path.join(directory, file)
            print(f"읽는 중: {file} → {month}")

            df = None
            ext = os.path.splitext(file)[1].lower()

            # 파일 형식에 따라 읽기
            if ext == '.csv':
                # CSV 파일 읽기 (여러 인코딩 시도)
                # dtype={'약품코드': str}로 약품코드의 선행 0 보존
                for encoding in ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr']:
                    try:
                        df = pd.read_csv(file_path, encoding=encoding, dtype={'약품코드': str})
                        break
                    except:
                        continue

            elif ext in ['.xls', '.xlsx']:
                # Excel 파일 읽기
                # dtype={'약품코드': str}로 약품코드의 선행 0 보존
                try:
                    # .xls는 calamine, .xlsx는 openpyxl 우선 사용
                    engine = 'calamine' if ext == '.xls' else 'openpyxl'
                    df = pd.read_excel(file_path, engine=engine, dtype={'약품코드': str})
                except:
                    # 실패 시 다른 엔진 시도
                    try:
                        fallback_engine = 'openpyxl' if ext == '.xls' else 'calamine'
                        df = pd.read_excel(file_path, engine=fallback_engine, dtype={'약품코드': str})
                    except:
                        pass

            if df is not None:
                # 파일 로드 시 약품코드 정규화 (1회만 수행)
                if '약품코드' in df.columns:
                    df['약품코드'] = df['약품코드'].apply(normalize_drug_code)
                monthly_data[month] = df
                print(f"  ✅ 성공: {len(df)}개 행")
            else:
                print(f"  ⚠️ 실패: {file}")
        else:
            print(f"⚠️ 날짜 정보를 추출할 수 없습니다: {file}")

    if not monthly_data:
        print("읽을 수 있는 월별 데이터가 없습니다.")
        return None

    print(f"\n총 {len(monthly_data)}개월의 데이터를 로드했습니다.")
    return monthly_data

def merge_by_drug_code(monthly_data, mode='dispense'):
    """약품코드 기준으로 월별 데이터 통합

    Args:
        monthly_data: 월별 데이터 딕셔너리
        mode: 'dispense' (전문약, 조제수량만) 또는 'sale' (일반약, 판매수량만)
    """
    if not monthly_data:
        return None

    mode_name = '조제수량 (전문약)' if mode == 'dispense' else '판매수량 (일반약)'
    print(f"\n약품코드 기준으로 데이터 통합 중... (모드: {mode_name})")

    # 모든 약품코드 수집 (NaN 제외)
    # 참고: 약품코드는 load_multiple_csv_files()에서 이미 정규화됨
    all_drug_codes = set()
    for month, df in monthly_data.items():
        if '약품코드' in df.columns:
            # 'nan' 제외하고 수집
            codes = df['약품코드'].unique()
            all_drug_codes.update([code for code in codes if code != 'nan'])

    print(f"총 {len(all_drug_codes)}개의 약품 발견")

    # 월 리스트 (시간순 정렬)
    months = sorted(monthly_data.keys())

    # 결과 데이터프레임 구축
    result_rows = []

    # 최신순으로 순회하기 위한 역순 리스트 생성
    months_reversed = list(reversed(months))

    for drug_code in all_drug_codes:
        row_data = {
            '약품코드': drug_code,
            '약품명': None,
            '제약회사': None,
            '최종_재고수량': None  # None으로 초기화 (아직 채택 안 됨)
        }

        monthly_quantities = []

        # Step 1: 약품명/제약회사 채택 (최신 월 우선 - 역순 탐색)
        for month in months_reversed:
            df = monthly_data[month]
            if '약품코드' not in df.columns:
                continue

            # 해당 약품코드 찾기
            drug_row = df[df['약품코드'] == drug_code]

            if not drug_row.empty:
                drug_row = drug_row.iloc[0]

                # 최신 월의 약품명/제약회사 채택 (유효한 값이 있으면)
                if pd.notna(drug_row.get('약품명')) and row_data['약품명'] is None:
                    row_data['약품명'] = drug_row['약품명']
                    row_data['제약회사'] = drug_row.get('제약회사', '')
                    break  # 최신 정보 발견 시 중단

        # Step 2: 월별 조제/판매 수량 수집 (시간순 정방향)
        for month in months:
            df = monthly_data[month]
            if '약품코드' not in df.columns:
                continue

            # 해당 약품코드 찾기
            drug_row = df[df['약품코드'] == drug_code]

            if not drug_row.empty:
                drug_row = drug_row.iloc[0]

                # mode에 따라 조제수량 또는 판매수량만 추출
                qty = 0

                if mode == 'dispense':
                    # 전문약 모드: 조제수량만
                    if '조제수량' in drug_row:
                        dispense = str(drug_row['조제수량']).replace(',', '').replace('-', '0')
                        qty = pd.to_numeric(dispense, errors='coerce')
                        if pd.isna(qty):
                            qty = 0
                elif mode == 'sale':
                    # 일반약 모드: 판매수량만
                    if '판매수량' in drug_row:
                        sale = str(drug_row['판매수량']).replace(',', '').replace('-', '0')
                        qty = pd.to_numeric(sale, errors='coerce')
                        if pd.isna(qty):
                            qty = 0

                monthly_quantities.append(qty)
                row_data[f'{month}_조제수량'] = qty
            else:
                # 해당 월에 데이터가 없는 경우
                row_data[f'{month}_조제수량'] = 0
                monthly_quantities.append(0)

        # Step 3: 최신 재고수량 채택 (최신 월 우선 - 역순 탐색)
        for month in months_reversed:
            df = monthly_data[month]
            if '약품코드' not in df.columns:
                continue

            drug_row = df[df['약품코드'] == drug_code]

            if not drug_row.empty and '재고수량' in drug_row.columns:
                drug_row = drug_row.iloc[0]
                # 콤마만 제거 (음수 기호는 유지)
                stock = str(drug_row['재고수량']).replace(',', '')
                stock = pd.to_numeric(stock, errors='coerce')
                # 유효한 숫자면 채택 (음수 포함, NaN 제외)
                if pd.notna(stock):
                    row_data['최종_재고수량'] = stock
                    break  # 가장 최신의 유효한 재고를 찾았으므로 중단

        # 여전히 None이면 0으로 설정
        if row_data['최종_재고수량'] is None:
            row_data['최종_재고수량'] = 0

        # 약품명이 여전히 None이면 빈 문자열로 설정
        if row_data['약품명'] is None:
            row_data['약품명'] = ''
            row_data['제약회사'] = ''

        # 시계열 데이터 저장 (리스트 형태)
        row_data['월별_조제수량_리스트'] = monthly_quantities

        result_rows.append(row_data)

    result_df = pd.DataFrame(result_rows)
    print(f"통합 완료: {len(result_df)}개 약품 (필터링 전)")

    # 전체 기간 동안 소모량이 0인 약품 제외
    before_count = len(result_df)
    result_df = result_df[result_df['월별_조제수량_리스트'].apply(lambda x: sum(x) > 0)]
    after_count = len(result_df)
    filtered_count = before_count - after_count

    mode_name = '조제수량' if mode == 'dispense' else '판매수량'
    print(f"필터링 완료: 전체 기간 {mode_name}이 0인 {filtered_count}개 약품 제외")
    print(f"최종 약품 수: {after_count}개")

    return result_df, months

def calculate_statistics(df, months):
    """통계 계산: 1년 이동평균, 3개월 이동평균, 런웨이"""
    print("\n통계 계산 중...")

    # 1년 이동평균 계산 (12개월 이동평균, 최근 트렌드 반영)
    def calculate_12ma(quantities):
        """
        12개월 이동평균 계산
        - 12개월 이상 데이터: 최근 12개월 평균
        - 12개월 미만 데이터: available months로 평균 (fallback)
        """
        if len(quantities) == 0:
            return 0

        # 최근 12개월 데이터 추출 (또는 가능한 모든 데이터)
        recent_data = quantities[-12:] if len(quantities) >= 12 else quantities

        return sum(recent_data) / len(recent_data)

    df['1년_이동평균'] = df['월별_조제수량_리스트'].apply(calculate_12ma)

    # 3개월 이동평균 계산
    def calculate_ma3(quantities):
        if len(quantities) < 3:
            return [None] * len(quantities)

        ma3 = []
        for i in range(len(quantities)):
            if i < 2:
                ma3.append(None)
            else:
                ma3.append(sum(quantities[i-2:i+1]) / 3)

        return ma3

    df['3개월_이동평균_리스트'] = df['월별_조제수량_리스트'].apply(calculate_ma3)

    # 런웨이 계산 (1년 이동평균 기반)
    def calculate_runway(row):
        if row['1년_이동평균'] == 0:
            return '재고만 있음'

        runway_months = row['최종_재고수량'] / row['1년_이동평균']

        if runway_months >= 1:
            return f"{runway_months:.2f}개월"
        else:
            runway_days = runway_months * 30.417
            return f"{runway_days:.2f}일"

    df['런웨이'] = df.apply(calculate_runway, axis=1)

    print("통계 계산 완료")

    return df

def process_inventory_data(df_all, m, mode='dispense'):
    """재고 데이터를 처리하고 분석하는 함수

    Args:
        df_all: 전체 데이터프레임
        m: 개월 수
        mode: 'dispense' (전문약, 조제수량만) 또는 'sale' (일반약, 판매수량만)
    """

    mode_name = '조제수량 (전문약)' if mode == 'dispense' else '판매수량 (일반약)'
    print(f"재고 데이터 처리 중... (모드: {mode_name})")

    # 전체 컬럼 확인
    print("전체 컬럼 목록:")
    print(df_all.columns.tolist())
    print("\n" + "="*50 + "\n")

    # 필요한 컬럼만 선택
    required_columns = ['약품명', '제약회사', '약품코드', '재고수량', '조제수량', '판매수량']

    # 컬럼이 존재하는지 확인하고 선택
    available_columns = [col for col in required_columns if col in df_all.columns]
    missing_columns = [col for col in required_columns if col not in df_all.columns]

    if missing_columns:
        print(f"다음 컬럼을 찾을 수 없습니다: {missing_columns}")
        print("\n사용 가능한 컬럼으로 매칭 시도...")

        # 비슷한 컬럼명 찾기 (대소문자, 공백 무시)
        for missing_col in missing_columns:
            for actual_col in df_all.columns:
                if missing_col.replace(' ', '').lower() in actual_col.replace(' ', '').lower():
                    print(f"'{missing_col}' -> '{actual_col}' 으로 매칭 가능")

    if available_columns:
        df = df_all[available_columns].copy()  # .copy() 추가하여 명시적 복사
        print(f"\n선택된 컬럼: {available_columns}")
        print(f"데이터프레임 형태: {df.shape}")

        # 월평균 소모량 계산 (mode에 따라 조제수량 또는 판매수량만)
        if mode == 'dispense':
            # 전문약 모드: 조제수량만
            if '조제수량' in df.columns:
                df['조제수량'] = df['조제수량'].astype(str).str.replace(',', '').replace('-', '0')
                df['조제수량'] = pd.to_numeric(df['조제수량'], errors='coerce').fillna(0)
                df['월평균_조제수량'] = df['조제수량'] / m
                print(f"\n{m}개월 데이터를 기준으로 월평균 조제수량을 계산했습니다.")
        elif mode == 'sale':
            # 일반약 모드: 판매수량만
            if '판매수량' in df.columns:
                df['판매수량'] = df['판매수량'].astype(str).str.replace(',', '').replace('-', '0')
                df['판매수량'] = pd.to_numeric(df['판매수량'], errors='coerce').fillna(0)
                df['월평균_조제수량'] = df['판매수량'] / m
                print(f"\n{m}개월 데이터를 기준으로 월평균 판매수량을 계산했습니다.")

            # 재고수량도 숫자로 변환 (음수 허용)
            if '재고수량' in df.columns:
                df['재고수량'] = df['재고수량'].astype(str).str.replace(',', '')
                df['재고수량'] = pd.to_numeric(df['재고수량'], errors='coerce').fillna(0)

                # 런웨이 계산
                def calculate_runway(row):
                    if row['월평균_조제수량'] == 0:
                        return '재고만 있음'

                    runway_months = row['재고수량'] / row['월평균_조제수량']

                    if runway_months >= 1:
                        # 1개월 이상인 경우 개월로 표시
                        return f"{runway_months:.2f}개월"
                    else:
                        # 1개월 미만인 경우 일로 변환
                        runway_days = runway_months * 30.417
                        return f"{runway_days:.2f}일"

                df['런웨이'] = df.apply(calculate_runway, axis=1)
                print("런웨이(재고 소진 예상 기간)을 계산했습니다.")

        print("\n처음 10개 행:")
        print(df.head(10))

        return df, m
    else:
        print("요청한 컬럼을 찾을 수 없습니다.")
        print("\n처음 5개 행 (전체 데이터):")
        print(df_all.head())
        return None, None

def init_recent_inventory_from_latest_month(result_df, drug_type='미분류'):
    """
    가장 최근 월의 재고수량으로 recent_inventory.sqlite3 초기화

    Args:
        result_df: merge_by_drug_code에서 반환된 DataFrame (최종_재고수량 포함)
        drug_type: 약품유형 ('전문약', '일반약', '미분류')
    """
    print(f"\n=== recent_inventory.sqlite3에 {drug_type} 데이터 추가 ===")

    # DB 초기화 (테이블이 없으면 생성)
    inventory_db.init_db()

    # 필요한 데이터 추출
    inventory_data = result_df[['약품코드', '약품명', '제약회사', '최종_재고수량']].copy()
    inventory_data.rename(columns={'최종_재고수량': '현재_재고수량'}, inplace=True)
    inventory_data['약품유형'] = drug_type

    # DB에 저장 (UPSERT이므로 기존 데이터는 업데이트, 신규는 추가)
    result = inventory_db.upsert_inventory(inventory_data, show_summary=True)

    print(f"✅ {drug_type} 데이터 DB 저장 완료!")
    print(f"   업데이트: {result['updated']}개, 신규 추가: {result['inserted']}개")


if __name__ == "__main__":
    # read_csv.py는 직접 실행하지 않습니다
    # init_db.py를 사용하세요
    print("=" * 60)
    print("❌ 이 파일은 직접 실행할 수 없습니다.")
    print("=" * 60)
    print()
    print("💡 대신 다음 명령어를 사용하세요:")
    print("   python init_db.py       # DB 초기화")
    print("   python web_app.py       # 보고서 생성 및 주문 산출")
    print()
    print("=" * 60)
    sys.exit(1)