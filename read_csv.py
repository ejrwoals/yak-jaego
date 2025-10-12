import pandas as pd
import os
import sys
import re
from datetime import datetime

def select_file_from_directory(directory='data'):
    """디렉토리에서 파일을 선택하는 함수"""
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
    """파일명에서 날짜 정보 추출 (예: 2025-01.csv, 202501.csv, 2025_01.csv 등)"""
    patterns = [
        r'(\d{4})[-_]?(\d{2})',  # 2025-01, 202501, 2025_01
        r'(\d{4})년\s*(\d{1,2})월',  # 2025년 1월
    ]

    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            year, month = match.groups()
            return f"{year}-{month.zfill(2)}"

    return None

def load_multiple_csv_files(directory='data'):
    """여러 CSV 파일을 읽어 월별 데이터로 구성"""
    if not os.path.exists(directory):
        print(f"'{directory}' 디렉토리가 존재하지 않습니다.")
        return None

    files = sorted([f for f in os.listdir(directory) if f.endswith('.csv')])

    if not files:
        print(f"'{directory}' 디렉토리에 CSV 파일이 없습니다.")
        return None

    print(f"\n'{directory}' 디렉토리에서 {len(files)}개의 CSV 파일을 발견했습니다.")

    monthly_data = {}

    for file in files:
        month = extract_month_from_file(file)
        if month:
            file_path = os.path.join(directory, file)
            print(f"읽는 중: {file} → {month}")

            # CSV 파일 읽기 (여러 인코딩 시도)
            df = None
            for encoding in ['utf-8', 'cp949', 'euc-kr']:
                try:
                    df = pd.read_csv(file_path, encoding=encoding)
                    break
                except:
                    continue

            if df is not None:
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
    all_drug_codes = set()
    for month, df in monthly_data.items():
        if '약품코드' in df.columns:
            # 약품코드를 string으로 변환 (float 형태의 .0 제거)
            df['약품코드'] = df['약품코드'].astype(str).str.strip()
            # .0으로 끝나는 경우 제거 (예: "673400030.0" → "673400030")
            df['약품코드'] = df['약품코드'].str.replace(r'\.0$', '', regex=True)
            # 'nan' 제외하고 수집
            codes = df['약품코드'].unique()
            all_drug_codes.update([code for code in codes if code != 'nan'])

    print(f"총 {len(all_drug_codes)}개의 약품 발견")

    # 월 리스트 (시간순 정렬)
    months = sorted(monthly_data.keys())

    # 결과 데이터프레임 구축
    result_rows = []

    for drug_code in all_drug_codes:
        row_data = {
            '약품코드': drug_code,
            '약품명': None,
            '제약회사': None,
            '최종_재고수량': None  # None으로 초기화 (아직 채택 안 됨)
        }

        monthly_quantities = []

        # 최신순으로 순회하며 재고수량 찾기 위해 역순 리스트 생성
        months_reversed = list(reversed(months))

        for month in months:
            df = monthly_data[month]
            if '약품코드' not in df.columns:
                continue

            # 해당 약품코드 찾기 (float 형태의 .0 제거)
            df['약품코드'] = df['약품코드'].astype(str).str.strip()
            df['약품코드'] = df['약품코드'].str.replace(r'\.0$', '', regex=True)
            drug_row = df[df['약품코드'] == drug_code]

            if not drug_row.empty:
                drug_row = drug_row.iloc[0]

                # 기본 정보 업데이트 (처음 발견시)
                if row_data['약품명'] is None:
                    row_data['약품명'] = drug_row.get('약품명', '')
                    row_data['제약회사'] = drug_row.get('제약회사', '')

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

                # 재고수량 처리: 아직 채택되지 않았고, 현재 행에 유효한 재고가 있으면 채택
                if row_data['최종_재고수량'] is None and '재고수량' in drug_row:
                    stock = str(drug_row['재고수량']).replace(',', '').replace('-', '0')
                    stock = pd.to_numeric(stock, errors='coerce')
                    # 유효한 재고 (not NaN and > 0)만 채택
                    if pd.notna(stock) and stock > 0:
                        row_data['최종_재고수량'] = stock
            else:
                # 해당 월에 데이터가 없는 경우
                row_data[f'{month}_조제수량'] = 0
                monthly_quantities.append(0)

        # 최신순으로 재고수량 검색 (이미 채택 안 되었으면)
        if row_data['최종_재고수량'] is None:
            for month in months_reversed:
                df = monthly_data[month]
                if '약품코드' not in df.columns:
                    continue

                df['약품코드'] = df['약품코드'].astype(str).str.strip()
                df['약품코드'] = df['약품코드'].str.replace(r'\.0$', '', regex=True)
                drug_row = df[df['약품코드'] == drug_code]

                if not drug_row.empty and '재고수량' in drug_row.columns:
                    drug_row = drug_row.iloc[0]
                    stock = str(drug_row['재고수량']).replace(',', '').replace('-', '0')
                    stock = pd.to_numeric(stock, errors='coerce')
                    if pd.notna(stock) and stock > 0:
                        row_data['최종_재고수량'] = stock
                        break  # 가장 최신의 유효한 재고를 찾았으므로 중단

        # 여전히 None이면 0으로 설정
        if row_data['최종_재고수량'] is None:
            row_data['최종_재고수량'] = 0

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
    """통계 계산: 월평균, 3개월 이동평균, 런웨이"""
    print("\n통계 계산 중...")

    # 월평균 조제수량
    df['월평균_조제수량'] = df['월별_조제수량_리스트'].apply(
        lambda x: sum(x) / len(x) if len(x) > 0 else 0
    )

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

    # 런웨이 계산
    def calculate_runway(row):
        if row['월평균_조제수량'] == 0:
            return '재고만 있음'

        runway_months = row['최종_재고수량'] / row['월평균_조제수량']

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

            # 재고수량도 숫자로 변환
            if '재고수량' in df.columns:
                df['재고수량'] = df['재고수량'].astype(str).str.replace(',', '').replace('-', '0')
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

def main():
    """메인 함수 - 직접 실행시에만 동작"""
    try:
        # Excel 파일 선택
        file_path = select_file_from_directory()

        # 파일이 선택되지 않았으면 종료
        if not file_path:
            sys.exit()

        # 파일 읽기
        df_all = read_csv_file(file_path)

        # 사용자에게 데이터 기간 물어보기
        while True:
            try:
                m = int(input("\n총 몇개월 간의 데이터입니까? "))
                if m > 0:
                    break
                else:
                    print("양수를 입력해주세요.")
            except ValueError:
                print("올바른 숫자를 입력해주세요.")

        # 데이터 처리
        df, m = process_inventory_data(df_all, m)

        if df is not None:
            # 결과를 CSV로 저장할지 물어보기
            save = input("\n결과를 CSV 파일로 저장하시겠습니까? (y/n): ")
            if save.lower() == 'y':
                output_file = 'processed_inventory.csv'
                df.to_csv(output_file, index=False, encoding='utf-8-sig')
                print(f"파일이 {output_file}에 저장되었습니다.")

    except FileNotFoundError:
        print(f"파일을 찾을 수 없습니다: {file_path}")
    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    main()