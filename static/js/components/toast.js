/**
 * Jaego Toast Component
 * Toast notification system
 */

(function(Jaego) {
    'use strict';

    Jaego.toast = {
        /**
         * Show a toast notification
         * @param {string} message - Message to display
         * @param {string} type - Toast type: 'success', 'error', 'info', 'warning'
         */
        show: function(message, type) {
            type = type || 'success';
            var container = document.getElementById('toast-container');

            if (!container) {
                console.warn('Toast container not found');
                return;
            }

            var toast = document.createElement('div');
            toast.className = 'toast ' + type;
            toast.textContent = message;
            container.appendChild(toast);

            // Trigger animation
            requestAnimationFrame(function() {
                toast.classList.add('show');
            });

            // Auto-remove after 3 seconds
            setTimeout(function() {
                toast.classList.remove('show');
                setTimeout(function() {
                    if (toast.parentNode) {
                        toast.remove();
                    }
                }, 300);
            }, 3000);
        },

        /**
         * Show success toast
         * @param {string} message - Message to display
         */
        success: function(message) {
            this.show(message, 'success');
        },

        /**
         * Show error toast
         * @param {string} message - Message to display
         */
        error: function(message) {
            this.show(message, 'error');
        },

        /**
         * Show info toast
         * @param {string} message - Message to display
         */
        info: function(message) {
            this.show(message, 'info');
        },

        /**
         * Show warning toast
         * @param {string} message - Message to display
         */
        warning: function(message) {
            this.show(message, 'warning');
        }
    };

    // Global compatibility function
    window.showToast = function(message, type) {
        return Jaego.toast.show(message, type);
    };

})(window.Jaego = window.Jaego || {});
