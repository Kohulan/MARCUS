import api from './api'
import { api as sessionAwareApi } from './apiClient'
import sessionService from './sessionService'

/**
 * Service for interacting with the OCSR (Optical Chemical Structure Recognition) endpoints
 * Enhanced with session management and concurrency control
 */
const ocsrService = {
  /**
   * Check if user has an active session before making requests
   * @returns {boolean} - True if session is active
   */
  _validateSession() {
    if (!sessionService.isActive()) {
      throw new Error('No active session. Please wait for your turn or create a new session.');
    }
    return true;
  },

  /**
   * Generate SMILES from a chemical structure image
   * @param {File|null} imageFile - The chemical structure image file (optional)
   * @param {string|null} imagePath - Path to an existing image on the server (optional)
   * @param {Object} options - Processing options
   * @param {string} options.engine - OCSR engine to use ('decimer', 'molnextr', or 'molscribe')
   * @param {boolean} options.handDrawn - Whether to use the hand-drawn model (only for DECIMER)
   * @returns {Promise} - Promise with the generated SMILES data
   */
  generateSmiles: async (imageFile = null, imagePath = null, options = {}) => {
    // Validate session before making request
    ocsrService._validateSession();
    
    const formData = new FormData()
    
    if (imageFile) {
      formData.append('image_file', imageFile)
    } else if (imagePath) {
      // Send the full path as the backend needs it to locate the file
      formData.append('image_path', imagePath)
    } else {
      throw new Error('Either imageFile or imagePath must be provided')
    }
    
    // Add options
    formData.append('engine', options.engine || 'decimer')
    formData.append('hand_drawn', options.handDrawn || false)
    
    // Use session-aware API client for file uploads
    try {
      const response = await sessionAwareApi.uploadFile('/latest/ocsr/generate_smiles', imageFile || formData)
      
      // Log usage for session tracking
      console.log(`OCSR SMILES generation completed for session ${sessionService.getSessionId()}`);
      
      return response.data
    } catch (error) {
      console.error('Error generating SMILES:', error)
      
      // Handle session-specific errors
      if (error.response?.data?.error_code === 'SESSION_NOT_ACTIVE') {
        throw new Error('Your session is not active. Please wait in the queue.');
      }
      
      throw error
    }
  },
  
  /**
   * Generate a molfile from a chemical structure image
   * @param {File|null} imageFile - The chemical structure image file (optional)
   * @param {string|null} imagePath - Path to an existing image on the server (optional)
   * @param {Object} options - Processing options
   * @param {string} options.engine - OCSR engine to use ('molnextr' or 'molscribe')
   * @returns {Promise} - Promise with the generated molfile data
   */
  generateMolfile: async (imageFile = null, imagePath = null, options = {}) => {
    const formData = new FormData()
    
    if (imageFile) {
      formData.append('image_file', imageFile)
    } else if (imagePath) {
      // Send the full path as the backend needs it to locate the file
      formData.append('image_path', imagePath)
    } else {
      throw new Error('Either imageFile or imagePath must be provided')
    }
    
    // MolNexTR and MolScribe engines support molfile generation
    formData.append('engine', options.engine || 'molnextr')
    
    // Use multipart/form-data for file uploads
    const config = {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }
    
    try {
      const response = await api.post('/ocsr/generate_molfile', formData, config)
      return response.data
    } catch (error) {
      console.error('Error generating molfile:', error)
      throw error
    }
  },
  
  /**
   * Generate both SMILES and molfile (if available) from a chemical structure image
   * @param {File|null} imageFile - The chemical structure image file (optional)
   * @param {string|null} imagePath - Path to an existing image on the server (optional)
   * @param {Object} options - Processing options
   * @param {string} options.engine - OCSR engine to use ('decimer', 'molnextr', or 'molscribe')
   * @param {boolean} options.handDrawn - Whether to use the hand-drawn model (only for DECIMER)
   * @returns {Promise} - Promise with both SMILES and molfile data
   */
  generateBoth: async (imageFile = null, imagePath = null, options = {}) => {
    const formData = new FormData()
    
    if (imageFile) {
      formData.append('image_file', imageFile)
    } else if (imagePath) {
      // Clean and normalize the path before sending
      const cleanPath = ocsrService.normalizePath(imagePath)
      formData.append('image_path', cleanPath)
      console.log(`Using normalized path for generateBoth: ${cleanPath}`)
    } else {
      throw new Error('Either imageFile or imagePath must be provided')
    }
    
    // Add options
    formData.append('engine', options.engine || 'molnextr')
    formData.append('hand_drawn', options.handDrawn || false)
    
    // Use multipart/form-data for file uploads
    const config = {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      timeout: 60000 // Increase timeout for larger images
    }
    
    try {
      const response = await api.post('/ocsr/generate_both', formData, config)
      return response.data
    } catch (error) {
      console.error('Error generating structure data:', error)
      throw error
    }
  },
  
  /**
   * Generate OCSR results with depiction in a single call
   * @param {File|null} imageFile - The chemical structure image file (optional)
   * @param {string|null} imagePath - Path to an existing image on the server (optional)
   * @param {Object} options - Processing options
   * @param {string} options.engine - OCSR engine to use ('decimer', 'molnextr', or 'molscribe')
   * @param {boolean} options.handDrawn - Whether to use the hand-drawn model (only for DECIMER)
   * @param {string} options.depictEngine - Depiction engine to use ('rdkit' or 'cdk')
   * @param {string} options.depictFormat - Depiction format ('svg', 'png', or 'base64')
   * @returns {Promise} - Promise with OCSR results and depiction
   */
  generateWithDepiction: async (imageFile = null, imagePath = null, options = {}) => {
    const formData = new FormData()
    
    if (imageFile) {
      formData.append('image_file', imageFile)
    } else if (imagePath) {
      // Clean and normalize the path before sending
      const cleanPath = ocsrService.normalizePath(imagePath)
      formData.append('image_path', cleanPath)
      console.log(`Using normalized path for generateWithDepiction: ${cleanPath}`)
    } else {
      throw new Error('Either imageFile or imagePath must be provided')
    }
    
    // Add OCSR options
    formData.append('engine', options.engine || 'molnextr')
    
    // When includeMolfile is true, use 'molfile' or 'both' as output_type depending on engine
    const useCoordinates = options.includeMolfile === true;
    
    // For MolNexTR and MolScribe with coordinates, set output_type to molfile or both
    if (useCoordinates && (options.engine === 'molnextr' || options.engine === 'molscribe')) {
      formData.append('output_type', 'both');
    } else {
      // For DECIMER or when not using coordinates, just get SMILES
      formData.append('output_type', 'smiles');
    }
    
    formData.append('hand_drawn', options.handDrawn || false)
    
    // Add depiction options
    formData.append('depict_engine', options.depictEngine || 'rdkit')
    formData.append('depict_width', options.depictWidth || 512)
    formData.append('depict_height', options.depictHeight || 512)
    formData.append('depict_format', options.depictFormat || 'svg')
    
    // Use multipart/form-data for file uploads
    const config = {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      timeout: 60000 // Increase timeout for larger images
    }
    
    try {
      const response = await api.post('/ocsr/generate_with_depiction', formData, config)
      return response.data
    } catch (error) {
      console.error('Error generating with depiction:', error)
      throw error
    }
  },
  
  /**
   * Normalize a path to be consistent with backend expectations
   * Handles various path formats and ensures a clean, valid path is returned
   * @param {string} path - Original path to normalize 
   * @returns {string} - Normalized path
   */
  normalizePath: (path) => {
    if (!path) return '';
    
    console.log(`Normalizing path: ${path}`);
    
    // If path already contains /api/, it's likely a full URL - return just the path part
    if (path.includes('/api/')) {
      const pathParts = path.split('/api/');
      if (pathParts.length > 1) {
        // Get everything after /api/
        path = pathParts[1];
        // Remove any additional URL parts (like query params)
        if (path.includes('?')) {
          path = path.split('?')[0];
        }
      }
    }
    
    // If path has URL encoded characters, decode them
    if (path.includes('%')) {
      try {
        path = decodeURIComponent(path);
      } catch (e) {
        console.warn('Failed to decode URL-encoded path', e);
      }
    }
    
    // Check if the path contains "all_segments" - if not, try to reconstruct it
    if (!path.includes('all_segments') && path.includes('/')) {
      // Split by directory separator and rebuild path
      const pathParts = path.split('/').filter(p => p.trim() !== '');
      
      // If we have at least a directory and a filename
      if (pathParts.length >= 2) {
        const directory = pathParts[0];
        const filename = pathParts[pathParts.length - 1];
        path = `${directory}/all_segments/${filename}`;
      }
    }
    
    // Clean up any double slashes
    path = path.replace(/\/+/g, '/');
    
    // Make sure path doesn't start with a slash (unless it's an absolute path)
    if (path.startsWith('/') && !path.startsWith('/home/') && !path.startsWith('/var/')) {
      path = path.substring(1);
    }
    
    console.log(`Normalized path: ${path}`);
    return path;
  },
  
  /**
   * Get a specific chemical structure image
   * @param {string} imageName - The image filename
   * @returns {Promise} - Promise with the image data
   */
  getImage: async (imageName) => {
    try {
      // Use 'responseType: blob' to get the image data as a Blob
      const config = {
        responseType: 'blob'
      }
      
      const response = await api.get(`/ocsr/get_image/${imageName}`, config)
      return {
        blob: response.data,
        url: URL.createObjectURL(response.data)
      }
    } catch (error) {
      console.error('Error getting image:', error)
      throw error
    }
  },
  
  /**
   * Extract filename from path
   * @param {string} path - Path containing filename
   * @returns {string} - Extracted filename
   */
  extractFilename: (path) => {
    if (!path) return '';
    
    // Get the last part of the path
    const parts = path.split('/');
    return parts[parts.length - 1];
  },
  
/**
 * Process multiple segments with OCSR
 * @param {Array} segments - Array of segment objects with imageUrl or path
 * @param {Object} options - Processing options
 * @param {string} options.engine - OCSR engine to use ('decimer', 'molnextr', or 'molscribe')
 * @param {boolean} options.handDrawn - Whether to use the hand-drawn model (only for DECIMER)
 * @param {boolean} options.includeMolfile - Whether to include molfile data (for molnextr and molscribe)
 * @param {string} options.pdfId - Unique ID for the current PDF to prevent mixing structures
 * @returns {Promise} - Promise with array of processed structures
 */
processSegments: async (segments, options = {}) => {
  const results = [];
  console.log(`Processing ${segments.length} segments with ${options.engine} engine`);
  
  // Get PDF ID from options
  const pdfId = options.pdfId || `pdf-${Date.now()}`;
  console.log(`Using PDF ID: ${pdfId} for structure processing`);
  
  // Determine if we should get and use coordinates (molfile)
  const useCoordinates = options.includeMolfile === true && 
                         (options.engine === 'molnextr' || options.engine === 'molscribe');
  
  console.log(`Using coordinates: ${useCoordinates}`);
  
  // Unique ID for this batch of processing (for debugging)
  const batchId = `batch-${Date.now()}`;
  
  // Process segments sequentially to ensure correct order
  for (let i = 0; i < segments.length; i++) {
    const segment = segments[i];
    
    try {
      // Skip empty segments
      if (!segment || (!segment.path && !segment.imageUrl)) {
        console.warn(`Skipping empty or invalid segment at index ${i}`);
        continue;
      }
      
      // Extract page and segment information from the segment
      let pageNum = 0;
      let segmentNum = 0;
      
      // Try to parse from ID 
      if (segment.id) {
        const pageMatch = segment.id.match(/page-(\d+)-segment-(\d+)/);
        if (pageMatch && pageMatch.length > 2) {
          pageNum = parseInt(pageMatch[1], 10);
          segmentNum = parseInt(pageMatch[2], 10);
        }
      }
      
      // Override with explicit properties if available
      if (segment.pageIndex !== undefined) {
        pageNum = segment.pageIndex;
      }
      
      if (segment.segmentNumber !== undefined) {
        segmentNum = segment.segmentNumber;
      }
      
      // Extract filename for reliable identification
      const filename = segment.filename || ocsrService.extractFilename(segment.path || segment.imageUrl);
      
      console.log(`[${batchId}] Processing segment ${i+1}/${segments.length}: ${segment.id} - ${filename}`);
      
      // Use the segment path 
      let imagePath = segment.path || '';
      
      // Normalize the path
      imagePath = ocsrService.normalizePath(imagePath);
      
      console.log(`[${batchId}] Using image path: ${imagePath}`);
      
      try {
        // Use the combined API endpoint that includes depiction
        console.log(`[${batchId}] Calling generateWithDepiction for ${segment.id} - ${filename}`);
        const response = await ocsrService.generateWithDepiction(null, imagePath, {
          engine: options.engine,
          handDrawn: options.handDrawn || false,
          includeMolfile: options.includeMolfile || false,
          depictEngine: 'rdkit',  // Use RDKit as default
          depictFormat: 'svg'
        });
        
        console.log(`[${batchId}] Got response for ${segment.id} - ${filename}:`, 
          response.smiles ? `SMILES found (${response.smiles.length} chars)` : 'No SMILES');
        
        // Create structure object with the correct segmentId AND PDF ID
        const structure = {
          segmentId: segment.id, 
          originalSegmentId: segment.id,
          segmentUrl: segment.imageUrl || segment.path,
          filename: filename,
          smiles: response.smiles || '',
          molfile: response.molfile || null,
          engine: options.engine,
          name: filename,
          pdfId: pdfId, // IMPORTANT: Store the PDF ID with each structure
          pageIndex: pageNum,
          segmentIndex: segmentNum,
          uniqueKey: `pdf-${pdfId}-page-${pageNum}-segment-${segmentNum}`,
          depiction: response.depiction || null,
          useCoordinates: useCoordinates,
          processingTime: new Date().toISOString()
        };
        
        results.push(structure);
        
      } catch (apiError) {
        console.error(`[${batchId}] API error processing segment ${segment.id} - ${filename}:`, apiError);
        
        // Try fallback approach
        console.log(`[${batchId}] Trying fallback with generateBoth for ${segment.id} - ${filename}`);
        try {
          const fallbackResponse = await ocsrService.generateBoth(null, imagePath, options);
          
          // Add to results with full identifiers and PDF ID
          results.push({
            segmentId: segment.id,
            originalSegmentId: segment.id,
            segmentUrl: segment.imageUrl || segment.path,
            filename: filename,
            smiles: fallbackResponse.smiles || '',
            molfile: fallbackResponse.molfile || null,
            engine: options.engine,
            name: filename,
            pdfId: pdfId, // Store the PDF ID
            pageIndex: pageNum,
            segmentIndex: segmentNum,
            uniqueKey: `pdf-${pdfId}-page-${pageNum}-segment-${segmentNum}`,
            useCoordinates: useCoordinates,
            fromFallback: true,
            processingTime: new Date().toISOString()
          });
        } catch (fallbackError) {
          // If even the fallback approach fails, add error result
          console.error(`[${batchId}] Fallback also failed for segment ${segment.id} - ${filename}:`, fallbackError);
          results.push({
            segmentId: segment.id,
            segmentUrl: segment.imageUrl || segment.path,
            filename: filename,
            name: filename,
            pdfId: pdfId, // Store the PDF ID
            pageIndex: pageNum,
            segmentIndex: segmentNum,
            uniqueKey: `pdf-${pdfId}-page-${pageNum}-segment-${segmentNum}`,
            error: apiError.message || 'API processing failed',
            processingTime: new Date().toISOString()
          });
        }
      }
    } catch (error) {
      console.error(`[${batchId}] Error processing segment ${segment ? segment.id : 'unknown'}:`, error);
      
      // Include failed segment in results with error information
      if (segment) {
        const filename = segment.filename || ocsrService.extractFilename(segment.path || segment.imageUrl);
        const pageNum = segment.pageIndex || 0;
        const segmentNum = segment.segmentNumber || 0;
        
        results.push({
          segmentId: segment.id,
          segmentUrl: segment.imageUrl || segment.path,
          filename: filename,
          name: filename,
          pdfId: pdfId, // Store the PDF ID
          pageIndex: pageNum,
          segmentIndex: segmentNum,
          uniqueKey: `pdf-${pdfId}-page-${pageNum}-segment-${segmentNum}`,
          error: error.message || 'Processing failed',
          processingTime: new Date().toISOString()
        });
      }
    }
  }
  
  console.log(`[${batchId}] Completed processing ${segments.length} segments. Got ${results.length} results.`);
  
  // Debug: log all processed filenames to ensure they match segments
  console.log(`[${batchId}] Processed segment filenames:`, results.map(r => r.name).join(', '));
  
  return results;
}
};

export default ocsrService;