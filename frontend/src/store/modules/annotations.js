import openaiService from '@/services/openaiService'

/**
 * Vuex module for handling annotations/named entities extraction
 */
export default {
  namespaced: true,
  
  state: {
    items: [],            // Array of annotation items
    rawData: null,        // Raw annotation data from API
    isLoading: false,     // Loading state
    error: null,          // Error information
    savedFilename: null   // Filename of saved annotation result on server
  },
  
  mutations: {
    SET_ITEMS(state, items) {
      state.items = items
    },
    SET_RAW_DATA(state, data) {
      state.rawData = data
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
    SET_SAVED_FILENAME(state, filename) {
      state.savedFilename = filename
    }
  },
  
  actions: {
    /**
     * Fetch annotations for a text
     * @param {Object} context - Vuex action context
     * @param {string} text - The text to analyze
     */
    async fetchAnnotations({ commit, dispatch }, text) {
      if (!text || typeof text !== 'string' || text.trim() === '') {
        commit('SET_ERROR', 'No text provided for annotation')
        return
      }
      
      commit('SET_LOADING', true)
      commit('CLEAR_ERROR')
      
      try {
        // Call the API to extract annotations
        const response = await openaiService.extractAll(text)
        
        // Process the positions data into annotation items
        if (response && response.positions && Array.isArray(response.positions)) {
          const annotationItems = response.positions.map(position => {
            return {
              label: position.label,
              start_offset: position.start_offset,
              end_offset: position.end_offset,
              text: text.substring(position.start_offset, position.end_offset)
            }
          })
          
          commit('SET_ITEMS', annotationItems)
          commit('SET_RAW_DATA', response.extracted_data || {})
          
          if (response.saved_as) {
            commit('SET_SAVED_FILENAME', response.saved_as)
          }
          
          // Show success notification
          dispatch('showNotification', {
            type: 'success',
            message: `Extracted ${annotationItems.length} annotations`
          }, { root: true })
        } else {
          throw new Error('Invalid annotation data received')
        }
      } catch (error) {
        commit('SET_ERROR', error.message || 'Failed to extract annotations')
        
        // Show error notification
        dispatch('showNotification', {
          type: 'error',
          message: error.message || 'Failed to extract annotations'
        }, { root: true })
      } finally {
        commit('SET_LOADING', false)
      }
    },
    
    /**
     * Load a saved annotation from the server
     * @param {Object} context - Vuex action context
     * @param {string} filename - The saved annotation filename
     */
    async loadSavedAnnotation({ commit, dispatch }, filename) {
      if (!filename) {
        commit('SET_ERROR', 'No filename provided')
        return
      }
      
      commit('SET_LOADING', true)
      commit('CLEAR_ERROR')
      
      try {
        // Call the API to get the saved annotation
        const response = await openaiService.getExtraction(filename)
        
        if (response && response.positions && Array.isArray(response.positions)) {
          const text = response.input_text || ''
          
          const annotationItems = response.positions.map(position => {
            return {
              label: position.label,
              start_offset: position.start_offset,
              end_offset: position.end_offset,
              text: text.substring(position.start_offset, position.end_offset)
            }
          })
          
          commit('SET_ITEMS', annotationItems)
          commit('SET_RAW_DATA', response.extracted_json || {})
          commit('SET_SAVED_FILENAME', filename)
          
          // Show success notification
          dispatch('showNotification', {
            type: 'success',
            message: `Loaded ${annotationItems.length} annotations from saved result`
          }, { root: true })
          
          // Return the text in case we need to update it in another store
          return text
        } else {
          throw new Error('Invalid saved annotation data')
        }
      } catch (error) {
        commit('SET_ERROR', error.message || 'Failed to load saved annotation')
        
        // Show error notification
        dispatch('showNotification', {
          type: 'error',
          message: error.message || 'Failed to load saved annotation'
        }, { root: true })
        
        return null
      } finally {
        commit('SET_LOADING', false)
      }
    },
    
    /**
     * Clear the current annotations
     * @param {Object} context - Vuex action context
     */
    clearAnnotations({ commit }) {
      commit('SET_ITEMS', [])
      commit('SET_RAW_DATA', null)
      commit('SET_SAVED_FILENAME', null)
      commit('CLEAR_ERROR')
    }
  },
  
  getters: {
    hasAnnotations: state => state.items && state.items.length > 0,
    annotationsByType: state => {
      if (!state.items || state.items.length === 0) {
        return {}
      }
      
      // Group annotations by their label/type
      return state.items.reduce((groups, item) => {
        const label = item.label
        if (!groups[label]) {
          groups[label] = []
        }
        groups[label].push(item)
        return groups
      }, {})
    },
    annotationTypes: state => {
      if (!state.items || state.items.length === 0) {
        return []
      }
      
      // Get unique annotation types/labels
      return [...new Set(state.items.map(item => item.label))]
    },
    annotationCount: state => state.items ? state.items.length : 0
  }
}