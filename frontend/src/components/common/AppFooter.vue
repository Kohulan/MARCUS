<template>
  <footer class="app-footer">
    <div class="floating-element"></div>
    <div class="footer-content">
      <!-- Single streamlined footer layout -->
      <div class="footer-main">
        <!-- Left side: Copyright -->
        <div class="copyright-section">
          <div class="copyright-text">&copy; 2025 <span class="marcus-text">MARCUS</span>. All rights reserved.</div>
        </div>

        <!-- Center: Credits with tagline -->
        <div class="center-section">
          <div class="credits">
            Crafted with
            <svg class="coffee-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
              fill="none" stroke="#a0522d" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 8h1a4 4 0 0 1 0 8h-1"></path>
              <path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"></path>
              <line x1="6" y1="1" x2="6" y2="4"></line>
              <line x1="10" y1="1" x2="10" y2="4"></line>
              <line x1="14" y1="1" x2="14" y2="4"></line>
            </svg>
            by <a href="https://kohulanr.com" target="_blank">Kohulan Rajan</a> @ <a
              href="https://github.com/Steinbeck-Lab" target="_blank">Steinbeck Lab</a>
          </div>
        </div>

        <!-- Right side: Links with icons -->
        <div class="links-section">
          <div class="footer-link-wrapper">
            <a href="https://github.com/Kohulan/MARCUS" target="_blank" class="footer-link">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path
                  d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22">
                </path>
              </svg>
              GitHub
            </a>
            <div class="tooltip">
              <span class="tooltip-text">Almost there! Kohulan is still cooking up.. </span>
              <div class="tooltip-sparkle">✨</div>
            </div>
          </div>
          <a href="https://opensource.org/license/MIT" target="_blank" class="footer-link">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="8" r="7"></circle>
              <polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"></polyline>
            </svg>
            MIT License
          </a>
          <a href="#" class="footer-link" @click.prevent="showPrivacyPolicy">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14,2 14,8 20,8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
              <polyline points="10,9 9,9 8,9"></polyline>
            </svg>
            Privacy Policy
          </a>
        </div>
      </div>
    </div>
  </footer>
</template>

<script>
import { mapActions } from 'vuex'

export default {
  name: 'AppFooter',
  computed: {
    currentYear() {
      return new Date().getFullYear()
    }
  },
  methods: {
    ...mapActions(['showPrivacyPolicy'])
  }
}
</script>

<style lang="scss" scoped>
:root {
  /* Base theme colors - light mode defaults */
  --footer-bg: linear-gradient(135deg,
      rgba(99, 102, 241, 0.05) 0%,
      rgba(139, 69, 19, 0.03) 25%,
      rgba(99, 102, 241, 0.08) 50%,
      rgba(168, 85, 247, 0.06) 75%,
      rgba(99, 102, 241, 0.04) 100%);
  --primary: #6366f1;
  --secondary: #8b4513;
  --accent: #a855f7;
  --primary-light: rgba(99, 102, 241, 0.1);
  --primary-border: rgba(99, 102, 241, 0.2);

  /* Text colors */
  --text-heading: #0f172a;
  --text-body: #334155;
  --text-muted: #64748b;
  --text-light: #94a3b8;

  /* Enhanced gradients and effects */
  --primary-gradient: linear-gradient(135deg, #4338ca 0%, #6366f1 50%, #8b5cf6 100%);
  --coffee-gradient: linear-gradient(45deg, #8b4513 0%, #a0522d 50%, #8b4513 100%);
  --primary-shadow: rgba(99, 102, 241, 0.3);
  --glow-effect: 0 0 20px rgba(99, 102, 241, 0.2);
  --card-bg: white;
  --card-border: #e2e8f0;
}

/* Dark mode colors */
@media (prefers-color-scheme: dark) {
  :root {
    --footer-bg: linear-gradient(135deg,
        rgba(99, 102, 241, 0.08) 0%,
        rgba(139, 69, 19, 0.05) 25%,
        rgba(99, 102, 241, 0.12) 50%,
        rgba(168, 85, 247, 0.08) 75%,
        rgba(99, 102, 241, 0.06) 100%);
    --primary: #818cf8;
    --secondary: #d2691e;
    --accent: #c084fc;
    --primary-light: rgba(129, 140, 248, 0.15);
    --primary-border: rgba(129, 140, 248, 0.2);

    /* Text colors - inverted for dark mode */
    --text-heading: #f1f5f9;
    --text-body: #e2e8f0;
    --text-muted: #cbd5e1;
    --text-light: #94a3b8;

    /* Dark mode specific backgrounds */
    --card-bg: #1e293b;
    --card-border: #334155;

    /* Enhanced dark mode gradients */
    --primary-gradient: linear-gradient(135deg, #4338ca 0%, #6366f1 50%, #8b5cf6 100%);
    --coffee-gradient: linear-gradient(45deg, #a0522d 0%, #cd853f 50%, #a0522d 100%);
    --glow-effect: 0 0 25px rgba(129, 140, 248, 0.3);
  }
}

/* Component Styles */
.app-footer {
  background: var(--footer-bg);
  position: relative;
  overflow: hidden;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  height: auto;
  /* Changed from fixed height to auto */
  min-height: 50px;
  /* Minimum height to ensure content fits */
  padding: 5px 0;
  /* Add a small padding for vertical spacing */
  border-top: 2px solid transparent;
  border-image: var(--primary-gradient) 1;
  backdrop-filter: blur(15px) saturate(180%);
  box-shadow:
    0 -8px 32px rgba(99, 102, 241, 0.12),
    0 -4px 16px rgba(168, 85, 247, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
  transition: all 0.3s ease;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(90deg,
        transparent 0%,
        rgba(99, 102, 241, 0.05) 25%,
        rgba(168, 85, 247, 0.05) 50%,
        rgba(99, 102, 241, 0.05) 75%,
        transparent 100%);
    animation: shimmer 8s linear infinite;
    z-index: 0;
  }

  // Enhanced floating orbs
  &::after {
    content: '';
    position: absolute;
    top: -40px;
    right: -40px;
    width: 120px;
    height: 120px;
    border-radius: 50%;
    background: radial-gradient(circle,
        rgba(99, 102, 241, 0.15) 0%,
        rgba(168, 85, 247, 0.1) 50%,
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
    top: -20px;
    left: -20px;
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

  .footer-content {
    max-width: 100%;
    margin: 0;
    padding: 0 2rem;
    position: relative;
    z-index: 1;
    height: 100%;

    @media (max-width: 768px) {
      padding: 0 1rem;
    }
  }

  // Streamlined single-row footer layout
  .footer-main {
    display: flex;
    justify-content: space-between;
    align-items: center;
    height: 100%;
    gap: 2rem;
    width: 100%;

    @media (max-width: 968px) {
      gap: 1rem;
    }

    @media (max-width: 768px) {
      flex-direction: column;
      gap: 0.5rem;
      padding: 0.5rem 0;
      justify-content: center;
    }
  }

  // Left: Copyright section
  .copyright-section {
    flex-shrink: 0;
    min-width: fit-content;

    .copyright-text {
      font-size: 0.9rem;
      font-weight: 700;
      letter-spacing: 1px;
      color: var(--primary);
      text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
      position: relative;
      transition: all 0.3s ease;

      .marcus-text {
        font-family: 'GmarketSansLight', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        color: var(--primary);
      }

      &:hover {
        transform: translateY(-1px);
        text-shadow: 0 4px 8px rgba(99, 102, 241, 0.3);
      }

      @media (max-width: 768px) {
        font-size: 0.85rem;
      }
    }
  }

  // Center: Credits with tagline
  .center-section {
    flex: 1;
    text-align: center;
    max-width: 700px;
    margin: 0 auto;

    @media (max-width: 968px) {
      max-width: 500px;
    }

    .credits {
      font-size: 0.85rem;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.25rem;
      flex-wrap: nowrap;
      line-height: 1.4;
      white-space: nowrap;
      overflow: hidden;

      @media (max-width: 968px) {
        font-size: 0.8rem;
        gap: 0.2rem;
      }

      @media (max-width: 768px) {
        font-size: 0.7rem;
        gap: 0.15rem;
      }

      @media (max-width: 580px) {
        font-size: 0.65rem;
        gap: 0.1rem;
      }

      a {
        color: var(--primary);
        text-decoration: none;
        font-weight: 600;
        transition: all 0.3s ease;
        position: relative;

        &:hover {
          text-decoration: underline;
          transform: translateY(-1px);
          text-shadow: 0 2px 4px rgba(99, 102, 241, 0.3);
        }
      }

      .coffee-icon {
        width: 14px;
        height: 14px;
        background: var(--coffee-gradient);
        border-radius: 2px;
        margin: 0 0.2rem;
        animation: steam-dance 4s infinite ease-in-out;
        filter: drop-shadow(0 2px 4px rgba(201, 101, 29, 0.3)) drop-shadow(0 0 8px rgba(139, 69, 19, 0.2));
        transition: all 0.3s ease;
        flex-shrink: 0;
        position: relative;
        overflow: visible;

        // Enhanced steam effect
        &::before {
          content: '☕';
          position: absolute;
          top: -2px;
          left: 50%;
          transform: translateX(-50%);
          font-size: 12px;
          opacity: 0;
          animation: steam-rise 3s infinite ease-in-out;
        }

        &::after {
          content: '';
          position: absolute;
          top: -1px;
          left: 50%;
          transform: translateX(-50%);
          width: 2px;
          height: 6px;
          background: linear-gradient(to top, transparent, rgba(255, 255, 255, 0.6));
          border-radius: 1px;
          animation: steam-wisp 2s infinite ease-in-out;
        }

        @media (max-width: 768px) {
          width: 12px;
          height: 12px;
          margin: 0 0.15rem;
        }

        @media (max-width: 580px) {
          width: 10px;
          height: 10px;
          margin: 0 0.1rem;
        }

        &:hover {
          transform: scale(1.2) rotate(10deg);
          filter: drop-shadow(0 4px 8px rgba(139, 69, 19, 0.4)) drop-shadow(0 0 12px rgba(139, 69, 19, 0.3)) drop-shadow(0 0 20px rgba(160, 82, 45, 0.2));
        }
      }
    }
  }

  // Right: Links with icons
  .links-section {
    display: flex;
    gap: 1.5rem;
    flex-shrink: 0;
    min-width: fit-content;

    @media (max-width: 968px) {
      gap: 1rem;
    }

    @media (max-width: 768px) {
      gap: 1rem;
      justify-content: center;
    }

    .footer-link {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      text-decoration: none;
      color: var(--text-muted);
      font-size: 0.9rem;
      font-weight: 600;
      transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
      white-space: nowrap;
      padding: 0.4rem 0.8rem;
      border-radius: 12px;
      position: relative;
      background: linear-gradient(135deg,
          rgba(99, 102, 241, 0.03) 0%,
          rgba(168, 85, 247, 0.02) 100%);
      border: 1px solid rgba(99, 102, 241, 0.1);
      overflow: hidden;

      // Animated background gradient
      &::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg,
            transparent 0%,
            rgba(99, 102, 241, 0.1) 50%,
            transparent 100%);
        transition: left 0.5s ease;
        z-index: 0;
      }

      &::after {
        content: '';
        position: absolute;
        bottom: 0;
        left: 50%;
        transform: translateX(-50%);
        width: 0;
        height: 2px;
        background: var(--primary-gradient);
        border-radius: 1px;
        transition: width 0.3s ease;
        z-index: 1;
      }

      svg {
        color: var(--primary);
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        filter: drop-shadow(0 2px 4px rgba(99, 102, 241, 0.2));
        z-index: 2;
        position: relative;
      }

      span {
        z-index: 2;
        position: relative;
      }

      &:hover {
        color: var(--primary);
        transform: translateY(-3px) scale(1.05);
        background: linear-gradient(135deg,
            rgba(99, 102, 241, 0.1) 0%,
            rgba(168, 85, 247, 0.08) 100%);
        border-color: rgba(99, 102, 241, 0.3);
        box-shadow:
          0 8px 25px rgba(99, 102, 241, 0.2),
          0 4px 12px rgba(168, 85, 247, 0.1),
          var(--glow-effect);

        &::before {
          left: 0;
        }

        &::after {
          width: 80%;
        }

        svg {
          transform: scale(1.2) rotate(8deg);
          filter: drop-shadow(0 4px 8px rgba(99, 102, 241, 0.3)) drop-shadow(0 0 12px rgba(99, 102, 241, 0.2));
          color: var(--accent);
        }
      }

      &:active {
        transform: translateY(-1px) scale(1.02);
      }

      @media (max-width: 968px) {
        font-size: 0.85rem;
        gap: 0.4rem;
        padding: 0.3rem 0.6rem;
      }

      @media (max-width: 768px) {
        font-size: 0.8rem;
        gap: 0.3rem;
        padding: 0.25rem 0.5rem;
      }
    }
  }
}

// Enhanced animations
@keyframes steam-dance {

  0%,
  100% {
    transform: translateY(0) rotate(0deg);
    opacity: 1;
  }

  25% {
    transform: translateY(-1px) rotate(3deg);
    opacity: 0.9;
  }

  50% {
    transform: translateY(-2px) rotate(-2deg);
    opacity: 0.95;
  }

  75% {
    transform: translateY(-1px) rotate(4deg);
    opacity: 0.85;
  }
}

@keyframes steam-rise {
  0% {
    opacity: 0;
    transform: translateX(-50%) translateY(0) scale(0.5);
  }

  50% {
    opacity: 0.6;
    transform: translateX(-50%) translateY(-8px) scale(1);
  }

  100% {
    opacity: 0;
    transform: translateX(-50%) translateY(-15px) scale(1.2);
  }
}

@keyframes steam-wisp {

  0%,
  100% {
    opacity: 0;
    transform: translateX(-50%) scaleY(0);
  }

  50% {
    opacity: 0.8;
    transform: translateX(-50%) scaleY(1);
  }
}

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
    transform: translateY(0) rotate(0deg);
    opacity: 0.8;
  }

  33% {
    transform: translateY(-10px) rotate(120deg);
    opacity: 0.6;
  }

  66% {
    transform: translateY(-5px) rotate(240deg);
    opacity: 0.9;
  }
}

@keyframes float-reverse {

  0%,
  100% {
    transform: translateY(0) rotate(0deg) scale(1);
    opacity: 0.6;
  }

  50% {
    transform: translateY(-8px) rotate(180deg) scale(1.1);
    opacity: 0.4;
  }
}

@keyframes pulse-glow {

  0%,
  100% {
    transform: translate(-50%, -50%) scale(1);
    opacity: 0.3;
  }

  50% {
    transform: translate(-50%, -50%) scale(1.2);
    opacity: 0.6;
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

// Legacy steam animation (keeping for compatibility)
@keyframes steam {

  0%,
  100% {
    transform: translateY(0) rotate(0);
    opacity: 1;
  }

  25% {
    transform: translateY(-1px) rotate(2deg);
    opacity: 0.8;
  }

  50% {
    transform: translateY(-2px) rotate(3deg);
    opacity: 0.9;
  }

  75% {
    transform: translateY(-1px) rotate(-1deg);
    opacity: 0.7;
  }
}

// Enhanced pulse animation
@keyframes pulse {

  0%,
  100% {
    transform: scale(1);
    opacity: 0.6;
  }

  50% {
    transform: scale(1.15);
    opacity: 0.3;
  }
}

// Tooltip Styles
.footer-link-wrapper {
  position: relative;
  display: inline-block;
}

.tooltip {
  position: absolute;
  right: 100%;
  top: 50%;
  transform: translateY(-50%) translateX(-8px);
  background: linear-gradient(135deg,
      rgba(99, 102, 241, 0.95) 0%,
      rgba(168, 85, 247, 0.95) 100%);
  color: white;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 0.8rem;
  font-weight: 500;
  white-space: nowrap;
  z-index: 1000;
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  backdrop-filter: blur(10px);
  box-shadow:
    0 8px 25px rgba(99, 102, 241, 0.3),
    0 4px 12px rgba(168, 85, 247, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.1);

  &::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 100%;
    transform: translateY(-50%);
    border: 6px solid transparent;
    border-left-color: rgba(99, 102, 241, 0.95);
    filter: drop-shadow(0 2px 4px rgba(99, 102, 241, 0.2));
  }

  .tooltip-text {
    display: inline-block;
    animation: none;
    transition: all 0.3s ease;
  }

  .tooltip-sparkle {
    position: absolute;
    top: -5px;
    right: -5px;
    font-size: 12px;
    opacity: 0;
    transform: scale(0.5) rotate(0deg);
    transition: all 0.3s ease;
    animation: sparkle 2s ease-in-out infinite;
  }
}

.footer-link-wrapper:hover .tooltip {
  opacity: 1;
  visibility: visible;
  transform: translateY(-50%) translateX(-12px) scale(1.02);

  .tooltip-text {
    animation: glow 1.5s ease-in-out infinite alternate;
  }

  .tooltip-sparkle {
    opacity: 1;
    transform: scale(1) rotate(180deg);
  }
}

// Tooltip animations
@keyframes glow {
  0% {
    text-shadow: 0 0 5px rgba(255, 255, 255, 0.5);
  }

  100% {
    text-shadow: 0 0 10px rgba(255, 255, 255, 0.8), 0 0 15px rgba(255, 255, 255, 0.4);
  }
}

@keyframes sparkle {

  0%,
  100% {
    transform: scale(1) rotate(0deg);
    opacity: 0.7;
  }

  25% {
    transform: scale(1.2) rotate(90deg);
    opacity: 1;
  }

  50% {
    transform: scale(0.8) rotate(180deg);
    opacity: 0.8;
  }

  75% {
    transform: scale(1.1) rotate(270deg);
    opacity: 0.9;
  }
}
</style>