<template>
  <div class="text-panel">
    <div v-if="!hasText" class="empty-state">
      <vue-feather type="file-text" size="48" class="empty-icon"></vue-feather>
      <h3>No Text Extracted Yet</h3>
      <p>Upload a PDF and click "Extract Text" to view the extracted content here.</p>
    </div>
    
    <div v-else class="text-content">
      <div class="text-actions">
        <button 
          class="btn btn-primary"
          @click="extractAnnotations"
          :disabled="isLoadingAnnotations"
        >
          <span v-if="!isLoadingAnnotations">
            <vue-feather type="tag" class="icon"></vue-feather>
            Extract Annotations
          </span>
          <span v-else class="loading-text">
            <vue-feather type="loader" class="icon spin"></vue-feather>
            Extracting...
          </span>
        </button>
        
        <button class="btn btn-outline" @click="downloadText">
          <vue-feather type="download" class="icon"></vue-feather>
          Download Text
        </button>
      </div>
      
      <div class="text-display">
        <HighlightedText 
          :text="extractedText"
          :annotations="annotations"
        />
      </div>
      
      <div v-if="annotations && annotations.length > 0" class="annotations-section">
        <h3 class="section-title">
          <vue-feather type="list" class="icon"></vue-feather>
          Extracted Annotations
        </h3>
        
        <AnnotationViewer :annotations="annotations" />
        
        <div class="annotation-actions">
          <button class="btn btn-outline" @click="downloadAnnotations">
            <vue-feather type="download" class="icon"></vue-feather>
            Download Annotations
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import HighlightedText from './HighlightedText.vue'
import AnnotationViewer from './AnnotationViewer.vue'

export default {
  name: 'TextPanel',
  components: {
    HighlightedText,
    AnnotationViewer
  },
  props: {
    extractedText: {
      type: String,
      default: ''
    },
    annotations: {
      type: Array,
      default: () => []
    },
    isLoadingAnnotations: {
      type: Boolean,
      default: false
    }
  },
  computed: {
    hasText() {
      return !!this.extractedText
    }
  },
  methods: {
    extractAnnotations() {
      this.$emit('extract-annotations')
    },
    downloadText() {
      if (!this.extractedText) return
      
      const blob = new Blob([this.extractedText], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'extracted_text.txt'
      a.click()
      URL.revokeObjectURL(url)
    },
    downloadAnnotations() {
      if (!this.annotations || this.annotations.length === 0) return
      
      // Format annotations as JSON
      const formattedAnnotations = this.annotations.map(ann => {
        return {
          label: ann.label,
          text: ann.text,
          start_offset: ann.start_offset,
          end_offset: ann.end_offset
        }
      })
      
      const blob = new Blob([JSON.stringify(formattedAnnotations, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'annotations.json'
      a.click()
      URL.revokeObjectURL(url)
    }
  }
}
</script>

<style lang="scss" scoped>
.text-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    height: 100%;
    min-height: 300px;
    padding: 2rem;
    
    .empty-icon {
      color: var(--color-text-light);
      margin-bottom: 1rem;
    }
    
    h3 {
      margin-bottom: 0.5rem;
    }
    
    p {
      color: var(--color-text-light);
      max-width: 280px;
    }
  }
  
  .text-content {
    display: flex;
    flex-direction: column;
    height: 100%;
    
    .text-actions {
      display: flex;
      gap: 1rem;
      margin-bottom: 1rem;
      
      .btn {
        flex: 1;
        
        @media (min-width: 768px) {
          flex: 0 0 auto;
        }
      }
      
      .icon {
        width: 16px;
        height: 16px;
      }
      
      .loading-text {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
      }
      
      .spin {
        animation: spin 1s linear infinite;
      }
    }
    
    .text-display {
      flex: 1;
      background-color: var(--color-card-bg);
      border-radius: var(--radius-lg);
      padding: 1.5rem;
      box-shadow: var(--shadow-sm);
      overflow-y: auto;
      margin-bottom: 1.5rem;
      min-height: 200px;
    }
    
    .annotations-section {
      background-color: var(--color-card-bg);
      border-radius: var(--radius-lg);
      padding: 1.5rem;
      box-shadow: var(--shadow-sm);
      margin-bottom: 1rem;
      
      .section-title {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 1.25rem;
        margin-bottom: 1rem;
        
        .icon {
          color: var(--color-primary);
        }
      }
      
      .annotation-actions {
        display: flex;
        justify-content: flex-end;
        margin-top: 1rem;
        
        .icon {
          width: 16px;
          height: 16px;
        }
      }
    }
  }
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>