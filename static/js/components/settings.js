/**
 * Jaego Settings Component
 * User settings modal and management
 */

(function(Jaego) {
    'use strict';

    // 기본값 정의
    var DEFAULT_SETTINGS = {
        ma_months: 3,
        threshold_low: 1,
        threshold_high: 3,
        runway_threshold: 1.0
    };

    // 현재 설정값 (모달 열 때 로드됨)
    var currentSettings = Object.assign({}, DEFAULT_SETTINGS);

    // 모달 내 임시 설정값 (저장 전)
    var tempSettings = Object.assign({}, DEFAULT_SETTINGS);

    // 슬라이더 상수
    var RUNWAY_MAX_VALUE = 7;
    var HIGHLIGHT_MIN_VALUE = 0.5;
    var HIGHLIGHT_MAX_VALUE = 6;
    var HIGHLIGHT_STEP = 0.5;

    Jaego.settings = {
        /**
         * 설정 모달 열기
         */
        open: async function() {
            // 서버에서 현재 설정 로드
            await this.loadSettings();

            // 임시 설정을 현재 설정으로 초기화
            tempSettings = Object.assign({}, currentSettings);

            // UI에 설정값 반영
            this.updateUI();

            // 슬라이더 초기화
            this.initRunwaySlider();
            this.initHighlightSlider();

            // 드롭다운 이벤트 연결
            this.initDropdown();

            // 모달 표시
            var modal = document.getElementById('settingsModal');
            if (modal) {
                modal.classList.add('visible');
            }
        },

        /**
         * 설정 모달 닫기
         */
        close: function() {
            var modal = document.getElementById('settingsModal');
            if (modal) {
                modal.classList.remove('visible');
            }
        },

        /**
         * 서버에서 설정 로드
         */
        loadSettings: async function() {
            try {
                var response = await fetch('/api/settings');
                var data = await response.json();
                if (data.success) {
                    currentSettings = data.settings;
                }
            } catch (e) {
                console.error('설정 로드 실패:', e);
            }
        },

        /**
         * 설정 저장
         */
        save: async function() {
            // UI에서 값 수집
            this.collectFromUI();

            try {
                var response = await fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(tempSettings)
                });
                var data = await response.json();

                if (data.success) {
                    currentSettings = Object.assign({}, tempSettings);
                    this.close();
                    if (typeof showToast === 'function') {
                        showToast('설정이 저장되었습니다.', 'success');
                    }
                    return true;
                } else {
                    if (typeof showToast === 'function') {
                        showToast('설정 저장 실패: ' + data.message, 'error');
                    }
                    return false;
                }
            } catch (e) {
                console.error('설정 저장 실패:', e);
                if (typeof showToast === 'function') {
                    showToast('설정 저장 중 오류 발생', 'error');
                }
                return false;
            }
        },

        /**
         * 기본값으로 복원
         */
        resetToDefaults: async function() {
            var confirmed = true;
            if (typeof showConfirmModal === 'function') {
                confirmed = await showConfirmModal({
                    icon: 'warning',
                    title: '기본값 복원',
                    message: '모든 설정을 기본값으로 복원하시겠습니까?',
                    confirmText: '복원',
                    isDanger: false
                });
            }

            if (!confirmed) return;

            try {
                var response = await fetch('/api/settings/reset', { method: 'POST' });
                var data = await response.json();

                if (data.success) {
                    currentSettings = data.settings;
                    tempSettings = Object.assign({}, data.settings);
                    this.updateUI();
                    this.updateRunwaySliderUI();
                    this.updateHighlightSliderUI();
                    if (typeof showToast === 'function') {
                        showToast('기본값으로 복원되었습니다.', 'success');
                    }
                }
            } catch (e) {
                console.error('기본값 복원 실패:', e);
                if (typeof showToast === 'function') {
                    showToast('복원 중 오류 발생', 'error');
                }
            }
        },

        /**
         * UI 업데이트 (현재 설정값을 UI에 반영)
         */
        updateUI: function() {
            // 드롭다운 업데이트
            var dropdown = document.getElementById('settingsMaMonthsDropdown');
            if (dropdown) {
                var options = dropdown.querySelectorAll('.custom-dropdown-option');
                var selected = dropdown.querySelector('.custom-dropdown-selected');
                options.forEach(function(opt) {
                    opt.classList.remove('selected');
                    if (parseInt(opt.dataset.value) === tempSettings.ma_months) {
                        opt.classList.add('selected');
                        if (selected) {
                            selected.textContent = opt.textContent;
                        }
                    }
                });
            }
            document.getElementById('settings_ma_months').value = tempSettings.ma_months;

            // 런웨이 슬라이더 업데이트
            this.updateRunwaySliderUI();

            // 강조 표시 슬라이더 업데이트
            this.updateHighlightSliderUI();
        },

        /**
         * UI에서 값 수집
         */
        collectFromUI: function() {
            tempSettings.ma_months = parseInt(document.getElementById('settings_ma_months').value);
            tempSettings.threshold_low = parseInt(document.getElementById('settings_threshold_low').value);
            tempSettings.threshold_high = parseInt(document.getElementById('settings_threshold_high').value);
            tempSettings.runway_threshold = parseFloat(document.getElementById('settings_runway_threshold').value);
        },

        /**
         * 드롭다운 초기화
         */
        initDropdown: function() {
            var dropdown = document.getElementById('settingsMaMonthsDropdown');
            if (!dropdown) return;

            var options = dropdown.querySelectorAll('.custom-dropdown-option');
            options.forEach(function(option) {
                option.onclick = function() {
                    var value = parseInt(this.dataset.value);
                    tempSettings.ma_months = value;

                    // 선택 상태 업데이트
                    options.forEach(function(opt) { opt.classList.remove('selected'); });
                    this.classList.add('selected');

                    // 표시 텍스트 업데이트
                    var selected = dropdown.querySelector('.custom-dropdown-selected');
                    selected.textContent = this.textContent;
                    selected.classList.remove('open');
                    dropdown.querySelector('.custom-dropdown-options').classList.remove('open');

                    // hidden input 업데이트
                    document.getElementById('settings_ma_months').value = value;
                };
            });
        },

        /**
         * 런웨이 슬라이더 초기화
         */
        initRunwaySlider: function() {
            var self = this;
            var bar = document.querySelector('.settings-runway-bar');
            var handleLow = document.getElementById('settings-handle-low');
            var handleHigh = document.getElementById('settings-handle-high');

            if (!bar || !handleLow || !handleHigh) return;

            function startDrag(handle, isLow) {
                return function(e) {
                    e.preventDefault();
                    var barRect = bar.getBoundingClientRect();

                    function onMove(e) {
                        var clientX = e.touches ? e.touches[0].clientX : e.clientX;
                        var percent = (clientX - barRect.left) / barRect.width;
                        percent = Math.max(0, Math.min(1, percent));
                        var value = Math.round(percent * RUNWAY_MAX_VALUE);

                        if (isLow) {
                            // 최소 1, 최대 high-1
                            value = Math.max(1, Math.min(value, tempSettings.threshold_high - 1));
                            tempSettings.threshold_low = value;
                        } else {
                            // 최소 low+1, 최대 7
                            value = Math.max(tempSettings.threshold_low + 1, Math.min(value, RUNWAY_MAX_VALUE));
                            tempSettings.threshold_high = value;
                        }

                        self.updateRunwaySliderUI();
                    }

                    function onEnd() {
                        document.removeEventListener('mousemove', onMove);
                        document.removeEventListener('mouseup', onEnd);
                        document.removeEventListener('touchmove', onMove);
                        document.removeEventListener('touchend', onEnd);
                    }

                    document.addEventListener('mousemove', onMove);
                    document.addEventListener('mouseup', onEnd);
                    document.addEventListener('touchmove', onMove);
                    document.addEventListener('touchend', onEnd);
                };
            }

            handleLow.onmousedown = startDrag(handleLow, true);
            handleLow.ontouchstart = startDrag(handleLow, true);
            handleHigh.onmousedown = startDrag(handleHigh, false);
            handleHigh.ontouchstart = startDrag(handleHigh, false);
        },

        /**
         * 런웨이 슬라이더 UI 업데이트
         */
        updateRunwaySliderUI: function() {
            var lowValue = tempSettings.threshold_low;
            var highValue = tempSettings.threshold_high;

            var lowPercent = (lowValue / RUNWAY_MAX_VALUE) * 100;
            var highPercent = (highValue / RUNWAY_MAX_VALUE) * 100;

            // 세그먼트 크기
            var segmentShortage = document.getElementById('settings-segment-shortage');
            var segmentSufficient = document.getElementById('settings-segment-sufficient');
            var segmentExcess = document.getElementById('settings-segment-excess');

            if (segmentShortage) segmentShortage.style.flex = lowPercent;
            if (segmentSufficient) segmentSufficient.style.flex = highPercent - lowPercent;
            if (segmentExcess) segmentExcess.style.flex = 100 - highPercent;

            // 핸들 위치
            var handleLow = document.getElementById('settings-handle-low');
            var handleHigh = document.getElementById('settings-handle-high');

            if (handleLow) handleLow.style.left = lowPercent + '%';
            if (handleHigh) handleHigh.style.left = highPercent + '%';

            // 스케일 라벨
            var scaleLow = document.getElementById('settings-scale-low');
            var scaleHigh = document.getElementById('settings-scale-high');

            if (scaleLow) scaleLow.textContent = lowValue;
            if (scaleHigh) scaleHigh.textContent = highValue;

            // 값 표시
            var valueLow = document.getElementById('settings-value-low');
            var valueHigh = document.getElementById('settings-value-high');

            if (valueLow) valueLow.textContent = lowValue;
            if (valueHigh) valueHigh.textContent = highValue;

            // hidden input
            document.getElementById('settings_threshold_low').value = lowValue;
            document.getElementById('settings_threshold_high').value = highValue;
        },

        /**
         * 강조 표시 슬라이더 초기화
         */
        initHighlightSlider: function() {
            var self = this;
            var track = document.getElementById('settingsHighlightTrack');
            var handle = document.getElementById('settingsHighlightHandle');

            if (!track || !handle) return;

            function valueToPercent(value) {
                return ((value - HIGHLIGHT_MIN_VALUE) / (HIGHLIGHT_MAX_VALUE - HIGHLIGHT_MIN_VALUE)) * 100;
            }

            function percentToValue(percent) {
                var value = HIGHLIGHT_MIN_VALUE + (percent / 100) * (HIGHLIGHT_MAX_VALUE - HIGHLIGHT_MIN_VALUE);
                // STEP 단위로 반올림
                value = Math.round(value / HIGHLIGHT_STEP) * HIGHLIGHT_STEP;
                return Math.max(HIGHLIGHT_MIN_VALUE, Math.min(HIGHLIGHT_MAX_VALUE, value));
            }

            function startDrag(e) {
                e.preventDefault();
                var trackRect = track.getBoundingClientRect();

                function onMove(e) {
                    var clientX = e.touches ? e.touches[0].clientX : e.clientX;
                    var percent = ((clientX - trackRect.left) / trackRect.width) * 100;
                    percent = Math.max(0, Math.min(100, percent));

                    tempSettings.runway_threshold = percentToValue(percent);
                    self.updateHighlightSliderUI();
                }

                function onEnd() {
                    document.removeEventListener('mousemove', onMove);
                    document.removeEventListener('mouseup', onEnd);
                    document.removeEventListener('touchmove', onMove);
                    document.removeEventListener('touchend', onEnd);
                }

                document.addEventListener('mousemove', onMove);
                document.addEventListener('mouseup', onEnd);
                document.addEventListener('touchmove', onMove);
                document.addEventListener('touchend', onEnd);
            }

            handle.onmousedown = startDrag;
            handle.ontouchstart = startDrag;
        },

        /**
         * 강조 표시 슬라이더 UI 업데이트
         */
        updateHighlightSliderUI: function() {
            var value = tempSettings.runway_threshold;
            var percent = ((value - HIGHLIGHT_MIN_VALUE) / (HIGHLIGHT_MAX_VALUE - HIGHLIGHT_MIN_VALUE)) * 100;

            var handle = document.getElementById('settingsHighlightHandle');
            if (handle) {
                handle.style.left = percent + '%';
            }

            var valueDisplay = document.getElementById('settingsHighlightValue');
            if (valueDisplay) {
                valueDisplay.textContent = value;
            }

            document.getElementById('settings_runway_threshold').value = value;
        },

        /**
         * 현재 저장된 설정 가져오기
         */
        get: function(key) {
            return currentSettings[key];
        },

        getAll: function() {
            return Object.assign({}, currentSettings);
        }
    };

    // Global compatibility functions
    window.openSettingsModal = function() { return Jaego.settings.open(); };
    window.closeSettingsModal = function() { return Jaego.settings.close(); };
    window.saveSettings = function() { return Jaego.settings.save(); };
    window.resetSettingsToDefault = function() { return Jaego.settings.resetToDefaults(); };

    // 드롭다운 토글 함수 (설정 모달 전용)
    window.toggleSettingsDropdown = function(dropdownId) {
        var dropdown = document.getElementById(dropdownId);
        if (!dropdown) return;
        var selected = dropdown.querySelector('.custom-dropdown-selected');
        var options = dropdown.querySelector('.custom-dropdown-options');
        selected.classList.toggle('open');
        options.classList.toggle('open');
    };

})(window.Jaego = window.Jaego || {});
