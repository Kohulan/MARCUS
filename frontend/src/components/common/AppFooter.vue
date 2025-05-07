<template>
  <footer class="app-footer">
    <div class="footer-content">
      <!-- Main content area -->
      <div class="main-section">
        <!-- Logo and branding -->
        <div class="branding">
          <div class="logo">MARCUS <span class="badge">NP</span></div>
          <div class="tagline">Molecular Annotation and Recognition for Curating Unravelled Structures</div>

          <!-- Social links below tagline -->
          <div class="social-links">
            <a href="https://github.com/Kohulan/MARCUS" target="_blank" aria-label="GitHub" class="social-link">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path
                  d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22">
                </path>
              </svg>
            </a>
            <a href="mailto:kohulan.rajan@uni-jena.de" aria-label="Email" class="social-link">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
                <polyline points="22,6 12,13 2,6"></polyline>
              </svg>
            </a>
            <a href="https://cheminf.uni-jena.de/" target="_blank" aria-label="Website" class="social-link">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="2" y1="12" x2="22" y2="12"></line>
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z">
                </path>
              </svg>
            </a>
          </div>
        </div>

        <!-- Resources section -->
        <div class="resources-section">
          <div class="resources-container">
            <!-- Resources heading directly above DECIMER -->
            <h3 class="resources-heading">Resources</h3>

            <div class="resources-items">
              <a href="https://decimer.ai" target="_blank" class="resource-link">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="16 18 22 12 16 6"></polyline>
                  <polyline points="8 6 2 12 8 18"></polyline>
                </svg>
                <span>DECIMER</span>
              </a>
              <a href="https://coconut.naturalproducts.net/" target="_blank" class="resource-link">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
                  <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
                  <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
                </svg>
                <span>COCONUT</span>
              </a>
              <div class="resource-group">
                <a href="https://naturalprducts.net/" target="_blank" class="resource-link">
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none"
                    stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
                    <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
                    <line x1="6" y1="6" x2="6.01" y2="6"></line>
                    <line x1="6" y1="18" x2="6.01" y2="18"></line>
                  </svg>
                  <span>Natural Products Services</span>
                </a>

                <!-- Coming Soon banner next to Natural Products Services -->
                <div class="coming-soon-banner">
                  <a href="https://github.com/Kohulan/MARCUS" target="_blank" class="coming-soon-link">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
                      stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path
                        d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22">
                      </path>
                    </svg>
                    <span>Source Code</span>
                    <span class="coming-soon-text">Coming Soon</span>
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Bottom credits area -->
      <div class="bottom-section">
        <div class="copyright">&copy; {{ currentYear }} MARCUS</div>

        <div class="credits">
          Crafted with
          <svg class="coffee-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 8h1a4 4 0 0 1 0 8h-1"></path>
            <path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"></path>
            <line x1="6" y1="1" x2="6" y2="4"></line>
            <line x1="10" y1="1" x2="10" y2="4"></line>
            <line x1="14" y1="1" x2="14" y2="4"></line>
          </svg>
          by <a href="https://kohulanr.com" target="_blank">Kohulan Rajan</a> @ <a
            href="https://github.com/Steinbeck-Lab" target="_blank">Steinbeck Lab</a>
        </div>

        <div class="license">
          <svg class="license-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="8" r="7"></circle>
            <polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"></polyline>
          </svg>
          <a href="https://opensource.org/license/MIT" target="_blank">MIT License</a>
        </div>
      </div>
    </div>
  </footer>
</template>

<script>
export default {
  name: 'AppFooter',
  computed: {
    currentYear() {
      return new Date().getFullYear()
    }
  }
}
</script>

<style lang="scss" scoped>
:root {
  /* Base theme colors - light mode defaults */
  --footer-bg: linear-gradient(to right, rgba(99, 102, 241, 0.03), rgba(99, 102, 241, 0.08));
  --primary: #6366f1;
  --primary-light: rgba(99, 102, 241, 0.1);
  --primary-border: rgba(99, 102, 241, 0.2);

  /* Text colors */
  --text-heading: #0f172a;
  /* Very dark - high contrast for headings */
  --text-body: #334155;
  /* Dark gray for body text */
  --text-muted: #64748b;
  /* Medium gray for less important text */
  --text-light: #94a3b8;
  /* Lighter gray for subtle text */


  /* Gradients and effects */
  --primary-gradient: linear-gradient(90deg, #4338ca, #6366f1);
  /* Darker gradient for better visibility */
  --primary-shadow: rgba(99, 102, 241, 0.3);
  --card-bg: white;
  --card-border: #e2e8f0;

  /* Fixed logo color - won't change in dark mode */
  --logo-color: #6366f1;
  --logo-badge-bg: #6366f1;
}

/* Dark mode colors */
@media (prefers-color-scheme: dark) {
  :root {
    --footer-bg: linear-gradient(to right, rgba(99, 102, 241, 0.05), rgba(99, 102, 241, 0.1));
    --primary: #818cf8;
    /* Lighter indigo in dark mode */
    --primary-light: rgba(129, 140, 248, 0.15);
    --primary-border: rgba(129, 140, 248, 0.2);

    /* Text colors - inverted for dark mode */
    --text-heading: #f1f5f9;
    /* Very light for headings */
    --text-body: #e2e8f0;
    /* Light gray for body text */
    --text-muted: #cbd5e1;
    /* Medium light gray */
    --text-light: #94a3b8;
    /* Dim gray for subtle text */

    /* Dark mode specific backgrounds */
    --card-bg: #1e293b;
    /* Dark blue gray */
    --card-border: #334155;
    /* Darker border color */

    /* Primary gradient for dark mode */
    --primary-gradient: linear-gradient(90deg, #4338ca, #6366f1);
  }
}

/* Component Styles - Now using CSS variables */
.app-footer {
  background: var(--footer-bg);
  position: relative;
  overflow: hidden;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;

  // Decorative elements
  &::before {
    content: '';
    position: absolute;
    top: -100px;
    right: -100px;
    width: 300px;
    height: 300px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(99, 102, 241, 0.2) 0%, transparent 70%);
    opacity: 0.3;
    z-index: 0;
  }

  &::after {
    content: '';
    position: absolute;
    bottom: -50px;
    left: -50px;
    width: 200px;
    height: 200px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, transparent 70%);
    opacity: 0.3;
    z-index: 0;
  }

  .footer-content {
    max-width: 1400px;
    margin: 0 auto;
    padding: 1.25rem;
    position: relative;
    z-index: 1;
  }

  // Main section with logo and resources
  .main-section {
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.75rem;

    @media (max-width: 1024px) {
      flex-direction: column;
      gap: 1.5rem;
    }
  }

  // Logo and branding
  .branding {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    max-width: 600px;

    .logo {
      font-size: 1.75rem;
      font-weight: 800;
      letter-spacing: 1px;
      margin: 0;
      background: var(--gradient-primary);
      /* Fixed color that doesn't change in dark mode */
      letter-spacing: 0.5px;
      display: flex;
      align-items: center;
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
      transform: translateZ(0);
      text-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);

      .badge {
        font-size: 0.7rem;
        margin-left: 0.5rem;
        padding: 0.1rem 0.4rem;
        background-color: var(--logo-badge-bg);
        /* Fixed color that doesn't change in dark mode */
        color: white;
        border-radius: 4px;
        font-weight: 600;
        transform: translateY(-1px);
      }
    }

    .tagline {
      font-size: 0.95rem;
      color: var(--text-body);
      white-space: nowrap;

      @media (max-width: 1200px) {
        white-space: normal;
      }
    }

    // Social links below tagline
    .social-links {
      display: flex;
      gap: 0.75rem;
      margin-top: 0.5rem;

      .social-link {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        border-radius: 50%;
        background-color: var(--primary-light);
        color: var(--primary);
        transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);

        &:hover {
          background-color: var(--primary);
          color: white;
          transform: translateY(-3px);
          box-shadow: 0 8px 16px var(--primary-shadow);
        }
      }
    }
  }

  // Resources section - redesigned
  .resources-section {
    display: flex;
    flex-direction: column;

    @media (max-width: 1024px) {
      width: 100%;
    }

    .resources-container {
      display: flex;
      flex-direction: column;
      align-items: flex-end;

      @media (max-width: 1024px) {
        align-items: flex-start;
      }
    }

    // Resources heading with improved visibility
    .resources-heading {
      font-weight: 700;
      font-size: 1.15rem;
      color: var(--text-heading);
      margin: 0 0 0.75rem 0;
      position: relative;
      display: inline-block;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      align-self: flex-start;

      &::after {
        content: '';
        position: absolute;
        bottom: -4px;
        left: 0;
        width: 100%;
        height: 3px;
        /* Increased from 2px to make line more visible */
        background-color: var(--primary);
        border-radius: 1px;
      }
    }

    .resources-items {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      align-items: flex-start;

      .resource-link {
        display: flex;
        align-items: center;
        text-decoration: none;
        color: var(--text-body);
        font-size: 0.95rem;
        font-weight: 500;
        transition: all 0.2s ease;
        gap: 0.5rem;
        white-space: nowrap;

        svg {
          color: var(--primary);
          transition: transform 0.2s ease;
        }

        &:hover {
          color: var(--primary);
          transform: translateY(-2px);

          svg {
            transform: scale(1.1);
          }
        }
      }

      // Resource group for Natural Products + Coming Soon
      .resource-group {
        display: flex;
        align-items: center;
        gap: 0.75rem;

        @media (max-width: 768px) {
          flex-direction: column;
          align-items: flex-start;
          gap: 0.5rem;
        }
      }

      // Coming Soon banner with improved visibility
      .coming-soon-banner {
        .coming-soon-link {
          display: flex;
          align-items: center;
          text-decoration: none;
          color: var(--text-body);
          font-size: 0.95rem;
          font-weight: 500;
          gap: 0.5rem;
          position: relative;

          svg {
            color: var(--primary);
            transition: transform 0.3s ease;
          }

          /* Improved Coming Soon text with better contrast */
          .coming-soon-text {
            font-size: 0.7rem;
            font-weight: 700;
            /* Increased from 600 */
            background: #4338ca;
            /* Fixed dark color that works in both modes */
            color: white;
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
            box-shadow: 0 2px 8px rgba(67, 56, 202, 0.4);
            /* Darker shadow for better visibility */
            position: relative;
            overflow: hidden;

            // Shine animation effect
            &::after {
              content: '';
              position: absolute;
              top: -50%;
              left: -50%;
              width: 200%;
              height: 200%;
              background: linear-gradient(90deg,
                  rgba(255, 255, 255, 0) 0%,
                  rgba(255, 255, 255, 0.5) 50%,
                  rgba(255, 255, 255, 0) 100%);
              transform: rotate(25deg) translateY(60%);
              animation: shine 3s infinite;
            }
          }

          &:hover {
            color: var(--primary);
            transform: translateY(-2px);

            svg {
              transform: scale(1.1) rotate(10deg);
            }

            .coming-soon-text {
              box-shadow: 0 4px 12px rgba(67, 56, 202, 0.5);
              /* Darker shadow on hover */
            }
          }
        }
      }
    }
  }

  // Bottom credits section
  .bottom-section {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 0.75rem;
    border-top: 1px solid var(--primary-border);
    font-size: 0.85rem;
    color: var(--text-muted);

    @media (max-width: 768px) {
      flex-direction: column;
      gap: 0.75rem;
      align-items: center;
      text-align: center;
    }

    a {
      color: var(--primary);
      text-decoration: none;
      font-weight: 500;
      transition: all 0.2s ease;

      &:hover {
        text-decoration: underline;
      }
    }

    .credits,
    .license {
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }

    /* Fixed coffee cup color */
    .coffee-icon {
      width: 12px;
      height: 12px;
      color: #6f4e37;
      margin: 0 0.2rem;
      animation: steam 3s infinite ease-in-out;
      filter: drop-shadow(0 1px 1px rgba(0, 0, 0, 0.1));
    }

    .license-icon {
      color: var(--primary);
    }
  }
}

// Animation for Coming Soon badge
@keyframes shine {
  0% {
    transform: rotate(25deg) translateY(60%);
  }

  100% {
    transform: rotate(25deg) translateY(-100%);
  }
}

@keyframes steam {

  0%,
  100% {
    transform: translateY(0) rotate(0);
  }

  50% {
    transform: translateY(-3px) rotate(5deg);
  }
}
</style>