import doclingService from '@/services/doclingService'

/**
 * Vuex module for handling text extraction
 */
export default {
  namespaced: true,
  
  state: {
    content: '',           // Extracted text content
    metadata: null,        // Metadata about the extracted text
    isLoading: false,      // Loading state
    error: null,           // Error information
    extractionHistory: []  // History of extracted texts
  },
  
  mutations: {
    SET_CONTENT(state, content) {
      state.content = content
    },
    SET_METADATA(state, metadata) {
      state.metadata = metadata
    },
    SET_LOADING(state, isLoading) {
      state.isLoading = isLoading
    },
    SET_ERROR(state, error) {
      state.error = error
    },
    CLEAR_ERROR(state) {
      state.error = null
    },
    ADD_TO_HISTORY(state, item) {
      // Check if already in history
      const exists = state.extractionHistory.some(
        historyItem => historyItem.id === item.id
      )
      
      if (!exists) {
        state.extractionHistory.unshift(item)
        
        // Limit history to last 10 items
        if (state.extractionHistory.length > 10) {
          state.extractionHistory.pop()
        }
      }
    }
  },
  
  actions: {
    /**
     * Fetch extracted text from a PDF file
     * @param {Object} context - Vuex action context
     * @param {File} pdfFile - The PDF file to process
     * @param {Object} options - Optional extraction parameters
     */
    async fetchExtractedText({ commit, dispatch }, pdfFile, options = {}) {
      if (!pdfFile) {
        commit('SET_ERROR', 'No PDF file provided')
        return
      }
      
      commit('SET_LOADING', true)
      commit('CLEAR_ERROR')
      
      try {
        // Call the API to extract text
        const response = await doclingService.extractText(pdfFile, options)
        
        // Check if text was successfully extracted
        if (response && response.text) {
          commit('SET_CONTENT', response.text)
          
          // Set metadata
          const metadata = {
            pdfFilename: response.pdf_filename,
            extractedAt: new Date().toISOString(),
            characterCount: response.text.length,
            wordCount: response.text.split(/\s+/).length
          }
          commit('SET_METADATA', metadata)
          
          // Add to extraction history
          const historyItem = {
            id: new Date().getTime(),
            pdfFilename: response.pdf_filename,
            extractedAt: new Date().toISOString(),
            textPreview: response.text.substring(0, 100) + '...',
            characterCount: response.text.length
          }
          commit('ADD_TO_HISTORY', historyItem)
          
          // Show success notification
          dispatch('showNotification', {
            type: 'success',
            message: 'Text extracted successfully'
          }, { root: true })
        } else {
          throw new Error('No text content in response')
        }
      } catch (error) {
        commit('SET_ERROR', error.message || 'Failed to extract text')
        
        // Show error notification
        dispatch('showNotification', {
          type: 'error',
          message: error.message || 'Failed to extract text'
        }, { root: true })
      } finally {
        commit('SET_LOADING', false)
      }
    },
    
    /**
     * Clear the current extracted text
     * @param {Object} context - Vuex action context
     */
    clearExtractedText({ commit }) {
      commit('SET_CONTENT', '')
      commit('SET_METADATA', null)
      commit('CLEAR_ERROR')
    }
  },
  
  getters: {
    hasText: state => !!state.content,
    wordCount: state => {
      if (!state.content) return 0
      return state.content.split(/\s+/).filter(word => word.length > 0).length
    },
    characterCount: state => state.content ? state.content.length : 0
  }
}