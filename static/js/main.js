/**
 * FarmLink AI - Main JavaScript File
 * Handles frontend interactions and enhancements
 */

// Define the FarmLink object
const FarmLink = {
    initModals: function() {
        // Calculate scrollbar width once
        const scrollDiv = document.createElement('div');
        scrollDiv.className = 'modal-scrollbar-measure';
        document.body.appendChild(scrollDiv);
        const scrollbarWidth = scrollDiv.getBoundingClientRect().width - scrollDiv.clientWidth;
        document.body.removeChild(scrollDiv);
        document.documentElement.style.setProperty('--scrollbar-width', `${scrollbarWidth}px`);

        // Process each modal
        document.querySelectorAll('.modal').forEach(modal => {
            // Prevent double initialization
            if (modal.dataset.initialized === 'true') return;
            modal.dataset.initialized = 'true';
            
            // Remove any existing Bootstrap modal instance to prevent conflicts
            const existingInstance = bootstrap.Modal.getInstance(modal);
            if (existingInstance) {
                existingInstance.dispose();
            }
            
            // Initialize Bootstrap modal with specific config
            const modalInstance = new bootstrap.Modal(modal, {
                backdrop: modal.classList.contains('delete-confirmation-modal') ? 'static' : true,
                keyboard: true,
                focus: true
            });

            // Cache form elements
            const form = modal.querySelector('form');
            const firstInput = modal.querySelector('input:not([type="hidden"]), textarea, select');
            const submitButton = form ? form.querySelector('button[type="submit"]') : null;
            
            // Handle confirmation modals specifically
            if (modal.classList.contains('delete-confirmation-modal')) {
                const confirmBtn = modal.querySelector('.confirm-delete');
                const cancelBtn = modal.querySelector('.cancel-delete');
                
                if (confirmBtn) {
                    confirmBtn.addEventListener('click', (e) => {
                        // Add loading state
                        confirmBtn.disabled = true;
                        confirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';
                        
                        // If it's a link, proceed with navigation
                        if (confirmBtn.tagName === 'A') {
                            return true;
                        }
                        
                        // If it's a form submission, submit the form
                        const form = modal.querySelector('form');
                        if (form) {
                            form.submit();
                        }
                    });
                }
                
                if (cancelBtn) {
                    cancelBtn.addEventListener('click', () => {
                        modalInstance.hide();
                    });
                }
                
                // Add confirmation sound effect (optional)
                modal.addEventListener('show.bs.modal', () => {
                    // You could add a subtle sound here if needed
                    console.log('Delete confirmation modal opened');
                });
            }

            // Handle modal opening
            modal.addEventListener('show.bs.modal', (e) => {
                // Reset form if exists
                if (form) {
                    form.reset();
                    form.classList.remove('was-validated');
                }

                // Remove any previous error messages
                modal.querySelectorAll('.invalid-feedback').forEach(el => el.remove());
                modal.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
                
                // Clear any existing timeouts for delete modals
                if (modal.hideTimeout) {
                    clearTimeout(modal.hideTimeout);
                }
            });

            // Handle modal shown
            modal.addEventListener('shown.bs.modal', () => {
                // Focus first input if available
                if (firstInput) {
                    firstInput.focus();
                }

                // Enable submit button if it was disabled
                if (submitButton) {
                    submitButton.disabled = false;
                }
            });

            // Handle form submission
            if (form) {
                form.addEventListener('submit', (e) => {
                    if (!form.checkValidity()) {
                        e.preventDefault();
                        e.stopPropagation();
                    } else if (submitButton) {
                        // Disable submit button to prevent double submission
                        submitButton.disabled = true;
                        submitButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';
                    }
                    form.classList.add('was-validated');
                });
            }

            // Handle modal hiding
            modal.addEventListener('hide.bs.modal', () => {
                // Remove validation states
                if (form) {
                    form.classList.remove('was-validated');
                    form.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
                }
            });

            // Clean up after modal is hidden
            modal.addEventListener('hidden.bs.modal', () => {
                // Reset form if exists
                if (form) {
                    form.reset();
                }

                // Clear any error messages
                modal.querySelectorAll('.invalid-feedback').forEach(el => el.remove());
                
                // Reset submit button if exists
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.innerHTML = submitButton.dataset.originalText || 'Submit';
                }

                // Check if there are other modals open
                if (document.querySelector('.modal.show')) {
                    document.body.classList.add('modal-open');
                }
            });

            // Handle keyboard navigation
            modal.addEventListener('keydown', (e) => {
                // Close on escape key
                if (e.key === 'Escape') {
                    modalInstance.hide();
                }
                
                // Trap focus within modal
                if (e.key === 'Tab') {
                    const focusableElements = modal.querySelectorAll(
                        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
                    );
                    const firstFocusable = focusableElements[0];
                    const lastFocusable = focusableElements[focusableElements.length - 1];

                    if (e.shiftKey) {
                        if (document.activeElement === firstFocusable) {
                            lastFocusable.focus();
                            e.preventDefault();
                        }
                    } else {
                        if (document.activeElement === lastFocusable) {
                            firstFocusable.focus();
                            e.preventDefault();
                        }
                    }
                }
            });
            
            // Prevent event bubbling on modal content clicks
            const modalContent = modal.querySelector('.modal-content');
            if (modalContent) {
                modalContent.addEventListener('click', (e) => {
                    e.stopPropagation();
                });
            }
            
            // Prevent multiple rapid clicks on modal trigger buttons
            const modalTriggers = document.querySelectorAll(`[data-bs-target="#${modal.id}"]`);
            modalTriggers.forEach(trigger => {
                let isOpening = false;
                trigger.addEventListener('click', (e) => {
                    if (isOpening) {
                        e.preventDefault();
                        e.stopImmediatePropagation();
                        return false;
                    }
                    isOpening = true;
                    setTimeout(() => {
                        isOpening = false;
                    }, 500);
                }, true);
            });
        });
    },
    
    init: function() {
        this.initEventListeners();
        this.initFormValidations();
        this.initTooltips();
        this.initModals();
        this.initSearchEnhancements();
        this.initImageHandling();
        this.initOrderCalculations();
        this.initMessageSystem();
        this.initDashboardEnhancements();
        this.initMobileOptimizations();
        this.initPasswordToggle();
    },

    // Initialize password visibility toggle
    initPasswordToggle: function() {
        const passwordInputs = document.querySelectorAll('input[type="password"]');
        passwordInputs.forEach(input => {
            if (input.classList.contains('has-password-toggle')) return;
            input.classList.add('has-password-toggle');

            const btn = document.createElement('button');
            btn.className = 'btn btn-outline-secondary toggle-password';
            btn.type = 'button';
            if (input.classList.contains('form-control-lg')) {
                btn.classList.add('btn-lg');
            }
            btn.innerHTML = '<i class="fas fa-eye"></i>';
            
            btn.addEventListener('click', function() {
                const icon = this.querySelector('i');
                if (input.type === 'password') {
                    input.type = 'text';
                    icon.classList.remove('fa-eye');
                    icon.classList.add('fa-eye-slash');
                } else {
                    input.type = 'password';
                    icon.classList.remove('fa-eye-slash');
                    icon.classList.add('fa-eye');
                }
            });

            if (input.parentNode.classList.contains('input-group')) {
                input.parentNode.appendChild(btn);
            } else {
                const wrapper = document.createElement('div');
                wrapper.className = 'input-group';
                input.parentNode.insertBefore(wrapper, input);
                wrapper.appendChild(input);
                wrapper.appendChild(btn);
            }
        });
    },

    // Initialize all event listeners
    initEventListeners: function() {
        // Smooth scrolling for anchor links
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });

        // Auto-dismiss alerts after 5 seconds
        setTimeout(() => {
            const alerts = document.querySelectorAll('.alert');
            alerts.forEach(alert => {
                if (alert.classList.contains('alert-success') || alert.classList.contains('alert-info')) {
                    const bsAlert = new bootstrap.Alert(alert);
                    bsAlert.close();
                }
            });
        }, 5000);

        // Add loading states to forms
        document.querySelectorAll('form').forEach(form => {
            form.addEventListener('submit', function() {
                const submitBtn = this.querySelector('button[type="submit"], input[type="submit"]');
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.classList.add('loading');
                    
                    // Re-enable after 10 seconds as fallback
                    setTimeout(() => {
                        submitBtn.disabled = false;
                        submitBtn.classList.remove('loading');
                    }, 10000);
                }
            });
        });
    },

    // Enhanced form validations
    initFormValidations: function() {
        // Real-time email validation
        const emailInputs = document.querySelectorAll('input[type="email"]');
        emailInputs.forEach(input => {
            input.addEventListener('blur', function() {
                this.validateEmail();
            });
        });

        // Phone number formatting
        const phoneInputs = document.querySelectorAll('input[name="phone"]');
        phoneInputs.forEach(input => {
            input.addEventListener('input', function() {
                this.value = this.value.replace(/[^0-9+\-\s()]/g, '');
            });
        });

        // Price validation
        const priceInputs = document.querySelectorAll('input[name="price_per_unit"], input[name="min_price"], input[name="max_price"]');
        priceInputs.forEach(input => {
            input.addEventListener('input', function() {
                const value = parseFloat(this.value);
                if (value < 0) {
                    this.value = 0;
                }
            });
        });

        // Quantity validation
        const quantityInputs = document.querySelectorAll('input[name="quantity"], input[name="quantity_requested"]');
        quantityInputs.forEach(input => {
            input.addEventListener('input', function() {
                const value = parseFloat(this.value);
                if (value < 0) {
                    this.value = 0;
                }
                
                // Update order calculations if on order form
                if (this.name === 'quantity_requested') {
                    this.updateOrderTotal();
                }
            });
        });

        // Password strength indicator
        const passwordInputs = document.querySelectorAll('input[type="password"]');
        passwordInputs.forEach(input => {
            if (input.name === 'password') {
                input.addEventListener('input', function() {
                    this.checkPasswordStrength();
                });
            }
        });
    },

    // Initialize tooltips
    initTooltips: function() {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    },

    // Enhanced search functionality
    initSearchEnhancements: function() {
        const searchForm = document.querySelector('#marketplaceSearch, .search-filters form');
        if (searchForm) {
            // Auto-submit search after typing stops
            let searchTimeout;
            const searchInput = searchForm.querySelector('input[name="query"]');
            
            if (searchInput) {
                searchInput.addEventListener('input', function() {
                    clearTimeout(searchTimeout);
                    searchTimeout = setTimeout(() => {
                        // Only auto-submit if user has typed at least 3 characters
                        if (this.value.length >= 3 || this.value.length === 0) {
                            searchForm.submit();
                        }
                    }, 1000);
                });
            }

            // Clear filters button
            const clearBtn = document.createElement('button');
            clearBtn.type = 'button';
            clearBtn.className = 'btn btn-outline-secondary';
            clearBtn.innerHTML = '<i class="fas fa-times me-1"></i>Clear';
            clearBtn.addEventListener('click', function() {
                searchForm.reset();
                window.location.href = window.location.pathname;
            });

            const submitBtn = searchForm.querySelector('button[type="submit"]');
            if (submitBtn && submitBtn.parentNode) {
                submitBtn.parentNode.appendChild(clearBtn);
            }
        }
    },

    // Image handling and preview
    initImageHandling: function() {
        const imageUrlInputs = document.querySelectorAll('input[name="image_url"], input[name="profile_image"]');
        
        imageUrlInputs.forEach(input => {
            // Create image preview container
            const previewContainer = document.createElement('div');
            previewContainer.className = 'image-preview mt-2';
            previewContainer.style.display = 'none';
            input.parentNode.appendChild(previewContainer);

            input.addEventListener('blur', function() {
                const url = this.value.trim();
                if (url) {
                    this.showImagePreview(url, previewContainer);
                } else {
                    previewContainer.style.display = 'none';
                }
            });
        });
    },

    // Order calculations
    initOrderCalculations: function() {
        const orderForm = document.querySelector('form[action*="place_order"]');
        if (orderForm) {
            const quantityInput = orderForm.querySelector('input[name="quantity_requested"]');
            const priceDisplay = document.createElement('div');
            priceDisplay.className = 'order-calculation mt-2 p-3 bg-light rounded';
            
            if (quantityInput) {
                quantityInput.parentNode.appendChild(priceDisplay);
                
                quantityInput.addEventListener('input', function() {
                    this.updateOrderCalculation(priceDisplay);
                });

                // Initial calculation
                quantityInput.updateOrderCalculation(priceDisplay);
            }
        }
    },

    // Message system enhancements
    initMessageSystem: function() {
        // Auto-expand message content that's too long
        document.querySelectorAll('.message-item').forEach(item => {
            const content = item.querySelector('p');
            if (content && content.textContent.length > 100) {
                content.style.cursor = 'pointer';
                content.title = 'Click to expand';
                
                content.addEventListener('click', function() {
                    const fullContent = this.dataset.fullContent || this.textContent;
                    if (this.textContent.includes('...')) {
                        this.textContent = fullContent;
                    } else {
                        this.textContent = fullContent.substring(0, 100) + '...';
                    }
                });
            }
        });

        // Initialize reply functionality
        window.replyToMessage = function(recipientId, recipientName, subject, messageId) {
            const modal = document.getElementById('newMessageModal');
            if (!modal) return;

            const form = modal.querySelector('form');
            if (!form) return;

            // Update form action for reply
            form.action = `/messages/reply/${messageId}`;

            // Update the recipient info
            const recipientInfo = modal.querySelector('.recipient-info');
            if (recipientInfo) {
                recipientInfo.innerHTML = `
                    <div class="d-flex align-items-center">
                        <img src="https://ui-avatars.com/api/?name=${encodeURIComponent(recipientName)}&background=28a745&color=fff&size=32"
                             class="rounded-circle me-2" width="32" height="32" alt="Recipient">
                        <div class="fw-bold">${recipientName}</div>
                    </div>
                `;
            }

            // Set the subject
            const subjectInput = modal.querySelector('input[name="subject"]');
            if (subjectInput) {
                subjectInput.value = subject;
            }

            // Clear and focus the content
            const contentInput = modal.querySelector('textarea[name="content"]');
            if (contentInput) {
                contentInput.value = '';
            }

            // Show the modal
            const modalInstance = new bootstrap.Modal(modal);
            modalInstance.show();

            // Focus on the content area after modal is shown
            modal.addEventListener('shown.bs.modal', function () {
                if (contentInput) {
                    contentInput.focus();
                }
            }, { once: true });
        };

        // Mark messages as read when clicked
        document.querySelectorAll('.message-item').forEach(item => {
            if (item.classList.contains('bg-light')) { // Unread message
                item.addEventListener('click', function() {
                    const messageId = this.dataset.messageId;
                    if (messageId) {
                        // Create a hidden form to mark as read
                        const form = document.createElement('form');
                        form.method = 'POST';
                        form.action = `/messages/read/${messageId}`;
                        form.style.display = 'none';
                        document.body.appendChild(form);
                        form.submit();
                    }
                });
            }
        });
    },

    // Dashboard enhancements
    initDashboardEnhancements: function() {
        // Animate counter numbers
        document.querySelectorAll('.card h2, .card h3').forEach(counter => {
            if (/^\d+$/.test(counter.textContent.trim())) {
                this.animateCounter(counter);
            }
        });

        // Weather widget interactions
        const weatherWidget = document.querySelector('.weather-widget, .card .fa-cloud-sun');
        if (weatherWidget) {
            weatherWidget.addEventListener('click', function() {
                // Refresh weather data (if implemented)
                this.classList.add('fa-spin');
                setTimeout(() => {
                    this.classList.remove('fa-spin');
                }, 2000);
            });
        }

        // Quick action buttons hover effects
        document.querySelectorAll('.btn[href*="add"], .btn[href*="manage"]').forEach(btn => {
            btn.addEventListener('mouseenter', function() {
                this.style.transform = 'scale(1.05)';
            });
            
            btn.addEventListener('mouseleave', function() {
                this.style.transform = 'scale(1)';
            });
        });
    },

    // Mobile optimizations and rightbar functionality
    initMobileOptimizations: function() {
        // ===== RIGHTBAR NAVIGATION FUNCTIONALITY =====
        
        // Initialize rightbar elements
        const rightbarToggle = document.getElementById('rightbarToggle');
        const rightbar = document.getElementById('rightbar');
        const rightbarOverlay = document.getElementById('rightbarOverlay');
        const rightbarClose = document.getElementById('rightbarClose');
        const rightbarLinks = document.querySelectorAll('.rightbar-link');
        
        // Only initialize if elements exist
        if (!rightbarToggle || !rightbar || !rightbarOverlay || !rightbarClose) {
            console.warn('Rightbar elements not found');
            return;
        }
        
        // Function to open rightbar
        const openRightbar = () => {
            rightbar.classList.add('show');
            rightbarOverlay.classList.add('show');
            document.body.classList.add('rightbar-open');
            rightbar.setAttribute('aria-hidden', 'false');
            rightbarToggle.setAttribute('aria-expanded', 'true');
            
            // Focus first link for accessibility
            const firstLink = rightbar.querySelector('.rightbar-link');
            if (firstLink) {
                setTimeout(() => firstLink.focus(), 300);
            }
        };
        
        // Function to close rightbar
        const closeRightbar = () => {
            rightbar.classList.remove('show');
            rightbarOverlay.classList.remove('show');
            document.body.classList.remove('rightbar-open');
            rightbar.setAttribute('aria-hidden', 'true');
            rightbarToggle.setAttribute('aria-expanded', 'false');
            
            // Return focus to toggle button
            rightbarToggle.focus();
        };
        
        // Event listeners for rightbar
        rightbarToggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            openRightbar();
        });
        
        rightbarClose.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            closeRightbar();
        });
        
        rightbarOverlay.addEventListener('click', function(e) {
            e.preventDefault();
            closeRightbar();
        });
        
        // Close rightbar when a link is clicked (mobile navigation behavior)
        rightbarLinks.forEach(link => {
            link.addEventListener('click', function() {
                // Only close if it's not a dropdown toggle or hash link
                if (!this.classList.contains('dropdown-toggle') && 
                    !this.getAttribute('href')?.startsWith('#')) {
                    setTimeout(() => closeRightbar(), 150);
                }
            });
        });
        
        // Keyboard navigation for rightbar
        document.addEventListener('keydown', function(e) {
            // Close rightbar on Escape key
            if (e.key === 'Escape' && rightbar.classList.contains('show')) {
                closeRightbar();
            }
            
            // Trap focus within rightbar when open
            if (rightbar.classList.contains('show')) {
                const focusableElements = rightbar.querySelectorAll(
                    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
                );
                const firstElement = focusableElements[0];
                const lastElement = focusableElements[focusableElements.length - 1];
                
                if (e.key === 'Tab') {
                    if (e.shiftKey) {
                        if (document.activeElement === firstElement) {
                            e.preventDefault();
                            lastElement.focus();
                        }
                    } else {
                        if (document.activeElement === lastElement) {
                            e.preventDefault();
                            firstElement.focus();
                        }
                    }
                }
            }
        });
        
        // Handle window resize - close rightbar if screen becomes large
        window.addEventListener('resize', function() {
            if (window.innerWidth >= 992 && rightbar.classList.contains('show')) {
                closeRightbar();
            }
        });

        // ===== MOBILE TOUCH OPTIMIZATIONS =====
        
        // Improve touch interactions on mobile
        if ('ontouchstart' in window) {
            document.body.classList.add('touch-device');
        }

        // Optimize table scrolling on mobile
        const tables = document.querySelectorAll('.table-responsive');
        tables.forEach(table => {
            if (window.innerWidth < 768) {
                table.style.overflowX = 'auto';
                table.style.webkitOverflowScrolling = 'touch';
            }
        });
    },

    // Utility functions
    animateCounter: function(element) {
        const target = parseInt(element.textContent);
        const duration = 2000;
        const step = target / (duration / 16);
        let current = 0;
        
        const timer = setInterval(() => {
            current += step;
            if (current >= target) {
                element.textContent = target;
                clearInterval(timer);
            } else {
                element.textContent = Math.floor(current);
            }
        }, 16);
    },

    showNotification: function(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        alertDiv.style.top = '20px';
        alertDiv.style.right = '20px';
        alertDiv.style.zIndex = '9999';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(alertDiv);
        
        // Auto remove after 5 seconds
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 5000);
    },

    formatCurrency: function(amount) {
        return '₹' + new Intl.NumberFormat('en-IN').format(amount);
    }
};

// Make FarmLink globally available
window.FarmLink = FarmLink;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    FarmLink.init();
});

// Extend native prototypes with useful methods
HTMLInputElement.prototype.validateEmail = function() {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const isValid = emailRegex.test(this.value);
    
    if (this.value && !isValid) {
        this.classList.add('is-invalid');
        this.setCustomValidity('Please enter a valid email address');
    } else {
        this.classList.remove('is-invalid');
        this.setCustomValidity('');
    }
    
    return isValid;
};

HTMLInputElement.prototype.checkPasswordStrength = function() {
    const password = this.value;
    const strengthMeter = document.getElementById('passwordStrength') || this.createPasswordMeter();
    
    let strength = 0;
    let feedback = [];
    
    if (password.length >= 8) strength++;
    else feedback.push('At least 8 characters');
    
    if (/[a-z]/.test(password)) strength++;
    else feedback.push('Lowercase letter');
    
    if (/[A-Z]/.test(password)) strength++;
    else feedback.push('Uppercase letter');
    
    if (/[0-9]/.test(password)) strength++;
    else feedback.push('Number');
    
    if (/[^A-Za-z0-9]/.test(password)) strength++;
    else feedback.push('Special character');
    
    const strengthText = ['Very Weak', 'Weak', 'Fair', 'Good', 'Strong'][strength];
    const strengthColor = ['danger', 'warning', 'info', 'success', 'success'][strength];
    
    strengthMeter.innerHTML = `
        <div class="progress mt-2" style="height: 5px;">
            <div class="progress-bar bg-${strengthColor}" style="width: ${(strength/5)*100}%"></div>
        </div>
        <small class="text-${strengthColor}">${strengthText}</small>
        ${feedback.length ? `<small class="text-muted d-block">Missing: ${feedback.join(', ')}</small>` : ''}
    `;
};

HTMLInputElement.prototype.createPasswordMeter = function() {
    const meter = document.createElement('div');
    meter.id = 'passwordStrength';
    meter.className = 'password-strength w-100 mt-1';
    
    if (this.parentNode.classList.contains('input-group')) {
        this.parentNode.parentNode.appendChild(meter);
    } else {
        this.parentNode.appendChild(meter);
    }
    return meter;
};

HTMLInputElement.prototype.updateOrderTotal = function() {
    const pricePerUnit = parseFloat(document.querySelector('[data-price-per-unit]')?.dataset.pricePerUnit || 0);
    const quantity = parseFloat(this.value || 0);
    const total = pricePerUnit * quantity;
    
    const totalDisplay = document.querySelector('.order-total, .total-amount');
    if (totalDisplay) {
        totalDisplay.textContent = FarmLink.formatCurrency(total);
    }
};

HTMLInputElement.prototype.updateOrderCalculation = function(container) {
    const pricePerUnit = parseFloat(this.closest('form').dataset.pricePerUnit || 
                         document.querySelector('[data-price]')?.dataset.price || 0);
    const quantity = parseFloat(this.value || 0);
    const total = pricePerUnit * quantity;
    
    if (quantity && pricePerUnit) {
        container.innerHTML = `
            <div class="row">
                <div class="col-6">
                    <strong>Quantity:</strong> ${quantity} units
                </div>
                <div class="col-6">
                    <strong>Price per unit:</strong> ${FarmLink.formatCurrency(pricePerUnit)}
                </div>
                <div class="col-12 mt-2">
                    <strong class="text-success">Total Amount: ${FarmLink.formatCurrency(total)}</strong>
                </div>
            </div>
        `;
        container.style.display = 'block';
    } else {
        container.style.display = 'none';
    }
};

HTMLInputElement.prototype.showImagePreview = function(url, container) {
    // Create image element
    const img = document.createElement('img');
    img.src = url;
    img.className = 'img-thumbnail';
    img.style.maxWidth = '200px';
    img.style.maxHeight = '150px';
    
    // Handle load success
    img.onload = function() {
        container.innerHTML = `
            <div class="d-flex align-items-center">
                <img src="${url}" class="img-thumbnail me-2" style="width: 60px; height: 60px; object-fit: cover;">
                <span class="text-success"><i class="fas fa-check me-1"></i>Image loaded successfully</span>
            </div>
        `;
        container.style.display = 'block';
    };
    
    // Handle load error
    img.onerror = function() {
        container.innerHTML = `
            <div class="text-danger">
                <i class="fas fa-times me-1"></i>Invalid image URL or image cannot be loaded
            </div>
        `;
        container.style.display = 'block';
    };
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    FarmLink.init();
});

// Additional event listeners for specific pages
window.addEventListener('load', function() {
    // Marketplace page enhancements
    if (window.location.pathname.includes('/marketplace')) {
        // Add price range sliders if price inputs exist
        const minPriceInput = document.querySelector('input[name="min_price"]');
        const maxPriceInput = document.querySelector('input[name="max_price"]');
        
        if (minPriceInput && maxPriceInput) {
            // Add price range validation
            minPriceInput.addEventListener('change', function() {
                const maxPrice = parseFloat(maxPriceInput.value);
                const minPrice = parseFloat(this.value);
                
                if (maxPrice && minPrice > maxPrice) {
                    maxPriceInput.value = minPrice;
                }
            });
            
            maxPriceInput.addEventListener('change', function() {
                const minPrice = parseFloat(minPriceInput.value);
                const maxPrice = parseFloat(this.value);
                
                if (minPrice && maxPrice < minPrice) {
                    minPriceInput.value = maxPrice;
                }
            });
        }
    }
    
    // Dashboard page enhancements
    if (window.location.pathname.includes('/dashboard')) {
        // Add auto-refresh for certain widgets every 5 minutes
        setInterval(function() {
            // Refresh weather widget if present
            const weatherWidget = document.querySelector('.weather-widget');
            if (weatherWidget) {
                // Add subtle indication of refresh
                weatherWidget.style.opacity = '0.8';
                setTimeout(() => {
                    weatherWidget.style.opacity = '1';
                }, 500);
            }
        }, 5 * 60 * 1000); // 5 minutes
    }
    
    // Order form enhancements
    if (window.location.pathname.includes('order') || document.querySelector('form[action*="order"]')) {
        // Get price from page data
        const priceElement = document.querySelector('[data-price], .text-success.fw-bold');
        if (priceElement) {
            const priceText = priceElement.textContent.replace(/[₹,]/g, '');
            const price = parseFloat(priceText);
            
            if (price) {
                const form = document.querySelector('form[action*="order"]');
                if (form) {
                    form.dataset.pricePerUnit = price;
                }
            }
        }
    }
});

// Messaging system for real-time communication
const MessagingSystem = {
    init: function() {
        this.initWebSocket();
        this.setupEventHandlers();
        this.setupNotifications();
        this.typingTimeouts = new Map();
    },

    initWebSocket: function() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/messages`;
        
        this.socket = new WebSocket(wsUrl);
        this.socket.onopen = () => console.log('WebSocket connected');
        this.socket.onclose = () => {
            console.log('WebSocket disconnected, attempting to reconnect...');
            setTimeout(() => this.initWebSocket(), 3000);
        };
        
        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            switch(data.type) {
                case 'new_message':
                    this.handleNewMessage(data.message);
                    this.showNotification(data.message);
                    break;
                case 'typing':
                    this.handleTypingIndicator(data.user);
                    break;
                case 'read':
                    this.updateMessageReadStatus(data.messageId);
                    break;
            }
        };
    },

    setupNotifications: function() {
        if ('Notification' in window) {
            Notification.requestPermission();
        }
    },

    handleNewMessage: function(message) {
        const messageList = document.querySelector('.message-list');
        if (messageList) {
            const messageHtml = this.createMessageElement(message);
            messageList.insertAdjacentHTML('beforeend', messageHtml);
            this.scrollToBottom();
            
            // Play notification sound
            const audio = new Audio('/static/sounds/message.mp3');
            audio.play().catch(e => console.log('Audio play failed:', e));
        }
        
        this.updateUnreadCount();
        this.updateMessageBadge();
    },

    showNotification: function(message) {
        if (Notification.permission === 'granted' && document.hidden) {
            const notification = new Notification('New Message', {
                body: `${message.sender}: ${message.content.substring(0, 50)}...`,
                icon: '/static/img/logo.png'
            });
            
            notification.onclick = () => {
                window.focus();
                notification.close();
            };
        }
    },

    handleTypingIndicator: function(user) {
        const typingIndicator = document.querySelector('.typing-indicator');
        if (!typingIndicator) return;

        // Clear existing timeout for this user
        if (this.typingTimeouts.has(user.id)) {
            clearTimeout(this.typingTimeouts.get(user.id));
        }

        // Show typing indicator
        typingIndicator.textContent = `${user.name} is typing...`;
        typingIndicator.classList.remove('d-none');

        // Set timeout to hide indicator after 2 seconds
        const timeout = setTimeout(() => {
            typingIndicator.classList.add('d-none');
            this.typingTimeouts.delete(user.id);
        }, 2000);

        this.typingTimeouts.set(user.id, timeout);
    },

    sendMessage: function(messageData) {
        if (this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                type: 'message',
                data: messageData
            }));
            return true;
        }
        return false;
    },

    sendTypingIndicator: function() {
        if (this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                type: 'typing'
            }));
        }
    },

    setupEventHandlers: function() {
        const messageForm = document.getElementById('messageForm');
        if (messageForm) {
            const textArea = messageForm.querySelector('textarea[name="content"]');
            if (textArea) {
                // Add typing indicator
                let typingTimeout;
                textArea.addEventListener('input', () => {
                    if (typingTimeout) clearTimeout(typingTimeout);
                    this.sendTypingIndicator();
                    typingTimeout = setTimeout(() => {
                        typingTimeout = null;
                    }, 1000);
                });
            }

            messageForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(messageForm);
                this.sendMessage({
                    recipient_id: formData.get('recipient_id'),
                    subject: formData.get('subject'),
                    content: formData.get('content')
                });
            });
        }
    }
};

// Download Receipt Function
function downloadReceipt(paymentId) {
    try {
        const modal = document.getElementById(`receiptModal${paymentId}`);
        if (!modal) {
            throw new Error('Receipt modal not found');
        }
        
        const receiptContent = modal.querySelector('.receipt-content');
        if (!receiptContent) {
            throw new Error('Receipt content not found');
        }
        
        const clonedContent = receiptContent.cloneNode(true);
        
        // Create a new window for the receipt
        const receiptWindow = window.open('', '_blank', 'width=600,height=800,scrollbars=yes');
        
        if (!receiptWindow) {
            alert('Please allow popups to download receipts');
            return;
        }
        
        receiptWindow.document.write(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>Payment Receipt - FarmLink AI</title>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    * { box-sizing: border-box; }
                    body { 
                        font-family: Arial, sans-serif; 
                        padding: 20px; 
                        max-width: 600px; 
                        margin: 0 auto;
                        background-color: white;
                    }
                    .receipt-content {
                        font-family: 'Courier New', monospace;
                        background-color: #f8f9fa;
                        padding: 1.5rem;
                        border-radius: 8px;
                        border: 2px solid #dee2e6;
                    }
                    .receipt-header {
                        text-align: center;
                        border-bottom: 2px dashed #dee2e6;
                        padding-bottom: 1rem;
                        margin-bottom: 1rem;
                    }
                    .receipt-header h5 {
                        margin: 0.5rem 0;
                        font-size: 1.2rem;
                    }
                    .receipt-row {
                        display: flex;
                        justify-content: space-between;
                        padding: 0.5rem 0;
                        border-bottom: 1px dotted #dee2e6;
                    }
                    .receipt-row:last-child {
                        border-bottom: none;
                        font-weight: bold;
                        border-top: 2px solid #dee2e6;
                        margin-top: 1rem;
                        padding-top: 1rem;
                    }
                    .badge {
                        padding: 0.25em 0.5em;
                        font-size: 0.75em;
                        border-radius: 0.375rem;
                        display: inline-block;
                    }
                    .bg-success { background-color: #198754; color: white; }
                    .bg-warning { background-color: #ffc107; color: black; }
                    .bg-danger { background-color: #dc3545; color: white; }
                    .bg-info { background-color: #0dcaf0; color: black; }
                    .bg-secondary { background-color: #6c757d; color: white; }
                    .action-buttons {
                        text-align: center;
                        margin-top: 20px;
                        padding: 20px;
                        border-top: 1px solid #dee2e6;
                    }
                    .btn {
                        padding: 10px 20px;
                        border: none;
                        border-radius: 4px;
                        cursor: pointer;
                        margin: 0 5px;
                        font-size: 14px;
                    }
                    .btn-primary { background: #007bff; color: white; }
                    .btn-secondary { background: #6c757d; color: white; }
                    .btn:hover { opacity: 0.8; }
                    @media print {
                        body { margin: 0; padding: 10px; }
                        .no-print, .action-buttons { display: none !important; }
                        .receipt-content {
                            background-color: white !important;
                            border: 2px solid #000 !important;
                        }
                        .receipt-header { border-bottom: 2px solid #000 !important; }
                        .receipt-row { border-bottom: 1px solid #000 !important; }
                        .receipt-row:last-child { border-top: 2px solid #000 !important; }
                        .badge {
                            border: 1px solid #000 !important;
                            color: #000 !important;
                            background-color: transparent !important;
                        }
                    }
                </style>
            </head>
            <body>
                ${clonedContent.outerHTML}
                <div class="action-buttons no-print">
                    <button onclick="window.print()" class="btn btn-primary">
                        🖨️ Print Receipt
                    </button>
                    <button onclick="window.close()" class="btn btn-secondary">
                        ❌ Close
                    </button>
                </div>
                <script>
                    // Focus window and optionally auto-print
                    window.focus();
                    
                    // Uncomment the line below for auto-print
                    // setTimeout(() => window.print(), 1000);
                </script>
            </body>
            </html>
        `);
        
        receiptWindow.document.close();
        
    } catch (error) {
        console.error('Error downloading receipt:', error);
        alert('Error generating receipt: ' + error.message + '. Please try again.');
    }
}

// Validate Receipt Data
function validateReceiptData(paymentId) {
    const modal = document.getElementById(`receiptModal${paymentId}`);
    if (!modal) return false;
    
    const requiredElements = [
        '.receipt-content',
        '.receipt-header', 
        '.receipt-row'
    ];
    
    return requiredElements.every(selector => modal.querySelector(selector));
}

// Export for use in other scripts if needed
window.FarmLink = FarmLink;

// Initialize FarmLink when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
        FarmLink.init();
    });
} else {
    // DOM is already loaded
    FarmLink.init();
}
