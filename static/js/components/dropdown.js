/**
 * Jaego Custom Dropdown Component
 * Replacement for native select elements
 */

(function(Jaego) {
    'use strict';

    Jaego.dropdown = {
        /**
         * Toggle dropdown open/close state
         * @param {string} dropdownId - ID of the dropdown element
         */
        toggle: function(dropdownId) {
            var dropdown = document.getElementById(dropdownId);
            if (!dropdown) return;

            var selected = dropdown.querySelector('.custom-dropdown-selected');
            var options = dropdown.querySelector('.custom-dropdown-options');

            // Close other dropdowns
            document.querySelectorAll('.custom-dropdown').forEach(function(dd) {
                if (dd.id !== dropdownId) {
                    var ddSelected = dd.querySelector('.custom-dropdown-selected');
                    var ddOptions = dd.querySelector('.custom-dropdown-options');
                    if (ddSelected) ddSelected.classList.remove('open');
                    if (ddOptions) ddOptions.classList.remove('open');
                }
            });

            if (selected) selected.classList.toggle('open');
            if (options) options.classList.toggle('open');
        },

        /**
         * Close all dropdowns
         */
        closeAll: function() {
            document.querySelectorAll('.custom-dropdown').forEach(function(dropdown) {
                var selected = dropdown.querySelector('.custom-dropdown-selected');
                var options = dropdown.querySelector('.custom-dropdown-options');
                if (selected) selected.classList.remove('open');
                if (options) options.classList.remove('open');
            });
        },

        /**
         * Initialize dropdown event listeners
         * Call this on DOMContentLoaded
         */
        init: function() {
            // Option click handler
            document.querySelectorAll('.custom-dropdown-option').forEach(function(option) {
                option.addEventListener('click', function() {
                    var dropdown = this.closest('.custom-dropdown');
                    if (!dropdown) return;

                    var selected = dropdown.querySelector('.custom-dropdown-selected');
                    var options = dropdown.querySelector('.custom-dropdown-options');
                    var hiddenInput = dropdown.nextElementSibling;

                    // Remove selected class from all options
                    dropdown.querySelectorAll('.custom-dropdown-option').forEach(function(opt) {
                        opt.classList.remove('selected');
                    });

                    // Add selected class to clicked option
                    this.classList.add('selected');

                    // Update selected text
                    if (selected) {
                        selected.textContent = this.textContent;
                    }

                    // Update hidden input value
                    if (hiddenInput && hiddenInput.type === 'hidden') {
                        hiddenInput.value = this.dataset.value;
                    }

                    // Close dropdown
                    if (selected) selected.classList.remove('open');
                    if (options) options.classList.remove('open');

                    // Emit change event
                    Jaego.events.emit('dropdown:change', {
                        dropdown: dropdown,
                        value: this.dataset.value,
                        text: this.textContent
                    });
                });
            });

            // Close on outside click
            document.addEventListener('click', function(e) {
                if (!e.target.closest('.custom-dropdown')) {
                    Jaego.dropdown.closeAll();
                }
            });

            // ESC key to close dropdowns
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape') {
                    Jaego.dropdown.closeAll();
                }
            });
        }
    };

    // Global compatibility function
    window.toggleDropdown = function(dropdownId) {
        return Jaego.dropdown.toggle(dropdownId);
    };

    // Auto-initialize on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            Jaego.dropdown.init();
        });
    } else {
        Jaego.dropdown.init();
    }

})(window.Jaego = window.Jaego || {});
