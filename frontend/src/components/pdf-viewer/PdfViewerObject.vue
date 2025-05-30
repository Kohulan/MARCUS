<template>
  <div class="pdf-viewer">
    <div v-if="isLoading" class="loading-container">
      <vue-feather type="loader" class="loading-icon spin"></vue-feather>
      <p>Loading PDF...</p>
    </div>

    <div v-else-if="error" class="error-container">
      <vue-feather type="alert-circle" class="error-icon"></vue-feather>
      <p>{{ error }}</p>
    </div>

    <div v-else class="pdf-container">
      <div class="pdf-controls">
        <div class="page-info">
          <div class="document-title">
            <vue-feather type="file-text" size="16" class="document-icon"></vue-feather>
            <span>PDF Document</span>
          </div>
          <div v-if="doi" class="doi-section">
            <div class="doi-info">
              <span class="doi-label">DOI:</span>
              <a :href="'https://doi.org/' + doi" target="_blank" class="doi-link" title="Open DOI in new tab">
                {{ doi }}
                <vue-feather type="external-link" size="12" class="external-icon"></vue-feather>
              </a>
              <div v-if="coconutMoleculeCount !== null" class="coconut-results-inline">
                <div class="coconut-badge"
                  :class="{ 'has-results': coconutMoleculeCount > 0, 'no-results': coconutMoleculeCount === 0 }">
                  <vue-feather type="database" size="14" class="coconut-icon"></vue-feather>
                  <span class="coconut-text">
                    {{ coconutMoleculeCount }} molecule{{ coconutMoleculeCount === 1 ? '' : 's' }} in COCONUT
                  </span>
                  <a v-if="coconutMoleculeCount > 0" :href="coconutSearchUrl" target="_blank" class="coconut-link-btn"
                    title="View results in COCONUT database">
                    <vue-feather type="arrow-right" size="12"></vue-feather>
                  </a>
                </div>
              </div>
              <div class="inline-controls">
                <button v-if="doi" class="btn btn-coconut-inline" @click="checkInCoconut" :disabled="isCheckingCoconut"
                  title="Search for molecules in COCONUT database">
                  <vue-feather :type="isCheckingCoconut ? 'loader' : 'database'" :size="14"
                    :class="{ 'spin': isCheckingCoconut }" class="btn-icon"></vue-feather>
                  <span>{{ isCheckingCoconut ? 'Searching...' : 'Check COCONUT' }}</span>
                </button>
                <button class="eye-button-inline" @click="togglePdfVisibility"
                  :class="{ 'eye-button--hide': isPdfVisible, 'eye-button--show': !isPdfVisible }"
                  :title="isPdfVisible ? 'Hide PDF' : 'Show PDF'">
                  <div class="eye-button__icon-container">
                    <vue-feather :type="isPdfVisible ? 'eye-off' : 'eye'" size="14"
                      class="eye-button__icon"></vue-feather>
                  </div>
                  <span class="eye-button__text">{{ isPdfVisible ? 'Hide PDF' : 'Show PDF' }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>


      </div>

      <div class="pdf-wrapper" ref="pdfWrapper" v-if="isPdfVisible && !showContextView">
        <PdfJsViewer v-if="pdfUrl" :pdfUrl="pdfUrl" />
      </div>
      <div v-else-if="!showContextView" class="pdf-hidden-message">
        <p>PDF is currently hidden. Click "Show PDF" to display it again.</p>
      </div>

      <!-- PDF Context Viewer -->
      <PDFContextViewer v-if="currentSegment" :segment="currentSegment" :showContextView="showContextView"
        @close="closeContextView" @notification="handleNotification" @error="handleError" />
    </div>
  </div>
</template>

<script>
import decimerService from '@/services/decimerService';
import PDFContextViewer from './PDFContextViewer.vue';
import PdfJsViewer from './PdfJsViewer.vue';
import eventBus from '@/utils/eventBus';

export default {
  name: 'PdfViewerObject',
  components: {
    PDFContextViewer,
    PdfJsViewer
  },
  props: {
    pdfUrl: {
      type: String,
      required: true
    },
    pdfFile: {
      type: Object,
      required: false
    }
  },
  data() {
    return {
      isLoading: true,
      error: null,
      isPdfVisible: true, // Track if PDF is visible or hidden
      doi: null, // Store the DOI when extracted
      showContextView: false, // Track if showing segment in context
      currentSegment: null, // Current segment to show in context
      isCheckingCoconut: false, // Track COCONUT search status
      coconutResults: null, // Store COCONUT search results
      coconutMoleculeCount: null, // Store molecule count for display
      coconutSearchUrl: null // Store COCONUT search URL
    }
  },
  watch: {
    pdfUrl: {
      immediate: true,
      handler(newUrl) {
        console.log('PDF URL changed:', newUrl)
        if (newUrl) {
          this.isLoading = true
          this.error = null

          // Add a slight delay since the load event isn't always reliable
          setTimeout(() => {
            this.isLoading = false
          }, 1500)
        }
      }
    },
    pdfFile: {
      immediate: true,
      handler(newFile) {
        if (newFile) {
          this.extractDoi(newFile);
        }
      }
    }
  },
  mounted() {
    console.log('PDF Viewer (Object) mounted, URL:', this.pdfUrl)
    // If pdfFile exists, we try to extract DOI
    if (this.pdfFile) {
      this.extractDoi(this.pdfFile);
    }

    // Listen for segment-in-context events using our custom EventBus
    eventBus.on('show-segment-in-context', this.showSegmentInContext);
  },
  beforeUnmount() {
    // Clean up event listener when component is unmounted
    eventBus.off('show-segment-in-context', this.showSegmentInContext);
  },
  methods: {
    onPdfLoaded() {
      console.log('PDF loaded via object tag')
      this.isLoading = false
    },
    onPdfError(error) {
      this.isLoading = false
      this.error = `Failed to load PDF: ${error?.message || 'Unknown error'}`
      console.error('PDF loading error:', error)
    },
    togglePdfVisibility() {
      this.isPdfVisible = !this.isPdfVisible;
    },
    async extractDoi(pdfFile) {
      try {
        const response = await decimerService.extractDoi(pdfFile);
        if (response && response.doi) {
          this.doi = response.doi;
          console.log('Extracted DOI:', this.doi);
        }
      } catch (error) {
        console.error('Error extracting DOI:', error);
        // We don't set an error state here to avoid interrupting the PDF display
      }
    },
    // New methods for handling segment in context
    showSegmentInContext(segment) {
      console.log('Showing segment in context:', segment);
      if (!segment) return;

      // Hide PDF and show context view
      this.isPdfVisible = false;
      this.currentSegment = segment;
      this.showContextView = true;

      // Emit event to notify parent components
      this.$emit('segment-context-shown', segment);
    },
    closeContextView() {
      this.showContextView = false;
      // Optional: Show PDF again when context view is closed
      this.isPdfVisible = true;

      // Emit event to notify parent components
      this.$emit('segment-context-closed');
    },
    handleNotification(notification) {
      // Forward notification to parent components
      this.$emit('notification', notification);
    },
    handleError(error) {
      // Forward error to parent components
      this.$emit('error', error);
    },
    async checkInCoconut() {
      if (!this.doi) {
        console.warn('No DOI available for COCONUT search');
        return;
      }

      this.isCheckingCoconut = true;
      this.coconutResults = null;

      try {
        // Clean the DOI (remove any URL prefixes)
        const cleanDoi = this.doi.replace(/^https?:\/\/doi\.org\//i, '');

        // Create the request payload
        const payload = {
          type: "tags",
          tagType: "citations",
          query: cleanDoi,
          limit: 20,
          sort: "desc",
          page: 1,
          offset: 0
        };

        console.log('Searching COCONUT with payload:', payload);

        // Make the POST request to COCONUT API
        const response = await fetch('https://coconut.naturalproducts.net/api/search', {
          method: 'POST',
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(payload)
        });

        if (!response.ok) {
          throw new Error(`COCONUT API request failed: ${response.status} ${response.statusText}`);
        }

        const data = await response.json();
        console.log('COCONUT API response:', data);
        console.log('Response structure:', JSON.stringify(data, null, 2));

        // Process the results
        this.coconutResults = data;

        // Count unique molecules
        const uniqueIdentifiers = new Set();
        let results = [];

        // Handle COCONUT API response structure
        if (data.data && data.data.data && Array.isArray(data.data.data)) {
          results = data.data.data;
        } else if (data.data && Array.isArray(data.data)) {
          results = data.data;
        } else if (data.results && Array.isArray(data.results)) {
          results = data.results;
        } else if (Array.isArray(data)) {
          results = data;
        }

        console.log('Processing results array:', results);
        console.log('Number of molecules in results:', results.length);

        results.forEach((result, index) => {
          console.log(`Molecule ${index + 1}:`, {
            id: result.id,
            coconut_id: result.coconut_id,
            identifier: result.identifier,
            name: result.name
          });

          if (result.id) {
            uniqueIdentifiers.add(result.id);
          } else if (result.coconut_id) {
            uniqueIdentifiers.add(result.coconut_id);
          } else if (result.identifier) {
            uniqueIdentifiers.add(result.identifier);
          }
        });

        const moleculeCount = uniqueIdentifiers.size;
        console.log('Unique molecules found:', moleculeCount);
        console.log('Unique identifiers:', Array.from(uniqueIdentifiers));

        // Create COCONUT search URL
        const coconutUrl = `https://coconut.naturalproducts.net/search?q=${encodeURIComponent(cleanDoi)}&tagType=citations&type=tags&activeTab=citations`;

        // Store the results for display
        this.coconutMoleculeCount = moleculeCount;
        this.coconutSearchUrl = coconutUrl;

        // Show results to user
        if (moleculeCount > 0) {
          // Also open the COCONUT page
          window.open(coconutUrl, '_blank');
        }

      } catch (error) {
        console.error('Error searching COCONUT:', error);
        this.$emit('notification', {
          type: 'error',
          message: `Failed to search COCONUT: ${error.message}`
        });
      } finally {
        this.isCheckingCoconut = false;
      }
    }
  }
}
</script>

<style lang="scss" scoped>
.pdf-viewer {
  display: flex;
  flex-direction: column;
  background-color: var(--color-card-bg);
  border-radius: 6px;
  box-shadow: var(--shadow-sm);
  height: 100%;
  overflow: hidden;
  position: relative;
  /* Added for absolute positioning of context viewer */

  .loading-container,
  .error-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 200px;
    padding: 1rem;
    text-align: center;

    .loading-icon,
    .error-icon {
      width: 36px;
      height: 36px;
      margin-bottom: 0.5rem;
    }

    .loading-icon {
      color: var(--color-primary);
    }

    .error-icon {
      color: var(--color-error);
    }

    p {
      color: var(--color-text-light);
      font-size: 0.9rem;
      max-width: 280px;
      margin: 0;
    }
  }

  .loading-icon.spin {
    animation: spin 1s linear infinite;
  }

  .pdf-container {
    display: flex;
    flex-direction: column;
    height: 100%;
    position: relative;
    /* Added for absolute positioning of context viewer */
  }

  .pdf-controls {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--color-border);
    background: linear-gradient(135deg, var(--color-card-bg) 0%, rgba(255, 255, 255, 0.05) 100%);
    backdrop-filter: blur(8px);

    .page-info {
      flex: 1;
      font-weight: 600;
      font-size: 0.9rem;

      .document-title {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 0.5rem;
        color: var(--color-text);

        .document-icon {
          color: var(--color-primary);
        }
      }

      .doi-section {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;

        .doi-info {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.8rem;
          flex-wrap: wrap;

          .doi-label {
            font-weight: 600;
            color: var(--color-text-light);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-size: 0.75rem;
          }

          .doi-link {
            display: flex;
            align-items: center;
            gap: 0.25rem;
            color: var(--color-primary);
            text-decoration: none;
            font-family: 'JetBrains Mono', 'Monaco', 'Consolas', monospace;
            padding: 0.25rem 0.5rem;
            background: rgba(59, 130, 246, 0.1);
            border-radius: 4px;
            transition: all 0.2s ease;
            border: 1px solid rgba(59, 130, 246, 0.2);

            .external-icon {
              opacity: 0.7;
              transition: opacity 0.2s ease;
            }

            &:hover {
              background: rgba(59, 130, 246, 0.15);
              border-color: rgba(59, 130, 246, 0.3);
              transform: translateY(-1px);
              box-shadow: 0 2px 8px rgba(59, 130, 246, 0.2);

              .external-icon {
                opacity: 1;
              }
            }
          }

          .coconut-results-inline {
            margin-left: 0.75rem;

            .coconut-badge {
              display: inline-flex;
              align-items: center;
              gap: 0.5rem;
              padding: 0.375rem 0.75rem;
              border-radius: 20px;
              font-size: 0.8rem;
              font-weight: 500;
              transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
              border: 1px solid transparent;
              backdrop-filter: blur(8px);

              &.has-results {
                background: linear-gradient(135deg, rgba(76, 175, 80, 0.15) 0%, rgba(56, 142, 60, 0.2) 100%);
                color: #2e7d32;
                border-color: rgba(76, 175, 80, 0.3);
                box-shadow: 0 2px 8px rgba(76, 175, 80, 0.2);

                .coconut-icon {
                  filter: drop-shadow(0 1px 2px rgba(46, 125, 50, 0.3));
                }

                .coconut-link-btn {
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  width: 20px;
                  height: 20px;
                  background: rgba(46, 125, 50, 0.1);
                  border: 1px solid rgba(46, 125, 50, 0.2);
                  border-radius: 50%;
                  color: #2e7d32;
                  transition: all 0.3s ease;
                  margin-left: 0.25rem;

                  &:hover {
                    background: rgba(46, 125, 50, 0.2);
                    border-color: rgba(46, 125, 50, 0.4);
                    transform: translateX(2px) scale(1.1);
                    box-shadow: 0 2px 6px rgba(46, 125, 50, 0.3);
                  }
                }

                &:hover {
                  transform: translateY(-2px);
                  box-shadow: 0 4px 12px rgba(76, 175, 80, 0.25);
                  background: linear-gradient(135deg, rgba(76, 175, 80, 0.2) 0%, rgba(56, 142, 60, 0.3) 100%);
                  border-color: rgba(76, 175, 80, 0.4);
                }
              }

              &.no-results {
                background: linear-gradient(135deg, rgba(255, 193, 7, 0.15) 0%, rgba(255, 160, 0, 0.2) 100%);
                color: #f57c00;
                border-color: rgba(255, 193, 7, 0.3);
                box-shadow: 0 2px 8px rgba(255, 193, 7, 0.2);

                .coconut-icon {
                  filter: drop-shadow(0 1px 2px rgba(245, 124, 0, 0.3));
                }

                &:hover {
                  transform: translateY(-2px);
                  box-shadow: 0 4px 12px rgba(255, 193, 7, 0.25);
                  background: linear-gradient(135deg, rgba(255, 193, 7, 0.2) 0%, rgba(255, 160, 0, 0.3) 100%);
                  border-color: rgba(255, 193, 7, 0.4);
                }
              }

              .coconut-text {
                letter-spacing: 0.02em;
                font-weight: 500;
              }
            }
          }
        }
      }

      .inline-controls {
        display: flex;
        gap: 0.75rem;
        align-items: center;
        margin-left: 0.75rem;

        .btn-coconut-inline {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.375rem 0.75rem;
          background: linear-gradient(135deg, rgba(103, 58, 183, 0.1) 0%, rgba(103, 58, 183, 0.15) 100%);
          color: #673ab7;
          border: 1px solid rgba(103, 58, 183, 0.2);
          border-radius: 20px;
          font-weight: 500;
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          box-shadow: 0 2px 4px rgba(103, 58, 183, 0.1);
          position: relative;
          overflow: hidden;
          backdrop-filter: blur(8px);

          .btn-icon {
            transition: all 0.3s ease;

            &.spin {
              animation: spin 1s linear infinite;
            }
          }

          &:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(103, 58, 183, 0.2);
            background: linear-gradient(135deg, rgba(103, 58, 183, 0.15) 0%, rgba(103, 58, 183, 0.25) 100%);
            border-color: rgba(103, 58, 183, 0.3);

            .btn-icon {
              transform: scale(1.1) rotate(5deg);
            }
          }

          &:active:not(:disabled) {
            transform: translateY(-1px);
            box-shadow: 0 2px 6px rgba(103, 58, 183, 0.15);
          }

          &:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
            background: rgba(103, 58, 183, 0.05);
            color: rgba(103, 58, 183, 0.5);
          }

          &::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.3), transparent);
            transition: left 0.6s ease;
          }

          &:hover:not(:disabled)::before {
            left: 100%;
          }
        }

        .eye-button-inline {
          position: relative;
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.375rem 0.75rem;
          border: 1px solid transparent;
          border-radius: 20px;
          cursor: pointer;
          font-weight: 500;
          font-size: 0.8rem;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          overflow: hidden;
          backdrop-filter: blur(8px);

          .eye-button__icon-container {
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.3s ease;
          }

          .eye-button__icon {
            transition: all 0.3s ease;
          }

          .eye-button__text {
            z-index: 2;
            letter-spacing: 0.02em;
            transition: all 0.3s ease;
          }

          /* Hide PDF button (pastel coral) */
          &.eye-button--hide {
            background: linear-gradient(135deg, rgba(255, 138, 128, 0.15) 0%, rgba(255, 112, 97, 0.2) 100%);
            color: #d32f2f;
            border-color: rgba(255, 138, 128, 0.3);
            box-shadow: 0 2px 4px rgba(255, 138, 128, 0.2);

            .eye-button__icon {
              filter: drop-shadow(0 1px 2px rgba(211, 47, 47, 0.2));
            }
          }

          /* Show PDF button (pastel blue) */
          &.eye-button--show {
            background: linear-gradient(135deg, rgba(100, 181, 246, 0.15) 0%, rgba(66, 165, 245, 0.2) 100%);
            color: #1976d2;
            border-color: rgba(100, 181, 246, 0.3);
            box-shadow: 0 2px 4px rgba(100, 181, 246, 0.2);

            .eye-button__icon {
              filter: drop-shadow(0 1px 2px rgba(25, 118, 210, 0.2));
            }
          }

          /* Hover effects */
          &:hover {
            transform: translateY(-2px);

            &.eye-button--hide {
              box-shadow: 0 4px 12px rgba(255, 138, 128, 0.25);
              background: linear-gradient(135deg, rgba(255, 138, 128, 0.2) 0%, rgba(255, 112, 97, 0.3) 100%);
              border-color: rgba(255, 138, 128, 0.4);
            }

            &.eye-button--show {
              box-shadow: 0 4px 12px rgba(100, 181, 246, 0.25);
              background: linear-gradient(135deg, rgba(100, 181, 246, 0.2) 0%, rgba(66, 165, 245, 0.3) 100%);
              border-color: rgba(100, 181, 246, 0.4);
            }

            .eye-button__icon-container {
              transform: scale(1.1);
            }

            .eye-button__text {
              transform: scale(1.02);
            }
          }

          /* Active effects */
          &:active {
            transform: translateY(-1px);

            &.eye-button--hide {
              box-shadow: 0 2px 6px rgba(255, 138, 128, 0.2);
            }

            &.eye-button--show {
              box-shadow: 0 2px 6px rgba(100, 181, 246, 0.2);
            }

            .eye-button__icon-container {
              transform: scale(0.95);
            }
          }

          /* Ripple effect */
          &::after {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            width: 0;
            height: 0;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.4);
            transform: translate(-50%, -50%);
            transition: width 0.6s, height 0.6s;
          }

          &:active::after {
            width: 120px;
            height: 120px;
          }
        }
      }
    }

    .zoom-controls {
      display: flex;
      gap: 0.75rem;
      align-items: center;

      .btn-coconut {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 1rem;
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        color: white;
        border: none;
        border-radius: 6px;
        font-weight: 500;
        font-size: 0.85rem;
        cursor: pointer;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
        position: relative;
        overflow: hidden;

        .btn-icon {
          transition: transform 0.2s ease;

          &.spin {
            animation: spin 1s linear infinite;
          }
        }

        &:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
          background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);

          .btn-icon {
            transform: scale(1.1);
          }
        }

        &:active:not(:disabled) {
          transform: translateY(0);
          box-shadow: 0 2px 6px rgba(59, 130, 246, 0.3);
        }

        &:disabled {
          opacity: 0.7;
          cursor: not-allowed;
          transform: none;
        }

        &::before {
          content: '';
          position: absolute;
          top: 0;
          left: -100%;
          width: 100%;
          height: 100%;
          background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
          transition: left 0.5s ease;
        }

        &:hover:not(:disabled)::before {
          left: 100%;
        }
      }

      a {
        display: flex;
        align-items: center;
        gap: 0.25rem;
        padding: 0.25rem 0.5rem;
        font-size: 0.8rem;
      }
    }
  }

  /* New eye button styling */
  .eye-button {
    position: relative;
    display: flex;
    align-items: center;
    padding: 0.4rem 0.8rem;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-weight: 600;
    font-size: 0.85rem;
    transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
    overflow: hidden;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);

    &__icon-container {
      display: flex;
      align-items: center;
      justify-content: center;
      margin-right: 0.5rem;
      transition: transform 0.3s ease;
    }

    &__icon {
      transition: all 0.3s ease;
    }

    &__text {
      z-index: 2;
      letter-spacing: 0.01em;
      transition: transform 0.2s ease;
    }

    &__shine {
      position: absolute;
      top: -50%;
      left: -50%;
      width: 200%;
      height: 200%;
      background: linear-gradient(45deg,
          rgba(255, 255, 255, 0) 0%,
          rgba(255, 255, 255, 0.2) 50%,
          rgba(255, 255, 255, 0) 100%);
      transform: translateX(-100%) rotate(45deg);
      transition: transform 0.7s ease;
      pointer-events: none;
      z-index: 1;
    }

    /* Hide PDF button (red gradient) */
    &--hide {
      background: linear-gradient(-45deg, #d63031, #e84393, #fd79a8, #e17055);
      background-size: 400% 400%;
      animation: gradientBg 15s ease infinite;
      color: white;

      .eye-button__icon {
        filter: drop-shadow(0 1px 1px rgba(0, 0, 0, 0.3));
      }
    }

    /* Show PDF button (blue gradient) */
    &--show {
      background: linear-gradient(-45deg, #0984e3, #00cec9, #74b9ff, #6c5ce7);
      background-size: 400% 400%;
      animation: gradientBg 15s ease infinite;
      color: white;

      .eye-button__icon {
        filter: drop-shadow(0 1px 1px rgba(0, 0, 0, 0.3));
      }
    }

    /* Hover effects */
    &:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.15);

      .eye-button__icon-container {
        transform: scale(1.15);
      }

      .eye-button__text {
        transform: scale(1.05);
      }

      .eye-button__shine {
        transform: translateX(100%) rotate(45deg);
      }
    }

    /* Active effects */
    &:active {
      transform: translateY(1px);
      box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);

      .eye-button__icon-container {
        transform: scale(0.95);
      }
    }
  }

  .pdf-wrapper {
    flex: 1;
    overflow: hidden;
    display: flex;
    background-color: var(--color-bg);
    position: relative;

    .pdf-object {
      width: 100%;
      height: 100%;
      border: none;
    }

    .fallback-message {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100%;
      padding: 1rem;
      text-align: center;

      p {
        margin-bottom: 0.5rem;
        color: var(--color-text-light);
        font-size: 0.9rem;
      }

      .btn {
        display: flex;
        align-items: center;
        gap: 0.25rem;
        padding: 0.25rem 0.5rem;
        font-size: 0.8rem;
      }
    }
  }

  .pdf-hidden-message {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    background-color: var(--color-bg);
    color: var(--color-text-light);
    font-size: 1rem;
    font-style: italic;
    padding: 2rem;
    text-align: center;
    animation: fadeIn 0.5s ease;

    p {
      background: linear-gradient(45deg, #636e72, #b2bec3);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
      font-weight: 500;
      max-width: 400px;
      line-height: 1.5;
      text-shadow: 0 1px 1px rgba(255, 255, 255, 0.1);
    }

    &::before {
      content: '';
      display: block;
      width: 60px;
      height: 60px;
      margin-bottom: 1rem;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%23b2bec3' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z'%3E%3C/path%3E%3Ccircle cx='12' cy='12' r='3'%3E%3C/circle%3E%3Cline x1='3' y1='3' x2='21' y2='21'%3E%3C/line%3E%3C/svg%3E");
      background-size: contain;
      background-position: center;
      background-repeat: no-repeat;
      opacity: 0.7;
      animation: pulse 2s infinite;
    }
  }
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }

  100% {
    transform: rotate(360deg);
  }
}

@keyframes gradientBg {
  0% {
    background-position: 0% 50%;
  }

  50% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0% 50%;
  }
}

@keyframes pulse {
  0% {
    transform: scale(1);
    opacity: 0.7;
  }

  50% {
    transform: scale(1.1);
    opacity: 0.9;
  }

  100% {
    transform: scale(1);
    opacity: 0.7;
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>