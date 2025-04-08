<template>
  <div class="segments-panel">
    <div v-if="!hasSegments" class="empty-state">
      <vue-feather type="image" size="48" class="empty-icon"></vue-feather>
      <h3>No Structures Extracted Yet</h3>
      <p>Upload a PDF and click "Extract Structures" to view chemical structure segments here.</p>
    </div>
    
    <div v-else-if="isLoading" class="loading-state">
      <vue-feather type="loader" class="loading-icon spin"></vue-feather>
      <p>Loading segments...</p>
    </div>
    
    <div v-else class="segments-content">
      <div class="segments-actions">
        <ModelSelector 
          v-model="selectedModel"
          :disabled="isLoadingStructures"
          @update:options="updateModelOptions"
        />
        
        <button 
          class="btn btn-primary"
          @click="processStructures"
          :disabled="isLoadingStructures || !segments.length"
        >
          <span v-if="!isLoadingStructures">
            <vue-feather type="codepen" class="icon"></vue-feather>
            Get Structures
          </span>
          <span v-else class="loading-text">
            <vue-feather type="loader" class="icon spin"></vue-feather>
            Processing...
          </span>
        </button>
      </div>
      
      <div class="segments-grid">
        <div 
          v-for="segment in sortedSegments" 
          :key="segment.id" 
          class="segment-item"
          :class="{ 'has-structure': hasStructureForSegment(segment) }"
          @click="selectSegment(segment)"
        >
          <div class="segment-card">
            <div class="segment-image">
              <img 
                :src="getSegmentImageUrl(segment)" 
                :alt="segment.filename"
                @error="handleImageError($event, segment)"
                @load="handleImageSuccess($event, segment)"
              />
            </div>
            
            <div v-if="hasStructureForSegment(segment)" class="structure-result">
              <h4 class="structure-title">
                <vue-feather type="hexagon" class="icon"></vue-feather>
                Structure
              </h4>
              
              <!-- Use our improved depiction component for visualization -->
              <ImprovedChemicalStructureViewer 
                :smiles="getStructureSmiles(segment)"
                :molfile="getStructureMolfile(segment)"
                :name="getStructureName(segment)"
                :source-engine="getStructureEngine(segment)"
                :use-coordinates="shouldUseCoordinates(segment)"
              />
            </div>
            
            <div class="segment-info">
              <span class="segment-id">{{ segment.filename }}</span>
              <div v-if="showDebugInfo" class="debug-info">
                <small>ID: {{ segment.id }}</small>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Detailed segment viewer modal -->
    <div v-if="selectedSegment" class="segment-modal-backdrop" @click.self="closeDetailView">
      <div class="segment-modal">
        <SegmentViewer 
          :segment="selectedSegment"
          :processed-structure="getStructureForSegment(selectedSegment)"
          :is-processing="isProcessingSegment"
          @close="closeDetailView"
          @process-segment="processSingleSegment"
          @run-comparison="runComparisonForSegment"
          @error="handleSegmentViewerError"
          @copy-complete="handleCopyComplete"
          @download-complete="handleDownloadComplete"
          @notification="handleNotification"
        />
      </div>
    </div>
  </div>
</template>

<script>
import ModelSelector from './ModelSelector.vue'
import SegmentViewer from './SegmentViewer.vue'
import ImprovedChemicalStructureViewer from './ImprovedChemicalStructureViewer.vue'
import ocsrService from '@/services/ocsrService'
import { mapState } from 'vuex'

export default {
  name: 'SegmentsPanel',
  components: {
    ModelSelector,
    SegmentViewer,
    ImprovedChemicalStructureViewer
  },
  props: {
    segments: {
      type: Array,
      default: () => []
    },
    convertedStructures: {
      type: Array,
      default: () => []
    },
    isLoadingStructures: {
      type: Boolean,
      default: false
    },
    currentPdfId: {
      type: String,
      default: null
    }
  },
  data() {
    return {
      selectedModel: 'decimer',
      isLoading: false,
      modelOptions: {
        handDrawn: false,
        includeMolfile: false
      },
      imageErrors: {},
      imageSuccess: {},
      selectedSegment: null,
      isProcessingSegment: false,
      comparisonEngines: ['decimer', 'molnextr', 'molscribe'],
      showDebugInfo: process.env.NODE_ENV === 'development' || false,
      // Track processedStructuresMap by filename
      processedStructuresMap: new Map()
    }
  },
  computed: {
    hasSegments() {
      return this.segments && this.segments.length > 0
    },
    ...mapState({
      segmentsDirectory: state => state.structures.segmentsDirectory,
      storeCurrentPdfId: state => state.structures.currentPdfId
    }),
    // Use the currentPdfId from props or from the store
    effectivePdfId() {
      return this.currentPdfId || this.storeCurrentPdfId;
    },
    // Sort segments by filename
    sortedSegments() {
      if (!this.segments || !this.segments.length) return [];
      
      return [...this.segments].sort((a, b) => {
        // First check if both have filenames
        if (a.filename && b.filename) {
          // Extract page and segment numbers for more intelligent sorting
          const aMatch = a.filename.match(/page_(\d+)_(\d+)_segmented/);
          const bMatch = b.filename.match(/page_(\d+)_(\d+)_segmented/);
          
          if (aMatch && bMatch) {
            // First sort by page number
            const aPage = parseInt(aMatch[1], 10);
            const bPage = parseInt(bMatch[1], 10);
            
            if (aPage !== bPage) {
              return aPage - bPage;
            }
            
            // Then sort by segment number within the page
            const aSegment = parseInt(aMatch[2], 10);
            const bSegment = parseInt(bMatch[2], 10);
            return aSegment - bSegment;
          }
          
          // If pattern doesn't match, use basic string comparison
          return a.filename.localeCompare(b.filename);
        }
        
        // If no filename, try to use id
        if (a.id && b.id) {
          return a.id.localeCompare(b.id);
        }
        
        // Fall back to segment number if available
        const getSegmentNumber = (segment) => {
          if (segment.id) {
            const match = segment.id.match(/segment-(\d+)/);
            if (match && match[1]) {
              return parseInt(match[1], 10);
            }
          }
          return 0; // Default if no number found
        };
        
        return getSegmentNumber(a) - getSegmentNumber(b);
      });
    }
  },
  watch: {
  // Reset image errors when segments change
  segments(newSegments, oldSegments) {
    // Check if this is a new set of segments from a different PDF
    const oldPdfId = oldSegments && oldSegments.length > 0 ? 
      oldSegments[0].pdfId || this.storeCurrentPdfId : null;
    
    const newPdfId = newSegments && newSegments.length > 0 ? 
      newSegments[0].pdfId || this.storeCurrentPdfId : null;
    
    // If PDF ID changed or no segments, clear everything
    if (newPdfId !== oldPdfId || !newSegments || newSegments.length === 0) {
      console.log('PDF changed - clearing segment caches');
      this.imageErrors = {};
      this.imageSuccess = {};
      // Reset structures map when PDF changes
      this.processedStructuresMap = new Map();
    }
  },
    // Update our structures map when converted structures change
    convertedStructures: {
    handler(newStructures, oldStructures) {
      // Check if this is a completely new set of structures 
      const isNewStructureSet = !oldStructures || 
                               oldStructures.length === 0 || 
                               (newStructures && newStructures.length > 0 && 
                                oldStructures && oldStructures.length > 0 &&
                                newStructures[0].pdfId !== oldStructures[0].pdfId);
      
      // If this is a new set, clear the map first
      if (isNewStructureSet) {
        console.log('New structure set detected - clearing processed structures map');
        this.processedStructuresMap = new Map();
      }
      
      if (newStructures && newStructures.length) {
        // Add new structures to the map
        newStructures.forEach(structure => {
          if (structure.name) {
            // Only add structures from current PDF session
            if (!this.effectivePdfId || structure.pdfId === this.effectivePdfId) {
              // Index by name/filename for direct lookup
              this.processedStructuresMap.set(structure.name, structure);
              
              // Also index by uniqueKey if available
              if (structure.uniqueKey) {
                this.processedStructuresMap.set(structure.uniqueKey, structure);
              }
            }
          }
        });
          
        console.log(`Updated processed structures map with ${this.processedStructuresMap.size} entries`);
      }
    },
    immediate: true
  },
  
  // Add a watch for current PDF ID
  effectivePdfId(newPdfId, oldPdfId) {
    if (newPdfId !== oldPdfId) {
      console.log(`PDF ID changed from ${oldPdfId} to ${newPdfId} - clearing structures map`);
      this.processedStructuresMap = new Map();
    }
  }
},
  methods: {
    getSegmentImageUrl(segment) {
      // If image has error, use a placeholder or return the original URL
      if (this.imageErrors[segment.id]) {
        return `/assets/placeholder-structure.png`
      }
      
      return segment.imageUrl || segment.path || ''
    },
    handleImageError(event, segment) {
      this.imageErrors[segment.id] = true
      console.error(`Error loading image for segment ${segment.id} with filename ${segment.filename}`)
      this.$forceUpdate()
    },
    handleImageSuccess(event, segment) {
      this.imageSuccess[segment.id] = true
      console.log(`Successfully loaded image for segment ${segment.id}: ${segment.filename}`)
    },
    updateModelOptions(options) {
      this.modelOptions = { ...this.modelOptions, ...options }
      
      // Auto-enable includeMolfile for molnextr and molscribe engines
      if (options.model) {
        const engine = options.model
        if (engine === 'molnextr' || engine === 'molscribe') {
          this.modelOptions.includeMolfile = true
        }
      }
    },
    hasStructureForSegment(segment) {
      if (!segment) return false
      
      // Get structure for this segment
      const structure = this.getStructureForSegment(segment)
      return !!structure
    },
    getStructureForSegment(segment) {
  if (!segment) return null
  
  // Extract page and segment information
  let pageNum = 0;
  let segmentNum = 0;
  
  // Try to parse from ID or filename
  if (segment.id) {
    const pageMatch = segment.id.match(/page-(\d+)-segment-(\d+)/);
    if (pageMatch && pageMatch.length > 2) {
      pageNum = parseInt(pageMatch[1], 10);
      segmentNum = parseInt(pageMatch[2], 10);
    }
  }
  
  if (segment.filename) {
    const parts = segment.filename.split('_');
    if (parts.length > 2 && parts[0] === 'page') {
      // Override with filename info if available (more reliable)
      pageNum = parseInt(parts[1], 10) || pageNum;
      segmentNum = parts.length > 2 ? parseInt(parts[2], 10) || segmentNum : segmentNum;
    }
  }
  
  // 1. Try to match using our uniqueKey which combines page and segment numbers
  const uniqueKey = `page-${pageNum}-segment-${segmentNum}`;
  let structure = this.convertedStructures.find(s => 
    s.uniqueKey === uniqueKey || s.segmentId === uniqueKey
  );
  if (structure) return structure;
  
  // 2. Try exact filename match (high confidence match)
  if (segment.filename) {
    structure = this.convertedStructures.find(s => 
      s.name === segment.filename || s.filename === segment.filename
    );
    if (structure) return structure;
  }
  
  // 3. Try to match by page and segment index explicitly
  if (segment.pageIndex !== undefined && segment.segmentNumber !== undefined) {
    structure = this.convertedStructures.find(s => 
      s.pageIndex === segment.pageIndex && s.segmentIndex === segment.segmentNumber
    );
    if (structure) return structure;
  }
  
  // 4. Try to match extracted page and segment numbers
  structure = this.convertedStructures.find(s => 
    (s.pageIndex === pageNum || s.pageIndex === segment.pageIndex) && 
    (s.segmentIndex === segmentNum || s.segmentIndex === segment.segmentNumber)
  );
  if (structure) return structure;
  
  // 5. As a last resort, fall back to previous methods
  structure = this.convertedStructures.find(s => s.segmentId === segment.id);
  
  if (!structure && segment.path) {
    structure = this.convertedStructures.find(s => 
      (s.segmentUrl && s.segmentUrl.includes(segment.path)) ||
      (segment.path && segment.path.includes(s.segmentUrl))
    );
  }
  
  return structure;
},
    getStructureSmiles(segment) {
      const structure = this.getStructureForSegment(segment)
      return structure ? structure.smiles : ''
    },
    getStructureMolfile(segment) {
      const structure = this.getStructureForSegment(segment)
      return structure ? structure.molfile : null
    },
    getStructureName(segment) {
      return segment.filename
    },
    getStructureEngine(segment) {
      const structure = this.getStructureForSegment(segment)
      return structure ? structure.engine : ''
    },
    processStructures() {
      // When processing structures, include current model options
      // Important: Pass sorted segments to maintain proper processing order
      this.$emit('process-structures', {
        model: this.selectedModel,
        ...this.modelOptions,
        segments: this.sortedSegments, // Use sorted segments for consistent processing
        pdfId: this.effectivePdfId
      })
    },
    selectSegment(segment) {
      this.selectedSegment = segment
    },
    closeDetailView() {
      this.selectedSegment = null
    },
    handleNotification(notification) {
      this.$emit('notification', notification)
    },
    async processSingleSegment(segment) {
      if (!segment) return
      
      this.isProcessingSegment = true
      
      try {
        // Generate a unique ID for this processing run
        const processId = `manual-${Date.now()}-${segment.id}`
        console.log(`[${processId}] Processing single segment: ${segment.id} - ${segment.filename}`)
        
        // Get the correct image path for this segment
        const imagePath = segment.path
        console.log(`[${processId}] Using image path: ${imagePath}`)
        
        // Set up options based on current model settings
        const options = {
          engine: this.selectedModel,
          handDrawn: this.modelOptions.handDrawn,
          includeMolfile: this.modelOptions.includeMolfile || 
                        (this.selectedModel === 'molnextr' || this.selectedModel === 'molscribe')
        }
        
        // Process the segment with OCSR service
        console.log(`[${processId}] Calling OCSR service with options:`, options)
        const result = await ocsrService.generateBoth(null, imagePath, options)
        console.log(`[${processId}] Got OCSR result:`, 
                  result.smiles ? `SMILES found (${result.smiles.length} chars)` : 'No SMILES')
        
        // Ensure segment has the correct pdfId
        const pdfId = segment.pdfId || this.effectivePdfId
        
        // Create structure object with the correct segmentId AND explicit filename
        const structure = {
          segmentId: segment.id, // Use segment.id for consistency
          originalSegmentId: segment.id, // Keep original in case of modifications
          imageUrl: segment.imageUrl || segment.path,
          filename: segment.filename, // IMPORTANT: Add explicit filename for reliable matching
          smiles: result.smiles || '',
          molfile: result.molfile || null,
          engine: result.engine || options.engine,
          name: segment.filename, // IMPORTANT: This is used for matching
          pdfId: pdfId,
          useCoordinates: options.includeMolfile && 
                         (options.engine === 'molnextr' || options.engine === 'molscribe'),
          processId: processId,
          timestamp: new Date().toISOString()
        }
        
        console.log(`[${processId}] Created structure object for ${structure.name}`)
        
        // Add directly to our map for immediate availability
        this.processedStructuresMap.set(segment.filename, structure);
        
        // Add structure to the list of converted structures
        this.$emit('add-structure', structure)
        
        // Show success notification
        this.$emit('notification', {
          type: 'success',
          message: `Successfully processed segment ${segment.filename}`
        })
      } catch (error) {
        console.error('Error processing segment:', error)
        
        // Create error structure object
        const errorStructure = {
          segmentId: segment.id, // Use segment.id for consistency
          imageUrl: segment.imageUrl || segment.path,
          filename: segment.filename, // IMPORTANT: Add explicit filename for reliable matching
          smiles: '',
          molfile: null,
          engine: this.selectedModel,
          name: segment.filename, // IMPORTANT: This is used for matching
          pdfId: segment.pdfId || this.effectivePdfId,
          error: error.message || 'Failed to process segment',
          timestamp: new Date().toISOString()
        }
        
        // Add to our map for immediate availability
        this.processedStructuresMap.set(segment.filename, errorStructure);
        
        // Add error structure to the list
        this.$emit('add-structure', errorStructure)
        
        // Show error notification
        this.$emit('notification', {
          type: 'error',
          message: `Failed to process segment: ${error.message}`
        })
      } finally {
        this.isProcessingSegment = false
      }
    },
    async runComparisonForSegment(segment) {
      if (!segment) return
      
      this.isProcessingSegment = true
      
      try {
        // Generate a unique ID for this comparison run
        const comparisonId = `comparison-${Date.now()}`
        console.log(`[${comparisonId}] Running comparison for segment: ${segment.id} - ${segment.filename}`)
        
        // Get the correct image path for this segment
        const imagePath = segment.path
        console.log(`[${comparisonId}] Using image path: ${imagePath}`)
        
        // Process with all engines in parallel
        const promises = this.comparisonEngines.map(engine => {
          return this.processWithEngine(imagePath, engine, segment, comparisonId)
        })
        
        // Wait for all engines to complete
        await Promise.all(promises)
        
        // Show success notification
        this.$emit('notification', {
          type: 'success',
          message: `Comparison completed for segment ${segment.filename}`
        })
      } catch (error) {
        console.error('Error running comparison:', error)
        
        // Show error notification
        this.$emit('notification', {
          type: 'error',
          message: `Failed to run comparison: ${error.message}`
        })
      } finally {
        this.isProcessingSegment = false
      }
    },
    async processWithEngine(imagePath, engine, segment, comparisonId) {
      try {
        console.log(`[${comparisonId}] Processing with engine ${engine} for ${segment.filename}`)
        
        // Set up options for this engine
        const options = {
          engine: engine,
          handDrawn: false,
          includeMolfile: engine !== 'decimer' // Always use molfile for non-DECIMER engines
        }
        
        // Process the segment with this engine
        const result = await ocsrService.generateBoth(null, imagePath, options)
        console.log(`[${comparisonId}] Got result for ${engine} with segment ${segment.filename}`)
        
        // Create unique structure ID for this engine
        const structureId = `${segment.id}-${engine}-comparison`
        
        // Ensure segment has the correct pdfId
        const pdfId = segment.pdfId || this.effectivePdfId
        
        // Create structure object with explicit filename for matching
        const structure = {
          segmentId: structureId, // Use unique ID for each engine
          originalSegmentId: segment.id, // Keep reference to original segment
          imageUrl: segment.imageUrl || segment.path,
          filename: `${segment.filename}-${engine}`, // Unique filename for each engine's result
          smiles: result.smiles || '',
          molfile: result.molfile || null,
          engine: engine,
          name: `${segment.filename} (${engine})`,
          pdfId: pdfId,
          useCoordinates: options.includeMolfile,
          comparison: true, // Mark as comparison result
          comparisonId: comparisonId,
          timestamp: new Date().toISOString()
        }
        
        console.log(`[${comparisonId}] Created structure for ${engine}: ${structureId}`)
        
        // Add to our map for immediate availability
        this.processedStructuresMap.set(`${segment.filename}-${engine}`, structure);
        
        // Add structure to the list of converted structures
        this.$emit('add-structure', structure)
        
        return structure
      } catch (error) {
        console.error(`[${comparisonId}] Error processing with ${engine}:`, error)
        
        // Create error structure object
        const errorStructure = {
          segmentId: `${segment.id}-${engine}-comparison`,
          originalSegmentId: segment.id,
          imageUrl: segment.imageUrl || segment.path,
          filename: `${segment.filename}-${engine}`, // Unique filename for each engine's result
          smiles: '',
          molfile: null,
          engine: engine,
          name: `${segment.filename} (${engine})`,
          pdfId: segment.pdfId || this.effectivePdfId,
          error: error.message || `Failed to process with ${engine}`,
          comparison: true,
          comparisonId: comparisonId,
          timestamp: new Date().toISOString()
        }
        
        // Add error structure to our map
        this.processedStructuresMap.set(`${segment.filename}-${engine}`, errorStructure);
        
        // Add error structure to the list
        this.$emit('add-structure', errorStructure)
        
        return errorStructure
      }
    },
    handleSegmentViewerError(message) {
      this.$emit('notification', {
        type: 'error',
        message
      })
    },
    handleCopyComplete(message) {
      this.$emit('notification', {
        type: 'success',
        message
      })
    },
    handleDownloadComplete(message) {
      this.$emit('notification', {
        type: 'success',
        message
      })
    },
    shouldUseCoordinates(segment) {
      // Get structure for this segment
      const structure = this.getStructureForSegment(segment)
      if (!structure) return false
      
      // First check if useCoordinates flag is explicitly set
      if (structure.useCoordinates === true) {
        return true
      }
      
      // Otherwise determine based on engine type and available molfile data
      return !!structure.molfile && 
        (structure.engine === 'molnextr' || structure.engine === 'molscribe')
    }
  }
}
</script>

<style lang="scss" scoped>
.segments-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  
  .empty-state, .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    height: 100%;
    min-height: 200px;
    
    .empty-icon, .loading-icon {
      color: var(--color-text-light);
      margin-bottom: 0.5rem;
    }
    
    .loading-icon.spin {
      animation: spin 1s linear infinite;
      color: var(--color-primary);
    }
    
    h3 {
      margin-bottom: 0.5rem;
    }
    
    p {
      color: var(--color-text-light);
    }
  }
  
  .segments-content {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    
    .segments-actions {
      display: flex;
      flex-direction: row;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 0.75rem;
      flex-shrink: 0;
      
      .btn {
        flex: 0 0 auto;
        white-space: nowrap;
      }
      
      .icon {
        width: 16px;
        height: 16px;
      }
      
      .loading-text {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.25rem;
      }
      
      .spin {
        animation: spin 1s linear infinite;
      }
    }
    
    .segments-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 0.5rem;
      overflow-y: auto;
      height: 100%;
      padding: 0.25rem;
      
      @media (min-width: 640px) {
        grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      }
      
      @media (min-width: 768px) {
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
      }
      
      @media (min-width: 1024px) {
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      }
      
      @media (min-width: 1280px) {
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      }
    }
    
    .segment-item {
      cursor: pointer;
      transition: transform 0.2s ease;
      
      &:hover {
        transform: translateY(-2px);
      }
      
      .segment-card {
        background-color: var(--color-card-bg);
        border-radius: 4px;
        overflow: hidden;
        height: 100%;
        display: flex;
        flex-direction: column;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
      }
      
      &.has-structure .segment-card {
        border: 1px solid var(--color-primary-light);
      }
      
      .segment-image {
        flex: 1;
        display: flex;
        justify-content: center;
        align-items: center;
        background-color: #fff;
        padding: 0.5rem;
        max-height: 280px;
        
        img {
          width: 100%;
          height: 100%;
          object-fit: contain;
          max-height: 280px;
        }
      }
      
      .segment-info {
        padding: 0.25rem 0.5rem;
        border-top: 1px solid var(--color-border);
        font-size: 0.7rem;
        color: var(--color-text-light);
        text-align: center;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        
        .segment-id {
          font-family: monospace;
          font-size: medium;
          font-size: 10px;
        }
      }
      
      .structure-result {
        padding: 0.5rem;
        border-top: 1px solid var(--color-border);
        background-color: rgba(74, 77, 231, 0.05);
        
        .structure-title {
          display: flex;
          align-items: center;
          gap: 0.25rem;
          font-size: 0.8rem;
          margin-bottom: 0.5rem;
          
          .icon {
            color: var(--color-primary);
          }
        }
      }
    }
  }
  
  .segment-modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.5);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
    
    .segment-modal {
      background-color: var(--color-bg);
      border-radius: var(--radius-lg);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
      width: 100%;
      max-width: 1000px;
      max-height: 90vh;
      overflow-y: auto;
      padding: 1.5rem;
    }
  }
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>