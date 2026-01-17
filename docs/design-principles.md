# Jaego 디자인 원칙

이 문서는 Jaego 프로젝트의 UI/UX 디자인 원칙을 정의합니다. 모든 프론트엔드 작업은 이 원칙을 따라야 합니다.

---

## 목차

1. [디자인 철학](#디자인-철학)
2. [색상 시스템](#색상-시스템)
3. [타이포그래피](#타이포그래피)
4. [공간과 레이아웃](#공간과-레이아웃)
5. [깊이와 그림자](#깊이와-그림자)
6. [모서리 곡률](#모서리-곡률)
7. [아이콘](#아이콘)
8. [인터랙션과 애니메이션](#인터랙션과-애니메이션)
9. [컴포넌트별 가이드](#컴포넌트별-가이드)
10. [금지 사항](#금지-사항)

---

## 디자인 철학

### 핵심 원칙

1. **명확성 (Clarity)**
   - 정보의 계층 구조를 명확히 표현
   - 사용자가 현재 상태를 즉시 파악 가능
   - 불필요한 장식 요소 배제

2. **일관성 (Consistency)**
   - 동일한 기능은 동일한 시각적 표현
   - 색상, 간격, 타이포그래피의 체계적 사용
   - 예측 가능한 인터랙션 패턴

3. **전문성 (Professionalism)**
   - 의료/약국 도메인에 적합한 신뢰감 있는 디자인
   - 과도한 장식이나 이모지 사용 자제
   - 깔끔하고 정돈된 시각적 표현

4. **효율성 (Efficiency)**
   - 최소한의 클릭으로 작업 완료
   - 자주 사용하는 기능에 빠른 접근
   - 불필요한 확인 단계 최소화

---

## 색상 시스템

### 브랜드 색상

차분하고 모던한 슬레이트 블루 기반 팔레트를 사용합니다.

```css
:root {
    /* 브랜드 Primary - 차분하고 모던한 슬레이트 블루 */
    --brand-primary: #475569;
    --brand-primary-dark: #334155;
    --brand-primary-light: #64748b;
    --brand-primary-subtle: #f1f5f9;

    /* 브랜드 Accent - 행동 유도용 주황색 */
    --brand-accent: #f97316;
    --brand-accent-dark: #ea580c;
    --brand-accent-light: #fb923c;
}
```

### 시맨틱 색상

의미를 전달하는 기능적 색상입니다.

```css
:root {
    /* 성공/긍정 */
    --color-success: #10b981;
    --color-success-dark: #059669;
    --color-success-light: #d1fae5;

    /* 위험/부정 */
    --color-danger: #ef4444;
    --color-danger-dark: #dc2626;
    --color-danger-light: #fee2e2;

    /* 경고/주의 */
    --color-warning: #f59e0b;
    --color-warning-dark: #d97706;
    --color-warning-light: #fef3c7;

    /* 정보/안내 */
    --color-info: #3b82f6;
    --color-info-dark: #2563eb;
    --color-info-light: #dbeafe;
}
```

### 재고 상태 색상

약국 재고 관리에 특화된 상태 색상입니다.

```css
:root {
    /* 재고 부족 - 빨강 계열 */
    --status-shortage: #ef4444;
    --status-shortage-bg: #fef2f2;

    /* 재고 적정 - 초록 계열 */
    --status-sufficient: #22c55e;
    --status-sufficient-bg: #f0fdf4;

    /* 재고 과잉 - 파랑 계열 */
    --status-excess: #3b82f6;
    --status-excess-bg: #eff6ff;
}
```

### 중립 색상

텍스트, 배경, 테두리에 사용하는 중립 색상입니다.

```css
:root {
    /* 텍스트 계층 */
    --text-primary: #18181b;      /* 제목, 중요 텍스트 */
    --text-secondary: #52525b;    /* 본문 */
    --text-muted: #a1a1aa;        /* 보조 설명 */
    --text-disabled: #d4d4d8;     /* 비활성 */

    /* 배경 계층 */
    --bg-page: #fafafa;           /* 페이지 배경 */
    --bg-surface: #ffffff;        /* 카드, 모달 배경 */
    --bg-subtle: #f4f4f5;         /* 구분 영역 */
    --bg-hover: #e4e4e7;          /* 호버 상태 */

    /* 테두리 */
    --border-default: #e4e4e7;
    --border-strong: #d4d4d8;
    --border-subtle: #f4f4f5;
}
```

### 색상 사용 규칙

| 용도 | 색상 | 예시 |
|------|------|------|
| 주요 액션 버튼 | `--brand-primary` | 저장, 생성, 확인 |
| 위험한 액션 | `--color-danger` | 삭제, 초기화 |
| 보조 액션 | `--text-secondary` | 취소, 닫기 |
| 링크 | `--brand-primary` | 텍스트 링크 |
| 성공 피드백 | `--color-success` | 저장 완료 토스트 |
| 오류 피드백 | `--color-danger` | 에러 토스트, 유효성 검사 |

---

## 타이포그래피

### 폰트 스택

```css
:root {
    --font-sans: 'Pretendard', 'Noto Sans KR', -apple-system, BlinkMacSystemFont,
                 'Segoe UI', Roboto, sans-serif;
    --font-mono: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
}
```

### 타입 스케일

1.25 비율의 타입 스케일을 사용합니다.

```css
:root {
    --text-xs: 0.75rem;     /* 12px - 캡션, 배지 */
    --text-sm: 0.875rem;    /* 14px - 보조 텍스트 */
    --text-base: 1rem;      /* 16px - 본문 */
    --text-lg: 1.125rem;    /* 18px - 강조 본문 */
    --text-xl: 1.25rem;     /* 20px - 소제목 */
    --text-2xl: 1.5rem;     /* 24px - 섹션 제목 */
    --text-3xl: 1.875rem;   /* 30px - 페이지 제목 */
    --text-4xl: 2.25rem;    /* 36px - 대형 제목 */
}
```

### 폰트 굵기

```css
:root {
    --font-normal: 400;     /* 본문 */
    --font-medium: 500;     /* 강조 본문 */
    --font-semibold: 600;   /* 버튼, 라벨 */
    --font-bold: 700;       /* 제목 */
}
```

### 행간 (Line Height)

```css
:root {
    --leading-none: 1;        /* 한 줄 텍스트 */
    --leading-tight: 1.25;    /* 제목 */
    --leading-normal: 1.5;    /* 본문 */
    --leading-relaxed: 1.625; /* 긴 문단 */
    --leading-loose: 2;       /* 여유로운 본문 */
}
```

### 자간 (Letter Spacing)

```css
:root {
    --tracking-tight: -0.025em;   /* 큰 제목 */
    --tracking-normal: 0;          /* 본문 */
    --tracking-wide: 0.025em;      /* 소문자 라벨 */
    --tracking-wider: 0.05em;      /* 대문자 라벨 */
}
```

### 타이포그래피 조합 예시

```css
/* 페이지 제목 */
.page-title {
    font-size: var(--text-3xl);
    font-weight: var(--font-bold);
    line-height: var(--leading-tight);
    letter-spacing: var(--tracking-tight);
    color: var(--text-primary);
}

/* 섹션 제목 */
.section-title {
    font-size: var(--text-xl);
    font-weight: var(--font-semibold);
    line-height: var(--leading-tight);
    color: var(--text-primary);
}

/* 본문 */
.body-text {
    font-size: var(--text-base);
    font-weight: var(--font-normal);
    line-height: var(--leading-normal);
    color: var(--text-secondary);
}

/* 라벨 */
.label {
    font-size: var(--text-xs);
    font-weight: var(--font-medium);
    line-height: var(--leading-none);
    letter-spacing: var(--tracking-wide);
    text-transform: uppercase;
    color: var(--text-muted);
}

/* 캡션 */
.caption {
    font-size: var(--text-sm);
    font-weight: var(--font-normal);
    line-height: var(--leading-normal);
    color: var(--text-muted);
}
```

---

## 공간과 레이아웃

### 간격 스케일

4px 기반의 간격 시스템을 사용합니다.

```css
:root {
    --space-0: 0;
    --space-1: 0.25rem;   /* 4px */
    --space-2: 0.5rem;    /* 8px */
    --space-3: 0.75rem;   /* 12px */
    --space-4: 1rem;      /* 16px */
    --space-5: 1.25rem;   /* 20px */
    --space-6: 1.5rem;    /* 24px */
    --space-8: 2rem;      /* 32px */
    --space-10: 2.5rem;   /* 40px */
    --space-12: 3rem;     /* 48px */
    --space-16: 4rem;     /* 64px */
}
```

### 간격 사용 가이드

| 용도 | 간격 | 값 |
|------|------|-----|
| 인라인 요소 간 | `--space-1` ~ `--space-2` | 4-8px |
| 관련 요소 그룹 내 | `--space-2` ~ `--space-3` | 8-12px |
| 폼 필드 간 | `--space-4` ~ `--space-5` | 16-20px |
| 섹션 내 콘텐츠 | `--space-4` ~ `--space-6` | 16-24px |
| 섹션 간 | `--space-8` ~ `--space-12` | 32-48px |
| 페이지 패딩 | `--space-4` ~ `--space-8` | 16-32px |

### 레이아웃 원칙

#### 1. 의도적 비대칭

완벽한 대칭보다 시각적 계층을 우선합니다.

```css
/* 권장: 주요 콘텐츠를 더 크게 */
.layout-asymmetric {
    display: grid;
    grid-template-columns: 1.2fr 0.8fr;
    gap: var(--space-6);
}

/* 피해야 함: 모든 요소 동일 크기 */
.layout-symmetric {
    display: grid;
    grid-template-columns: 1fr 1fr;
}
```

#### 2. 콘텐츠 기반 너비

고정 너비보다 콘텐츠에 맞는 유연한 너비를 사용합니다.

```css
/* 권장 */
.card {
    max-width: 480px;
    width: 100%;
}

/* 피해야 함 */
.card {
    width: 480px;
}
```

#### 3. 시각적 그룹화

관련 요소는 가깝게, 무관한 요소는 멀리 배치합니다.

```css
/* 폼 그룹 내부: 좁은 간격 */
.form-group {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
}

/* 폼 그룹 간: 넓은 간격 */
.form {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
}
```

---

## 깊이와 그림자

### 그림자 스케일

```css
:root {
    /* 레벨 0: 그림자 없음 - 평면 요소 */
    --shadow-none: none;

    /* 레벨 1: 미세한 구분 - 카드, 입력 필드 */
    --shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.05);

    /* 레벨 2: 떠있는 느낌 - 호버 상태, 드롭다운 */
    --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.1),
                 0 1px 2px rgba(0, 0, 0, 0.06);

    /* 레벨 3: 강조 - 활성 카드, 팝오버 */
    --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.1),
                 0 2px 4px rgba(0, 0, 0, 0.06);

    /* 레벨 4: 부유 - 토스트, 드래그 중 요소 */
    --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.1),
                 0 4px 6px rgba(0, 0, 0, 0.05);

    /* 레벨 5: 최상위 - 모달 */
    --shadow-xl: 0 20px 25px rgba(0, 0, 0, 0.1),
                 0 10px 10px rgba(0, 0, 0, 0.04);
}
```

### 그림자 사용 가이드

| 컴포넌트 | 기본 상태 | 호버/활성 상태 |
|----------|----------|---------------|
| 카드 | `--shadow-xs` | `--shadow-sm` |
| 버튼 | `--shadow-none` | `--shadow-sm` |
| 입력 필드 | `--shadow-xs` | `--shadow-sm` |
| 드롭다운 메뉴 | `--shadow-md` | - |
| 토스트 | `--shadow-lg` | - |
| 모달 | `--shadow-xl` | - |

### 그림자 원칙

1. **계층 표현**: 높이 있는 요소일수록 큰 그림자
2. **상태 피드백**: 호버 시 그림자 증가로 인터랙션 표현
3. **절제**: 모든 요소에 그림자를 넣지 않음

---

## 모서리 곡률

### 곡률 스케일

```css
:root {
    --radius-none: 0;
    --radius-sm: 4px;      /* 작은 요소: 배지, 태그 */
    --radius-md: 6px;      /* 중간 요소: 버튼, 입력 필드 */
    --radius-lg: 8px;      /* 큰 요소: 카드 */
    --radius-xl: 12px;     /* 더 큰 요소: 모달 */
    --radius-2xl: 16px;    /* 컨테이너 */
    --radius-full: 9999px; /* 완전 둥근: 원형 버튼, 배지 */
}
```

### 곡률 사용 가이드

| 컴포넌트 | 곡률 |
|----------|------|
| 배지, 태그 | `--radius-sm` |
| 버튼 | `--radius-md` |
| 입력 필드 | `--radius-md` |
| 드롭다운 | `--radius-md` |
| 카드 | `--radius-lg` |
| 모달 | `--radius-xl` |
| 페이지 컨테이너 | `--radius-2xl` |
| 아바타, 원형 버튼 | `--radius-full` |

### 곡률 원칙

1. **크기 비례**: 작은 요소는 작은 곡률, 큰 요소는 큰 곡률
2. **일관성**: 같은 유형의 컴포넌트는 같은 곡률
3. **중첩 고려**: 내부 요소는 외부보다 작은 곡률 사용

```css
/* 예: 카드 내부의 버튼 */
.card {
    border-radius: var(--radius-lg);  /* 8px */
}

.card .btn {
    border-radius: var(--radius-md);  /* 6px */
}
```

---

## 아이콘

### 아이콘 시스템

**Lucide Icons**를 표준 아이콘 라이브러리로 사용합니다.

- 공식 사이트: https://lucide.dev
- 라이선스: ISC (MIT와 유사)
- 특징: 일관된 선 굵기, 심플한 디자인

### 아이콘 크기

```css
:root {
    --icon-xs: 14px;   /* 인라인 텍스트 */
    --icon-sm: 16px;   /* 버튼 내 아이콘 */
    --icon-md: 20px;   /* 일반 아이콘 */
    --icon-lg: 24px;   /* 강조 아이콘 */
    --icon-xl: 32px;   /* 빈 상태, 헤더 */
}
```

### SVG 아이콘 사용법

```html
<!-- 기본 사용 -->
<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <path d="..." />
</svg>

<!-- 크기 클래스 적용 -->
<svg class="icon icon-sm">...</svg>
<svg class="icon icon-lg">...</svg>
```

```css
.icon {
    width: var(--icon-md);
    height: var(--icon-md);
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
    flex-shrink: 0;
}

.icon-xs { width: var(--icon-xs); height: var(--icon-xs); }
.icon-sm { width: var(--icon-sm); height: var(--icon-sm); }
.icon-lg { width: var(--icon-lg); height: var(--icon-lg); }
.icon-xl { width: var(--icon-xl); height: var(--icon-xl); }
```

### 아이콘 색상

아이콘은 `currentColor`를 사용하여 텍스트 색상을 상속받습니다.

```css
/* 텍스트와 함께 사용 시 자동으로 색상 일치 */
.btn {
    color: var(--text-primary);
}

.btn .icon {
    stroke: currentColor;  /* 부모의 color 상속 */
}
```

### 자주 사용하는 아이콘 매핑

| 기능 | 아이콘 이름 | 용도 |
|------|------------|------|
| 추가/생성 | `plus` | 새 항목 추가 |
| 삭제 | `trash-2` | 항목 삭제 |
| 편집 | `pencil` | 수정 |
| 저장 | `save` | 저장 |
| 검색 | `search` | 검색 |
| 설정 | `settings` | 설정 |
| 사용자 | `user` | 사용자/환자 |
| 약품 | `pill` | 약품 |
| 차트 | `bar-chart-2` | 통계/보고서 |
| 달력 | `calendar` | 날짜 선택 |
| 체크 | `check` | 완료/선택됨 |
| 닫기 | `x` | 닫기/취소 |
| 경고 | `alert-triangle` | 경고 |
| 정보 | `info` | 안내 |
| 성공 | `check-circle` | 성공 |
| 오류 | `x-circle` | 오류 |

---

## 인터랙션과 애니메이션

### 트랜지션 속도

```css
:root {
    --duration-instant: 0ms;      /* 즉시 */
    --duration-fast: 100ms;       /* 색상 변화 */
    --duration-normal: 200ms;     /* 일반 트랜지션 */
    --duration-slow: 300ms;       /* 복잡한 트랜지션 */
    --duration-slower: 500ms;     /* 페이지 전환 */
}
```

### 이징 함수

```css
:root {
    --ease-linear: linear;
    --ease-in: cubic-bezier(0.4, 0, 1, 1);
    --ease-out: cubic-bezier(0, 0, 0.2, 1);
    --ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);

    /* 스프링 효과 */
    --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
}
```

### 기본 트랜지션

```css
/* 색상 변화 */
.color-transition {
    transition: color var(--duration-fast) var(--ease-out),
                background-color var(--duration-fast) var(--ease-out);
}

/* 크기/위치 변화 */
.transform-transition {
    transition: transform var(--duration-normal) var(--ease-out);
}

/* 복합 트랜지션 */
.all-transition {
    transition: all var(--duration-normal) var(--ease-out);
}
```

### 호버 인터랙션

```css
/* 버튼: 미세한 상승 */
.btn {
    transition: transform var(--duration-fast) var(--ease-out),
                box-shadow var(--duration-fast) var(--ease-out);
}

.btn:hover {
    transform: translateY(-1px);
    box-shadow: var(--shadow-sm);
}

.btn:active {
    transform: translateY(0);
    box-shadow: var(--shadow-xs);
}

/* 카드: 미세한 확대 */
.card-interactive {
    transition: transform var(--duration-normal) var(--ease-out),
                box-shadow var(--duration-normal) var(--ease-out);
}

.card-interactive:hover {
    transform: scale(1.01);
    box-shadow: var(--shadow-md);
}

/* 링크: 밑줄 애니메이션 */
.link {
    position: relative;
}

.link::after {
    content: '';
    position: absolute;
    bottom: -2px;
    left: 0;
    width: 0;
    height: 2px;
    background: currentColor;
    transition: width var(--duration-normal) var(--ease-out);
}

.link:hover::after {
    width: 100%;
}
```

### 표준 애니메이션

```css
/* 페이드 인 */
@keyframes fadeIn {
    from {
        opacity: 0;
    }
    to {
        opacity: 1;
    }
}

/* 슬라이드 업 */
@keyframes slideUp {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* 슬라이드 다운 */
@keyframes slideDown {
    from {
        opacity: 0;
        transform: translateY(-10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* 스케일 인 (모달용) */
@keyframes scaleIn {
    from {
        opacity: 0;
        transform: scale(0.95);
    }
    to {
        opacity: 1;
        transform: scale(1);
    }
}

/* 흔들림 (에러 피드백) */
@keyframes shake {
    0%, 100% { transform: translateX(0); }
    20%, 60% { transform: translateX(-4px); }
    40%, 80% { transform: translateX(4px); }
}

/* 스핀 (로딩) */
@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
```

### 애니메이션 원칙

1. **목적성**: 모든 애니메이션은 기능적 목적이 있어야 함
2. **미묘함**: 과도한 애니메이션은 피로감 유발
3. **일관성**: 같은 유형의 인터랙션은 같은 애니메이션
4. **성능**: `transform`과 `opacity`만 애니메이션 (GPU 가속)

---

## 컴포넌트별 가이드

### 버튼

```css
/* 기본 버튼 */
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);

    padding: var(--space-2) var(--space-4);

    font-size: var(--text-sm);
    font-weight: var(--font-semibold);
    line-height: var(--leading-none);

    border: 1px solid transparent;
    border-radius: var(--radius-md);

    cursor: pointer;
    transition: all var(--duration-fast) var(--ease-out);
}

/* Primary 버튼 */
.btn-primary {
    background: var(--brand-primary);
    color: white;
}

.btn-primary:hover {
    background: var(--brand-primary-dark);
}

/* Secondary 버튼 */
.btn-secondary {
    background: transparent;
    color: var(--text-secondary);
    border-color: var(--border-default);
}

.btn-secondary:hover {
    background: var(--bg-subtle);
    border-color: var(--border-strong);
}

/* Danger 버튼 */
.btn-danger {
    background: var(--color-danger);
    color: white;
}

.btn-danger:hover {
    background: var(--color-danger-dark);
}

/* Ghost 버튼 */
.btn-ghost {
    background: transparent;
    color: var(--text-secondary);
}

.btn-ghost:hover {
    background: var(--bg-subtle);
}
```

### 입력 필드

```css
.input {
    width: 100%;
    padding: var(--space-3) var(--space-4);

    font-size: var(--text-base);
    line-height: var(--leading-normal);
    color: var(--text-primary);

    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);

    transition: border-color var(--duration-fast) var(--ease-out),
                box-shadow var(--duration-fast) var(--ease-out);
}

.input:hover {
    border-color: var(--border-strong);
}

.input:focus {
    outline: none;
    border-color: var(--brand-primary);
    box-shadow: 0 0 0 3px var(--brand-primary-subtle);
}

.input::placeholder {
    color: var(--text-muted);
}

/* 에러 상태 */
.input-error {
    border-color: var(--color-danger);
}

.input-error:focus {
    box-shadow: 0 0 0 3px var(--color-danger-light);
}
```

### 카드

```css
.card {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-xs);

    padding: var(--space-6);
}

/* 인터랙티브 카드 */
.card-interactive {
    cursor: pointer;
    transition: transform var(--duration-normal) var(--ease-out),
                box-shadow var(--duration-normal) var(--ease-out);
}

.card-interactive:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-sm);
}
```

### 모달

```css
/* 배경 오버레이 */
.modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: var(--z-modal-backdrop);

    animation: fadeIn var(--duration-normal) var(--ease-out);
}

/* 모달 컨테이너 */
.modal {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);

    width: 90%;
    max-width: 480px;
    max-height: 90vh;

    background: var(--bg-surface);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-xl);

    z-index: var(--z-modal);

    animation: scaleIn var(--duration-slow) var(--ease-spring);
}

/* 모달 헤더 */
.modal-header {
    padding: var(--space-6);
    border-bottom: 1px solid var(--border-subtle);
}

/* 모달 본문 */
.modal-body {
    padding: var(--space-6);
    overflow-y: auto;
}

/* 모달 푸터 */
.modal-footer {
    padding: var(--space-4) var(--space-6);
    border-top: 1px solid var(--border-subtle);

    display: flex;
    justify-content: flex-end;
    gap: var(--space-3);
}
```

### 토스트

```css
.toast {
    position: fixed;
    top: var(--space-6);
    right: var(--space-6);

    display: flex;
    align-items: center;
    gap: var(--space-3);

    padding: var(--space-4) var(--space-5);

    background: var(--bg-surface);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-lg);

    z-index: var(--z-toast);

    animation: slideDown var(--duration-slow) var(--ease-spring);
}

/* 상태별 스타일 */
.toast-success {
    border-left: 4px solid var(--color-success);
}

.toast-error {
    border-left: 4px solid var(--color-danger);
}

.toast-warning {
    border-left: 4px solid var(--color-warning);
}

.toast-info {
    border-left: 4px solid var(--color-info);
}
```

---

## 금지 사항

### 절대 사용하지 말 것

1. **이모지를 아이콘으로 사용**
   ```html
   <!-- 금지 -->
   <span>📊</span> 보고서

   <!-- 권장 -->
   <svg class="icon">...</svg> 보고서
   ```

2. **브라우저 기본 confirm/alert**
   ```javascript
   // 금지
   if (confirm('삭제하시겠습니까?')) { ... }

   // 권장
   const confirmed = await showConfirmModal({...});
   ```

3. **브라우저 기본 select**
   ```html
   <!-- 금지 -->
   <select>...</select>

   <!-- 권장 -->
   <div class="custom-dropdown">...</div>
   ```

4. **인라인 스타일**
   ```html
   <!-- 금지 -->
   <div style="color: red; margin: 10px;">

   <!-- 권장 -->
   <div class="error-text">
   ```

5. **하드코딩된 색상값**
   ```css
   /* 금지 */
   color: #555;

   /* 권장 */
   color: var(--text-secondary);
   ```

6. **px 단위 폰트 크기**
   ```css
   /* 금지 */
   font-size: 14px;

   /* 권장 */
   font-size: var(--text-sm);
   ```

7. **!important 남용**
   ```css
   /* 금지 */
   .btn { background: red !important; }

   /* 권장: 명시도(specificity)로 해결 */
   .modal .btn-danger { background: red; }
   ```

8. **과도한 그라데이션**
   ```css
   /* 금지: 모든 버튼에 그라데이션 */
   .btn { background: linear-gradient(...); }

   /* 권장: 단색 또는 미묘한 그라데이션 */
   .btn { background: var(--brand-primary); }
   ```

### 주의해서 사용할 것

1. **애니메이션**: 기능적 목적이 있을 때만
2. **그림자**: 계층 표현이 필요할 때만
3. **색상**: 의미 전달이 필요할 때만
4. **둥근 모서리**: 크기에 비례하여

---

## 체크리스트

새로운 UI를 만들 때 확인할 사항:

- [ ] CSS 변수를 사용했는가?
- [ ] 아이콘은 SVG를 사용했는가?
- [ ] 색상이 시맨틱한 의미와 일치하는가?
- [ ] 간격이 스케일 시스템을 따르는가?
- [ ] 그림자가 적절한 깊이를 표현하는가?
- [ ] 곡률이 요소 크기에 비례하는가?
- [ ] 트랜지션이 일관되게 적용되었는가?
- [ ] 호버/포커스 상태가 명확한가?
- [ ] 반응형 레이아웃을 고려했는가?
- [ ] 접근성을 고려했는가? (색상 대비, 포커스 표시)

---

## 참고 자료

- [Lucide Icons](https://lucide.dev) - 아이콘 라이브러리
- [Tailwind CSS Colors](https://tailwindcss.com/docs/colors) - 색상 참고
- [Refactoring UI](https://www.refactoringui.com) - 디자인 원칙
