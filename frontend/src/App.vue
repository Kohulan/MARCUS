<template>
  <div class="app-container">
    <!-- Session Manager - handles user queue and concurrency -->
    <session-manager
      @session-activated="onSessionActivated"
      @session-ended="onSessionEnded"
      @connection-failed="onConnectionFailed"
      @max-retries-reached="onMaxRetriesReached"
    >
      <template #main-content>
        <!-- Original App Content -->
        <!-- Cinematic Loading Masterpiece -->
        <loading-screen 
          v-if="!appLoaded" 
          @loading-complete="finishLoading" 
        />
        
        <!-- App Content - only visible after loading -->
        <template v-if="appLoaded">
          <AppHeader />
          
          <main class="main-content" v-show="!isDisclaimerVisible && !isFeaturesVisible && !isAboutVisible && !isPrivacyPolicyVisible">
            <HomeView />
          </main>
          
          <!-- Disclaimer page - shown when isDisclaimerVisible is true -->
          <div class="disclaimer-wrapper" v-if="isDisclaimerVisible">
            <disclaimer-page 
              @close="hideDisclaimer" 
            />
          </div>
          
          <!-- Features section - shown when isFeaturesVisible is true -->
          <div class="features-wrapper" v-if="isFeaturesVisible">
            <features-section 
              :showCloseButton="true"
              @close="hideFeatures" 
            />
          </div>
          
          <!-- About page - shown when isAboutVisible is true -->
          <div class="about-wrapper" v-if="isAboutVisible">
            <about-page 
              :showCloseButton="true"
              @close="hideAbout" 
            />
          </div>
          
          <!-- Privacy Policy page - shown when isPrivacyPolicyVisible is true -->
          <div class="privacy-policy-wrapper" v-if="isPrivacyPolicyVisible">
            <privacy-policy-page 
              @close="hidePrivacyPolicy" 
            />
          </div>
          
          <AppFooter />
        </template>
      </template>
    </session-manager>
    
    <!-- Notifications -->
    <div class="notifications-container">
      <transition-group name="notification">
        <div 
          v-for="notification in notifications" 
          :key="notification.id"
          class="notification"
          :class="'notification-' + notification.type"
        >
          <div class="notification-content">
            {{ notification.message }}
          </div>
          <button @click="removeNotification(notification.id)" class="notification-close">
            <vue-feather type="x" class="icon"></vue-feather>
          </button>
        </div>
      </transition-group>
    </div>
  </div>
</template>

<script>
import { mapState, mapActions } from 'vuex'
import AppHeader from './components/common/AppHeader.vue'
import AppFooter from './components/common/AppFooter.vue'
import HomeView from './views/HomeView.vue'
import DisclaimerPage from './views/DisclaimerPage.vue'
import FeaturesSection from './views/FeaturesSection.vue'
import AboutPage from './views/AboutPage.vue'
import PrivacyPolicyPage from './views/PrivacyPolicyPage.vue'
import LoadingScreen from './components/common/LoadingScreen.vue'
import SessionManager from './components/SessionManager.vue'

export default {
  name: 'App',
  components: {
    AppHeader,
    AppFooter,
    HomeView,
    DisclaimerPage,
    FeaturesSection,
    AboutPage,
    PrivacyPolicyPage,
    LoadingScreen,
    SessionManager
  },
  
  data() {
    return {
      appLoaded: false
    }
  },
  
  computed: {
    ...mapState({
      isDarkMode: state => state.theme.isDarkMode,
      notifications: state => state.notifications,
      isDisclaimerVisible: state => state.isDisclaimerVisible,
      isFeaturesVisible: state => state.isFeaturesVisible,
      isAboutVisible: state => state.isAboutVisible,
      isPrivacyPolicyVisible: state => state.isPrivacyPolicyVisible
    })
  },
  
  methods: {
    ...mapActions({
      removeNotification: 'removeNotification',
      hideDisclaimer: 'hideDisclaimer',
      hideFeatures: 'hideFeatures',
      hideAbout: 'hideAbout',
      hidePrivacyPolicy: 'hidePrivacyPolicy'
    }),
    
    finishLoading() {
      this.appLoaded = true;
    },
    
    // Session Manager Event Handlers
    onSessionActivated() {
      console.log('Session activated - user can now use MARCUS');
      // You can add notifications or analytics here
    },
    
    onSessionEnded() {
      console.log('Session ended');
      // Handle session cleanup if needed
    },
    
    onConnectionFailed() {
      console.error('Connection to session service failed');
      // You could show a fallback interface or error message
    },
    
    onMaxRetriesReached() {
      console.error('Maximum connection retries reached');
      // Handle complete failure to connect
    }
  }
}
</script>

<style lang="scss">
@use './assets/styles/main.scss' as *;

.app-container {
  display: flex;
  flex-direction: column;
  height: 100vh; /* Changed from min-height to exact height */
  background: var(--color-bg);
  color: var(--color-text);
  transition: background-color 0.3s ease, color 0.3s ease;
}

.main-content {
  flex: 1;
  width: 100%;
  max-width: 100%;
  margin: 0 auto;
  padding: 0.25rem 0.5rem; /* Reduced top/bottom padding from 0.5rem to 0.25rem */
  overflow-y: auto; /* Allow scrolling within the content if needed */
}

@media (min-width: 1200px) {
  .main-content {
    padding: 0.5rem 2rem; /* Reduced top/bottom padding from 2rem to 0.5rem, kept horizontal at 2rem */
  }
}

/* Notifications */
.notifications-container {
  position: fixed;
  bottom: 1rem;
  right: 1rem;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-width: 350px;
}

.notification {
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  animation: slideIn 0.3s ease forwards;
  
  &-success {
    background-color: #10b981;
    color: white;
  }
  
  &-error {
    background-color: #ef4444;
    color: white;
  }
  
  &-info {
    background-color: #3b82f6;
    color: white;
  }
  
  &-warning {
    background-color: #f59e0b;
    color: white;
  }
  
  &-content {
    flex: 1;
  }
  
  &-close {
    background: transparent;
    border: none;
    color: white;
    cursor: pointer;
    opacity: 0.7;
    transition: opacity 0.2s;
    
    &:hover {
      opacity: 1;
    }
    
    .icon {
      width: 16px;
      height: 16px;
    }
  }
}

/* Animations */
.notification-enter-active, .notification-leave-active {
  transition: all 0.3s;
}

.notification-enter-from, .notification-leave-to {
  opacity: 0;
  transform: translateX(30px);
}

// Add styles for the info icon and tooltip
.info-icon-blue {
  color: #3b82f6 !important;
  cursor: help;
  transition: transform 0.2s ease;
  
  &:hover {
    transform: scale(1.1);
  }
}

// Enhanced tooltip styling
.custom-tooltip-theme {
  background-color: #f8fafc !important;
  color: #334155 !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 6px !important;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
  padding: 10px 14px !important;
  font-size: 0.875rem !important;
  line-height: 1.5 !important;
  max-width: 300px !important;
  z-index: 1500 !important;
  
  // Dark mode styling
  @media (prefers-color-scheme: dark) {
    background-color: #1e293b !important;
    color: #f1f5f9 !important;
    border-color: #475569 !important;
  }
}

/* Features wrapper */
.features-wrapper {
  height: 100vh;
  width: 100%;
  overflow-y: auto; /* Enable vertical scrolling */
  position: relative;
}

/* About wrapper */
.about-wrapper {
  height: 100vh;
  width: 100%;
  overflow-y: auto; /* Enable vertical scrolling */
  position: relative;
}

/* Disclaimer wrapper */
.disclaimer-wrapper {
  height: 100vh;
  width: 100%;
  overflow-y: auto; /* Enable vertical scrolling */
  position: relative;
}

/* Privacy Policy wrapper */
.privacy-policy-wrapper {
  height: 100vh;
  width: 100%;
  overflow-y: auto; /* Enable vertical scrolling */
  position: relative;
}
</style>