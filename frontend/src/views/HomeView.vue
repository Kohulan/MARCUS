<template>
  <div class="home-container">
    <h1 class="page-title">Molecular Annotation and Recognition for Curating Unravelled Structures</h1>
    
    <!-- Warning Banner -->
    <div class="warning-banner">
      <vue-feather type="alert-triangle" class="icon warning-icon"></vue-feather>
      <span>Note: We are still optimizing our workflows. If you experience timeouts, please try again.</span>
    </div>
    
    <div class="columns-container" ref="columnsContainer">
      <!-- Column 1: PDF Upload and Visualization -->
      <div class="column pdf-column" :style="{ width: columnWidths[0] + 'px' }">
        <div class="panel">
          <h2 class="panel-title">
            <vue-feather type="file-text" class="icon"></vue-feather>
            Document Upload
          </h2>
          <PdfUploadPanel 
            @pdf-uploaded="handlePdfUploaded" 
            :isLoading="isLoadingPdf" 
          />
          
          <!-- MOVED: Prominent Action Buttons - Now placed before the PDF viewer -->
          <div class="action-buttons prominent" v-if="pdfUrl">
            <button 
              class="btn btn-primary btn-large" 
              @click="extractText"
              :disabled="isExtractingText"
            >
              <vue-feather type="align-left" class="icon"></vue-feather>
              {{ isExtractingText ? 'Extracting Text...' : 'Extract Text' }}
            </button>
            
            <button 
              class="btn btn-primary btn-large" 
              @click="extractStructures"
              :disabled="isExtractingStructures"
            >
              <vue-feather type="image" class="icon"></vue-feather>
              {{ isExtractingStructures ? 'Extracting Structures...' : 'Extract Structures' }}
            </button>
          </div>
          
          <div class="pdf-viewer-container" v-if="pdfUrl">
            <PdfViewerObject :pdfUrl="pdfUrl" :pdfFile="pdfFile" />
          </div>
        </div>
        
        <!-- Column Resizer 1 -->
        <div 
          class="column-resizer"
          @mousedown.prevent="startResize($event, 0)"
          @touchstart.prevent="startResizeTouch($event, 0)"
        ></div>
      </div>
      
      <!-- Column 2: Text and Annotations -->
      <div class="column text-column" :style="{ width: columnWidths[1] + 'px' }">
        <div class="panel">
          <h2 class="panel-title">
            <vue-feather type="type" class="icon"></vue-feather>
            Text & Annotations
          </h2>
          
          <TextPanel 
            :extractedText="extractedText"
            :annotations="annotations"
            :isLoadingAnnotations="isLoadingAnnotations"
            @extract-annotations="extractAnnotations"
          />
        </div>
        
        <!-- Column Resizer 2 -->
        <div 
          class="column-resizer"
          @mousedown.prevent="startResize($event, 1)"
          @touchstart.prevent="startResizeTouch($event, 1)"
        ></div>
      </div>
      
      <!-- Column 3: Chemical Structures -->
      <div class="column structures-column" :style="{ width: columnWidths[2] + 'px' }">
        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">
              <vue-feather type="hexagon" class="icon"></vue-feather>
              Chemical Structures
            </h2>
            
            <div class="panel-actions">
              <!-- Enhanced visually stunning export button -->
              <button 
                class="export-button" 
                @click="exportSelectedData" 
                :disabled="!hasSelectedStructures"
                :class="{ 'disabled': !hasSelectedStructures, 'pulse': selectedSegmentCount > 0 }"
                title="Export Selected Structures, Text and Annotations as JSON"
              >
                <div class="button-content">
                  <vue-feather type="download-cloud" class="export-icon"></vue-feather>
                  <span class="label">Download Data</span>
                  <div class="badge-container" v-if="selectedSegmentCount > 0">
                    <span class="badge">{{ selectedSegmentCount }}</span>
                  </div>
                </div>
                <div class="button-glow"></div>
              </button>
              
              <!-- New Submit to COCONUT button -->
              <button 
                class="coconut-button" 
                @click="openCoconutSubmitDialog" 
                :disabled="!hasOneStructureSelected"
                :class="{ 'disabled': !hasOneStructureSelected, 'pulse': hasOneStructureSelected }"
                title="Submit selected structure to COCONUT database"
              >
                <div class="button-content">
                  <vue-feather type="database" class="coconut-icon"></vue-feather>
                  <span class="label">Prepare for COCONUT</span>
                </div>
                <div class="button-glow"></div>
              </button>
            </div>
          </div>
          
          <SegmentsPanel 
            :segments="segments"
            :convertedStructures="convertedStructures"
            :isLoadingStructures="isLoadingStructures"
            @process-structures="processStructures"
            ref="segmentsPanel"
          />
        </div>
      </div>
    </div>
  
    <!-- COCONUT Submission Dialog -->
    <div v-if="showCoconutDialog" class="coconut-modal-backdrop" @click.self="closeCoconutDialog">
      <div class="coconut-modal">
        <div class="coconut-modal-header">
          <h2 class="modal-title">
            <vue-feather type="database" class="icon"></vue-feather>
            Submit to COCONUT Database
          </h2>
          <button class="btn-close" @click="closeCoconutDialog">
            <vue-feather type="x" size="20"></vue-feather>
          </button>
        </div>
        
        <div class="coconut-modal-content">
          <div v-if="submitData" class="coconut-form">
            <!-- Structure Preview -->
            <div class="structure-preview-section">
              <h3 class="section-title">Chemical Structure</h3>
              <div class="structure-preview">
                <div v-if="submitData.structureData" class="structure-card">
                  <div class="structure-image">
                    <img v-if="submitData.structureData.svgImage" 
                      :src="submitData.structureData.svgImage" 
                      alt="Chemical structure" 
                      class="structure-svg" 
                    />
                    <div v-else class="structure-placeholder">
                      <vue-feather type="hexagon" size="48"></vue-feather>
                    </div>
                  </div>
                  <div class="structure-details">
                    <div class="smiles-section">
                      <h4 class="details-title">SMILES</h4>
                      <div class="smiles-code">{{ submitData.structureData.smiles }}</div>
                    </div>
                    <div class="details-row">
                      <span class="detail-label">Engine:</span>
                      <span class="detail-value">{{ submitData.structureData.engine }}</span>
                    </div>
                    <div class="details-row">
                      <span class="detail-label">Source:</span>
                      <span class="detail-value">{{ submitData.documentInfo.pdfFilename }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- Form Fields -->
            <div class="form-section">
              <h3 class="section-title">Molecule Information</h3>
              
              <div class="form-group">
                <label for="molecule-title">
                  Submission Identifier
                  <span class="info-icon" title="This identifier is used only for tracking COCONUT submissions. It will not be included in the public database once the molecule is published.">
                    <vue-feather type="info" size="16" class="info-icon-blue"></vue-feather>
                  </span>
                </label>
                <input 
                  type="text" 
                  id="molecule-title" 
                  v-model="coconutForm.title" 
                  class="form-control"
                  placeholder="e.g., Isolation of Berberine from Berberis vulgaris"
                >
              </div>
              
              <div class="form-group">
                <label for="molecule-name">Molecule Name</label>
                <input 
                  type="text" 
                  id="molecule-name" 
                  v-model="coconutForm.name" 
                  class="form-control"
                  placeholder="e.g., Berberine"
                >
              </div>
              
              <div class="form-group">
                <label for="evidence">Evidence</label>
                <textarea 
                  id="evidence" 
                  v-model="coconutForm.evidence" 
                  class="form-control" 
                  rows="3"
                  placeholder="e.g., The compound was isolated from the root bark extract using column chromatography and structure confirmed by NMR and MS analysis."
                ></textarea>
              </div>
              
              <div class="form-group">
                <label for="comment">Comment</label>
                <textarea 
                  id="comment" 
                  v-model="coconutForm.comment" 
                  class="form-control" 
                  rows="3"
                  placeholder="e.g., This alkaloid has shown significant antimicrobial activity against gram-positive bacteria."
                ></textarea>
              </div>
              
              <div class="form-group">
                <label for="reference-id">Reference ID (if available)</label>
                <input 
                  type="text" 
                  id="reference-id" 
                  v-model="coconutForm.referenceId" 
                  class="form-control"
                  placeholder="e.g., DOI or PubMed ID"
                >
              </div>
              
              <div class="form-group">
                <label for="pubchem-link">PubChem Link (if known)</label>
                <input 
                  type="text" 
                  id="pubchem-link" 
                  v-model="coconutForm.link" 
                  class="form-control"
                  placeholder="e.g., https://pubchem.ncbi.nlm.nih.gov/compound/2353"
                >
              </div>
              
              <div class="form-group">
                <label for="structural-comments">Structural Comments</label>
                <textarea 
                  id="structural-comments" 
                  v-model="coconutForm.structuralComments" 
                  class="form-control" 
                  rows="2"
                  placeholder="e.g., Quaternary isoquinoline alkaloid with a tetracyclic skeleton"
                ></textarea>
              </div>
            </div>
            
            <!-- Source Organism Section -->
            <div class="form-section">
              <h3 class="section-title">Source Organism</h3>
              <div v-for="(organism, index) in coconutForm.organisms" :key="index" class="organism-section">
                <div class="organism-header">
                  <h4 class="organism-title">Organism {{ index + 1 }}</h4>
                  <button v-if="coconutForm.organisms.length > 1" type="button" class="btn-remove" @click="removeOrganism(index)">
                    <vue-feather type="trash-2" size="16"></vue-feather>
                  </button>
                </div>
                
                <div class="form-group">
                  <label :for="'organism-name-' + index">Organism Name</label>
                  <input 
                    :id="'organism-name-' + index" 
                    v-model="organism.name" 
                    class="form-control"
                    placeholder="e.g., Berberis vulgaris"
                  >
                </div>
                
                <div class="form-group">
                  <label :for="'organism-parts-' + index">Organism Parts</label>
                  <input 
                    :id="'organism-parts-' + index" 
                    v-model="organism.parts" 
                    class="form-control"
                    placeholder="e.g., root, bark, rhizome (comma separated)"
                  >
                </div>
                
                <div class="form-group">
                  <label :for="'organism-location-' + index">Location</label>
                  <input 
                    :id="'organism-location-' + index" 
                    v-model="organism.location" 
                    class="form-control"
                    placeholder="e.g., Eastern Europe"
                  >
                </div>
                
                <div class="form-group">
                  <label :for="'organism-ecosystem-' + index">Ecosystems</label>
                  <input 
                    :id="'organism-ecosystem-' + index" 
                    v-model="organism.ecosystems" 
                    class="form-control"
                    placeholder="e.g., temperate forest, woodland (comma separated)"
                  >
                </div>
              </div>
              
              <button type="button" class="btn-add-organism" @click="addOrganism">
                <vue-feather type="plus-circle" size="16"></vue-feather>
                Add Another Organism
              </button>
            </div>
          </div>
          
          <div v-else class="loading-container">
            <vue-feather type="loader" class="loading-icon spin"></vue-feather>
            <p>Loading structure data...</p>
          </div>
        </div>
        
        <div class="coconut-modal-footer">
          <button type="button" class="btn-cancel" @click="closeCoconutDialog">Cancel</button>
          <button 
            type="button" 
            class="btn-submit" 
            @click="submitToCoconut"
            :disabled="!isFormValid || isSubmitting"
          >
            <vue-feather v-if="isSubmitting" type="loader" size="16" class="spin"></vue-feather>
            <vue-feather v-else type="upload-cloud" size="16"></vue-feather>
            {{ isSubmitting ? 'Submitting...' : 'Submit to COCONUT' }}
          </button>
        </div>
      </div>
    </div>
    
    <!-- Add this COCONUT Login Modal -->
    <CoconutLoginModal 
      v-if="showCoconutLoginModal" 
      @close="showCoconutLoginModal = false" 
      @login-success="handleCoconutLoginSuccess"
    />
  </div>
</template>

<script>
import PdfUploadPanel from '@/components/pdf-viewer/PdfUploadPanel.vue'
import PdfViewerObject from '@/components/pdf-viewer/PdfViewerObject.vue'
import TextPanel from '@/components/text-extraction/TextPanel.vue'
import SegmentsPanel from '@/components/structure-extraction/SegmentsPanel.vue'
import depictionService from '@/services/depictionService'
import publicationService from '@/services/publicationService'
import decimerService from '@/services/decimerService'
import coconutService from '@/services/coconutService' // Import the new COCONUT service
import CoconutLoginModal from '@/components/coconut/CoconutLoginModal.vue' // Import the COCONUT login modal component

import { mapState, mapActions } from 'vuex'

export default {
  name: 'HomeView',
  components: {
    PdfUploadPanel,
    PdfViewerObject,
    TextPanel,
    SegmentsPanel,
    CoconutLoginModal, // Register the COCONUT login modal component
  },
  
  data() {
    return {
      isLoadingPdf: false,
      isExtractingText: false,
      isExtractingStructures: false,
      isLoadingAnnotations: false,
      isLoadingStructures: false,
      columnWidths: [0, 0, 0],  // Initial widths (will be calculated on mount)
      totalWidth: 0,            // Total container width
      isResizing: false,        // Flag for active resizing
      currentResizer: -1,       // Current resizer index being dragged
      startX: 0,                // Starting X position for resize
      startWidths: null,        // Starting widths when resize began
      minColumnWidth: 280,      // Minimum column width in pixels
      showCoconutDialog: false, // Flag to show/hide COCONUT submission dialog
      showCoconutLoginModal: false, // Flag to show/hide COCONUT login modal
      submitData: null,         // Data to be submitted to COCONUT
      extractedDoi: null,       // Store extracted DOI directly in component data
      coconutForm: {            // Form data for COCONUT submission
        title: '',
        name: '',
        evidence: '',
        comment: '',
        referenceId: '',
        link: '',
        structuralComments: '',
        pubchemData: null,      // Added to store PubChem data
        doiData: null,          // Added to store DOI metadata
        trivialNames: [],       // Added to store multiple trivial names
        iupacNames: [],         // Added to store IUPAC names
        compoundClasses: [],    // Added to store compound classes
        organisms: [
          {
            name: '',
            parts: '',
            location: '',
            ecosystems: ''
          }
        ]
      },
      isSubmitting: false       // Flag to indicate submission in progress
    }
  },
  
  computed: {
    ...mapState({
      pdfUrl: state => state.pdf.url,
      pdfFile: state => state.pdf.file,
      extractedText: state => state.text.content,
      annotations: state => state.annotations.items,
      segments: state => state.structures.segments,
      convertedStructures: state => state.structures.convertedStructures
    }),
    
    // New computed properties for the export button
    selectedSegmentCount() {
      return this.$store.getters['structures/selectedSegmentCount'] || 0;
    },
    
    hasSelectedStructures() {
      return this.selectedSegmentCount > 0;
    },
    
    // New computed property for COCONUT submission button
    hasOneStructureSelected() {
      return this.selectedSegmentCount === 1;
    },
    
    // Check if at least one valid organism exists (with a name)
    hasValidOrganism() {
      return this.coconutForm.organisms.some(organism => organism.name.trim() !== '');
    },
    
    // New computed property to validate the form
    isFormValid() {
      return this.coconutForm.title && 
             this.coconutForm.name && 
             this.coconutForm.evidence &&
             this.hasValidOrganism;
    }
  },
  
  mounted() {
    // Initialize column widths
    this.$nextTick(() => {
      this.initializeColumnWidths();
    });
    
    // Add resize event listener to handle window resizing
    window.addEventListener('resize', this.handleWindowResize);
    
    // Bind event handlers to component instance to prevent losing context
    this.boundHandleMouseMove = this.handleMouseMove.bind(this);
    this.boundHandleMouseUp = this.handleMouseUp.bind(this);
    this.boundHandleTouchMove = this.handleTouchMove.bind(this);
    this.boundHandleTouchEnd = this.handleTouchEnd.bind(this);
    
    // Add event listeners
    document.addEventListener('mousemove', this.boundHandleMouseMove);
    document.addEventListener('mouseup', this.boundHandleMouseUp);
    document.addEventListener('touchmove', this.boundHandleTouchMove, { passive: false });
    document.addEventListener('touchend', this.boundHandleTouchEnd);
    
    // Debounce the window resize handler
    this.debouncedWindowResize = this.debounce(this.handleWindowResize, 200);
  },
  
  beforeUnmount() {
    // Clean up event listeners
    window.removeEventListener('resize', this.debouncedWindowResize);
    document.removeEventListener('mousemove', this.boundHandleMouseMove);
    document.removeEventListener('mouseup', this.boundHandleMouseUp);
    document.removeEventListener('touchmove', this.boundHandleTouchMove);
    document.removeEventListener('touchend', this.boundHandleTouchEnd);
  },
  
  methods: {
    ...mapActions({
      setPdfFile: 'pdf/setPdfFile',
      fetchExtractedText: 'text/fetchExtractedText',
      fetchSegments: 'structures/fetchSegments',
      fetchAnnotations: 'annotations/fetchAnnotations',
      processSegments: 'structures/processSegments'
    }),
    
    // Debounce function to prevent too many resize calls
    debounce(fn, wait) {
      let timeout;
      return function(...args) {
        const context = this;
        clearTimeout(timeout);
        timeout = setTimeout(() => fn.apply(context, args), wait);
      };
    },
    
    // Initialize column widths based on container width
    initializeColumnWidths() {
      if (!this.$refs.columnsContainer) return;
      
      const containerWidth = this.$refs.columnsContainer.clientWidth;
      this.totalWidth = containerWidth;
      
      // Check if we're in mobile view
      if (window.innerWidth < 1200) {
        // In mobile view, set full width for each column
        this.columnWidths = [containerWidth, containerWidth, containerWidth];
      } else {
        // In desktop view, distribute the width evenly
        const colWidth = Math.max(this.minColumnWidth, Math.floor(containerWidth / 3));
        this.columnWidths = [colWidth, colWidth, colWidth];
        
        // Adjust last column to take remaining space
        const totalAllocated = colWidth * 2;
        const remaining = containerWidth - totalAllocated;
        if (remaining >= this.minColumnWidth) {
          this.columnWidths[2] = remaining;
        }
      }
    },
    
    // Handle window resize
    handleWindowResize() {
      // Check if component is still mounted and container ref exists
      if (!this.$refs || !this.$refs.columnsContainer) return;
      
      const newTotalWidth = this.$refs.columnsContainer.clientWidth;
      
      // Check if we're in mobile view (stack columns)
      if (window.innerWidth < 1200) {
        this.columnWidths = [newTotalWidth, newTotalWidth, newTotalWidth];
        this.totalWidth = newTotalWidth;
        return;
      }
      
      // Calculate how much each column should adjust
      const ratio = newTotalWidth / this.totalWidth;
      
      // Ensure minimum widths and adjust proportionally
      let totalDesiredWidth = 0;
      const desiredWidths = this.columnWidths.map(width => {
        const newWidth = Math.max(this.minColumnWidth, Math.floor(width * ratio));
        totalDesiredWidth += newWidth;
        return newWidth;
      });
      
      // If the total width doesn't match the container width, adjust the last column
      if (totalDesiredWidth !== newTotalWidth && totalDesiredWidth > 0) {
        const diff = newTotalWidth - totalDesiredWidth;
        const lastIndex = desiredWidths.length - 1;
        const adjustedLastCol = desiredWidths[lastIndex] + diff;
        
        // Ensure last column still meets minimum requirements
        if (adjustedLastCol >= this.minColumnWidth) {
          desiredWidths[lastIndex] = adjustedLastCol;
        } else {
          // If last column can't be adjusted, distribute among all columns
          const perColumnAdjustment = Math.floor(diff / desiredWidths.length);
          for (let i = 0; i < desiredWidths.length; i++) {
            desiredWidths[i] = Math.max(this.minColumnWidth, desiredWidths[i] + perColumnAdjustment);
          }
        }
      }
      
      this.columnWidths = desiredWidths;
      this.totalWidth = newTotalWidth;
    },
    
    // Start resizing column (mouse)
    startResize(e, index) {
      // Don't allow resizing in mobile view
      if (window.innerWidth < 1200) return;
      
      this.isResizing = true;
      this.currentResizer = index;
      this.startX = e.clientX;
      this.startWidths = [...this.columnWidths];
      
      // Add active class to the body for cursor styling
      document.body.classList.add('resizing');
    },
    
    // Start resizing column (touch)
    startResizeTouch(e, index) {
      // Don't allow resizing in mobile view
      if (window.innerWidth < 1200) return;
      
      this.isResizing = true;
      this.currentResizer = index;
      this.startX = e.touches[0].clientX;
      this.startWidths = [...this.columnWidths];
      
      // Add active class to the body for styling
      document.body.classList.add('resizing');
    },
    
    // Handle mouse movement during resize
    handleMouseMove(e) {
      if (!this.isResizing) return;
      
      const delta = e.clientX - this.startX;
      this.updateColumnWidths(delta);
    },
    
    // Handle touch movement during resize
    handleTouchMove(e) {
      if (!this.isResizing) return;
      
      e.preventDefault(); // Prevent scrolling while resizing
      const delta = e.touches[0].clientX - this.startX;
      this.updateColumnWidths(delta);
    },
    
    // Update column widths based on drag delta with constraints
    updateColumnWidths(delta) {
      if (this.currentResizer < 0 || this.currentResizer >= this.columnWidths.length - 1) return;
      
      // Make sure we have valid starting widths
      if (!this.startWidths || this.startWidths.length === 0) {
        this.startWidths = [...this.columnWidths];
      }
      
      const newWidths = [...this.startWidths];
      const containerWidth = this.totalWidth;
      
      // Get the original columns we're adjusting
      let col1Width = newWidths[this.currentResizer];
      let col2Width = newWidths[this.currentResizer + 1];
      
      // Calculate new widths
      let newCol1Width = col1Width + delta;
      let newCol2Width = col2Width - delta;
      
      // Apply minimum width constraints
      newCol1Width = Math.max(this.minColumnWidth, newCol1Width);
      newCol2Width = Math.max(this.minColumnWidth, newCol2Width);
      
      // Make sure we're not exceeding the container width
      const otherColsWidth = newWidths.reduce((sum, width, index) => {
        if (index !== this.currentResizer && index !== this.currentResizer + 1) {
          return sum + width;
        }
        return sum;
      }, 0);
      
      const maxAvailableWidth = containerWidth - otherColsWidth;
      
      // If the combined width is too large, adjust to fit
      if (newCol1Width + newCol2Width > maxAvailableWidth) {
        const excess = (newCol1Width + newCol2Width) - maxAvailableWidth;
        
        // Distribute the excess proportionally
        const col1Ratio = newCol1Width / (newCol1Width + newCol2Width);
        const col1Reduction = Math.ceil(excess * col1Ratio);
        const col2Reduction = Math.floor(excess * (1 - col1Ratio));
        
        newCol1Width -= col1Reduction;
        newCol2Width -= col2Reduction;
        
        // Double-check minimum widths again
        newCol1Width = Math.max(this.minColumnWidth, newCol1Width);
        newCol2Width = Math.max(this.minColumnWidth, newCol2Width);
      }
      
      // Update the widths array
      newWidths[this.currentResizer] = newCol1Width;
      newWidths[this.currentResizer + 1] = newCol2Width;
      
      // Apply the new widths
      this.columnWidths = newWidths;
    },
    
    // End resizing (mouse)
    handleMouseUp() {
      if (!this.isResizing) return;
      
      // Complete the resize operation
      this.finishResize();
    },
    
    // End resizing (touch)
    handleTouchEnd() {
      if (!this.isResizing) return;
      
      // Complete the resize operation
      this.finishResize();
    },
    
    // Common cleanup function for ending resize operations
    finishResize() {
      this.isResizing = false;
      this.currentResizer = -1;
      this.startWidths = null;
      this.startX = 0;
      
      // Remove active class from body
      document.body.classList.remove('resizing');
    },
    
    /**
     * Handle PDF upload event
     */
    async handlePdfUploaded(file) {
      if (!file) return;
      
      try {
        // Try to extract DOI if it's a PDF file
        const doiResult = await decimerService.extractDoi(file);
        if (doiResult && doiResult.doi) {
          console.log('Extracted DOI:', doiResult.doi);
          
          // Store DOI in component data for local reference
          this.extractedDoi = doiResult.doi;
          
          // Store DOI in the annotations store using the new action
          try {
            console.log('Pre-fetching DOI metadata for:', doiResult.doi);
            const doiMetadata = await publicationService.fetchFromDOI(doiResult.doi);
            
            // Dispatch the new action to store both DOI and its metadata
            this.$store.dispatch('annotations/setDoi', { 
              doi: doiResult.doi, 
              metadata: doiMetadata 
            });
            
            // Generate title from metadata if available
            if (doiMetadata && doiMetadata.firstAuthor && doiMetadata.year) {
              const titleValue = `MARCUS_Submission ${doiMetadata.firstAuthor} ${doiMetadata.year}`;
              console.log('Pre-generated title:', titleValue);
              
              // For backward compatibility, also update rawData
              this.$store.commit('annotations/SET_RAW_DATA', { 
                doi: doiResult.doi,
                coconut_title: titleValue,
                doi_metadata: doiMetadata 
              });
            }
          } catch (doiMetadataError) {
            console.error('Error pre-fetching DOI metadata:', doiMetadataError);
            // Still store the DOI even without metadata
            this.$store.dispatch('annotations/setDoi', { doi: doiResult.doi });
          }
        }
      } catch (doiError) {
        console.error('Error extracting DOI:', doiError);
        // Continue without DOI - not critical
      }
      
      // Set PDF file in the store
      await this.setPdfFile({ 
        file: file, 
        url: null 
      });
      
      // Don't extract text automatically - let user click the button instead
      // await this.extractText();
    },
    
    async extractText() {
      if (!this.pdfFile) return;
      
      this.isExtractingText = true;
      try {
        await this.fetchExtractedText(this.pdfFile);
      } catch (error) {
        console.error('Error extracting text:', error);
        // Show error notification
      } finally {
        this.isExtractingText = false;
      }
    },
    
    async extractStructures() {
      if (!this.pdfFile) return;
      
      this.isExtractingStructures = true;
      try {
        await this.fetchSegments(this.pdfFile);
      } catch (error) {
        console.error('Error extracting structures:', error);
        // Show error notification
      } finally {
        this.isExtractingStructures = false;
      }
    },
    
    async extractAnnotations() {
      if (!this.extractedText) return;
      
      this.isLoadingAnnotations = true;
      try {
        await this.fetchAnnotations(this.extractedText);
      } catch (error) {
        console.error('Error extracting annotations:', error);
        // Show error notification
      } finally {
        this.isLoadingAnnotations = false;
      }
    },
    
    async processStructures(options) {
      if (!this.segments || this.segments.length === 0) return;
      
      this.isLoadingStructures = true;
      try {
        await this.processSegments(options);
      } catch (error) {
        console.error('Error processing structures:', error);
        // Show error notification
      } finally {
        this.isLoadingStructures = false;
      }
    },
    
    /**
     * Export selected structures, text, and annotations as a JSON file
     */
    exportSelectedData() {
      // Get the SegmentsPanel component reference
      const segmentsPanel = this.$refs.segmentsPanel;
      if (!segmentsPanel) {
        this.$store.dispatch('showNotification', {
          type: 'error',
          message: 'Could not access segments panel for export'
        });
        return;
      }
      
      // Check if there are selected segments
      if (this.selectedSegmentCount === 0) {
        this.$store.dispatch('showNotification', {
          type: 'warning',
          message: 'No structures selected for export. Please select at least one structure.'
        });
        return;
      }
      
      try {
        // Get visible segments that are selected
        const selectedSegments = this.$store.getters['structures/visibleSegments'].filter(segment => 
          this.$store.getters['structures/isSegmentSelected'](segment.id)
        );
        
        // Format selected structures with only the essential data
        const selectedStructures = selectedSegments.map(segment => {
          const structure = segmentsPanel.getStructureForSegment(segment);
          if (!structure) {
            return {
              segmentId: segment.id,
              filename: segment.filename,
              imageUrl: segment.imageUrl || segment.path,
              error: 'No structure data available'
            };
          }
          
          return {
            segmentId: structure.segmentId,
            name: structure.name,
            filename: structure.filename,
            smiles: structure.smiles,
            molfile: structure.molfile,
            engine: structure.engine
          };
        });
        
        // Format annotations for export
        const formattedAnnotations = this.annotations.map(ann => ({
          label: ann.label,
          text: ann.text,
          start_offset: ann.start_offset,
          end_offset: ann.end_offset
        }));
        
        // Create the export data object
        const exportData = {
          timestamp: new Date().toISOString(),
          documentInfo: {
            pdfId: this.$store.state.structures.currentPdfId,
            pdfFilename: this.$store.state.text.metadata?.pdfFilename || 'Unknown',
            extractedAt: this.$store.state.text.metadata?.extractedAt || new Date().toISOString()
          },
          extractedText: this.extractedText,
          annotations: formattedAnnotations,
          structures: selectedStructures
        };
        
        // Convert to JSON and download
        const jsonData = JSON.stringify(exportData, null, 2);
        const blob = new Blob([jsonData], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        // Generate filename based on PDF name or default
        const pdfName = exportData.documentInfo.pdfFilename.replace(/\.pdf$/i, '') || 'export';
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19);
        a.download = `${pdfName}_export_${timestamp}.json`;
        
        // Trigger download
        a.click();
        URL.revokeObjectURL(url);
        
        // Show success notification
        this.$store.dispatch('showNotification', {
          type: 'success',
          message: `Exported data with ${selectedStructures.length} structures and ${formattedAnnotations.length} annotations`
        });
      } catch (error) {
        console.error('Error exporting data:', error);
        
        // Show error notification
        this.$store.dispatch('showNotification', {
          type: 'error',
          message: `Failed to export data: ${error.message}`
        });
      }
    },
    
    /**
     * Open the COCONUT submission dialog
     */
     async openCoconutSubmitDialog() {
  // Get the selected structure data
  const selectedSegment = this.$store.getters['structures/visibleSegments'].find(segment => 
    this.$store.getters['structures/isSegmentSelected'](segment.id)
  );
  
  if (!selectedSegment) {
    this.$store.dispatch('showNotification', {
      type: 'error',
      message: 'No structure selected for submission'
    });
    return;
  }
  
  const structure = this.$refs.segmentsPanel.getStructureForSegment(selectedSegment);
  if (!structure) {
    this.$store.dispatch('showNotification', {
      type: 'error',
      message: 'No structure data available for the selected segment'
    });
    return;
  }
  
  // Add loading notification
  this.$store.dispatch('showNotification', {
    type: 'info',
    message: 'Preparing COCONUT submission form...'
  });
  
  // Force extract annotations if we have text but no annotations
  if (this.extractedText && 
      (!this.$store.state.annotations.items || this.$store.state.annotations.items.length === 0) &&
      !this.$store.state.annotations.rawData) {
    console.log("No annotations found but text is available, extracting annotations first");
    this.isLoadingAnnotations = true;
    try {
      await this.fetchAnnotations(this.extractedText);
      console.log("Annotations extracted successfully");
      // Wait a moment for store to update
      await new Promise(resolve => setTimeout(resolve, 300));
    } catch (error) {
      console.error("Error extracting annotations:", error);
    } finally {
      this.isLoadingAnnotations = false;
    }
  }
  
  // Generate SVG depiction for the structure
  try {
    const depictionOptions = {
      smiles: structure.smiles,
      molfile: structure.molfile,
      useMolfileDirectly: !!structure.molfile && (structure.engine === 'molnextr' || structure.engine === 'molscribe'),
      format: 'svg',
      width: 300,
      height: 300
    };
    
    // Generate SVG depiction
    const svgData = await depictionService.generateDepiction(depictionOptions);
    
    // Create the SVG data URL
    const svgImageUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgData);
    
    // Prepare the submission data
    this.submitData = {
      structureData: {
        smiles: structure.smiles,
        engine: structure.engine,
        svgImage: svgImageUrl
      },
      documentInfo: {
        pdfFilename: this.$store.state.text.metadata?.pdfFilename || 'Unknown',
        pdfId: this.$store.state.structures.currentPdfId
      }
    };

    // Store for PubChem data
    let pubchemData = null;
    let pubchemUrl = null;

    // Immediately perform PubChem search for this structure
    try {
      console.log('Performing PubChem search for selected structure');
      if (structure.smiles) {
        pubchemData = await publicationService.searchPubChemBySmiles(structure.smiles);
        if (pubchemData) {
          console.log('Successfully found PubChem data:', pubchemData);
          this.submitData.structureData.pubchemData = pubchemData;
          this.submitData.structureData.pubchemUrl = pubchemData.url;
          this.submitData.structureData.iupacName = pubchemData.iupacName;
          
          // Save the URL for later
          pubchemUrl = pubchemData.url;
        } else {
          console.warn('No PubChem data found for this structure');
        }
      }
    } catch (pubchemError) {
      console.error('Error searching PubChem:', pubchemError);
    }

    // Reset form before populating
    this.resetCoconutForm();
    
    // IMPORTANT: Restore PubChem data after reset
    if (pubchemData) {
      this.coconutForm.pubchemData = pubchemData;
      this.coconutForm.link = pubchemUrl;
    }
    
    // Check annotation state
    console.log("Current annotation state:", {
      hasItems: !!this.$store.state.annotations.items,
      itemCount: this.$store.state.annotations.items?.length || 0,
      hasRawData: !!this.$store.state.annotations.rawData,
      extractedDoi: this.extractedDoi
    });

    // Try to populate the form
    try {
      // First try using DOI if available
      if (this.extractedDoi) {
        console.log('Using directly stored DOI to generate title:', this.extractedDoi);
        const doiData = await publicationService.fetchFromDOI(this.extractedDoi);
        
        if (doiData && doiData.firstAuthor && doiData.year) {
          const titleValue = `MARCUS_Submission ${doiData.firstAuthor} ${doiData.year}`;
          this.coconutForm.title = titleValue;
          this.coconutForm.referenceId = this.extractedDoi;
          
          // Set other fields
          if (doiData.title) {
            this.coconutForm.evidence = doiData.title;
          }
          
          if (doiData.abstract) {
            this.coconutForm.comment = doiData.abstract;
          }
        }
      }
      
      // Then populate form from annotations
      await this.populateFormFromAnnotations();
      
      // If title still not set, use stored DOI as fallback
      if (!this.coconutForm.title) {
        const doi = this.getStoredDOI();
        if (doi) {
          try {
            const doiData = await publicationService.fetchFromDOI(doi);
            if (doiData && doiData.firstAuthor && doiData.year) {
              this.coconutForm.title = `MARCUS_Submission ${doiData.firstAuthor} ${doiData.year}`;
              if (!this.coconutForm.referenceId) {
                this.coconutForm.referenceId = doi;
              }
              if (!this.coconutForm.evidence && doiData.title) {
                this.coconutForm.evidence = doiData.title;
              }
            }
          } catch (error) {
            console.error('Error fetching DOI data:', error);
          }
        }
      }
      
      // Last resort - generate a dummy title
      if (!this.coconutForm.title) {
        this.coconutForm.title = `MARCUS_Submission Unknown ${new Date().getFullYear()}`;
      }
      
      // IMPORTANT: Make sure PubChem link is still set
      if (pubchemUrl && !this.coconutForm.link) {
        console.log("Restoring PubChem URL after form population:", pubchemUrl);
        this.coconutForm.link = pubchemUrl;
      }
      
      console.log('Form data populated:', {
        title: this.coconutForm.title,
        name: this.coconutForm.name,
        evidence: this.coconutForm.evidence ? 'Set' : 'Not set',
        referenceId: this.coconutForm.referenceId,
        pubchemLink: this.coconutForm.link || 'Not set'
      });
      
      // Make sure ecosystems field contains location data
      if (this.coconutForm.organisms && this.coconutForm.organisms.length > 0) {
        const annotationData = this.$store.state.annotations.rawData;
        
        this.coconutForm.organisms.forEach(organism => {
          // Check for location data in different places
          let locationValue = null;
          
          // Try extracted_json.location first
          if (annotationData?.extracted_json?.location && 
              annotationData.extracted_json.location !== 'nan') {
            locationValue = annotationData.extracted_json.location;
          }
          // Then try direct location field
          else if (annotationData?.location && annotationData.location !== 'nan') {
            locationValue = annotationData.location;
          }
          
          // If we found location data, use it for ecosystems field
          if (locationValue) {
            organism.ecosystems = locationValue;
            console.log(`Set Ecosystems field to location: ${locationValue}`);
          }
        });
      }
      
    } catch (error) {
      console.error('Error populating form:', error);
    }
    
    // Show the dialog
    this.showCoconutDialog = true;
    
  } catch (error) {
    console.error('Error generating structure depiction:', error);
    this.$store.dispatch('showNotification', {
      type: 'error',
      message: 'Failed to generate structure depiction'
    });
  }
},
    
    /**
     * Pre-populate form with data from annotations and external sources
     */
    /**
 * Pre-populate form with data from annotations and external sources
 */
async populateFormFromAnnotations() {
  // Reset form first
  this.resetCoconutForm();
  
  // Get raw annotation data from store - check both formats
  const annotationData = this.$store.state.annotations.rawData;
  const annotationItems = this.$store.state.annotations.items;
  
  console.log('Starting populateFormFromAnnotations with data:', { 
    rawData: annotationData, 
    items: annotationItems 
  });
  
  if (!annotationData && !annotationItems) {
    console.warn('No annotation data available for form population');
    return;
  }
  
  try {
    // STEP 1: Extract DOI first if available
    let doi = null;
    
    // From structured data
    if (annotationData && annotationData.doi) {
      doi = annotationData.doi;
      this.coconutForm.referenceId = doi;
      console.log("DOI found in annotationData:", doi);
    }
    
    // Or try to find DOI in annotation items
    if (!doi && annotationItems) {
      const doiAnnotation = annotationItems.find(a => 
        a.label === 'doi' || a.label === 'reference_id'
      );
      
      if (doiAnnotation) {
        doi = doiAnnotation.text;
        this.coconutForm.referenceId = doi;
        console.log("DOI found in annotation items:", doi);
      }
    }
    
    // STEP 2: Get publication data from DOI if available
    let doiData = null;
    if (doi) {
      try {
        doiData = await publicationService.fetchFromDOI(doi);
        this.coconutForm.doiData = doiData;
        
        // Set title per requirements - MARCUS_Submission with firstauthor name and year
        if (doiData.firstAuthor && doiData.year) {
          const titleValue = `MARCUS_Submission ${doiData.firstAuthor} ${doiData.year}`;
          this.coconutForm.title = titleValue;
          console.log("Title set from DOI data:", titleValue);
        } else {
          console.log("Missing DOI data for title - firstAuthor:", doiData?.firstAuthor, "year:", doiData?.year);
        }
        
        // Set evidence to paper title per requirements
        if (doiData.title) {
          this.coconutForm.evidence = doiData.title;
        }
        
        // Set comment to paper abstract per requirements
        if (doiData.abstract) {
          this.coconutForm.comment = doiData.abstract;
        }
      } catch (error) {
        console.error("Error fetching DOI data:", error);
      }
    } else {
      console.log("No DOI found in annotations");
    }
    
    // STEP 3: NEW - Handle extraction from extracted_json field if present
    if (annotationData && annotationData.extracted_json) {
      console.log("Found extracted_json data:", annotationData.extracted_json);
      this.processExtractedJsonData(annotationData.extracted_json);
    }
    
    // STEP 4: Look for compound names in all formats
    const trivialNames = [];
    
    // From structured data
    if (annotationData) {
      // Direct fields
      if (annotationData.compound_name) {
        trivialNames.push(annotationData.compound_name);
      }
      
      if (annotationData.trivial_name && annotationData.trivial_name !== 'nan' && 
          !trivialNames.includes(annotationData.trivial_name)) {
        trivialNames.push(annotationData.trivial_name);
      }
      
      // Multiple trivial names from array if present
      if (annotationData.trivial_names && Array.isArray(annotationData.trivial_names)) {
        annotationData.trivial_names.forEach(name => {
          if (name !== 'nan' && !trivialNames.includes(name)) {
            trivialNames.push(name);
          }
        });
      }
      
      // Check extracted_json fields
      if (annotationData.extracted_json && annotationData.extracted_json.trivial_name &&
          annotationData.extracted_json.trivial_name !== 'nan') {
        const names = Array.isArray(annotationData.extracted_json.trivial_name) 
          ? annotationData.extracted_json.trivial_name 
          : [annotationData.extracted_json.trivial_name];
          
        names.forEach(name => {
          if (!trivialNames.includes(name)) {
            trivialNames.push(name);
          }
        });
      }
    }
    
    // From annotation items
    if (annotationItems) {
      const nameAnnotations = annotationItems.filter(a => 
        a.label === 'chemical_compound' || 
        a.label === 'compound_name' || 
        a.label === 'trivial_name'
      );
      
      nameAnnotations.forEach(ann => {
        if (ann.text !== 'nan' && !trivialNames.includes(ann.text)) {
          trivialNames.push(ann.text);
        }
      });
    }
    
    // Store trivial names
    this.coconutForm.trivialNames = trivialNames.filter(name => name && name !== 'nan');
    console.log("Collected trivial names:", this.coconutForm.trivialNames);
    
    // Set name to first trivial name if available (user can select others)
    if (trivialNames.length > 0) {
      this.coconutForm.name = trivialNames[0];
    }
    
    // STEP 5: Collect IUPAC names and compound classes
    const iupacNames = [];
    const compoundClasses = [];
    
    if (annotationData) {
      if (annotationData.iupac_name && annotationData.iupac_name !== 'nan') {
        iupacNames.push(annotationData.iupac_name);
      }
      
      if (annotationData.compound_class && annotationData.compound_class !== 'nan') {
        // Handle comma-separated values in compound_class
        const classes = annotationData.compound_class.split(',').map(c => c.trim());
        classes.forEach(cls => {
          if (!compoundClasses.includes(cls)) {
            compoundClasses.push(cls);
          }
        });
      }
      
      // Array versions if present
      if (annotationData.compound_classes && Array.isArray(annotationData.compound_classes)) {
        annotationData.compound_classes.forEach(cls => {
          if (cls !== 'nan' && !compoundClasses.includes(cls)) {
            compoundClasses.push(cls);
          }
        });
      }
      
      // Check extracted_json for compound_class
      if (annotationData.extracted_json && annotationData.extracted_json.compound_class) {
        const classValue = annotationData.extracted_json.compound_class;
        
        // Handle both array and string cases
        const classes = Array.isArray(classValue) 
          ? classValue 
          : classValue.split(',').map(c => c.trim());
          
        classes.forEach(cls => {
          if (cls !== 'nan' && !compoundClasses.includes(cls)) {
            compoundClasses.push(cls);
          }
        });
      }
    }
    
    // From annotation items
    if (annotationItems) {
      const iupacAnnotations = annotationItems.filter(a => 
        a.label === 'iupac_name' || a.label === 'systematic_name'
      );
      
      iupacAnnotations.forEach(ann => {
        if (ann.text !== 'nan' && !iupacNames.includes(ann.text)) {
          iupacNames.push(ann.text);
        }
      });
      
      const classAnnotations = annotationItems.filter(a => 
        a.label === 'compound_class' || 
        a.label === 'compound_group' || 
        a.label === 'compound_type'
      );
      
      classAnnotations.forEach(ann => {
        if (ann.text !== 'nan' && !compoundClasses.includes(ann.text)) {
          // Check if we have comma-separated values
          const classes = ann.text.split(',').map(c => c.trim());
          classes.forEach(cls => {
            if (!compoundClasses.includes(cls)) {
              compoundClasses.push(cls);
            }
          });
        }
      });
    }
    
    // Store IUPAC names and compound classes
    this.coconutForm.iupacNames = iupacNames;
    this.coconutForm.compoundClasses = compoundClasses;
    
    console.log("Collected compound classes:", compoundClasses);
    console.log("Collected IUPAC names:", iupacNames);
    
    // Structural comments should include compound class, IUPAC name, compound group
    const structuralElements = [];
    
    if (compoundClasses.length > 0) {
      structuralElements.push(`Class: ${compoundClasses.join(', ')}`);
    }
    
    if (iupacNames.length > 0) {
      structuralElements.push(`IUPAC: ${iupacNames[0]}`);
    }

    if (annotationData && annotationData.iupac_like_name && annotationData.iupac_like_name !== 'nan') {
  structuralElements.push(`IUPAC-like: ${annotationData.iupac_like_name}`);
} else if (annotationData?.extracted_json?.iupac_like_name && 
           annotationData.extracted_json.iupac_like_name !== 'nan') {
  structuralElements.push(`IUPAC-like: ${annotationData.extracted_json.iupac_like_name}`);
}
    
    if (structuralElements.length > 0) {
      this.coconutForm.structuralComments = structuralElements.join('; ');
    }
    
    // STEP 6: Handle organism information
    const organisms = [];
    
    // From extracted_json if available
if (annotationData && annotationData.extracted_json) {
  const extractedJson = annotationData.extracted_json;
  
  // Check for organism_or_species
  if (extractedJson.organism_or_species && extractedJson.organism_or_species !== 'nan') {
    // Handle various formats: string, comma-separated string, or array
    const speciesList = Array.isArray(extractedJson.organism_or_species) 
      ? extractedJson.organism_or_species 
      : extractedJson.organism_or_species.split(',').map(s => s.trim());
    
    speciesList.forEach(species => {
      if (species && species !== 'nan') {
        const organismParts = extractedJson.organism_part !== 'nan' ? extractedJson.organism_part : '';
        
        // Get location data
        const location = 
          (extractedJson.geo_location && extractedJson.geo_location !== 'nan' ? extractedJson.geo_location : '') || 
          (extractedJson.location && extractedJson.location !== 'nan' ? extractedJson.location : '');
        
        // CHANGE: Use location as ecosystems
        organisms.push({
          name: species,
          parts: organismParts,
          location: location,     // Keep location in location
          ecosystems: location    // Use location as ecosystems value
        });
      }
    });
  }
}
    
    // From structured data
    if (annotationData && annotationData.source_organism && annotationData.source_organism.length > 0) {
      annotationData.source_organism.forEach(organism => {
        organisms.push({
          name: organism.name || '',
          parts: organism.parts?.join(', ') || '',
          location: organism.location || '',
          ecosystems: organism.ecosystem || organism.ecosystems || ''
        });
      });
    }
    
    // Check for organism_or_species in raw annotationData first (highest priority)
    if (annotationData && annotationData.organism_or_species && annotationData.organism_or_species !== 'nan' && organisms.length === 0) {
      // Handle single string or array
      const speciesList = Array.isArray(annotationData.organism_or_species) 
        ? annotationData.organism_or_species 
        : annotationData.organism_or_species.split(',').map(s => s.trim());
      
      speciesList.forEach(species => {
        if (species && species !== 'nan') {
          organisms.push({
            name: species,
            parts: annotationData.organism_part && annotationData.organism_part !== 'nan' ? annotationData.organism_part : '',
            location: 
              (annotationData.geo_location && annotationData.geo_location !== 'nan' ? annotationData.geo_location : '') || 
              (annotationData.location && annotationData.location !== 'nan' ? annotationData.location : ''),
            ecosystems: annotationData.habitat && annotationData.habitat !== 'nan' ? annotationData.habitat : ''
          });
        }
      });
    }
    
    // From annotation items
    if (annotationItems && organisms.length === 0) {
      // Extract organism names
      const organismAnnotations = annotationItems.filter(a => 
        a.label === 'organism' || 
        a.label === 'source_organism' || 
        a.label === 'species' ||
        a.label === 'organism_or_species'
      );
      
      // Log organism annotations for debugging
      if (organismAnnotations.length > 0) {
        console.log("Found organism annotations:", organismAnnotations);
      } else {
        console.log("No organism annotations found in items");
      }
      
      // Extract parts
      const partAnnotations = annotationItems.filter(a => 
        a.label === 'organism_part' || 
        a.label === 'plant_part'
      );
      
      // Extract locations
      const locationAnnotations = annotationItems.filter(a => 
        a.label === 'geo_location' || 
        a.label === 'location'
      );
      
      // Track unique organism names to avoid duplicates
      const uniqueOrganismNames = new Set();
      
      organismAnnotations.forEach((orgAnnotation, index) => {
  // Skip 'nan' values
  if (orgAnnotation.text === 'nan' || uniqueOrganismNames.has(orgAnnotation.text)) {
    return;
  }
  
  // Add to tracking set
  uniqueOrganismNames.add(orgAnnotation.text);
  
  // Get location
  const locationText = locationAnnotations[index]?.text !== 'nan' ? locationAnnotations[index]?.text : 
                      locationAnnotations.length > 0 ? locationAnnotations.filter(a => a.text !== 'nan').map(a => a.text).join(', ') : '';
  
  organisms.push({
    name: orgAnnotation.text,
    parts: partAnnotations[index]?.text !== 'nan' ? partAnnotations[index]?.text : 
           partAnnotations.length > 0 ? partAnnotations.filter(a => a.text !== 'nan').map(a => a.text).join(', ') : '',
    location: locationText,     // Keep location in location field
    ecosystems: locationText    // CHANGE: Use location as ecosystems value
  });
});
    }
    
    // Update organism data if found
    if (organisms.length > 0) {
      console.log("Found organism data:", organisms);
      this.coconutForm.organisms = organisms;
    } else {
      console.log("No organism data found");
    }
    
  } catch (error) {
    console.error('Error populating form from annotations:', error);
  }
},

/**
 * New helper method to process extracted_json data
 */
processExtractedJsonData(extractedJson) {
  if (!extractedJson) return;
  
  console.log("Processing extracted_json data:", extractedJson);
  
  // Helper function to process fields that might be comma-separated or arrays
  const processField = (fieldValue) => {
    if (!fieldValue || fieldValue === 'nan') return [];
    
    return Array.isArray(fieldValue) 
      ? fieldValue.filter(v => v !== 'nan') 
      : fieldValue.split(',').map(v => v.trim()).filter(v => v !== 'nan');
  };
  
  // Process compound names
  if (extractedJson.trivial_name && extractedJson.trivial_name !== 'nan') {
    if (!this.coconutForm.name) {
      this.coconutForm.name = extractedJson.trivial_name;
    }
    if (!this.coconutForm.trivialNames.includes(extractedJson.trivial_name)) {
      this.coconutForm.trivialNames.push(extractedJson.trivial_name);
    }
  }
  
  // Process compound classes
  if (extractedJson.compound_class && extractedJson.compound_class !== 'nan') {
    const classes = processField(extractedJson.compound_class);
    classes.forEach(cls => {
      if (!this.coconutForm.compoundClasses.includes(cls)) {
        this.coconutForm.compoundClasses.push(cls);
      }
    });
  }
  
  // Process IUPAC names
  if (extractedJson.iupac_name && extractedJson.iupac_name !== 'nan') {
    if (!this.coconutForm.iupacNames.includes(extractedJson.iupac_name)) {
      this.coconutForm.iupacNames.push(extractedJson.iupac_name);
    }
  }
  
  // Update structural comments if applicable
  if (this.coconutForm.compoundClasses.length > 0 || this.coconutForm.iupacNames.length > 0) {
    const structuralElements = [];
    
    if (this.coconutForm.compoundClasses.length > 0) {
      structuralElements.push(`Class: ${this.coconutForm.compoundClasses.join(', ')}`);
    }
    
    if (this.coconutForm.iupacNames.length > 0) {
      structuralElements.push(`IUPAC: ${this.coconutForm.iupacNames[0]}`);
    }
    
    this.coconutForm.structuralComments = structuralElements.join('; ');
  }
},
    
    /**
     * Close the COCONUT submission dialog
     */
    closeCoconutDialog() {
      this.showCoconutDialog = false;
      this.submitData = null;
      this.resetCoconutForm();
    },
    
    /**
     * Reset the COCONUT form fields
     */
    resetCoconutForm() {
      this.coconutForm = {
        title: '',
        name: '',
        evidence: '',
        comment: '',
        referenceId: '',
        link: '',
        structuralComments: '',
        pubchemData: null,      // Added to store PubChem data
        doiData: null,          // Added to store DOI metadata
        trivialNames: [],       // Added to store multiple trivial names
        iupacNames: [],         // Added to store IUPAC names
        compoundClasses: [],    // Added to store compound classes
        organisms: [
          {
            name: '',
            parts: '',
            location: '',
            ecosystems: ''
          }
        ]
      };
    },
    
    /**
     * Add a new organism to the form
     */
    addOrganism() {
      this.coconutForm.organisms.push({
        name: '',
        parts: '',
        location: '',
        ecosystems: ''
      });
    },
    
    /**
     * Remove an organism from the form
     */
    removeOrganism(index) {
      this.coconutForm.organisms.splice(index, 1);
    },
    
    /**
     * Submit the form data to COCONUT
     */
    async submitToCoconut() {
      if (!this.isFormValid) return;
      
      this.isSubmitting = true;
      try {
        // Check if the user is already authenticated with COCONUT
        if (!coconutService.isAuthenticated()) {
          // Show the login modal if not authenticated
          this.showCoconutLoginModal = true;
          this.isSubmitting = false;
          return;
        }
        
        // Prepare the submission payload
        const payload = {
          title: this.coconutForm.title,
          name: this.coconutForm.name,
          evidence: this.coconutForm.evidence,
          comment: this.coconutForm.comment,
          referenceId: this.coconutForm.referenceId,
          link: this.coconutForm.link,
          structuralComments: this.coconutForm.structuralComments,
          organisms: this.coconutForm.organisms,
          structureData: this.submitData.structureData,
          documentInfo: this.submitData.documentInfo
        };
        
        // Submit to COCONUT API
        const result = await coconutService.submitToCoconut(payload);
        
        if (result.success) {
          // Show success notification
          this.$store.dispatch('showNotification', {
            type: 'success',
            message: 'Successfully submitted to COCONUT database'
          });
          
          // Close the dialog
          this.closeCoconutDialog();
        } else {
          // Show error notification
          this.$store.dispatch('showNotification', {
            type: 'error',
            message: `Failed to submit to COCONUT: ${result.error}`
          });
        }
      } catch (error) {
        console.error('Error submitting to COCONUT:', error);
        
        // Show error notification
        this.$store.dispatch('showNotification', {
          type: 'error',
          message: `Failed to submit to COCONUT: ${error.message || 'Unknown error'}`
        });
      } finally {
        this.isSubmitting = false;
      }
    },

    /**
     * Handle successful login from COCONUT login modal
     * @param {Object} user - The authenticated user object
     */
    handleCoconutLoginSuccess(user) {
      this.showCoconutLoginModal = false;
      
      // Show success notification
      this.$store.dispatch('showNotification', {
        type: 'success',
        message: `Successfully logged in as ${user?.email || 'COCONUT user'}`
      });
      
      // Continue with submission if we were in the middle of submitting
      if (this.isSubmitting) {
        // Resume submission process
        setTimeout(() => {
          this.submitToCoconut();
        }, 500);
      }
    },

    /**
     * Get the DOI from stored annotations
     * @returns {string|null} The DOI or null if not found
     */
    /**
 * Get the DOI from stored annotations
 * @returns {string|null} The DOI or null if not found
 */
getStoredDOI() {
  // Check component's directly stored DOI first (highest priority)
  if (this.extractedDoi) {
    console.log("Using component's directly stored DOI:", this.extractedDoi);
    return this.extractedDoi;
  }
  
  // Then check using the annotations store getter
  const extractedDoi = this.$store.getters['annotations/extractedDoi'];
  if (extractedDoi) {
    console.log("Found DOI using annotations/extractedDoi getter:", extractedDoi);
    return extractedDoi;
  }
  
  // Fallback to raw annotation data
  const annotationData = this.$store.state.annotations.rawData;
  if (annotationData) {
    // Check direct DOI field
    if (annotationData.doi) {
      return annotationData.doi;
    }
    
    // Check DOI in extracted_json if available
    if (annotationData.extracted_json && annotationData.extracted_json.doi) {
      return annotationData.extracted_json.doi;
    }
    
    // Check if we've stored coconut_title separately
    if (annotationData.coconut_title) {
      // Even if we don't have the DOI, we can still use the pre-generated title
      this.coconutForm.title = annotationData.coconut_title;
    }
  }
  
  // Then check from annotation items
  const annotationItems = this.$store.state.annotations.items;
  if (annotationItems) {
    const doiAnnotation = annotationItems.find(a => 
      a.label === 'doi' || a.label === 'reference_id'
    );
    
    if (doiAnnotation) {
      console.log("Found DOI in annotation items:", doiAnnotation.text);
      return doiAnnotation.text;
    }
  }
  
  // Try to extract from positions array in annotationData
  if (annotationData && annotationData.positions) {
    const doiPosition = annotationData.positions.find(p => 
      p.label === 'doi' || p.label === 'reference_id'
    );
    
    if (doiPosition && annotationData.input_text) {
      const doi = annotationData.input_text.substring(
        doiPosition.start_offset, 
        doiPosition.end_offset
      );
      console.log("Extracted DOI from positions:", doi);
      return doi;
    }
  }
  
  // Generate a default title based on PDF filename if we can't find a DOI
  if (!this.coconutForm.title) {
    const pdfFilename = this.$store.state.text.metadata?.pdfFilename || '';
    if (pdfFilename) {
      // Try to extract author and year from filename patterns like "2020_-_Smith_-_Title.pdf"
      const filenameMatch = pdfFilename.match(/(\d{4})_-_([^_-]+)/i);
      if (filenameMatch) {
        // Use array destructuring but skip the first match (the full matched string)
        const [, year, author] = filenameMatch;
        const defaultTitle = `MARCUS_Submission ${author} ${year}`;
        this.coconutForm.title = defaultTitle;
      }
    }
  }
  
  return null;
},
  }
}
</script>

<style lang="scss" scoped>
.home-container {
  display: flex;
  flex-direction: column;
  gap: 0.6rem; /* Further reduced from 0.8rem to save more vertical space */
  max-width: 100%;
  padding: 0 0.5rem;
  height: 100%;
  overflow: hidden;
}

.page-title {
  text-align: center;
  font-size: 1.8rem; /* Reduced from 2rem */
  margin: 0.1rem 0; /* Further reduced from 0.3rem to move content up */
  background: linear-gradient(to right, #1e3a8a, #2563eb);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  font-weight: 700;
  flex-shrink: 0;
}

/* Warning banner styles */
.warning-banner {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  background-color: rgba(255, 193, 7, 0.2);
  border-left: 4px solid #ffc107;
  padding: 0.4rem 0.75rem; /* Further reduced from 0.5rem to 0.4rem */
  border-radius: 4px;
  margin-bottom: 0.3rem; /* Further reduced from 0.5rem to 0.3rem */
  font-size: 0.9rem; /* Reduced from 0.95rem */
}

.warning-icon {
  color: #ffc107;
}

.columns-container {
  display: flex;
  gap: 0;
  height: calc(100vh - 253px); /* Adjusted for reduced header height (was 260px, now 253px - saving 7px) */
  width: 100%;
  position: relative;
  overflow: hidden; /* Keep this as hidden to prevent horizontal scrolling */
  
  /* Add styles to make sure child components display correctly */
  :deep(.segments-panel) {
    height: 100%;
    overflow: auto;
    
    /* Make sure the segments actions (contains Get Structures button) is visible */
    .segments-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-bottom: 0.75rem;
      
      /* Ensure ModelSelector fits */
      > * {
        min-width: 0;
      }
      
      /* Make sure the button is visible */
      .btn-primary {
        white-space: nowrap;
        flex-shrink: 0;
      }
    }
  }
  
  /* Ensure segment modal appears correctly */
  :deep(.segment-modal-backdrop) {
    z-index: 1100; /* Higher z-index to ensure it appears over other elements */
    
    .segment-modal {
      max-height: 90vh;
      max-width: 90vw;
      width: 90vw;
      
      @media (min-width: 768px) {
        width: 80vw;
      }
      
      @media (min-width: 1024px) {
        width: 70vw;
      }
      
      @media (min-width: 1280px) {
        width: auto;
        max-width: 1000px;
      }
    }
  }
}

.column {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  transition: width 0.1s ease;
  overflow: visible; /* Changed from hidden to visible to show all content */
  min-width: 0; /* Allow column to shrink below content width */
}

.column-resizer {
  position: absolute;
  right: -3px; /* Position center of the resizer at the border */
  top: 0;
  width: 6px;
  height: 100%;
  background-color: transparent;
  cursor: col-resize;
  z-index: 10;
  transition: background-color 0.2s ease;
  
  &:hover, &:active {
    background-color: rgba(0, 123, 255, 0.3);
  }
  
  &::after {
    content: '';
    position: absolute;
    top: 0;
    left: 2px;
    width: 2px;
    height: 100%;
    background-color: rgba(0, 0, 0, 0.1);
  }
}

.panel {
  background: var(--color-panel-bg);
  border-radius: 8px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
  padding: 0.75rem;
  height: 100%;
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  flex-direction: column;
  overflow: auto; /* Changed from hidden to auto to allow scrolling */
  margin-right: 6px; /* Make space for the resizer */
  
  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
    flex-shrink: 0;
  }
  
  &-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 1.25rem;
    font-weight: 600;
    flex-shrink: 0;
    margin-bottom: 0; /* Override previous margin as we now use panel-header */
    
    .icon {
      color: var(--color-primary);
    }
  }
}

/* Material Design Download Data Button with Flat Pastel Indigo */
.export-button {
  --export-50: #EDE7F6;
  --export-100: #c4cae9;
  --export-200: #9daddb;
  --export-800: #2727a0;
  --export-900: #1b3592;
  
  position: relative;
  padding: 0;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
  isolation: isolate;
  
  /* Flat Material Design Pastel Background */
  background: var(--export-100);
  
  /* Professional shadow with indigo accent */
  box-shadow: 
    0 2px 8px rgba(69, 39, 160, 0.15),
    0 1px 3px rgba(0, 0, 0, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
  
  .button-content {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.375rem 0.625rem; /* Reduced from 0.75rem 1.5rem */
    color: var(--export-800);
    font-weight: 600;
    font-size: 0.75rem; /* Reduced from 0.95rem */
    letter-spacing: 0.02em;
    z-index: 5;
  }
  
  /* Professional shine effect */
  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(255, 255, 255, 0.4),
      transparent
    );
    transition: left 0.6s ease;
    z-index: 3;
  }
  
  /* Subtle button glow effect */
  .button-glow {
    position: absolute;
    top: -25%;
    left: -25%;
    width: 150%;
    height: 150%;
    background: radial-gradient(circle, rgba(69, 39, 160, 0.1) 0%, rgba(69, 39, 160, 0) 70%);
    opacity: 0;
    transition: opacity 0.3s ease;
    z-index: 2;
    pointer-events: none;
  }
  
  /* Professional hover state */
  &:hover:not(.disabled) {
    transform: translateY(-2px) scale(1.02);
    box-shadow: 
      0 6px 20px rgba(69, 39, 160, 0.25),
      0 2px 8px rgba(0, 0, 0, 0.15),
      inset 0 1px 0 rgba(255, 255, 255, 0.2);
    
    /* Flat pastel hover color */
    background: var(--export-200);
    
    .button-glow {
      opacity: 1;
    }
    
    .export-icon {
      transform: scale(1.1);
      filter: drop-shadow(0 2px 4px rgba(69, 39, 160, 0.3));
    }
    
    .badge-container {
      transform: scale(1.05);
    }
    
    /* Trigger shine animation */
    &::before {
      left: 100%;
    }
  }
  
  &:active:not(.disabled) {
    transform: translateY(-1px) scale(0.98);
    box-shadow: 
      0 3px 12px rgba(69, 39, 160, 0.2),
      0 1px 4px rgba(0, 0, 0, 0.1),
      inset 0 1px 0 rgba(255, 255, 255, 0.1);
    
    .button-glow {
      opacity: 0.7;
    }
  }
  
  /* Professional disabled state */
  &.disabled {
    background: #F5F5F5; /* Flat gray instead of gradient */
    color: #9E9E9E;
    cursor: not-allowed;
    opacity: 0.6;
    box-shadow: 
      0 1px 3px rgba(0, 0, 0, 0.1),
      inset 0 1px 0 rgba(255, 255, 255, 0.1);
    filter: saturate(0.7);
    
    .export-icon {
      color: #9E9E9E;
    }
    
    .badge {
      background: #E0E0E0;
      color: #9E9E9E;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }
  }
  
  /* Subtle pulsing effect when active */
  &.pulse:not(.disabled) {
    animation: subtlePulse 2s ease-in-out infinite;
  }
  
  /* Icon styling - reduced size */
  .export-icon {
    width: 16px; /* Reduced from 20px */
    height: 16px; /* Reduced from 20px */
    color: var(--export-800);
    transition: all 0.3s ease;
  }
  
  /* Label styling */
  .label {
    font-weight: 600;
    color: var(--export-800);
  }
  
  /* Badge container and styling */
  .badge-container {
    position: relative;
    transition: transform 0.3s ease;
  }
  
  .badge {
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--export-800);
    color: white;
    border-radius: 999px;
    min-width: 18px; /* Reduced from 24px */
    height: 18px; /* Reduced from 24px */
    padding: 0 0.375rem; /* Reduced from 0.5rem */
    font-size: 0.7rem; /* Reduced from 0.85rem */
    font-weight: 700;
    box-shadow: 0 2px 4px rgba(69, 39, 160, 0.3);
    transition: all 0.3s ease;
  }
}

/* Define animations */
@keyframes subtlePulse {
  0%, 100% { 
    box-shadow: 
      0 2px 8px rgba(69, 39, 160, 0.15),
      0 1px 3px rgba(0, 0, 0, 0.1),
      inset 0 1px 0 rgba(255, 255, 255, 0.1);
  }
  50% { 
    box-shadow: 
      0 4px 12px rgba(69, 39, 160, 0.25),
      0 2px 6px rgba(0, 0, 0, 0.15),
      inset 0 1px 0 rgba(255, 255, 255, 0.15);
  }
}

@keyframes pulse {
  0% { opacity: 0.6; transform: scale(0.9); }
  50% { opacity: 0.1; transform: scale(1.1); }
  100% { opacity: 0.6; transform: scale(0.9); }
}

@keyframes levitate {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}

@keyframes bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-5px); }
}

.pdf-viewer-container {
  margin-top: 0.5rem;
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* UPDATED: Action buttons styling to make them more prominent */
.action-buttons {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
  flex-shrink: 0;
  
  .btn {
    flex: 1;
    padding: 0.5rem;
    font-size: 0.9rem;
    white-space: nowrap;
  }
  
  /* New styles for more prominent buttons */
  &.prominent {
    margin: 1rem 0;
    padding: 0.5rem;
    background-color: rgba(var(--color-primary-rgb), 0.08);
    border-radius: 8px;
    border: 1px dashed rgba(var(--color-primary-rgb), 0.3);
    
    .btn-large {
      padding: 0.75rem 1rem;
      font-size: 1rem;
      font-weight: 600;
      min-height: 48px;
      transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
      position: relative;
      overflow: hidden;
      
      &:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 15px rgba(var(--color-primary-rgb), 0.25);
      }
      
      .icon {
        width: 18px;
        height: 18px;
      }
      
      &:before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: linear-gradient(
          45deg,
          rgba(255, 255, 255, 0) 0%,
          rgba(255, 255, 255, 0.1) 100%
        );
        z-index: 1;
      }
    }
  }
}

.icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

/* When resizing is active */
:global(body.resizing) {
  cursor: col-resize !important;
  user-select: none;
  
  /* Prevent text selection during resize */
  * {
    user-select: none !important;
  }
}

@media (max-width: 1199px) {
  .home-container {
    height: auto;
    overflow: visible;
  }
  
  .columns-container {
    flex-direction: column;
    height: auto;
    overflow: visible;
  }
  
  .column {
    width: 100% !important; /* Override inline styles for mobile */
    height: auto;
    min-height: 0;
    overflow: visible;
  }
  
  .column-resizer {
    display: none;
  }
  
  .panel {
    height: auto;
    min-height: 400px;
    margin-right: 0;
    margin-bottom: 1rem;
    overflow: visible;
  }
  
  /* Make buttons stack on mobile */
  .action-buttons.prominent {
    flex-direction: column;
    
    .btn-large {
      width: 100%;
    }
  }
}

/* COCONUT modal styles */
.coconut-modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1200;
}

.coconut-modal {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.coconut-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid #e5e7eb;
}

.modal-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.25rem;
  font-weight: 600;
}

.btn-close {
  background: none;
  border: none;
  cursor: pointer;
}

.coconut-modal-content {
  padding: 1rem;
  flex-grow: 1;
}

.coconut-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.structure-preview-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.structure-preview {
  display: flex;
  justify-content: center;
}

.structure-card {
  display: flex;
  gap: 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 1rem;
}

.structure-image {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100px;
  height: 100px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.structure-svg {
  max-width: 100%;
  max-height: 100%;
}

.structure-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: #9ca3af;
}

.structure-details {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.smiles-section {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.details-title {
  font-size: 0.875rem;
  font-weight: 600;
}

.smiles-code {
  font-family: monospace;
  background: #f3f4f6;
  padding: 0.25rem;
  border-radius: 4px;
}

.details-row {
  display: flex;
  gap: 0.5rem;
}

.detail-label {
  font-weight: 600;
}

.detail-value {
  color: #6b7280;
}

.form-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.section-title {
  font-size: 1rem;
  font-weight: 600;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.form-control {
  padding: 0.5rem;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
}

/* Add custom placeholder styling */
.form-control::placeholder {
  color: rgba(153, 157, 163, 0.6);
  font-style: italic;
}

.organism-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 1rem;
}

.organism-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.organism-title {
  font-size: 1rem;
  font-weight: 600;
}

.btn-remove {
  background: none;
  border: none;
  cursor: pointer;
  color: #ef4444;
}

.btn-add-organism {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: none;
  border: none;
  cursor: pointer;
  color: #3b82f6;
  font-weight: 600;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.loading-icon {
  color: #3b82f6;
}

.coconut-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  padding: 1rem;
  border-top: 1px solid #e5e7eb;
}

.btn-cancel {
  background: none;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  padding: 0.5rem 1rem;
  cursor: pointer;
}

.btn-submit {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #3b82f6;
  border: none;
  border-radius: 4px;
  padding: 0.5rem 1rem;
  color: #fff;
  cursor: pointer;
}

.btn-submit:disabled {
  background: #9ca3af;
  cursor: not-allowed;
}

/* COCONUT button styles */
.panel-actions {
  display: flex;
  gap: 0.75rem;
}

/* Material Design COCONUT Button with Professional Teal Styling */
.coconut-button {
  --coconut-50: #E0F2F1;
  --coconut-100: #B2DFDB;
  --coconut-200: #80CBC4;
  --coconut-800: #00695C;
  --coconut-900: #004D40;
  
  position: relative;
  padding: 0;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
  isolation: isolate;
  
  /* Flat Material Design Teal Pastel Background */
  background: var(--coconut-100);
  
  /* Professional shadow with teal accent */
  box-shadow: 
    0 2px 8px rgba(0, 105, 92, 0.15),
    0 1px 3px rgba(0, 0, 0, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
  
  .button-content {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.375rem 0.625rem; /* Reduced from 0.75rem 1.5rem */
    color: var(--coconut-800);
    font-weight: 600;
    font-size: 0.75rem; /* Reduced from 0.95rem */
    letter-spacing: 0.02em;
    z-index: 5;
  }
  
  /* Professional shine effect */
  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(255, 255, 255, 0.4),
      transparent
    );
    transition: left 0.6s ease;
    z-index: 3;
  }
  
  /* Subtle button glow effect */
  .button-glow {
    position: absolute;
    top: -25%;
    left: -25%;
    width: 150%;
    height: 150%;
    background: radial-gradient(circle, rgba(0, 105, 92, 0.1) 0%, rgba(0, 105, 92, 0) 70%);
    opacity: 0;
    transition: opacity 0.3s ease;
    z-index: 2;
    pointer-events: none;
  }
  
  /* Professional hover state */
  &:hover:not(.disabled) {
    transform: translateY(-2px) scale(1.02);
    box-shadow: 
      0 6px 20px rgba(0, 105, 92, 0.25),
      0 2px 8px rgba(0, 0, 0, 0.15),
      inset 0 1px 0 rgba(255, 255, 255, 0.2);
    
    /* Flat pastel hover color */
    background: var(--coconut-200);
    
    .button-glow {
      opacity: 1;
    }
    
    .coconut-icon {
      transform: scale(1.1);
      filter: drop-shadow(0 2px 4px rgba(0, 105, 92, 0.3));
    }
    
    /* Trigger shine animation */
    &::before {
      left: 100%;
    }
  }
  
  &:active:not(.disabled) {
    transform: translateY(-1px) scale(0.98);
    box-shadow: 
      0 3px 12px rgba(0, 105, 92, 0.2),
      0 1px 4px rgba(0, 0, 0, 0.1),
      inset 0 1px 0 rgba(255, 255, 255, 0.1);
    
    .button-glow {
      opacity: 0.7;
    }
  }
  
  /* Professional disabled state */
  &.disabled {
    background: #F5F5F5; /* Flat gray instead of gradient */
    color: #9E9E9E;
    cursor: not-allowed;
    opacity: 0.6;
    box-shadow: 
      0 1px 3px rgba(0, 0, 0, 0.1),
      inset 0 1px 0 rgba(255, 255, 255, 0.1);
    filter: saturate(0.7);
    
    .coconut-icon {
      color: #9E9E9E;
    }
    
    .label {
      color: #9E9E9E;
    }
  }
  
  /* Elegant pulsing effect when active */
  &.pulse:not(.disabled)::after {
    content: '';
    position: absolute;
    top: -4px;
    left: -4px;
    right: -4px;
    bottom: -4px;
    border-radius: 14px;
    background: rgba(0, 105, 92, 0.2);
    z-index: 1;
    animation: pulse 2.5s infinite;
    pointer-events: none;
  }
  
  /* Icon styling */
  .coconut-icon {
    width: 16px; /* Reduced from 20px */
    height: 16px; /* Reduced from 20px */
    color: var(--coconut-800);
    filter: drop-shadow(0 1px 2px rgba(0, 105, 92, 0.1));
    transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
  }
  
  /* Label styling */
  .label {
    font-weight: 600;
    color: var(--coconut-800);
    text-shadow: 0 1px 1px rgba(255, 255, 255, 0.5);
  }
}
</style>