import api from './api'

/**
 * Service for interacting with the Docling PDF text extraction endpoints
 */
const doclingService = {
  /**
   * Extract text from a PDF file
   * @param {File} pdfFile - The PDF file to process
   * @param {Object} options - Optional parameters
   * @param {number} options.pages - Number of pages to process (default: 3)
   * @returns {Promise} - Promise with the extracted text data
   */
  extractText: async (pdfFile, options = {}) => {
    const formData = new FormData()
    formData.append('pdf_file', pdfFile)
    
    // Add optional parameters
    if (options.pages) {
      formData.append('pages', options.pages)
    }
    
    // Use multipart/form-data for file uploads
    const config = {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }
    
    try {
      const response = await api.post('/docling_conversion/extract_text', formData, config)
      return response.data
    } catch (error) {
      console.error('Error extracting text from PDF:', error)
      throw error
    }
  },
  
  /**
   * Extract structured JSON data from a PDF file
   * @param {File} pdfFile - The PDF file to process
   * @param {Object} options - Optional parameters
   * @param {number} options.pages - Number of pages to process (default: 3)
   * @returns {Promise} - Promise with the extracted JSON data
   */
  extractJson: async (pdfFile, options = {}) => {
    const formData = new FormData()
    formData.append('pdf_file', pdfFile)
    
    // Add optional parameters
    if (options.pages) {
      formData.append('pages', options.pages)
    }
    
    // Use multipart/form-data for file uploads
    const config = {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }
    
    try {
      const response = await api.post('/v1/docling_conversion/extract_json', formData, config)
      return response.data
    } catch (error) {
      console.error('Error extracting JSON from PDF:', error)
      throw error
    }
  },
  
  /**
   * List available PDF files on the server
   * @returns {Promise} - Promise with the list of PDF files
   */
  listPdfs: async () => {
    try {
      const response = await api.get('/v1/docling_conversion/list_pdfs')
      return response.data
    } catch (error) {
      console.error('Error listing PDFs:', error)
      throw error
    }
  }
}

export default doclingService