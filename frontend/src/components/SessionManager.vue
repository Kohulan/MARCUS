<template>
  <div class="session-manager" :class="{ 'session-active': isActive }">
    <!-- Loading Screen -->
    <div v-if="isInitializing" class="loading-screen">
      <div class="loading-content">
        <div class="loading-spinner"></div>
        <h2>Initializing MARCUS...</h2>
        <p>Checking availability...</p>
      </div>
    </div>

    <!-- Queue/Waiting Screen -->
    <div v-else-if="isWaiting" class="waiting-screen">
      <div class="waiting-content">
        <!-- Clean Header -->
        <div class="header-section">
          <div class="marcus-logo">
            <span class="marcus-text">MARCUS</span>
          </div>
          <h1 class="main-title">Almost Ready</h1>
          <p class="subtitle">We limit concurrent users to ensure optimal performance for everyone.</p>
        </div>

        <!-- Simple Stats -->
        <div class="stats-section">
          <div class="stat-item">
            <div class="stat-number">{{ queuePosition }}</div>
            <div class="stat-label">Your Position</div>
          </div>
          <div class="stat-item">
            <div class="stat-number">{{ activeUsers }}/3</div>
            <div class="stat-label">Active Users</div>
          </div>
          <div class="stat-item">
            <div class="stat-number">{{ formatTime(estimatedWaitTime) }}</div>
            <div class="stat-label">Est. Wait Time</div>
          </div>
        </div>
        
        <!-- Simple Progress Bar -->
        <div class="progress-section">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: progressPercentage + '%' }"></div>
          </div>
          <div class="progress-text">{{ progressPercentage }}% complete</div>
        </div>

        <!-- Clean Action Buttons -->
        <div class="action-section">
          <button 
            @click="refreshStatus" 
            class="btn btn-secondary"
            :disabled="isRefreshing"
          >
            <span v-if="isRefreshing">Refreshing...</span>
            <span v-else>Refresh Status</span>
          </button>

          <button @click="leaveQueue" class="btn btn-outline">
            Leave Queue
          </button>
        </div>
      </div>
    </div>

    <!-- Connection Error -->
    <div v-else-if="hasConnectionError" class="error-screen">
      <div class="error-content">
        <div class="error-icon">⚠️</div>
        <h1>Connection Error</h1>
        <p>Unable to connect to MARCUS services.</p>
        <button @click="retryConnection" class="btn btn-primary">
          Retry Connection
        </button>
      </div>
    </div>

    <!-- Active Session - Show main app -->
    <div v-else-if="isActive" class="active-session">
      <div class="session-indicator">
        <span class="status-dot"></span>
        <span>MARCUS Active</span>
        <span class="session-timer">{{ formatTime(sessionDuration) }}</span>
      </div>
      <!-- Main app content goes here -->
      <slot name="main-content"></slot>
    </div>
  </div>
</template>

<script>
import sessionService from '@/services/sessionService';

export default {
  name: 'SessionManager',
  data() {
    return {
      // UI states
      isInitializing: true,
      isActive: false,
      isWaiting: false,
      hasConnectionError: false,
      isRefreshing: false,

      
      // Session data
      sessionStatus: null,
      queueStatus: null,
      queuePosition: 0,
      activeUsers: 0,
      estimatedWaitTime: 0,
      sessionStartTime: null,
      
      // UI state
      connectionRetries: 0,
      maxRetries: 3
    };
  },
  
  computed: {
    progressPercentage() {
      if (!this.queuePosition || this.queuePosition <= 0) return 100;
      const maxPosition = 10; // Assume max queue length for progress calculation
      const progress = Math.max(0, (maxPosition - this.queuePosition) / maxPosition * 100);
      return Math.round(progress);
    },
    
    sessionDuration() {
      if (!this.sessionStartTime) return 0;
      return Math.floor((Date.now() - this.sessionStartTime) / 1000);
    }
  },
  
  async mounted() {
    this.setupEventListeners();
    await this.initializeSession();
    
    // Check for page reload and clear any stale session data
    this.handlePageReload();
  },
  
  beforeUnmount() {
    this.cleanup();
  },
  
  methods: {
    setupEventListeners() {
      // Session service events
      sessionService.on('connected', this.onConnected);
      sessionService.on('disconnected', this.onDisconnected);
      sessionService.on('statusUpdate', this.onStatusUpdate);
      sessionService.on('queueUpdate', this.onQueueUpdate);
      sessionService.on('error', this.onError);
      sessionService.on('reconnectFailed', this.onReconnectFailed);
      sessionService.on('sessionExpired', this.onSessionExpired);
      
      // Browser events
      window.addEventListener('beforeunload', this.handleBeforeUnload);
      window.addEventListener('visibilitychange', this.handleVisibilityChange);
    },
    
    async initializeSession() {
      try {
        this.isInitializing = true;
        this.hasConnectionError = false;
        
        // Create session
        const result = await sessionService.createSession();
        
        this.updateSessionState(result.session, result.queue_status);
        
      } catch (error) {
        console.error('Failed to initialize session:', error);
        this.hasConnectionError = true;
      } finally {
        this.isInitializing = false;
      }
    },
    
    updateSessionState(sessionStatus, queueStatus) {
      this.sessionStatus = sessionStatus;
      this.queueStatus = queueStatus;
      
      if (sessionStatus.status === 'active') {
        this.isActive = true;
        this.isWaiting = false;
        this.sessionStartTime = Date.now();
      } else if (sessionStatus.status === 'waiting') {
        this.isActive = false;
        this.isWaiting = true;
        this.queuePosition = sessionStatus.queue_position || 0;
        this.estimatedWaitTime = sessionStatus.estimated_wait_time || 0;
      }
      
      if (queueStatus) {
        this.activeUsers = queueStatus.active_sessions || 0;
      }
    },
    
    async refreshStatus() {
      if (this.isRefreshing) return;
      
      try {
        this.isRefreshing = true;
        // Only try to refresh if we have an active session
        if (!sessionService.isActive()) {
          console.log('No active session for status refresh, skipping');
          return;
        }
        
        const result = await sessionService.getSessionStatus();
        
        if (result.success) {
          this.updateSessionState(result.session_status, result.queue_status);
        }
      } catch (error) {
        console.error('Failed to refresh status:', error);
        // Don't emit error for "No active session" as this is expected during reinitialization
        if (!error.message.includes('No active session')) {
          this.$emit('error', 'Failed to refresh status');
        }
      } finally {
        this.isRefreshing = false;
      }
    },
    
    async leaveQueue() {
      try {
        const result = await sessionService.endSession();
        console.log('Leave queue result:', result);
        
        // Close the tab/window
        if (window.opener) {
          // If opened by another window, close this window
          window.close();
        } else {
          // Try to close the tab
          window.close();
          
          // If close doesn't work (some browsers prevent it), 
          // redirect to a goodbye page or show a message
          setTimeout(() => {
            if (!window.closed) {
              // Fallback: navigate to about:blank or show message
              document.body.innerHTML = `
                <div style="
                  display: flex; 
                  flex-direction: column; 
                  align-items: center; 
                  justify-content: center; 
                  height: 100vh; 
                  font-family: system-ui, -apple-system, sans-serif;
                  text-align: center;
                  background: #f8fafc;
                  color: #334155;
                ">
                  <h1 style="font-size: 2rem; margin-bottom: 1rem; color: #0f172a;">You've left the queue</h1>
                  <p style="font-size: 1.1rem; margin-bottom: 2rem; color: #64748b;">You can safely close this tab now.</p>
                  <button onclick="window.close()" style="
                    padding: 0.75rem 1.5rem;
                    background: #3b82f6;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 1rem;
                    cursor: pointer;
                    transition: all 0.2s ease;
                  " onmouseover="this.style.background='#2563eb'" onmouseout="this.style.background='#3b82f6'">
                    Close Tab
                  </button>
                </div>
              `;
            }
          }, 100);
        }
        
        this.$emit('session-ended');
      } catch (error) {
        console.error('Failed to leave queue:', error);
        // Still try to close the tab even if there was an error
        window.close();
      }
    },
    

    async retryConnection() {
      if (this.connectionRetries >= this.maxRetries) {
        this.$emit('max-retries-reached');
        return;
      }
      
      this.connectionRetries++;
      await this.initializeSession();
    },
    
    onSessionExpired() {
      console.log('Session expired, reinitializing...');
      this.isActive = false;
      this.isWaiting = false;
      this.sessionStatus = null;
      this.queueStatus = null;
      
      // Automatically try to create a new session
      this.initializeSession();
    },
    
    // Event handlers
    onConnected() {
      console.log('Session WebSocket connected - SessionId:', sessionService.getSessionId());
      this.hasConnectionError = false;
      this.connectionRetries = 0;
    },
    
    onDisconnected() {
      console.log('Session WebSocket disconnected - SessionId:', sessionService.getSessionId());
    },
    
    onStatusUpdate(data) {
      this.updateSessionState(data.sessionStatus, data.queueStatus);
    },
    
    onQueueUpdate(data) {
      this.updateSessionState(data.sessionStatus, data.queueStatus);
      
      // Show notification if promoted to active
      if (data.sessionStatus.status === 'active' && this.isWaiting) {
        this.$emit('session-activated');
      }
    },
    
    onError(error) {
      console.error('Session service error:', error);
      this.hasConnectionError = true;
    },
    
    onReconnectFailed() {
      this.hasConnectionError = true;
      this.$emit('connection-failed');
    },
    
    handleBeforeUnload() {
      sessionService.endSession();
    },
    
    handleVisibilityChange() {
      if (document.visibilityState === 'hidden') {
        // Page is hidden, reduce activity
      } else if (document.visibilityState === 'visible') {
        // Page is visible again, refresh status
        this.refreshStatus();
      }
    },
    
    handlePageReload() {
      // Clear any stale session data on page reload
      const isPageReload = performance.getEntriesByType('navigation')[0]?.type === 'reload';
      
      if (isPageReload) {
        console.log('Page reload detected, will reinitialize session');
        // Don't cleanup immediately - let the session recovery process handle it
        // If the stored session is invalid, it will be cleared during createSession()
      }
    },
    
    cleanup() {
      // Remove event listeners
      sessionService.off('connected', this.onConnected);
      sessionService.off('disconnected', this.onDisconnected);
      sessionService.off('statusUpdate', this.onStatusUpdate);
      sessionService.off('queueUpdate', this.onQueueUpdate);
      sessionService.off('error', this.onError);
      sessionService.off('reconnectFailed', this.onReconnectFailed);
      sessionService.off('sessionExpired', this.onSessionExpired);
      
      window.removeEventListener('beforeunload', this.handleBeforeUnload);
      window.removeEventListener('visibilitychange', this.handleVisibilityChange);
      
      // End session
      sessionService.endSession();
    },
    
    formatTime(seconds) {
      if (seconds < 60) {
        return `${seconds}s`;
      } else if (seconds < 3600) {
        const minutes = Math.floor(seconds / 60);
        return `${minutes}m`;
      } else {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${minutes}m`;
      }
    }
  }
};
</script>

<style scoped>
/* Import MARCUS design system variables */
@import '@/assets/styles/_variables.scss';

.session-manager {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg, #f8fafc);
  font-family: var(--font-family, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif);
  z-index: 9999;
}

/* Remove background when session is active */
.session-manager.session-active {
  position: relative;
  background: none;
  display: block;
  height: auto;
  z-index: auto;
}

/* Screen Content Containers */
.loading-screen,
.waiting-screen,
.error-screen {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  text-align: center;
  color: var(--color-text, #1f2937);
  padding: 2rem;
  box-sizing: border-box;
}

.loading-content,
.waiting-content,
.error-content {
  background: var(--color-card-bg, #ffffff);
  border-radius: 16px;
  padding: 3rem 2rem;
  box-shadow: var(--shadow-lg, 0 25px 50px -12px rgba(0, 0, 0, 0.25));
  border: 1px solid var(--color-border, #e5e7eb);
  max-width: 500px;
  width: 100%;
  margin: auto;
}

/* Header Section */
.header-section {
  margin-bottom: 2.5rem;
}

.marcus-logo {
  margin-bottom: 1.5rem;
}

.marcus-text {
  font-family: 'GmarketSansLight', var(--font-family, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif);
  font-size: 2rem;
  font-weight: 700;
  color: var(--color-primary, #3b82f6);
  letter-spacing: 1px;
}

.main-title {
  font-size: 2rem;
  font-weight: 700;
  color: var(--color-heading, #1f2937);
  margin-bottom: 0.75rem;
}

.subtitle {
  font-size: 1rem;
  color: var(--color-text-secondary, #6b7280);
  line-height: 1.6;
  margin: 0;
}

/* Stats Section */
.stats-section {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin-bottom: 2rem;
}

.stat-item {
  background: var(--color-panel-bg);
  border-radius: 12px;
  padding: 1.5rem 1rem;
  border: 1px solid var(--color-border);
  text-align: center;
  transition: all 0.2s ease;
}

.stat-item:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--color-primary);
}

.stat-number {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--color-primary);
  margin-bottom: 0.25rem;
  line-height: 1;
}

.stat-label {
  font-size: 0.85rem;
  color: var(--color-text-secondary);
  font-weight: 500;
}

/* Progress Section */
.progress-section {
  margin-bottom: 2rem;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--color-border);
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: 0.75rem;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary), var(--color-secondary));
  transition: width 0.8s ease;
  border-radius: 6px;
}

.progress-text {
  font-size: 0.9rem;
  color: var(--color-text-secondary);
  font-weight: 500;
}

/* Action Section */
.action-section {
  display: flex;
  gap: 1rem;
  justify-content: center;
}

.btn {
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  border: none;
  min-width: 120px;
}

.btn-primary {
  background: var(--color-primary);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-dark);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.btn-secondary {
  background: var(--color-secondary);
  color: white;
}

.btn-secondary:hover:not(:disabled) {
  background: var(--color-secondary-dark);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.btn-outline {
  background: transparent;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
}

.btn-outline:hover:not(:disabled) {
  background: var(--color-hover-bg);
  border-color: var(--color-border-hover);
  color: var(--color-text);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none !important;
}

/* Loading Spinner */
.loading-spinner {
  width: 40px;
  height: 40px;
  margin: 0 auto 1.5rem;
  border: 3px solid var(--color-border);
  border-top: 3px solid var(--color-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.loading-content h2 {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--color-heading);
  margin-bottom: 0.5rem;
}

.loading-content p {
  font-size: 1rem;
  color: var(--color-text-secondary);
  margin: 0;
}

/* Error Screen */
.error-content {
  text-align: center;
}

.error-icon {
  font-size: 3rem;
  margin-bottom: 1.5rem;
}

.error-content h1 {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--color-error);
  margin-bottom: 0.75rem;
}

.error-content p {
  font-size: 1rem;
  color: var(--color-text-secondary);
  margin-bottom: 1.5rem;
  line-height: 1.6;
}

/* Session Indicator */
.session-indicator {
  position: fixed;
  top: 20px;
  right: 20px;
  background: var(--color-card-bg);
  color: var(--color-text);
  padding: 0.75rem 1rem;
  border-radius: 12px;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.85rem;
  font-weight: 500;
  z-index: 1000;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--color-border);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-success);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.session-timer {
  color: var(--color-text-secondary);
  font-size: 0.8rem;
}

.active-session {
  width: 100%;
  height: 100%;
}

/* Responsive Design */
@media (max-width: 768px) {
  .session-manager {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100% !important;
    height: 100vh !important;
    height: 100dvh; /* Dynamic viewport height for mobile */
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    z-index: 9999 !important;
  }

  .waiting-content,
  .loading-content,
  .error-content {
    padding: 2rem 1.5rem;
    margin: 1rem;
    max-width: calc(100vw - 2rem);
  }

  .main-title {
    font-size: 1.75rem;
  }

  .marcus-text {
    font-size: 1.75rem;
  }

  .stats-section {
    grid-template-columns: 1fr;
    gap: 0.75rem;
  }

  .stat-item {
    padding: 1.25rem 1rem;
  }

  .action-section {
    flex-direction: column;
    align-items: center;
  }

  .btn {
    width: 100%;
    max-width: 200px;
  }

  .session-indicator {
    position: relative;
    top: auto;
    right: auto;
    margin: 1rem;
    justify-content: center;
  }
}

@media (max-width: 480px) {
  .session-manager {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100% !important;
    height: 100vh !important;
    height: 100dvh; /* Dynamic viewport height for mobile */
  }

  .waiting-content,
  .loading-content,
  .error-content {
    padding: 1.5rem 1rem;
    margin: 0.5rem;
    max-width: calc(100vw - 1rem);
  }

  .main-title {
    font-size: 1.5rem;
  }

  .marcus-text {
    font-size: 1.5rem;
  }

  .stats-section {
    gap: 0.5rem;
    margin-bottom: 1.5rem;
  }

  .stat-item {
    padding: 1rem;
  }

  .stat-number {
    font-size: 1.5rem;
  }
}
</style>