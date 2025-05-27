<template>
  <div class="annotation-viewer">
    <div v-if="isEmpty" class="empty-state">
      <p>No annotations found</p>
    </div>
    
    <div v-else>
      <div class="annotation-filters">
        <div class="filter-label">Filter by type:</div>
        <div class="filter-options">
          <button 
            class="filter-btn" 
            :class="{ active: selectedFilter === 'all' }"
            @click="setFilter('all')"
          >
            All
          </button>
          
          <button 
            v-for="label in uniqueLabels" 
            :key="label"
            class="filter-btn"
            :class="{ active: selectedFilter === label }"
            :style="getLabelStyles(label)"
            @click="setFilter(label)"
          >
            {{ formatLabel(label) }}
          </button>
        </div>
      </div>
      
      <div class="annotation-list">
        <div 
          v-for="(annotation, index) in filteredAnnotations" 
          :key="index"
          class="annotation-item"
          :style="getItemStyles(annotation.label)"
        >
          <div class="annotation-header">
            <span 
              class="annotation-label"
              :style="getLabelStyles(annotation.label)"
            >
              {{ formatLabel(annotation.label) }}
            </span>
          </div>
          
          <div class="annotation-text">
            "{{ annotation.text }}"
          </div>
        </div>
      </div>
      
      <div v-if="hasFilteredResults" class="annotation-summary">
        Showing {{ filteredAnnotations.length }} of {{ annotations.length }} annotations
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'AnnotationViewer',
  props: {
    annotations: {
      type: Array,
      default: () => []
    }
  },
  data() {
    return {
      selectedFilter: 'all'
    }
  },
  computed: {
    isEmpty() {
      return !this.annotations || this.annotations.length === 0
    },
    uniqueLabels() {
      if (this.isEmpty) return []
      
      // Extract unique labels
      const labels = new Set(this.annotations.map(ann => ann.label))
      return [...labels]
    },
    filteredAnnotations() {
      if (this.isEmpty) return []
      if (this.selectedFilter === 'all') return this.annotations
      
      return this.annotations.filter(ann => ann.label === this.selectedFilter)
    },
    hasFilteredResults() {
      return this.selectedFilter !== 'all' && this.filteredAnnotations.length > 0
    }
  },
  methods: {
    setFilter(label) {
      this.selectedFilter = label
    },
    formatLabel(label) {
      if (!label) return ''
      
      // Format the label for display (capitalize, replace underscores, etc.)
      return label
        .replace(/_/g, ' ')
        .replace(/\b\w/g, char => char.toUpperCase())
    },
    getLabelColor(label) {
      // Generate a consistent color based on the label string (same function as in HighlightedText)
      const colors = [
        '#1e3a8a', // Primary (navy blue)
        '#2563eb', // Secondary (blue)
        '#00c853', // Success (green)
        '#ff3d71', // Error (red)
        '#ffab00', // Warning (orange)
        '#0095ff', // Info (light blue)
        '#ff6b6b', // Coral
        '#4facfe', // Light blue
        '#42d392', // Mint
        '#a78bfa'  // Lavender
      ]
      
      // Simple hash function for string to number
      const hash = label.split('').reduce((acc, char) => {
        return char.charCodeAt(0) + ((acc << 5) - acc)
      }, 0)
      
      // Use the hash to select a color
      const index = Math.abs(hash) % colors.length
      return colors[index]
    },
    getLabelStyles(label) {
      const color = this.getLabelColor(label)
      return {
        'background-color': `${color}25`, // 25% opacity
        'color': color
      }
    },
    getItemStyles(label) {
      const color = this.getLabelColor(label)
      return {
        'border-left-color': color
      }
    }
  }
}
</script>

<style lang="scss" scoped>
.annotation-viewer {
  .empty-state {
    text-align: center;
    padding: 1.5rem;
    color: var(--color-text-light);
  }
  
  .annotation-filters {
    margin-bottom: 1rem;
    
    .filter-label {
      font-size: 0.875rem;
      font-weight: 500;
      margin-bottom: 0.5rem;
    }
    
    .filter-options {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }
    
    .filter-btn {
      background: var(--color-card-bg);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-full);
      padding: 0.25rem 0.75rem;
      font-size: 0.875rem;
      cursor: pointer;
      transition: all 0.2s ease;
      
      &:hover:not(.active) {
        border-color: var(--color-border-hover);
      }
      
      &.active {
        font-weight: 500;
      }
    }
  }
  
  .annotation-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    max-height: 300px;
    overflow-y: auto;
  }
  
  .annotation-item {
    background-color: var(--color-input-bg);
    border-radius: var(--radius-md);
    padding: 0.75rem;
    border-left: 3px solid var(--color-primary);
    
    .annotation-header {
      margin-bottom: 0.5rem;
      
      .annotation-label {
        display: inline-block;
        padding: 0.125rem 0.5rem;
        border-radius: var(--radius-full);
        font-size: 0.75rem;
        font-weight: 500;
      }
    }
    
    .annotation-text {
      font-size: 0.9375rem;
      color: var(--color-text);
      font-style: italic;
    }
  }
  
  .annotation-summary {
    margin-top: 1rem;
    font-size: 0.875rem;
    color: var(--color-text-light);
    text-align: right;
  }
}
</style>