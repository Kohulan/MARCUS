import api from './api'

/**
 * Service for interacting with the DECIMER segmentation endpoints
 */
const decimerService = {
  /**
   * Extract chemical structure segments from a PDF file
   * @param {File} pdfFile - The PDF file to process
   * @param {Object} options - Optional parameters
   * @param {boolean} options.collectAll - Whether to collect all segments in a common directory (default: true)
   * @returns {Promise} - Promise with the extracted segments data
   */
  extractSegments: async (pdfFile, options = {}) => {
    const formData = new FormData()
    formData.append('pdf_file', pdfFile)
    
    // Add optional parameters
    const collectAll = options.collectAll !== undefined ? options.collectAll : true
    formData.append('collect_all', collectAll)
    
    // Use multipart/form-data for file uploads
    const config = {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }
    
    try {
      console.log('Extracting segments from PDF:', pdfFile.name)
      const response = await api.post('/decimer/extract_segments', formData, config)
      console.log('Extraction response:', response.data)
      return response.data
    } catch (error) {
      console.error('Error extracting segments from PDF:', error)
      throw error
    }
  },
  
  /**
   * Extract DOI from a PDF file
   * @param {File} pdfFile - The PDF file to process
   * @returns {Promise} - Promise with the extracted DOI data
   */
  extractDoi: async (pdfFile) => {
    const formData = new FormData()
    formData.append('pdf_file', pdfFile)
    
    // Use multipart/form-data for file uploads
    const config = {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }
    
    try {
      const response = await api.post('/decimer/extract_doi', formData, config)
      return response.data
    } catch (error) {
      console.error('Error extracting DOI from PDF:', error)
      throw error
    }
  },
  
  /**
   * List available segment directories
   * @returns {Promise} - Promise with the list of segment directories
   */
  listSegments: async () => {
    try {
      const response = await api.get('/decimer/list_segments')
      console.log('List segments response:', response.data)
      return response.data
    } catch (error) {
      console.error('Error listing segments:', error)
      throw error
    }
  },

  // In decimerService.js
/**
 * List segment files from a specific directory
 * @param {string} directory - The directory name
 * @returns {Promise<Array>} - Promise with array of segment objects
 */
listSegmentFiles: async (directory) => {
  try {
    // Request the specific files from the directory
    const response = await api.get(`/decimer/list_directory/${directory}/all_segments`);
    
    if (!response.data.files || !Array.isArray(response.data.files)) {
      throw new Error("Invalid response format: files array missing");
    }
    
    console.log(`Got ${response.data.files.length} files from server:`, response.data.files);
    
    // Map the files to segment objects with proper URLs
    const segments = response.data.files.map((filename) => {
      // Extract page and index from filenames like "page_2_0_segmented.png"
      const parts = filename.split('_');
      
      // Default values if parsing fails
      let pageNum = 0;
      let segmentIndex = 0;
      
      // Try to extract page number and segment index
      if (parts.length > 1 && parts[0] === 'page') {
        pageNum = parseInt(parts[1], 10) || 0;
        segmentIndex = parts.length > 2 ? parseInt(parts[2], 10) || 0 : 0;
      }
      
      // Create a unique ID that includes the page number
      const uniqueId = `page-${pageNum}-segment-${segmentIndex}`;
      
      // FIXED: Don't construct the URL manually - this is missing the /latest/ prefix in development
      // Instead, just store the path and let getApiImageUrl handle the proper URL construction
      return {
        id: uniqueId, // Use unique ID that includes page number
        // Don't set imageUrl here - let the imageUrl helper handle this consistently
        path: `${directory}/all_segments/${filename}`,
        filename: filename,
        pageNumber: pageNum + 1, // 1-based page number for display
        segmentNumber: segmentIndex,
        pageIndex: pageNum // Store original 0-based page index
      };
    });
    
    console.log(`Mapped ${segments.length} segment files to segment objects with unique IDs`);
    return segments;
  } catch (error) {
    console.error('Error listing segment files:', error);
    throw error;
  }
},
  
  /**
   * Get a specific segment image
   * @param {string} directory - The segment directory name
   * @param {string} imageName - The image filename
   * @returns {Promise} - Promise with the image data
   */
  getSegmentImage: async (directory, imageName) => {
    try {
      // Use 'responseType: blob' to get the image data as a Blob
      const config = {
        responseType: 'blob'
      }
      
      // Log the URL we're trying to access for debugging
      const url = `/decimer/get_segment_image/${directory}/${imageName}`
      console.log('Requesting segment image from:', url)
      
      const response = await api.get(url, config)
      return {
        blob: response.data,
        url: URL.createObjectURL(response.data)
      }
    } catch (error) {
      console.error('Error getting segment image:', error)
      throw error
    }
  },
  
  /**
   * Create mock segment data for testing
   * @param {number} count - Number of segments to create
   * @param {string} baseDir - Base directory name
   * @returns {Array} - Array of segment objects
   */
  createMockSegments: (count, baseDir) => {
    const apiBaseUrl = process.env.VUE_APP_API_URL || 'http://localhost:9000/latest'
    const segments = []
    
    console.log(`Creating ${count} mock segments for directory: ${baseDir}`)
    
    // Standard test patterns for segment images
    const patterns = [
      'page_0_{index}_segmented.png', 
      '{index}_segmented.png',
      'segment_{index}_segmented.png'
    ]
    
    // Create segments with each pattern to maximize chance of success
    for (let i = 1; i <= count; i++) {
      const segmentId = `segment-${i}`
      
      // Find filenames for different image formats for this index
      for (const pattern of patterns) {
        const imageName = pattern.replace('{index}', i)
        segments.push({
          id: segmentId,
          imageUrl: `${apiBaseUrl}/decimer/get_segment_image/${baseDir}/${imageName}`,
          path: `${baseDir}/${imageName}`,
          pattern: pattern,
          pageNumber: Math.floor((i-1) / 2) + 1,
          segmentNumber: i
        })
      }
    }
    
    return segments
  }
}

export default decimerService