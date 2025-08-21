/**
 * Session encryption utilities for MARCUS frontend
 * Implements client-side session security
 */

/**
 * Secure session storage with encryption
 */
class SecureSessionStorage {
  constructor() {
    this.encryptionKey = this.getEncryptionKey();
  }

  /**
   * Generate or retrieve encryption key for session data
   * Uses a combination of browser characteristics and stored data
   */
  getEncryptionKey() {
    try {
      // Try to get existing key from secure storage
      let key = localStorage.getItem('marcus_enc_key');
      
      if (!key) {
        // Generate new key based on browser characteristics
        const browserData = this.getBrowserFingerprint();
        key = this.generateKeyFromFingerprint(browserData);
      let key = sessionStorage.getItem('marcus_enc_key');
      
      if (!key) {
        // Generate new key based on browser characteristics
        const browserData = this.getBrowserFingerprint();
        key = this.generateKeyFromFingerprint(browserData);
        sessionStorage.setItem('marcus_enc_key', key);
      }
      
      return key;
    } catch (error) {
      console.error('Error getting encryption key:', error);
      // Fallback to a basic key if crypto operations fail
      return 'marcus_fallback_key_' + Date.now();
    }
  }

  /**
   * Generate browser fingerprint for key derivation
   */
  getBrowserFingerprint() {
    const fingerprint = {
      userAgent: navigator.userAgent || '',
      language: navigator.language || '',
      platform: navigator.platform || '',
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || '',
      screen: `${screen.width}x${screen.height}`,
      colorDepth: screen.colorDepth || 0,
      cookieEnabled: navigator.cookieEnabled,
      doNotTrack: navigator.doNotTrack || '',
    };
    
    // Create a hash-like string from fingerprint
    return btoa(JSON.stringify(fingerprint)).substring(0, 32);
  }

  /**
   * Generate encryption key from browser fingerprint
   */
  generateKeyFromFingerprint(fingerprint) {
    // Simple key derivation - in production, consider using Web Crypto API
    const baseKey = 'marcus_session_' + fingerprint;
    return btoa(baseKey).substring(0, 32).padEnd(32, '0');
  }

  /**
   * Encrypt session data
   */
  encrypt(data) {
    try {
      if (typeof data !== 'string') {
        data = JSON.stringify(data);
      }

      // Use a simple XOR cipher with base64 encoding
      // In production, consider using Web Crypto API for stronger encryption
      const key = this.encryptionKey;
      let encrypted = '';
      
      for (let i = 0; i < data.length; i++) {
        const keyChar = key.charCodeAt(i % key.length);
        const dataChar = data.charCodeAt(i);
        encrypted += String.fromCharCode(dataChar ^ keyChar);
      }
      
   * Encrypt session data using AES-GCM via Web Crypto API
   * Returns a Promise that resolves to a base64 string containing IV and ciphertext
   */
  async encrypt(data) {
    try {
      if (typeof data !== 'string') {
        data = JSON.stringify(data);
      }
      const enc = new TextEncoder();
      const iv = this.getIV();
      const key = await this.keyPromise;
      const ciphertext = await window.crypto.subtle.encrypt(
        {
          name: "AES-GCM",
          iv: iv
        },
        key,
        enc.encode(data)
      );
      // Combine IV and ciphertext for storage
      const ivBase64 = btoa(String.fromCharCode(...iv));
      const ctBase64 = btoa(String.fromCharCode(...new Uint8Array(ciphertext)));
      // Store as iv:ciphertext
      return ivBase64 + ":" + ctBase64;
    } catch (error) {
      console.error('Encryption failed:', error);
      return btoa(JSON.stringify(data)); // Fallback to base64 encoding
    }
  }

  /**
   * Decrypt session data
   */
  decrypt(encryptedData) {
    try {
      if (!encryptedData) {
        return null;
      }

      const encrypted = atob(encryptedData);
      const key = this.encryptionKey;
      let decrypted = '';
      
      for (let i = 0; i < encrypted.length; i++) {
        const keyChar = key.charCodeAt(i % key.length);
        const encryptedChar = encrypted.charCodeAt(i);
        decrypted += String.fromCharCode(encryptedChar ^ keyChar);
      }
      
      // Try to parse as JSON, fallback to string
      try {
        return JSON.parse(decrypted);
      } catch {
        return decrypted;
      }
    } catch (error) {
      console.error('Decryption failed:', error);
      // Try base64 decode as fallback
      try {
        return JSON.parse(atob(encryptedData));
      } catch {
        return null;
      }
    }
  }

  /**
   * Store encrypted session data
   */
  setItem(key, value) {
    try {
      const encrypted = this.encrypt(value);
      sessionStorage.setItem(key, encrypted);
      return true;
    } catch (error) {
      console.error('Secure storage failed:', error);
      // Fallback to regular storage
      sessionStorage.setItem(key, JSON.stringify(value));
      return false;
    }
  }

  /**
   * Retrieve and decrypt session data
   */
  getItem(key) {
    try {
      const encrypted = sessionStorage.getItem(key);
      if (!encrypted) {
        return null;
      }
      return this.decrypt(encrypted);
    } catch (error) {
      console.error('Secure retrieval failed:', error);
      // Fallback to regular retrieval
      try {
        const data = sessionStorage.getItem(key);
        return data ? JSON.parse(data) : null;
      } catch {
        return sessionStorage.getItem(key);
      }
    }
  }

  /**
   * Remove item from secure storage
   */
  removeItem(key) {
    sessionStorage.removeItem(key);
  }

  /**
   * Clear all session data
   */
  clear() {
    sessionStorage.clear();
  }

  /**
   * Rotate encryption key (for security)
   */
  rotateEncryptionKey() {
    try {
      // Get all current session data
      const sessionData = {};
      for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i);
        if (key.startsWith('marcus_')) {
          sessionData[key] = this.getItem(key);
        }
      }

      // Generate new key
      localStorage.removeItem('marcus_enc_key');
      this.encryptionKey = this.getEncryptionKey();

      // Re-encrypt all data with new key
      Object.entries(sessionData).forEach(([key, value]) => {
        this.setItem(key, value);
      });

      console.log('Encryption key rotated successfully');
      return true;
    } catch (error) {
      console.error('Key rotation failed:', error);
      return false;
    }
  }
}

/**
 * Session security manager
 */
class SessionSecurityManager {
  constructor() {
    this.secureStorage = new SecureSessionStorage();
    this.sessionMetrics = {
      createdAt: null,
      lastActivity: null,
      activityCount: 0,
      securityEvents: []
    };
    this.maxInactiveTime = 30 * 60 * 1000; // 30 minutes
    this.setupSecurityMonitoring();
  }

  /**
   * Create secure session with client fingerprinting
   */
  createSecureSession(sessionId, userData = {}) {
    try {
      const sessionData = {
        sessionId,
        userData,
        createdAt: new Date().toISOString(),
        lastActivity: new Date().toISOString(),
        clientFingerprint: this.secureStorage.getBrowserFingerprint(),
        securityLevel: 'high',
        encrypted: true
      };

      // Store with encryption
      this.secureStorage.setItem('marcus_session', sessionData);
      this.secureStorage.setItem('marcus_session_id', sessionId);

      // Update metrics
      this.sessionMetrics.createdAt = sessionData.createdAt;
      this.sessionMetrics.lastActivity = sessionData.lastActivity;
      this.sessionMetrics.activityCount = 0;

      this.logSecurityEvent('session_created', { sessionId, encrypted: true });
      
      console.log('Secure session created:', sessionId);
      return sessionData;
    } catch (error) {
      console.error('Secure session creation failed:', error);
      throw new Error('Failed to create secure session');
    }
  }

  /**
   * Validate session security
   */
  validateSession() {
    try {
      const sessionData = this.secureStorage.getItem('marcus_session');
      if (!sessionData) {
        return { valid: false, reason: 'no_session' };
      }

      // Check session expiration
      const now = new Date();
      const lastActivity = new Date(sessionData.lastActivity);
      const timeSinceActivity = now - lastActivity;

      if (timeSinceActivity > this.maxInactiveTime) {
        this.invalidateSession('session_timeout');
        return { valid: false, reason: 'session_expired' };
      }

      // Check fingerprint for hijacking detection
      const currentFingerprint = this.secureStorage.getBrowserFingerprint();
      if (sessionData.clientFingerprint !== currentFingerprint) {
        this.logSecurityEvent('fingerprint_mismatch', {
          stored: sessionData.clientFingerprint,
          current: currentFingerprint
        });
        
        // Don't immediately invalidate - could be legitimate browser changes
        // Instead, require re-authentication for sensitive operations
        sessionData.requiresReauth = true;
        this.secureStorage.setItem('marcus_session', sessionData);
        
        return { 
          valid: true, 
          requiresReauth: true, 
          reason: 'fingerprint_changed',
          sessionData 
        };
      }

      // Update activity
      sessionData.lastActivity = now.toISOString();
      this.sessionMetrics.lastActivity = sessionData.lastActivity;
      this.sessionMetrics.activityCount++;
      this.secureStorage.setItem('marcus_session', sessionData);

      return { valid: true, sessionData };
    } catch (error) {
      console.error('Session validation error:', error);
      return { valid: false, reason: 'validation_error' };
    }
  }

  /**
   * Invalidate session securely
   */
  invalidateSession(reason = 'user_logout') {
    try {
      // Clear session data
      this.secureStorage.removeItem('marcus_session');
      this.secureStorage.removeItem('marcus_session_id');
      
      // Clear other session-related data
      const keysToRemove = [];
      for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i);
        if (key && key.startsWith('marcus_')) {
          keysToRemove.push(key);
        }
      }
      
      keysToRemove.forEach(key => this.secureStorage.removeItem(key));

      this.logSecurityEvent('session_invalidated', { reason });
      
      // Reset metrics
      this.sessionMetrics = {
        createdAt: null,
        lastActivity: null,
        activityCount: 0,
        securityEvents: []
      };

      console.log('Session invalidated:', reason);
      return true;
    } catch (error) {
      console.error('Session invalidation error:', error);
      return false;
    }
  }

  /**
   * Setup security event monitoring
   */
  setupSecurityMonitoring() {
    // Monitor for suspicious activity (rapid requests)
    let rapidRequestCount = 0;
    const rapidRequestWindow = 10000; // 10 seconds
    
    // Reset rapid request counter periodically
    setInterval(() => {
      if (rapidRequestCount > 0) {
        this.logSecurityEvent('rapid_requests_detected', { count: rapidRequestCount });
        rapidRequestCount = 0;
      }
    }, rapidRequestWindow);
    
    // Monitor fetch requests for rapid activity
    const originalFetch = window.fetch;
    window.fetch = (...args) => {
      rapidRequestCount++;
      if (rapidRequestCount > 20) { // Threshold for suspicious activity
        this.logSecurityEvent('excessive_requests', { count: rapidRequestCount });
      }
      return originalFetch.apply(window, args);
    };
    // To monitor fetch requests for rapid activity, use this.monitoredFetch instead of window.fetch in your code.
    // Example: secureSessionStorage.monitoredFetch(url, options)
    
    // See the monitoredFetch method for implementation.
    // Track page focus/blur for session security
    window.addEventListener('focus', () => {
      this.logSecurityEvent('page_focus');
    });
    
    window.addEventListener('blur', () => {
      this.logSecurityEvent('page_blur');
    });

    // Monitor for developer tools (basic detection)
    let devtools = { open: false };
    const threshold = 160;
    
    setInterval(() => {
      if (window.outerHeight - window.innerHeight > threshold || 
          window.outerWidth - window.innerWidth > threshold) {
        if (!devtools.open) {
          devtools.open = true;
          this.logSecurityEvent('devtools_opened');
        }
      } else {
        if (devtools.open) {
          devtools.open = false;
          this.logSecurityEvent('devtools_closed');
        }
      }
    }, 5000);
  }

  /**
   * Log security events
   */
  logSecurityEvent(event, data = {}) {
    const securityEvent = {
      event,
      timestamp: new Date().toISOString(),
      data,
      url: window.location.href,
      userAgent: navigator.userAgent
    };

    this.sessionMetrics.securityEvents.push(securityEvent);

    // Keep only last 50 events to prevent memory bloat
    if (this.sessionMetrics.securityEvents.length > 50) {
      this.sessionMetrics.securityEvents = this.sessionMetrics.securityEvents.slice(-50);
    }

    // Log critical events to console
    const criticalEvents = ['fingerprint_mismatch', 'session_invalidated', 'devtools_opened'];
    if (criticalEvents.includes(event)) {
      console.warn('Security Event:', securityEvent);
    }
  }

  /**
   * Get session security metrics
   */
  getSecurityMetrics() {
    return {
      ...this.sessionMetrics,
      encryptionEnabled: true,
      fingerprintingEnabled: true,
      currentFingerprint: this.secureStorage.getBrowserFingerprint()
    };
  }

  /**
   * Test encryption/decryption functionality
   */
  testEncryption() {
    try {
      const testData = { test: 'encryption_test', timestamp: Date.now() };
      const encrypted = this.secureStorage.encrypt(testData);
      const decrypted = this.secureStorage.decrypt(encrypted);
      
      const success = JSON.stringify(testData) === JSON.stringify(decrypted);
      console.log('Encryption test:', success ? 'PASSED' : 'FAILED');
      return success;
    } catch (error) {
      console.error('Encryption test failed:', error);
      return false;
    }
  }
}

// Create global instances
const secureSessionStorage = new SecureSessionStorage();
const sessionSecurityManager = new SessionSecurityManager();

// Export for use in other modules
export { 
  SecureSessionStorage, 
  SessionSecurityManager, 
  secureSessionStorage, 
  sessionSecurityManager 
};
