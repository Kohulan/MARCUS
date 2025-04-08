<template>
    <div class="segment-popup">
      <div class="popup-header">
        <h3 class="segment-title">
          {{ segment.filename || 'Chemical Structure Segment' }}
        </h3>
        <div class="popup-actions">
          <button class="btn-close" @click="$emit('close')">
            <vue-feather type="x" size="20"></vue-feather>
          </button>
        </div>
      </div>
      
      <!-- Comparison Mode Toggle -->
      <div v-if="!comparisonMode" class="segment-content">
        <div class="segment-image-container">
          <img :src="segment.imageUrl" :alt="segment.filename" class="segment-image" />
        </div>
        
        <template v-if="structure">
          <div class="structure-container">
            <improved-chemical-structure-viewer
              :smiles="structure.smiles"
              :molfile="structure.molfile"
              :name="segment.filename"
              :source-engine="structure.engine"
            />
          </div>
        </template>
        
        <template v-else>
          <div class="no-structure">
            <p>This segment has not been processed yet. Process segments to view chemical structure.</p>
          </div>
        </template>
        
        <div class="segment-actions">
          <button 
            class="btn btn-primary" 
            @click="toggleComparisonMode"
            title="Compare this segment across all OCSR engines"
          >
            <vue-feather type="bar-chart-2" class="btn-icon"></vue-feather>
            Compare Across All Engines
          </button>
        </div>
      </div>
      
      <!-- Comparison Mode -->
      <ocsr-comparison 
        v-else 
        :segment="segment" 
        @close="toggleComparisonMode"
      />
    </div>
  </template>
  
  <script>
  import ImprovedChemicalStructureViewer from './ImprovedChemicalStructureViewer.vue';
  import OCSRComparison from './OCSRComparison.vue';
  
  export default {
    name: 'SegmentPopup',
    components: {
      ImprovedChemicalStructureViewer,
      OCSRComparison
    },
    props: {
      segment: {
        type: Object,
        required: true
      },
      structure: {
        type: Object,
        default: null
      }
    },
    emits: ['close'],
    data() {
      return {
        comparisonMode: false
      };
    },
    methods: {
      toggleComparisonMode() {
        this.comparisonMode = !this.comparisonMode;
      }
    }
  };
  </script>
  
  <style lang="scss" scoped>
  .segment-popup {
    width: 100%;
    max-width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    background-color: var(--color-bg);
    
    .popup-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 1rem;
      border-bottom: 1px solid var(--color-border);
      
      .segment-title {
        font-size: 1.25rem;
        margin: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        max-width: 90%;
      }
      
      .popup-actions {
        .btn-close {
          background: none;
          border: none;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 0.25rem;
          border-radius: 4px;
          cursor: pointer;
          color: var(--color-text-light);
          
          &:hover {
            background-color: rgba(0, 0, 0, 0.05);
            color: var(--color-text);
          }
        }
      }
    }
    
    .segment-content {
      flex: 1;
      display: flex;
      flex-direction: column;
      padding: 1rem;
      overflow-y: auto;
      
      .segment-image-container {
        display: flex;
        justify-content: center;
        margin-bottom: 1.5rem;
        
        .segment-image {
          max-height: 300px;
          max-width: 100%;
          object-fit: contain;
          border: 1px solid var(--color-border);
          border-radius: var(--radius-md);
          padding: 0.5rem;
          background: white;
        }
      }
      
      .structure-container {
        margin-bottom: 1.5rem;
      }
      
      .no-structure {
        text-align: center;
        color: var(--color-text-light);
        padding: 2rem;
        background-color: var(--color-card-bg);
        border-radius: var(--radius-md);
        border: 1px dashed var(--color-border);
        margin-bottom: 1.5rem;
      }
      
      .segment-actions {
        display: flex;
        justify-content: center;
        
        .btn {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.75rem 1.5rem;
          border-radius: var(--radius-md);
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
          
          .btn-icon {
            width: 18px;
            height: 18px;
          }
          
          &.btn-primary {
            background-color: var(--color-primary);
            color: white;
            border: none;
            
            &:hover {
              background-color: var(--color-primary-dark);
            }
          }
        }
      }
    }
  }
  </style>