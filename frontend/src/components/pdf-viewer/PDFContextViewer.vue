<template>
  <div v-if="showContextView" class="context-view-container">
    <div class="context-view-header">
      <h3>Original Context - Page {{ segment.pageNumber || 1 }}</h3>
      <button class="btn-close" @click="closeContextView">
        <vue-feather type="x" size="16"></vue-feather>
      </button>
    </div>

    <div class="context-view-content">
      <div v-if="isLoadingContext" class="loading-context">
        <div class="loader-pulse"></div>
      </div>
      <img v-else-if="contextImageUrl" :src="contextImageUrl" alt="Segment in context" class="context-image"
        @load="contextImageLoaded" @error="handleContextImageError" />
      <div v-else class="context-error">
        <vue-feather type="alert-triangle" size="24"></vue-feather>
        <p>Failed to load page context</p>
      </div>
    </div>
  </div>
</template>

<script>
import { getApiImageUrl } from '@/services/api'

export default {
  name: 'PDFContextViewer',
  props: {
    segment: {
      type: Object,
      default: null
    },
    showContextView: {
      type: Boolean,
      default: false
    }
  },
  data() {
    return {
      isLoadingContext: false,
      hasContextError: false,
      contextImageUrl: null
    }
  },
  watch: {
    segment: {
      immediate: true,
      handler(newSegment) {
        if (newSegment && this.showContextView) {
          this.loadContextImage();
        }
      }
    },
    showContextView: {
      handler(newValue) {
        if (newValue && this.segment) {
          this.loadContextImage();
        } else if (!newValue && this.contextImageUrl) {
          // Clean up when closing
          URL.revokeObjectURL(this.contextImageUrl);
          this.contextImageUrl = null;
        }
      }
    }
  },
  methods: {
    closeContextView() {
      this.$emit('close');
      if (this.contextImageUrl) {
        URL.revokeObjectURL(this.contextImageUrl);
        this.contextImageUrl = null;
      }
    },

    async loadContextImage() {
      if (!this.segment) return;

      this.isLoadingContext = true;
      this.hasContextError = false;

      try {
        // Log the segment object to debug
        console.log('Segment object:', this.segment);

        // Get segment filename
        const segmentFilename = this.segment.filename;

        if (!segmentFilename) {
          throw new Error('Could not determine segment filename from metadata');
        }

        // Extract PDF filename from the path if pdfFilename is not available
        let pdfFilename;

        if (this.segment.pdfFilename) {
          pdfFilename = this.segment.pdfFilename;
        } else if (this.segment.path) {
          // Extract the directory name from the path which should be the PDF name
          const pathParts = this.segment.path.split('/');
          if (pathParts.length >= 2) {
            // Get the directory name (first part)
            pdfFilename = pathParts[0] + '.pdf';
            console.log('Extracted PDF filename from path:', pdfFilename);
          }
        }

        if (!pdfFilename) {
          throw new Error('Could not determine PDF filename from segment metadata');
        }

        // Get page number from filename
        let pageNumber = 0;
        if (this.segment.pageNumber !== undefined) {
          pageNumber = this.segment.pageNumber;
        } else if (segmentFilename && segmentFilename.startsWith('page_')) {
          const parts = segmentFilename.split('_');
          if (parts.length >= 2) {
            pageNumber = parseInt(parts[1], 10);
            console.log('Extracted page number:', pageNumber);
          }
        }

        // Construct the URL with the proper format for both development and production
        const apiPath = `/decimer/get_highlighted_page/${encodeURIComponent(segmentFilename)}?pdf_filename=${encodeURIComponent(pdfFilename)}`;
        const url = getApiImageUrl(apiPath);

        console.log('Requesting highlighted page:', url);

        // Fetch the highlighted image
        const response = await fetch(url);

        if (!response.ok) {
          // If highlighted page fails, check the response for details
          const errorData = await response.json().catch(() => ({}));
          console.error('Highlighted page error:', errorData);

          // Fall back to getting the segment image at a larger size
          console.log('Falling back to segment image');

          // Try to use segment image URL if available
          if (this.segment.imageUrl) {
            this.contextImageUrl = getApiImageUrl(this.segment.imageUrl);
            this.$emit('notification', {
              type: 'warning',
              message: 'Showing segment only - page context is not available'
            });
          } else if (this.segment.path) {
            this.contextImageUrl = getApiImageUrl(this.segment.path);
            this.$emit('notification', {
              type: 'warning',
              message: 'Showing segment only - page context is not available'
            });
          } else {
            throw new Error(`Failed to load page context: ${errorData.detail || response.statusText}`);
          }
        } else {
          const blob = await response.blob();
          this.contextImageUrl = URL.createObjectURL(blob);
        }
      } catch (error) {
        console.error('Error loading context image:', error);
        this.hasContextError = true;

        // As a last resort, if we have the segment image URL, just show that
        if (this.segment.imageUrl) {
          this.contextImageUrl = getApiImageUrl(this.segment.imageUrl);
          this.$emit('notification', {
            type: 'warning',
            message: 'Showing segment only - full page context not available'
          });
        } else if (this.segment.path) {
          this.contextImageUrl = getApiImageUrl(this.segment.path);
          this.$emit('notification', {
            type: 'warning',
            message: 'Showing segment only - full page context not available'
          });
        } else {
          this.$emit('error', `Failed to load context image: ${error.message}`);
        }
      } finally {
        this.isLoadingContext = false;
      }
    },

    contextImageLoaded() {
      this.isLoadingContext = false;
    },

    handleContextImageError() {
      this.isLoadingContext = false;
      this.hasContextError = true;
      this.$emit('error', 'Failed to load page context image');
    }
  }
}
</script>

<style lang="scss" scoped>
.context-view-container {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.85);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(8px);
  animation: fadeIn 0.3s ease;

  .context-view-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.25rem 1.5rem;
    background-color: rgba(255, 255, 255, 0.95);
    border-bottom: 1px solid #e2e8f0;
    backdrop-filter: blur(8px);

    h3 {
      margin: 0;
      font-size: 1.25rem;
      color: #0f172a;
      font-weight: 600;
    }

    .btn-close {
      background: none;
      border: none;
      color: #64748b;
      cursor: pointer;
      padding: 0.5rem;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;

      &:hover {
        background-color: #fee2e2;
        color: #ef4444;
        transform: rotate(90deg);
      }
    }
  }

  .context-view-content {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
    overflow: auto;

    .loading-context {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;

      .loader-pulse {
        width: 70px;
        height: 70px;
        border-radius: 50%;
        background-color: rgba(255, 255, 255, 0.2);
        animation: pulse 1.5s ease-in-out infinite;
        margin-bottom: 1.5rem;
        box-shadow: 0 0 30px rgba(255, 255, 255, 0.3);
      }
    }

    .context-image {
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      background-color: white;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
      border-radius: 4px;
      transition: transform 0.3s ease;

      &:hover {
        transform: scale(1.02);
      }
    }

    .context-error {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 1.25rem;
      color: white;

      svg {
        filter: drop-shadow(0 2px 8px rgba(255, 255, 255, 0.2));
      }

      p {
        margin: 0;
        font-size: 1.125rem;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
      }
    }
  }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes pulse {
  0% { transform: scale(1); opacity: 0.7; }
  50% { transform: scale(1.1); opacity: 0.9; }
  100% { transform: scale(1); opacity: 0.7; }
}
</style>