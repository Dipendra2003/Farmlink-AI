/**
 * FarmLink AI - Cart Operations with AJAX
 * Handles all cart-related AJAX operations with loading indicators and toast notifications
 */

(function() {
    'use strict';

    // Cart state management
    const CartManager = {
        isProcessing: false,
        
        // Initialize cart functionality
        init: function() {
            console.log('Initializing Cart Manager');
            this.bindEvents();
            this.updateCartCount();
            this.initToastContainer();
        },

        // Create toast container if it doesn't exist
        initToastContainer: function() {
            if (!document.getElementById('toast-container')) {
                const container = document.createElement('div');
                container.id = 'toast-container';
                container.className = 'position-fixed top-0 end-0 p-3';
                container.style.zIndex = '9999';
                document.body.appendChild(container);
            }
        },

        // Bind all cart event listeners
        bindEvents: function() {
            // Add to cart buttons (on product pages)
            document.querySelectorAll('.add-to-cart-btn, #add-to-cart-btn').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleAddToCart(e));
            });

            // Buy now buttons
            document.querySelectorAll('.buy-now-btn, #buy-now-btn').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleBuyNow(e));
            });

            // Quantity update inputs
            document.querySelectorAll('.qty-input').forEach(input => {
                input.addEventListener('change', (e) => this.handleQuantityChange(e));
            });

            // Quantity increase buttons
            document.querySelectorAll('.qty-increase').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleQuantityIncrease(e));
            });

            // Quantity decrease buttons
            document.querySelectorAll('.qty-decrease').forEach(btn => {
                btn.addEventListener('click', (e) => this.handleQuantityDecrease(e));
            });

            // Remove item buttons
            document.querySelectorAll('.remove-item-form').forEach(form => {
                form.addEventListener('submit', (e) => this.handleRemoveItem(e));
            });

            // Clear cart button
            document.querySelectorAll('.clear-cart-form').forEach(form => {
                form.addEventListener('submit', (e) => this.handleClearCart(e));
            });
        },

        // Get CSRF token
        getCSRFToken: function() {
            const meta = document.querySelector('meta[name="csrf-token"]');
            return meta ? meta.content : '';
        },

        // Show toast notification
        showToast: function(message, type = 'success') {
            const container = document.getElementById('toast-container');
            if (!container) return;

            const toastId = 'toast-' + Date.now();
            const iconClass = type === 'success' ? 'fa-check-circle' : 
                            type === 'error' ? 'fa-exclamation-circle' : 
                            type === 'warning' ? 'fa-exclamation-triangle' : 'fa-info-circle';
            const bgClass = type === 'success' ? 'bg-success' : 
                          type === 'error' ? 'bg-danger' : 
                          type === 'warning' ? 'bg-warning' : 'bg-info';

            const toast = document.createElement('div');
            toast.id = toastId;
            toast.className = `toast align-items-center text-white ${bgClass} border-0`;
            toast.setAttribute('role', 'alert');
            toast.setAttribute('aria-live', 'assertive');
            toast.setAttribute('aria-atomic', 'true');
            toast.innerHTML = `
                <div class="d-flex">
                    <div class="toast-body">
                        <i class="fas ${iconClass} me-2"></i>${message}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
            `;

            container.appendChild(toast);
            const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
            bsToast.show();

            // Remove toast element after it's hidden
            toast.addEventListener('hidden.bs.toast', () => {
                toast.remove();
            });
        },

        // Show loading indicator on button
        showButtonLoading: function(button, loadingText = 'Processing...') {
            if (!button) return null;
            
            const originalState = {
                html: button.innerHTML,
                disabled: button.disabled,
                classes: button.className
            };

            button.disabled = true;
            button.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>${loadingText}`;
            
            return originalState;
        },

        // Restore button state
        restoreButton: function(button, originalState) {
            if (!button || !originalState) return;
            
            button.innerHTML = originalState.html;
            button.disabled = originalState.disabled;
            button.className = originalState.classes;
        },

        // Update cart count in navbar
        updateCartCount: function() {
            fetch('/cart/count', {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const count = data.count || 0;
                    document.querySelectorAll('.cart-count, .cart-count-badge').forEach(el => {
                        el.textContent = count;
                        el.style.display = count > 0 ? '' : 'none';
                    });
                }
            })
            .catch(error => {
                console.error('Error updating cart count:', error);
            });
        },

        // Handle add to cart
        handleAddToCart: function(e) {
            e.preventDefault();
            
            if (this.isProcessing) return;
            
            const button = e.currentTarget;
            const cropId = button.dataset.cropId;
            
            if (!cropId) {
                this.showToast('Invalid product', 'error');
                return;
            }

            // Try to find quantity input - either on product detail page or browse page
            let quantityInput = document.getElementById('product-quantity');
            if (!quantityInput) {
                // Try browse page quantity input
                quantityInput = document.querySelector(`.cart-quantity-input[data-crop-id="${cropId}"]`);
            }
            
            if (!quantityInput) {
                this.showToast('Quantity input not found', 'error');
                return;
            }

            const quantity = parseFloat(quantityInput.value);
            const maxQuantity = parseFloat(quantityInput.getAttribute('max'));
            
            if (isNaN(quantity) || quantity <= 0) {
                this.showToast('Please enter a valid quantity', 'error');
                quantityInput.focus();
                return;
            }

            if (maxQuantity && quantity > maxQuantity) {
                this.showToast(`Only ${maxQuantity} units available in stock`, 'error');
                quantityInput.focus();
                return;
            }

            this.isProcessing = true;
            const originalState = this.showButtonLoading(button, 'Adding to Cart...');

            fetch(`/cart/add/${cropId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken(),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ quantity: quantity })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.showToast(data.message, 'success');
                    this.updateCartCount();
                    
                    // Show success state briefly
                    button.innerHTML = '<i class="fas fa-check me-2"></i>Added!';
                    setTimeout(() => {
                        this.restoreButton(button, originalState);
                        this.isProcessing = false;
                    }, 2000);
                } else {
                    this.showToast(data.error || 'Failed to add item to cart', 'error');
                    this.restoreButton(button, originalState);
                    this.isProcessing = false;
                }
            })
            .catch(error => {
                console.error('Error adding to cart:', error);
                this.showToast('An error occurred. Please try again.', 'error');
                this.restoreButton(button, originalState);
                this.isProcessing = false;
            });
        },

        // Handle buy now
        handleBuyNow: function(e) {
            e.preventDefault();
            
            if (this.isProcessing) return;
            
            const button = e.currentTarget;
            const cropId = button.dataset.cropId;
            
            if (!cropId) {
                this.showToast('Invalid product', 'error');
                return;
            }

            // Try to find quantity input - either on product detail page or browse page
            let quantityInput = document.getElementById('product-quantity');
            if (!quantityInput) {
                // Try browse page quantity input
                quantityInput = document.querySelector(`.cart-quantity-input[data-crop-id="${cropId}"]`);
            }
            
            if (!quantityInput) {
                this.showToast('Quantity input not found', 'error');
                return;
            }

            const quantity = parseFloat(quantityInput.value);
            const maxQuantity = parseFloat(quantityInput.getAttribute('max'));
            
            if (isNaN(quantity) || quantity <= 0) {
                this.showToast('Please enter a valid quantity', 'error');
                quantityInput.focus();
                return;
            }

            if (maxQuantity && quantity > maxQuantity) {
                this.showToast(`Only ${maxQuantity} units available in stock`, 'error');
                quantityInput.focus();
                return;
            }

            this.isProcessing = true;
            const originalState = this.showButtonLoading(button, 'Processing...');

            fetch(`/cart/buy-now/${cropId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken(),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ quantity: quantity })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.showToast(data.message, 'success');
                    // Redirect to checkout
                    window.location.href = data.redirect_url || '/checkout';
                } else {
                    this.showToast(data.error || 'Failed to process request', 'error');
                    this.restoreButton(button, originalState);
                    this.isProcessing = false;
                }
            })
            .catch(error => {
                console.error('Error processing buy now:', error);
                this.showToast('An error occurred. Please try again.', 'error');
                this.restoreButton(button, originalState);
                this.isProcessing = false;
            });
        },

        // Handle quantity change
        handleQuantityChange: function(e) {
            const input = e.currentTarget;
            const itemId = input.dataset.itemId;
            const quantity = parseFloat(input.value);
            const max = parseFloat(input.getAttribute('max'));

            if (isNaN(quantity) || quantity <= 0) {
                this.showToast('Quantity must be greater than 0', 'error');
                input.value = 0.1;
                return;
            }

            if (max && quantity > max) {
                this.showToast(`Maximum available quantity is ${max}`, 'warning');
                input.value = max;
                this.updateCartItemQuantity(itemId, max);
                return;
            }

            this.updateCartItemQuantity(itemId, quantity);
        },

        // Handle quantity increase
        handleQuantityIncrease: function(e) {
            const button = e.currentTarget;
            const itemId = button.dataset.itemId;
            const max = parseFloat(button.dataset.max);
            const input = document.querySelector(`.qty-input[data-item-id="${itemId}"]`);
            
            if (!input) return;

            let quantity = parseFloat(input.value);
            if (isNaN(quantity)) quantity = 0;
            
            // Get step value from input, default to 1
            const step = parseFloat(input.getAttribute('step')) || 1;

            if (!max || quantity < max) {
                quantity += step;
                input.value = quantity.toFixed(step < 1 ? 1 : 0);
                this.updateCartItemQuantity(itemId, quantity);
            } else {
                this.showToast(`Maximum available quantity is ${max}`, 'warning');
            }
        },

        // Handle quantity decrease
        handleQuantityDecrease: function(e) {
            const button = e.currentTarget;
            const itemId = button.dataset.itemId;
            const input = document.querySelector(`.qty-input[data-item-id="${itemId}"]`);
            
            if (!input) return;

            let quantity = parseFloat(input.value);
            // Get step value from input, default to 1
            const step = parseFloat(input.getAttribute('step')) || 1;
            const minQuantity = step;
            
            if (isNaN(quantity)) quantity = minQuantity;

            if (quantity > minQuantity) {
                quantity = Math.max(minQuantity, quantity - step);
                input.value = quantity.toFixed(step < 1 ? 1 : 0);
                this.updateCartItemQuantity(itemId, quantity);
            }
        },

        // Update cart item quantity via AJAX
        updateCartItemQuantity: function(itemId, quantity) {
            fetch(`/cart/update/${itemId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: `quantity=${quantity}&csrf_token=${this.getCSRFToken()}`
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Update item subtotal
                    const subtotalEl = document.querySelector(`.item-subtotal[data-item-id="${itemId}"]`);
                    if (subtotalEl) {
                        subtotalEl.textContent = '₹' + data.item_subtotal.toFixed(2);
                    }

                    // Update cart totals
                    document.querySelectorAll('#cart-subtotal, #cart-total').forEach(el => {
                        el.textContent = '₹' + data.cart_total.toFixed(2);
                    });

                    const itemCountEl = document.getElementById('cart-item-count');
                    if (itemCountEl) {
                        itemCountEl.textContent = data.item_count;
                    }

                    this.showToast('Cart updated successfully', 'success');
                } else {
                    this.showToast(data.error || 'Failed to update quantity', 'error');
                    location.reload();
                }
            })
            .catch(error => {
                console.error('Error updating cart item:', error);
                this.showToast('An error occurred. Refreshing page...', 'error');
                setTimeout(() => location.reload(), 1500);
            });
        },

        // Handle remove item
        handleRemoveItem: function(e) {
            e.preventDefault();
            
            if (!confirm('Remove this item from cart?')) {
                return;
            }

            const form = e.currentTarget;
            const url = form.action;
            const submitBtn = form.querySelector('button[type="submit"]');
            
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
            }

            fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: `csrf_token=${this.getCSRFToken()}`
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Remove item from DOM with animation
                    const cartItem = form.closest('.cart-item');
                    if (cartItem) {
                        cartItem.style.transition = 'opacity 0.3s';
                        cartItem.style.opacity = '0';
                        setTimeout(() => {
                            cartItem.remove();

                            // Update totals
                            document.querySelectorAll('#cart-subtotal, #cart-total').forEach(el => {
                                el.textContent = '₹' + data.cart_total.toFixed(2);
                            });

                            const itemCountEl = document.getElementById('cart-item-count');
                            if (itemCountEl) {
                                itemCountEl.textContent = data.cart_count;
                            }

                            this.updateCartCount();

                            // Reload if cart is empty
                            if (data.cart_count === 0) {
                                location.reload();
                            }
                        }, 300);
                    }

                    this.showToast(data.message, 'success');
                } else {
                    this.showToast(data.error || 'Failed to remove item', 'error');
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = '<i class="fas fa-trash me-1"></i>Remove';
                    }
                }
            })
            .catch(error => {
                console.error('Error removing item:', error);
                this.showToast('An error occurred. Please try again.', 'error');
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i class="fas fa-trash me-1"></i>Remove';
                }
            });
        },

        // Handle clear cart
        handleClearCart: function(e) {
            e.preventDefault();
            
            if (!confirm('Are you sure you want to clear your cart?')) {
                return;
            }

            const form = e.currentTarget;
            const submitBtn = form.querySelector('button[type="submit"]');
            
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Clearing...';
            }

            fetch('/cart/clear', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: `csrf_token=${this.getCSRFToken()}`
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.showToast(data.message, 'success');
                    this.updateCartCount();
                    // Reload page to show empty cart
                    setTimeout(() => location.reload(), 1000);
                } else {
                    this.showToast(data.error || 'Failed to clear cart', 'error');
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = '<i class="fas fa-trash me-1"></i>Clear Cart';
                    }
                }
            })
            .catch(error => {
                console.error('Error clearing cart:', error);
                this.showToast('An error occurred. Please try again.', 'error');
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i class="fas fa-trash me-1"></i>Clear Cart';
                }
            });
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => CartManager.init());
    } else {
        CartManager.init();
    }

    // Make CartManager globally available
    window.CartManager = CartManager;
})();
