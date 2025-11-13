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

            for (let key in elements) {
                  if (!elements[key]) {
                        console.error('Required element not found:', key);
                        return;
                  }
            }

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
                  const file = e.target.files[0];
                  if (file) handleFileSelect(file);
            });

            function handleFileSelect(file) {
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
                        originalImageData = readerEvent.target.result;
                        elements.cropImage.src = originalImageData;

                        if (cropper) {
                              cropper.destroy();
                              cropper = null;
                        }

                        setTimeout(function () {
                              openModal();
                              updateImageInfo(file);
                              showLoading(false);
                        }, 100);
                  };

                  reader.onerror = function () {
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
                  elements.modalEl.classList.add('show', 'fade');
                  elements.modalEl.style.display = 'block';
                  elements.modalEl.setAttribute('aria-modal', 'true');
                  elements.modalEl.setAttribute('role', 'dialog');
                  elements.modalEl.removeAttribute('aria-hidden');

                  let backdrop = document.getElementById('cropModalBackdrop');
                  if (!backdrop) {
                        backdrop = document.createElement('div');
                        backdrop.className = 'modal-backdrop fade show';
                        backdrop.id = 'cropModalBackdrop';
                        document.body.appendChild(backdrop);
                  }

                  document.body.classList.add('modal-open');

                  setTimeout(function () {
                        if (typeof bootstrap !== 'undefined' && bootstrap.Modal && !modalInstance) {
                              modalInstance = new bootstrap.Modal(elements.modalEl, {
                                    backdrop: 'static',
                                    keyboard: false
                              });
                        }
                  }, 100);
            }

            function closeModal() {
                  elements.modalEl.classList.remove('show');
                  elements.modalEl.style.display = 'none';
                  elements.modalEl.setAttribute('aria-hidden', 'true');
                  elements.modalEl.removeAttribute('aria-modal');
                  elements.modalEl.removeAttribute('role');
                  document.body.classList.remove('modal-open');

                  const backdrop = document.getElementById('cropModalBackdrop');
                  if (backdrop) backdrop.remove();

                  if (modalInstance) {
                        try {
                              modalInstance.hide();
                        } catch (e) { }
                  }

                  resetFiltersUI();
            }

            elements.modalEl.addEventListener('shown.bs.modal', function () {
                  if (cropper) {
                        cropper.destroy();
                        cropper = null;
                  }

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
                                    ready: function () {
                                          saveHistory();
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
                  if (!cropper) return;
                  const imageElement = cropper.getImageElement();
                  imageElement.style.filter = `
                brightness(${filters.brightness}%)
                contrast(${filters.contrast}%)
                saturate(${filters.saturation}%)
                blur(${filters.blur}px)
            `;
            }

            const brightnessSlider = document.getElementById('brightness');
            if (brightnessSlider) {
                  brightnessSlider.oninput = function () {
                        filters.brightness = this.value;
                        document.getElementById('brightnessValue').textContent = this.value;
                        applyFilters();
                  };
            }

            const contrastSlider = document.getElementById('contrast');
            if (contrastSlider) {
                  contrastSlider.oninput = function () {
                        filters.contrast = this.value;
                        document.getElementById('contrastValue').textContent = this.value;
                        applyFilters();
                  };
            }

            const saturationSlider = document.getElementById('saturation');
            if (saturationSlider) {
                  saturationSlider.oninput = function () {
                        filters.saturation = this.value;
                        document.getElementById('saturationValue').textContent = this.value;
                        applyFilters();
                  };
            }

            const blurSlider = document.getElementById('blur');
            if (blurSlider) {
                  blurSlider.oninput = function () {
                        filters.blur = this.value;
                        document.getElementById('blurValue').textContent = this.value;
                        applyFilters();
                  };
            }

            const resetFiltersBtn = document.getElementById('resetFilters');
            if (resetFiltersBtn) {
                  resetFiltersBtn.onclick = function () {
                        resetFiltersUI();
                        applyFilters();
                  };
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
                        if (!cropper) {
                              alert('Crop tool not ready. Please wait a moment and try again.');
                              return;
                        }

                        if (!currentFile) {
                              alert('No image file selected.');
                              return;
                        }

                        showLoading(true);

                        try {
                              const sizeSelect = document.getElementById('sizeSelect');
                              const qualitySelect = document.getElementById('qualitySelect');
                              const size = sizeSelect ? parseInt(sizeSelect.value) : 400;
                              const quality = qualitySelect ? parseFloat(qualitySelect.value) : 0.92;

                              const canvas = cropper.getCroppedCanvas({
                                    width: size,
                                    height: size,
                                    imageSmoothingEnabled: true,
                                    imageSmoothingQuality: 'high'
                              });

                              if (!canvas) {
                                    throw new Error('Failed to create canvas');
                              }

                              // Apply filters to canvas
                              const ctx = canvas.getContext('2d');
                              ctx.filter = `
                        brightness(${filters.brightness}%)
                        contrast(${filters.contrast}%)
                        saturate(${filters.saturation}%)
                        blur(${filters.blur}px)
                    `;
                              ctx.drawImage(canvas, 0, 0);

                              canvas.toBlob(function (blob) {
                                    if (!blob) {
                                          alert('Error processing image. Please try again.');
                                          showLoading(false);
                                          return;
                                    }

                                    const previewUrl = URL.createObjectURL(blob);
                                    elements.preview.src = '';

                                    setTimeout(function () {
                                          elements.preview.src = previewUrl;
                                    }, 50);

                                    try {
                                          const file = new File([blob], currentFile.name, {
                                                type: currentFile.type,
                                                lastModified: Date.now()
                                          });

                                          const dt = new DataTransfer();
                                          dt.items.add(file);
                                          elements.input.files = dt.files;
                                    } catch (fileError) {
                                          console.error('Error updating file input:', fileError);
                                    }

                                    const newSizeKB = (blob.size / 1024).toFixed(2);
                                    elements.fileName.innerHTML = `
                            <i class="fas fa-check-circle text-success me-1"></i>
                            <strong>Processed:</strong> ${currentFile.name} 
                            <span class="badge bg-success">✓ ${size}x${size}px • ${newSizeKB} KB</span>
                        `;

                                    showLoading(false);
                                    setTimeout(function () {
                                          closeModal();
                                    }, 200);

                              }, currentFile.type, quality);

                        } catch (error) {
                              console.error('Error during crop:', error);
                              alert('Error cropping image. Please try again.');
                              showLoading(false);
                        }
                  };
            }
      }
})();
