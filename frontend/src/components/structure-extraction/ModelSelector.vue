<template>
  <div class="model-selector">
    <!-- Model Selection Header -->
    <div class="model-header">
      <h4 class="model-title">Choose a model:</h4>
    </div>
    
    <!-- Model Options -->
    <div class="model-options">
      <!-- DECIMER Model -->
      <div 
        class="model-button"
        :class="{ 
          active: modelValue === 'decimer',
          disabled: disabled 
        }"
        @click="selectModel('decimer')"
        role="button"
        tabindex="0"
        @keydown.enter="selectModel('decimer')"
        @keydown.space="selectModel('decimer')"
      >
        <input 
          type="radio" 
          id="decimer" 
          name="model" 
          value="decimer"
          :checked="modelValue === 'decimer'"
          :disabled="disabled"
          class="model-radio"
        />
        
        <div class="model-icon decimer-icon">
          <vue-feather type="cpu" class="icon"></vue-feather>
        </div>
        
        <div class="model-content">
          <div class="model-name">DECIMER</div>
          <div class="model-subtitle">Deep learning based optical chemical structure recognition</div>
        </div>
      </div>
      
      <!-- MolNexTR Model -->
      <div 
        class="model-button"
        :class="{ 
          active: modelValue === 'molnextr',
          disabled: disabled 
        }"
        @click="selectModel('molnextr')"
        role="button"
        tabindex="0"
        @keydown.enter="selectModel('molnextr')"
        @keydown.space="selectModel('molnextr')"
      >
        <input 
          type="radio" 
          id="molnextr" 
          name="model" 
          value="molnextr"
          :checked="modelValue === 'molnextr'"
          :disabled="disabled"
          class="model-radio"
        />
        
        <div class="model-icon molnextr-icon">
          <vue-feather type="grid" class="icon"></vue-feather>
        </div>
        
        <div class="model-content">
          <div class="model-name">MolNexTR</div>
          <div class="model-subtitle">ConvNext based Image-to-graph model with enhanced spatial understanding</div>
        </div>
      </div>
      
      <!-- MolScribe Model -->
      <div 
        class="model-button"
        :class="{ 
          active: modelValue === 'molscribe',
          disabled: disabled 
        }"
        @click="selectModel('molscribe')"
        role="button"
        tabindex="0"
        @keydown.enter="selectModel('molscribe')"
        @keydown.space="selectModel('molscribe')"
      >
        <input 
          type="radio" 
          id="molscribe" 
          name="model" 
          value="molscribe"
          :checked="modelValue === 'molscribe'"
          :disabled="disabled"
          class="model-radio"
        />
        
        <div class="model-icon molscribe-icon">
          <vue-feather type="edit-3" class="icon"></vue-feather>
        </div>
        
        <div class="model-content">
          <div class="model-name">MolScribe</div>
          <div class="model-subtitle">Swin Transformer based image to graph generation with state-of-the-art performance</div>
        </div>
      </div>
    </div>
    
    <!-- Configuration Section -->
    <div class="model-configuration" v-if="modelValue">
      <!-- DECIMER Options -->
      <div v-if="modelValue === 'decimer'" class="config-group">
        <div class="toggle-option">
          <div class="toggle-switch" @click="toggleHandDrawn">
            <div 
              class="switch-track"
              :class="{ active: handDrawn }"
            >
              <div class="switch-thumb"></div>
            </div>
            <div class="toggle-content">
              <span class="toggle-label">Use Hand-drawn model</span>
              <span class="toggle-subtitle">Optimized for hand-drawn chemical structures</span>
            </div>
          </div>
        </div>
      </div>
      
      <!-- MolNexTR & MolScribe Options -->
      <div v-if="modelValue === 'molnextr' || modelValue === 'molscribe'" class="config-group">
        <div class="toggle-option">
          <div class="toggle-switch" @click="toggleCoordinates">
            <div 
              class="switch-track"
              :class="{ active: includeCoordinates }"
            >
              <div class="switch-thumb"></div>
            </div>
            <span class="toggle-label">Include atom coordinates</span>
          </div>
        </div>
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

    toggleHandDrawn() {
      if (this.disabled) return
      this.handDrawn = !this.handDrawn
      this.updateOptions()
    },

    toggleCoordinates() {
      if (this.disabled) return
      this.includeCoordinates = !this.includeCoordinates
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
  background: linear-gradient(145deg, #f8fafc 0%, #eef2ff 100%);
  border-radius: 16px;
  padding: 1.5rem;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(10px);

  /* Model Header */
  .model-header {
    margin-bottom: 1rem;

    .model-title {
      font-size: 1rem;
      font-weight: 600;
      color: #374151;
      margin: 0;
      letter-spacing: -0.01em;
    }
  }

  /* Model Options */
  .model-options {
    display: flex;
    gap: 0.75rem;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;

    @media (max-width: 768px) {
      flex-direction: column;
    }
  }

  .model-button {
    flex: 1;
    min-width: 120px;
    background: rgba(255, 255, 255, 0.9);
    border: 2px solid rgba(226, 232, 240, 0.8);
    border-radius: 8px;
    padding: 0.75rem 1rem;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    display: flex;
    align-items: center;
    gap: 0.75rem;
    position: relative;
    overflow: hidden;

    &::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.1) 0%, rgba(255, 255, 255, 0) 100%);
      opacity: 0;
      transition: opacity 0.3s ease;
      z-index: 1;
    }

    .model-radio {
      position: absolute;
      opacity: 0;
      pointer-events: none;
    }

    &:hover:not(.disabled) {
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
      border-color: rgba(99, 102, 241, 0.3);

      &::before {
        opacity: 1;
      }
    }

    &.active {
      border-color: #6366f1;
      background: rgba(99, 102, 241, 0.05);
      box-shadow: 0 0 0 1px rgba(99, 102, 241, 0.2), 0 4px 12px rgba(99, 102, 241, 0.15);
    }

    &.disabled {
      opacity: 0.6;
      cursor: not-allowed;
      pointer-events: none;
    }

    .model-icon {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
      position: relative;
      z-index: 2;

      .icon {
        width: 16px;
        height: 16px;
        color: white;
      }

      &.decimer-icon {
        background: linear-gradient(135deg, #ff9500 0%, #ff7b00 100%);
      }

      &.molnextr-icon {
        background: linear-gradient(135deg, #059669 0%, #047857 100%);
      }

      &.molscribe-icon {
        background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
      }
    }

    .model-title {
      font-size: 0.875rem;
      font-weight: 600;
      color: #1f2937;
      letter-spacing: -0.01em;
      position: relative;
      z-index: 2;
    }

    .model-content {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      flex: 1;
      position: relative;
      z-index: 2;

      .model-name {
        font-size: 0.875rem;
        font-weight: 600;
        color: #1f2937;
        letter-spacing: -0.01em;
        line-height: 1.2;
      }

      .model-subtitle {
        font-size: 0.75rem;
        font-weight: 400;
        color: #6b7280;
        line-height: 1.3;
        letter-spacing: -0.005em;
      }
    }
  }

  /* Configuration Section */
  .model-configuration {
    background: rgba(255, 255, 255, 0.7);
    border: 1px solid rgba(226, 232, 240, 0.8);
    border-radius: 12px;
    padding: 1rem;
    backdrop-filter: blur(8px);

    .config-group {
      margin: 0;
    }

    .toggle-option {
      .toggle-switch {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        cursor: pointer;
        padding: 0.5rem;
        border-radius: 8px;
        transition: all 0.2s ease;

        &:hover {
          background: rgba(248, 250, 252, 0.8);
        }

        .switch-track {
          position: relative;
          width: 2.5rem;
          height: 1.375rem;
          background: #e5e7eb;
          border-radius: 0.6875rem;
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          flex-shrink: 0;

          .switch-thumb {
            position: absolute;
            top: 0.125rem;
            left: 0.125rem;
            width: 1.125rem;
            height: 1.125rem;
            background: white;
            border-radius: 50%;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
          }

          &.active {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);

            .switch-thumb {
              transform: translateX(1.125rem);
              box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
            }
          }
        }

        .toggle-label {
          font-weight: 500;
          color: #374151;
          font-size: 0.875rem;
        }

        .toggle-content {
          display: flex;
          flex-direction: column;
          gap: 0.125rem;

          .toggle-label {
            font-weight: 500;
            color: #374151;
            font-size: 0.875rem;
            line-height: 1.2;
          }

          .toggle-subtitle {
            font-size: 0.75rem;
            font-weight: 400;
            color: #6b7280;
            line-height: 1.3;
            letter-spacing: -0.005em;
          }
        }
      }
    }
  }

  /* Responsive Design */
  @media (max-width: 767px) {
    padding: 1rem;

    .model-header {
      margin-bottom: 0.75rem;

      .model-title {
        font-size: 0.9rem;
      }
    }

    .model-options {
      gap: 0.5rem;
      margin-bottom: 1rem;
    }

    .model-button {
      padding: 0.625rem 0.75rem;
      min-width: auto;

      .model-icon {
        width: 28px;
        height: 28px;

        .icon {
          width: 14px;
          height: 14px;
        }
      }

      .model-content {
        .model-name {
          font-size: 0.8125rem;
        }

        .model-subtitle {
          font-size: 0.6875rem;
        }
      }
    }

    .model-configuration {
      padding: 0.75rem;
    }
  }

  /* Animation keyframes */
  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .model-configuration {
    animation: slideIn 0.3s ease-out;
  }
}
</style>