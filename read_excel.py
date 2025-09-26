import pandas as pd
import os
import sys

def select_file_from_directory(directory='data'):
    """디렉토리에서 파일을 선택하는 함수"""
    if not os.path.exists(directory):
        print(f"'{directory}' 디렉토리가 존재하지 않습니다.")
        return None

    files = [f for f in os.listdir(directory) if f.endswith(('.xls', '.xlsx', '.csv'))]

    if not files:
        print(f"'{directory}' 디렉토리에 Excel 또는 CSV 파일이 없습니다.")
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

# Excel 파일 선택
file_path = select_file_from_directory()

# 파일이 선택되지 않았으면 종료
if not file_path:
    sys.exit()

# 파일 읽기 (Excel 또는 CSV)
try:
    print(f"파일 읽는 중: {file_path}")

    # 파일 크기 확인
    file_size = os.path.getsize(file_path)
    print(f"파일 크기: {file_size:,} bytes")

    success = False

    # CSV 파일인지 확인
    if file_path.endswith('.csv'):
        try:
            print("CSV 파일로 읽기 시도...")
            df_all = pd.read_csv(file_path, encoding='utf-8')
            print("✅ CSV 파일 읽기 성공!")
            success = True
        except:
            try:
                df_all = pd.read_csv(file_path, encoding='cp949')
                print("✅ CSV 파일 읽기 성공! (cp949 인코딩)")
                success = True
            except Exception as e:
                print(f"❌ CSV 파일 읽기 실패: {str(e)[:100]}...")

    # Excel 파일 처리
    if not success and file_path.endswith(('.xls', '.xlsx')):
        # 1. 일반적인 엔진들 시도
        engines = ['openpyxl', 'xlrd', 'calamine', None]

        for engine in engines:
            try:
                if engine:
                    print(f"{engine} 엔진으로 시도 중...")
                    df_all = pd.read_excel(file_path, engine=engine)
                else:
                    print("기본 엔진으로 시도 중...")
                    df_all = pd.read_excel(file_path)
                print(f"✅ 파일 읽기 성공!")
                success = True
                break
            except Exception as e:
                print(f"❌ {engine or '기본'} 엔진 실패: {str(e)[:100]}...")

    # 2. 모든 엔진이 실패했을 때 추가 시도
    if not success:
        print("\n🔄 추가 방법으로 시도 중...")

        # CSV로 변환 시도 (LibreOffice나 다른 도구가 있다면)
        try:
            import subprocess
            print("LibreOffice를 이용한 CSV 변환 시도...")
            csv_path = file_path.replace('.xls', '_converted.csv')
            subprocess.run([
                'libreoffice', '--headless', '--convert-to', 'csv',
                '--outdir', os.path.dirname(file_path), file_path
            ], check=True, capture_output=True)

            if os.path.exists(csv_path):
                df_all = pd.read_csv(csv_path, encoding='utf-8')
                print("✅ LibreOffice CSV 변환으로 성공!")
                success = True
            else:
                print("❌ CSV 파일이 생성되지 않음")
        except Exception as e:
            print(f"❌ LibreOffice 변환 실패: {str(e)[:100]}...")

    if not success:
        print("\n💡 해결방법 제안:")
        print("1. Excel에서 해당 파일을 열어 .xlsx 형식으로 다시 저장해보세요")
        print("2. 또는 Excel에서 CSV 형식으로 저장한 후 data 폴더에 넣어보세요")
        print("3. 파일이 손상되었을 가능성이 있습니다")

        # 다른 파일 선택 옵션 제공
        retry = input("\n다른 파일을 선택하시겠습니까? (y/n): ")
        if retry.lower() == 'y':
            new_file = select_file_from_directory()
            if new_file and new_file != file_path:
                file_path = new_file
                # 재귀적으로 다시 시도하지 않고 간단히 처리
                try:
                    df_all = pd.read_excel(file_path)
                    success = True
                    print("✅ 다른 파일로 성공!")
                except Exception as e:
                    print(f"❌ 다른 파일도 실패: {e}")

        if not success:
            raise Exception("파일을 읽을 수 없습니다")
    
    # 전체 컬럼 확인
    print("전체 컬럼 목록:")
    print(df_all.columns.tolist())
    print("\n" + "="*50 + "\n")
    
    # 필요한 컬럼만 선택
    required_columns = ['약품명', '제약회사', '약품코드', '재고수량', '조제수량']
    
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
        
        # 월평균 조제수량 계산
        if '조제수량' in df.columns:
            # 조제수량을 숫자로 변환 (쉼표 제거 및 숫자 변환)
            df['조제수량'] = df['조제수량'].astype(str).str.replace(',', '').replace('-', '0')
            df['조제수량'] = pd.to_numeric(df['조제수량'], errors='coerce').fillna(0)
            
            df['월평균_조제수량'] = df['조제수량'] / m
            print(f"\n{m}개월 데이터를 기준으로 월평균 조제수량을 계산했습니다.")
            
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
        
        # 결과를 CSV로 저장할지 물어보기
        save = input("\n결과를 CSV 파일로 저장하시겠습니까? (y/n): ")
        if save.lower() == 'y':
            output_file = 'processed_inventory.csv'
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
            print(f"파일이 {output_file}에 저장되었습니다.")
    else:
        print("요청한 컬럼을 찾을 수 없습니다.")
        print("\n처음 5개 행 (전체 데이터):")
        print(df_all.head())
    
except FileNotFoundError:
    print(f"파일을 찾을 수 없습니다: {file_path}")
except Exception as e:
    print(f"오류 발생: {e}")