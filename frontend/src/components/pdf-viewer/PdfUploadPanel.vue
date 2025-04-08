<template>
    <div class="pdf-upload-panel">
      <div 
        class="upload-area" 
        :class="{ 'drag-over': isDragging, 'has-file': hasFile }"
        @dragover.prevent="onDragOver"
        @dragleave.prevent="onDragLeave"
        @drop.prevent="onDrop"
        @click="triggerFileInput"
      >
        <input 
          type="file" 
          ref="fileInput"
          accept=".pdf"
          class="file-input" 
          @change="onFileSelected"
        />
        
        <div v-if="!hasFile" class="upload-placeholder">
          <vue-feather type="file-plus" size="48" class="upload-icon"></vue-feather>
          <h3>Upload PDF Document</h3>
          <p>Drag & drop your file here or click to browse</p>
          <p class="file-types">Supported file type: PDF (max 10MB)</p>
        </div>
        
        <div v-else class="file-info">
          <vue-feather type="file-text" size="32" class="file-icon"></vue-feather>
          <div class="file-details">
            <h3 class="file-name">{{ fileName }}</h3>
            <p class="file-size">{{ formattedFileSize }}</p>
          </div>
          <button class="btn-remove" @click.stop="removeFile">
            <vue-feather type="x" size="20"></vue-feather>
          </button>
        </div>
      </div>
      
      <button 
        class="btn btn-primary btn-upload w-100 mt-3" 
        :disabled="!hasFile || isLoading" 
        @click="uploadFile"
      >
        <span v-if="!isLoading">
          <vue-feather type="upload" class="icon"></vue-feather>
          Upload Document
        </span>
        <span v-else class="loading-text">
          <vue-feather type="loader" class="icon spin"></vue-feather>
          Uploading...
        </span>
      </button>
    </div>
  </template>
  
  <script>
  export default {
    name: 'PdfUploadPanel',
    props: {
      isLoading: {
        type: Boolean,
        default: false
      }
    },
    data() {
      return {
        isDragging: false,
        selectedFile: null
      }
    },
    computed: {
      hasFile() {
        return !!this.selectedFile
      },
      fileName() {
        return this.selectedFile ? this.selectedFile.name : ''
      },
      formattedFileSize() {
        if (!this.selectedFile) return ''
        
        const bytes = this.selectedFile.size
        if (bytes < 1024) return bytes + ' bytes'
        else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
        else return (bytes / 1048576).toFixed(1) + ' MB'
      }
    },
    methods: {
      triggerFileInput() {
        if (!this.isLoading) {
          this.$refs.fileInput.click()
        }
      },
      onDragOver(e) {
        this.isDragging = true
        e.dataTransfer.dropEffect = 'copy'
      },
      onDragLeave() {
        this.isDragging = false
      },
      onDrop(e) {
        this.isDragging = false
        const files = e.dataTransfer.files
        if (files.length > 0) {
          this.processFile(files[0])
        }
      },
      onFileSelected(e) {
        const files = e.target.files
        if (files.length > 0) {
          this.processFile(files[0])
        }
      },
      processFile(file) {
        // Check if it's a PDF
        if (!file.type.includes('pdf')) {
          this.$emit('error', 'Please upload a PDF file')
          return
        }
        
        // Check file size (max 10MB)
        const maxSize = 10 * 1024 * 1024 // 10MB in bytes
        if (file.size > maxSize) {
          this.$emit('error', 'File size exceeds 10MB limit')
          return
        }
        
        this.selectedFile = file
        this.$refs.fileInput.value = null // Reset input to allow selecting the same file again
      },
      removeFile(e) {
        e.stopPropagation()
        this.selectedFile = null
      },
      uploadFile() {
        if (this.hasFile && !this.isLoading) {
          this.$emit('pdf-uploaded', this.selectedFile)
        }
      }
    }
  }
  </script>
  
  <style lang="scss" scoped>
  .pdf-upload-panel {
  .upload-area {
    position: relative;
    border: 2px dashed var(--color-border);
    border-radius: 6px;
    padding: 1rem 0.75rem;
    background-color: var(--color-input-bg);
    transition: all 0.3s ease;
    cursor: pointer;
    text-align: center;
    min-height: 100px;
    display: flex;
    align-items: center;
    justify-content: center;
    
    &:hover {
      border-color: var(--color-primary-light);
    }
    
    &.drag-over {
      border-color: var(--color-primary);
      background-color: rgba(74, 77, 231, 0.05);
    }
    
    &.has-file {
      border-style: solid;
      border-color: var(--color-primary-light);
      background-color: rgba(74, 77, 231, 0.05);
    }
  }
  
  .file-input {
    position: absolute;
    width: 0;
    height: 0;
    opacity: 0;
  }
  
  .upload-placeholder {
    .upload-icon {
      color: var(--color-primary);
      margin-bottom: 0.5rem;
      width: 32px;
      height: 32px;
    }
    
    h3 {
      font-size: 1.1rem;
      margin-bottom: 0.25rem;
    }
    
    p {
      color: var(--color-text-light);
      margin-bottom: 0.25rem;
      font-size: 0.9rem;
    }
    
    .file-types {
      font-size: 0.8rem;
    }
  }
  
  .file-info {
    display: flex;
    align-items: center;
    width: 100%;
    
    .file-icon {
      color: var(--color-primary);
      margin-right: 0.75rem;
      flex-shrink: 0;
      width: 24px;
      height: 24px;
    }
    
    .file-details {
      flex: 1;
      min-width: 0;
      
      .file-name {
        font-size: 0.9rem;
        margin: 0 0 0.125rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      
      .file-size {
        color: var(--color-text-light);
        font-size: 0.8rem;
        margin: 0;
      }
    }
    
    .btn-remove {
      background: none;
      border: none;
      color: var(--color-text-light);
      cursor: pointer;
      padding: 0.35rem;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;
      
      &:hover {
        color: var(--color-error);
        background-color: rgba(255, 61, 113, 0.1);
      }
    }
  }
  
  .btn-upload {
    margin-top: 0.5rem;
    
    .icon {
      width: 16px;
      height: 16px;
    }
    
    .loading-text {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.25rem;
    }
    
    .spin {
      animation: spin 1s linear infinite;
    }
  }
}
  
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  </style>