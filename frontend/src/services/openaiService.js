import api from './api'

/**
 * Service for interacting with the OpenAI annotation endpoints
 */
const openaiService = {
  /**
   * Extract JSON data from text using OpenAI
   * @param {string} text - The text to process
   * @returns {Promise} - Promise with the extracted JSON data
   */
  extractJson: async (text) => {
    try {
      const response = await api.post('/openai/extract_json', { text })
      return response.data
    } catch (error) {
      console.error('Error extracting JSON from text:', error)
      throw error
    }
  },
  
  /**
   * Extract entity positions from text using OpenAI
   * @param {string} text - The text to process
   * @returns {Promise} - Promise with the extracted entity positions
   */
  extractPositions: async (text) => {
    try {
      const response = await api.post('/openai/extract_positions', { text })
      return response.data
    } catch (error) {
      console.error('Error extracting positions from text:', error)
      throw error
    }
  },
  
  /**
   * Extract both JSON and positions from text using OpenAI
   * @param {string} text - The text to process
   * @returns {Promise} - Promise with both extracted JSON and positions
   */
  extractAll: async (text) => {
    try {
      const response = await api.post('/openai/extract_all', { text })
      return response.data
    } catch (error) {
      console.error('Error extracting data from text:', error)
      throw error
    }
  },
  
  /**
   * List all saved extractions
   * @returns {Promise} - Promise with the list of saved extraction results
   */
  listExtractions: async () => {
    try {
      const response = await api.get('/openai/list_extractions')
      return response.data
    } catch (error) {
      console.error('Error listing extractions:', error)
      throw error
    }
  },
  
  /**
   * Get a specific extraction result
   * @param {string} filename - The filename of the extraction result
   * @returns {Promise} - Promise with the complete extraction result
   */
  getExtraction: async (filename) => {
    try {
      const response = await api.get(`/openai/get_extraction/${filename}`)
      return response.data
    } catch (error) {
      console.error('Error getting extraction result:', error)
      throw error
    }
  }
}

export default openaiService