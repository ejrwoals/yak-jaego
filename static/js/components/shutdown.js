/**
 * Jaego Shutdown Component
 * Application exit functionality
 */

(function(Jaego) {
    'use strict';

    Jaego.shutdown = {
        /**
         * Execute application shutdown
         * Shows confirmation modal and sends shutdown request
         */
        execute: async function() {
            var confirmed = await Jaego.confirmModal.show({
                icon: '\u23FB',
                title: '\uC560\uD50C\uB9AC\uCF00\uC774\uC158 \uC885\uB8CC',
                message: '\uC815\uB9D0 \uC560\uD50C\uB9AC\uCF00\uC774\uC158\uC744 \uC885\uB8CC\uD558\uC2DC\uACA0\uC2B5\uB2C8\uAE4C?',
                confirmText: '\uC885\uB8CC',
                isDanger: true
            });

            if (!confirmed) return;

            // Try multiple endpoints for compatibility
            var endpoints = ['/api/shutdown', '/shutdown'];

            for (var i = 0; i < endpoints.length; i++) {
                try {
                    await fetch(endpoints[i], {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        }
                    });
                    break;
                } catch (e) {
                    continue;
                }
            }

            // Show shutdown message
            document.body.innerHTML = '<div style="display: flex; justify-content: center; align-items: center; height: 100vh; font-size: 24px; color: #2d3748;">\u2705 \uC11C\uBC84\uAC00 \uC885\uB8CC\uB418\uC5C8\uC2B5\uB2C8\uB2E4. \uC774 \uCC3D\uC744 \uB2EB\uC73C\uC154\uB3C4 \uB429\uB2C8\uB2E4.</div>';
        }
    };

    // Global compatibility functions
    window.shutdownServer = function() {
        return Jaego.shutdown.execute();
    };

    window.exitApp = function() {
        return Jaego.shutdown.execute();
    };

})(window.Jaego = window.Jaego || {});
