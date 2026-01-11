/**
 * Jaego Confirm Modal Component
 * Custom confirmation dialog replacement for browser's confirm()
 */

(function(Jaego) {
    'use strict';

    let confirmCallback = null;

    Jaego.confirmModal = {
        /**
         * Show confirmation modal
         * @param {Object} options - Modal options
         * @param {string} options.icon - Icon to display (emoji)
         * @param {string} options.title - Modal title
         * @param {string} options.message - Modal message (supports HTML)
         * @param {string} options.confirmText - Confirm button text
         * @param {boolean} options.isDanger - Use danger styling for confirm button
         * @returns {Promise<boolean>} - Resolves to true if confirmed, false if cancelled
         */
        show: function(options) {
            var icon = options.icon || '\u26A0\uFE0F';
            var title = options.title;
            var message = options.message;
            var confirmText = options.confirmText || '\uD655\uC778';
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

            if (iconEl) iconEl.textContent = icon;
            if (titleEl) titleEl.textContent = title;
            if (messageEl) messageEl.innerHTML = message;

            if (confirmBtn) {
                confirmBtn.textContent = confirmText;
                confirmBtn.className = isDanger ? 'btn-danger' : 'btn-confirm';
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
