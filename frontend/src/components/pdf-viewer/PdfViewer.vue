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
            <span>PDF Viewer</span>
          </div>
          
          <div class="zoom-controls">
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
        
        <div class="pdf-wrapper" ref="pdfWrapper">
          <!-- Using embed tag for maximum browser compatibility -->
          <embed
            v-if="pdfUrl"
            :src="pdfUrl"
            class="pdf-embed"
            type="application/pdf"
            @load="onPdfLoaded"
          />
        </div>
      </div>
    </div>
  </template>
  
  <script>
  export default {
    name: 'PdfViewer',
    props: {
      pdfUrl: {
        type: String,
        required: true
      }
    },
    data() {
      return {
        isLoading: true,
        error: null
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
            
            // Use a slight delay to allow the embed tag to load
            setTimeout(() => {
              this.isLoading = false
            }, 1000)
          }
        }
      }
    },
    mounted() {
      console.log('PDF Viewer mounted, URL:', this.pdfUrl)
    },
    methods: {
      onPdfLoaded() {
        console.log('PDF loaded')
        this.isLoading = false
      },
      onPdfError(error) {
        this.isLoading = false
        this.error = `Failed to load PDF: ${error?.message || 'Unknown error'}`
        console.error('PDF loading error:', error)
      }
    }
  }
  </script>
  
  <style lang="scss" scoped>
  .pdf-viewer {
    display: flex;
    flex-direction: column;
    background-color: var(--color-card-bg);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
    height: 100%;
    min-height: 400px;
    overflow: hidden;
    
    .loading-container, .error-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100%;
      min-height: 300px;
      padding: 2rem;
      text-align: center;
      
      .loading-icon, .error-icon {
        width: 48px;
        height: 48px;
        margin-bottom: 1rem;
      }
      
      .loading-icon {
        color: var(--color-primary);
      }
      
      .error-icon {
        color: var(--color-error);
      }
      
      p {
        color: var(--color-text-light);
        font-size: 1rem;
        max-width: 280px;
      }
    }
    
    .loading-icon.spin {
      animation: spin 1s linear infinite;
    }
    
    .pdf-container {
      display: flex;
      flex-direction: column;
      height: 100%;
      min-height: 300px;
    }
    
    .pdf-controls {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--color-border);
      background-color: var(--color-card-bg);
      
      .page-info {
        font-weight: 600;
      }
      
      .zoom-controls {
        a {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.5rem 0.75rem;
          font-size: 0.875rem;
        }
      }
    }
    
    .pdf-wrapper {
      flex: 1;
      overflow: hidden;
      display: flex;
      background-color: var(--color-bg);
      
      .pdf-embed {
        width: 100%;
        height: 100%;
        border: none;
      }
    }
  }
  
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  </style>