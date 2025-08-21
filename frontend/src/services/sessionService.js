/**
 * Enhanced session service with security improvements
 * Implements comprehensive session management
 */

import { sessionSecurityManager } from '../utils/sessionSecurity.js';

class SessionService {
  constructor() {
    this.websocket = null;
    this.sessionId = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 2000;
    this.heartbeatInterval = null;
    this.listeners = new Map();
    this.pageUnloadHandlerAdded = false;
    this.sessionKey = 'marcus_session_id';
    
    // Get backend URL using the same logic as other services
    this.backendUrl = this.getApiBaseUrl();
    this.wsUrl = this.getWebSocketUrl();
    
    // Try to recover existing session
    this.recoverSession();
    
    // Add page unload handler immediately
    this.addPageUnloadHandler();
  }

  /**
   * Try to recover an existing session from secure storage
   */
  recoverSession() {
    try {
      // Try secure session recovery first
      const validation = sessionSecurityManager.validateSession();
      if (validation.valid && validation.sessionData) {
        this.sessionId = validation.sessionData.sessionId;
        console.log('Recovered secure session:', this.sessionId);
        
        if (validation.requiresReauth) {
          console.warn('Session requires re-authentication due to security concerns');
          this.emit('requiresReauth', validation.reason);
        }
        return;
      }
    } catch (error) {
      console.warn('Secure session recovery failed:', error);
    }
    
    // Fallback to regular session storage
    const storedSessionId = sessionStorage.getItem(this.sessionKey);
    if (storedSessionId) {
      this.sessionId = storedSessionId;
      console.log('Recovered session from regular storage:', storedSessionId);
    }
  }

  /**
   * Store session ID in secure encrypted storage
   */
  storeSession(sessionId) {
    if (sessionId) {
      this.sessionId = sessionId;
      
      // Use secure storage with encryption
      try {
        sessionSecurityManager.createSecureSession(sessionId, {
          userAgent: navigator.userAgent,
          timestamp: new Date().toISOString()
        });
        console.log('Session stored securely with encryption');
      } catch (error) {
        console.warn('Secure storage failed, falling back to regular storage:', error);
        sessionStorage.setItem(this.sessionKey, sessionId);
      }
    }
  }

  /**
   * Clear stored session securely
   */
  clearStoredSession() {
    try {
      sessionSecurityManager.invalidateSession('user_logout');
      console.log('Session cleared securely');
    } catch (error) {
      console.warn('Secure session clearing failed, using fallback:', error);
      sessionStorage.removeItem(this.sessionKey);
    }
  }

  /**
   * Create a new session with improved error handling and retry logic
   */
  async createSession(userId = null) {
    console.log('createSession called, current sessionId:', this.sessionId);
    
    // If we have a stored session, try to verify it first
    if (this.sessionId) {
      console.log('Found existing sessionId, verifying with backend...');
      try {
        const status = await this.getSessionStatus();
        console.log('Session status check result:', status);
        if (status.success) {
          console.log('Using existing session:', this.sessionId);
          // Try to connect WebSocket, but don't fail session recovery if WebSocket fails
          try {
            await this.connectWebSocket();
          } catch (wsError) {
            console.warn('WebSocket connection failed, but session is valid:', wsError.message);
          }
          return status;
        }
      } catch (error) {
        console.log('Existing session invalid, creating new one. Error:', error);
        this.clearStoredSession();
        this.sessionId = null;
      }
    }

    // Retry logic for session creation
    const maxRetries = 3;
    let lastError;
    
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        console.log(`Creating session attempt ${attempt}/${maxRetries}`);
        
        if (!this.backendUrl) {
          this.backendUrl = this.getApiBaseUrl();
        }
        
        console.log('Creating session with backend URL:', this.backendUrl);
        
        // Add timeout to fetch request
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
        
        let requestUrl;
        try {
          const url = new URL(`${this.backendUrl}/session/create`);
          if (userId) {
            url.searchParams.append('user_id', userId);
          }
          requestUrl = url.toString();
        } catch (urlError) {
          console.warn('URL construction failed, falling back to string concatenation');
          requestUrl = `${this.backendUrl}/session/create${userId ? `?user_id=${encodeURIComponent(userId)}` : ''}`;
        }
        
        console.log('Session creation URL:', requestUrl);
        
        const response = await fetch(requestUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
          const errorText = await response.text().catch(() => 'Unknown error');
          throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        const data = await response.json();
        
        if (data.success) {
          this.storeSession(data.session.session_id);
          // Try to connect WebSocket, but don't fail session creation if WebSocket fails
          try {
            await this.connectWebSocket();
          } catch (wsError) {
            console.warn('WebSocket connection failed, but session created successfully:', wsError.message);
          }
          return data;
        } else {
          throw new Error('Server returned unsuccessful response');
        }
        
      } catch (error) {
        lastError = error;
        console.error(`Session creation attempt ${attempt} failed:`, error);
        
        // If this is the last attempt, throw the error
        if (attempt === maxRetries) {
          break;
        }
        
        // Wait before retrying (exponential backoff)
        const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000);
        console.log(`Retrying in ${delay}ms...`);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
    
    // If we get here, all retries failed
    throw new Error(`Failed to create session after ${maxRetries} attempts. Last error: ${lastError.message}`);
  }

  /**
   * Connect to WebSocket for real-time updates with improved error handling
   */
  async connectWebSocket() {
    if (!this.sessionId) {
      throw new Error('No session ID available for WebSocket connection');
    }

    return new Promise((resolve, reject) => {
      try {
        // Ensure the WebSocket URL is properly formatted
        if (window.location.hostname === 'marcus.decimer.ai' && !this.wsUrl.startsWith('wss://')) {
          console.log('Updating wsUrl for production environment');
          this.wsUrl = 'wss://api.marcus.decimer.ai';
        }
        
        const wsUrl = `${this.wsUrl}/session/ws/${this.sessionId}`;
        console.log('Connecting to WebSocket:', wsUrl);
        this.websocket = new WebSocket(wsUrl);
        
        // Add connection timeout
        const connectionTimeout = setTimeout(() => {
          if (this.websocket.readyState === WebSocket.CONNECTING) {
            this.websocket.close();
            reject(new Error('WebSocket connection timeout'));
          }
        }, 10000); // 10 second timeout
        
        this.websocket.onopen = () => {
          clearTimeout(connectionTimeout);
          console.log('WebSocket connected');
          this.reconnectAttempts = 0;
          this.reconnectDelay = 2000;
          this.startHeartbeat();
          this.emit('connected');
          resolve();
        };

        this.websocket.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            this.handleWebSocketMessage(message);
          } catch (error) {
            console.error('Error parsing WebSocket message:', error);
          }
        };

        this.websocket.onclose = (event) => {
          clearTimeout(connectionTimeout);
          console.log('WebSocket closed:', event.code, event.reason);
          this.stopHeartbeat();
          this.emit('disconnected');
          
          // Only attempt reconnect for unexpected closures
          if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.attemptReconnect();
          }
        };

        this.websocket.onerror = (error) => {
          clearTimeout(connectionTimeout);
          console.error('WebSocket error:', error);
          this.emit('error', error);
          reject(error);
        };

      } catch (error) {
        console.error('Failed to create WebSocket:', error);
        reject(error);
      }
    });
  }

  /**
   * Handle incoming WebSocket messages
   */
  handleWebSocketMessage(message) {
    switch (message.type) {
      case 'status_update':
        this.emit('statusUpdate', {
          sessionStatus: message.session_status,
          queueStatus: message.queue_status
        });
        break;
      
      case 'queue_update':
        this.emit('queueUpdate', {
          sessionStatus: message.session_status,
          queueStatus: message.queue_status
        });
        break;

      case 'ping':
        // Respond to server ping
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
          this.websocket.send(JSON.stringify({ type: 'pong' }));
        }
        break;
      
      default:
        console.log('Unknown message type:', message.type);
    }
  }

  /**
   * Start sending heartbeat messages with improved error handling
   */
  startHeartbeat() {
    this.heartbeatInterval = setInterval(() => {
      if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
        try {
          this.websocket.send(JSON.stringify({ type: 'heartbeat' }));
        } catch (error) {
          console.error('Failed to send WebSocket heartbeat:', error);
          // Fall back to HTTP heartbeat
          this.sendHttpHeartbeat();
        }
      } else if (this.sessionId) {
        // WebSocket is not available, use HTTP heartbeat
        this.sendHttpHeartbeat();
      }
    }, 15000);
  }

  /**
   * Stop sending heartbeat messages
   */
  stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  /**
   * Attempt to reconnect WebSocket
   */
  attemptReconnect() {
    // Don't attempt to reconnect if we don't have a session ID
    if (!this.sessionId) {
      console.log('No session ID available for reconnection, skipping reconnect attempt');
      this.emit('reconnectFailed');
      return;
    }

    this.reconnectAttempts++;
    console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
    
    setTimeout(() => {
      this.connectWebSocket().catch((error) => {
        console.error('Reconnection failed:', error);
        
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
          this.emit('reconnectFailed');
        } else {
          this.reconnectDelay *= 1.5;
        }
      });
    }, this.reconnectDelay);
  }

  /**
   * Get current session status
   */
  async getSessionStatus() {
    if (!this.sessionId) {
      throw new Error('No active session');
    }

    try {
      const response = await fetch(`${this.backendUrl}/session/status/${this.sessionId}`);
      
      if (response.status === 404) {
        console.log('Session not found, cleaning up local state');
        this.cleanup();
        this.emit('sessionExpired');
        return { success: false, error: 'Session expired' };
      }
      
      if (!response.ok) {
        throw new Error(`Failed to get session status: ${response.statusText}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error getting session status:', error);
      throw error;
    }
  }

  /**
   * Get queue status
   */
  async getQueueStatus() {
    try {
      const response = await fetch(`${this.backendUrl}/session/queue`);
      
      if (!response.ok) {
        throw new Error(`Failed to get queue status: ${response.statusText}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error getting queue status:', error);
      throw error;
    }
  }

  /**
   * End the current session
   */
  async endSession() {
    if (!this.sessionId) {
      return { success: true, message: 'No active session to end' };
    }

    try {
      if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
        this.websocket.send(JSON.stringify({ type: 'disconnect' }));
      }

      let response = await fetch(`${this.backendUrl}/session/remove/${this.sessionId}`, {
        method: 'DELETE'
      });

      if (response.status === 405) {
        response = await fetch(`${this.backendUrl}/session/remove/${this.sessionId}`, {
          method: 'POST'
        });
      }

      if (response.ok) {
        return { success: true, message: 'Session ended successfully' };
      } else if (response.status === 404) {
        console.log('Session was already removed or expired');
        return { success: true, message: 'Session was already ended' };
      } else {
        console.warn(`Failed to end session: ${response.status} ${response.statusText}`);
        return { success: false, error: `HTTP ${response.status}` };
      }

    } catch (error) {
      console.error('Error ending session:', error);
      return { success: false, error: error.message };
    } finally {
      this.cleanup();
    }
  }

  /**
   * Clean up resources
   */
  cleanup() {
    this.stopHeartbeat();
    
    if (this.websocket) {
      this.websocket.close(1000, 'Session ended');
      this.websocket = null;
    }
    
    this.clearStoredSession();
    this.sessionId = null;
    this.reconnectAttempts = 0;
    this.listeners.clear();
  }

  /**
   * Add event listener
   */
  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(callback);
  }

  /**
   * Remove event listener
   */
  off(event, callback) {
    if (this.listeners.has(event)) {
      const callbacks = this.listeners.get(event);
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
      }
    }
  }

  /**
   * Emit event to listeners
   */
  emit(event, data = null) {
    if (this.listeners.has(event)) {
      this.listeners.get(event).forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error(`Error in event listener for ${event}:`, error);
        }
      });
    }
  }

  /**
   * Check if user is currently active
   */
  isActive() {
    return this.sessionId !== null;
  }

  /**
   * Get current session ID
   */
  getSessionId() {
    return this.sessionId;
  }

  /**
   * Add page unload handler to ensure session cleanup with improved reliability
   */
  addPageUnloadHandler() {
    if (this.pageUnloadHandlerAdded) return;
    
    const handlePageUnload = () => {
      if (this.sessionId) {
        try {
          // Use sendBeacon as primary method (most reliable)
          const success = navigator.sendBeacon(
            `${this.backendUrl}/session/remove/${this.sessionId}`,
            JSON.stringify({})
          );
          
          if (!success) {
            // Fallback to synchronous XHR if sendBeacon fails
            const xhr = new XMLHttpRequest();
            xhr.open('POST', `${this.backendUrl}/session/remove/${this.sessionId}`, false);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.send(JSON.stringify({}));
          }
          
          // Also signal through WebSocket if available
          if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify({ type: 'disconnect' }));
          }
          
          console.log('Session cleanup triggered on page unload');
        } catch (error) {
          console.warn('Failed session cleanup on unload:', error);
        }
        
        // Clear local session references
        this.sessionId = null;
        sessionStorage.removeItem(this.sessionKey);
      }
    };
    
    // Add multiple event listeners to ensure cleanup happens
    window.addEventListener('beforeunload', handlePageUnload);
    window.addEventListener('unload', handlePageUnload);
    window.addEventListener('pagehide', handlePageUnload);
    
    // Handle tab visibility changes
    document.addEventListener('visibilitychange', () => {
      // Only on hiding the tab - don't cleanup on just switching tabs
      if (document.visibilityState === 'hidden' && this.sessionId) {
        // Just send websocket signal, don't remove session on tab switch
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
          this.websocket.send(JSON.stringify({ type: 'heartbeat' }));
        }
      }
    });
    
    this.pageUnloadHandlerAdded = true;
  }

  /**
   * Send HTTP heartbeat when WebSocket is unavailable
   */
  async sendHttpHeartbeat() {
    if (!this.sessionId) return;
    
    try {
      const response = await fetch(`${this.backendUrl}/session/heartbeat/${this.sessionId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.session_status) {
          this.emit('statusUpdate', {
            sessionStatus: data.session_status,
            queueStatus: null
          });
        }
      } else if (response.status === 404) {
        console.log('Session expired, clearing local state');
        this.cleanup();
        this.emit('sessionExpired');
      }
    } catch (error) {
      console.error('HTTP heartbeat failed:', error);
    }
  }

  /**
   * Get the API base URL with proper fallbacks - matches api.js logic
   */
  getApiBaseUrl() {
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
  }

  /**
   * Get WebSocket URL based on the HTTP API URL
   */
  getWebSocketUrl() {
    // In production on the marcus.decimer.ai server
    if (window.location.hostname === 'marcus.decimer.ai') {
      // Use the API domain but with WebSocket protocol
      return 'wss://api.marcus.decimer.ai';
    }

    // Check for environment variables and convert to WebSocket URL
    if (process.env && process.env.VUE_APP_API_URL) {
      const apiUrl = process.env.VUE_APP_API_URL;
      return apiUrl.replace(/^https?:/, 'ws:');
    }

    // Docker compose environment - use nginx proxy with WebSocket upgrade
    if (process.env.NODE_ENV === 'production') {
      return `ws://${window.location.host}/api`;
    }

    // Development fallback - connect directly to backend
    return 'ws://localhost:9000';
  }
}

// Create and export singleton instance
const sessionService = new SessionService();

export default sessionService;