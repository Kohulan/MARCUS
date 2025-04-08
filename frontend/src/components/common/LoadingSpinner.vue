<template>
    <div class="loading-spinner" :class="{ overlay: overlay, centered: centered }">
      <div class="spinner-container">
        <div class="spinner"></div>
        <p v-if="message" class="spinner-message">{{ message }}</p>
      </div>
    </div>
  </template>
  
  <script>
  export default {
    name: 'LoadingSpinner',
    props: {
      message: {
        type: String,
        default: 'Loading...'
      },
      overlay: {
        type: Boolean,
        default: false
      },
      centered: {
        type: Boolean,
        default: true
      }
    }
  }
  </script>
  
  <style lang="scss" scoped>
  .loading-spinner {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
    
    &.overlay {
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: rgba(255, 255, 255, 0.8);
      z-index: 100;
      backdrop-filter: blur(3px);
      
      @media (prefers-color-scheme: dark) {
        background-color: rgba(21, 23, 42, 0.8);
      }
    }
    
    &.centered {
      min-height: 200px;
    }
    
    .spinner-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    }
    
    .spinner {
      width: 40px;
      height: 40px;
      border: 3px solid rgba(var(--color-primary-rgb), 0.3);
      border-radius: 50%;
      border-top-color: var(--color-primary);
      animation: spin 1s linear infinite;
    }
    
    .spinner-message {
      margin-top: 1rem;
      color: var(--color-text-light);
      font-size: 0.9375rem;
      text-align: center;
    }
  }
  
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  </style>