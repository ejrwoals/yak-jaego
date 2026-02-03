"""
공통 유틸리티 함수 모듈

여러 모듈에서 재사용되는 공통 함수들을 모아놓은 모듈입니다.
"""

import pandas as pd
import os
from datetime import datetime


def normalize_drug_code(code):
    """
    약품코드를 문자열로 정규화하고 .0 형태 제거

    Args:
        code: 약품코드 (int, float, str 등)

    Returns:
        str: 정규화된 약품코드

    Examples:
        >>> normalize_drug_code(12345.0)
        '12345'
        >>> normalize_drug_code('12345')
        '12345'
        >>> normalize_drug_code(12345)
        '12345'
        >>> normalize_drug_code('ABC123')
        'ABC123'
    """
    code_str = str(code)

    # .0으로 끝나는 숫자 형태인 경우 .0 제거
    if code_str.endswith('.0'):
        # 숫자로만 구성되어 있는지 확인 (.을 제외하고)
        if code_str.replace('.', '').replace('-', '').isdigit():
            return code_str[:-2]

    return code_str


def normalize_drug_codes_in_df(df, code_column='약품코드'):
    """
    DataFrame의 약품코드 컬럼을 정규화

    Args:
        df (pd.DataFrame): 대상 DataFrame
        code_column (str): 약품코드 컬럼명

    Returns:
        pd.DataFrame: 약품코드가 정규화된 DataFrame (복사본)
    """
    df = df.copy()
    if code_column in df.columns:
        df[code_column] = df[code_column].apply(normalize_drug_code)
    return df


def validate_columns(df, required_columns, df_name='DataFrame'):
    """
    DataFrame에 필수 컬럼이 있는지 검증

    Args:
        df (pd.DataFrame): 검증할 DataFrame
        required_columns (list): 필수 컬럼 리스트
        df_name (str): DataFrame 이름 (에러 메시지용)

    Returns:
        tuple: (bool, list) - (검증 성공 여부, 누락된 컬럼 리스트)
    """
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        print(f"❌ {df_name}에 필수 컬럼이 누락되었습니다: {missing_columns}")
        print(f"   현재 컬럼: {list(df.columns)}")
        return False, missing_columns

    return True, []


def safe_float_conversion(value, default=0.0):
    """
    안전하게 float으로 변환

    Args:
        value: 변환할 값
        default (float): 변환 실패 시 기본값

    Returns:
        float: 변환된 값
    """
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def generate_month_list_from_metadata():
    """
    drug_timeseries_db의 메타데이터에서 월 리스트 생성

    DB에 저장된 month_list가 있으면 그대로 반환하고,
    없으면 start_month와 total_months로 생성합니다.

    Returns:
        list: ['2023-10', '2023-11', ...] 형태의 월 리스트
              메타데이터가 없으면 None 반환

    Examples:
        >>> months = generate_month_list_from_metadata()
        >>> if months:
        >>>     print(f"분석 기간: {months[0]} ~ {months[-1]}")
    """
    import drug_timeseries_db
    from dateutil.relativedelta import relativedelta

    data_period = drug_timeseries_db.get_metadata()
    if not data_period:
        return None

    # DB에 month_list가 저장되어 있으면 그대로 사용
    if 'month_list' in data_period and data_period['month_list']:
        return data_period['month_list']

    # 없으면 start_month와 total_months로 생성
    start_month = data_period.get('start_month')
    total_months = data_period.get('total_months')

    if not start_month or not total_months:
        return None

    start_date = datetime.strptime(start_month, '%Y-%m')
    months = []
    for i in range(total_months):
        month_date = start_date + relativedelta(months=i)
        months.append(month_date.strftime('%Y-%m'))

    return months


def read_today_file(base_name_or_path='today'):
    """
    today.csv 또는 today.xls/today.xlsx 파일을 자동으로 찾아서 읽기
    절대 경로가 주어지면 해당 파일을 직접 읽기

    Args:
        base_name_or_path (str): 기본 파일명 (확장자 제외) 또는 절대 경로

    Returns:
        tuple: (pd.DataFrame, str) - (데이터프레임, 사용된 파일 경로)
               파일이 없으면 (None, None) 반환

    Examples:
        >>> df, filepath = read_today_file('today')
        >>> if df is not None:
        >>>     print(f"파일 로드 성공: {filepath}")
        >>>
        >>> # 절대 경로 사용
        >>> df, filepath = read_today_file('/path/to/file.xlsx')
    """

    # 절대 경로가 주어진 경우 직접 처리
    if os.path.isabs(base_name_or_path) and os.path.exists(base_name_or_path):
        filepath = base_name_or_path
        ext = os.path.splitext(filepath)[1].lower()

        print(f"📂 {filepath} 파일 발견 (절대 경로)")

        try:
            if ext == '.csv':
                # CSV 파일 읽기 (다중 인코딩 시도)
                # dtype={'약품코드': str}로 약품코드의 선행 0 보존
                df = None
                for encoding in ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr']:
                    try:
                        df = pd.read_csv(filepath, encoding=encoding, dtype={'약품코드': str})
                        print(f"   ✅ 파일 읽기 성공 ({encoding} 인코딩)")
                        return df, filepath
                    except UnicodeDecodeError:
                        continue
                    except Exception as e:
                        print(f"   ⚠️  CSV 읽기 오류: {e}")
                        return None, None

                if df is None:
                    print(f"   ❌ CSV 파일을 읽을 수 없습니다 (인코딩 문제)")
                    return None, None

            elif ext in ['.xls', '.xlsx']:
                # Excel 파일 읽기
                # dtype={'약품코드': str}로 약품코드의 선행 0 보존
                try:
                    engine = 'calamine' if ext == '.xls' else 'openpyxl'
                    df = pd.read_excel(filepath, engine=engine, dtype={'약품코드': str})
                    print(f"   ✅ Excel 파일 읽기 성공 ({engine} 엔진)")
                    return df, filepath
                except Exception as e:
                    # 실패 시 다른 엔진 시도
                    fallback_engine = 'openpyxl' if ext == '.xls' else 'calamine'
                    try:
                        df = pd.read_excel(filepath, engine=fallback_engine, dtype={'약품코드': str})
                        print(f"   ✅ Excel 파일 읽기 성공 ({fallback_engine} 엔진)")
                        return df, filepath
                    except Exception as e2:
                        print(f"   ❌ Excel 파일 읽기 실패: {e}")
                        return None, None
            else:
                print(f"   ❌ 지원하지 않는 파일 형식입니다: {ext}")
                return None, None

        except Exception as e:
            print(f"   ❌ 파일 읽기 중 오류 발생: {e}")
            return None, None

    # 기본 로직: base_name으로 루트 디렉토리에서 찾기
    # 지원하는 파일 확장자 우선순위 (CSV 우선)
    extensions = ['.csv', '.xls', '.xlsx']

    for ext in extensions:
        filepath = f"{base_name_or_path}{ext}"

        if not os.path.exists(filepath):
            continue

        print(f"📂 {filepath} 파일 발견")

        try:
            if ext == '.csv':
                # CSV 파일 읽기 (다중 인코딩 시도)
                # dtype={'약품코드': str}로 약품코드의 선행 0 보존
                df = None
                for encoding in ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr']:
                    try:
                        df = pd.read_csv(filepath, encoding=encoding, dtype={'약품코드': str})
                        print(f"   ✅ 파일 읽기 성공 ({encoding} 인코딩)")
                        return df, filepath
                    except UnicodeDecodeError:
                        continue
                    except Exception as e:
                        print(f"   ⚠️  CSV 읽기 오류: {e}")
                        return None, None

                if df is None:
                    print(f"   ❌ CSV 파일을 읽을 수 없습니다 (인코딩 문제)")
                    return None, None

            elif ext in ['.xls', '.xlsx']:
                # Excel 파일 읽기
                # calamine 엔진: 윈도우에서 생성된 오래된 .xls 파일도 지원
                # openpyxl 엔진: .xlsx 파일에 최적화
                # dtype={'약품코드': str}로 약품코드의 선행 0 보존
                try:
                    # .xls는 calamine, .xlsx는 openpyxl 우선 사용
                    engine = 'calamine' if ext == '.xls' else 'openpyxl'
                    df = pd.read_excel(filepath, engine=engine, dtype={'약품코드': str})
                    print(f"   ✅ Excel 파일 읽기 성공 ({engine} 엔진)")
                    return df, filepath
                except Exception as e:
                    # 실패 시 다른 엔진 시도
                    fallback_engine = 'openpyxl' if ext == '.xls' else 'calamine'
                    try:
                        df = pd.read_excel(filepath, engine=fallback_engine, dtype={'약품코드': str})
                        print(f"   ✅ Excel 파일 읽기 성공 ({fallback_engine} 엔진)")
                        return df, filepath
                    except Exception as e2:
                        print(f"   ❌ Excel 파일 읽기 실패: {e}")
                        return None, None

        except Exception as e:
            print(f"   ❌ 파일 읽기 중 오류 발생: {e}")
            return None, None

    # 어떤 파일도 찾지 못함
    print(f"⚠️  {base_name_or_path}.csv, {base_name_or_path}.xls, {base_name_or_path}.xlsx 파일을 찾을 수 없습니다.")
    return None, None


if __name__ == '__main__':
    # 테스트 코드
    print("=== utils.py 테스트 ===\n")

    # 1. normalize_drug_code 테스트
    print("1. normalize_drug_code 테스트")
    test_cases = [
        (12345.0, '12345'),
        ('12345', '12345'),
        (12345, '12345'),
        ('ABC123', 'ABC123'),
        ('A123.0', 'A123.0'),  # 문자 포함이므로 .0 유지
        (123.45, '123.45'),    # 소수점 값이므로 .0이 아님
    ]

    for input_val, expected in test_cases:
        result = normalize_drug_code(input_val)
        status = "✅" if result == expected else "❌"
        print(f"   {status} {input_val} -> {result} (expected: {expected})")

    # 2. normalize_drug_codes_in_df 테스트
    print("\n2. normalize_drug_codes_in_df 테스트")
    test_df = pd.DataFrame({
        '약품코드': [12345.0, 67890.0, 'ABC123'],
        '약품명': ['약품A', '약품B', '약품C']
    })
    print("변환 전:")
    print(test_df)

    normalized_df = normalize_drug_codes_in_df(test_df)
    print("\n변환 후:")
    print(normalized_df)

    # 3. validate_columns 테스트
    print("\n3. validate_columns 테스트")
    test_df = pd.DataFrame({'A': [1, 2], 'B': [3, 4]})

    is_valid, missing = validate_columns(test_df, ['A', 'B'], 'TestDF')
    print(f"   필수 컬럼 ['A', 'B'] 검증: {'✅ 통과' if is_valid else '❌ 실패'}")

    is_valid, missing = validate_columns(test_df, ['A', 'C'], 'TestDF')
    print(f"   필수 컬럼 ['A', 'C'] 검증: {'✅ 통과' if is_valid else '❌ 실패'} (누락: {missing})")

    # 4. safe_float_conversion 테스트
    print("\n4. safe_float_conversion 테스트")
    test_values = [
        (100, 100.0),
        ('50.5', 50.5),
        ('invalid', 0.0),
        (None, 0.0),
        (float('nan'), 0.0),
    ]

    for input_val, expected in test_values:
        result = safe_float_conversion(input_val)
        status = "✅" if result == expected else "❌"
        print(f"   {status} {repr(input_val)} -> {result} (expected: {expected})")

    print("\n✅ 테스트 완료!")
