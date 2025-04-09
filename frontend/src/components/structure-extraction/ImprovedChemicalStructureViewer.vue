<template>
  <div class="chemical-structure-viewer">
    <div v-if="!smiles && !molfile" class="empty-state">
      <p>No structure data available</p>
    </div>
    
    <div v-else class="structure-content">
      
      <div class="structure-display">
        <div v-if="isLoading" class="loading-overlay">
          <vue-feather type="loader" class="loading-icon spin"></vue-feather>
          <p>Generating depiction...</p>
        </div>
        
        <!-- SVG depiction container -->
        <div v-if="depictionData && depictionFormat === 'svg'" 
             class="svg-container"
             v-html="sanitizedSvg">
        </div>
        
        <!-- Base64 image container -->
        <img v-else-if="depictionData && depictionFormat === 'base64'"
             :src="'data:image/png;base64,' + depictionData"
             class="structure-image"
             alt="Chemical structure" />
             
        <!-- Fallback container -->
        <div v-else class="fallback-container">
          <p class="smiles-fallback">{{ truncatedSmiles }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import depictionService from '@/services/depictionService'

export default {
  name: 'ImprovedChemicalStructureViewer',
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
    },
    // Original source engine (e.g., 'decimer', 'molnextr', 'molscribe')
    sourceEngine: {
      type: String,
      default: ''
    },
    // Whether to use coordinates from the molfile for depiction
    useCoordinates: {
      type: Boolean,
      default: false
    },
    // SMARTS pattern to highlight in the structure
    highlight: {
      type: String,
      default: ''
    }
  },
  data() {
    return {
      isLoading: false,
      depictionData: null,
      depictionFormat: 'svg',
      depictionError: null,
      usingMolfile: false
    }
  },
  computed: {
    truncatedSmiles() {
      if (!this.smiles) return ''
      return this.smiles.length > 30 ? this.smiles.substring(0, 27) + '...' : this.smiles
    },
    shouldUseMolfile() {
      // Use molfile if available AND either:
      // 1. useCoordinates prop is true (explicit request to use coordinates)
      // 2. The source is molnextr or molscribe AND there's no explicit request not to use coordinates
      return !!this.molfile && 
        (this.useCoordinates === true || 
         ((this.sourceEngine === 'molnextr' || this.sourceEngine === 'molscribe') && 
          this.useCoordinates !== false))
    },
    sanitizedSvg() {
      if (!this.depictionData) return '';
      
      // For CDK SVG, we need to clean it up
      return this.sanitizeCdkSvg(this.depictionData);
    },
    // Added computed property for engine class
    engineClass() {
      if (this.sourceEngine === 'decimer') return 'decimer-tag';
      if (this.sourceEngine === 'molnextr') return 'molnextr-tag';
      if (this.sourceEngine === 'molscribe') return 'molscribe-tag';
      return '';
    },
    // Added computed property for engine label
    engineLabel() {
      if (this.sourceEngine === 'decimer') return 'DECIMER';
      if (this.sourceEngine === 'molnextr') return 'MolNexTR';
      if (this.sourceEngine === 'molscribe') return 'MolScribe';
      return this.sourceEngine || 'Unknown engine';
    }
  },
  watch: {
    smiles() {
      this.generateDepiction()
    },
    molfile() {
      this.generateDepiction()
    },
    useCoordinates() {
      // Regenerate depiction if useCoordinates changes
      this.generateDepiction()
    },
    highlight() {
      // Regenerate depiction if highlight pattern changes
      this.generateDepiction()
    }
  },
  mounted() {
    this.generateDepiction()
  },
  methods: {
    async generateDepiction() {
      if (!this.smiles && !this.molfile) return
      
      this.isLoading = true
      this.depictionError = null
      
      try {
        // Determine whether to use SMILES or molfile
        this.usingMolfile = this.shouldUseMolfile
        
        // Set up options for the depiction service - always use CDK
        const options = {
          engine: 'cdk',
          width: 400,
          height: 300,
          format: 'svg',
          kekulize: true,
          cip: true,
          unicolor: false
        }
        
        // Add either SMILES or molfile based on the decision
        if (this.usingMolfile) {
          console.log('Using molfile for depiction');
          options.molfile = this.molfile
          options.useMolfileDirectly = true  // Flag to tell backend to use the molfile directly
        } else {
          console.log('Using SMILES for depiction');
          options.smiles = this.smiles
        }
        
        // Add highlight pattern if provided
        if (this.highlight) {
          options.highlight = this.highlight
          console.log(`Adding highlight pattern: ${this.highlight}`)
        }
        
        // Generate the depiction
        const result = await depictionService.generateDepiction(options)
        
        // Store the depiction data and format
        this.depictionData = result
        this.depictionFormat = 'svg'
        
        // Log the depiction method used
        console.log(`Depiction generated using ${this.usingMolfile ? 'molfile' : 'SMILES'}`);
        
      } catch (error) {
        console.error('Error generating depiction:', error)
        this.depictionError = error.message || 'Failed to generate depiction'
        this.depictionData = null
        
        // Emit error event
        this.$emit('error', this.depictionError)
      } finally {
        this.isLoading = false
      }
    },
    sanitizeCdkSvg(svgString) {
      if (!svgString) return '';
      
      try {
        // Step 1: Replace namespace prefixes in tags
        let cleanedSvg = svgString.replace(/<ns0:/g, '<')
                               .replace(/<\/ns0:/g, '</')
                               .replace(/<\/ns0:SVG>/g, '</svg>');
                               
        // Step 2: Ensure the root SVG tag has proper attributes
        cleanedSvg = cleanedSvg.replace(/<svg/i, '<svg xmlns="http://www.w3.org/2000/svg"');
        
        // Step 3: Fix any other CDK-specific issues
        cleanedSvg = cleanedSvg.replace(/xmlns:ns0=".*?"/g, '');
        
        // Step 4: Make sure viewBox is properly set
        if (!cleanedSvg.includes('viewBox') && cleanedSvg.includes('width') && cleanedSvg.includes('height')) {
          const widthMatch = cleanedSvg.match(/width="(\d+\.?\d*)px?"/);
          const heightMatch = cleanedSvg.match(/height="(\d+\.?\d*)px?"/);
          
          if (widthMatch && heightMatch) {
            const width = widthMatch[1];
            const height = heightMatch[1];
            cleanedSvg = cleanedSvg.replace(/<svg/, `<svg viewBox="0 0 ${width} ${height}"`);
          }
        }
        
        return cleanedSvg;
      } catch (error) {
        console.error('Error sanitizing CDK SVG:', error);
        return svgString; // Return original on error
      }
    },
    copySmiles() {
      if (!this.smiles) return
      
      navigator.clipboard.writeText(this.smiles)
        .then(() => {
          // Emit copied event
          this.$emit('copied', 'SMILES copied to clipboard')
        })
        .catch(err => {
          console.error('Could not copy SMILES:', err)
          this.$emit('error', 'Failed to copy SMILES')
        })
    },
    copyMolfile() {
      if (!this.molfile) return
      
      navigator.clipboard.writeText(this.molfile)
        .then(() => {
          // Emit copied event
          this.$emit('copied', 'Molfile copied to clipboard')
        })
        .catch(err => {
          console.error('Could not copy Molfile:', err)
          this.$emit('error', 'Failed to copy Molfile')
        })
    },
    downloadImage() {
      if (!this.depictionData) return
      
      try {
        let dataUrl = ''
        
        if (this.depictionFormat === 'svg') {
          // Create a temporary SVG element with the sanitized SVG
          const svgElement = document.createElement('div')
          svgElement.innerHTML = this.sanitizedSvg
          const svg = svgElement.firstChild
          
          // Set needed attributes for SVG
          if (svg) {
            svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
            dataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(svg))
          } else {
            throw new Error('Invalid SVG data')
          }
        } else if (this.depictionFormat === 'base64') {
          dataUrl = 'data:image/png;base64,' + this.depictionData
        } else {
          throw new Error('Unsupported depiction format')
        }
        
        // Create a download link
        const link = document.createElement('a')
        link.download = `${this.name || 'structure'}.${this.depictionFormat === 'svg' ? 'svg' : 'png'}`
        link.href = dataUrl
        
        // Trigger download
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        
        // Emit download complete event
        this.$emit('download-complete', `Structure image downloaded`)
      } catch (error) {
        console.error('Error downloading image:', error)
        this.$emit('error', 'Failed to download structure image')
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
        align-items: center;
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
      height: 300px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 0.75rem;
      border: 1px solid var(--color-border);
      overflow: hidden;
      
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
      
      .svg-container {
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        
        :deep(svg) {
          max-width: 100%;
          max-height: 100%;
        }
      }
      
      .structure-image {
        max-width: 100%;
        max-height: 100%;
      }
      
      .fallback-container {
        display: flex;
        align-items: center;
        justify-content: center;
        height: 100%;
        
        .smiles-fallback {
          font-family: monospace;
          font-size: 0.875rem;
          color: var(--color-text-light);
          text-align: center;
          max-width: 90%;
          word-break: break-all;
        }
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
          font-family: monospace;
        }
      }
      
      .structure-source {
        display: flex;
        flex-wrap: wrap; /* Allow tags to wrap if needed */
        gap: 0.75rem;
        
        .source-tag, .engine-tag {
          display: flex;
          align-items: center;
          gap: 0.25rem;
          font-size: 0.75rem;
          border-radius: 4px;
          padding: 0.25rem 0.5rem;
          
          .icon-source {
            flex-shrink: 0;
          }
        }
        
        .molfile-tag {
          background-color: rgba(52, 199, 89, 0.1);
          color: var(--color-success);
          border: 1px solid rgba(52, 199, 89, 0.2);
        }
        
        .smiles-tag {
          background-color: rgba(74, 77, 231, 0.1);
          color: var(--color-primary);
          border: 1px solid rgba(74, 77, 231, 0.2);
        }
        
        .engine-tag {
          background-color: rgba(100, 100, 100, 0.1);
          color: var(--color-text-light);
          border: 1px solid rgba(100, 100, 100, 0.2);
        }
        
        /* Added specific tags for each engine */
        .decimer-tag {
          background-color: rgba(255, 149, 0, 0.1);
          color: #ff9500;
          border: 1px solid rgba(255, 149, 0, 0.2);
        }
        
        .molnextr-tag {
          background-color: rgba(0, 122, 255, 0.1);
          color: #007aff;
          border: 1px solid rgba(0, 122, 255, 0.2);
        }
        
        .molscribe-tag {
          background-color: rgba(175, 82, 222, 0.1);
          color: #af52de;
          border: 1px solid rgba(175, 82, 222, 0.2);
        }
      }
    }
  }
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* Deep selectors for SVG content */
:deep(svg) {
  background-color: white;
}
</style>