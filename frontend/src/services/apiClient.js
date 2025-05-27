/**
 * Enhanced API client with session management integration
 * Automatically includes session ID in requests and handles session-related errors
 */

import axios from 'axios';
import sessionService from './sessionService';

// Create axios instance with default configuration
const apiClient = axios.create({
  timeout: 30000, // 30 seconds
  headers: {
    'Content-Type': 'application/json'
  }
});

// Request interceptor to add session ID
apiClient.interceptors.request.use(
  (config) => {
    // Add session ID to headers if available
    const sessionId = sessionService.getSessionId();
    if (sessionId) {
      config.headers['X-Session-ID'] = sessionId;
    }
    
    // Log request for debugging
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`, {
      sessionId,
      headers: config.headers
    });
    
    return config;
  },
  (error) => {
    console.error('Request interceptor error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor to handle session-related errors
apiClient.interceptors.response.use(
  (response) => {
    // Log successful response
    console.log(`API Response: ${response.status} ${response.config.url}`);
    return response;
  },
  (error) => {
    console.error('API Error:', error.response?.status, error.response?.data);
    
    // Handle session-related errors
    if (error.response) {
      const { status, data } = error.response;
      
      switch (data?.error_code) {
        case 'NO_SESSION':
          console.warn('No session ID provided, redirecting to session creation');
          handleSessionError('no_session', data);
          break;
          
        case 'SESSION_NOT_FOUND':
          console.warn('Session not found or expired');
          handleSessionError('session_expired', data);
          break;
          
        case 'SESSION_NOT_ACTIVE':
          console.warn('Session not active, user needs to wait in queue');
          handleSessionError('session_waiting', data);
          break;
          
        default:
          // Handle other HTTP errors
          if (status === 429) {
            handleSessionError('rate_limited', data);
          }
      }
    }
    
    return Promise.reject(error);
  }
);

/**
 * Handle session-related errors
 * @param {string} errorType - Type of session error
 * @param {Object} errorData - Error data from API response
 */
function handleSessionError(errorType, errorData) {
  // Emit custom events that components can listen to
  const event = new CustomEvent('session-error', {
    detail: {
      type: errorType,
      data: errorData
    }
  });
  window.dispatchEvent(event);
  
  // You could also update a global store or redirect user
  switch (errorType) {
    case 'no_session':
    case 'session_expired':
      // Could redirect to session creation
      console.log('Session needed - should create new session');
      break;
      
    case 'session_waiting':
      console.log('User needs to wait in queue', {
        position: errorData.queue_position,
        waitTime: errorData.estimated_wait_time
      });
      break;
      
    case 'rate_limited':
      console.log('Rate limited - user should slow down requests');
      break;
  }
}

/**
 * Enhanced API methods with session management
 */
export const api = {
  // Generic HTTP methods
  get: (url, config = {}) => apiClient.get(url, config),
  post: (url, data, config = {}) => apiClient.post(url, data, config),
  put: (url, data, config = {}) => apiClient.put(url, data, config),
  delete: (url, config = {}) => apiClient.delete(url, config),
  patch: (url, data, config = {}) => apiClient.patch(url, data, config),
  
  // File upload with session
  uploadFile: async (url, file, onProgress = null) => {
    const formData = new FormData();
    formData.append('file', file);
    
    const config = {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      onUploadProgress: onProgress ? (progressEvent) => {
        const percentCompleted = Math.round(
          (progressEvent.loaded * 100) / progressEvent.total
        );
        onProgress(percentCompleted);
      } : undefined
    };
    
    return apiClient.post(url, formData, config);
  },
  
  // Batch requests with session validation
  batch: async (requests) => {
    // Ensure session is active before making batch requests
    if (!sessionService.isActive()) {
      throw new Error('No active session for batch requests');
    }
    
    try {
      const responses = await Promise.allSettled(
        requests.map(request => {
          const { method, url, data, config } = request;
          return apiClient[method](url, data, config);
        })
      );
      
      return responses;
    } catch (error) {
      console.error('Batch request error:', error);
      throw error;
    }
  },
  
  // Health check without session requirement
  healthCheck: () => {
    return axios.get('/health', { timeout: 5000 });
  }
};

// Export the configured axios instance for direct use if needed
export { apiClient };

export default api;
