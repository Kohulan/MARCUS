<template>
  <header class="app-header" :class="{'scrolled': isScrolled}">
    <div class="header-bg-glow"></div>
    <div class="container">
      <!-- Updated logo click to hide both disclaimer and features -->
      <router-link to="/" class="logo" @click="homeNavigation">
        <div class="logo-img">
          <div class="logo-shine"></div>
          <img src="@/assets/logo.png" alt="MARKUS" />
        </div>
        <div class="logo-text">
          <h1>MARCUS<span class="badge">Beta Release</span></h1>
        </div>
      </router-link>
      
      <nav class="header-nav">
        <a href="#features" class="nav-link" @click.prevent="scrollToFeatures">
          <div class="nav-icon-wrapper">
            <vue-feather type="layers" class="nav-icon"></vue-feather>
          </div>
          <span>Features</span>
        </a>
        <a href="#about" class="nav-link">
          <div class="nav-icon-wrapper">
            <vue-feather type="info" class="nav-icon"></vue-feather>
          </div>
          <span>About</span>
        </a>
        <a href="#help" class="nav-link">
          <div class="nav-icon-wrapper">
            <vue-feather type="help-circle" class="nav-icon"></vue-feather>
          </div>
          <span>Documentation</span>
        </a>
        <a href="#" class="nav-link" @click.prevent="toggleDisclaimer">
          <div class="nav-icon-wrapper">
            <vue-feather type="shield" class="nav-icon"></vue-feather>
          </div>
          <span>Disclaimer</span>
        </a>
      </nav>
      
      <div class="header-actions">
        <button 
          class="theme-toggle" 
          @click="toggleTheme" 
          :title="isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'"
          aria-label="Toggle dark mode"
        >
          <div class="toggle-track">
            <div class="toggle-icons">
              <vue-feather type="sun" class="sun-icon" :class="{'active': !isDarkMode}"></vue-feather>
              <vue-feather type="moon" class="moon-icon" :class="{'active': isDarkMode}"></vue-feather>
            </div>
            <div class="toggle-thumb" :class="{'is-dark': isDarkMode}"></div>
          </div>
          <span class="toggle-label">{{ isDarkMode ? 'Dark' : 'Light' }}</span>
        </button>
        
        <a href="https://coconut.naturalproducts.net/" target="_blank" class="btn btn-primary">
          <div class="btn-bg"></div>
          <img src="@/assets/coconut-logo.svg" alt="COCONUT" class="btn-icon" />
          <span>Visit COCONUT</span>
        </a>
      </div>
      
      <!-- Improved mobile menu toggle button -->
      <button class="mobile-menu-toggle" aria-label="Toggle mobile menu" @click="toggleMobileMenu">
        <div class="hamburger-container">
          <div class="hamburger" :class="{'is-active': isMobileMenuOpen}">
            <span></span>
            <span></span>
            <span></span>
          </div>
          <span class="menu-label" v-if="!isMobileMenuOpen">Menu</span>
          <span class="menu-label" v-else>Close</span>
        </div>
      </button>
    </div>
    
    <!-- Mobile menu backdrop overlay -->
    <transition name="fade">
      <div class="mobile-menu-backdrop" v-if="isMobileMenuOpen" @click="closeMobileMenu"></div>
    </transition>
    
    <!-- Improved mobile menu with slide animation -->
    <transition name="slide">
      <div class="mobile-menu" :class="{'is-open': isMobileMenuOpen}" v-if="isMobileMenuOpen">
        <div class="mobile-menu-header">
          <div class="logo-mini">
            <img src="@/assets/logo.png" alt="MARKUS" />
            <h2>MARCUS<span class="badge">Beta</span></h2>
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
          <a href="#about" class="mobile-nav-link" @click="closeMobileMenu">
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
          
          <a href="https://coconut.naturalproducts.net/" target="_blank" class="btn btn-primary btn-full">
            <div class="btn-bg"></div>
            <img src="@/assets/coconut-logo.svg" alt="COCONUT" class="btn-icon" />
            <span>Visit COCONUT</span>
          </a>
        </div>
      </div>
    </transition>
  </header>
</template>

<script>
import { mapState, mapActions } from 'vuex'

export default {
  name: 'AppHeader',
  
  data() {
    return {
      isScrolled: false,
      isMobileMenuOpen: false
    }
  },
  
  computed: {
    ...mapState({
      isDarkMode: state => state.theme.isDarkMode,
      isFeaturesVisible: state => state.isFeaturesVisible,
      isDisclaimerVisible: state => state.isDisclaimerVisible
    })
  },
  
  methods: {
    ...mapActions({
      toggleDarkMode: 'theme/toggleDarkMode',
      toggleDisclaimer: 'toggleDisclaimer',
      showDisclaimer: 'showDisclaimer',
      hideDisclaimer: 'hideDisclaimer',
      showFeatures: 'showFeatures',
      hideFeatures: 'hideFeatures'
    }),
    
    // New method to handle logo navigation
    homeNavigation() {
      // Hide both disclaimer and features when navigating home
      this.hideDisclaimer();
      this.hideFeatures();
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
    
    homeAndCloseMenu() {
      this.hideDisclaimer();
      this.hideFeatures();
      this.closeMobileMenu();
    },
    
    // Methods for features section
    scrollToFeatures() {
      const featuresSection = document.getElementById('features')
      if (featuresSection) {
        // Hide disclaimer if it's showing
        this.hideDisclaimer();
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
    }
  },
  
  created() {
    // Initialize theme when component is created
    this.$store.dispatch('theme/initTheme')
  },
  
  mounted() {
    window.addEventListener('scroll', this.handleScroll)
  },
  
  beforeUnmount() {
    window.removeEventListener('scroll', this.handleScroll)
  }
}
</script>

<style lang="scss" scoped>
.app-header {
  background: rgba(var(--color-panel-bg-rgb), 0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  overflow: visible;
  
  &:before {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    width: 100%;
    height: 1px;
    background: linear-gradient(90deg, 
      transparent 0%, 
      rgba(var(--color-primary-rgb), 0.1) 15%, 
      rgba(var(--color-primary-rgb), 0.3) 50%, 
      rgba(var(--color-primary-rgb), 0.1) 85%, 
      transparent 100%
    );
  }
  
  &.scrolled {
    box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.1);
    
    .container {
      padding-top: 0.5rem;
      padding-bottom: 0.5rem;
    }
    
    .logo-img {
      transform: scale(0.9);
    }
    
    .logo h1 {
      font-size: 1.35rem;
    }
  }
  
  .header-bg-glow {
    position: absolute;
    top: -100px;
    left: 50%;
    transform: translateX(-50%);
    width: 80%;
    height: 150px;
    background: radial-gradient(
      circle at center,
      rgba(var(--color-primary-rgb), 0.15) 0%, 
      rgba(var(--color-primary-rgb), 0.05) 40%, 
      rgba(var(--color-primary-rgb), 0) 70%
    );
    z-index: -1;
    opacity: 0.8;
    filter: blur(40px);
    border-radius: 50%;
    pointer-events: none;
  }
  
  .container {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1.5rem;
    max-width: 1800px;
    margin: 0 auto;
    transition: padding 0.3s ease;
  }
  
  .logo {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    position: relative;
    z-index: 2;
    text-decoration: none; /* Added for router-link */
    
    .logo-img {
      position: relative;
      height: 48px;
      width: 48px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 12px;
      background: rgba(var(--color-primary-rgb), 0.08);
      box-shadow: 
        0 4px 10px -2px rgba(var(--color-primary-rgb), 0.15),
        inset 0 0 0 1px rgba(var(--color-primary-rgb), 0.2);
      overflow: hidden;
      transition: all 0.3s ease;
      
      &:before {
        content: '';
        position: absolute;
        top: -2px;
        left: -2px;
        right: -2px;
        bottom: -2px;
        background: var(--gradient-primary);
        opacity: 0.4;
        border-radius: 14px;
        transform: rotate(-3deg) scale(0.97);
        transition: transform 0.5s ease;
        z-index: 0;
      }
      
      &:hover {
        transform: translateY(-2px) scale(1.05);
        
        &:before {
          transform: rotate(0) scale(1);
        }
        
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
        background: linear-gradient(
          90deg, 
          rgba(255, 255, 255, 0) 0%, 
          rgba(255, 255, 255, 0.5) 50%, 
          rgba(255, 255, 255, 0) 100%
        );
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
        background: var(--gradient-primary);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        display: flex;
        align-items: center;
        transition: font-size 0.3s ease;
        text-shadow: 0 1px 1px rgba(0, 0, 0, 0.05);
        
        .badge {
          font-size: 0.55rem;
          background: var(--gradient-primary);
          color: white;
          padding: 0.15rem 0.35rem;
          border-radius: 0.25rem;
          margin-left: 0.4rem;
          display: inline-block;
          font-weight: 700;
          box-shadow: 0 2px 4px rgba(var(--color-primary-rgb), 0.3);
          text-shadow: none;
          letter-spacing: 0;
        }
      }
      
      .tagline {
        font-size: 0.7rem;
        color: var(--color-text-light);
        font-weight: 500;
        letter-spacing: 0.3px;
        margin-top: 0.1rem;
        opacity: 0.8;
      }
    }
  }
  
  .header-nav {
    display: none;
    
    @media (min-width: 768px) {
      display: flex;
      align-items: center;
      gap: 1.25rem;
      margin-left: 2rem;
    }
    
    .nav-link {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      color: var(--color-text-light);
      font-weight: 500;
      font-size: 0.875rem;
      text-decoration: none;
      padding: 0.35rem 0.5rem;
      position: relative;
      transition: all 0.2s ease;
      border-radius: 6px;
      
      &:after {
        content: '';
        position: absolute;
        bottom: -2px;
        left: 0;
        width: 0;
        height: 2px;
        background: var(--gradient-primary);
        transition: width 0.3s cubic-bezier(0.19, 1, 0.22, 1);
        border-radius: 2px;
      }
      
      &:hover {
        color: var(--color-primary);
        background: rgba(var(--color-primary-rgb), 0.05);
        
        &:after {
          width: 100%;
        }
        
        .nav-icon-wrapper {
          background: rgba(var(--color-primary-rgb), 0.15);
          transform: translateY(-2px);
          
          .nav-icon {
            transform: scale(1.1);
          }
        }
      }
      
      .nav-icon-wrapper {
        width: 26px;
        height: 26px;
        border-radius: 6px;
        background: rgba(var(--color-primary-rgb), 0.08);
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.3s ease;
      }
      
      .nav-icon {
        width: 14px;
        height: 14px;
        color: var(--color-primary);
        transition: transform 0.3s ease;
      }
    }
  }
  
  .header-actions {
    display: flex;
    align-items: center;
    gap: 1rem;
    
    @media (max-width: 767px) {
      .btn span {
        display: none;
      }
      
      .btn {
        width: 42px;
        padding: 0;
      }
    }
  }
  
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
      background: rgba(var(--color-primary-rgb), 0.08);
      
      .toggle-track {
        box-shadow: 0 2px 8px rgba(var(--color-primary-rgb), 0.25);
      }
    }
    
    .toggle-label {
      font-size: 0.8rem;
      font-weight: 600;
      margin-left: 8px;
      color: var(--color-text);
      transition: color 0.2s ease;
      
      @media (max-width: 767px) {
        display: none;
      }
    }
    
    .toggle-track {
      position: relative;
      width: 48px;
      height: 24px;
      background: rgba(var(--color-primary-rgb), 0.15);
      border-radius: 12px;
      transition: all 0.3s ease;
      padding: 2px;
      box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
      border: 1px solid rgba(var(--color-primary-rgb), 0.2);
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
      
      .sun-icon, .moon-icon {
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
    
    &.btn-primary {
      color: white;
      
      .btn-bg {
        background: var(--gradient-primary);
        box-shadow: 
          0 4px 10px rgba(var(--color-primary-rgb), 0.2),
          inset 0 0 0 1px rgba(255, 255, 255, 0.1);
      }
      
      &:hover {
        transform: translateY(-3px);
        
        .btn-bg {
          box-shadow: 
            0 6px 15px rgba(var(--color-primary-rgb), 0.3),
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
      filter: brightness(0) invert(1);
      transition: transform 0.3s ease;
      
      @media (max-width: 767px) {
        margin-right: 0;
      }
    }
  }
  
  /* Improved Mobile Menu Toggle */
  .mobile-menu-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 8px 12px;
    background: rgba(var(--color-primary-rgb), 0.1);
    border: none;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.3s ease;
    
    @media (min-width: 768px) {
      display: none;
    }
    
    &:hover {
      background: rgba(var(--color-primary-rgb), 0.2);
    }
    
    .hamburger-container {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    
    .menu-label {
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--color-primary);
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
        background-color: var(--color-primary);
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
  
  /* Improved Mobile Menu */
  .mobile-menu {
    position: fixed;
    top: 0;
    right: 0;
    width: 85%;
    max-width: 320px;
    height: 100vh;
    background: var(--color-panel-bg);
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
      border-bottom: 1px solid rgba(var(--color-primary-rgb), 0.1);
      
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
          background: var(--gradient-primary);
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
          display: flex;
          align-items: center;
          
          .badge {
            font-size: 0.5rem;
            background: var(--gradient-primary);
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
        background: rgba(var(--color-primary-rgb), 0.1);
        border: none;
        cursor: pointer;
        color: var(--color-primary);
        transition: all 0.3s ease;
        
        &:hover {
          background: rgba(var(--color-primary-rgb), 0.2);
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
        background: rgba(var(--color-primary-rgb), 0.05);
        color: var(--color-text);
        font-weight: 500;
        text-decoration: none;
        transition: all 0.3s ease;
        
        &:hover {
          background: rgba(var(--color-primary-rgb), 0.1);
          transform: translateX(5px);
          
          .mobile-nav-icon {
            transform: scale(1.1);
          }
        }
        
        .mobile-nav-icon {
          width: 20px;
          height: 20px;
          color: var(--color-primary);
          transition: transform 0.3s ease;
        }
      }
    }
    
    .mobile-menu-footer {
      padding: 1.5rem;
      border-top: 1px solid rgba(var(--color-primary-rgb), 0.1);
      display: flex;
      flex-direction: column;
      gap: 1rem;
      
      .theme-toggle-mobile {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.75rem;
        border-radius: 8px;
        background: rgba(var(--color-primary-rgb), 0.05);
        border: none;
        cursor: pointer;
        color: var(--color-text);
        font-weight: 500;
        transition: all 0.3s ease;
        
        &:hover {
          background: rgba(var(--color-primary-rgb), 0.1);
        }
        
        .theme-icon {
          width: 20px;
          height: 20px;
          color: var(--color-primary);
        }
      }
    }
  }
}

/* Add transition classes for the slide and fade effects */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}

/* Add these CSS variables to your app's global styles */
:root {
  --gradient-primary: linear-gradient(135deg, #4a6cf7 0%, #2254e2 100%);
  --color-primary: #3461ff;
  --color-primary-rgb: 52, 97, 255;
  --color-panel-bg: #f7f9fc;
  --color-panel-bg-rgb: 247, 249, 252;
  --color-border: #e4e9f2;
  --color-text: #3b4863;
  --color-text-light: #8392ab;
  --z-sticky: 100;
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  :root {
    --color-panel-bg: #1a1f2e;
    --color-panel-bg-rgb: 26, 31, 46;
    --color-border: #2a3247;
    --color-text: #e0e3e9;
    --color-text-light: #a0abc3;
  }
}
</style>