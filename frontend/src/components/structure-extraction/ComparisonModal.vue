<template>
    <div class="comparison-modal-backdrop" @click="closeModal">
      <div class="comparison-modal" @click.stop>
        <div class="modal-header">
          <h3 class="modal-title">
            <vue-feather type="bar-chart-2" class="icon"></vue-feather>
            OCSR Engine Comparison
          </h3>
          <button class="modal-close" @click="closeModal">
            <vue-feather type="x" size="24"></vue-feather>
          </button>
        </div>
        
        <div class="modal-body">
          <SimilarityComparison
            :comparison-result="comparisonResult"
            :is-loading="isLoading"
            :error="error"
            :original-smiles-list="smilesList"
          />
        </div>
        
        <div class="modal-footer">
          <button class="btn btn-outline" @click="closeModal">
            <vue-feather type="x" class="icon"></vue-feather>
            Close
          </button>
        </div>
      </div>
    </div>
  </template>
  
  <script>
  import SimilarityComparison from './SimilarityComparison.vue'
  
  export default {
    name: 'ComparisonModal',
    components: {
      SimilarityComparison
    },
    props: {
      comparisonResult: {
        type: Object,
        default: null
      },
      isLoading: {
        type: Boolean,
        default: false
      },
      error: {
        type: String,
        default: ''
      },
      smilesList: {
        type: Array,
        default: () => []
      }
    },
    methods: {
      closeModal() {
        this.$emit('close')
      }
    }
  }
  </script>
  
  <style lang="scss" scoped>
  .comparison-modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    backdrop-filter: blur(3px);
    
    .comparison-modal {
      background-color: var(--color-panel-bg);
      border-radius: 10px;
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.15);
      width: 90%;
      max-width: 900px;
      max-height: 90vh;
      display: flex;
      flex-direction: column;
      animation: modalFadeIn 0.3s ease-out;
      overflow: hidden;
      
      .modal-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 1.5rem;
        border-bottom: 1px solid var(--color-border);
        
        .modal-title {
          font-size: 1.25rem;
          font-weight: 600;
          margin: 0;
          display: flex;
          align-items: center;
          gap: 0.5rem;
          
          .icon {
            color: var(--color-primary);
          }
        }
        
        .modal-close {
          background: none;
          border: none;
          color: var(--color-text-light);
          cursor: pointer;
          transition: all 0.2s ease;
          width: 36px;
          height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 50%;
          
          &:hover {
            background-color: rgba(0, 0, 0, 0.05);
            color: var(--color-text);
            transform: rotate(90deg);
          }
        }
      }
      
      .modal-body {
        flex: 1;
        overflow-y: auto;
        padding: 1rem;
      }
      
      .modal-footer {
        padding: 1rem 1.5rem;
        border-top: 1px solid var(--color-border);
        display: flex;
        justify-content: flex-end;
        gap: 1rem;
        
        .btn {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.5rem 1rem;
          border-radius: 6px;
          font-weight: 500;
          font-size: 0.9rem;
          transition: all 0.2s ease;
          cursor: pointer;
          
          &.btn-outline {
            border: 1px solid var(--color-border);
            background-color: transparent;
            color: var(--color-text);
            
            &:hover {
              background-color: rgba(0, 0, 0, 0.05);
              border-color: var(--color-text-light);
            }
          }
          
          .icon {
            width: 16px;
            height: 16px;
          }
        }
      }
    }
  }
  
  @keyframes modalFadeIn {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  </style>