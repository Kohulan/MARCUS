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

        <!-- While You Wait Section -->
        <div class="while-wait-section">
          <h3 class="while-wait-title">While you wait, why don't you check out our other services?</h3>
          <div class="service-buttons">
            <a 
              href="https://coconut.naturalproducts.net" 
              target="_blank" 
              rel="noopener noreferrer"
              class="service-btn coconut-btn"
              title="COCONUT - Collection of Open Natural Products Database"
              data-tooltip="Explore the world's largest collection of natural products with detailed molecular information and biological activities"
            >
              <img src="@/assets/coconut-logo.svg" alt="COCONUT" class="service-logo">
              <span class="service-name">COCONUT</span>
            </a>
            <a 
              href="https://decimer.ai" 
              target="_blank" 
              rel="noopener noreferrer"
              class="service-btn decimer-btn"
              title="DECIMER - Deep Learning for Chemical Image Recognition"
              data-tooltip="Advanced AI-powered tool for extracting chemical structures from images and documents with high accuracy"
            >
              <img src="@/assets/decimer-logo.png" alt="DECIMER" class="service-logo">
              <span class="service-name">DECIMER</span>
            </a>
          </div>
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
      isInitializing: true,
      isWaiting: false,
      isActive: false,
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
        const result = await sessionService.getSessionStatus();
        
        if (result.success) {
          this.updateSessionState(result.session_status, result.queue_status);
        }
      } catch (error) {
        console.error('Failed to refresh status:', error);
        this.$emit('error', 'Failed to refresh status');
      } finally {
        this.isRefreshing = false;
      }
    },
    
    async leaveQueue() {
      try {
        // End the session first
        await sessionService.endSession();
        this.$emit('session-ended');
        
        // Immediately close the browser tab
        window.close();
      } catch (error) {
        console.error('Failed to leave queue:', error);
        // Even if there's an error, still close the tab
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
    
    // Event handlers
    onConnected() {
      console.log('Session WebSocket connected');
      this.hasConnectionError = false;
      this.connectionRetries = 0;
    },
    
    onDisconnected() {
      console.log('Session WebSocket disconnected');
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
    
    cleanup() {
      // Remove event listeners
      sessionService.off('connected', this.onConnected);
      sessionService.off('disconnected', this.onDisconnected);
      sessionService.off('statusUpdate', this.onStatusUpdate);
      sessionService.off('queueUpdate', this.onQueueUpdate);
      sessionService.off('error', this.onError);
      sessionService.off('reconnectFailed', this.onReconnectFailed);
      
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
  width: 100%;
  min-height: calc(100vh - 120px); /* Account for header/footer space */
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg);
  font-family: var(--font-family);
  padding: 2rem 0;
}

/* Remove background when session is active */
.session-manager.session-active {
  background: none;
  display: block;
  height: auto;
  min-height: auto;
  padding: 0;
}

/* Screen Content Containers */
.loading-screen,
.waiting-screen,
.error-screen {
  text-align: center;
  color: var(--color-text);
  max-width: 500px;
  width: 100%;
  padding: 2rem;
}

.loading-content,
.waiting-content,
.error-content {
  background: var(--color-card-bg);
  border-radius: 16px;
  padding: 3rem 2rem;
  box-shadow: var(--shadow-lg);
  border: 1px solid var(--color-border);
}

/* Header Section */
.header-section {
  margin-bottom: 2.5rem;
}

.marcus-logo {
  margin-bottom: 1.5rem;
}

.marcus-text {
  font-family: 'GmarketSansLight', var(--font-family);
  font-size: 2rem;
  font-weight: 700;
  color: var(--color-primary);
  letter-spacing: 1px;
}

.main-title {
  font-size: 2rem;
  font-weight: 700;
  color: var(--color-heading);
  margin-bottom: 0.75rem;
}

.subtitle {
  font-size: 1rem;
  color: var(--color-text-secondary);
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

/* While You Wait Section */
.while-wait-section {
  margin-bottom: 2.5rem;
}

.while-wait-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--color-heading);
  margin-bottom: 1.5rem;
  text-align: center;
}

.service-buttons {
  display: flex;
  gap: 1rem;
  justify-content: center;
}

.service-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 0.875rem 1.25rem;
  border-radius: 14px;
  text-decoration: none;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  border: 2px solid transparent;
  min-width: 140px;
  cursor: pointer;
  backdrop-filter: blur(10px);
  overflow: hidden;
}

.service-btn::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
  transition: left 0.5s ease;
}

.service-btn:hover::before {
  left: 100%;
}

.coconut-btn {
  background: linear-gradient(135deg, #E8F5E8, #F0FFF0);
  color: #2E7D32;
  border-color: #A5D6A7;
  box-shadow: 0 4px 15px rgba(76, 175, 80, 0.1);
}

.coconut-btn:hover {
  background: linear-gradient(135deg, #C8E6C9, #E8F5E8);
  border-color: #66BB6A;
  transform: translateY(-3px) scale(1.02);
  box-shadow: 0 12px 30px rgba(76, 175, 80, 0.25);
}

.decimer-btn {
  background: linear-gradient(135deg, #E3F2FD, #F0F8FF);
  color: #1565C0;
  border-color: #90CAF9;
  box-shadow: 0 4px 15px rgba(33, 150, 243, 0.1);
}

.decimer-btn:hover {
  background: linear-gradient(135deg, #BBDEFB, #E3F2FD);
  border-color: #42A5F5;
  transform: translateY(-3px) scale(1.02);
  box-shadow: 0 12px 30px rgba(33, 150, 243, 0.25);
}

.service-logo {
  width: 30px;
  height: 30px;
  object-fit: contain;
  flex-shrink: 0;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
  transition: transform 0.3s ease;
}

.service-btn:hover .service-logo {
  transform: scale(1.1) rotate(5deg);
}

.service-name {
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

/* Advanced Tooltip Styling */
.service-btn[data-tooltip] {
  position: relative;
}

.service-btn[data-tooltip]::after {
  content: attr(data-tooltip);
  position: absolute;
  bottom: 120%;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.9);
  color: white;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 0.85rem;
  font-weight: 500;
  line-height: 1.4;
  white-space: normal;
  width: 280px;
  text-align: center;
  opacity: 0;
  visibility: hidden;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 1000;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.service-btn[data-tooltip]::before {
  content: '';
  position: absolute;
  bottom: 110%;
  left: 50%;
  transform: translateX(-50%);
  border: 8px solid transparent;
  border-top-color: rgba(0, 0, 0, 0.9);
  opacity: 0;
  visibility: hidden;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 1001;
}

.service-btn[data-tooltip]:hover::after,
.service-btn[data-tooltip]:hover::before {
  opacity: 1;
  visibility: visible;
  transform: translateX(-50%) translateY(-8px);
}

.service-btn[data-tooltip]:hover::before {
  transform: translateX(-50%) translateY(-4px);
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
  .waiting-content,
  .loading-content,
  .error-content {
    padding: 2rem 1.5rem;
    margin: 1rem;
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

  .service-buttons {
    flex-direction: column;
    align-items: center;
    gap: 1.25rem;
  }

  .service-btn {
    width: 100%;
    max-width: 240px;
    min-width: auto;
  }

  .service-btn[data-tooltip]::after {
    width: 250px;
    font-size: 0.8rem;
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
  .waiting-content,
  .loading-content,
  .error-content {
    padding: 1.5rem 1rem;
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

  .service-btn {
    padding: 0.75rem 1rem;
    min-width: auto;
  }

  .service-logo {
    width: 30px;
    height: 30px;
  }

  .service-name {
    font-size: 1rem;
  }

  .service-btn[data-tooltip]::after {
    width: 220px;
    font-size: 0.75rem;
    padding: 10px 12px;
  }

  .while-wait-title {
    font-size: 1rem;
  }
}
</style>
