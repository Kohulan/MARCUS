/**
 * Utility for loading and confirming SmilesDrawer library availability
 */

// URL to the SmilesDrawer library CDN
const SMILES_DRAWER_URL = 'https://unpkg.com/smiles-drawer@1.2.0/dist/smiles-drawer.min.js';

/**
 * Load the SmilesDrawer library and returns a promise that resolves
 * when the library is available
 * @returns {Promise<any>} Promise that resolves with the SmilesDrawer object or rejects on error
 */
export const loadSmilesDrawer = () => {
  return new Promise((resolve, reject) => {
    // Check if SmilesDrawer is already loaded
    if (typeof window.SmilesDrawer !== 'undefined') {
      console.log('SmilesDrawer already loaded');
      resolve(window.SmilesDrawer);
      return;
    }

    console.log('Loading SmilesDrawer from CDN...');

    // Create a script element to load the library
    const script = document.createElement('script');
    script.src = SMILES_DRAWER_URL;
    script.async = true;
    
    // Set up callback for successful load
    script.onload = () => {
      console.log('SmilesDrawer loaded successfully');
      if (typeof window.SmilesDrawer !== 'undefined') {
        resolve(window.SmilesDrawer);
      } else {
        reject(new Error('SmilesDrawer loaded but not defined'));
      }
    };
    
    // Set up callback for loading error
    script.onerror = () => {
      console.error('Failed to load SmilesDrawer from CDN');
      reject(new Error('Failed to load SmilesDrawer library'));
    };
    
    // Add the script to the document to start loading
    document.head.appendChild(script);
  });
};

/**
 * Check if SmilesDrawer is already loaded
 * @returns {boolean} True if SmilesDrawer is available
 */
export const isSmilesDrawerLoaded = () => {
  return typeof window.SmilesDrawer !== 'undefined';
};

export default {
  loadSmilesDrawer,
  isSmilesDrawerLoaded
};