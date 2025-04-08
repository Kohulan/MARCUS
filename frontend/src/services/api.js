import axios from 'axios'
// Get the API URL with proper fallbacks
const getApiBaseUrl = () => {
  // In production on the marcus.decimer.ai server
  if (window.location.hostname === 'marcus.decimer.ai') {
    return '/api'; // This will be proxied by Nginx
  }

  // Check for environment variables
  if (process.env && process.env.VUE_APP_API_URL) {
    return process.env.VUE_APP_API_URL;
  }

  // Docker compose environment - frontend can reach backend directly
  if (process.env.NODE_ENV === 'production') {
    return 'http://backend:9000';
  }

  // Development fallback
  return 'http://localhost:9000';
};
// Create axios instance with default config
const api = axios.create({
  baseURL: getApiBaseUrl(),
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  },
  // Increase timeout for larger file uploads
  timeout: 300000 // 3 minutes
});
// Add version prefix to all requests that don't already have it
api.interceptors.request.use(
  config => {
    // Log the request URL for debugging
    console.log('API Request (original):', config.method.toUpperCase(), config.baseURL + config.url);

    // Add version prefix if not already present
    if (config.url && !config.url.startsWith('/v') && !config.url.startsWith('/latest')) {
      config.url = '/latest' + config.url;
    }

    // For file uploads, adjust content type and timeout
    if (config.data instanceof FormData) {
      // Remove content-type header to let the browser set it with the boundary
      delete config.headers['Content-Type'];

      // Increase timeout specifically for uploads
      config.timeout = 300000; // 5 minutes
    }

    console.log('API Request (modified):', config.method.toUpperCase(), config.baseURL + config.url);
    return config;
  },
  error => {
    return Promise.reject(error);
  }
);
// Response interceptor for API calls
api.interceptors.response.use(
  response => {
    return response;
  },
  async error => {
    // Handle specific error cases
    if (error.response) {
      // The request was made and the server responded with a status code
      // that falls out of the range of 2xx
      console.error('API Error Response:', error.response.data);

      // Handle specific status codes
      switch(error.response.status) {
        case 413: // Request Entity Too Large
          console.error('The file you are trying to upload is too large. Maximum allowed size is 10MB.');
          // You could display a user-friendly message here
          break;

        case 401: // Unauthorized
          // Handle authentication errors
          break;

        case 403: // Forbidden
          // Handle permission errors
          break;

        case 404: // Not found
          // Handle not found errors
          break;

        case 422: // Validation error
          // Handle validation errors
          break;

        case 500: // Server error
          // Handle server errors
          break;
      }
    } else if (error.request) {
      // The request was made but no response was received
      console.error('API No Response:', error.request);
    } else {
      // Something happened in setting up the request that triggered an Error
      console.error('API Request Error:', error.message);
    }

    return Promise.reject(error);
  }
);
export default api;