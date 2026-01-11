# Frontend Architecture Guide

이 문서는 Jaego 프로젝트의 프런트엔드 아키텍처 원칙과 가이드라인을 정리합니다.

## 목차

1. [디렉토리 구조](#디렉토리-구조)
2. [템플릿 상속 구조](#템플릿-상속-구조)
3. [컴포넌트 시스템](#컴포넌트-시스템)
4. [UI/UX 가이드라인](#uiux-가이드라인)
5. [JavaScript 작성 규칙](#javascript-작성-규칙)
6. [캐시 버스팅](#캐시-버스팅)
7. [새 페이지 추가하기](#새-페이지-추가하기)

---

## 디렉토리 구조

```
jaego/
├── static/
│   ├── css/
│   │   ├── base.css                    # CSS 변수, 공통 스타일
│   │   └── components/
│   │       ├── confirm-modal.css       # 확인 모달
│   │       ├── toast.css               # 토스트 알림
│   │       ├── dropdown.css            # 커스텀 드롭다운
│   │       └── shutdown-button.css     # 종료 버튼
│   └── js/
│       └── components/
│           ├── jaego-core.js           # 네임스페이스 및 유틸리티
│           ├── confirm-modal.js        # showConfirmModal()
│           ├── toast.js                # showToast()
│           ├── dropdown.js             # toggleDropdown()
│           └── shutdown.js             # exitApp(), shutdownServer()
│
├── templates/
│   ├── base.html                       # 기본 레이아웃 템플릿
│   ├── partials/
│   │   ├── _confirm_modal.html         # 확인 모달 HTML
│   │   ├── _toast_container.html       # 토스트 컨테이너
│   │   └── _shutdown_button.html       # 종료 버튼
│   └── [페이지 템플릿들]
│
└── web_app.py                          # Flask 앱 (VERSION 설정 포함)
```

---

## 템플릿 상속 구조

### base.html 블록 구조

모든 페이지는 `base.html`을 상속하며, 다음 블록들을 오버라이드할 수 있습니다:

```html
<!DOCTYPE html>
<html lang="ko">
<head>
    <title>{% block title %}Jaego{% endblock %}</title>

    <!-- 컴포넌트 CSS -->
    {% block component_styles %}{% endblock %}

    <!-- 페이지별 CSS -->
    {% block page_styles %}{% endblock %}
</head>
<body class="{% block body_class %}{% endblock %}">
    <!-- 종료 버튼 (기본 포함) -->
    {% block shutdown_button %}
        {% include 'partials/_shutdown_button.html' %}
    {% endblock %}

    <!-- 메인 콘텐츠 -->
    {% block content %}{% endblock %}

    <!-- 확인 모달 (기본 포함) -->
    {% block confirm_modal %}
        {% include 'partials/_confirm_modal.html' %}
    {% endblock %}

    <!-- 토스트 컨테이너 -->
    {% block toast_container %}{% endblock %}

    <!-- 기본 스크립트 -->
    {% block base_scripts %}
        <script src="{{ url_for('static', filename='js/components/jaego-core.js') }}"></script>
        <script src="{{ url_for('static', filename='js/components/confirm-modal.js') }}"></script>
    {% endblock %}

    <!-- 컴포넌트 스크립트 -->
    {% block component_scripts %}{% endblock %}

    <!-- 페이지별 스크립트 -->
    {% block page_scripts %}{% endblock %}
</body>
</html>
```

### 블록 사용 가이드

| 블록 | 용도 | 기본값 |
|------|------|--------|
| `title` | 페이지 제목 | "Jaego" |
| `component_styles` | 사용할 컴포넌트 CSS 링크 | 없음 |
| `page_styles` | 페이지 고유 CSS (인라인 또는 링크) | 없음 |
| `body_class` | body 태그에 추가할 클래스 | 없음 |
| `shutdown_button` | 종료 버튼 (비우면 제거) | partial 포함 |
| `content` | 메인 콘텐츠 | 없음 |
| `confirm_modal` | 확인 모달 (비우면 제거) | partial 포함 |
| `toast_container` | 토스트 컨테이너 | 없음 |
| `base_scripts` | 기본 JS (거의 오버라이드 안함) | jaego-core, confirm-modal |
| `component_scripts` | 추가 컴포넌트 JS | 없음 |
| `page_scripts` | 페이지 고유 JS | 없음 |

---

## 컴포넌트 시스템

### 1. 확인 모달 (Confirm Modal)

**사용 시점:** 사용자에게 확인이 필요한 모든 작업

```javascript
const confirmed = await showConfirmModal({
    icon: '🗑️',           // 모달 상단 아이콘
    title: '삭제 확인',     // 제목
    message: '정말 삭제하시겠습니까?',  // 본문 (HTML 지원)
    confirmText: '삭제',   // 확인 버튼 텍스트
    isDanger: true        // true면 빨간색 확인 버튼
});

if (!confirmed) return;
// 확인된 경우 작업 수행
```

**필요한 파일:**
- CSS: `confirm-modal.css`
- JS: `jaego-core.js`, `confirm-modal.js`
- HTML: `_confirm_modal.html` partial

### 2. 토스트 알림 (Toast)

**사용 시점:** 사용자에게 피드백을 줄 때 (성공, 실패, 정보)

```javascript
showToast('저장되었습니다.', 'success');  // 성공 (초록)
showToast('오류가 발생했습니다.', 'error');  // 오류 (빨강)
showToast('처리 중입니다.', 'info');      // 정보 (파랑)
showToast('주의가 필요합니다.', 'warning'); // 경고 (노랑)
```

**필요한 파일:**
- CSS: `toast.css`
- JS: `toast.js`
- HTML: `_toast_container.html` partial

### 3. 커스텀 드롭다운 (Dropdown)

**사용 시점:** 옵션 선택이 필요할 때 (`<select>` 대신 사용)

```html
<div class="custom-dropdown" id="myDropdown">
    <div class="custom-dropdown-selected" onclick="toggleDropdown('myDropdown')">
        선택된 옵션
    </div>
    <div class="custom-dropdown-options">
        <div class="custom-dropdown-option" data-value="1">옵션 1</div>
        <div class="custom-dropdown-option selected" data-value="2">옵션 2</div>
    </div>
</div>
<input type="hidden" name="field_name" id="fieldId" value="2">
```

**필요한 파일:**
- CSS: `dropdown.css`
- JS: `dropdown.js`

### 4. 종료 버튼 (Shutdown Button)

**기본 포함:** `base.html`에서 자동으로 포함됨

제거하려면:
```jinja2
{% block shutdown_button %}{% endblock %}
```

**필요한 파일:**
- CSS: `shutdown-button.css`
- JS: `shutdown.js`
- HTML: `_shutdown_button.html` partial

---

## UI/UX 가이드라인

### 금지 사항

| 금지 | 대체 |
|------|------|
| `alert()` | `showToast()` |
| `confirm()` | `showConfirmModal()` |
| `<select>` | 커스텀 드롭다운 |

### 모달 닫기 보호

사용자가 모달에서 내용을 작성 중일 때, 실수로 닫히는 것을 방지:

1. 모달에 내용이 있으면 외부 클릭/ESC 시 확인 대화상자 표시
2. 내용이 없으면 바로 닫기
3. 흔들림(shake) 애니메이션으로 시각적 피드백

```javascript
async function tryCloseModal() {
    if (hasModalContent()) {
        const confirmed = await showConfirmModal({
            icon: '⚠️',
            title: '작성 중인 내용이 있습니다',
            message: '정말 닫으시겠습니까?',
            confirmText: '닫기',
            isDanger: true
        });
        if (!confirmed) {
            shakeModal();
            return;
        }
    }
    closeModal();
}
```

---

## JavaScript 작성 규칙

### ES5 호환성

WebView 환경에서의 호환성을 위해 ES5 문법 사용:

```javascript
// ❌ 사용 금지
let x = 1;
const y = 2;
const fn = () => {};
`template ${string}`;

// ✅ 권장
var x = 1;
var y = 2;
var fn = function() {};
'string ' + variable;
```

### 전역 함수 호환성

기존 코드와의 호환성을 위해 전역 함수 유지:

```javascript
// 컴포넌트 내부
window.Jaego = window.Jaego || {};
Jaego.toast = {
    show: function(message, type) { /* ... */ }
};

// 전역 호환 래퍼
window.showToast = function(message, type) {
    return Jaego.toast.show(message, type);
};
```

### 이벤트 리스너

```javascript
// DOMContentLoaded에서 이벤트 등록
document.addEventListener('DOMContentLoaded', function() {
    // 옵션 클릭 이벤트
    document.querySelectorAll('.option').forEach(function(el) {
        el.addEventListener('click', function() {
            // 처리
        });
    });
});

// ESC 키 처리
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        // 모달 닫기 등
    }
});
```

---

## 캐시 버스팅

정적 파일 변경 시 브라우저 캐시 문제를 방지하기 위해 버전 파라미터 사용:

### web_app.py 설정

```python
app.config['VERSION'] = '1'  # 변경 시 증가
```

### 템플릿에서 사용

```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/components/toast.css') }}?v={{ config.get('VERSION', '1') }}">
<script src="{{ url_for('static', filename='js/components/toast.js') }}?v={{ config.get('VERSION', '1') }}"></script>
```

---

## 새 페이지 추가하기

### 1. 기본 템플릿 생성

```jinja2
{% extends "base.html" %}

{% block title %}페이지 제목 - Jaego{% endblock %}

{% block component_styles %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/components/confirm-modal.css') }}?v={{ config.get('VERSION', '1') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/components/toast.css') }}?v={{ config.get('VERSION', '1') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/components/shutdown-button.css') }}?v={{ config.get('VERSION', '1') }}">
{% endblock %}

{% block page_styles %}
<style>
    /* 페이지 고유 스타일 */
</style>
{% endblock %}

{% block toast_container %}
{% include 'partials/_toast_container.html' %}
{% endblock %}

{% block content %}
<div class="container">
    <!-- 페이지 콘텐츠 -->
</div>
{% endblock %}

{% block component_scripts %}
<script src="{{ url_for('static', filename='js/components/toast.js') }}?v={{ config.get('VERSION', '1') }}"></script>
<script src="{{ url_for('static', filename='js/components/shutdown.js') }}?v={{ config.get('VERSION', '1') }}"></script>
{% endblock %}

{% block page_scripts %}
<script>
    // 페이지 고유 스크립트
</script>
{% endblock %}
```

### 2. 체크리스트

- [ ] `{% extends "base.html" %}` 사용
- [ ] 필요한 컴포넌트 CSS/JS 포함
- [ ] `alert()` 대신 `showToast()` 사용
- [ ] `confirm()` 대신 `showConfirmModal()` 사용
- [ ] `<select>` 대신 커스텀 드롭다운 사용
- [ ] ES5 문법 사용 (var, function)
- [ ] 캐시 버스팅 파라미터 포함 (`?v={{ config.get('VERSION', '1') }}`)

---

## 참고

- 상세 UI/UX 가이드라인: [CLAUDE.md](../CLAUDE.md)
- 리팩토링 계획: `.claude/plans/` 폴더
