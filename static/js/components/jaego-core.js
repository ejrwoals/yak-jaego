/**
 * Jaego Core JavaScript
 * Namespace and utility functions
 */

window.Jaego = window.Jaego || {};

// Utility functions
Jaego.utils = {
    /**
     * Safely get DOM element by ID
     * @param {string} id - Element ID
     * @returns {HTMLElement|null}
     */
    getElement: function(id) {
        return document.getElementById(id);
    },

    /**
     * Toggle class on element
     * @param {HTMLElement} element - Target element
     * @param {string} className - Class to toggle
     */
    toggleClass: function(element, className) {
        if (element) {
            element.classList.toggle(className);
        }
    },

    /**
     * Add event listener with delegation
     * @param {HTMLElement} parent - Parent element
     * @param {string} selector - Child selector
     * @param {string} eventType - Event type
     * @param {Function} handler - Event handler
     */
    delegate: function(parent, selector, eventType, handler) {
        parent.addEventListener(eventType, function(e) {
            const target = e.target.closest(selector);
            if (target) {
                handler.call(target, e);
            }
        });
    }
};

// Event bus for component communication
Jaego.events = {
    _handlers: {},

    /**
     * Subscribe to an event
     * @param {string} event - Event name
     * @param {Function} handler - Event handler
     */
    on: function(event, handler) {
        if (!this._handlers[event]) {
            this._handlers[event] = [];
        }
        this._handlers[event].push(handler);
    },

    /**
     * Emit an event
     * @param {string} event - Event name
     * @param {*} data - Event data
     */
    emit: function(event, data) {
        const handlers = this._handlers[event];
        if (handlers) {
            handlers.forEach(function(h) {
                h(data);
            });
        }
    },

    /**
     * Unsubscribe from an event
     * @param {string} event - Event name
     * @param {Function} handler - Event handler to remove
     */
    off: function(event, handler) {
        const handlers = this._handlers[event];
        if (handlers) {
            const idx = handlers.indexOf(handler);
            if (idx > -1) {
                handlers.splice(idx, 1);
            }
        }
    }
};

// Modal content detection interface (to be overridden by pages)
Jaego.modal = Jaego.modal || {};
Jaego.modal.hasContent = function() {
    return false;
};
