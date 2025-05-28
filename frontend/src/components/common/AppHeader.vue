<template>
  <header class="app-header" :class="{ 'scrolled': isScrolled }">
    <div class="header-bg-glow"></div>
    <div class="floating-element"></div>

    <!-- Full width container matching footer -->
    <div class="header-content">
      <div class="header-main">

        <!-- Left Section: MARCUS Logo & Navigation -->
        <div class="left-section">
          <!-- MARCUS Logo -->
          <router-link to="/" class="logo" @click="homeNavigation">
            <div class="logo-img">
              <div class="logo-shine"></div>
              <img src="@/assets/logo.png" alt="MARKUS" />
            </div>
            <div class="logo-text">
              <h1><span class="marcus-text">MARCUS</span><span class="badge">Beta</span></h1>
            </div>
          </router-link>

          <!-- Prominent Navigation Buttons -->
          <nav class="header-nav">
            <a href="#features" class="nav-btn" @click.prevent="scrollToFeatures">
              <div class="btn-bg"></div>
              <vue-feather type="layers" class="nav-icon"></vue-feather>
              <span>Features</span>
            </a>
            <a href="#about" class="nav-btn" @click.prevent="showAbout">
              <div class="btn-bg"></div>
              <vue-feather type="info" class="nav-icon"></vue-feather>
              <span>About</span>
            </a>
            <a href="#" class="nav-btn" @click.prevent="toggleDisclaimer">
              <div class="btn-bg"></div>
              <vue-feather type="shield" class="nav-icon"></vue-feather>
              <span>Disclaimer</span>
            </a>
          </nav>
        </div>

        <!-- Right Section: Status, Theme & External Links -->
        <div class="right-section">
          <!-- Backend status indicator with animation and transition -->
          <transition name="fade-slide">
            <div v-if="!backendReady || showReadyMessage" class="backend-status-indicator" :class="{
              ready: backendReady,
              notready: !backendReady,
              'pulse-animation': !backendReady
            }" title="Backend status">
              <span class="status-dot"></span>
              <span class="status-text">{{ backendReady ? 'Backend ready' : 'Backend initializing' }}</span>
            </div>
          </transition>

          <button class="theme-toggle" @click="toggleTheme"
            :title="isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'" aria-label="Toggle dark mode">
            <div class="toggle-track">
              <div class="toggle-icons">
                <vue-feather type="sun" class="sun-icon" :class="{ 'active': !isDarkMode }"></vue-feather>
                <vue-feather type="moon" class="moon-icon" :class="{ 'active': isDarkMode }"></vue-feather>
              </div>
              <div class="toggle-thumb" :class="{ 'is-dark': isDarkMode }"></div>
            </div>
            <span class="toggle-label">{{ isDarkMode ? 'Dark' : 'Light' }}</span>
          </button>


        </div>
      </div>
    </div>

    <!-- Mobile menu toggle button (only visible on mobile) -->
    <button class="mobile-menu-toggle" aria-label="Toggle mobile menu" @click="toggleMobileMenu">
      <div class="hamburger-container">
        <div class="hamburger" :class="{ 'is-active': isMobileMenuOpen }">
          <span></span>
          <span></span>
          <span></span>
        </div>
        <span class="menu-label" v-if="!isMobileMenuOpen">Menu</span>
        <span class="menu-label" v-else>Close</span>
      </div>
    </button>

    <!-- Mobile menu backdrop overlay -->
    <transition name="fade">
      <div class="mobile-menu-backdrop" v-if="isMobileMenuOpen" @click="closeMobileMenu"></div>
    </transition>

    <!-- Improved mobile menu with slide animation -->
    <transition name="slide">
      <div class="mobile-menu" :class="{ 'is-open': isMobileMenuOpen }" v-if="isMobileMenuOpen">
        <div class="mobile-menu-header">
          <div class="logo-mini">
            <img src="@/assets/logo.png" alt="MARKUS" />
            <h2><span class="marcus-text">MARCUS</span><span class="badge">Beta</span></h2>
          </div>
          <button class="close-menu-btn" @click="closeMobileMenu">
            <vue-feather type="x" size="24"></vue-feather>
          </button>
        </div>

        <nav class="mobile-nav">
          <a href="#features" class="mobile-nav-link" @click="featuresAndCloseMenu">
            <vue-feather type="layers" class="mobile-nav-icon"></vue-feather>
            <span>Features</span>
          </a>
          <a href="#about" class="mobile-nav-link" @click="showAboutAndCloseMenu">
            <vue-feather type="info" class="mobile-nav-icon"></vue-feather>
            <span>About</span>
          </a>
          <a href="#help" class="mobile-nav-link" @click="closeMobileMenu">
            <vue-feather type="help-circle" class="mobile-nav-icon"></vue-feather>
            <span>Documentation</span>
          </a>
          <a href="#" class="mobile-nav-link" @click="showDisclaimerAndCloseMenu">
            <vue-feather type="shield" class="mobile-nav-icon"></vue-feather>
            <span>Disclaimer</span>
          </a>
          <router-link to="/" class="mobile-nav-link" @click="homeAndCloseMenu">
            <vue-feather type="home" class="mobile-nav-icon"></vue-feather>
            <span>Home</span>
          </router-link>
        </nav>

        <div class="mobile-menu-footer">
          <button class="theme-toggle-mobile" @click="toggleTheme">
            <vue-feather :type="isDarkMode ? 'moon' : 'sun'" class="theme-icon"></vue-feather>
            <span>{{ isDarkMode ? 'Dark Mode' : 'Light Mode' }}</span>
          </button>


        </div>
      </div>
    </transition>
  </header>
</template>

<script>
import { mapState, mapActions } from 'vuex'
import { checkBackendHealth } from '@/services/api.js'

export default {
  name: 'AppHeader',

  data() {
    return {
      isScrolled: false,
      isMobileMenuOpen: false,
      backendReady: false,
      backendCheckInterval: null,
      showReadyMessage: false,
      readyMessageTimeout: null
    }
  },

  computed: {
    ...mapState({
      isDarkMode: state => state.theme.isDarkMode,
      isFeaturesVisible: state => state.isFeaturesVisible,
      isDisclaimerVisible: state => state.isDisclaimerVisible,
      isAboutVisible: state => state.isAboutVisible
    })
  },

  methods: {
    ...mapActions({
      toggleDarkMode: 'theme/toggleDarkMode',
      toggleDisclaimer: 'toggleDisclaimer',
      showDisclaimer: 'showDisclaimer',
      hideDisclaimer: 'hideDisclaimer',
      showFeatures: 'showFeatures',
      hideFeatures: 'hideFeatures',
      showAbout: 'showAbout',
      hideAbout: 'hideAbout'
    }),

    // New method to handle logo navigation
    homeNavigation() {
      // Hide all modals when navigating home
      this.hideDisclaimer();
      this.hideFeatures();
      this.hideAbout();
    },

    toggleTheme() {
      this.toggleDarkMode()
    },

    toggleMobileMenu() {
      this.isMobileMenuOpen = !this.isMobileMenuOpen
      document.body.style.overflow = this.isMobileMenuOpen ? 'hidden' : ''
    },

    closeMobileMenu() {
      this.isMobileMenuOpen = false
      document.body.style.overflow = ''
    },

    showDisclaimerAndCloseMenu() {
      this.showDisclaimer();
      this.closeMobileMenu();
    },

    showAboutAndCloseMenu() {
      this.showAbout();
      this.closeMobileMenu();
    },

    homeAndCloseMenu() {
      this.hideDisclaimer();
      this.hideFeatures();
      this.hideAbout();
      this.closeMobileMenu();
    },

    // Methods for features section
    scrollToFeatures() {
      const featuresSection = document.getElementById('features')
      if (featuresSection) {
        // Hide disclaimer if it's showing
        this.hideDisclaimer();
        this.hideAbout();
        // Scroll to features section with smooth animation
        featuresSection.scrollIntoView({ behavior: 'smooth' })
      } else {
        // If features section doesn't exist, trigger showFeatures action
        this.showFeatures();
      }
    },

    featuresAndCloseMenu() {
      this.closeMobileMenu();
      // Small timeout to ensure menu is closed before scrolling
      setTimeout(() => {
        this.scrollToFeatures();
      }, 300);
    },

    handleScroll() {
      this.isScrolled = window.scrollY > 20
    },

    async pollBackendHealth() {
      const wasReady = this.backendReady;
      this.backendReady = await checkBackendHealth();

      // If backend just became ready, show the ready message for 5 seconds then hide it
      if (!wasReady && this.backendReady) {
        this.showReadyMessage = true;

        // Clear any existing timeout
        if (this.readyMessageTimeout) {
          clearTimeout(this.readyMessageTimeout);
        }

        // Set timeout to hide the message after 5 seconds
        this.readyMessageTimeout = setTimeout(() => {
          this.showReadyMessage = false;
        }, 5000);

        // Once backend is ready, we can check less frequently
        if (this.backendCheckInterval) {
          clearInterval(this.backendCheckInterval);
          this.backendCheckInterval = setInterval(this.pollBackendHealth, 30000); // Check every 30 seconds
        }
      }
    },
  },

  created() {
    // Initialize theme when component is created
    this.$store.dispatch('theme/initTheme')
  },

  mounted() {
    window.addEventListener('scroll', this.handleScroll)
    // Poll backend health every 3 seconds initially
    this.pollBackendHealth();
    this.backendCheckInterval = setInterval(this.pollBackendHealth, 3000);
  },

  beforeUnmount() {
    window.removeEventListener('scroll', this.handleScroll)
    if (this.backendCheckInterval) clearInterval(this.backendCheckInterval);
    if (this.readyMessageTimeout) clearTimeout(this.readyMessageTimeout);
  }
}
</script>

<style lang="scss" scoped>
/* Header Variables - Light Theme (Default) - Navy Blue Color Scheme */
.app-header {
  /* Primary colors - Navy Blue Palette */
  --header-primary: #1e3a8a;
  /* Navy Blue */
  --header-primary-rgb: 30, 58, 138;
  --header-secondary: #3b82f6;
  /* Blue */
  --header-accent: #60a5fa;
  /* Light Blue */
  --header-primary-light: rgba(30, 58, 138, 0.15);
  --header-primary-border: rgba(30, 58, 138, 0.2);

  /* Text colors */
  --header-text-heading: #0f172a;
  /* Dark Navy for headings */
  --header-text-body: #1e40af;
  /* Blue for body text */
  --header-text-muted: #3b82f6;
  /* Medium Blue for muted text */
  --header-text-light: #60a5fa;
  /* Light Blue for secondary text */

  /* Enhanced gradients and effects - Blue Spectrum */
  --header-primary-gradient: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 50%, #60a5fa 100%);
  --header-secondary-gradient: linear-gradient(135deg, #1e40af 0%, #3b82f6 50%, #93c5fd 100%);
  --header-primary-shadow: rgba(30, 58, 138, 0.3);
  --header-glow-effect: 0 0 20px rgba(30, 58, 138, 0.2);
  --header-bg: rgba(255, 255, 255, 0.95);
  --header-card-bg: white;
  --header-card-border: #dbeafe;
  /* Light blue border */
}

/* Dark Mode Header Variables - Navy Blue Dark Theme */
[data-theme="dark"] .app-header {
  --header-primary: #60a5fa;
  /* Light Blue for dark mode */
  --header-primary-rgb: 96, 165, 250;
  --header-secondary: #93c5fd;
  /* Lighter Blue */
  --header-accent: #bfdbfe;
  /* Very Light Blue */
  --header-primary-light: rgba(96, 165, 250, 0.15);
  --header-primary-border: rgba(96, 165, 250, 0.2);

  /* Text colors - for dark mode */
  --header-text-heading: #f1f5f9;
  /* Light text for headings */
  --header-text-body: #e2e8f0;
  /* Light text for body */
  --header-text-muted: #cbd5e1;
  /* Muted light text */
  --header-text-light: #94a3b8;
  /* Secondary light text */

  /* Dark mode specific backgrounds */
  --header-bg: rgba(15, 23, 42, 0.95);
  /* Dark navy background */
  --header-card-bg: #1e293b;
  /* Dark blue card background */
  --header-card-border: #334155;
  /* Dark blue border */

  /* Enhanced dark mode gradients - Blue Spectrum */
  --header-primary-gradient: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 50%, #60a5fa 100%);
  --header-secondary-gradient: linear-gradient(135deg, #374151 0%, #4b5563 50%, #6b7280 100%);
  --header-glow-effect: 0 0 25px rgba(96, 165, 250, 0.3);
}

/* Enhanced Keyframe Animations */
@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }

  100% {
    transform: translateX(100%);
  }
}

@keyframes float {

  0%,
  100% {
    transform: translateY(0px) rotate(0deg);
  }

  50% {
    transform: translateY(-10px) rotate(180deg);
  }
}

@keyframes float-reverse {

  0%,
  100% {
    transform: translateY(0px) rotate(0deg);
  }

  50% {
    transform: translateY(10px) rotate(-180deg);
  }
}

@keyframes pulse-glow {

  0%,
  100% {
    opacity: 0.6;
    transform: scale(1);
  }

  50% {
    opacity: 1;
    transform: scale(1.1);
  }
}

@keyframes gradient-shift {

  0%,
  100% {
    background-position: 0% 50%;
  }

  50% {
    background-position: 100% 50%;
  }
}

/* Main Header Styles */
.app-header {
  background: var(--header-bg);
  position: sticky;
  top: 0;
  z-index: var(--z-sticky, 100);
  overflow: hidden;
  min-height: 57px;
  border-bottom: 2px solid transparent;
  border-image: var(--header-primary-gradient) 1;
  backdrop-filter: blur(15px) saturate(180%);
  box-shadow:
    0 8px 32px rgba(30, 58, 138, 0.12),
    0 4px 16px rgba(59, 130, 246, 0.08),
    inset 0 -1px 0 rgba(255, 255, 255, 0.1);
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(90deg,
        transparent 0%,
        rgba(30, 58, 138, 0.05) 25%,
        rgba(59, 130, 246, 0.05) 50%,
        rgba(30, 58, 138, 0.05) 75%,
        transparent 100%);
    animation: shimmer 8s linear infinite;
    z-index: 0;
  }

  // Enhanced floating orbs
  &::after {
    content: '';
    position: absolute;
    bottom: -40px;
    left: -40px;
    width: 120px;
    height: 120px;
    border-radius: 50%;
    background: radial-gradient(circle,
        rgba(30, 58, 138, 0.15) 0%,
        rgba(59, 130, 246, 0.1) 50%,
        transparent 70%);
    opacity: 0.8;
    z-index: 0;
    animation: float 6s ease-in-out infinite;
  }

  // Additional floating elements
  .floating-element {
    position: absolute;
    width: 60px;
    height: 60px;
    border-radius: 50%;
    background: radial-gradient(circle,
        rgba(139, 69, 19, 0.12) 0%,
        transparent 70%);
    bottom: -20px;
    right: -20px;
    animation: float-reverse 8s ease-in-out infinite;
    z-index: 0;
    opacity: 0.6;

    &::before {
      content: '';
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: 30px;
      height: 30px;
      border-radius: 50%;
      background: rgba(255, 215, 0, 0.1);
      animation: pulse-glow 4s ease-in-out infinite;
    }
  }

  .header-bg-glow {
    position: absolute;
    bottom: -100px;
    left: 50%;
    transform: translateX(-50%);
    width: 80%;
    height: 150px;
    background: radial-gradient(circle at center,
        rgba(var(--header-primary-rgb), 0.15) 0%,
        rgba(var(--header-primary-rgb), 0.05) 40%,
        rgba(var(--header-primary-rgb), 0) 70%);
    z-index: -1;
    opacity: 0.8;
    filter: blur(40px);
    border-radius: 50%;
    pointer-events: none;
  }

  &.scrolled {
    box-shadow:
      0 10px 40px rgba(30, 58, 138, 0.15),
      0 5px 20px rgba(59, 130, 246, 0.1);

    .header-content {
      padding-top: 0.675rem;
      padding-bottom: 0.675rem;
    }

    .logo-img {
      transform: scale(0.9);
    }

    .logo h1 {
      font-size: 1.35rem;
    }
  }
}

/* Header Content Layout - Full Width like Footer */
.header-content {
  max-width: 100%;
  margin: 0;
  padding: 0.8rem 2rem;
  position: relative;
  z-index: 1;

  @media (max-width: 768px) {
    padding: 0.8rem;
  }
}

.header-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 2rem;
  width: 100%;

  @media (max-width: 1200px) {
    gap: 1rem;
  }

  @media (max-width: 768px) {
    flex-direction: column;
    gap: 1rem;
  }
}

/* Left Section: Logo & Navigation */
.left-section {
  display: flex;
  align-items: center;
  gap: 2rem;
  flex: 1;

  @media (max-width: 1024px) {
    gap: 1rem;
  }

  @media (max-width: 768px) {
    justify-content: center;
    flex-direction: column;
    gap: 1rem;
  }
}

/* Logo Styles */
.logo {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  position: relative;
  z-index: 2;
  text-decoration: none;
  flex-shrink: 0;

  .logo-img {
    position: relative;
    height: 48px;
    width: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 12px;
    overflow: hidden;
    transition: all 0.3s ease;

    &:hover {
      transform: translateY(-2px) scale(1.05);

      .logo-shine {
        transform: translateX(100%) rotate(25deg);
        opacity: 0.8;
      }

      img {
        transform: scale(1.1);
      }
    }

    .logo-shine {
      position: absolute;
      top: -50%;
      left: -100%;
      width: 60%;
      height: 200%;
      background: linear-gradient(90deg,
          rgba(255, 255, 255, 0) 0%,
          rgba(255, 255, 255, 0.5) 50%,
          rgba(255, 255, 255, 0) 100%);
      transform: translateX(-100%) rotate(25deg);
      opacity: 0;
      transition: transform 0.6s cubic-bezier(0.11, 0, 0.5, 0), opacity 0.3s ease;
      z-index: 1;
    }

    img {
      height: 36px;
      width: auto;
      position: relative;
      z-index: 1;
      filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
      transition: transform 0.3s ease;
    }
  }

  .logo-text {
    display: flex;
    flex-direction: column;

    h1 {
      font-size: 1.5rem;
      font-weight: 800;
      margin: 0;
      line-height: 1;
      letter-spacing: 0.5px;
      background: var(--header-primary-gradient);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
      display: flex;
      align-items: center;
      transition: font-size 0.3s ease;
      text-shadow: 0 1px 1px rgba(0, 0, 0, 0.05);

      .badge {
        font-size: 0.55rem;
        background: var(--header-primary-gradient);
        color: white;
        padding: 0.15rem 0.35rem;
        border-radius: 0.25rem;
        margin-left: 0.4rem;
        display: inline-block;
        font-weight: 700;
        box-shadow: 0 2px 4px rgba(var(--header-primary-rgb), 0.3);
        text-shadow: none;
        letter-spacing: 0;
      }
    }
  }
}

/* Prominent Navigation Buttons */
.header-nav {
  display: none;

  @media (min-width: 768px) {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .nav-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    border-radius: 8px;
    font-weight: 600;
    font-size: 0.875rem;
    text-decoration: none;
    color: var(--header-text-body);
    position: relative;
    overflow: hidden;
    transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
    border: 1px solid rgba(var(--header-primary-rgb), 0.1);
    background: rgba(var(--header-card-bg), 0.7);
    backdrop-filter: blur(8px);

    .btn-bg {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: var(--header-primary-gradient);
      opacity: 0;
      transition: opacity 0.3s ease;
      z-index: -1;
    }

    .nav-icon {
      width: 16px;
      height: 16px;
      color: var(--header-primary);
      transition: all 0.3s ease;
    }

    &:hover {
      transform: translateY(-2px);
      color: white;
      border-color: rgba(var(--header-primary-rgb), 0.3);
      box-shadow: 0 8px 25px rgba(var(--header-primary-rgb), 0.25);

      .btn-bg {
        opacity: 1;
      }

      .nav-icon {
        color: white;
        transform: scale(1.1);
      }
    }

    &:active {
      transform: translateY(0);
    }
  }
}

/* Right Section: Status, Theme & Links */
.right-section {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-shrink: 0;

  @media (max-width: 768px) {
    justify-content: center;
    flex-wrap: wrap;
  }
}

/* External Links Container */
.external-links {
  display: flex;
  align-items: center;
  gap: 0.75rem;

  @media (max-width: 768px) {
    gap: 0.5rem;
  }
}

/* Backend Status Indicator */
.backend-status-indicator {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
  font-weight: 500;
  margin-right: 0.5rem;
  border-radius: 20px;
  padding: 5px 12px;
  background: rgba(var(--header-card-bg), 0.8);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  border: 1px solid rgba(var(--header-primary-rgb), 0.1);
  transition: all 0.5s ease;

  &.pulse-animation .status-dot {
    animation: pulse 2s infinite;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #f59e0b;
    box-shadow: 0 0 4px rgba(0, 0, 0, 0.12);
    transition: background 0.3s;
  }

  &.ready {
    background: rgba(16, 185, 129, 0.1);
    border-color: rgba(16, 185, 129, 0.2);
    transform: translateY(0);
  }

  &.ready .status-dot {
    background: #10b981;
  }

  &.notready .status-dot {
    background: #f59e0b;
  }

  .status-text {
    color: var(--header-text-muted);
    transition: color 0.3s;
  }

  &.ready .status-text {
    color: #10b981;
  }

  &.notready .status-text {
    color: #f59e0b;
  }
}

/* Theme Toggle */
.theme-toggle {
  display: flex;
  align-items: center;
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 8px;
  transition: all 0.2s ease;

  &:hover {
    background: rgba(var(--header-primary-rgb), 0.08);

    .toggle-track {
      box-shadow: 0 2px 8px rgba(var(--header-primary-rgb), 0.25);
    }
  }

  .toggle-label {
    font-size: 0.8rem;
    font-weight: 600;
    margin-left: 8px;
    color: var(--header-text-body);
    transition: color 0.2s ease;

    @media (max-width: 767px) {
      display: none;
    }
  }

  .toggle-track {
    position: relative;
    width: 48px;
    height: 24px;
    background: rgba(var(--header-primary-rgb), 0.15);
    border-radius: 12px;
    transition: all 0.3s ease;
    padding: 2px;
    box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.1);
    border: 1px solid rgba(var(--header-primary-rgb), 0.2);
    overflow: hidden;
  }

  .toggle-icons {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 4px;
    pointer-events: none;
    z-index: 1;

    .sun-icon,
    .moon-icon {
      width: 14px;
      height: 14px;
      opacity: 0.4;
      transition: all 0.3s ease;

      &.active {
        opacity: 1;
      }
    }

    .sun-icon {
      color: #f59e0b;
      margin-left: 1px;
    }

    .moon-icon {
      color: #60a5fa;
      margin-right: 1px;
    }
  }

  .toggle-thumb {
    width: 18px;
    height: 18px;
    background: white;
    border-radius: 50%;
    position: absolute;
    top: 2px;
    left: 2px;
    transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
    z-index: 2;
    border: 1px solid rgba(0, 0, 0, 0.05);

    &.is-dark {
      transform: translateX(24px);
      background: #2d3748;
    }
  }
}

/* Enhanced Button Styles */
.btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  height: 40px;
  padding: 0 1.25rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.875rem;
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  text-decoration: none;
  position: relative;
  overflow: hidden;
  border: none;
  background: none;
  cursor: pointer;

  .btn-bg {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    border-radius: 8px;
    transition: all 0.3s ease;
    z-index: -1;
  }

  .btn-shine {
    position: absolute;
    top: -50%;
    left: -100%;
    width: 30%;
    height: 200%;
    background: linear-gradient(90deg,
        rgba(255, 255, 255, 0) 0%,
        rgba(255, 255, 255, 0.4) 50%,
        rgba(255, 255, 255, 0) 100%);
    transform: translateX(-100%) rotate(25deg);
    opacity: 0;
    transition: transform 0.6s cubic-bezier(0.11, 0, 0.5, 0), opacity 0.3s ease;
    z-index: 1;
  }

  .external-icon {
    width: 14px;
    height: 14px;
    opacity: 0.8;
    transition: all 0.3s ease;
  }

  /* COCONUT Button - Material Design Pastel Green/Teal */
  &.btn-coconut {
    --coconut-primary: #E0F2F1;
    /* Material Teal 50 */
    --coconut-secondary: #B2DFDB;
    /* Material Teal 100 */
    --coconut-accent: #80CBC4;
    /* Material Teal 200 */
    --coconut-text: #00695C;
    /* Material Teal 800 */
    --coconut-rgb: 0, 105, 92;

    color: var(--coconut-text);
    border: none;
    position: relative;
    background: linear-gradient(135deg, var(--coconut-primary), var(--coconut-secondary));
    backdrop-filter: blur(10px);
    box-shadow:
      0 3px 12px rgba(var(--coconut-rgb), 0.15),
      0 1px 6px rgba(0, 0, 0, 0.08);

    .btn-bg {
      background: linear-gradient(135deg,
          var(--coconut-primary) 0%,
          var(--coconut-secondary) 50%,
          var(--coconut-accent) 100%);
      opacity: 1;
    }

    .btn-icon {
      filter: none;
      color: var(--coconut-text);
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .external-icon {
      color: var(--coconut-text);
      opacity: 0.7;
    }

    &:hover {
      transform: translateY(-2px) scale(1.01);
      background: linear-gradient(135deg, var(--coconut-secondary), var(--coconut-accent));
      box-shadow:
        0 6px 20px rgba(var(--coconut-rgb), 0.25),
        0 2px 10px rgba(0, 0, 0, 0.12);

      .btn-shine {
        transform: translateX(300%) rotate(25deg);
        opacity: 0.6;
      }

      .external-icon {
        transform: translateX(2px);
        opacity: 1;
      }

      .btn-icon {
        transform: scale(1.05);
        filter: brightness(1.1);
      }

      span {
        color: var(--coconut-text);
      }
    }

    &:active {
      transform: translateY(-1px) scale(0.99);
      box-shadow:
        0 2px 8px rgba(var(--coconut-rgb), 0.2),
        0 1px 4px rgba(0, 0, 0, 0.1);
    }
  }

  /* DECIMER Button - Material Design Pastel Blue */
  &.btn-decimer {
    --decimer-primary: #E3F2FD;
    /* Material Blue 50 */
    --decimer-secondary: #BBDEFB;
    /* Material Blue 100 */
    --decimer-accent: #90CAF9;
    /* Material Blue 200 */
    --decimer-text: #1565C0;
    /* Material Blue 800 */
    --decimer-rgb: 21, 101, 192;

    color: var(--decimer-text);
    border: none;
    position: relative;
    background: linear-gradient(135deg, var(--decimer-primary), var(--decimer-secondary));
    backdrop-filter: blur(10px);
    box-shadow:
      0 3px 12px rgba(var(--decimer-rgb), 0.15),
      0 1px 6px rgba(0, 0, 0, 0.08);

    .btn-bg {
      background: linear-gradient(135deg,
          var(--decimer-primary) 0%,
          var(--decimer-secondary) 50%,
          var(--decimer-accent) 100%);
      opacity: 1;
    }

    .btn-icon {
      filter: none;
      color: var(--decimer-text);
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .external-icon {
      color: var(--decimer-text);
      opacity: 0.7;
    }

    &:hover {
      transform: translateY(-2px) scale(1.01);
      background: linear-gradient(135deg, var(--decimer-secondary), var(--decimer-accent));
      box-shadow:
        0 6px 20px rgba(var(--decimer-rgb), 0.25),
        0 2px 10px rgba(0, 0, 0, 0.12);

      .btn-shine {
        transform: translateX(300%) rotate(25deg);
        opacity: 0.6;
      }

      .external-icon {
        transform: translateX(2px);
        opacity: 1;
      }

      .btn-icon {
        transform: scale(1.05);
        filter: brightness(1.1);
      }

      span {
        color: var(--decimer-text);
      }
    }

    &:active {
      transform: translateY(-1px) scale(0.99);
      box-shadow:
        0 2px 8px rgba(var(--decimer-rgb), 0.2),
        0 1px 4px rgba(0, 0, 0, 0.1);
    }
  }

  /* Dark Mode Button Adaptations */
  [data-theme="dark"] .external-links {

    /* COCONUT Button - Dark Mode Pastel Teal/Green */
    .btn.btn-coconut {
      --coconut-primary: #1f2937;
      /* Gray 800 - Dark teal-gray */
      --coconut-secondary: #374151;
      /* Gray 700 - Medium dark */
      --coconut-accent: #4b5563;
      /* Gray 600 - Lighter dark */
      --coconut-text: #6ee7b7;
      /* Emerald 300 - Light teal text */
      --coconut-rgb: 110, 231, 183;

      color: var(--coconut-text);
      background: linear-gradient(135deg, var(--coconut-primary), var(--coconut-secondary));
      box-shadow:
        0 3px 12px rgba(var(--coconut-rgb), 0.2),
        0 1px 6px rgba(0, 0, 0, 0.3);

      .btn-bg {
        background: linear-gradient(135deg,
            var(--coconut-primary) 0%,
            var(--coconut-secondary) 50%,
            var(--coconut-accent) 100%);
      }

      .btn-icon,
      .external-icon {
        color: var(--coconut-text);
        filter: none;
      }

      &:hover {
        background: linear-gradient(135deg, var(--coconut-secondary), var(--coconut-accent));
        box-shadow:
          0 6px 20px rgba(var(--coconut-rgb), 0.3),
          0 2px 10px rgba(0, 0, 0, 0.4);

        .btn-icon,
        .external-icon,
        span {
          color: #a7f3d0;
          /* Emerald 200 - Even lighter on hover */
        }
      }

      &:active {
        box-shadow:
          0 2px 8px rgba(var(--coconut-rgb), 0.25),
          0 1px 4px rgba(0, 0, 0, 0.3);
      }
    }

    /* DECIMER Button - Dark Mode Pastel Blue */
    .btn.btn-decimer {
      --decimer-primary: #1e293b;
      /* Slate 800 - Dark blue-gray */
      --decimer-secondary: #334155;
      /* Slate 700 - Medium dark */
      --decimer-accent: #475569;
      /* Slate 600 - Lighter dark */
      --decimer-text: #93c5fd;
      /* Blue 300 - Light blue text */
      --decimer-rgb: 147, 197, 253;

      color: var(--decimer-text);
      background: linear-gradient(135deg, var(--decimer-primary), var(--decimer-secondary));
      box-shadow:
        0 3px 12px rgba(var(--decimer-rgb), 0.2),
        0 1px 6px rgba(0, 0, 0, 0.3);

      .btn-bg {
        background: linear-gradient(135deg,
            var(--decimer-primary) 0%,
            var(--decimer-secondary) 50%,
            var(--decimer-accent) 100%);
      }

      .btn-icon,
      .external-icon {
        color: var(--decimer-text);
        filter: none;
      }

      &:hover {
        background: linear-gradient(135deg, var(--decimer-secondary), var(--decimer-accent));
        box-shadow:
          0 6px 20px rgba(var(--decimer-rgb), 0.3),
          0 2px 10px rgba(0, 0, 0, 0.4);

        .btn-icon,
        .external-icon,
        span {
          color: #bfdbfe;
          /* Blue 200 - Even lighter on hover */
        }
      }

      &:active {
        box-shadow:
          0 2px 8px rgba(var(--decimer-rgb), 0.25),
          0 1px 4px rgba(0, 0, 0, 0.3);
      }
    }
  }

  /* Legacy support for existing button classes */
  &.btn-primary {
    color: white;

    .btn-bg {
      background: var(--header-primary-gradient);
      box-shadow:
        0 4px 10px rgba(var(--header-primary-rgb), 0.2),
        inset 0 0 0 1px rgba(255, 255, 255, 0.1);
    }

    &:hover {
      transform: translateY(-3px);

      .btn-bg {
        box-shadow:
          0 6px 15px rgba(var(--header-primary-rgb), 0.3),
          inset 0 0 0 1px rgba(255, 255, 255, 0.2);
      }
    }

    &:active {
      transform: scale(0.98);
    }
  }

  &.btn-secondary {
    color: white;

    .btn-bg {
      background: var(--header-secondary-gradient);
      box-shadow:
        0 4px 10px rgba(71, 85, 105, 0.2),
        inset 0 0 0 1px rgba(255, 255, 255, 0.1);
    }

    &:hover {
      transform: translateY(-3px);

      .btn-bg {
        box-shadow:
          0 6px 15px rgba(71, 85, 105, 0.3),
          inset 0 0 0 1px rgba(255, 255, 255, 0.2);
      }
    }

    &:active {
      transform: scale(0.98);
    }
  }

  &.btn-full {
    width: 100%;
    justify-content: center;
  }

  .btn-icon {
    width: 16px;
    height: 16px;
    transition: transform 0.3s ease;

    @media (max-width: 767px) {
      margin-right: 0;
    }
  }
}

/* Mobile Menu Toggle (only visible on mobile) */
.mobile-menu-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px 12px;
  background: rgba(var(--header-primary-rgb), 0.1);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.3s ease;
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 1001;

  @media (min-width: 768px) {
    display: none;
  }

  &:hover {
    background: rgba(var(--header-primary-rgb), 0.2);
  }

  .hamburger-container {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .menu-label {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--header-primary);
  }

  .hamburger {
    width: 24px;
    height: 20px;
    position: relative;
    display: flex;
    flex-direction: column;
    justify-content: space-between;

    span {
      display: block;
      width: 100%;
      height: 2px;
      background-color: var(--header-primary);
      border-radius: 2px;
      transition: all 0.3s cubic-bezier(0.68, -0.6, 0.32, 1.6);
    }

    &.is-active {
      span:nth-child(1) {
        transform: rotate(45deg) translate(6px, 6px);
      }

      span:nth-child(2) {
        opacity: 0;
      }

      span:nth-child(3) {
        transform: rotate(-45deg) translate(6px, -6px);
      }
    }
  }
}

/* Mobile Menu Backdrop */
.mobile-menu-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100vh;
  background: rgba(0, 0, 0, 0.5);
  z-index: 999;
}

/* Mobile Menu */
.mobile-menu {
  position: fixed;
  top: 0;
  right: 0;
  width: 85%;
  max-width: 320px;
  height: 100vh;
  background: var(--header-card-bg);
  box-shadow: -5px 0 25px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow-y: auto;
  transform: translateX(0);
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);

  .mobile-menu-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.25rem;
    border-bottom: 1px solid rgba(var(--header-primary-rgb), 0.1);

    .logo-mini {
      display: flex;
      align-items: center;
      gap: 0.5rem;

      img {
        height: 28px;
        width: auto;
      }

      h2 {
        font-size: 1.25rem;
        font-weight: 700;
        margin: 0;
        background: var(--header-primary-gradient);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        display: flex;
        align-items: center;

        .badge {
          font-size: 0.5rem;
          background: var(--header-primary-gradient);
          color: white;
          padding: 0.1rem 0.25rem;
          border-radius: 0.2rem;
          margin-left: 0.3rem;
          display: inline-block;
          font-weight: 600;
        }
      }
    }

    .close-menu-btn {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      background: rgba(var(--header-primary-rgb), 0.1);
      border: none;
      cursor: pointer;
      color: var(--header-primary);
      transition: all 0.3s ease;

      &:hover {
        background: rgba(var(--header-primary-rgb), 0.2);
        transform: rotate(90deg);
      }
    }
  }

  .mobile-nav {
    flex: 1;
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;

    .mobile-nav-link {
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 1rem;
      border-radius: 8px;
      background: rgba(var(--header-primary-rgb), 0.05);
      color: var(--header-text-body);
      font-weight: 500;
      text-decoration: none;
      transition: all 0.3s ease;

      &:hover {
        background: rgba(var(--header-primary-rgb), 0.1);
        transform: translateX(5px);

        .mobile-nav-icon {
          transform: scale(1.1);
        }
      }

      .mobile-nav-icon {
        width: 20px;
        height: 20px;
        color: var(--header-primary);
        transition: transform 0.3s ease;
      }
    }
  }

  .mobile-menu-footer {
    padding: 1.5rem;
    border-top: 1px solid rgba(var(--header-primary-rgb), 0.1);
    display: flex;
    flex-direction: column;
    gap: 1rem;

    .theme-toggle-mobile {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.75rem;
      border-radius: 8px;
      background: rgba(var(--header-primary-rgb), 0.05);
      border: none;
      cursor: pointer;
      color: var(--header-text-body);
      font-weight: 500;
      transition: all 0.3s ease;

      &:hover {
        background: rgba(var(--header-primary-rgb), 0.1);
      }

      .theme-icon {
        width: 20px;
        height: 20px;
        color: var(--header-primary);
      }
    }
  }
}

/* Animations */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.5s ease;
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

@keyframes pulse {

  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.5;
  }
}

/* Dark Mode Mobile Menu Button Adaptations */
[data-theme="dark"] .mobile-menu-footer {

  /* Mobile COCONUT Button - Dark Mode Teal/Green */
  .btn.btn-coconut {
    --coconut-primary: #1f2937;
    --coconut-secondary: #374151;
    --coconut-accent: #4b5563;
    --coconut-text: #6ee7b7;
    --coconut-rgb: 110, 231, 183;

    color: var(--coconut-text);
    background: linear-gradient(135deg, var(--coconut-primary), var(--coconut-secondary));
    box-shadow:
      0 3px 12px rgba(var(--coconut-rgb), 0.2),
      0 1px 6px rgba(0, 0, 0, 0.3);

    .btn-bg {
      background: linear-gradient(135deg,
          var(--coconut-primary) 0%,
          var(--coconut-secondary) 50%,
          var(--coconut-accent) 100%);
    }

    .btn-icon,
    .external-icon {
      color: var(--coconut-text);
      filter: none;
    }

    &:hover {
      background: linear-gradient(135deg, var(--coconut-secondary), var(--coconut-accent));
      box-shadow:
        0 6px 20px rgba(var(--coconut-rgb), 0.3),
        0 2px 10px rgba(0, 0, 0, 0.4);

      .btn-icon,
      .external-icon,
      span {
        color: #a7f3d0;
      }
    }
  }

  /* Mobile DECIMER Button - Dark Mode Blue */
  .btn.btn-decimer {
    --decimer-primary: #1e293b;
    --decimer-secondary: #334155;
    --decimer-accent: #475569;
    --decimer-text: #93c5fd;
    --decimer-rgb: 147, 197, 253;

    color: var(--decimer-text);
    background: linear-gradient(135deg, var(--decimer-primary), var(--decimer-secondary));
    box-shadow:
      0 3px 12px rgba(var(--decimer-rgb), 0.2),
      0 1px 6px rgba(0, 0, 0, 0.3);

    .btn-bg {
      background: linear-gradient(135deg,
          var(--decimer-primary) 0%,
          var(--decimer-secondary) 50%,
          var(--decimer-accent) 100%);
    }

    .btn-icon,
    .external-icon {
      color: var(--decimer-text);
      filter: none;
    }

    &:hover {
      background: linear-gradient(135deg, var(--decimer-secondary), var(--decimer-accent));
      box-shadow:
        0 6px 20px rgba(var(--decimer-rgb), 0.3),
        0 2px 10px rgba(0, 0, 0, 0.4);

      .btn-icon,
      .external-icon,
      span {
        color: #bfdbfe;
      }
    }
  }
}
</style>