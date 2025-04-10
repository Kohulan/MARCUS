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
            <PdfViewerObject :pdfUrl="pdfUrl" />
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
                <span class="label">Export Data</span>
                <div class="badge-container" v-if="selectedSegmentCount > 0">
                  <span class="badge">{{ selectedSegmentCount }}</span>
                </div>
              </div>
              <div class="button-glow"></div>
            </button>
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
  </div>
</template>

<script>
import PdfUploadPanel from '@/components/pdf-viewer/PdfUploadPanel.vue'
import PdfViewerObject from '@/components/pdf-viewer/PdfViewerObject.vue'
import TextPanel from '@/components/text-extraction/TextPanel.vue'
import SegmentsPanel from '@/components/structure-extraction/SegmentsPanel.vue'

import { mapState, mapActions } from 'vuex'

export default {
  name: 'HomeView',
  components: {
    PdfUploadPanel,
    PdfViewerObject,
    TextPanel,
    SegmentsPanel
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
      minColumnWidth: 280       // Minimum column width in pixels
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
    
    async handlePdfUploaded(file) {
      this.isLoadingPdf = true;
      try {
        console.log('PDF file uploaded:', file.name);
        // Create a URL for the PDF file
        const pdfUrl = URL.createObjectURL(file);
        console.log('Created PDF URL:', pdfUrl);
        
        // Set the PDF file in store (this will also set the URL)
        await this.setPdfFile({
          file,
          url: pdfUrl
        });
        
        console.log('PDF file set in store');
      } catch (error) {
        console.error('Error uploading PDF:', error);
        // Show error notification
      } finally {
        this.isLoadingPdf = false;
      }
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
    }
  }
}
</script>

<style lang="scss" scoped>
.home-container {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-width: 100%;
  padding: 0 0.5rem;
  height: 100vh;
  overflow: hidden;
}

.page-title {
  text-align: center;
  font-size: 2rem;
  margin: 0.5rem 0;
  background: linear-gradient(to right, #4a4de7, #8a2be2);
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
  gap: 0.5rem;
  background-color: rgba(255, 193, 7, 0.2);
  border-left: 4px solid #ffc107;
  padding: 0.75rem 1rem;
  border-radius: 4px;
  margin-bottom: 1rem;
  font-size: 0.95rem;
}

.warning-icon {
  color: #ffc107;
}

.columns-container {
  display: flex;
  gap: 0;
  height: calc(100vh - 120px);
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

/* Styling for the new export button */
.export-button {
  position: relative;
  padding: 0;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3), 0 0 0 2px rgba(59, 130, 246, 0.2);
  isolation: isolate;
  
  /* Gradient background with animation */
  background: linear-gradient(-45deg, #4338ca, #3b82f6, #2563eb, #1d4ed8);
  background-size: 300% 300%;
  animation: gradientShift 8s ease infinite;
  
  .button-content {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    color: white;
    font-weight: 600;
    font-size: 0.95rem;
    letter-spacing: 0.01em;
    z-index: 5;
  }
  
  /* Subtle button glow effect */
  .button-glow {
    position: absolute;
    top: -25%;
    left: -25%;
    width: 150%;
    height: 150%;
    background: radial-gradient(circle, rgba(255, 255, 255, 0.25) 0%, rgba(255, 255, 255, 0) 70%);
    opacity: 0;
    transition: opacity 0.3s ease;
    z-index: 2;
    pointer-events: none;
  }
  
  /* Interactive states */
  &:hover:not(.disabled) {
    transform: translateY(-3px) scale(1.02);
    box-shadow: 0 8px 25px rgba(59, 130, 246, 0.35), 0 0 0 2px rgba(96, 165, 250, 0.5);
    
    .button-glow {
      opacity: 1;
      animation: pulse 2s infinite;
    }
    
    .export-icon {
      animation: levitate 1.5s ease-in-out infinite;
      filter: drop-shadow(0 0 8px rgba(255, 255, 255, 0.5));
    }
    
    .badge-container {
      transform: scale(1.1);
    }
  }
  
  &:active:not(.disabled) {
    transform: translateY(1px) scale(0.98);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
    
    .button-glow {
      opacity: 0.7;
    }
  }
  
  /* Disabled state with improved contrast */
  &.disabled {
    background: linear-gradient(135deg, #94a3b8 0%, #64748b 100%);
    cursor: not-allowed;
    opacity: 0.8;
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1), 0 0 0 1px rgba(255, 255, 255, 0.1);
    filter: saturate(0.7);
  }
  
  /* Pulsing effect when active */
  &.pulse:not(.disabled)::after {
    content: '';
    position: absolute;
    top: -8px;
    left: -8px;
    right: -8px;
    bottom: -8px;
    border-radius: 16px;
    background: rgba(59, 130, 246, 0.3);
    z-index: 1;
    animation: pulse 2s infinite;
    pointer-events: none;
  }
  
  /* Icon styling */
  .export-icon {
    width: 20px;
    height: 20px;
    color: white;
    filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));
    transition: all 0.3s ease;
  }
  
  /* Label styling */
  .label {
    font-weight: 700;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
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
    background: #ffffff;
    color: #3b82f6;
    border-radius: 999px;
    min-width: 24px;
    height: 24px;
    padding: 0 0.5rem;
    font-size: 0.85rem;
    font-weight: 800;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25), 0 0 0 2px rgba(59, 130, 246, 0.3);
    transition: all 0.3s ease;
    
    /* Ensure badge is readable in dark mode */
    @media (prefers-color-scheme: dark) {
      background: #ffffff;
      color: #3b82f6;
      box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.2), 0 0 10px rgba(255, 255, 255, 0.4);
    }
  }
}

/* Define animations */
@keyframes gradientShift {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
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
</style>