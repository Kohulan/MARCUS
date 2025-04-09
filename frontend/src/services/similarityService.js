import api from './api'

/**
 * Service for interacting with the similarity comparison endpoints
 */
const similarityService = {
  /**
   * Compare SMILES strings from different OCSR engines
   * @param {Array} smilesList - Array of SMILES strings from different engines
   * @param {Array} engineNames - Array of engine names corresponding to the SMILES strings
   * @returns {Promise} - Promise with the similarity analysis results
   */
  compareSmiles: async (smilesList, engineNames) => {
    try {
      // Validate input
      if (!Array.isArray(smilesList) || !Array.isArray(engineNames)) {
        throw new Error('SMILES list and engine names must be arrays')
      }
      
      if (smilesList.length !== engineNames.length) {
        throw new Error('Number of SMILES strings must match number of engine names')
      }
      
      // Filter out empty SMILES (but keep track of indices)
      const filteredData = smilesList.map((smiles, index) => ({
        smiles,
        engine: engineNames[index],
        valid: !!smiles && smiles.trim() !== ''
      })).filter(item => item.valid);
      
      // If we have fewer than 2 valid SMILES, we can't do a comparison
      if (filteredData.length < 2) {
        return {
          error: 'Insufficient valid SMILES for comparison',
          matrix: [],
          engine_names: [],
          identical: false,
          agreement_summary: {
            identical: false,
            agreement_percentage: 0,
            total_comparisons: 0,
            total_agreements: 0,
            pair_agreements: {},
            invalid_smiles: smilesList.map((smiles, index) => ({
              engine: engineNames[index],
              smiles: smiles || '',
              valid: !!smiles && smiles.trim() !== ''
            })).filter(item => !item.valid)
          }
        }
      }
      
      // Prepare request payload
      const payload = {
        smiles_list: filteredData.map(item => item.smiles),
        engine_names: filteredData.map(item => item.engine)
      }
      
      // Call the API
      const response = await api.post('/similarity/compare_smiles', payload)
      return response.data
    } catch (error) {
      console.error('Error comparing SMILES:', error)
      throw error
    }
  }
}

export default similarityService