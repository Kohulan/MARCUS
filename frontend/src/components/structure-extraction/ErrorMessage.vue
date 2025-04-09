<template>
  <div class="error-message" :class="type">
    <vue-feather :type="icon" class="icon"></vue-feather>
    <span class="message">{{ message }}</span>
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
    type: {
      type: String,
      default: 'error',
      validator: (value) => ['error', 'warning', 'info'].includes(value)
    }
  },
  computed: {
    icon() {
      const icons = {
        error: 'alert-circle',
        warning: 'alert-triangle',
        info: 'info'
      }
      return icons[this.type] || 'alert-circle'
    }
  }
}
</script>

<style lang="scss" scoped>
.error-message {
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  border-radius: 4px;
  margin-bottom: 1rem;
  
  &.error {
    background-color: rgba(220, 53, 69, 0.1);
    border: 1px solid rgba(220, 53, 69, 0.3);
    color: #dc3545;
  }
  
  &.warning {
    background-color: rgba(255, 193, 7, 0.1);
    border: 1px solid rgba(255, 193, 7, 0.3);
    color: #e0a800;
  }
  
  &.info {
    background-color: rgba(13, 110, 253, 0.1);
    border: 1px solid rgba(13, 110, 253, 0.3);
    color: #0d6efd;
  }
  
  .icon {
    margin-right: 0.5rem;
    width: 16px;
    height: 16px;
  }
  
  .message {
    font-size: 0.9rem;
  }
}
</style>