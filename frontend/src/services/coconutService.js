// filepath: /Volumes/Data_Drive/Project/2025/Project_marcus/Project_MARCUS/frontend/src/services/coconutService.js
import axios from 'axios';

// Create a dedicated axios instance for COCONUT API
const coconutApi = axios.create({
  baseURL: 'https://coconut.naturalproducts.net/api',
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  },
  timeout: 30000 // 30 seconds
});

// Local storage keys
const TOKEN_KEY = 'coconut_auth_token';
const USER_KEY = 'coconut_user';

/**
 * COCONUT API Service
 */
export default {
  /**
   * Authenticate with COCONUT API
   * @param {Object} credentials - User credentials
   * @param {string} credentials.email - User email
   * @param {string} credentials.password - User password
   * @returns {Promise<Object>} - Authentication result with token and user info
   */
  async login(credentials) {
    try {
      const response = await coconutApi.post('/auth/login', credentials);
      
      if (response.data && response.data.access_token) {
        // Store token and user info in local storage
        localStorage.setItem(TOKEN_KEY, response.data.access_token);
        
        if (response.data.user) {
          localStorage.setItem(USER_KEY, JSON.stringify(response.data.user));
        }
        
        return {
          success: true,
          token: response.data.access_token,
          user: response.data.user
        };
      }
      
      return {
        success: false,
        error: 'Authentication failed: Invalid response format'
      };
    } catch (error) {
      console.error('COCONUT authentication error:', error);
      
      return {
        success: false,
        error: error.response?.data?.message || 'Authentication failed'
      };
    }
  },

  /**
   * Check if user is authenticated
   * @returns {boolean} - True if authenticated
   */
  isAuthenticated() {
    return !!localStorage.getItem(TOKEN_KEY);
  },

  /**
   * Get authentication token
   * @returns {string|null} - Authentication token or null
   */
  getToken() {
    return localStorage.getItem(TOKEN_KEY);
  },

  /**
   * Get current user information
   * @returns {Object|null} - User information or null
   */
  getCurrentUser() {
    const userJson = localStorage.getItem(USER_KEY);
    return userJson ? JSON.parse(userJson) : null;
  },

  /**
   * Logout user and remove stored authentication
   */
  logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },

  /**
   * Format the COCONUT submission data
   * @param {Object} submissionData - The data from the submission form
   * @returns {Object} - Formatted data for COCONUT API
   */
  formatSubmissionData(submissionData) {
    // Extract location and ecosystem data from each organism
    const formattedOrganisms = submissionData.organisms.map(org => {
      // Skip empty organisms
      if (!org.name) return null;
      
      // Process the parts - convert comma-separated string to array
      const parts = org.parts ? org.parts.split(',').map(part => part.trim()).filter(Boolean) : [];
      
      // Format the location object
      const location = {
        name: org.location || '',
        ecosystems: org.ecosystems ? org.ecosystems.split(',').map(eco => eco.trim()).filter(Boolean) : []
      };
      
      return {
        name: org.name,
        parts: parts,
        locations: location.name ? [location] : []
      };
    }).filter(Boolean); // Remove null entries
    
    // Format the main submission data
    const formattedData = {
      mutate: [
        {
          operation: "create",
          attributes: {
            title: submissionData.title,
            evidence: submissionData.evidence,
            comment: submissionData.comment,
            suggested_changes: {
              new_molecule_data: {
                canonical_smiles: submissionData.structureData.smiles,
                reference_id: submissionData.referenceId || '',
                name: submissionData.name,
                link: submissionData.link || '',
                structural_comments: submissionData.structuralComments,
                references: formattedOrganisms.length > 0 ? [
                  {
                    doi: submissionData.referenceId || '',
                    organisms: formattedOrganisms
                  }
                ] : []
              }
            }
          },
          relations: []
        }
      ]
    };
    
    return formattedData;
  },

  /**
   * Submit data to COCONUT
   * @param {Object} formData - The form data to submit
   * @returns {Promise<Object>} - Submission result
   */
  async submitToCoconut(formData) {
    try {
      // Ensure we have a token
      const token = this.getToken();
      if (!token) {
        return {
          success: false,
          error: 'Authentication required. Please log in.'
        };
      }
      
      // Format the data for submission
      const formattedData = this.formatSubmissionData(formData);
      
      // Make the API call with authentication
      const response = await coconutApi.post('/reports/mutate', formattedData, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      return {
        success: true,
        data: response.data
      };
    } catch (error) {
      console.error('COCONUT submission error:', error);
      
      return {
        success: false,
        error: error.response?.data?.message || 'Submission failed'
      };
    }
  }
};