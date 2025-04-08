import api from './api'

/**
 * Service for interacting with the molecular depiction endpoints
 */
const depictionService = {
  /**
   * Generate a molecular depiction using JSON body
   * @param {Object} options - Depiction options
   * @param {string} options.smiles - SMILES string (optional if molfile is provided)
   * @param {string} options.molfile - Molfile string (optional if SMILES is provided)
   * @param {boolean} options.useMolfileDirectly - Whether to use molfile directly (for MolNexTR output)
   * @param {number} options.width - Width of the depiction in pixels
   * @param {number} options.height - Height of the depiction in pixels
   * @param {number} options.rotate - Rotation angle in degrees
   * @param {boolean} options.kekulize - Whether to kekulize the molecule
   * @param {boolean} options.cip - Whether to display CIP stereochemistry annotations
   * @param {boolean} options.unicolor - Whether to use a single color for all atoms
   * @param {string} options.highlight - SMARTS pattern to highlight
   * @param {boolean} options.transparent - Whether to use transparent background
   * @param {string} options.format - Output format ('svg', 'png', or 'base64')
   * @returns {Promise} - Promise with the depiction data
   */
  generateDepiction: async (options = {}) => {
    try {
      // Set default values for missing options
      const defaults = {
        engine: 'cdk',  // Always use CDK as the default engine
        width: 512,
        height: 512,
        rotate: 0,
        kekulize: true,
        cip: true,
        unicolor: false,
        highlight: '',
        transparent: false,
        format: 'svg',
        useMolfileDirectly: false
      }
      
      const requestData = { ...defaults, ...options }
      
      // Ensure we're always using CDK regardless of what was passed
      requestData.engine = 'cdk';
      
      // Make sure we're prioritizing molfile properly when useMolfileDirectly is true
      if (requestData.useMolfileDirectly && requestData.molfile) {
        // When using molfile directly, we need to signal this to the backend
        requestData.use_molfile_directly = true;
        console.log('Using molfile directly for depiction');
      } else if (!requestData.smiles && !requestData.molfile) {
        throw new Error('Either SMILES or molfile must be provided');
      }
      
      // Set response type based on format
      const config = {
        responseType: requestData.format === 'png' ? 'arraybuffer' : 'text'
      }
      
      const response = await api.post('/depiction/generate', requestData, config)
      
      // Process response based on format
      if (requestData.format === 'svg') {
        return response.data
      } else if (requestData.format === 'png') {
        return response.data
      } else { // base64
        return response.data.data
      }
    } catch (error) {
      console.error('Error generating depiction:', error)
      throw error
    }
  },
  
  /**
   * Generate a depiction from OCSR results
   * @param {Object} options - Depiction options
   * @param {string} options.smiles - SMILES string from OCSR
   * @param {string} options.molfile - Molfile string from OCSR (if available)
   * @param {boolean} options.useMolfile - Whether to use molfile when available
   * @returns {Promise} - Promise with the depiction data
   */
  depictFromOcsr: async (options = {}) => {
    try {
      const formData = new FormData()
      
      // Add SMILES if provided
      if (options.smiles) {
        formData.append('smiles', options.smiles)
      }
      
      // Add molfile if provided and useMolfile is true
      if (options.molfile && (options.useMolfile !== false)) {
        formData.append('molfile', options.molfile)
        formData.append('use_molfile_directly', 'true')
      }
      
      // Always use CDK engine
      formData.append('engine', 'cdk')
      
      // Add additional parameters
      formData.append('width', options.width || 512)
      formData.append('height', options.height || 512)
      formData.append('use_molfile', options.useMolfile !== false)
      formData.append('cip', options.cip !== false)
      formData.append('format', options.format || 'svg')
      
      // Set response type based on format
      const responseType = options.format === 'png' ? 'blob' : 
                          (options.format === 'base64' ? 'json' : 'text')
      const config = {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        responseType
      }
      
      const response = await api.post('/depiction/from_ocsr', formData, config)
      
      // Process response based on format
      if (options.format === 'svg' || !options.format) {
        return response.data
      } else if (options.format === 'png') {
        return URL.createObjectURL(response.data)
      } else { // base64
        return response.data.data
      }
    } catch (error) {
      console.error('Error depicting from OCSR:', error)
      throw error
    }
  },
  
  /**
   * Get the URL for direct visualization in an <img> tag
   * @param {Object} options - Depiction options
   * @returns {string} - URL for direct visualization
   */
  getVisualizationUrl: (options = {}) => {
    const baseUrl = api.defaults.baseURL || '';
    const endpoint = '/depiction/visualize';
    
    // Ensure we're using CDK
    const updatedOptions = { ...options, engine: 'cdk' };
    
    // If molfile is provided and useMolfileDirectly is true, adjust params accordingly
    if (updatedOptions.molfile && updatedOptions.useMolfileDirectly) {
      updatedOptions.use_molfile_directly = true;
    }
    
    // Convert options to query parameters
    const params = new URLSearchParams();
    Object.entries(updatedOptions).forEach(([key, value]) => {
      if (value !== undefined) {
        params.append(key, value);
      }
    });
    
    return `${baseUrl}${endpoint}?${params.toString()}`;
  }
}

export default depictionService;