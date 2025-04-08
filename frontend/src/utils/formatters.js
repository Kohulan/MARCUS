/**
 * Utility functions for formatting data
 */

/**
 * Format a date into a readable string
 * @param {string|Date} date - Date to format
 * @param {Object} options - Formatting options
 * @returns {string} - Formatted date string
 */
export const formatDate = (date, options = {}) => {
    if (!date) return ''
    
    const dateObj = typeof date === 'string' ? new Date(date) : date
    
    if (isNaN(dateObj.getTime())) {
      return 'Invalid date'
    }
    
    const defaultOptions = {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    }
    
    const mergedOptions = { ...defaultOptions, ...options }
    
    return dateObj.toLocaleDateString(undefined, mergedOptions)
  }
  
  /**
   * Format a number with commas
   * @param {number} number - Number to format
   * @param {number} decimals - Number of decimal places
   * @returns {string} - Formatted number
   */
  export const formatNumber = (number, decimals = 0) => {
    if (number === null || number === undefined) return ''
    
    return Number(number).toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    })
  }
  
  /**
   * Capitalize the first letter of a string
   * @param {string} string - String to capitalize
   * @returns {string} - Capitalized string
   */
  export const capitalize = (string) => {
    if (!string) return ''
    
    return string.charAt(0).toUpperCase() + string.slice(1)
  }
  
  /**
   * Format a string to title case
   * @param {string} string - String to format
   * @returns {string} - Title case string
   */
  export const titleCase = (string) => {
    if (!string) return ''
    
    return string
      .toLowerCase()
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')
  }
  
  /**
   * Convert snake_case to camelCase
   * @param {string} string - Snake case string
   * @returns {string} - Camel case string
   */
  export const snakeToCamel = (string) => {
    if (!string) return ''
    
    return string.replace(
      /([-_][a-z])/g,
      group => group.toUpperCase()
        .replace('-', '')
        .replace('_', '')
    )
  }
  
  /**
   * Convert camelCase to snake_case
   * @param {string} string - Camel case string
   * @returns {string} - Snake case string
   */
  export const camelToSnake = (string) => {
    if (!string) return ''
    
    return string.replace(
      /[A-Z]/g,
      letter => `_${letter.toLowerCase()}`
    )
  }
  
  /**
   * Format a label from snake_case or camelCase to human-readable
   * @param {string} label - Label to format
   * @returns {string} - Formatted label
   */
  export const formatLabel = (label) => {
    if (!label) return ''
    
    // Replace underscores and hyphens with spaces
    let formatted = label.replace(/[_-]/g, ' ')
    
    // Insert space before capital letters (for camelCase)
    formatted = formatted.replace(/([A-Z])/g, ' $1')
    
    // Trim extra spaces, ensure single space between words
    formatted = formatted.replace(/\s+/g, ' ').trim()
    
    // Capitalize first letter of each word
    return titleCase(formatted)
  }
  
  /**
   * Truncate a string with ellipsis
   * @param {string} string - String to truncate
   * @param {number} length - Maximum length
   * @param {string} ellipsis - Ellipsis string
   * @returns {string} - Truncated string
   */
  export const truncate = (string, length = 50, ellipsis = '...') => {
    if (!string) return ''
    
    if (string.length <= length) {
      return string
    }
    
    return string.slice(0, length) + ellipsis
  }
  
  /**
   * Format bytes to human-readable file size
   * @param {number} bytes - Number of bytes
   * @param {number} decimals - Number of decimal places
   * @returns {string} - Formatted file size
   */
  export const formatBytes = (bytes, decimals = 2) => {
    if (bytes === 0) return '0 Bytes'
    
    const k = 1024
    const dm = decimals < 0 ? 0 : decimals
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB']
    
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i]
  }
  
  /**
   * Format a percentage
   * @param {number} value - Value to format
   * @param {number} total - Total value
   * @param {number} decimals - Number of decimal places
   * @returns {string} - Formatted percentage
   */
  export const formatPercentage = (value, total, decimals = 1) => {
    if (!value || !total) return '0%'
    
    const percentage = (value / total) * 100
    
    return percentage.toFixed(decimals) + '%'
  }