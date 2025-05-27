<template>
  <div class="professional-loading-screen"
    :class="{ 'dark-mode': isDarkMode, 'light-mode': !isDarkMode, 'loaded': isLoaded }" ref="loadingScreen">
    <!-- Subtle animated background -->
    <div class="animated-background">
      <div class="gradient-overlay"></div>
      <div class="geometric-pattern">
        <div class="pattern-circle circle-1"></div>
        <div class="pattern-circle circle-2"></div>
        <div class="pattern-circle circle-3"></div>
      </div>
    </div>

    <!-- Main content container -->
    <div class="content-container">
      <!-- Logo section -->
      <div class="logo-section">
        <!-- Clean circular background for logo -->
        <div class="logo-background">
          <div class="background-ring ring-1"></div>
          <div class="background-ring ring-2"></div>
        </div>

        <!-- Logo container with zoom out effect -->
        <div class="logo-container">
          <div class="logo-shadow"></div>
          <img src="@/assets/logo.png" alt="MARCUS" class="logo" />
          <div class="logo-glow"></div>
        </div>
      </div>

      <!-- Text elements -->
      <div class="text-elements" :class="{ 'text-visible': titleVisible }">
        <div class="title-container">
          <h1 class="title"><span class="marcus-text">MARCUS</span></h1>
          <div class="badge-wrapper">
            <span class="badge">Public-Beta</span>
            <span class="badge-shine"></span>
          </div>
        </div>

        <div class="tagline-wrapper">
          <div class="tagline-glow"></div>
          <p class="tagline">Molecular Annotation and Recognition for Curating Unravelled Structures</p>
        </div>
      </div>

      <!-- Loading elements -->
      <div class="loading-elements" v-if="!isLoaded">
        <div class="loading-track">
          <div class="loading-progress-container">
            <div class="loading-bar">
              <div class="loading-progress" :style="{ width: `${loadingProgress}%` }"></div>
              <div class="loading-glow" :style="{ left: `${loadingProgress}%` }"></div>
              <div class="loading-particles">
                <div v-for="n in 5" :key="`load-particle-${n}`" class="loading-particle"
                  :style="getLoadingParticleStyle(n, loadingProgress)"></div>
              </div>
            </div>
          </div>

          <div class="loading-message-container">
            <p class="loading-message">
              <span class="message-text">{{ loadingMessage }}</span>
              <span class="loading-dots"><span>.</span><span>.</span><span>.</span></span>
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { mapState } from 'vuex';

export default {
  data() {
    return {
      loadingProgress: 0,
      titleVisible: false,
      isLoaded: false,
      loadingMessages: [
        'Initializing system...',
        'Loading molecular engines...',
        'Calibrating structure detection...',
        'Systems operational'
      ],
      currentMessageIndex: 0,
      maxLoadTime: 2500
    };
  },

  computed: {
    ...mapState({
      isDarkMode: state => state.theme?.isDarkMode || false
    }),

    loadingMessage() {
      return this.loadingMessages[this.currentMessageIndex];
    }
  },

  mounted() {
    setTimeout(() => {
      this.titleVisible = true;
    }, 400);

    this.simulateLoading();
  },

  methods: {
    simulateLoading() {
      const startTime = performance.now();
      const totalDuration = this.maxLoadTime;
      const messageThresholds = [0, 33, 66, 90];

      const updateLoading = () => {
        const elapsedTime = performance.now() - startTime;
        const progress = Math.min((elapsedTime / totalDuration) * 100, 100);

        this.loadingProgress = progress;

        for (let i = 0; i < messageThresholds.length; i++) {
          if (progress >= messageThresholds[i] && this.currentMessageIndex !== i) {
            this.currentMessageIndex = i;
          }
        }

        if (progress < 100) {
          requestAnimationFrame(updateLoading);
        } else {
          setTimeout(() => {
            this.isLoaded = true;

            setTimeout(() => {
              this.$emit('loading-complete');
            }, 800);
          }, 200);
        }
      };

      updateLoading();
    },

    getLoadingParticleStyle(particleIndex, progress) {
      const offset = (progress / 100) * 100;
      const basePos = (particleIndex / 5) * 100;
      const pos = (basePos + offset) % 100;

      return {
        left: `${pos}%`,
        animationDelay: `${particleIndex * 0.1}s`,
        backgroundColor: particleIndex % 2 === 0 ?
          'rgb(59, 130, 246)' : 'rgb(99, 102, 241)'
      };
    }
  }
};
</script>

<style lang="scss" scoped>
/* Professional Loading Screen Styles */
.professional-loading-screen {
  /* Dark mode (default) */
  --color-primary: 59, 130, 246;
  /* Professional blue */
  --color-secondary: 99, 102, 241;
  /* Indigo */
  --color-accent: 16, 185, 129;
  /* Emerald */
  --color-highlight: 245, 101, 101;
  /* Rose */
  --color-background: 15, 23, 42;
  /* Slate dark */
  --color-surface: 30, 41, 59;
  /* Slate surface */
  --color-text: 248, 250, 252;
  /* Slate light */
  --color-text-secondary: 148, 163, 184;
  /* Slate gray */

  /* Light mode overrides */
  &.light-mode {
    --color-primary: 37, 99, 235;
    /* Blue */
    --color-secondary: 79, 70, 229;
    /* Indigo */
    --color-accent: 5, 150, 105;
    /* Emerald */
    --color-highlight: 239, 68, 68;
    /* Red */
    --color-background: 248, 250, 252;
    /* Light slate */
    --color-surface: 255, 255, 255;
    /* White */
    --color-text: 15, 23, 42;
    /* Dark slate */
    --color-text-secondary: 100, 116, 139;
    /* Slate gray */
  }
}

/* Main container */
.professional-loading-screen {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 9999;
  display: flex;
  justify-content: center;
  align-items: center;
  background: rgb(var(--color-background));
  overflow: hidden;
  transition: opacity 1s cubic-bezier(0.4, 0, 0.2, 1);

  /* Transition when loading completes - PRESERVE ZOOM OUT EFFECT */
  &.loaded {
    opacity: 0;
    pointer-events: none;

    .logo-container {
      animation: logoZoomOut 1.2s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }

    .content-container {
      opacity: 0;
      transition: opacity 0.8s ease;
    }
  }
}

/* Professional animated background */
.animated-background {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 1;
  overflow: hidden;
}

.gradient-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg,
      rgba(var(--color-primary), 0.05) 0%,
      rgba(var(--color-secondary), 0.05) 50%,
      rgba(var(--color-accent), 0.05) 100%);
  animation: gradientShift 8s ease-in-out infinite alternate;
}

.geometric-pattern {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

.pattern-circle {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(var(--color-primary), 0.1);
  animation: float 6s ease-in-out infinite;

  &.circle-1 {
    width: 200px;
    height: 200px;
    top: 20%;
    left: 10%;
    animation-delay: 0s;
    animation-duration: 8s;
  }

  &.circle-2 {
    width: 150px;
    height: 150px;
    top: 60%;
    right: 15%;
    animation-delay: 2s;
    animation-duration: 10s;
  }

  &.circle-3 {
    width: 100px;
    height: 100px;
    bottom: 20%;
    left: 50%;
    animation-delay: 4s;
    animation-duration: 12s;
  }
}

/* Content container */
.content-container {
  position: relative;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  max-width: 600px;
  padding: 2rem;
}

/* Logo section */
.logo-section {
  position: relative;
  margin-bottom: 3rem;
}

/* Logo background with clean design */
.logo-background {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 200px;
  height: 200px;
  z-index: 1;
}

.background-ring {
  position: absolute;
  top: 50%;
  left: 50%;
  border-radius: 50%;
  border: 1px solid rgba(var(--color-primary), 0.2);
  transform: translate(-50%, -50%);
  animation: ringRotate 20s linear infinite;

  &.ring-1 {
    width: 180px;
    height: 180px;
    border-width: 2px;
    animation-direction: normal;
  }

  &.ring-2 {
    width: 160px;
    height: 160px;
    border-color: rgba(var(--color-secondary), 0.15);
    animation-direction: reverse;
    animation-duration: 30s;
  }
}

/* Main logo container - PRESERVES ZOOM OUT EFFECT */
.logo-container {
  position: relative;
  width: 120px;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  animation: logoScale 1s cubic-bezier(0.34, 1.56, 0.64, 1) forwards 0.3s;
  transform: scale(0);

  .logo {
    width: 100%;
    height: 100%;
    object-fit: contain;
    position: relative;
    z-index: 2;
    filter: drop-shadow(0 4px 12px rgba(var(--color-primary), 0.3));
    transition: transform 0.3s ease;
  }
}

.logo-shadow {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 130px;
  height: 130px;
  transform: translate(-50%, -50%);
  background: radial-gradient(circle at center,
      rgba(var(--color-primary), 0.2) 0%,
      rgba(var(--color-primary), 0.1) 50%,
      transparent 70%);
  border-radius: 50%;
  filter: blur(15px);
  z-index: 1;
  animation: shadowPulse 3s ease-in-out infinite alternate;
}

.logo-glow {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 140px;
  height: 140px;
  transform: translate(-50%, -50%);
  background: radial-gradient(circle at center,
      rgba(var(--color-primary), 0.15) 0%,
      rgba(var(--color-primary), 0.05) 50%,
      transparent 70%);
  border-radius: 50%;
  filter: blur(20px);
  z-index: 0;
  animation: glowPulse 4s ease-in-out infinite alternate;
}

/* Text elements - Professional styling */
.text-elements {
  text-align: center;
  opacity: 0;
  transform: translateY(20px);
  transition: all 0.8s cubic-bezier(0.4, 0, 0.2, 1);

  &.text-visible {
    opacity: 1;
    transform: translateY(0);
  }
}

.title-container {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1rem;
  gap: 0.5rem;
}

.title {
  font-size: 3rem;
  font-weight: 700;
  color: rgb(var(--color-text));
  margin: 0;
  letter-spacing: -0.02em;
  text-shadow: 0 2px 8px rgba(var(--color-primary), 0.2);
}

.badge-wrapper {
  position: relative;
  display: inline-block;
}

.badge {
  font-size: 0.875rem;
  background: rgba(var(--color-primary), 0.1);
  color: rgb(var(--color-primary));
  padding: 0.25rem 0.5rem;
  border-radius: 0.375rem;
  font-weight: 600;
  border: 1px solid rgba(var(--color-primary), 0.2);
}

.badge-shine {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg,
      transparent 0%,
      rgba(255, 255, 255, 0.2) 50%,
      transparent 100%);
  transform: translateX(-100%);
  animation: shine 3s ease-in-out infinite;
}

.tagline-wrapper {
  position: relative;
  max-width: 500px;
  margin: 0 auto;
}

.tagline-glow {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: radial-gradient(ellipse at center,
      rgba(var(--color-primary), 0.05) 0%,
      transparent 70%);
  filter: blur(10px);
}

.tagline {
  font-size: 1rem;
  color: rgb(var(--color-text-secondary));
  margin: 0;
  line-height: 1.5;
  font-weight: 400;
}

/* Loading elements - Clean professional style */
.loading-elements {
  margin-top: 3rem;
  width: 100%;
  max-width: 400px;
}

.loading-track {
  position: relative;
}

.loading-progress-container {
  margin-bottom: 1.5rem;
}

.loading-bar {
  width: 100%;
  height: 6px;
  background: rgba(var(--color-primary), 0.1);
  border-radius: 3px;
  overflow: hidden;
  position: relative;

  .loading-progress {
    height: 100%;
    background: linear-gradient(90deg,
        rgb(var(--color-primary)) 0%,
        rgb(var(--color-secondary)) 100%);
    border-radius: 3px;
    transition: width 0.3s ease;
    position: relative;

    &::after {
      content: '';
      position: absolute;
      top: 0;
      right: -20px;
      width: 20px;
      height: 100%;
      background: linear-gradient(90deg,
          rgba(255, 255, 255, 0.3) 0%,
          transparent 100%);
      animation: progressShine 2s ease-in-out infinite;
    }
  }
}

.loading-glow {
  position: absolute;
  top: -2px;
  height: 10px;
  width: 20px;
  background: rgba(var(--color-primary), 0.5);
  border-radius: 10px;
  filter: blur(6px);
  transform: translateX(-10px);
  animation: glowMove 2s ease-in-out infinite;
}

.loading-particles {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.loading-particle {
  position: absolute;
  width: 3px;
  height: 3px;
  background: rgb(var(--color-primary));
  border-radius: 50%;
  opacity: 0.7;
  animation: particleFloat 1.5s ease-in-out infinite;
}

.loading-message-container {
  text-align: center;
}

.loading-message {
  font-size: 0.875rem;
  color: rgb(var(--color-text-secondary));
  margin: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
}

.message-text {
  transition: opacity 0.3s ease;
}

.loading-dots {
  display: inline-flex;
  gap: 0.125rem;

  span {
    display: inline-block;
    animation: dot 1.4s ease-in-out infinite both;

    &:nth-child(1) {
      animation-delay: 0s;
    }

    &:nth-child(2) {
      animation-delay: 0.16s;
    }

    &:nth-child(3) {
      animation-delay: 0.32s;
    }
  }
}

/* Professional Keyframes */
@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

@keyframes logoScale {
  0% {
    transform: scale(0);
  }

  60% {
    transform: scale(1.05);
  }

  100% {
    transform: scale(1);
  }
}

/* PRESERVE ZOOM OUT EFFECT - CRITICAL */
@keyframes logoZoomOut {
  0% {
    transform: translateZ(0) scale(1);
    opacity: 1;
  }

  100% {
    transform: translateZ(1500px) scale(30);
    opacity: 0;
  }
}

@keyframes ringRotate {
  from {
    transform: translate(-50%, -50%) rotate(0deg);
  }

  to {
    transform: translate(-50%, -50%) rotate(360deg);
  }
}

@keyframes float {

  0%,
  100% {
    transform: translateY(0);
  }

  50% {
    transform: translateY(-10px);
  }
}

@keyframes gradientShift {
  0% {
    opacity: 0.3;
  }

  50% {
    opacity: 0.1;
  }

  100% {
    opacity: 0.3;
  }
}

@keyframes shadowPulse {
  0% {
    opacity: 0.2;
  }

  100% {
    opacity: 0.4;
  }
}

@keyframes glowPulse {
  0% {
    opacity: 0.3;
  }

  100% {
    opacity: 0.6;
  }
}

@keyframes shine {
  0% {
    transform: translateX(-100%);
  }

  100% {
    transform: translateX(100%);
  }
}

@keyframes progressShine {
  0% {
    opacity: 0;
  }

  50% {
    opacity: 1;
  }

  100% {
    opacity: 0;
  }
}

@keyframes glowMove {
  0% {
    transform: translateX(-10px);
    opacity: 0;
  }

  50% {
    opacity: 1;
  }

  100% {
    transform: translateX(10px);
    opacity: 0;
  }
}

@keyframes particleFloat {
  0% {
    transform: translateY(0) scale(1);
    opacity: 0.7;
  }

  50% {
    transform: translateY(-5px) scale(1.2);
    opacity: 1;
  }

  100% {
    transform: translateY(0) scale(1);
    opacity: 0.7;
  }
}

@keyframes dot {

  0%,
  80%,
  100% {
    opacity: 0.3;
  }

  40% {
    opacity: 1;
  }
}

/* Responsive Design */
@media (max-width: 768px) {
  .professional-loading-screen {
    padding: 1rem;
  }

  .content-container {
    max-width: 100%;
    padding: 1rem;
  }

  .logo-container {
    width: 100px;
    height: 100px;
  }

  .title {
    font-size: 2.4rem;
  }

  .tagline {
    font-size: 0.9rem;
  }

  .loading-elements {
    margin-top: 2rem;
  }
}
</style>
