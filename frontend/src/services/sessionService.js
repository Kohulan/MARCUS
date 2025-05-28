/**
 * Session Management Service for MARCUS
 * Handles user session creation, WebSocket connections, and queue management
 */

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
   * Try to recover an existing session from storage
   */
  recoverSession() {
    const storedSessionId = sessionStorage.getItem(this.sessionKey);
    if (storedSessionId) {
      this.sessionId = storedSessionId;
      console.log('Recovered session from storage:', storedSessionId);
    }
  }

  /**
   * Store session ID in session storage
   */
  storeSession(sessionId) {
    if (sessionId) {
      this.sessionId = sessionId;
      sessionStorage.setItem(this.sessionKey, sessionId);
    }
  }

  /**
   * Clear stored session
   */
  clearStoredSession() {
    sessionStorage.removeItem(this.sessionKey);
  }

  /**
   * Create a new session
   */
  async createSession(userId = null) {
    // If we have a stored session, try to verify it first
    if (this.sessionId) {
      try {
        const status = await this.getSessionStatus();
        if (status.success) {
          console.log('Using existing session:', this.sessionId);
          // Try to connect WebSocket, but don't fail session recovery if WebSocket fails
          try {
            await this.connectWebSocket();
          } catch (wsError) {
            console.warn('WebSocket connection failed, but session is valid:', wsError.message);
            // Session is still valid even if WebSocket fails
          }
          return status;
        }
      } catch (error) {
        console.log('Existing session invalid, creating new one');
        this.clearStoredSession();
        this.sessionId = null;
      }
    }

    try {
      // Make sure we have a valid backend URL
      if (!this.backendUrl) {
        this.backendUrl = this.getApiBaseUrl();
      }
      
      console.log('Creating session with backend URL:', this.backendUrl);
      
      // For production environment, ensure we're using the direct API URL
      if (window.location.hostname === 'marcus.decimer.ai' && !this.backendUrl.startsWith('https://api.')) {
        console.log('Updating backendUrl for production environment');
        this.backendUrl = 'https://api.marcus.decimer.ai';
      }
      
      // Safely construct the URL or fall back to string concatenation
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
        }
      });

      if (!response.ok) {
        throw new Error(`Failed to create session: ${response.statusText}`);
      }

      const data = await response.json();
      
      if (data.success) {
        this.storeSession(data.session.session_id);
        // Try to connect WebSocket, but don't fail session creation if WebSocket fails
        try {
          await this.connectWebSocket();
        } catch (wsError) {
          console.warn('WebSocket connection failed, but session created successfully:', wsError.message);
          // Session is still valid even if WebSocket fails
        }
        return data;
      } else {
        throw new Error('Failed to create session');
      }
    } catch (error) {
      console.error('Error creating session:', error);
      throw error;
    }
  }

  /**
   * Connect to WebSocket for real-time updates
   */
  async connectWebSocket() {
    if (!this.sessionId) {
      throw new Error('No session ID available for WebSocket connection');
    }

    try {
      // Ensure the WebSocket URL is properly formatted
      if (window.location.hostname === 'marcus.decimer.ai' && !this.wsUrl.startsWith('wss://')) {
        console.log('Updating wsUrl for production environment');
        this.wsUrl = 'wss://api.marcus.decimer.ai';
      }
      
      const wsUrl = `${this.wsUrl}/session/ws/${this.sessionId}`;
      console.log('Connecting to WebSocket:', wsUrl);
      this.websocket = new WebSocket(wsUrl);
      
      this.websocket.onopen = () => {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.reconnectDelay = 2000;
        this.startHeartbeat();
        this.emit('connected');
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
        console.log('WebSocket closed:', event.code, event.reason);
        this.stopHeartbeat();
        this.emit('disconnected');
        
        if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.attemptReconnect();
        }
      };

      this.websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.emit('error', error);
      };

    } catch (error) {
      console.error('Failed to connect WebSocket:', error);
      throw error;
    }
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
      
      default:
        console.log('Unknown message type:', message.type);
    }
  }

  /**
   * Start sending heartbeat messages
   */
  startHeartbeat() {
    this.heartbeatInterval = setInterval(() => {
      if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
        this.websocket.send(JSON.stringify({ type: 'heartbeat' }));
      } else if (this.sessionId) {
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
   * Add page unload handler to ensure session cleanup
   */
  addPageUnloadHandler() {
    if (this.pageUnloadHandlerAdded) return;
    
    const handlePageUnload = () => {
      if (this.sessionId) {
        // Explicit synchronous disconnection - more reliable for tab close
        // Try both methods to ensure session cleanup
        try {
          // 1. Synchronous XHR request (works during unload)
          const xhr = new XMLHttpRequest();
          xhr.open('POST', `${this.backendUrl}/session/remove/${this.sessionId}`, false); // false = synchronous
          xhr.setRequestHeader('Content-Type', 'application/json');
          xhr.send(JSON.stringify({}));
          
          // 2. Also try WebSocket if available
          if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify({ type: 'disconnect' }));
          }
          
          // 3. Beacon as last resort fallback
          navigator.sendBeacon(
            `${this.backendUrl}/session/remove/${this.sessionId}`,
            JSON.stringify({})
          );
          
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
   * Get the API base URL with proper fallbacks - matches api.js logic but for session endpoints
   */
  getApiBaseUrl() {
    // In production on the marcus.decimer.ai server
    if (window.location.hostname === 'marcus.decimer.ai') {
      // Direct API connection instead of proxy
      return 'https://api.marcus.decimer.ai';
    }

    // Check for environment variables
    if (process.env.VUE_APP_API_URL) {
      return process.env.VUE_APP_API_URL;
    }

    // Docker compose environment - frontend can reach backend directly
    if (process.env.NODE_ENV === 'production') {
      return 'http://backend:9000';
    }

    // Development fallback - always use localhost for development
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
    if (process.env.VUE_APP_API_URL) {
      const apiUrl = process.env.VUE_APP_API_URL;
      return apiUrl.replace(/^https?:/, 'ws:');
    }

    // Docker compose environment - frontend can reach backend directly
    if (process.env.NODE_ENV === 'production') {
      return 'ws://backend:9000';
    }

    // Development fallback - always use localhost for development
    return 'ws://localhost:9000';
  }
}

// Create and export singleton instance
const sessionService = new SessionService();

export default sessionService;
