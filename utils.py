"""
공통 유틸리티 함수 모듈

여러 모듈에서 재사용되는 공통 함수들을 모아놓은 모듈입니다.
"""

import pandas as pd


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
