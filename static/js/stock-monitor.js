/**
 * Real-time Stock Monitoring
 * Automatically updates stock displays on product pages
 */

class StockMonitor {
    constructor() {
        this.updateInterval = 30000; // Update every 30 seconds
        this.activeMonitors = new Map();
    }

    /**
     * Start monitoring a crop's stock level
     * @param {number} cropId - The crop ID to monitor
     * @param {string} elementId - The DOM element ID to update
     */
    startMonitoring(cropId, elementId) {
        if (this.activeMonitors.has(cropId)) {
            console.log(`Already monitoring crop ${cropId}`);
            return;
        }

        // Initial update
        this.updateStock(cropId, elementId);

        // Set up periodic updates
        const intervalId = setInterval(() => {
            this.updateStock(cropId, elementId);
        }, this.updateInterval);

        this.activeMonitors.set(cropId, intervalId);
        console.log(`Started monitoring crop ${cropId}`);
    }

    /**
     * Stop monitoring a crop
     * @param {number} cropId - The crop ID to stop monitoring
     */
    stopMonitoring(cropId) {
        const intervalId = this.activeMonitors.get(cropId);
        if (intervalId) {
            clearInterval(intervalId);
            this.activeMonitors.delete(cropId);
            console.log(`Stopped monitoring crop ${cropId}`);
        }
    }

    /**
     * Stop all active monitors
     */
    stopAll() {
        this.activeMonitors.forEach((intervalId, cropId) => {
            clearInterval(intervalId);
            console.log(`Stopped monitoring crop ${cropId}`);
        });
        this.activeMonitors.clear();
    }

    /**
     * Update stock display for a crop
     * @param {number} cropId - The crop ID
     * @param {string} elementId - The DOM element ID to update
     */
    async updateStock(cropId, elementId) {
        try {
            const response = await fetch(`/api/crop/${cropId}/stock`);
            const data = await response.json();

            if (data.success) {
                this.updateStockDisplay(elementId, data);
            } else {
                console.error(`Failed to fetch stock for crop ${cropId}:`, data.error);
            }
        } catch (error) {
            console.error(`Error fetching stock for crop ${cropId}:`, error);
        }
    }

    /**
     * Update the DOM with new stock information
     * @param {string} elementId - The DOM element ID
     * @param {object} stockData - The stock data from API
     */
    updateStockDisplay(elementId, stockData) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.warn(`Element ${elementId} not found`);
            return;
        }

        // Update quantity text
        const quantityText = `${stockData.quantity} ${stockData.unit}`;
        element.textContent = quantityText;

        // Update visual indicators
        element.classList.remove('text-success', 'text-warning', 'text-danger');
        
        if (stockData.quantity === 0) {
            element.classList.add('text-danger');
            element.textContent = 'Out of Stock';
            
            // Disable order buttons if present
            this.disableOrderButtons(stockData.crop_id);
        } else if (stockData.quantity < 50) {
            element.classList.add('text-warning');
            element.textContent = `${quantityText} (Low Stock)`;
        } else {
            element.classList.add('text-success');
        }

        // Update availability status
        if (!stockData.is_available) {
            this.disableOrderButtons(stockData.crop_id);
        }
    }

    /**
     * Disable order buttons for a crop
     * @param {number} cropId - The crop ID
     */
    disableOrderButtons(cropId) {
        const buttons = document.querySelectorAll(`[data-crop-id="${cropId}"]`);
        buttons.forEach(button => {
            if (button.classList.contains('btn-order') || 
                button.classList.contains('add-to-cart')) {
                button.disabled = true;
                button.classList.add('disabled');
                button.title = 'Out of stock';
            }
        });
    }

    /**
     * Check availability before adding to cart
     * @param {number} cropId - The crop ID
     * @param {number} quantity - The requested quantity
     * @returns {Promise<boolean>} - True if available, false otherwise
     */
    async checkAvailability(cropId, quantity) {
        try {
            const response = await fetch(`/api/crop/${cropId}/check-availability`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ quantity: quantity })
            });

            const data = await response.json();

            if (data.success && data.available) {
                return true;
            } else {
                // Show error message
                const message = data.reason || data.error || 'Insufficient stock';
                this.showAvailabilityError(message, data);
                return false;
            }
        } catch (error) {
            console.error('Error checking availability:', error);
            this.showAvailabilityError('Unable to verify stock availability');
            return false;
        }
    }

    /**
     * Show availability error message
     * @param {string} message - The error message
     * @param {object} data - Additional data from API
     */
    showAvailabilityError(message, data = {}) {
        // Create alert element
        const alert = document.createElement('div');
        alert.className = 'alert alert-warning alert-dismissible fade show';
        alert.role = 'alert';
        
        let alertContent = `<i class="fas fa-exclamation-triangle me-2"></i>${message}`;
        
        if (data.available_quantity !== undefined) {
            alertContent += `<br><small>Available: ${data.available_quantity} ${data.unit}</small>`;
        }
        
        alertContent += `
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        alert.innerHTML = alertContent;

        // Insert at top of page
        const container = document.querySelector('.container') || document.body;
        container.insertBefore(alert, container.firstChild);

        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            alert.remove();
        }, 5000);
    }

    /**
     * Monitor all crops on current page
     */
    monitorPageCrops() {
        const stockElements = document.querySelectorAll('[data-stock-monitor]');
        stockElements.forEach(element => {
            const cropId = parseInt(element.dataset.cropId);
            const elementId = element.id;
            
            if (cropId && elementId) {
                this.startMonitoring(cropId, elementId);
            }
        });
    }
}

// Create global instance
const stockMonitor = new StockMonitor();

// Auto-initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Monitor all crops on page
    stockMonitor.monitorPageCrops();

    // Add availability check to order forms
    const orderForms = document.querySelectorAll('form[data-check-stock]');
    orderForms.forEach(form => {
        form.addEventListener('submit', async function(e) {
            const cropId = parseInt(form.dataset.cropId);
            const quantityInput = form.querySelector('input[name="quantity_requested"]');
            
            if (cropId && quantityInput) {
                const quantity = parseFloat(quantityInput.value);
                
                if (quantity > 0) {
                    e.preventDefault();
                    
                    const isAvailable = await stockMonitor.checkAvailability(cropId, quantity);
                    
                    if (isAvailable) {
                        form.submit();
                    }
                }
            }
        });
    });

    // Add availability check to add-to-cart buttons
    const addToCartButtons = document.querySelectorAll('.add-to-cart[data-check-stock]');
    addToCartButtons.forEach(button => {
        button.addEventListener('click', async function(e) {
            const cropId = parseInt(button.dataset.cropId);
            const quantity = parseFloat(button.dataset.quantity || 1);
            
            if (cropId) {
                e.preventDefault();
                
                const isAvailable = await stockMonitor.checkAvailability(cropId, quantity);
                
                if (isAvailable) {
                    // Proceed with add to cart
                    const originalOnClick = button.getAttribute('onclick');
                    if (originalOnClick) {
                        eval(originalOnClick);
                    }
                }
            }
        });
    });
});

// Clean up on page unload
window.addEventListener('beforeunload', function() {
    stockMonitor.stopAll();
});

// Export for use in other scripts
window.stockMonitor = stockMonitor;
