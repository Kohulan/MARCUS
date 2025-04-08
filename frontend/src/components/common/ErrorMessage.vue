<template>
    <div class="error-message" :class="typeClass">
      <div class="error-icon">
        <vue-feather 
          :type="iconType" 
          class="icon"
        ></vue-feather>
      </div>
      <div class="error-content">
        <h4 v-if="title" class="error-title">{{ title }}</h4>
        <p class="error-text">{{ message }}</p>
        <div v-if="$slots.actions" class="error-actions">
          <slot name="actions"></slot>
        </div>
      </div>
      <button 
        v-if="dismissible" 
        class="error-close"
        @click="$emit('dismiss')"
        aria-label="Dismiss"
      >
        <vue-feather type="x" size="16"></vue-feather>
      </button>
    </div>
  </template>
  
  <script>
  export default {
    name: 'ErrorMessage',
    props: {
      message: {
        type: String,
        required: true
      },
      title: {
        type: String,
        default: ''
      },
      type: {
        type: String,
        default: 'error',
        validator: (value) => ['error', 'warning', 'info', 'success'].includes(value)
      },
      dismissible: {
        type: Boolean,
        default: false
      }
    },
    computed: {
      typeClass() {
        return `type-${this.type}`
      },
      iconType() {
        switch (this.type) {
          case 'error':
            return 'alert-circle'
          case 'warning':
            return 'alert-triangle'
          case 'info':
            return 'info'
          case 'success':
            return 'check-circle'
          default:
            return 'alert-circle'
        }
      }
    }
  }
  </script>
  
  <style lang="scss" scoped>
  .error-message {
    display: flex;
    align-items: flex-start;
    padding: 1rem;
    border-radius: var(--radius-md);
    margin-bottom: 1rem;
    position: relative;
    
    &.type-error {
      background-color: rgba(255, 61, 113, 0.1);
      border-left: 4px solid var(--color-error);
      
      .error-icon {
        color: var(--color-error);
      }
      
      .error-title {
        color: var(--color-error);
      }
    }
    
    &.type-warning {
      background-color: rgba(255, 171, 0, 0.1);
      border-left: 4px solid var(--color-warning);
      
      .error-icon {
        color: var(--color-warning);
      }
      
      .error-title {
        color: var(--color-warning);
      }
    }
    
    &.type-info {
      background-color: rgba(0, 149, 255, 0.1);
      border-left: 4px solid var(--color-info);
      
      .error-icon {
        color: var(--color-info);
      }
      
      .error-title {
        color: var(--color-info);
      }
    }
    
    &.type-success {
      background-color: rgba(0, 200, 83, 0.1);
      border-left: 4px solid var(--color-success);
      
      .error-icon {
        color: var(--color-success);
      }
      
      .error-title {
        color: var(--color-success);
      }
    }
    
    .error-icon {
      margin-right: 0.75rem;
      display: flex;
      align-items: center;
      justify-content: center;
      
      .icon {
        width: 20px;
        height: 20px;
      }
    }
    
    .error-content {
      flex: 1;
      min-width: 0;
      
      .error-title {
        font-size: 1rem;
        font-weight: 600;
        margin-bottom: 0.25rem;
      }
      
      .error-text {
        font-size: 0.9375rem;
        color: var(--color-text);
        margin: 0;
      }
      
      .error-actions {
        margin-top: 0.75rem;
        display: flex;
        gap: 0.5rem;
      }
    }
    
    .error-close {
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
      margin-left: 0.5rem;
      
      &:hover {
        color: var(--color-text);
        background-color: rgba(0, 0, 0, 0.05);
      }
    }
  }
  </style>