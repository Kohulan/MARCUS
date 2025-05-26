<template>
  <div class="model-selector">
    <label class="selector-label">Choose Model:</label>
    
    <div class="model-options">
      <div 
        class="model-option"
        :class="{ active: modelValue === 'decimer' }"
        @click="selectModel('decimer')"
        :disabled="disabled"
      >
        <input 
          type="radio" 
          id="decimer" 
          name="model" 
          value="decimer"
          :checked="modelValue === 'decimer'"
          :disabled="disabled"
          @change="selectModel('decimer')"
        />
        <label for="decimer" class="option-label">
          <span class="option-icon decimer-icon">
            <vue-feather type="cpu" class="icon"></vue-feather>
          </span>
          <span class="option-text">
            <span class="option-title">DECIMER</span>
            <span class="option-description">Deep learning based optical chemical structure recognition</span>
          </span>
        </label>
      </div>
      
      <div 
        class="model-option"
        :class="{ active: modelValue === 'molnextr' }"
        @click="selectModel('molnextr')"
        :disabled="disabled"
      >
        <input 
          type="radio" 
          id="molnextr" 
          name="model" 
          value="molnextr"
          :checked="modelValue === 'molnextr'"
          :disabled="disabled"
          @change="selectModel('molnextr')"
        />
        <label for="molnextr" class="option-label">
          <span class="option-icon molnextr-icon">
            <vue-feather type="grid" class="icon"></vue-feather>
          </span>
          <span class="option-text">
            <span class="option-title">MolNexTR</span>
            <span class="option-description">ConvNext based Image-to-graph model</span>
          </span>
        </label>
      </div>
      
      <!-- New MolScribe option -->
      <div 
        class="model-option"
        :class="{ active: modelValue === 'molscribe' }"
        @click="selectModel('molscribe')"
        :disabled="disabled"
      >
        <input 
          type="radio" 
          id="molscribe" 
          name="model" 
          value="molscribe"
          :checked="modelValue === 'molscribe'"
          :disabled="disabled"
          @change="selectModel('molscribe')"
        />
        <label for="molscribe" class="option-label">
          <span class="option-icon molscribe-icon">
            <vue-feather type="edit-3" class="icon"></vue-feather>
          </span>
          <span class="option-text">
            <span class="option-title">MolScribe</span>
            <span class="option-description">Swin Transformer based image to graph Generation</span>
          </span>
        </label>
      </div>
    </div>
    
    <div class="model-details">
      <div v-if="modelValue === 'decimer'" class="model-detail-item">
        <label class="checkbox-container">
          <input 
            type="checkbox" 
            v-model="handDrawn"
            :disabled="disabled"
          />
          <span class="checkmark"></span>
          <span class="checkbox-label">Use hand-drawn model</span>
        </label>
        <p class="detail-description">Optimized for hand-drawn chemical structures</p>
      </div>
      
      <div v-if="modelValue === 'molnextr' || modelValue === 'molscribe'" class="model-detail-item">
        <label class="checkbox-container">
          <input 
            type="checkbox" 
            v-model="includeCoordinates"
            :disabled="disabled"
          />
          <span class="checkmark"></span>
          <span class="checkbox-label">Include coordinates (molfile)</span>
        </label>
        <p class="detail-description">Generate molfile with atom coordinates for better depiction</p>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ModelSelector',
  props: {
    modelValue: {
      type: String,
      default: 'decimer'
    },
    disabled: {
      type: Boolean,
      default: false
    }
  },
  emits: ['update:modelValue', 'update:options'],
  data() {
    return {
      handDrawn: false,
      includeCoordinates: true // Default to true for better initial depiction
    }
  },
  watch: {
    handDrawn() {
      this.updateOptions()
    },
    includeCoordinates() {
      this.updateOptions()
    },
    modelValue(newVal) {
      // Reset options when model changes
      if (newVal === 'decimer') {
        this.handDrawn = false;
        this.includeCoordinates = false; // DECIMER doesn't use coordinates
      } else {
        // For MolNexTR and MolScribe, default to using coordinates
        this.includeCoordinates = true;
      }
      this.updateOptions();
    }
  },
  mounted() {
    // Initialize options based on initial model
    if (this.modelValue === 'decimer') {
      this.includeCoordinates = false;
    } else {
      this.includeCoordinates = true;
    }
    this.updateOptions();
  },
  methods: {
    selectModel(model) {
      if (this.disabled) return
      this.$emit('update:modelValue', model)
      
      // Handle model-specific defaults
      if (model === 'decimer') {
        this.includeCoordinates = false; // DECIMER doesn't support molfiles
      } else {
        // Default to using coordinates for MolNexTR and MolScribe
        this.includeCoordinates = true;
      }
      
      this.updateOptions()
    },
    updateOptions() {
      const options = {
        handDrawn: this.handDrawn,
        includeMolfile: this.includeCoordinates
      }
      this.$emit('update:options', options)
    }
  }
}
</script>

<style lang="scss" scoped>
.model-selector {
  width: 100%;
  
  .selector-label {
    display: block;
    font-weight: 500;
    margin-bottom: 0.5rem;
  }
  
  .model-options {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-bottom: 1rem;
    
    @media (min-width: 768px) {
      flex-direction: row;
    }
  }
  
  .model-option {
    flex: 1;
    position: relative;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    padding: 0.75rem;
    cursor: pointer;
    transition: all 0.2s ease;
    overflow: hidden;
    background-color: var(--color-card-bg);
    
    &:hover:not([disabled]) {
      border-color: var(--color-primary-light);
    }
    
    &.active {
      border-color: var(--color-primary);
      background-color: rgba(74, 77, 231, 0.05);
      
      &:before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 4px;
        height: 100%;
        background-color: var(--color-primary);
      }
    }
    
    &[disabled] {
      opacity: 0.6;
      cursor: not-allowed;
    }
    
    input[type="radio"] {
      position: absolute;
      opacity: 0;
      cursor: pointer;
    }
    
    .option-label {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      cursor: pointer;
    }
    
    .option-icon {
      flex-shrink: 0;
      width: 32px;
      height: 32px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      
      .icon {
        color: white;
      }
      
      &.decimer-icon {
        background-color: #ff9500; /* Orange */
      }
      
      &.molnextr-icon {
        background-color: #007aff; /* Blue */
      }
      
      &.molscribe-icon {
        background-color: #2563eb; /* Blue */
      }
    }
    
    .option-text {
      flex: 1;
      min-width: 0;
      
      .option-title {
        display: block;
        font-weight: 600;
        margin-bottom: 0.25rem;
      }
      
      .option-description {
        display: block;
        font-size: 0.8125rem;
        color: var(--color-text-light);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
    }
  }
  
  .model-details {
    padding-top: 0.75rem;
    
    .model-detail-item {
      margin-bottom: 0.5rem;
    }
    
    .checkbox-container {
      display: flex;
      align-items: center;
      position: relative;
      padding-left: 28px;
      cursor: pointer;
      user-select: none;
      
      input {
        position: absolute;
        opacity: 0;
        cursor: pointer;
        height: 0;
        width: 0;
        
        &:checked ~ .checkmark {
          background-color: var(--color-primary);
          border-color: var(--color-primary);
          
          &:after {
            display: block;
          }
        }
        
        &:disabled ~ .checkmark,
        &:disabled ~ .checkbox-label {
          opacity: 0.6;
          cursor: not-allowed;
        }
      }
      
      .checkmark {
        position: absolute;
        top: 0;
        left: 0;
        height: 18px;
        width: 18px;
        background-color: var(--color-card-bg);
        border: 1px solid var(--color-border);
        border-radius: 4px;
        transition: all 0.2s ease;
        
        &:after {
          content: "";
          position: absolute;
          display: none;
          left: 5px;
          top: 2px;
          width: 5px;
          height: 9px;
          border: solid white;
          border-width: 0 2px 2px 0;
          transform: rotate(45deg);
        }
      }
      
      &:hover input:not(:disabled) ~ .checkmark {
        border-color: var(--color-primary-light);
      }
    }
    
    .detail-description {
      margin-left: 28px;
      font-size: 0.8125rem;
      color: var(--color-text-light);
      margin-top: 0.25rem;
    }
  }
}
</style>