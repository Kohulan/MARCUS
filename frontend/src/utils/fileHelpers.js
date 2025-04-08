/**
 * Utility functions for file operations
 */

/**
 * Format file size into human-readable string
 * @param {number} bytes - File size in bytes
 * @param {number} decimals - Number of decimal places
 * @returns {string} - Formatted file size
 */
export const formatFileSize = (bytes, decimals = 1) => {
    if (bytes === 0) return '0 Bytes'
    
    const k = 1024
    const dm = decimals < 0 ? 0 : decimals
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i]
  }
  
  /**
   * Get file extension from file name
   * @param {string} filename - File name
   * @returns {string} - File extension (without the dot)
   */
  export const getFileExtension = (filename) => {
    return filename.slice((filename.lastIndexOf('.') - 1 >>> 0) + 2)
  }
  
  /**
   * Check if file has allowed extension
   * @param {string} filename - File name
   * @param {Array} allowedExtensions - Array of allowed extensions
   * @returns {boolean} - Whether file has allowed extension
   */
  export const hasAllowedExtension = (filename, allowedExtensions) => {
    const extension = getFileExtension(filename).toLowerCase()
    return allowedExtensions.includes(extension)
  }
  
  /**
   * Create a safe filename (removes special characters)
   * @param {string} filename - Original filename
   * @returns {string} - Safe filename
   */
  export const createSafeFilename = (filename) => {
    // Replace spaces and special characters with underscores
    const safeName = filename.replace(/[^\w.-]/g, '_')
    return safeName
  }
  
  /**
   * Create a download link for a blob
   * @param {Blob} blob - Blob to download
   * @param {string} filename - File name
   */
  export const downloadBlob = (blob, filename) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }
  
  /**
   * Convert base64 string to Blob
   * @param {string} base64 - Base64 string
   * @param {string} mimeType - MIME type
   * @returns {Blob} - Blob object
   */
  export const base64ToBlob = (base64, mimeType) => {
    const byteString = atob(base64.split(',')[1])
    const ab = new ArrayBuffer(byteString.length)
    const ia = new Uint8Array(ab)
    
    for (let i = 0; i < byteString.length; i++) {
      ia[i] = byteString.charCodeAt(i)
    }
    
    return new Blob([ab], { type: mimeType })
  }
  
  /**
   * Read file as text
   * @param {File} file - File to read
   * @returns {Promise<string>} - File contents as text
   */
  export const readFileAsText = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result)
      reader.onerror = reject
      reader.readAsText(file)
    })
  }
  
  /**
   * Read file as data URL
   * @param {File} file - File to read
   * @returns {Promise<string>} - File contents as data URL
   */
  export const readFileAsDataURL = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result)
      reader.onerror = reject
      reader.readAsDataURL(file)
    })
  }