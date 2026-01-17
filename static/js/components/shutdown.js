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
            document.body.innerHTML = `
                <div style="display: flex; justify-content: center; align-items: center; height: 100vh; background: #fafafa;">
                    <div style="text-align: center; padding: 48px; background: white; border-radius: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 1px solid #e4e4e7; max-width: 400px;">
                        <div style="width: 64px; height: 64px; background: #d1fae5; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 24px;">
                            <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                                <polyline points="22 4 12 14.01 9 11.01"/>
                            </svg>
                        </div>
                        <h1 style="margin: 0 0 12px; font-size: 20px; font-weight: 700; color: #18181b;">서버가 종료되었습니다</h1>
                        <p style="margin: 0; font-size: 14px; color: #71717a;">이 창을 닫으셔도 됩니다.</p>
                    </div>
                </div>
            `;
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
