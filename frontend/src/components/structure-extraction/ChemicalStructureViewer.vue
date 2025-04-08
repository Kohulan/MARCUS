<template>
  <div class="chemical-structure-viewer">
    <div v-if="!smiles" class="empty-state">
      <p>No structure data available</p>
    </div>
    
    <div v-else class="structure-content">
      <div class="structure-header">
        <h4 class="structure-name">{{ name || 'Chemical Structure' }}</h4>
        <div class="structure-actions">
          <button class="btn-action" @click="copySmiles" title="Copy SMILES">
            <vue-feather type="copy" size="16"></vue-feather>
          </button>
          <button class="btn-action" @click="downloadImage" title="Download Image">
            <vue-feather type="download" size="16"></vue-feather>
          </button>
        </div>
      </div>
      
      <div class="structure-display">
        <div v-if="isLoading" class="loading-overlay">
          <vue-feather type="loader" class="loading-icon spin"></vue-feather>
          <p>Loading renderer...</p>
        </div>
        <canvas ref="structureCanvas" class="structure-canvas"></canvas>
      </div>
      
      <div class="structure-details">
        <div class="smiles-data">
          <div class="smiles-label">SMILES:</div>
          <div class="smiles-value" :title="smiles">{{ truncatedSmiles }}</div>
        </div>
        
        <div v-if="molfile" class="has-molfile">
          <vue-feather type="check-circle" class="icon-molfile" size="14"></vue-feather>
          Molfile available
        </div>
      </div>
    </div>
  </div>
</template>

<script>
// Import the SmilesDrawer loader utility
import { loadSmilesDrawer, isSmilesDrawerLoaded } from '@/utils/smilesDrawerLoader';

export default {
  name: 'ChemicalStructureViewer',
  props: {
    smiles: {
      type: String,
      default: ''
    },
    molfile: {
      type: String,
      default: ''
    },
    name: {
      type: String,
      default: ''
    }
  },
  data() {
    return {
      smilesDrawer: null,
      isLoading: false,
      libraryLoaded: false,
      libraryError: false
    }
  },
  computed: {
    truncatedSmiles() {
      if (!this.smiles) return ''
      return this.smiles.length > 30 ? this.smiles.substring(0, 27) + '...' : this.smiles
    }
  },
  watch: {
    smiles() {
      if (this.libraryLoaded) {
        this.renderStructure()
      } else {
        this.initializeSmilesDrawer()
      }
    }
  },
  mounted() {
    this.initializeSmilesDrawer()
  },
  methods: {
    async initializeSmilesDrawer() {
      // Don't try again if we've already loaded or if there's no SMILES
      if (this.libraryLoaded || !this.smiles) return
      
      this.isLoading = true
      this.libraryError = false
      
      try {
        // Check if SmilesDrawer is already loaded
        let SmilesDrawer
        
        if (isSmilesDrawerLoaded()) {
          SmilesDrawer = window.SmilesDrawer
          console.log('Using already loaded SmilesDrawer')
        } else {
          // Dynamically load SmilesDrawer
          console.log('Loading SmilesDrawer dynamically')
          SmilesDrawer = await loadSmilesDrawer()
        }
        
        // Create a new drawer instance
        this.smilesDrawer = new SmilesDrawer.Drawer({
          bondThickness: 1.5,
          width: 300,
          height: 200,
          padding: 20,
          atomVisualization: 'default',
          explicit: false
        })
        
        this.libraryLoaded = true
        this.renderStructure()
      } catch (error) {
        console.error('Error initializing SmilesDrawer:', error)
        this.libraryError = true
        this.renderFallbackStructure()
      } finally {
        this.isLoading = false
      }
    },
    renderStructure() {
      if (!this.smiles || !this.$refs.structureCanvas) return
      
      try {
        if (this.smilesDrawer) {
          // Use the SmilesDrawer library to render the structure
          window.SmilesDrawer.parse(this.smiles, (tree) => {
            try {
              this.smilesDrawer.draw(tree, this.$refs.structureCanvas)
            } catch (drawError) {
              console.error('Error drawing structure:', drawError)
              this.renderFallbackStructure()
            }
          }, (error) => {
            console.error('Error parsing SMILES:', error)
            this.renderFallbackStructure()
          })
        } else {
          this.renderFallbackStructure()
        }
      } catch (error) {
        console.error('Error rendering structure:', error)
        this.renderFallbackStructure()
      }
    },
    renderFallbackStructure() {
      // Fallback rendering using Canvas API
      if (!this.$refs.structureCanvas) return
      
      const canvas = this.$refs.structureCanvas
      const ctx = canvas.getContext('2d')
      
      // Set canvas size
      canvas.width = 300
      canvas.height = 200
      
      // Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      
      // Draw a simple hexagon as a fallback
      ctx.strokeStyle = '#333'
      ctx.lineWidth = 2
      ctx.beginPath()
      
      const centerX = canvas.width / 2
      const centerY = canvas.height / 2
      const radius = 50
      
      for (let i = 0; i < 6; i++) {
        const angle = (i * Math.PI / 3) - (Math.PI / 6)
        const x = centerX + radius * Math.cos(angle)
        const y = centerY + radius * Math.sin(angle)
        
        if (i === 0) {
          ctx.moveTo(x, y)
        } else {
          ctx.lineTo(x, y)
        }
      }
      
      ctx.closePath()
      ctx.stroke()
      
      // Add the SMILES as text
      ctx.fillStyle = '#666'
      ctx.font = '12px Arial'
      ctx.textAlign = 'center'
      ctx.fillText(this.truncatedSmiles, centerX, centerY + radius + 30)
    },
    copySmiles() {
      if (!this.smiles) return
      
      navigator.clipboard.writeText(this.smiles)
        .then(() => {
          // Show success message
          this.$emit('copied', 'SMILES copied to clipboard')
        })
        .catch(err => {
          console.error('Could not copy text:', err)
        })
    },
    downloadImage() {
      if (!this.$refs.structureCanvas) return
      
      try {
        const canvas = this.$refs.structureCanvas
        const link = document.createElement('a')
        
        // Convert canvas to PNG data URL
        const dataUrl = canvas.toDataURL('image/png')
        
        // Set download attributes
        const downloadName = `${this.name || 'structure'}.png`
        link.download = downloadName
        link.href = dataUrl
        
        // Trigger download
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        
        this.$emit('download-complete', `Structure image downloaded as ${downloadName}`)
      } catch (error) {
        console.error('Error downloading image:', error)
        this.$emit('download-error', 'Failed to download structure image')
      }
    }
  }
}
</script>

<style lang="scss" scoped>
.chemical-structure-viewer {
  width: 100%;
  
  .empty-state {
    text-align: center;
    padding: 1rem;
    color: var(--color-text-light);
    font-size: 0.875rem;
  }
  
  .structure-content {
    display: flex;
    flex-direction: column;
    
    .structure-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.75rem;
      
      .structure-name {
        font-size: 0.9375rem;
        margin: 0;
        font-weight: 600;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      
      .structure-actions {
        display: flex;
        gap: 0.5rem;
        
        .btn-action {
          background: none;
          border: none;
          color: var(--color-text-light);
          cursor: pointer;
          padding: 0.25rem;
          border-radius: 4px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s ease;
          
          &:hover {
            color: var(--color-primary);
            background-color: rgba(74, 77, 231, 0.1);
          }
        }
      }
    }
    
    .structure-display {
      position: relative;
      background-color: var(--color-input-bg);
      border-radius: var(--radius-md);
      padding: 0.75rem;
      height: 200px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 0.75rem;
      border: 1px solid var(--color-border);
      
      .loading-overlay {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        background-color: rgba(255, 255, 255, 0.9);
        z-index: 5;
        border-radius: var(--radius-md);
        
        .loading-icon {
          color: var(--color-primary);
          margin-bottom: 0.5rem;
        }
        
        .spin {
          animation: spin 1s linear infinite;
        }
        
        p {
          font-size: 0.875rem;
          color: var(--color-text);
        }
      }
      
      .structure-canvas {
        width: 100%;
        height: 100%;
        max-width: 300px;
        max-height: 200px;
      }
    }
    
    .structure-details {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      
      .smiles-data {
        display: flex;
        align-items: baseline;
        gap: 0.5rem;
        font-size: 0.875rem;
        
        .smiles-label {
          font-weight: 500;
          color: var(--color-text);
        }
        
        .smiles-value {
          color: var(--color-text-light);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
      }
      
      .has-molfile {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.8125rem;
        color: var(--color-success);
        
        .icon-molfile {
          color: var(--color-success);
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