<template>
  <div class="segment-viewer" :class="{ 'fullscreen-mode': isFullscreen }">
    <div v-if="!segment" class="empty-state">
      <vue-feather type="image" size="32" class="empty-icon"></vue-feather>
      <p>No segment selected</p>
    </div>
    
    <div v-else class="segment-content">
      <!-- Normal View Mode -->
      <div v-if="!comparisonMode" class="normal-view">
        <!-- Header with title and close button -->
        <div class="segment-header">
          <h3 class="segment-title">Segment #{{ segmentNumber }}</h3>
          <div class="segment-actions">
            <button class="btn-action btn-context" @click="showInContext" title="View in PDF context">
              <vue-feather type="file-text" size="16"></vue-feather>
            </button>
            <button class="btn-action btn-close" @click="$emit('close')" title="Close">
              <vue-feather type="x" size="16"></vue-feather>
            </button>
          </div>
        </div>
        
        <!-- Section headers on the same line -->
        <div class="section-headers">
          <div class="header-item">
            <h4 class="section-title">Original Image</h4>
          </div>
          <div class="header-item processed" v-if="processedStructure">
            <vue-feather type="check-circle" size="16" class="success-icon"></vue-feather>
            <h4 class="section-title">Processed Structure</h4>
          </div>
        </div>
        
        <!-- Main content panels side by side -->
        <div class="content-panels">
          <!-- Left panel - Original image -->
          <div class="panel original-panel">
            <!-- Download button -->
            <div class="download-container">
              <button class="download-btn" @click="downloadSegmentImage">
                <vue-feather type="download" size="16" class="download-icon"></vue-feather>
                <span>Download Image</span>
              </button>
            </div>
            
            <!-- Image container -->
            <div class="image-container">
              <div v-if="isLoading" class="loading-overlay">
                <div class="loader-pulse"></div>
              </div>
              <img 
                v-if="segmentUrl" 
                :src="segmentUrl" 
                alt="Chemical structure segment" 
                class="segment-image"
                @load="handleImageLoaded"
                @error="handleImageError"
              />
            </div>
            
            <!-- Metadata -->
            <div class="metadata-container">
              <div class="metadata-section">
                <div class="info-row">
                  <span class="info-label">Page:</span>
                  <span class="info-value">{{ segment.pageNumber || '1' }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Filename:</span>
                  <span class="info-value truncate" :title="segment.filename">{{ segment.filename }}</span>
                </div>
              </div>
              
              <!-- Processing info (moved here) -->
              <div v-if="processedStructure" class="processing-info">
                <div class="info-row">
                  <span class="info-label">Engine:</span>
                  <span class="info-value engine-tag">{{ processedStructure.engine || 'Unknown' }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Processed:</span>
                  <span class="info-value">{{ formatTimestamp(processedStructure.timestamp) }}</span>
                </div>
              </div>
            </div>
          </div>
          
          <!-- Right panel - Processed structure -->
          <div v-if="processedStructure" class="panel structure-panel">
            <!-- Structure header with title and actions -->
            <div class="structure-header-container">
              <div class="structure-title">Compound {{ segmentNumber }}</div>
              <div class="structure-actions">
                <button class="action-btn" @click="copySmilesToClipboard" title="Copy SMILES">
                  <vue-feather type="copy" size="16"></vue-feather>
                </button>
                <button class="download-btn" @click="downloadStructureImage">
                  <vue-feather type="download" size="16" class="download-icon"></vue-feather>
                  <span>Download Structure</span>
                </button>
              </div>
            </div>
            
            <!-- Structure visualization -->
            <div class="structure-visualization">
              <!-- Structure container with improved viewer -->
              <div class="structure-container">
                <ImprovedChemicalStructureViewer
                  :smiles="processedStructure.smiles"
                  :molfile="processedStructure.molfile"
                  :name="processedStructure.name || `Compound ${segmentNumber}`"
                  :source-engine="processedStructure.engine"
                  :use-coordinates="shouldUseCoordinates"
                  @copied="handleCopied"
                  @error="handleStructureError"
                  @download-complete="handleDownloadComplete"
                  hide-controls
                />
              </div>
            </div>
            
            <!-- SMILES section - single instance -->
            <div class="smiles-container">
              <div class="smiles-header">
                <span class="smiles-label">SMILES:</span>
              </div>
              <div class="smiles-content">
                <div class="smiles-box">{{ processedStructure.smiles }}</div>
              </div>
            </div>
            
            <!-- Tags row -->
            <div class="tags-row">
              <div class="tag smiles-tag">
                <vue-feather type="code" size="14" class="tag-icon"></vue-feather>
                <span>Using SMILES</span>
              </div>
              <div class="tag engine-tag" :class="engineTagClass">
                <vue-feather type="cpu" size="14" class="tag-icon"></vue-feather>
                <span>{{ processedStructure.engine || 'Unknown' }}</span>
              </div>
              <div class="tag tool-tag">
                <vue-feather type="tool" size="14" class="tag-icon"></vue-feather>
                <span>CDK engine</span>
              </div>
            </div>
          </div>
        </div>
        
        <!-- Compare callout with glowing effect -->
        <div class="compare-callout">
          <div class="callout-icon">
            <vue-feather type="info" size="18" class="info-icon"></vue-feather>
          </div>
          <div class="callout-text">
            <p>Want to see how different engines perform on this structure?</p>
          </div>
          <button class="compare-btn pulse-effect" @click="runComparison">
            <vue-feather type="bar-chart-2" size="16" class="btn-icon"></vue-feather>
            <span>Compare Across All Engines</span>
          </button>
        </div>
      </div>
      
      <!-- Comparison Mode -->
      <div v-else class="comparison-mode">
        <div class="comparison-header">
          <h3 class="comparison-title">
            <vue-feather type="bar-chart-2" class="title-icon"></vue-feather>
            <span class="title-text">Engine Comparison: Segment #{{ segmentNumber }}</span>
          </h3>
          <button class="back-btn" @click="comparisonMode = false">
            <vue-feather type="arrow-left" size="14"></vue-feather>
            <span>Back to Details</span>
          </button>
        </div>
        
        <div class="comparison-content">
          <!-- Original Segment Preview -->
          <div class="original-section">
            <h4 class="content-title">Original Segment</h4>
            <div class="original-preview">
              <div class="preview-image">
                <img 
                  v-if="segmentUrl" 
                  :src="segmentUrl" 
                  alt="Original chemical structure segment" 
                  class="original-img"
                />
              </div>
              <div class="preview-info">
                <div class="info-item">
                  <span class="info-key">Filename:</span>
                  <span class="info-value">{{ segment.filename }}</span>
                </div>
                <div class="info-item">
                  <span class="info-key">Page:</span>
                  <span class="info-value">{{ segment.pageNumber || '1' }}</span>
                </div>
              </div>
            </div>
          </div>
          
          <h4 class="content-title results-title">Comparison Results</h4>
          
          <!-- Loading indicator -->
          <div class="comparison-loading" v-if="isComparing">
            <div class="fancy-spinner">
              <div class="ring"></div>
              <div class="ring"></div>
              <div class="dot"></div>
            </div>
            <p class="loading-text">Comparing results across engines...</p>
          </div>
          
          <!-- Results grid -->
          <div v-else class="results-grid">
            <!-- DECIMER Result -->
            <div class="result-card">
              <div class="card-header decimer">
                <div class="engine-icon-wrapper">
                  <vue-feather type="cpu" class="engine-icon"></vue-feather>
                </div>
                <h4 class="engine-name">DECIMER</h4>
              </div>
              <div class="card-body">
                <div class="result-image-container">
                  <img 
                    v-if="decimerResult && decimerResult.svg" 
                    :src="'data:image/svg+xml;utf8,' + encodeURIComponent(decimerResult.svg)" 
                    class="result-image"
                    alt="DECIMER result"
                  />
                  <div v-else-if="decimerResult && decimerResult.error" class="error-result">
                    <vue-feather type="alert-circle" class="error-icon"></vue-feather>
                    <p>{{ decimerResult.error }}</p>
                  </div>
                  <div v-else class="empty-result">
                    <vue-feather type="help-circle" class="empty-icon"></vue-feather>
                    <p>No result available</p>
                  </div>
                </div>
                
                <div v-if="decimerResult && decimerResult.smiles" class="result-smiles">
                  <div class="smiles-header">SMILES:</div>
                  <div class="smiles-value">{{ truncateText(decimerResult.smiles, 30) }}</div>
                </div>
              </div>
            </div>
            
            <!-- MolNexTR Result -->
            <div class="result-card">
              <div class="card-header molnextr">
                <div class="engine-icon-wrapper">
                  <vue-feather type="grid" class="engine-icon"></vue-feather>
                </div>
                <h4 class="engine-name">MolNexTR</h4>
              </div>
              <div class="card-body">
                <div class="result-image-container">
                  <img 
                    v-if="molnextrResult && molnextrResult.svg" 
                    :src="'data:image/svg+xml;utf8,' + encodeURIComponent(molnextrResult.svg)" 
                    class="result-image"
                    alt="MolNexTR result"
                  />
                  <div v-else-if="molnextrResult && molnextrResult.error" class="error-result">
                    <vue-feather type="alert-circle" class="error-icon"></vue-feather>
                    <p>{{ molnextrResult.error }}</p>
                  </div>
                  <div v-else class="empty-result">
                    <vue-feather type="help-circle" class="empty-icon"></vue-feather>
                    <p>No result available</p>
                  </div>
                </div>
                
                <div v-if="molnextrResult && molnextrResult.smiles" class="result-smiles">
                  <div class="smiles-header">SMILES:</div>
                  <div class="smiles-value">{{ truncateText(molnextrResult.smiles, 30) }}</div>
                </div>
              </div>
            </div>
            
            <!-- MolScribe Result -->
            <div class="result-card">
              <div class="card-header molscribe">
                <div class="engine-icon-wrapper">
                  <vue-feather type="edit-3" class="engine-icon"></vue-feather>
                </div>
                <h4 class="engine-name">MolScribe</h4>
              </div>
              <div class="card-body">
                <div class="result-image-container">
                  <img 
                    v-if="molscribeResult && molscribeResult.svg" 
                    :src="'data:image/svg+xml;utf8,' + encodeURIComponent(molscribeResult.svg)" 
                    class="result-image"
                    alt="MolScribe result"
                  />
                  <div v-else-if="molscribeResult && molscribeResult.error" class="error-result">
                    <vue-feather type="alert-circle" class="error-icon"></vue-feather>
                    <p>{{ molscribeResult.error }}</p>
                  </div>
                  <div v-else class="empty-result">
                    <vue-feather type="help-circle" class="empty-icon"></vue-feather>
                    <p>No result available</p>
                  </div>
                </div>
                
                <div v-if="molscribeResult && molscribeResult.smiles" class="result-smiles">
                  <div class="smiles-header">SMILES:</div>
                  <div class="smiles-value">{{ truncateText(molscribeResult.smiles, 30) }}</div>
                </div>
              </div>
            </div>
          </div>
          
          <div class="comparison-footer">
            <button class="refresh-btn" @click="runComparisonAgain" :disabled="isComparing">
              <vue-feather type="refresh-cw" class="refresh-icon"></vue-feather>
              <span>Run Comparison Again</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Context View Modal -->
    <div v-if="showContextView" class="context-view-container">
      <div class="context-view-header">
        <h3>Original Context - Page {{ segment.pageNumber || 1 }}</h3>
        <button class="btn-close" @click="closeContextView">
          <vue-feather type="x" size="16"></vue-feather>
        </button>
      </div>
      
      <div class="context-view-content">
        <div v-if="isLoadingContext" class="loading-context">
          <div class="loader-pulse"></div>
        </div>
        <img 
          v-else-if="contextImageUrl" 
          :src="contextImageUrl" 
          alt="Segment in context"
          class="context-image"
          @load="contextImageLoaded"
          @error="handleContextImageError"
        />
        <div v-else class="context-error">
          <vue-feather type="alert-triangle" size="24"></vue-feather>
          <p>Failed to load page context</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import ImprovedChemicalStructureViewer from './ImprovedChemicalStructureViewer.vue'
import ocsrService from '@/services/ocsrService'
import depictionService from '@/services/depictionService'

export default {
  name: 'SegmentViewer',
  components: {
    ImprovedChemicalStructureViewer
  },
  props: {
    segment: {
      type: Object,
      default: null
    },
    processedStructure: {
      type: Object,
      default: null
    },
    isProcessing: {
      type: Boolean,
      default: false
    }
  },
  data() {
    return {
      isLoading: true,
      hasError: false,
      errorMessage: '',
      segmentUrl: null,
      comparisonMode: false,
      isComparing: false,
      decimerResult: null,
      molnextrResult: null,
      molscribeResult: null,
      isFullscreen: false,
      showContextView: false,
      contextImageUrl: null,
      isLoadingContext: false,
      hasContextError: false
    }
  },
  computed: {
    segmentNumber() {
      if (!this.segment) return 0
      return this.segment.segmentNumber || this.segment.id.split('-')[1] || '?'
    },
    engineTagClass() {
      if (!this.processedStructure || !this.processedStructure.engine) return ''
      
      const engine = this.processedStructure.engine.toLowerCase()
      if (engine.includes('decimer')) return 'decimer-tag'
      if (engine.includes('molnextr')) return 'molnextr-tag'
      if (engine.includes('molscribe')) return 'molscribe-tag'
      
      return ''
    },
    shouldUseCoordinates() {
      if (!this.processedStructure) return false;
  
      // Check if useCoordinates flag is explicitly set
      if (this.processedStructure.useCoordinates === true) {
        return true;
      }
      
      // Otherwise, use coordinates if:
      // 1. We have a molfile
      // 2. The engine is MolNexTR or MolScribe
      return !!this.processedStructure.molfile && 
        (this.processedStructure.engine === 'molnextr' || 
         this.processedStructure.engine === 'molscribe');
    }
  },
  watch: {
    segment: {
      immediate: true,
      handler(newSegment) {
        if (newSegment) {
          this.loadSegmentImage()
        } else {
          this.resetState()
        }
      }
    }
  },
  methods: {
    resetState() {
      this.isLoading = true
      this.hasError = false
      this.errorMessage = ''
      this.comparisonMode = false
      this.isComparing = false
      this.decimerResult = null
      this.molnextrResult = null
      this.molscribeResult = null
      this.showContextView = false
      this.contextImageUrl = null
      this.isLoadingContext = false
      this.hasContextError = false
      if (this.segmentUrl) {
        URL.revokeObjectURL(this.segmentUrl)
        this.segmentUrl = null
      }
      if (this.contextImageUrl) {
        URL.revokeObjectURL(this.contextImageUrl)
        this.contextImageUrl = null
      }
    },
    showInContext() {
      this.showContextView = true;
      this.loadContextImage();
    },
    closeContextView() {
      this.showContextView = false;
      if (this.contextImageUrl) {
        URL.revokeObjectURL(this.contextImageUrl);
        this.contextImageUrl = null;
      }
    },
    async loadContextImage() {
      if (!this.segment) return;
      
      this.isLoadingContext = true;
      this.hasContextError = false;
      
      try {
        // Log the segment object to debug
        console.log('Segment object:', this.segment);
        
        // Get segment filename
        const segmentFilename = this.segment.filename;
        
        if (!segmentFilename) {
          throw new Error('Could not determine segment filename from metadata');
        }
        
        // Extract PDF filename from the path if pdfFilename is not available
        let pdfFilename;
        
        if (this.segment.pdfFilename) {
          pdfFilename = this.segment.pdfFilename;
        } else if (this.segment.path) {
          // Extract the directory name from the path which should be the PDF name
          const pathParts = this.segment.path.split('/');
          if (pathParts.length >= 2) {
            // Get the directory name (first part)
            pdfFilename = pathParts[0] + '.pdf';
            console.log('Extracted PDF filename from path:', pdfFilename);
          }
        }
        
        if (!pdfFilename) {
          throw new Error('Could not determine PDF filename from segment metadata');
        }
        
        // Get page number from filename
        let pageNumber = 0;
        if (this.segment.pageNumber !== undefined) {
          pageNumber = this.segment.pageNumber;
        } else if (segmentFilename && segmentFilename.startsWith('page_')) {
          const parts = segmentFilename.split('_');
          if (parts.length >= 2) {
            pageNumber = parseInt(parts[1], 10);
            console.log('Extracted page number:', pageNumber);
          }
        }
        
        // Construct the URL for the highlighted page endpoint using relative API path
        const url = `/api/decimer/get_highlighted_page/${encodeURIComponent(segmentFilename)}?pdf_filename=${encodeURIComponent(pdfFilename)}`;
        
        console.log('Requesting highlighted page:', url);
        
        // Fetch the highlighted image
        const response = await fetch(url);
        
        if (!response.ok) {
          // If highlighted page fails, check the response for details
          const errorData = await response.json().catch(() => ({}));
          console.error('Highlighted page error:', errorData);
          
          // Fall back to getting the segment image at a larger size
          console.log('Falling back to segment image');
          
          if (this.segmentUrl) {
            this.contextImageUrl = this.segmentUrl;
            this.$emit('notification', {
              type: 'warning',
              message: 'Showing segment only - page context is not available'
            });
          } else {
            throw new Error(`Failed to load page context: ${errorData.detail || response.statusText}`);
          }
        } else {
          const blob = await response.blob();
          this.contextImageUrl = URL.createObjectURL(blob);
        }
      } catch (error) {
        console.error('Error loading context image:', error);
        this.hasContextError = true;
        
        // As a last resort, if we have the segment image, just show that
        if (this.segmentUrl) {
          this.contextImageUrl = this.segmentUrl;
          this.$emit('notification', {
            type: 'warning',
            message: 'Showing segment only - full page context not available'
          });
        } else {
          this.$emit('error', `Failed to load context image: ${error.message}`);
        }
      } finally {
        this.isLoadingContext = false;
      }
    },
    contextImageLoaded() {
      this.isLoadingContext = false;
    },
    handleContextImageError() {
      this.isLoadingContext = false;
      this.hasContextError = true;
      this.$emit('error', 'Failed to load page context image');
    },
    runComparisonAgain() {
      this.runComparisonManual()
    },
    truncateText(text, maxLength) {
      if (!text) return '';
      return text.length > maxLength ? text.substring(0, maxLength - 3) + '...' : text;
    },
    runComparison() {
      // Switch to comparison mode
      this.comparisonMode = true
      // Run the comparison
      this.runComparisonManual()
      // Emit an event to notify parent component
      this.$emit('run-comparison', this.segment)
    },
    async runComparisonManual() {
      if (!this.segment || this.isComparing) return;
      
      this.isComparing = true;
      
      // Reset results
      this.decimerResult = null;
      this.molnextrResult = null;
      this.molscribeResult = null;
      
      // Determine image path format
      const segmentsDirectory = this.segment.path ? this.segment.path.split('/all_segments/')[0] : '';
      const imagePath = segmentsDirectory ? `${segmentsDirectory}/all_segments/${this.segment.filename}` : this.segment.filename;
      
      console.log('Segment path for comparison:', imagePath);
      
      try {
        // Process with DECIMER
        this.processEngine('decimer', imagePath);
        
        // Process with MolNexTR
        this.processEngine('molnextr', imagePath);
        
        // Process with MolScribe
        this.processEngine('molscribe', imagePath);
      } catch (error) {
        console.error('Error initiating comparisons:', error);
      }
    },
    async processEngine(engine, imagePath) {
      try {
        console.log(`Processing with ${engine}...`);
        
        const options = {
          engine: engine,
          handDrawn: false,
          includeMolfile: true
        };
        
        // Get SMILES and molfile
        const response = await ocsrService.generateBoth(null, imagePath, options);
        
        console.log(`${engine} response:`, response);
        
        // Create a depiction
        let svg = null;
        try {
          const depictionOptions = {
            engine: 'cdk',
            smiles: response.smiles,
            molfile: response.molfile,
            format: 'svg'
          };
          
          const svgResponse = await depictionService.generateDepiction(depictionOptions);
          svg = svgResponse;
        } catch (depError) {
          console.error(`Error generating depiction for ${engine}:`, depError);
        }
        
        // Store the results based on the engine
        const result = {
          smiles: response.smiles,
          molfile: response.molfile,
          svg: svg,
          error: null
        };
        
        if (engine === 'decimer') {
          this.decimerResult = result;
        } else if (engine === 'molnextr') {
          this.molnextrResult = result;
        } else if (engine === 'molscribe') {
          this.molscribeResult = result;
        }
      } catch (error) {
        console.error(`Error processing with ${engine}:`, error);
        
        // Store error in the appropriate result
        const errorResult = {
          smiles: null,
          molfile: null,
          svg: null,
          error: error.message || `Failed to process with ${engine}`
        };
        
        if (engine === 'decimer') {
          this.decimerResult = errorResult;
        } else if (engine === 'molnextr') {
          this.molnextrResult = errorResult;
        } else if (engine === 'molscribe') {
          this.molscribeResult = errorResult;
        }
      } finally {
        // Check if all engines have been processed
        if (this.decimerResult && this.molnextrResult && this.molscribeResult) {
          this.isComparing = false;
        }
      }
    },
    async loadSegmentImage() {
      if (!this.segment) return
      
      this.resetState()
      
      // If the segment already has a URL, use it
      if (this.segment.imageUrl) {
        console.log('Using existing segment image URL:', this.segment.imageUrl);
        this.segmentUrl = this.segment.imageUrl
        this.isLoading = false
        return
      }
      
      try {
        if (this.segment.path) {
          // Use relative URL path through the API proxy
          this.segmentUrl = `/api/decimer/get_segment_image/${this.segment.path}`;
          console.log('Created segment URL from path:', this.segmentUrl);
        } else {
          throw new Error('No image URL or path provided')
        }
      } catch (error) {
        this.hasError = true
        this.errorMessage = error.message || 'Failed to load segment image'
        this.isLoading = false
        
        // Notify parent component
        this.$emit('error', this.errorMessage)
      }
    },
    handleImageLoaded() {
      this.isLoading = false
      this.hasError = false
    },
    handleImageError() {
      this.isLoading = false
      this.hasError = true
      this.errorMessage = 'Failed to load image'
      
      // Notify parent component
      this.$emit('error', this.errorMessage)
    },
    copySmilesToClipboard() {
      if (!this.processedStructure || !this.processedStructure.smiles) return;
      
      try {
        navigator.clipboard.writeText(this.processedStructure.smiles)
          .then(() => {
            // Show success message
            this.$emit('copy-complete', 'SMILES copied to clipboard')
          })
          .catch(err => {
            console.error('Could not copy SMILES:', err)
            this.$emit('error', 'Failed to copy SMILES')
          });
      } catch (error) {
        console.error('Error copying to clipboard:', error)
        this.$emit('error', 'Failed to copy to clipboard')
      }
    },
    async downloadSegmentImage() {
      if (!this.segmentUrl) return
      
      try {
        // Fetch the image as a blob
        const response = await fetch(this.segmentUrl)
        const blob = await response.blob()
        
        // Create a download link
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `segment-${this.segmentNumber}.png`
        a.click()
        
        // Clean up
        URL.revokeObjectURL(url)
        
        // Notify parent component
        this.$emit('download-complete', 'Segment image downloaded')
      } catch (error) {
        console.error('Error downloading image:', error)
        
        // Notify parent component
        this.$emit('error', 'Failed to download image')
      }
    },
    async downloadStructureImage() {
      if (!this.processedStructure) return;
      
      try {
        // Use the structure viewer's download method or implement your own
        // Here we're creating a simple SVG download
        const svgElement = document.querySelector('.structure-container .svg-container svg');
        
        if (svgElement) {
          // Create a clone of the SVG element
          const svgClone = svgElement.cloneNode(true);
          
          // Set necessary attributes for standalone SVG
          svgClone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
          svgClone.setAttribute('version', '1.1');
          
          // Create blob from SVG string
          const svgString = new XMLSerializer().serializeToString(svgClone);
          const blob = new Blob([svgString], { type: 'image/svg+xml' });
          
          // Create download link
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `compound-${this.segmentNumber}.svg`;
          a.click();
          
          // Clean up
          URL.revokeObjectURL(url);
          
          // Notify parent component
          this.$emit('download-complete', 'Structure image downloaded');
        } else {
          throw new Error('SVG element not found');
        }
      } catch (error) {
        console.error('Error downloading structure image:', error);
        this.$emit('error', 'Failed to download structure image');
      }
    },
    handleCopied(message) {
      // Forward the copied event to parent
      this.$emit('copy-complete', message)
    },
    handleStructureError(message) {
      // Forward the error event to parent
      this.$emit('error', message)
    },
    handleDownloadComplete(message) {
      // Forward the download-complete event to parent
      this.$emit('download-complete', message)
    },
    formatTimestamp(timestamp) {
      if (!timestamp) return 'Unknown'
      
      try {
        const date = new Date(timestamp)
        return date.toLocaleString()
      } catch (e) {
        return timestamp
      }
    }
  }
}
</script>

<style lang="scss" scoped>
.segment-viewer {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: #f8fafc;
  border-radius: 12px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.08);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  transition: all 0.3s ease;
  position: relative;
  
  /* Empty state styling */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    padding: 2rem;
    color: #64748b;
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    
    .empty-icon {
      margin-bottom: 1rem;
      color: #94a3b8;
      filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
    }
    
    p {
      font-size: 1.125rem;
      font-weight: 500;
    }
  }
  
  .segment-content {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    
    /* Normal view styling */
    .normal-view {
      display: flex;
      flex-direction: column;
      height: 100%;
      padding: 1.5rem;
      
      /* Header styling */
      .segment-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1.5rem;
        
        .segment-title {
          font-size: 1.625rem;
          font-weight: 700;
          color: #0f172a;
          margin: 0;
          background: linear-gradient(90deg, #1e293b 0%, #334155 100%);
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
        }
        
        .segment-actions {
          display: flex;
          gap: 0.5rem;
          
          .btn-action {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 36px;
            height: 36px;
            border: none;
            border-radius: 8px;
            background-color: #f1f5f9;
            color: #64748b;
            cursor: pointer;
            transition: all 0.2s ease;
            
            &:hover {
              background-color: #e2e8f0;
              color: #334155;
              transform: translateY(-1px);
              box-shadow: 0 2px 5px rgba(0, 0, 0, 0.08);
            }
            
            &:active {
              transform: translateY(0px);
            }
            
            &.btn-close:hover {
              background-color: #fee2e2;
              color: #ef4444;
            }
            
            &.btn-context:hover {
              background-color: #e6f7ff;
              color: #0081ff;
            }
          }
        }
      }
      
      /* Section headers */
      .section-headers {
        display: flex;
        justify-content: space-between;
        margin-bottom: 1rem;
        padding: 0 1rem;
        
        .header-item {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          
          &.processed {
            .success-icon {
              color: #10b981;
              filter: drop-shadow(0 1px 2px rgba(16, 185, 129, 0.2));
            }
          }
          
          .section-title {
            margin: 0;
            font-size: 1.125rem;
            font-weight: 600;
            color: #334155;
          }
        }
      }
      
      /* Content panels */
      .content-panels {
        display: flex;
        gap: 1.5rem;
        height: 100%;
        margin-bottom: 1.5rem;
        
        @media (max-width: 768px) {
          flex-direction: column;
        }
        
        .panel {
          flex: 1;
          display: flex;
          flex-direction: column;
          border-radius: 12px;
          background-color: white;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
          overflow: hidden;
          height: fit-content;
          transition: transform 0.3s ease, box-shadow 0.3s ease;
          
          &:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 16px rgba(0, 0, 0, 0.08);
          }
          
          /* Original panel specific styling */
          &.original-panel {
            .download-container {
              display: flex;
              justify-content: flex-end;
              padding: 0.75rem 1rem;
              border-bottom: 1px solid #e2e8f0;
            }
            
            .image-container {
              display: flex;
              align-items: center;
              justify-content: center;
              padding: 1.5rem;
              background-color: white;
              min-height: 280px;
              position: relative;
              
              .loading-overlay {
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                background-color: rgba(255, 255, 255, 0.9);
                z-index: 2;
                
                .loader-pulse {
                  width: 60px;
                  height: 60px;
                  border-radius: 50%;
                  background-color: rgba(79, 70, 229, 0.2);
                  animation: pulse 1.5s ease-in-out infinite;
                  
                  &:before, &:after {
                    content: '';
                    position: absolute;
                    height: 100%;
                    width: 100%;
                    background-color: rgba(79, 70, 229, 0.2);
                    border-radius: 50%;
                    z-index: -1;
                    opacity: 0.7;
                  }
                  
                  &:before {
                    animation: pulse 1.5s ease-in-out infinite;
                    animation-delay: 0.3s;
                  }
                  
                  &:after {
                    animation: pulse 1.5s ease-in-out infinite;
                    animation-delay: 0.6s;
                  }
                }
              }
              
              .segment-image {
                max-width: 100%;
                max-height: 280px;
                object-fit: contain;
                border-radius: 4px;
                transition: all 0.2s ease;
              }
            }
            
            .metadata-container {
              padding: 1rem;
              border-top: 1px solid #e2e8f0;
              background-color: #f8fafc;
              
              .metadata-section, .processing-info {
                margin-bottom: 0.75rem;
                
                &:last-child {
                  margin-bottom: 0;
                }
              }
              
              .processing-info {
                border-top: 1px dashed #e2e8f0;
                padding-top: 0.75rem;
                margin-top: 0.75rem;
              }
              
              .info-row {
                display: flex;
                align-items: center;
                margin-bottom: 0.5rem;
                
                &:last-child {
                  margin-bottom: 0;
                }
                
                .info-label {
                  font-weight: 600;
                  color: #334155;
                  width: 80px;
                  flex-shrink: 0;
                  font-size: 0.875rem;
                }
                
                .info-value {
                  color: #64748b;
                  font-size: 0.875rem;
                  
                  &.truncate {
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                  }
                  
                  &.engine-tag {
                    font-weight: 500;
                    color: #4f46e5;
                  }
                }
              }
            }
          }
          
          /* Structure panel specific styling */
          &.structure-panel {
            .structure-header-container {
              display: flex;
              justify-content: space-between;
              align-items: center;
              padding: 0.75rem 1rem;
              border-bottom: 1px solid #e2e8f0;
              
              .structure-title {
                font-weight: 600;
                color: #0f172a;
                font-size: 1rem;
              }
              
              .structure-actions {
                display: flex;
                align-items: center;
                gap: 0.5rem;
                
                .action-btn {
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  width: 32px;
                  height: 32px;
                  border: none;
                  border-radius: 6px;
                  background-color: #f1f5f9;
                  color: #64748b;
                  cursor: pointer;
                  transition: all 0.2s ease;
                  
                  &:hover {
                    background-color: #e2e8f0;
                    color: #334155;
                  }
                }
              }
            }
            
            .structure-visualization {
              position: relative;
              padding: 1.5rem;
              background-color: white;
              min-height: 280px;
              
              .structure-title-overlay {
                position: absolute;
                top: 1rem;
                left: 1rem;
                font-size: 0.875rem;
                font-weight: 600;
                color: #64748b;
                background-color: rgba(255, 255, 255, 0.9);
                padding: 0.25rem 0.5rem;
                border-radius: 4px;
                z-index: 1;
                display: none; /* Hidden by default */
              }
              
              .structure-container {
                height: 100%;
                width: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                
                /* Deep selectors for chemical structure viewer */
                :deep(.chemical-structure-viewer) {
                  height: 100%;
                  width: 100%;
                  
                  .structure-display {
                    background-color: white !important;
                  }
                  
                  .svg-container {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    
                    svg {
                      max-width: 100%;
                      max-height: 280px;
                    }
                  }
                }
              }
            }
            
            .smiles-container {
              padding: 1rem;
              border-top: 1px solid #e2e8f0;
              
              .smiles-header {
                margin-bottom: 0.5rem;
                
                .smiles-label {
                  font-weight: 600;
                  color: #334155;
                  font-size: 0.875rem;
                }
              }
              
              .smiles-content {
                .smiles-box {
                  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
                  background-color: #f8fafc;
                  padding: 0.75rem;
                  border-radius: 6px;
                  font-size: 0.875rem;
                  color: #334155;
                  overflow-x: auto;
                  white-space: pre-wrap;
                  word-break: break-all;
                  border: 1px solid #e2e8f0;
                }
              }
            }
            
            .tags-row {
              display: flex;
              flex-wrap: wrap;
              gap: 0.5rem;
              padding: 0.75rem 1rem;
              border-top: 1px solid #e2e8f0;
              background-color: #f8fafc;
              
              .tag {
                display: flex;
                align-items: center;
                gap: 0.375rem;
                font-size: 0.75rem;
                padding: 0.25rem 0.5rem;
                border-radius: 4px;
                font-weight: 500;
                
                .tag-icon {
                  opacity: 0.8;
                }
                
                &.smiles-tag {
                  background-color: rgba(79, 70, 229, 0.1);
                  color: #4f46e5;
                  border: 1px solid rgba(79, 70, 229, 0.3);
                }
                
                &.engine-tag {
                  background-color: rgba(20, 184, 166, 0.1);
                  color: #14b8a6;
                  border: 1px solid rgba(20, 184, 166, 0.3);
                  
                  &.decimer-tag {
                    background-color: rgba(249, 115, 22, 0.1);
                    color: #f97316;
                    border: 1px solid rgba(249, 115, 22, 0.3);
                  }
                  
                  &.molnextr-tag {
                    background-color: rgba(14, 165, 233, 0.1);
                    color: #0ea5e9;
                    border: 1px solid rgba(14, 165, 233, 0.3);
                  }
                  
                  &.molscribe-tag {
                    background-color: rgba(168, 85, 247, 0.1);
                    color: #a855f7;
                    border: 1px solid rgba(168, 85, 247, 0.3);
                  }
                }
                
                &.tool-tag {
                  background-color: rgba(100, 116, 139, 0.1);
                  color: #64748b;
                  border: 1px solid rgba(100, 116, 139, 0.3);
                }
              }
            }
          }
        }
      }
      
      /* Download button styling */
      .download-btn {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        border: none;
        background-color: white;
        color: #334155;
        font-size: 0.875rem;
        font-weight: 500;
        padding: 0.5rem 0.75rem;
        border-radius: 6px;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
        border: 1px solid #e2e8f0;
        
        .download-icon {
          color: #64748b;
        }
        
        &:hover {
          border-color: #cbd5e1;
          background-color: #f8fafc;
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
          
          .download-icon {
            color: #4f46e5;
          }
        }
      }
      
      /* Compare callout */
      .compare-callout {
        display: flex;
        align-items: center;
        padding: 1.25rem;
        background: linear-gradient(135deg, rgba(79, 70, 229, 0.05) 0%, rgba(79, 70, 229, 0.1) 100%);
        border-radius: 12px;
        border: 1px solid rgba(79, 70, 229, 0.2);
        box-shadow: 0 4px 6px rgba(79, 70, 229, 0.05);
        margin-top: auto;
        
        .callout-icon {
          flex-shrink: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 38px;
          height: 38px;
          background-color: rgba(79, 70, 229, 0.1);
          border-radius: 50%;
          margin-right: 1rem;
          
          .info-icon {
            color: #4f46e5;
          }
        }
        
        .callout-text {
          flex: 1;
          
          p {
            margin: 0;
            color: #334155;
            font-weight: 500;
            font-size: 0.9375rem;
          }
        }
        
        .compare-btn {
          flex-shrink: 0;
          display: flex;
          align-items: center;
          gap: 0.5rem;
          background-color: #4f46e5;
          color: white;
          border: none;
          padding: 0.625rem 1rem;
          border-radius: 8px;
          font-weight: 500;
          font-size: 0.9375rem;
          cursor: pointer;
          transition: all 0.3s ease;
          box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2);
          
          .btn-icon {
            opacity: 0.9;
          }
          
          &:hover {
            background-color: #4338ca;
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(79, 70, 229, 0.3);
          }
          
          &:active {
            transform: translateY(0px);
          }
          
          &.pulse-effect {
            animation: subtle-pulse 3s infinite;
          }
        }
      }
    }
    
    /* Comparison mode styling */
    .comparison-mode {
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      height: 100%;
      overflow-y: auto;
      
      .comparison-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid #e2e8f0;
        
        .comparison-title {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 1.5rem;
          font-weight: 700;
          color: #0f172a;
          margin: 0;
          
          .title-icon {
            color: #4f46e5;
          }
        }
        
        .back-btn {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          background-color: white;
          border: 1px solid #e2e8f0;
          color: #334155;
          font-size: 0.875rem;
          font-weight: 500;
          padding: 0.5rem 1rem;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s ease;
          
          &:hover {
            background-color: #f8fafc;
            border-color: #cbd5e1;
          }
        }
      }
      
      .comparison-content {
        flex: 1;
        
        .content-title {
          font-size: 1.25rem;
          font-weight: 600;
          color: #334155;
          margin: 0 0 1rem 0;
          
          &.results-title {
            margin-top: 2rem;
          }
        }
        
        .original-section {
          margin-bottom: 2rem;
          
          .original-preview {
            display: flex;
            flex-direction: column;
            background-color: white;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
            overflow: hidden;
            
            @media (min-width: 768px) {
              flex-direction: row;
            }
            
            .preview-image {
              padding: 1.5rem;
              display: flex;
              align-items: center;
              justify-content: center;
              background-color: white;
              
              @media (min-width: 768px) {
                flex: 0 0 300px;
                border-right: 1px solid #e2e8f0;
              }
              
              .original-img {
                max-width: 100%;
                max-height: 200px;
                object-fit: contain;
              }
            }
            
            .preview-info {
              padding: 1.5rem;
              background-color: #f8fafc;
              
              @media (min-width: 768px) {
                flex: 1;
              }
              
              .info-item {
                margin-bottom: 0.5rem;
                
                &:last-child {
                  margin-bottom: 0;
                }
                
                .info-key {
                  font-weight: 600;
                  color: #334155;
                  margin-right: 0.5rem;
                  font-size: 0.875rem;
                }
                
                .info-value {
                  color: #64748b;
                  font-size: 0.875rem;
                }
              }
            }
          }
        }
        
        /* Fancy loading spinner */
        .comparison-loading {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 3rem;
          
          .fancy-spinner {
            position: relative;
            width: 80px;
            height: 80px;
            margin-bottom: 1.5rem;
            
            .ring {
              position: absolute;
              width: 100%;
              height: 100%;
              border-radius: 50%;
              border: 3px solid transparent;
              border-top-color: #4f46e5;
              animation: spin 1.5s linear infinite;
              
              &:nth-child(2) {
                border: 3px solid transparent;
                border-bottom-color: #4f46e5;
                animation: spin 2s linear infinite;
              }
            }
            
            .dot {
              position: absolute;
              top: 50%;
              left: 50%;
              transform: translate(-50%, -50%);
              width: 15px;
              height: 15px;
              border-radius: 50%;
              background-color: #4f46e5;
              animation: pulse 1s ease infinite alternate;
            }
          }
          
          .loading-text {
            font-weight: 500;
            color: #334155;
            font-size: 1.125rem;
          }
        }
        
        /* Results grid */
        .results-grid {
          display: grid;
          grid-template-columns: 1fr;
          gap: 1.5rem;
          margin-bottom: 2rem;
          
          @media (min-width: 768px) {
            grid-template-columns: repeat(2, 1fr);
          }
          
          @media (min-width: 1200px) {
            grid-template-columns: repeat(3, 1fr);
          }
          
          .result-card {
            display: flex;
            flex-direction: column;
            background-color: white;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            overflow: hidden;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            
            &:hover {
              transform: translateY(-3px);
              box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
            }
            
            .card-header {
              display: flex;
              align-items: center;
              gap: 0.75rem;
              padding: 1rem;
              
              &.decimer {
                background: linear-gradient(135deg, rgba(249, 115, 22, 0.1) 0%, rgba(249, 115, 22, 0.2) 100%);
                border-bottom: 2px solid rgba(249, 115, 22, 0.3);
                
                .engine-icon {
                  color: #f97316;
                }
              }
              
              &.molnextr {
                background: linear-gradient(135deg, rgba(14, 165, 233, 0.1) 0%, rgba(14, 165, 233, 0.2) 100%);
                border-bottom: 2px solid rgba(14, 165, 233, 0.3);
                
                .engine-icon {
                  color: #0ea5e9;
                }
              }
              
              &.molscribe {
                background: linear-gradient(135deg, rgba(168, 85, 247, 0.1) 0%, rgba(168, 85, 247, 0.2) 100%);
                border-bottom: 2px solid rgba(168, 85, 247, 0.3);
                
                .engine-icon {
                  color: #a855f7;
                }
              }
              
              .engine-icon-wrapper {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 36px;
                height: 36px;
                border-radius: 8px;
                background-color: white;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
              }
              
              .engine-name {
                font-size: 1rem;
                font-weight: 700;
                margin: 0;
                color: #0f172a;
              }
            }
            
            .card-body {
              flex: 1;
              display: flex;
              flex-direction: column;
              padding: 1rem;
              
              .result-image-container {
                flex: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 220px;
                background-color: white;
                border-radius: 8px;
                border: 1px solid #e2e8f0;
                margin-bottom: 1rem;
                padding: 1rem;
                
                .result-image {
                  max-width: 100%;
                  max-height: 180px;
                  object-fit: contain;
                }
                
                .error-result {
                  display: flex;
                  flex-direction: column;
                  align-items: center;
                  justify-content: center;
                  gap: 0.75rem;
                  text-align: center;
                  padding: 1.5rem;
                  background-color: #fee2e2;
                  border-radius: 8px;
                  
                  .error-icon {
                    color: #ef4444;
                  }
                  
                  p {
                    margin: 0;
                    color: #b91c1c;
                    font-size: 0.875rem;
                    font-weight: 500;
                  }
                }
                
                .empty-result {
                  display: flex;
                  flex-direction: column;
                  align-items: center;
                  justify-content: center;
                  gap: 0.75rem;
                  text-align: center;
                  color: #64748b;
                  
                  .empty-icon {
                    color: #94a3b8;
                  }
                  
                  p {
                    margin: 0;
                    font-size: 0.875rem;
                  }
                }
              }
              
              .result-smiles {
                background-color: #f8fafc;
                border-radius: 8px;
                padding: 0.75rem;
                
                .smiles-header {
                  font-weight: 600;
                  margin-bottom: 0.375rem;
                  font-size: 0.8125rem;
                  color: #334155;
                }
                
                .smiles-value {
                  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
                  font-size: 0.8125rem;
                  color: #334155;
                  word-break: break-all;
                }
              }
            }
          }
        }
        
        .comparison-footer {
          display: flex;
          justify-content: center;
          margin-top: 1rem;
          
          .refresh-btn {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            background-color: #4f46e5;
            color: white;
            border: none;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            font-weight: 500;
            font-size: 0.9375rem;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 2px 8px rgba(79, 70, 229, 0.25);
            
            .refresh-icon {
              opacity: 0.9;
            }
            
            &:hover:not(:disabled) {
              background-color: #4338ca;
              box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
              transform: translateY(-1px);
            }
            
            &:disabled {
              background-color: #818cf8;
              opacity: 0.7;
              cursor: not-allowed;
            }
          }
        }
      }
    }
  }

  /* Context View Modal */
  .context-view-container {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.8);
    z-index: 100;
    display: flex;
    flex-direction: column;
    padding: 2rem;
    
    .context-view-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
      
      h3 {
        color: white;
        margin: 0;
      }
      
      .btn-close {
        background: none;
        border: none;
        color: white;
        cursor: pointer;
        
        &:hover {
          color: #ff4d4f;
        }
      }
    }
    
    .context-view-content {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: auto;
      
      .context-image {
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
        border: 2px solid white;
        box-shadow: 0 0 20px rgba(0, 0, 0, 0.5);
      }
      
      .loading-context {
        display: flex;
        align-items: center;
        justify-content: center;
        
        .loader-pulse {
          width: 60px;
          height: 60px;
          border-radius: 50%;
          background-color: rgba(255, 255, 255, 0.2);
          animation: pulse 1.5s ease-in-out infinite;
          
          &:before, &:after {
            content: '';
            position: absolute;
            height: 100%;
            width: 100%;
            background-color: rgba(255, 255, 255, 0.2);
            border-radius: 50%;
            z-index: -1;
            opacity: 0.7;
          }
          
          &:before {
            animation: pulse 1.5s ease-in-out infinite;
            animation-delay: 0.3s;
          }
          
          &:after {
            animation: pulse 1.5s ease-in-out infinite;
            animation-delay: 0.6s;
          }
        }
      }
      
      .context-error {
        display: flex;
        flex-direction: column;
        align-items: center;
        color: white;
        
        p {
          margin-top: 1rem;
        }
      }
    }
  }
}

/* Animations */
@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@keyframes pulse {
  0% { transform: scale(0.8); opacity: 0.7; }
  100% { transform: scale(1.2); opacity: 1; }
}

@keyframes subtle-pulse {
  0% { transform: scale(1); box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2); }
  50% { transform: scale(1.03); box-shadow: 0 4px 8px rgba(79, 70, 229, 0.4); }
  100% { transform: scale(1); box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2); }
}

/* Mobile specific styling */
@media (max-width: 768px) {
  .segment-viewer {
    padding: 0.75rem;
    
    .segment-header {
      padding: 0.5rem;
      margin: -0.5rem -0.5rem 0.5rem -0.5rem;
    }
    
    .content-panels {
      flex-direction: column;
      
      .panel {
        width: 100%;
        margin-bottom: 1rem;
      }
    }
    
    .compare-callout {
      flex-direction: column;
      text-align: center;
      
      .callout-icon {
        margin-right: 0;
        margin-bottom: 0.5rem;
      }
      
      .callout-text {
        margin-bottom: 0.75rem;
      }
      
      .compare-btn {
        width: 100%;
        justify-content: center;
      }
    }
  }
}
</style>