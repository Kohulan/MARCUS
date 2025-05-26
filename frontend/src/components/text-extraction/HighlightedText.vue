<template>
  <div class="highlighted-text">
    <div v-html="highlightedText"></div>
  </div>
</template>

<script>
export default {
  name: 'HighlightedText',
  props: {
    text: {
      type: String,
      required: true
    },
    annotations: {
      type: Array,
      default: () => []
    }
  },
  computed: {
    highlightedText() {
      if (!this.text) return ''
      if (!this.annotations || this.annotations.length === 0) {
        return this.formatPlainText(this.text)
      }
      
      // Use a marker-based approach to avoid HTML parsing issues
      let markers = []
      
      // Create markers for start and end of each annotation
      this.annotations.forEach(annotation => {
        const { start_offset, end_offset, label } = annotation
        
        if (start_offset >= 0 && end_offset <= this.text.length && start_offset < end_offset) {
          // Create a unique ID for this annotation
          const id = `annotation-${start_offset}-${end_offset}`
          
          // Push start and end markers
          markers.push({
            position: start_offset,
            content: `<span class="highlight" data-label="${label}" id="${id}">`,
            isStart: true,
            priority: 1 // Start tags have higher priority
          })
          
          markers.push({
            position: end_offset,
            content: '</span>',
            isStart: false,
            priority: 0 // End tags have lower priority
          })
        }
      })
      
      // Sort markers by position, then priority (to ensure proper nesting)
      markers.sort((a, b) => {
        if (a.position !== b.position) {
          return a.position - b.position
        }
        return b.priority - a.priority
      })
      
      // Apply markers to text
      let result = this.text
      let offset = 0
      
      markers.forEach(marker => {
        const adjustedPosition = marker.position + offset
        result = result.slice(0, adjustedPosition) + marker.content + result.slice(adjustedPosition)
        offset += marker.content.length
      })
      
      // Format text for display (paragraphs, etc.)
      return this.formatPlainText(result)
    }
  },
  methods: {
    formatPlainText(text) {
      // Convert line breaks to <br> tags and wrap in paragraphs
      return text
        .split(/\n\n+/) // Split on multiple line breaks
        .map(para => {
          // Replace single line breaks with <br>
          const formatted = para.replace(/\n/g, '<br>')
          return `<p>${formatted}</p>`
        })
        .join('')
    },
    getLabelColor(label) {
      // Generate a consistent color based on the label string
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
    }
  },
  mounted() {
    // Apply colors to highlights after the component is mounted
    this.$nextTick(() => {
      if (this.$el) {
        const highlights = this.$el.querySelectorAll('.highlight')
        highlights.forEach(highlight => {
          const label = highlight.getAttribute('data-label')
          if (label) {
            const color = this.getLabelColor(label)
            highlight.style.borderBottom = `2px solid ${color}`
            highlight.style.backgroundColor = `${color}25`
          }
        })
      }
    })
  },
  updated() {
    // Reapply colors when component updates
    this.$nextTick(() => {
      if (this.$el) {
        const highlights = this.$el.querySelectorAll('.highlight')
        highlights.forEach(highlight => {
          const label = highlight.getAttribute('data-label')
          if (label) {
            const color = this.getLabelColor(label)
            highlight.style.borderBottom = `2px solid ${color}`
            highlight.style.backgroundColor = `${color}25`
          }
        })
      }
    })
  }
}
</script>

<style lang="scss" scoped>
.highlighted-text {
  font-size: 1rem;
  line-height: 1.6;
  color: var(--color-text);
  
  ::v-deep(p) {
    margin-bottom: 1rem;
    
    &:last-child {
      margin-bottom: 0;
    }
  }
  
  ::v-deep(.highlight) {
    position: relative;
    border-radius: 2px;
    padding: 0 2px;
    margin: 0 1px;
    cursor: pointer;
    transition: all 0.2s ease;
    
    &:hover {
      opacity: 0.9;
    }
    
    &::after {
      content: attr(data-label);
      position: absolute;
      top: -28px;
      left: 50%;
      transform: translateX(-50%) scale(0);
      background: var(--color-text-dark);
      color: white;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 0.75rem;
      white-space: nowrap;
      z-index: 10;
      opacity: 0;
      transition: all 0.2s ease;
      pointer-events: none;
    }
    
    &:hover::after {
      transform: translateX(-50%) scale(1);
      opacity: 1;
    }
  }
}
</style>