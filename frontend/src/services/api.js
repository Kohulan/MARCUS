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

  // Docker compose environment - use nginx proxy instead of direct backend connection
  if (process.env.NODE_ENV === 'production') {
    return '/api'; // This will be proxied by nginx to the backend
  }

  // Development fallback
  return 'http://localhost:9000';
};

// Helper function to get correct image URL in any environment
export const getApiImageUrl = (path) => {
  const baseUrl = getApiBaseUrl();
  
  // Handle empty or invalid paths
  if (!path) return '';
  
  // Debug logging
  console.log(`getApiImageUrl input path:`, path);
  
  // If the path already has a full URL with baseUrl but missing /latest/, fix it
  if (path.startsWith(baseUrl) && path.includes('/decimer/get_segment_image/')) {
    // Extract the path after the baseUrl
    const urlPath = path.substring(baseUrl.length);
    // Ensure /latest/ is included in the URL
    const correctedUrl = `${baseUrl}/latest${urlPath}`;
    console.log(`Corrected URL with /latest/ prefix:`, correctedUrl);
    return correctedUrl;
  }
  
  // If the path already starts with the base URL (and isn't a segment image), return it as is
  if (path.startsWith(baseUrl)) {
    console.log(`Path already starts with baseUrl, returning as is:`, path);
    return path;
  }
  
  // Handle segment image paths to ensure proper versioning and format
  if (path.includes('all_segments')) {
    // Extract relevant parts from the path
    let cleanPath = path;
    
    // Remove /api/ prefix if present
    if (cleanPath.startsWith('/api/')) {
      cleanPath = cleanPath.replace('/api/', '');
      console.log(`Removed /api/ prefix:`, cleanPath);
    }
    
    // If path starts with decimer/get_segment_image, remove it to get clean path
    if (cleanPath.startsWith('decimer/get_segment_image/')) {
      cleanPath = cleanPath.replace('decimer/get_segment_image/', '');
      console.log(`Removed decimer/get_segment_image/ prefix:`, cleanPath);
    }
    
    // The backend expects a specific format for segment images:
    // Instead of /Untitled-1/all_segments/page_0_0_segmented.png
    // It needs /Untitled-1/page_0_0_segmented.png
    
    const pathParts = cleanPath.split('/');
    console.log(`Path parts:`, pathParts);
    
    const pdfName = pathParts[0]; // e.g., Untitled-1
    const filename = pathParts[pathParts.length - 1]; // e.g., page_0_0_segmented.png
    
    // This format matches exactly what the backend expects
    const result = `${baseUrl}/latest/decimer/get_segment_image/${pdfName}/${filename}`;
    console.log(`Created segment image URL:`, result);
    return result;
  }
  
  // If the path starts with /api/ but we're in development
  if (path.startsWith('/api/')) {
    // Extract the part after /api/
    const pathWithoutApi = path.replace('/api/', '');
    console.log(`Removed /api/ prefix:`, pathWithoutApi);
    
    // For development, construct with baseUrl
    if (baseUrl !== '/api') {
      const result = `${baseUrl}/${pathWithoutApi}`;
      console.log(`Development URL constructed:`, result);
      return result;
    }
    
    // For production, keep as is
    console.log(`Production URL kept as is:`, path);
    return path;
  }
  
  // For all other paths, ensure they have the /latest/ prefix
  let result;
  if (!path.startsWith('/')) {
    result = `${baseUrl}/latest/${path}`;
    console.log(`Added /latest/ prefix to path without leading slash:`, result);
  } else {
    // If path starts with / but not with /latest/
    if (!path.startsWith('/latest/')) {
      result = `${baseUrl}/latest${path}`;
      console.log(`Added /latest/ prefix to path with leading slash:`, result);
    } else {
      result = `${baseUrl}${path}`;
      console.log(`Path already has /latest/ prefix, just added baseUrl:`, result);
    }
  }
  
  return result;
}

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
// Health check function to check if backend is ready
export const checkBackendHealth = async () => {
  try {
    console.log('Checking backend health...');
    
    // Use the standard API base URL for health check
    const baseUrl = getApiBaseUrl();
    const url = `${baseUrl}/health`;
    
    console.log('Health check URL:', url);
    
    const response = await axios.get(url);
    console.log('Health check response:', response.data);
    
    const isReady = response.data.status === 'OK';
    console.log('Backend ready:', isReady);
    return isReady;
  } catch (error) {
    console.error('Backend health check failed:', error);
    return false;
  }
};

export default api;