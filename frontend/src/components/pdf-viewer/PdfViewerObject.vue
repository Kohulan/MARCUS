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
            <span>PDF Document</span>
            <span v-if="doi" class="doi-link">
              DOI: <a :href="'https://doi.org/' + doi" target="_blank">{{ doi }}</a>
            </span>
          </div>
          
          <div class="zoom-controls">
            <button 
              class="eye-button"
              @click="togglePdfVisibility"
              :class="{'eye-button--hide': isPdfVisible, 'eye-button--show': !isPdfVisible}"
              :title="isPdfVisible ? 'Hide PDF' : 'Show PDF'"
            >
              <div class="eye-button__icon-container">
                <vue-feather :type="isPdfVisible ? 'eye-off' : 'eye'" size="18" class="eye-button__icon"></vue-feather>
              </div>
              <span class="eye-button__text">{{ isPdfVisible ? 'Hide PDF' : 'Show PDF' }}</span>
              <div class="eye-button__shine"></div>
            </button>
            <a 
              :href="pdfUrl" 
              target="_blank" 
              class="btn btn-outline"
              title="Open in new tab"
            >
              <vue-feather type="external-link" size="16"></vue-feather>
              Open in new tab
            </a>
          </div>
        </div>
        
        <div class="pdf-wrapper" ref="pdfWrapper" v-if="isPdfVisible">
          <!-- Using object tag as an alternative approach -->
          <object 
            v-if="pdfUrl"
            :data="pdfUrl"
            type="application/pdf"
            class="pdf-object"
            @load="onPdfLoaded"
          >
            <div class="fallback-message">
              <p>It appears your browser doesn't support embedded PDFs.</p>
              <a :href="pdfUrl" target="_blank" class="btn btn-primary">
                <vue-feather type="file-text" size="16"></vue-feather>
                Click here to view the PDF
              </a>
            </div>
          </object>
        </div>
        <div v-else class="pdf-hidden-message">
          <p>PDF is currently hidden. Click "Show PDF" to display it again.</p>
        </div>
      </div>
    </div>
  </template>
  
  <script>
  import decimerService from '@/services/decimerService';

  export default {
    name: 'PdfViewerObject',
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
        doi: null // Store the DOI when extracted
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
  
  .loading-container, .error-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 200px;
    padding: 1rem;
    text-align: center;
    
    .loading-icon, .error-icon {
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
  }
  
  .pdf-controls {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem;
    border-bottom: 1px solid var(--color-border);
    background-color: var(--color-card-bg);
    
    .page-info {
      font-weight: 600;
      font-size: 0.9rem;
      display: flex;
      align-items: center;
      gap: 0.75rem;
      
      .doi-link {
        font-weight: normal;
        font-size: 0.8rem;
        
        a {
          color: var(--color-primary);
          text-decoration: none;
          
          &:hover {
            text-decoration: underline;
          }
        }
      }
    }
    
    .zoom-controls {
      display: flex;
      gap: 0.5rem;
      
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
      background: linear-gradient(
        45deg,
        rgba(255, 255, 255, 0) 0%,
        rgba(255, 255, 255, 0.2) 50%,
        rgba(255, 255, 255, 0) 100%
      );
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
      text-shadow: 0 1px 1px rgba(255,255,255,0.1);
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
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  
  @keyframes gradientBg {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
  }
  
  @keyframes pulse {
    0% { transform: scale(1); opacity: 0.7; }
    50% { transform: scale(1.1); opacity: 0.9; }
    100% { transform: scale(1); opacity: 0.7; }
  }
  
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }
  </style>