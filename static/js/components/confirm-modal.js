/**
 * Jaego Confirm Modal Component
 * Custom confirmation dialog replacement for browser's confirm()
 */

(function(Jaego) {
    'use strict';

    var confirmCallback = null;

    // SVG icon map for common types
    var iconMap = {
        'warning': {
            svg: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><use href="#icon-alert-triangle"></use></svg>',
            className: 'icon-warning'
        },
        'danger': {
            svg: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><use href="#icon-trash-2"></use></svg>',
            className: 'icon-danger'
        },
        'info': {
            svg: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><use href="#icon-info"></use></svg>',
            className: 'icon-info'
        },
        'success': {
            svg: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><use href="#icon-check-circle"></use></svg>',
            className: 'icon-success'
        },
        'question': {
            svg: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><use href="#icon-help-circle"></use></svg>',
            className: 'icon-info'
        }
    };

    Jaego.confirmModal = {
        /**
         * Show confirmation modal
         * @param {Object} options - Modal options
         * @param {string} options.icon - Icon type ('warning', 'danger', 'info', 'success', 'question') or emoji
         * @param {string} options.title - Modal title
         * @param {string} options.message - Modal message (supports HTML)
         * @param {string} options.confirmText - Confirm button text
         * @param {string} options.cancelText - Cancel button text (optional)
         * @param {boolean} options.isDanger - Use danger styling for confirm button
         * @returns {Promise<boolean>} - Resolves to true if confirmed, false if cancelled
         */
        show: function(options) {
            var icon = options.icon || 'warning';
            var title = options.title;
            var message = options.message;
            var confirmText = options.confirmText || '\uD655\uC778';
            var cancelText = options.cancelText || '\uCDE8\uC18C';
            var isDanger = options.isDanger || false;

            var modal = document.getElementById('confirmModal');
            if (!modal) {
                console.error('Confirm modal element not found');
                return Promise.resolve(false);
            }

            var iconEl = document.getElementById('confirmModalIcon');
            var titleEl = document.getElementById('confirmModalTitle');
            var messageEl = document.getElementById('confirmModalMessage');
            var confirmBtn = document.getElementById('confirmModalBtn');
            var cancelBtn = document.getElementById('confirmModalCancelBtn');

            // Handle icon - either SVG type or emoji
            if (iconEl) {
                var iconConfig = iconMap[icon];
                if (iconConfig) {
                    iconEl.innerHTML = iconConfig.svg;
                    iconEl.className = 'confirm-modal-icon ' + iconConfig.className;
                } else {
                    // Fallback to emoji for backward compatibility
                    iconEl.textContent = icon;
                    iconEl.className = 'confirm-modal-icon';
                    iconEl.style.fontSize = '48px';
                }
            }

            if (titleEl) titleEl.textContent = title;
            if (messageEl) messageEl.innerHTML = message;

            if (confirmBtn) {
                confirmBtn.textContent = confirmText;
                confirmBtn.className = isDanger ? 'btn-danger' : 'btn-confirm';
            }

            if (cancelBtn) {
                cancelBtn.textContent = cancelText;
            }

            modal.classList.add('visible');

            return new Promise(function(resolve) {
                confirmCallback = resolve;
            });
        },

        /**
         * Close confirmation modal
         * @param {boolean} result - Result to return
         */
        close: function(result) {
            var modal = document.getElementById('confirmModal');
            if (modal) {
                modal.classList.remove('visible');
            }
            if (confirmCallback) {
                confirmCallback(result);
                confirmCallback = null;
            }
        },

        /**
         * Shake the modal box (for validation feedback)
         */
        shake: function() {
            var box = document.querySelector('.confirm-modal-box');
            if (box) {
                box.classList.add('shake');
                setTimeout(function() {
                    box.classList.remove('shake');
                }, 300);
            }
        }
    };

    // ESC key handler for confirm modal
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            var modal = document.getElementById('confirmModal');
            if (modal && modal.classList.contains('visible')) {
                Jaego.confirmModal.close(false);
            }
        }
    });

    // Global compatibility functions (for backward compatibility)
    window.showConfirmModal = function(options) {
        return Jaego.confirmModal.show(options);
    };

    window.closeConfirmModal = function(result) {
        return Jaego.confirmModal.close(result);
    };

})(window.Jaego = window.Jaego || {});
