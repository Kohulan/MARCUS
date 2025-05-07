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
        <ModelSelector v-model="selectedModel" :disabled="isLoadingStructures" @update:options="updateModelOptions" />

        <button class="btn btn-primary" @click="processStructures"
          :disabled="isLoadingStructures || !visibleSegments.length">
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

      <!-- New filter bar with segment selection options -->
      <div class="segments-filter-bar">
        <div class="filter-section">
          <span class="filter-section-label">Selection:</span>
          <div class="filter-options">
            <label class="filter-option">
              <input type="checkbox" v-model="hideIncorrectSegments" @change="toggleHideIncorrect">
              <span>Hide incorrect segments</span>
            </label>

            <label class="filter-option">
              <input type="checkbox" v-model="onlyProcessSelected" @change="toggleOnlyProcessSelected">
              <span>Only process selected segments</span>
            </label>
          </div>
        </div>

        <div class="filter-stats">
          <span class="stats-item">
            <span class="stats-value">{{ selectedSegmentCount }}</span> selected /
            <span class="stats-value">{{ visibleSegments.length }}</span> visible
          </span>
          <button class="select-all-btn" @click="selectAllVisible" :disabled="!sortedVisibleSegments.length">
            <vue-feather type="check-square" size="14"></vue-feather>
            <span>Select All Visible</span>
          </button>
          <button class="clear-selection-btn" @click="clearSelection" :disabled="selectedSegmentCount === 0">
            <vue-feather type="square" size="14"></vue-feather>
            <span>Clear Selection</span>
          </button>
        </div>
      </div>

      <div class="segments-grid">
        <div v-for="segment in sortedVisibleSegments" :key="segment.id" class="segment-item" :class="{
          'has-structure': hasStructureForSegment(segment),
          'is-selected': isSegmentSelected(segment.id)
        }">
          <div class="segment-card">
            <!-- Selection checkbox overlay -->
            <div class="segment-selection">
              <label class="selection-checkbox" @click.stop>
                <input type="checkbox" :checked="isSegmentSelected(segment.id)"
                  @change="toggleSegmentSelection(segment.id)">
                <span class="checkmark"></span>
              </label>
            </div>

            <div class="segment-image" @click="selectSegment(segment)">
              <img :src="getSegmentImageUrl(segment)" :alt="segment.filename" @error="handleImageError($event, segment)"
                @load="handleImageSuccess($event, segment)" />
            </div>

            <div v-if="hasStructureForSegment(segment)" class="structure-result">
              <h4 class="structure-title">
                <vue-feather type="hexagon" class="icon"></vue-feather>
                Structure
              </h4>

              <!-- Use our improved depiction component for visualization -->
              <ImprovedChemicalStructureViewer :smiles="getStructureSmiles(segment)"
                :molfile="getStructureMolfile(segment)" :name="getStructureName(segment)"
                :source-engine="getStructureEngine(segment)" :use-coordinates="shouldUseCoordinates(segment)" />
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
        <SegmentViewer :segment="selectedSegment" :processed-structure="getStructureForSegment(selectedSegment)"
          :is-processing="isProcessingSegment" :is-selected="isSegmentSelected(selectedSegment.id)"
          @close="closeDetailView" @process-segment="processSingleSegment" @run-comparison="runComparisonForSegment"
          @error="handleSegmentViewerError" @copy-complete="handleCopyComplete"
          @download-complete="handleDownloadComplete" @notification="handleNotification"
          @toggle-selection="toggleSegmentSelection(selectedSegment.id)"
          @prediction-selected="handlePredictionSelected" />
      </div>
    </div>
  </div>
</template>

<script>
import ModelSelector from './ModelSelector.vue'
import SegmentViewer from './SegmentViewer.vue'
import ImprovedChemicalStructureViewer from './ImprovedChemicalStructureViewer.vue'
import ocsrService from '@/services/ocsrService'
import { mapState, mapGetters, mapActions } from 'vuex'
import { getApiImageUrl } from '@/services/api'

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
      processedStructuresMap: new Map(),
      // New UI state properties
      hideIncorrectSegments: false,
      onlyProcessSelected: true
    }
  },
  computed: {
    hasSegments() {
      return this.segments && this.segments.length > 0
    },
    ...mapState({
      segmentsDirectory: state => state.structures.segmentsDirectory,
      storeCurrentPdfId: state => state.structures.currentPdfId,
      storeHideIncorrectSegments: state => state.structures.hideIncorrectSegments,
      storeOnlyProcessSelected: state => state.structures.onlyProcessSelected
    }),
    ...mapGetters('structures', [
      'visibleSegments',
      'isSegmentSelected',
      'selectedSegmentCount'
    ]),
    // Use the currentPdfId from props or from the store
    effectivePdfId() {
      return this.currentPdfId || this.storeCurrentPdfId;
    },
    // Sort segments by page number and segment number
    sortedVisibleSegments() {
      if (!this.visibleSegments || !this.visibleSegments.length) return [];
      
      return [...this.visibleSegments].sort((a, b) => {
        // Extract page and segment numbers
        const getPageAndSegment = (segment) => {
          let pageNum = 0;
          let segmentNum = 0;
          
          // Try to parse from ID first
          if (segment.id) {
            const pageMatch = segment.id.match(/page-(\d+)-segment-(\d+)/);
            if (pageMatch && pageMatch.length > 2) {
              pageNum = parseInt(pageMatch[1], 10);
              segmentNum = parseInt(pageMatch[2], 10);
            }
          }
          
          // Override with filename info if available (more reliable)
          if (segment.filename) {
            const parts = segment.filename.split('_');
            if (parts.length > 2 && parts[0] === 'page') {
              pageNum = parseInt(parts[1], 10) || pageNum;
              segmentNum = parts.length > 2 ? parseInt(parts[2], 10) || segmentNum : segmentNum;
            }
          }
          
          return { pageNum, segmentNum };
        };
        
        const aInfo = getPageAndSegment(a);
        const bInfo = getPageAndSegment(b);
        
        // Sort by page number first, then by segment number
        if (aInfo.pageNum !== bInfo.pageNum) {
          return aInfo.pageNum - bInfo.pageNum;
        }
        
        return aInfo.segmentNum - bInfo.segmentNum;
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
    },

    // Sync store values to local state
    storeHideIncorrectSegments: {
      handler(newValue) {
        this.hideIncorrectSegments = newValue;
      },
      immediate: true
    },

    storeOnlyProcessSelected: {
      handler(newValue) {
        this.onlyProcessSelected = newValue;
      },
      immediate: true
    }
  },
  methods: {
    ...mapActions('structures', [
      'setSegmentSelection',
      'toggleSegmentSelection',
      'setHideIncorrectSegments',
      'setOnlyProcessSelected'
    ]),

    getSegmentImageUrl(segment) {
      // If image has error, use a placeholder 
      if (this.imageErrors[segment.id]) {
        return ''; // Return empty string instead of placeholder
      }

      // Use the environment-aware URL helper for consistent URL generation
      let url;
      if (segment.imageUrl) {
        url = getApiImageUrl(segment.imageUrl);
      } else if (segment.path) {
        // Pass just the segment path to let the helper construct the URL correctly
        url = getApiImageUrl(segment.path);
      } else {
        url = '';
      }
      
      // Debug logging
      console.log(`Segment image URL for ${segment.id} (${segment.filename}):`, url);
      console.log(`Original segment path:`, segment.path);
      
      return url;
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
        segments: this.sortedVisibleSegments, // Use sorted visible segments
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

    // New methods for segment selection
    toggleHideIncorrect() {
      this.setHideIncorrectSegments(this.hideIncorrectSegments)
    },

    toggleOnlyProcessSelected() {
      this.setOnlyProcessSelected(this.onlyProcessSelected)
    },

    selectAllVisible() {
      if (!this.sortedVisibleSegments.length) return

      this.sortedVisibleSegments.forEach(segment => {
        this.setSegmentSelection({
          segmentId: segment.id,
          selected: true
        })
      })

      this.$emit('notification', {
        type: 'success',
        message: `Selected all ${this.sortedVisibleSegments.length} visible segments`
      })
    },

    clearSelection() {
      // Create an array of segments to deselect
      const segmentsToDeselect = this.sortedVisibleSegments.filter(segment =>
        this.isSegmentSelected(segment.id)
      )

      // Deselect all segments
      segmentsToDeselect.forEach(segment => {
        this.setSegmentSelection({
          segmentId: segment.id,
          selected: false
        })
      })

      this.$emit('notification', {
        type: 'info',
        message: 'Cleared selection'
      })
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

        // Auto-select this segment if it was processed successfully
        if (result.smiles) {
          this.setSegmentSelection({
            segmentId: segment.id,
            selected: true
          })
        }
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

        // Auto-select this segment when successful comparison is done
        this.setSegmentSelection({
          segmentId: segment.id,
          selected: true
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
    },
    /**
     * Handle the selection of a prediction from comparison view
     */
    handlePredictionSelected(updatedStructure) {
      if (!updatedStructure || !updatedStructure.segmentId) return;

      // Update the structure in the store
      this.$store.dispatch('structures/updateStructureWithPrediction', {
        segmentId: updatedStructure.segmentId,
        newStructure: updatedStructure
      });

      // Show notification 
      this.$store.dispatch('showNotification', {
        type: 'success',
        message: `Updated structure with ${this.getDisplayEngineName(updatedStructure.engine)} prediction`
      });
    },

    /**
     * Get a display name for an engine
     */
    getDisplayEngineName(engine) {
      if (!engine) return 'Unknown';

      const displayNames = {
        'decimer': 'DECIMER',
        'molnextr': 'MolNexTR',
        'molscribe': 'MolScribe'
      };

      return displayNames[engine.toLowerCase()] || engine;
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
  background: linear-gradient(145deg, #f8fafc 0%, #eef2ff 100%);
  border-radius: 20px;
  padding: 1.5rem;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);

  .empty-state,
  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    height: 100%;
    min-height: 300px;
    padding: 2rem;
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.5) 0%, rgba(243, 244, 246, 0.8) 100%);
    border-radius: 16px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.6);
    backdrop-filter: blur(10px);

    .empty-icon {
      color: #94a3b8;
      margin-bottom: 1.5rem;
      filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.1));
      animation: float 3s ease-in-out infinite;
    }

    .loading-icon {
      color: #4f46e5;
      margin-bottom: 1.5rem;
      filter: drop-shadow(0 4px 8px rgba(79, 70, 229, 0.3));

      &.spin {
        animation: spin 1.5s cubic-bezier(0.5, 0.1, 0.5, 0.9) infinite;
      }
    }

    h3 {
      margin-bottom: 1rem;
      font-size: 1.5rem;
      font-weight: 700;
      color: #334155;
      letter-spacing: -0.01em;
    }

    p {
      color: #64748b;
      font-size: 1.125rem;
      max-width: 400px;
      line-height: 1.6;
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
      gap: 0.875rem;
      margin-bottom: 1rem;
      flex-shrink: 0;

      .btn {
        flex: 0 0 auto;
        white-space: nowrap;
        padding: 0.75rem 1.25rem;
        border-radius: 12px;
        font-weight: 500;
        transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        font-size: 0.9375rem;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.06);
        position: relative;
        overflow: hidden;
        border: none;
        cursor: pointer;

        &::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          background: linear-gradient(135deg, rgba(255, 255, 255, 0.2) 0%, rgba(255, 255, 255, 0) 100%);
          opacity: 0;
          transition: opacity 0.3s ease;
          z-index: 1;
        }

        &:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);

          &::before {
            opacity: 1;
          }
        }

        &:active:not(:disabled) {
          transform: translateY(0);
        }

        &:disabled {
          opacity: 0.7;
          cursor: not-allowed;
        }

        &.btn-primary {
          background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);
          color: white;

          &:hover:not(:disabled) {
            background: linear-gradient(135deg, #4338ca 0%, #4f46e5 100%);
            box-shadow: 0 8px 16px rgba(79, 70, 229, 0.3);
          }
        }
      }

      .icon {
        width: 16px;
        height: 16px;
        position: relative;
        z-index: 2;
      }

      .loading-text {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        position: relative;
        z-index: 2;
      }

      .spin {
        animation: spin 1.5s cubic-bezier(0.5, 0.1, 0.5, 0.9) infinite;
      }
    }

    /* Enhanced segments filter bar styling */
    .segments-filter-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
      padding: 1rem 1.25rem;
      background: linear-gradient(135deg, rgba(79, 70, 229, 0.05) 0%, rgba(79, 70, 229, 0.12) 100%);
      border-radius: 16px;
      flex-wrap: wrap;
      gap: 0.875rem;
      border: 1px solid rgba(79, 70, 229, 0.2);
      box-shadow: 0 4px 12px rgba(79, 70, 229, 0.06);
      position: relative;
      overflow: hidden;

      &::before {
        content: '';
        position: absolute;
        top: -10px;
        right: -10px;
        width: 80px;
        height: 80px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(79, 70, 229, 0.3) 0%, transparent 70%);
        opacity: 0.4;
        z-index: 0;
      }

      .filter-section {
        display: flex;
        align-items: flex-start;
        flex-wrap: wrap;
        gap: 0.75rem;
        position: relative;
        z-index: 1;

        .filter-section-label {
          font-weight: 600;
          color: #334155;
          font-size: 0.9375rem;
          white-space: nowrap;
        }

        .filter-options {
          display: flex;
          flex-wrap: wrap;
          gap: 1rem;

          .filter-option {
            display: flex;
            align-items: center;
            gap: 0.625rem;
            cursor: pointer;
            font-size: 0.875rem;
            color: #475569;
            transition: color 0.2s ease;
            font-weight: 500;
            min-width: 0;

            &:hover {
              color: #4f46e5;
            }

            span {
              white-space: normal;
              line-height: 1.2;
            }

            input[type="checkbox"] {
              cursor: pointer;
              width: 18px;
              height: 18px;
              min-width: 18px;
              margin: 0;
              appearance: none;
              -webkit-appearance: none;
              background-color: white;
              border: 2px solid #cbd5e1;
              border-radius: 6px;
              transition: all 0.2s ease;
              position: relative;
              flex-shrink: 0;

              &:checked {
                background-color: #4f46e5;
                border-color: #4f46e5;
                box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.2);

                &::after {
                  content: '';
                  position: absolute;
                  top: 3px;
                  left: 6px;
                  width: 4px;
                  height: 8px;
                  border: solid white;
                  border-width: 0 2px 2px 0;
                  transform: rotate(45deg);
                }
              }

              &:hover {
                border-color: #4f46e5;
              }
            }
          }
        }
      }

      .filter-stats {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.875rem;
        position: relative;
        z-index: 1;

        .stats-item {
          font-size: 0.9375rem;
          color: #334155;
          font-weight: 500;
          white-space: nowrap;

          .stats-value {
            font-weight: 700;
            color: #4f46e5;
            background: linear-gradient(90deg, #4f46e5, #6366f1);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
          }
        }

        button {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.8125rem;
          padding: 0.5rem 0.75rem;
          border-radius: 10px;
          border: 1px solid rgba(226, 232, 240, 0.8);
          cursor: pointer;
          font-weight: 500;
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          position: relative;
          overflow: hidden;
          white-space: nowrap;

          &::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.2) 0%, rgba(255, 255, 255, 0) 100%);
            opacity: 0;
            transition: opacity 0.3s ease;
            z-index: 1;
          }

          svg {
            position: relative;
            z-index: 2;
            flex-shrink: 0;
          }

          span {
            position: relative;
            z-index: 2;
          }

          &:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.06);

            &::before {
              opacity: 1;
            }
          }

          &:active:not(:disabled) {
            transform: translateY(0);
          }

          &:disabled {
            opacity: 0.6;
            cursor: not-allowed;
          }

          &.select-all-btn {
            background-color: #f1f5f9;
            color: #334155;

            &:hover:not(:disabled) {
              background-color: #e2e8f0;
              border-color: #cbd5e1;
              color: #1e293b;
            }
          }

          &.clear-selection-btn {
            background-color: white;
            color: #64748b;

            &:hover:not(:disabled) {
              background-color: #fef2f2;
              border-color: #fecaca;
              color: #ef4444;
            }
          }
        }
      }

      @media (max-width: 768px) {
        flex-direction: column;
        align-items: stretch;
        gap: 1rem;
        padding: 1rem;

        .filter-section {
          width: 100%;
          flex-direction: column;
          align-items: flex-start;
        }

        .filter-options {
          width: 100%;
        }

        .filter-stats {
          width: 100%;
          justify-content: space-between;
          
          .stats-item {
            flex: 1;
          }
          
          button {
            min-width: auto;
            padding: 0.5rem;
            
            @media (max-width: 370px) {
              span {
                display: none;
              }
            }
          }
        }
      }
      
      @media (max-width: 480px) {
        .filter-stats {
          button {
            flex: 1;
            justify-content: center;
          }
        }
      }
    }

    .segments-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      gap: 1rem;
      overflow-y: auto;
      height: 100%;
      padding: 0.25rem 0.25rem 1rem 0.25rem;

      /* Customize scrollbar */
      &::-webkit-scrollbar {
        width: 8px;
      }

      &::-webkit-scrollbar-track {
        background: rgba(241, 245, 249, 0.6);
        border-radius: 8px;
      }

      &::-webkit-scrollbar-thumb {
        background: rgba(148, 163, 184, 0.5);
        border-radius: 8px;

        &:hover {
          background: rgba(100, 116, 139, 0.6);
        }
      }

      @media (min-width: 640px) {
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
      }

      @media (min-width: 768px) {
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      }

      @media (min-width: 1024px) {
        grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
      }

      @media (min-width: 1280px) {
        grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
      }

      .segment-item {
        cursor: pointer;
        transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        position: relative;

        &:hover {
          transform: translateY(-4px);

          .segment-card {
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.08);
          }
        }

        /* Selection state styling */
        &.is-selected .segment-card {
          box-shadow: 0 0 0 2px #4f46e5, 0 8px 20px rgba(79, 70, 229, 0.2);

          &::before {
            opacity: 1;
            background: linear-gradient(135deg, rgba(79, 70, 229, 0.1) 0%, rgba(79, 70, 229, 0.05) 100%);
          }

          .segment-selection .selection-checkbox .checkmark {
            background-color: #4f46e5;
            border-color: #4f46e5;
            box-shadow: 0 0 8px rgba(79, 70, 229, 0.4);

            &:after {
              display: block;
            }
          }
        }

        .segment-card {
          background-color: rgba(255, 255, 255, 0.85);
          border-radius: 16px;
          overflow: hidden;
          height: 100%;
          display: flex;
          flex-direction: column;
          box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
          position: relative;
          backdrop-filter: blur(10px);
          border: 1px solid rgba(255, 255, 255, 0.8);
          transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);

          &::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: transparent;
            opacity: 0;
            transition: opacity 0.3s ease;
            z-index: 0;
            pointer-events: none;
          }
        }

        /* Enhanced selection checkbox styling */
        .segment-selection {
          position: absolute;
          top: 10px;
          right: 10px;
          z-index: 5;

          .selection-checkbox {
            display: block;
            position: relative;
            padding-left: 0;
            cursor: pointer;
            user-select: none;

            input {
              position: absolute;
              opacity: 0;
              cursor: pointer;
              height: 0;
              width: 0;
            }

            .checkmark {
              position: relative;
              display: block;
              height: 24px;
              width: 24px;
              background-color: rgba(255, 255, 255, 0.95);
              border: 2px solid rgba(203, 213, 225, 0.8);
              border-radius: 8px;
              box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
              transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);

              &:after {
                content: "";
                position: absolute;
                display: none;
                left: 8px;
                top: 3px;
                width: 6px;
                height: 12px;
                border: solid white;
                border-width: 0 2px 2px 0;
                transform: rotate(45deg);
              }
            }

            &:hover .checkmark {
              border-color: #4f46e5;
              transform: scale(1.05);
            }

            input:checked~.checkmark {
              background-color: #4f46e5;
              border-color: #4f46e5;

              &:after {
                display: block;
              }
            }
          }
        }

        &.has-structure .segment-card {
          border: 1px solid rgba(79, 70, 229, 0.2);

          &::before {
            background: linear-gradient(135deg, rgba(79, 70, 229, 0.05) 0%, rgba(79, 70, 229, 0.01) 100%);
            opacity: 0.8;
          }
        }

        .segment-image {
          flex: 1;
          display: flex;
          justify-content: center;
          align-items: center;
          background-color: white;
          padding: 0.875rem;
          min-height: 220px;
          position: relative;
          z-index: 1;

          img {
            width: 100%;
            height: 100%;
            object-fit: contain;
            max-height: 220px;
            transition: transform 0.3s ease;
            filter: drop-shadow(0 2px 6px rgba(0, 0, 0, 0.08));

            &:hover {
              transform: scale(1.05);
              filter: drop-shadow(0 4px 12px rgba(0, 0, 0, 0.12));
            }
          }
        }

        .segment-info {
          padding: 0.5rem 0.75rem;
          border-top: 1px solid rgba(226, 232, 240, 0.7);
          font-size: 0.75rem;
          color: #64748b;
          text-align: center;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          background: linear-gradient(to bottom, #f8fafc, rgba(241, 245, 249, 0.7));
          position: relative;
          z-index: 1;

          .segment-id {
            font-family: monospace;
            font-size: 0.75rem;
            font-weight: 500;
          }

          .debug-info {
            margin-top: 0.25rem;
            font-size: 0.6875rem;
            color: #94a3b8;
          }
        }

        .structure-result {
          padding: 0.875rem;
          border-top: 1px solid rgba(226, 232, 240, 0.7);
          background: linear-gradient(145deg, rgba(79, 70, 229, 0.04) 0%, rgba(79, 70, 229, 0.08) 100%);
          position: relative;
          z-index: 1;

          .structure-title {
            display: flex;
            align-items: center;
            gap: 0.375rem;
            font-size: 0.875rem;
            margin-bottom: 0.75rem;
            color: #4f46e5;
            font-weight: 600;

            .icon {
              color: #4f46e5;
              filter: drop-shadow(0 1px 2px rgba(79, 70, 229, 0.3));
            }
          }

          /* Deep selectors for chemical structure viewer */
          :deep(.chemical-structure-viewer) {
            .structure-display {
              background-color: white !important;
              border-radius: 8px;
              overflow: hidden;
              box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
              border: 1px solid rgba(226, 232, 240, 0.8);
              transition: all 0.3s ease;

              &:hover {
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
                transform: translateY(-2px);
              }
            }

            .svg-container {
              svg {
                filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
                transition: filter 0.3s ease, transform 0.3s ease;

                &:hover {
                  filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.15));
                  transform: scale(1.02);
                }
              }
            }
          }
        }
      }
    }
  }

  /* Enhanced modal styling */
  .segment-modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.75);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
    backdrop-filter: blur(8px);
    animation: fadeIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);

    .segment-modal {
      background: linear-gradient(145deg, #f8fafc 0%, #eef2ff 100%);
      border-radius: 24px;
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.1), 0 8px 16px rgba(0, 0, 0, 0.06);
      width: 100%;
      max-width: 1100px;
      max-height: 90vh;
      overflow-y: auto;
      padding: 1.75rem;
      border: 1px solid rgba(255, 255, 255, 0.2);
      animation: modalSlideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1);

      /* Customize modal scrollbar */
      &::-webkit-scrollbar {
        width: 8px;
      }

      &::-webkit-scrollbar-track {
        background: rgba(241, 245, 249, 0.6);
        border-radius: 8px;
      }

      &::-webkit-scrollbar-thumb {
        background: rgba(148, 163, 184, 0.5);
        border-radius: 8px;

        &:hover {
          background: rgba(100, 116, 139, 0.6);
        }
      }
    }
  }
}

/* Animations */
@keyframes spin {
  0% {
    transform: rotate(0deg);
  }

  100% {
    transform: rotate(360deg);
  }
}

@keyframes float {
  0% {
    transform: translateY(0px);
  }

  50% {
    transform: translateY(-10px);
  }

  100% {
    transform: translateY(0px);
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

@keyframes modalSlideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .segments-panel {
    padding: 1rem;

    .segments-content {
      .segments-actions {
        flex-direction: column;
        align-items: stretch;

        .btn {
          width: 100%;
        }
      }
    }

    .segment-modal-backdrop {
      padding: 1rem;

      .segment-modal {
        padding: 1.25rem;
      }
    }
  }
}
</style>