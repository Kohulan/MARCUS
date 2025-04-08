/**
 * Vuex module for handling PDF operations
 */
export default {
  namespaced: true,
  
  state: {
    file: null,        // The PDF file object
    url: null,         // URL to the PDF file
    info: null,        // PDF metadata
    uploadedFiles: [], // History of uploaded files
    error: null,       // Error information
    currentPdfId: null // ID of the current PDF being processed
  },
  
  mutations: {
    SET_PDF_FILE(state, file) {
      state.file = file
    },
    SET_PDF_URL(state, url) {
      state.url = url
    },
    SET_PDF_INFO(state, info) {
      state.info = info
    },
    SET_CURRENT_PDF_ID(state, pdfId) {
      state.currentPdfId = pdfId
    },
    ADD_UPLOADED_FILE(state, fileInfo) {
      // Check if file is already in the list
      const exists = state.uploadedFiles.some(
        item => item.name === fileInfo.name
      )
      
      if (!exists) {
        state.uploadedFiles.unshift(fileInfo)
      }
    },
    SET_ERROR(state, error) {
      state.error = error
    },
    CLEAR_ERROR(state) {
      state.error = null
    }
  },
  
  actions: {
    /**
     * Set the current PDF file
     * @param {Object} context - Vuex action context
     * @param {Object} payload - The PDF file payload
     * @param {File} payload.file - The PDF file object
     * @param {string} payload.url - Optional URL for the PDF (if already created)
     * @param {string} payload.pdfId - Optional PDF ID (if already created)
     */
    setPdfFile({ commit, dispatch, state }, payload) {
      return new Promise((resolve, reject) => {
        try {
          let file, url, pdfId;
          
          // Check if payload is a File or an object with file property
          if (payload instanceof File) {
            file = payload;
            url = URL.createObjectURL(file);
          } else if (payload.file) {
            file = payload.file;
            url = payload.url || URL.createObjectURL(file);
            pdfId = payload.pdfId;
          } else {
            reject(new Error('Invalid payload for setPdfFile'));
            return;
          }
          
          if (!file) {
            reject(new Error('No file provided'));
            return;
          }
          
          // Check if file is a PDF
          if (file.type !== 'application/pdf') {
            reject(new Error('File is not a PDF'));
            return;
          }
          
          // Check if we're loading a different PDF
          const isNewPdf = !state.file || state.file.name !== file.name;
          
          // Only clear state if we're loading a new PDF
          if (isNewPdf) {
            console.log('Loading new PDF - clearing all related state');
            
            // Generate a unique PDF ID if not provided
            if (!pdfId) {
              pdfId = `pdf-${Date.now()}`;
            }
            
            // IMPORTANT: Clear structures BEFORE setting the new PDF
            // Use our new clearStructuresForNewPdf action instead of clearSegments
            dispatch('structures/clearStructuresForNewPdf', null, { root: true });
            
            // Then set the new PDF ID in structures module
            dispatch('structures/setCurrentPdfId', pdfId, { root: true });
            
            // Also clear other modules' data
            dispatch('annotations/clearAnnotations', null, { root: true });
            dispatch('text/clearExtractedText', null, { root: true });
          }
          
          console.log('Setting PDF file in store:', file.name);
          console.log('Setting PDF URL in store:', url);
          console.log('Using PDF ID:', pdfId);
          
          // Update state
          commit('SET_PDF_FILE', file);
          commit('SET_PDF_URL', url);
          commit('SET_CURRENT_PDF_ID', pdfId);
          
          // Add to uploaded files history
          const timestamp = new Date();
          const fileInfo = {
            name: file.name,
            size: file.size,
            url: url,
            pdfId: pdfId,
            timestamp: timestamp,
            timestampString: timestamp.toLocaleString()
          };
          commit('ADD_UPLOADED_FILE', fileInfo);
          
          // Clear any previous errors
          commit('CLEAR_ERROR');
          
          // Show success notification
          dispatch('showNotification', {
            type: 'success',
            message: `PDF "${file.name}" loaded successfully`
          }, { root: true });
          
          resolve({ file, url, pdfId });
        } catch (error) {
          console.error('Error in setPdfFile:', error);
          commit('SET_ERROR', error.message || 'Error processing PDF file');
          
          dispatch('showNotification', {
            type: 'error',
            message: error.message || 'Error processing PDF file'
          }, { root: true });
          
          reject(error);
        }
      });
    },
    
    /**
     * Clear the current PDF file
     * @param {Object} context - Vuex action context
     */
    clearPdfFile({ commit, dispatch, state }) {
      // Clean up object URL if it exists
      if (state.url) {
        URL.revokeObjectURL(state.url)
      }
      
      // Clear data from all modules using our comprehensive clear method
      dispatch('structures/clearStructuresForNewPdf', null, { root: true });
      dispatch('annotations/clearAnnotations', null, { root: true });
      dispatch('text/clearExtractedText', null, { root: true });
      
      // Reset state
      commit('SET_PDF_FILE', null)
      commit('SET_PDF_URL', null)
      commit('SET_PDF_INFO', null)
      commit('SET_CURRENT_PDF_ID', null)
      commit('CLEAR_ERROR')
    }
  },
  
  getters: {
    hasPdf: state => !!state.file,
    pdfName: state => state.file ? state.file.name : null,
    currentPdfId: state => state.currentPdfId,
    pdfSize: state => {
      if (!state.file) return null
      
      const bytes = state.file.size
      if (bytes < 1024) return bytes + ' bytes'
      else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
      else return (bytes / 1048576).toFixed(1) + ' MB'
    }
  }
}