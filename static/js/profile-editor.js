(function () {
      'use strict';

      function waitForDependencies(callback) {
            const checkInterval = setInterval(function () {
                  if (typeof bootstrap !== 'undefined' && bootstrap.Modal && typeof Cropper !== 'undefined') {
                        clearInterval(checkInterval);
                        callback();
                  }
            }, 100);
      }

      function init() {
            waitForDependencies(initProfileUpload);
      }

      if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', init);
      } else {
            init();
      }

      function initProfileUpload() {
            console.log('Initializing profile upload...');
            
            const elements = {
                  input: document.getElementById('profile_picture'),
                  preview: document.getElementById('profileImagePreview'),
                  fileName: document.getElementById('imageFileName'),
                  modalEl: document.getElementById('cropModal'),
                  cropImage: document.getElementById('cropImage'),
                  imageInfo: document.getElementById('imageInfo'),
                  loadingOverlay: document.getElementById('loadingOverlay'),
                  dropZone: document.getElementById('dropZone')
            };

            // Check for missing elements
            for (let key in elements) {
                  if (!elements[key]) {
                        console.error('Required element not found:', key);
                        return;
                  }
            }
            
            console.log('All required elements found. Setting up event listeners...');

            let cropper = null;
            let currentFile = null;
            let modalInstance = null;
            let originalImageData = null;
            let history = [];
            let historyIndex = -1;
            let filters = {
                  brightness: 100,
                  contrast: 100,
                  saturation: 100,
                  blur: 0
            };
            let scaleX = 1;
            let scaleY = 1;

            // Drag & Drop functionality
            const dropZoneEl = elements.dropZone;
            let dragCounter = 0;

            document.addEventListener('dragenter', function (e) {
                  e.preventDefault();
                  dragCounter++;
                  if (dragCounter === 1) {
                        dropZoneEl.classList.remove('d-none');
                  }
            });

            document.addEventListener('dragleave', function (e) {
                  e.preventDefault();
                  dragCounter--;
                  if (dragCounter === 0) {
                        dropZoneEl.classList.add('d-none');
                  }
            });

            document.addEventListener('dragover', function (e) {
                  e.preventDefault();
            });

            document.addEventListener('drop', function (e) {
                  e.preventDefault();
                  dragCounter = 0;
                  dropZoneEl.classList.add('d-none');

                  const files = e.dataTransfer.files;
                  if (files.length > 0) {
                        handleFileSelect(files[0]);
                  }
            });

            // File input change
            elements.input.addEventListener('change', function (e) {
                  console.log('File input changed');
                  const file = e.target.files[0];
                  if (file) {
                        console.log('File selected:', file.name, file.size, file.type);
                        handleFileSelect(file);
                  }
            });

            function handleFileSelect(file) {
                  console.log('handleFileSelect called with:', file.name);
                  
                  if (file.size > 5 * 1024 * 1024) {
                        alert('File size must be less than 5MB');
                        return;
                  }

                  if (!file.type.match(/^image\/(jpeg|jpg|png|gif|webp)$/i)) {
                        alert('Please select JPG, PNG, GIF or WebP image');
                        return;
                  }

                  currentFile = file;
                  elements.fileName.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Loading image...';
                  showLoading(true);

                  const reader = new FileReader();
                  reader.onload = function (readerEvent) {
                        console.log('Image loaded, updating preview...');
                        originalImageData = readerEvent.target.result;
                        
                        // Immediately update preview in the circular frame
                        elements.preview.src = originalImageData;
                        console.log('Preview updated');
                        
                        elements.cropImage.src = originalImageData;

                        if (cropper) {
                              cropper.destroy();
                              cropper = null;
                        }

                        setTimeout(function () {
                              console.log('Opening modal...');
                              openModal();
                              updateImageInfo(file);
                              showLoading(false);
                        }, 100);
                  };

                  reader.onerror = function () {
                        console.error('Error reading file');
                        alert('Error reading image file. Please try again.');
                        elements.fileName.innerHTML = '';
                        showLoading(false);
                  };

                  reader.readAsDataURL(file);
            }

            function showLoading(show) {
                  if (show) {
                        elements.loadingOverlay.classList.remove('d-none');
                  } else {
                        elements.loadingOverlay.classList.add('d-none');
                  }
            }

            function updateImageInfo(file) {
                  const img = new Image();
                  img.onload = function () {
                        const sizeKB = (file.size / 1024).toFixed(2);
                        elements.imageInfo.innerHTML = `
                    <i class="fas fa-image me-1"></i>${img.width}x${img.height}px • 
                    <i class="fas fa-file me-1"></i>${sizeKB} KB • 
                    <i class="fas fa-file-image me-1"></i>${file.type.split('/')[1].toUpperCase()}
                `;
                  };
                  img.src = originalImageData;
            }

            function openModal() {
                  console.log('openModal called');
                  // Show modal using Bootstrap's native method
                  if (!modalInstance) {
                        console.log('Creating new modal instance');
                        modalInstance = new bootstrap.Modal(elements.modalEl, {
                              backdrop: 'static',
                              keyboard: false
                        });
                  }
                  console.log('Showing modal...');
                  modalInstance.show();
                  console.log('Modal show() called');
            }

            function closeModal() {
                  if (modalInstance) {
                        modalInstance.hide();
                  }
                  resetFiltersUI();
            }

            elements.modalEl.addEventListener('shown.bs.modal', function () {
                  if (cropper) {
                        cropper.destroy();
                        cropper = null;
                  }
                  
                  // Reset filters to default and update UI
                  filters = { brightness: 100, contrast: 100, saturation: 100, blur: 0 };
                  
                  // Update slider values
                  const brightnessEl = document.getElementById('brightness');
                  const contrastEl = document.getElementById('contrast');
                  const saturationEl = document.getElementById('saturation');
                  const blurEl = document.getElementById('blur');
                  
                  if (brightnessEl) brightnessEl.value = 100;
                  if (contrastEl) contrastEl.value = 100;
                  if (saturationEl) saturationEl.value = 100;
                  if (blurEl) blurEl.value = 0;
                  
                  // Update value displays
                  const brightnessVal = document.getElementById('brightnessValue');
                  const contrastVal = document.getElementById('contrastValue');
                  const saturationVal = document.getElementById('saturationValue');
                  const blurVal = document.getElementById('blurValue');
                  
                  if (brightnessVal) brightnessVal.textContent = '100';
                  if (contrastVal) contrastVal.textContent = '100';
                  if (saturationVal) saturationVal.textContent = '100';
                  if (blurVal) blurVal.textContent = '0';

                  setTimeout(function () {
                        try {
                              cropper = new Cropper(elements.cropImage, {
                                    aspectRatio: 1,
                                    viewMode: 1,
                                    dragMode: 'move',
                                    autoCropArea: 0.9,
                                    restore: false,
                                    guides: true,
                                    center: true,
                                    highlight: true,
                                    cropBoxMovable: true,
                                    cropBoxResizable: true,
                                    responsive: true,
                                    checkOrientation: true,
                                    zoomOnWheel: true,
                                    zoomOnTouch: true,
                                    toggleDragModeOnDblclick: false,
                                    ready: function () {
                                          console.log('Cropper ready, initializing filters');
                                          saveHistory();
                                          // Apply initial filters after a short delay to ensure DOM is ready
                                          setTimeout(function() {
                                                applyFilters();
                                          }, 100);
                                    }
                              });
                        } catch (error) {
                              console.error('Error initializing cropper:', error);
                              alert('Error initializing crop tool. Please try again.');
                        }
                  }, 100);
            });

            elements.modalEl.addEventListener('hidden.bs.modal', function () {
                  if (cropper) {
                        cropper.destroy();
                        cropper = null;
                  }
                  elements.fileName.innerHTML = '';
                  history = [];
                  historyIndex = -1;
                  scaleX = 1;
                  scaleY = 1;
                  
                  // Reset filters
                  resetFiltersUI();

                  const backdrop = document.getElementById('cropModalBackdrop');
                  if (backdrop) backdrop.remove();
            });

            const closeButtons = elements.modalEl.querySelectorAll('[data-bs-dismiss="modal"], .btn-close');
            closeButtons.forEach(function (btn) {
                  btn.addEventListener('click', function (e) {
                        e.preventDefault();
                        closeModal();
                  });
            });

            // History Management
            function saveHistory() {
                  if (!cropper) return;
                  const data = cropper.getData();
                  history = history.slice(0, historyIndex + 1);
                  history.push(JSON.parse(JSON.stringify(data)));
                  historyIndex++;
                  updateHistoryButtons();
            }

            function updateHistoryButtons() {
                  const undoBtn = document.getElementById('undoBtn');
                  const redoBtn = document.getElementById('redoBtn');
                  if (undoBtn) undoBtn.disabled = historyIndex <= 0;
                  if (redoBtn) redoBtn.disabled = historyIndex >= history.length - 1;
            }

            const undoBtn = document.getElementById('undoBtn');
            if (undoBtn) {
                  undoBtn.onclick = function () {
                        if (historyIndex > 0) {
                              historyIndex--;
                              cropper.setData(history[historyIndex]);
                              updateHistoryButtons();
                        }
                  };
            }

            const redoBtn = document.getElementById('redoBtn');
            if (redoBtn) {
                  redoBtn.onclick = function () {
                        if (historyIndex < history.length - 1) {
                              historyIndex++;
                              cropper.setData(history[historyIndex]);
                              updateHistoryButtons();
                        }
                  };
            }

            // Transform Controls
            const zoomInBtn = document.getElementById('zoomIn');
            if (zoomInBtn) {
                  zoomInBtn.onclick = function () {
                        if (cropper) {
                              cropper.zoom(0.1);
                              saveHistory();
                        }
                  };
            }

            const zoomOutBtn = document.getElementById('zoomOut');
            if (zoomOutBtn) {
                  zoomOutBtn.onclick = function () {
                        if (cropper) {
                              cropper.zoom(-0.1);
                              saveHistory();
                        }
                  };
            }

            const rotateLeftBtn = document.getElementById('rotateLeft');
            if (rotateLeftBtn) {
                  rotateLeftBtn.onclick = function () {
                        if (cropper) {
                              cropper.rotate(-45);
                              saveHistory();
                        }
                  };
            }

            const rotateRightBtn = document.getElementById('rotateRight');
            if (rotateRightBtn) {
                  rotateRightBtn.onclick = function () {
                        if (cropper) {
                              cropper.rotate(45);
                              saveHistory();
                        }
                  };
            }

            const flipHBtn = document.getElementById('flipH');
            if (flipHBtn) {
                  flipHBtn.onclick = function () {
                        if (cropper) {
                              scaleX = -scaleX;
                              cropper.scaleX(scaleX);
                              saveHistory();
                        }
                  };
            }

            const flipVBtn = document.getElementById('flipV');
            if (flipVBtn) {
                  flipVBtn.onclick = function () {
                        if (cropper) {
                              scaleY = -scaleY;
                              cropper.scaleY(scaleY);
                              saveHistory();
                        }
                  };
            }

            // Aspect Ratio Controls
            document.querySelectorAll('.aspect-btn').forEach(function (btn) {
                  btn.onclick = function () {
                        document.querySelectorAll('.aspect-btn').forEach(b => b.classList.remove('active'));
                        this.classList.add('active');

                        const ratio = this.dataset.ratio;
                        if (cropper) {
                              if (ratio === 'free') {
                                    cropper.setAspectRatio(NaN);
                              } else {
                                    cropper.setAspectRatio(parseFloat(ratio));
                              }
                              saveHistory();
                        }
                  };
            });

            // Filter Controls
            function applyFilters() {
                  if (!cropper) {
                        console.log('Cropper not initialized, cannot apply filters');
                        return;
                  }
                  
                  // Apply filters to the cropper container's image
                  const cropperContainer = document.querySelector('.cropper-container');
                  if (cropperContainer) {
                        const cropperCanvas = cropperContainer.querySelector('.cropper-canvas img');
                        if (cropperCanvas) {
                              cropperCanvas.style.filter = `
                                    brightness(${filters.brightness}%)
                                    contrast(${filters.contrast}%)
                                    saturate(${filters.saturation}%)
                                    blur(${filters.blur}px)
                              `;
                              console.log('Filters applied to cropper canvas:', filters);
                        }
                  }
                  
                  // Also apply to the original image element as backup
                  if (elements.cropImage) {
                        elements.cropImage.style.filter = `
                              brightness(${filters.brightness}%)
                              contrast(${filters.contrast}%)
                              saturate(${filters.saturation}%)
                              blur(${filters.blur}px)
                        `;
                  }
            }

            const brightnessSlider = document.getElementById('brightness');
            if (brightnessSlider) {
                  brightnessSlider.addEventListener('input', function () {
                        filters.brightness = this.value;
                        const valueEl = document.getElementById('brightnessValue');
                        if (valueEl) valueEl.textContent = this.value;
                        console.log('Brightness changed to:', this.value);
                        applyFilters();
                  });
            }

            const contrastSlider = document.getElementById('contrast');
            if (contrastSlider) {
                  contrastSlider.addEventListener('input', function () {
                        filters.contrast = this.value;
                        const valueEl = document.getElementById('contrastValue');
                        if (valueEl) valueEl.textContent = this.value;
                        console.log('Contrast changed to:', this.value);
                        applyFilters();
                  });
            }

            const saturationSlider = document.getElementById('saturation');
            if (saturationSlider) {
                  saturationSlider.addEventListener('input', function () {
                        filters.saturation = this.value;
                        const valueEl = document.getElementById('saturationValue');
                        if (valueEl) valueEl.textContent = this.value;
                        console.log('Saturation changed to:', this.value);
                        applyFilters();
                  });
            }

            const blurSlider = document.getElementById('blur');
            if (blurSlider) {
                  blurSlider.addEventListener('input', function () {
                        filters.blur = this.value;
                        const valueEl = document.getElementById('blurValue');
                        if (valueEl) valueEl.textContent = this.value;
                        console.log('Blur changed to:', this.value);
                        applyFilters();
                  });
            }

            const resetFiltersBtn = document.getElementById('resetFilters');
            if (resetFiltersBtn) {
                  resetFiltersBtn.addEventListener('click', function () {
                        resetFiltersUI();
                        applyFilters();
                  });
            }

            function resetFiltersUI() {
                  filters = { brightness: 100, contrast: 100, saturation: 100, blur: 0 };
                  const brightnessEl = document.getElementById('brightness');
                  const contrastEl = document.getElementById('contrast');
                  const saturationEl = document.getElementById('saturation');
                  const blurEl = document.getElementById('blur');

                  if (brightnessEl) brightnessEl.value = 100;
                  if (contrastEl) contrastEl.value = 100;
                  if (saturationEl) saturationEl.value = 100;
                  if (blurEl) blurEl.value = 0;

                  const brightnessVal = document.getElementById('brightnessValue');
                  const contrastVal = document.getElementById('contrastValue');
                  const saturationVal = document.getElementById('saturationValue');
                  const blurVal = document.getElementById('blurValue');

                  if (brightnessVal) brightnessVal.textContent = '100';
                  if (contrastVal) contrastVal.textContent = '100';
                  if (saturationVal) saturationVal.textContent = '100';
                  if (blurVal) blurVal.textContent = '0';
                  
                  // Clear any applied filters
                  if (elements.cropImage) {
                        elements.cropImage.style.filter = '';
                  }
            }

            const resetCropBtn = document.getElementById('resetCrop');
            if (resetCropBtn) {
                  resetCropBtn.onclick = function () {
                        if (cropper) {
                              cropper.reset();
                              scaleX = 1;
                              scaleY = 1;
                              resetFiltersUI();
                              applyFilters();
                              history = [];
                              historyIndex = -1;
                              saveHistory();
                        }
                  };
            }

            // Compare Before/After
            let comparing = false;
            const compareBtn = document.getElementById('compareBtn');
            if (compareBtn) {
                  compareBtn.onclick = function () {
                        if (!cropper) return;
                        comparing = !comparing;

                        if (comparing) {
                              this.innerHTML = '<i class="fas fa-eye me-1"></i>Show After';
                              elements.cropImage.src = originalImageData;
                              if (cropper) cropper.destroy();
                        } else {
                              this.innerHTML = '<i class="fas fa-exchange-alt me-1"></i>Compare Before/After';
                              elements.cropImage.src = originalImageData;
                              setTimeout(() => {
                                    cropper = new Cropper(elements.cropImage, {
                                          aspectRatio: 1,
                                          viewMode: 1,
                                          dragMode: 'move',
                                          autoCropArea: 0.9
                                    });
                                    applyFilters();
                              }, 100);
                        }
                  };
            }

            // Keyboard Shortcuts
            document.addEventListener('keydown', function (e) {
                  if (!elements.modalEl.classList.contains('show')) return;

                  if (e.ctrlKey && e.key === 'z') {
                        e.preventDefault();
                        if (undoBtn) undoBtn.click();
                  } else if (e.ctrlKey && e.key === 'y') {
                        e.preventDefault();
                        if (redoBtn) redoBtn.click();
                  } else if (e.key === '+' || e.key === '=') {
                        e.preventDefault();
                        if (zoomInBtn) zoomInBtn.click();
                  } else if (e.key === '-') {
                        e.preventDefault();
                        if (zoomOutBtn) zoomOutBtn.click();
                  } else if (e.key.toLowerCase() === 'l') {
                        e.preventDefault();
                        if (rotateLeftBtn) rotateLeftBtn.click();
                  } else if (e.key.toLowerCase() === 'r') {
                        e.preventDefault();
                        if (rotateRightBtn) rotateRightBtn.click();
                  } else if (e.key.toLowerCase() === 'h') {
                        e.preventDefault();
                        if (flipHBtn) flipHBtn.click();
                  } else if (e.key.toLowerCase() === 'v') {
                        e.preventDefault();
                        if (flipVBtn) flipVBtn.click();
                  }
            });

            // Add smooth scroll animations
            document.querySelectorAll('a[href^="#"]').forEach(anchor => {
                  anchor.addEventListener('click', function (e) {
                        e.preventDefault();
                        const target = document.querySelector(this.getAttribute('href'));
                        if (target) {
                              target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }
                  });
            });

            // Add loading animation to form submit
            const form = document.querySelector('form[method="POST"]');
            if (form && !form.hasAttribute('data-listener-added')) {
                  form.setAttribute('data-listener-added', 'true');
                  form.addEventListener('submit', function (e) {
                        const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
                        if (submitBtn && !submitBtn.disabled) {
                              submitBtn.disabled = true;
                              const originalText = submitBtn.innerHTML;
                              submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Saving...';

                              // Re-enable after 5 seconds as fallback
                              setTimeout(() => {
                                    submitBtn.disabled = false;
                                    submitBtn.innerHTML = originalText;
                              }, 5000);
                        }
                  });
            }

            // Add hover effects to cards
            document.querySelectorAll('.card').forEach(card => {
                  card.addEventListener('mouseenter', function () {
                        this.style.transform = 'translateY(-5px)';
                  });
                  card.addEventListener('mouseleave', function () {
                        this.style.transform = 'translateY(0)';
                  });
            });

            // Add ripple effect to buttons
            document.querySelectorAll('.btn').forEach(button => {
                  button.addEventListener('click', function (e) {
                        const ripple = document.createElement('span');
                        const rect = this.getBoundingClientRect();
                        const size = Math.max(rect.width, rect.height);
                        const x = e.clientX - rect.left - size / 2;
                        const y = e.clientY - rect.top - size / 2;

                        ripple.style.width = ripple.style.height = size + 'px';
                        ripple.style.left = x + 'px';
                        ripple.style.top = y + 'px';
                        ripple.classList.add('ripple-effect');

                        this.appendChild(ripple);

                        setTimeout(() => ripple.remove(), 600);
                  });
            });

            // Add success animation to profile image after upload
            const observer = new MutationObserver(function (mutations) {
                  mutations.forEach(function (mutation) {
                        if (mutation.type === 'attributes' && mutation.attributeName === 'src') {
                              elements.preview.classList.add('success-pulse');
                              setTimeout(() => {
                                    elements.preview.classList.remove('success-pulse');
                              }, 2000);
                        }
                  });
            });

            observer.observe(elements.preview, { attributes: true });

            // Add tooltip initialization
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
                  tooltipTriggerList.map(function (tooltipTriggerEl) {
                        return new bootstrap.Tooltip(tooltipTriggerEl);
                  });
            }

            // Crop and Save
            const cropAndSaveBtn = document.getElementById('cropAndSave');
            if (cropAndSaveBtn) {
                  cropAndSaveBtn.onclick = function () {
                        console.log('Crop and Save button clicked');
                        
                        if (!cropper) {
                              console.error('Cropper not initialized');
                              alert('Crop tool not ready. Please wait a moment and try again.');
                              return;
                        }

                        if (!currentFile && !window.currentEditorFile) {
                              console.error('No current file');
                              alert('No image file selected.');
                              return;
                        }
                        
                        // Use currentFile if available, otherwise use window.currentEditorFile
                        const fileToUse = currentFile || window.currentEditorFile;

                        console.log('Starting crop process...');
                        showLoading(true);

                        try {
                              const sizeSelect = document.getElementById('sizeSelect');
                              const qualitySelect = document.getElementById('qualitySelect');
                              const size = sizeSelect ? parseInt(sizeSelect.value) : 400;
                              const quality = qualitySelect ? parseFloat(qualitySelect.value) : 0.92;

                              console.log('Crop settings:', { size, quality });

                              const canvas = cropper.getCroppedCanvas({
                                    width: size,
                                    height: size,
                                    imageSmoothingEnabled: true,
                                    imageSmoothingQuality: 'high'
                              });

                              if (!canvas) {
                                    throw new Error('Failed to create canvas');
                              }

                              console.log('Canvas created successfully');

                              canvas.toBlob(function (blob) {
                                    if (!blob) {
                                          console.error('Failed to create blob');
                                          alert('Error processing image. Please try again.');
                                          showLoading(false);
                                          return;
                                    }

                                    console.log('Blob created:', blob.size, 'bytes');

                                    // Create preview URL and update immediately
                                    const previewUrl = URL.createObjectURL(blob);
                                    console.log('Preview URL created:', previewUrl);
                                    
                                    // Force update the preview image
                                    if (elements.preview) {
                                          elements.preview.src = previewUrl;
                                          elements.preview.onload = function() {
                                                console.log('Preview image loaded successfully');
                                          };
                                          elements.preview.onerror = function() {
                                                console.error('Preview image failed to load');
                                          };
                                    } else {
                                          console.error('Preview element not found');
                                    }

                                    // Update file input
                                    try {
                                          const file = new File([blob], fileToUse.name, {
                                                type: fileToUse.type,
                                                lastModified: Date.now()
                                          });

                                          const dt = new DataTransfer();
                                          dt.items.add(file);
                                          elements.input.files = dt.files;
                                          console.log('File input updated successfully');
                                    } catch (fileError) {
                                          console.error('Error updating file input:', fileError);
                                    }

                                    const newSizeKB = (blob.size / 1024).toFixed(2);
                                    elements.fileName.innerHTML = `
                            <i class="fas fa-check-circle text-success me-1"></i>
                            <strong>Processed:</strong> ${fileToUse.name} 
                            <span class="badge bg-success">✓ ${size}x${size}px • ${newSizeKB} KB</span>
                        `;

                                    showLoading(false);
                                    
                                    // Close modal after a short delay
                                    setTimeout(function () {
                                          console.log('Closing modal...');
                                          closeModal();
                                          console.log('Modal closed, preview should be visible with src:', elements.preview.src);
                                    }, 500);

                              }, fileToUse.type, quality);

                        } catch (error) {
                              console.error('Error during crop:', error);
                              alert('Error cropping image. Please try again.');
                              showLoading(false);
                        }
                  };
            } else {
                  console.error('Crop and Save button not found');
            }
      }
})();


// Profile Picture Menu Functionality
(function() {
      'use strict';
      
      // View Profile Picture
      const viewProfilePicBtn = document.getElementById('viewProfilePic');
      if (viewProfilePicBtn) {
            viewProfilePicBtn.addEventListener('click', function(e) {
                  e.preventDefault();
                  const profileImg = document.getElementById('profileImagePreview');
                  const viewModal = new bootstrap.Modal(document.getElementById('viewProfilePicModal'));
                  const viewImage = document.getElementById('viewProfilePicImage');
                  
                  if (profileImg && viewImage) {
                        viewImage.src = profileImg.src;
                        viewModal.show();
                  }
            });
      }
      
      // Edit Profile Picture from menu - Opens editor directly with current image
      const editProfilePicBtn = document.getElementById('editProfilePic');
      if (editProfilePicBtn) {
            editProfilePicBtn.addEventListener('click', function(e) {
                  e.preventDefault();
                  
                  // Get current profile image
                  const profileImg = document.getElementById('profileImagePreview');
                  if (!profileImg) return;
                  
                  console.log('Edit Profile Pic clicked, loading current profile picture into editor...');
                  
                  // Load current image directly into editor
                  const cropImage = document.getElementById('cropImage');
                  const cropModal = document.getElementById('cropModal');
                  
                  if (cropImage && cropModal) {
                        // Set the image source
                        cropImage.src = profileImg.src;
                        
                        // Create a fake file object for tracking
                        fetch(profileImg.src)
                              .then(res => res.blob())
                              .then(blob => {
                                    window.currentEditorFile = new File([blob], 'profile-picture.jpg', { 
                                          type: blob.type || 'image/jpeg' 
                                    });
                              })
                              .catch(err => console.error('Error creating file:', err));
                        
                        // Open the crop modal directly
                        const modalInstance = new bootstrap.Modal(cropModal, {
                              backdrop: 'static',
                              keyboard: false
                        });
                        modalInstance.show();
                        
                        console.log('Photo editor opened with current profile picture');
                  }
            });
      }
      
      // Upload New Photo - Opens file manager
      const uploadNewPhotoBtn = document.getElementById('uploadNewPhoto');
      if (uploadNewPhotoBtn) {
            uploadNewPhotoBtn.addEventListener('click', function(e) {
                  e.preventDefault();
                  const fileInput = document.getElementById('profile_picture');
                  if (fileInput) {
                        fileInput.click();
                  }
            });
      }
      
      // Edit from View Modal
      const editFromViewBtn = document.getElementById('editFromView');
      if (editFromViewBtn) {
            editFromViewBtn.addEventListener('click', function(e) {
                  e.preventDefault();
                  
                  // Get current profile image
                  const profileImg = document.getElementById('profileImagePreview');
                  if (!profileImg) return;
                  
                  console.log('Edit from view clicked, loading current profile picture into editor...');
                  
                  // Close view modal first
                  const viewModal = bootstrap.Modal.getInstance(document.getElementById('viewProfilePicModal'));
                  if (viewModal) {
                        viewModal.hide();
                  }
                  
                  // Wait for modal to close, then open editor
                  setTimeout(function() {
                        // Load current image directly into editor
                        const cropImage = document.getElementById('cropImage');
                        const cropModal = document.getElementById('cropModal');
                        
                        if (cropImage && cropModal) {
                              // Set the image source
                              cropImage.src = profileImg.src;
                              
                              // Create a fake file object for tracking
                              fetch(profileImg.src)
                                    .then(res => res.blob())
                                    .then(blob => {
                                          window.currentEditorFile = new File([blob], 'profile-picture.jpg', { 
                                                type: blob.type || 'image/jpeg' 
                                          });
                                    })
                                    .catch(err => console.error('Error creating file:', err));
                              
                              // Open the crop modal directly
                              const modalInstance = new bootstrap.Modal(cropModal, {
                                    backdrop: 'static',
                                    keyboard: false
                              });
                              modalInstance.show();
                              
                              console.log('Photo editor opened with current profile picture');
                        }
                  }, 300);
            });
      }
})();


// AI Profile Insights functionality
function loadAIInsights() {
      const loadingDiv = document.getElementById('aiInsightsLoading');
      const contentDiv = document.getElementById('aiInsightsContent');
      const errorDiv = document.getElementById('aiInsightsError');
      const refreshBtn = document.getElementById('refreshInsightsBtn');

      // Check if elements exist (only on profile page)
      if (!loadingDiv || !contentDiv || !errorDiv || !refreshBtn) {
            return; // Not on profile page, skip
      }

      // Show loading state
      loadingDiv.classList.remove('d-none');
      contentDiv.classList.add('d-none');
      errorDiv.classList.add('d-none');
      refreshBtn.disabled = true;

      fetch('/profile/ai-insights')
            .then(response => response.json())
            .then(data => {
                  if (data.success && data.insights) {
                        displayAIInsights(data.insights);
                        loadingDiv.classList.add('d-none');
                        contentDiv.classList.remove('d-none');
                  } else {
                        throw new Error(data.error || 'Failed to load insights');
                  }
            })
            .catch(error => {
                  console.error('Error loading AI insights:', error);
                  loadingDiv.classList.add('d-none');
                  errorDiv.classList.remove('d-none');
                  
                  // Customize error message for quota issues
                  let errorMessage = error.message || 'Unable to load AI insights. Please try again later.';
                  if (errorMessage.includes('quota') || errorMessage.includes('exceeded')) {
                        errorMessage = 'AI service quota exceeded. The insights feature will be available again tomorrow. Thank you for your patience!';
                  }
                  
                  document.getElementById('aiInsightsErrorText').textContent = errorMessage;
            })
            .finally(() => {
                  refreshBtn.disabled = false;
            });
}

function displayAIInsights(insights) {
      try {
            // Display profile score
            const profileScoreEl = document.getElementById('profileScore');
            if (profileScoreEl) {
                  profileScoreEl.textContent = insights.profile_score || '--';
            }

            const statusBadge = document.getElementById('profileStatus');
            if (statusBadge) {
                  statusBadge.textContent = insights.profile_status || '--';

                  // Set badge color based on status
                  statusBadge.className = 'badge mt-2';
                  if (insights.profile_status === 'Excellent') {
                        statusBadge.classList.add('bg-success');
                  } else if (insights.profile_status === 'Good') {
                        statusBadge.classList.add('bg-info');
                  } else if (insights.profile_status === 'Fair') {
                        statusBadge.classList.add('bg-warning');
                  } else {
                        statusBadge.classList.add('bg-secondary');
                  }
            }

            // Display key insights
            const insightsList = document.getElementById('keyInsightsList');
            if (insightsList) {
                  insightsList.innerHTML = '';
                  if (insights.key_insights && insights.key_insights.length > 0) {
                        insights.key_insights.forEach(insight => {
                              const li = document.createElement('li');
                              li.className = 'mb-2';
                              li.innerHTML = `<i class="fas fa-check-circle text-success me-2"></i>${insight}`;
                              insightsList.appendChild(li);
                        });
                  } else {
                        insightsList.innerHTML = '<li class="text-muted">No insights available</li>';
                  }
            }

            // Display personalized message
            const messageEl = document.getElementById('personalizedMessageText');
            if (messageEl) {
                  messageEl.textContent = insights.personalized_message || 'Keep up the great work!';
            }

            // Display recommendations
            const recommendationsList = document.getElementById('recommendationsList');
            if (recommendationsList) {
                  recommendationsList.innerHTML = '';
                  if (insights.recommendations && insights.recommendations.length > 0) {
                        insights.recommendations.forEach(rec => {
                              const col = document.createElement('div');
                              col.className = 'col-md-6';

                              const priorityColor = rec.priority === 'high' ? 'danger' : rec.priority === 'medium' ? 'warning' : 'info';
                              const priorityIcon = rec.priority === 'high' ? 'exclamation-circle' : rec.priority === 'medium' ? 'star' : 'info-circle';

                              col.innerHTML = `
                        <div class="card border-${priorityColor} h-100">
                            <div class="card-body">
                                <h6 class="card-title">
                                    <i class="fas fa-${priorityIcon} text-${priorityColor} me-2"></i>${rec.title || 'Recommendation'}
                                </h6>
                                <p class="card-text small">${rec.description || ''}</p>
                                ${rec.action_url ? `<a href="${rec.action_url}" class="btn btn-sm btn-outline-${priorityColor}">Take Action</a>` : ''}
                            </div>
                        </div>
                    `;
                              recommendationsList.appendChild(col);
                        });
                  } else {
                        recommendationsList.innerHTML = '<div class="col-12"><p class="text-muted">No recommendations at this time</p></div>';
                  }
            }

            // Display next steps
            const nextStepsList = document.getElementById('nextStepsList');
            if (nextStepsList) {
                  nextStepsList.innerHTML = '';
                  if (insights.next_steps && insights.next_steps.length > 0) {
                        insights.next_steps.forEach((step, index) => {
                              const item = document.createElement('div');
                              item.className = 'list-group-item d-flex align-items-start';
                              item.innerHTML = `
                        <div class="me-3">
                            <span class="badge bg-primary rounded-circle" style="width: 30px; height: 30px; display: flex; align-items: center; justify-content: center;">
                                ${index + 1}
                            </span>
                        </div>
                        <div class="flex-grow-1">
                            <p class="mb-0">${step}</p>
                        </div>
                    `;
                              nextStepsList.appendChild(item);
                        });
                  } else {
                        nextStepsList.innerHTML = '<div class="list-group-item text-muted">No action items at this time</div>';
                  }
            }
      } catch (error) {
            console.error('Error displaying AI insights:', error);
      }
}

// Load AI insights when page loads
if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', loadAIInsights);
} else {
      loadAIInsights();
}

// Make loadAIInsights available globally for the refresh button
window.loadAIInsights = loadAIInsights;
