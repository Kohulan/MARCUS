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
      </div>
    </div>
  </template>
  
  <script>
  export default {
    name: 'PdfViewerObject',
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
            
            // Add a slight delay since the load event isn't always reliable
            setTimeout(() => {
              this.isLoading = false
            }, 1500)
          }
        }
      }
    },
    mounted() {
      console.log('PDF Viewer (Object) mounted, URL:', this.pdfUrl)
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
    }
    
    .zoom-controls {
      a {
        display: flex;
        align-items: center;
        gap: 0.25rem;
        padding: 0.25rem 0.5rem;
        font-size: 0.8rem;
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
}
  
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  </style>