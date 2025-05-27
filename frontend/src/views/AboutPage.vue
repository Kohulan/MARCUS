<template>
  <section id="about" class="about-section">
    <!-- Enhanced Background Elements -->
    <div class="hero-bg">
      <div class="particle particle-1"></div>
      <div class="particle particle-2"></div>
      <div class="particle particle-3"></div>
      <div class="particle particle-4"></div>
      <div class="particle particle-5"></div>
      <div class="circle-glow circle-glow-1"></div>
      <div class="circle-glow circle-glow-2"></div>
      <div class="hexagon-grid"></div>
    </div>

    <!-- Main Content Container -->
    <div class="container">
      <!-- Enhanced Section Header with Animation -->
      <div class="section-header reveal-animation">
        <div class="section-tag">About <span class="marcus-text">MARCUS</span></div>
        <h2 class="section-title">Unraveling Chemical Structures with AI</h2>
        <p class="section-description">
          Discover the story, mission, and team behind <span class="marcus-text">MARCUS</span> - Molecular Annotation and Recognition for Curating
          Unravelled Structures
        </p>
      </div>

      <!-- Project Overview with Enhanced Visual Design -->
      <div class="content-block overview-block reveal-animation-delay-1">
        <div class="block-decoration"></div>
        <h3 class="block-title">
          <vue-feather type="info" class="title-icon"></vue-feather>
          Project Overview
        </h3>
        <div class="overview-content">
          <div class="overview-text">
            <p>
              <strong><span class="marcus-text">MARCUS</span></strong> (Molecular Annotation and Recognition for Curating Unravelled Structures) is an
              advanced computational platform designed to revolutionize the extraction and annotation of chemical
              structures from scientific literature. By leveraging cutting-edge AI technologies, <span class="marcus-text">MARCUS</span> automates the
              previously labor-intensive process of manually identifying, extracting, and digitizing chemical structures
              from research papers.
            </p>
            <p>
              Developed at the Steinbeck Lab, <span class="marcus-text">MARCUS</span> bridges the gap between the vast knowledge hidden in the scientific
              literature and the digital representation required for computational analysis, database integration, and
              further research applications.
            </p>
          </div>
          <div class="overview-image">
            <div class="image-container">
              <div class="image-glow"></div>
              <img src="@/assets/logo.png" alt="MARCUS Logo" class="logo-large" />
            </div>
          </div>
        </div>
      </div>

      <!-- Team Section with Enhanced Design -->
      <div class="content-block team-block reveal-animation-delay-2">
        <div class="block-decoration"></div>
        <h3 class="block-title">
          <vue-feather type="users" class="title-icon"></vue-feather>
          Meet the Team
        </h3>
        <div class="team-content">
          <p class="team-intro">
            <span class="marcus-text">MARCUS</span> is developed by an interdisciplinary team of researchers at the Steinbeck Lab, bringing together
            expertise in cheminformatics, artificial intelligence, and software engineering.
          </p>

          <div class="team-grid">
            <div class="team-member hover-card">
              <div class="card-highlight"></div>
              <div class="member-photo kohulan">
                <div class="photo-glow"></div>
              </div>
              <div class="member-info">
                <h4>Kohulan Rajan</h4>
                <p class="member-role">Project Lead and Lead Developer</p>
                <p class="member-desc">Cheminformatics researcher specializing in deep learning and chemical structure
                  recognition</p>
                <div class="member-links">
                  <a href="https://github.com/Kohulan" target="_blank" class="member-link">
                    <vue-feather type="github" size="16"></vue-feather>
                  </a>
                  <a href="https://kohulanr.com" target="_blank" class="member-link">
                    <vue-feather type="globe" size="16"></vue-feather>
                  </a>
                </div>
              </div>
            </div>

            <div class="team-member hover-card">
              <div class="card-highlight"></div>
              <div class="member-photo christoph">
                <div class="photo-glow"></div>
              </div>
              <div class="member-info">
                <h4>Christoph Steinbeck</h4>
                <p class="member-role">Principal Investigator</p>
                <p class="member-desc">Professor of Analytical Chemistry, Cheminformatics and Chemometrics at
                  Friedrich-Schiller-University Jena</p>
                <div class="member-links">
                  <a href="https://github.com/steinbeck" target="_blank" class="member-link">
                    <vue-feather type="github" size="16"></vue-feather>
                  </a>
                  <a href="https://github.com/Steinbeck-Lab" target="_blank" class="member-link">
                    <vue-feather type="users" size="16"></vue-feather>
                  </a>
                </div>
              </div>
            </div>
          </div>

          <div class="team-cta glass-card">
            <div class="card-inner">
              <h4>Join the Community</h4>
              <p><span class="marcus-text">MARCUS</span> is an open-source project and we welcome contributions from the community.</p>
              <div class="team-buttons">
                <a href="https://github.com/Kohulan/MARCUS" target="_blank" class="btn btn-primary btn-glow">
                  <div class="btn-bg"></div>
                  <vue-feather type="github" class="btn-icon"></vue-feather>
                  <span>GitHub Repository</span>
                </a>
                <a href="https://github.com/Steinbeck-Lab" target="_blank" class="btn btn-secondary btn-pulse">
                  <vue-feather type="users" class="btn-icon"></vue-feather>
                  <span>Steinbeck Lab</span>
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Publications with Enhanced Visual Design -->
      <div class="content-block publications-block reveal-animation-delay-3">
        <div class="block-decoration"></div>
        <h3 class="block-title">
          <vue-feather type="book-open" class="title-icon"></vue-feather>
          Research & Publications
        </h3>
        <div class="publications-content">
          <p class="publications-intro">
            Learn more about the research behind <span class="marcus-text">MARCUS</span> and related technologies through our publications and others as
            well.
          </p>
          <div class="publications-list">
            <div class="publication hover-card">
              <div class="card-highlight"></div>
              <div class="publication-icon">
                <vue-feather type="file-text" size="24"></vue-feather>
                <div class="icon-glow"></div>
              </div>
              <div class="publication-info">
                <h4>DECIMER.ai: an open platform for automated optical chemical structure identification, segmentation
                  and recognition in scientific publications</h4>
                <p class="publication-authors">Rajan, K., Brinkhaus, H.O., Agea, I.A. Zielesny, A., Steinbeck, C.</p>
                <p class="publication-journal">Nat Commun, 14, 5045 (2023)</p>
                <a href="https://doi.org/10.1038/s41467-023-40648-7" target="_blank" class="publication-link">
                  <vue-feather type="external-link" size="14"></vue-feather>
                  <span>doi.org/10.1038/s41467-023-40648-7</span>
                </a>
              </div>
            </div>
            <div class="publication hover-card">
              <div class="card-highlight"></div>
              <div class="publication-icon">
                <vue-feather type="file-text" size="24"></vue-feather>
                <div class="icon-glow"></div>
              </div>
              <div class="publication-info">
                <h4>Advancements in hand-drawn chemical structure recognition through an enhanced DECIMER architecture
                </h4>
                <p class="publication-authors">Rajan, K., Brinkhaus, H.O., Zielesny, A., Steinbeck, C.</p>
                <p class="publication-journal">J Cheminform, 16, 78 (2024)</p>
                <a href="https://doi.org/10.1186/s13321-024-00901-5" target="_blank" class="publication-link">
                  <vue-feather type="external-link" size="14"></vue-feather>
                  <span>doi.org/10.1186/s13321-024-00901-5</span>
                </a>
              </div>
            </div>
            <div class="publication hover-card">
              <div class="card-highlight"></div>
              <div class="publication-icon">
                <vue-feather type="file-text" size="24"></vue-feather>
                <div class="icon-glow"></div>
              </div>
              <div class="publication-info">
                <h4>DECIMER-Segmentation: Automated extraction of chemical structure depictions from scientific
                  literature</h4>
                <p class="publication-authors">Rajan, K., Brinkhaus, H.O., Sorokina, M. et al.</p>
                <p class="publication-journal">J Cheminform, 13, 20 (2021)</p>
                <a href="https://doi.org/10.1186/s13321-021-00508-0" target="_blank" class="publication-link">
                  <vue-feather type="external-link" size="14"></vue-feather>
                  <span>doi.org/10.1186/s13321-021-00508-0</span>
                </a>
              </div>
            </div>
            <div class="publication hover-card">
              <div class="card-highlight"></div>
              <div class="publication-icon">
                <vue-feather type="file-text" size="24"></vue-feather>
                <div class="icon-glow"></div>
              </div>
              <div class="publication-info">
                <h4>MolNexTR: a generalized deep learning model for molecular image recognition</h4>
                <p class="publication-authors">Chen, Y., Leung, C.T., Huang, Y. et al.</p>
                <p class="publication-journal">J Cheminform 16, 141 (2024)</p>
                <a href="https://doi.org/10.1186/s13321-024-00926-w" target="_blank" class="publication-link">
                  <vue-feather type="external-link" size="14"></vue-feather>
                  <span>doi.org/10.1186/s13321-024-00926-w</span>
                </a>
              </div>
            </div>
            <div class="publication hover-card">
              <div class="card-highlight"></div>
              <div class="publication-icon">
                <vue-feather type="file-text" size="24"></vue-feather>
                <div class="icon-glow"></div>
              </div>
              <div class="publication-info">
                <h4>MolScribe: Robust molecular structure recognition with image-to-graph generation</h4>
                <p class="publication-authors">Qian Y., Guo J., Tu Z., Li Z., Coley C.W., Barzilay R.</p>
                <p class="publication-journal">J Chem Inf Model, 63(7):1925–34 (2023)</p>
                <a href="https://doi.org/10.1021/acs.jcim.2c01480" target="_blank" class="publication-link">
                  <vue-feather type="external-link" size="14"></vue-feather>
                  <span>doi.org/10.1021/acs.jcim.2c01480</span>
                </a>
              </div>
            </div>
            <div class="publication hover-card">
              <div class="card-highlight"></div>
              <div class="publication-icon">
                <vue-feather type="file-text" size="24"></vue-feather>
                <div class="icon-glow"></div>
              </div>
              <div class="publication-info">
                <h4>Docling: Document-level Pretraining for Scientific PDF Understanding</h4>
                <p class="publication-authors">Auer C., Lysak M., Nassar A., Dolfi M., Livathinos N., Vagenas P., et al.
                </p>
                <p class="publication-journal">arXiv [cs.CL] (2024)</p>
                <a href="https://arxiv.org/abs/2408.09869" target="_blank" class="publication-link">
                  <vue-feather type="external-link" size="14"></vue-feather>
                  <span>arxiv.org/abs/2408.09869</span>
                </a>
              </div>
            </div>
            <div class="publication hover-card">
              <div class="card-highlight"></div>
              <div class="publication-icon">
                <vue-feather type="file-text" size="24"></vue-feather>
                <div class="icon-glow"></div>
              </div>
              <div class="publication-info">
                <h4>COCONUT 2.0: a comprehensive overhaul and curation of the collection of open natural products
                  database</h4>
                <p class="publication-authors">Venkata Chandrasekhar, Kohulan Rajan, Sri Ram Sagar Kanakam, Nisha
                  Sharma, Viktor Weißenborn, Jonas Schaub, Christoph Steinbeck</p>
                <p class="publication-journal">Nucleic Acids Research, 2024; gkae1063</p>
                <a href="https://doi.org/10.1093/nar/gkae1063" target="_blank" class="publication-link">
                  <vue-feather type="external-link" size="14"></vue-feather>
                  <span>doi.org/10.1093/nar/gkae1063</span>
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Mission Statement with Enhanced Design -->
      <div class="content-block mission-block reveal-animation-delay-4">
        <div class="mission-overlay"></div>
        <div class="block-decoration mission-decoration"></div>
        <h3 class="block-title">
          <vue-feather type="target" class="title-icon"></vue-feather>
          Our Mission
        </h3>
        <div class="mission-content">
          <blockquote class="mission-quote">
            <span class="quote-mark quote-open">"</span>
            To accelerate chemical structure knowledge extraction from scientific literature using AI, making it
            accessible for research, drug discovery, and chemical database enrichment
            <span class="quote-mark quote-close">"</span>
          </blockquote>

          <p class="mission-details">
            At <span class="marcus-text">MARCUS</span>, we're committed to democratizing access to chemical knowledge hidden in scientific literature.
            Our project aims to make chemical structures discoverable, searchable, and accessible to researchers
            worldwide, enhancing natural products databases like COCONUT and enabling new frontiers in drug discovery
            research.
          </p>
        </div>
      </div>

      <!-- Features link with Enhanced Design -->
      <div class="content-block cta-block glass-card reveal-animation-delay-5">
        <div class="card-inner">
          <h3 class="block-title">
            <vue-feather type="layers" class="title-icon"></vue-feather>
            Discover <span class="marcus-text">MARCUS</span> Features
          </h3>
          <div class="cta-content-centered">
            <p class="cta-text">
              Curious about what <span class="marcus-text">MARCUS</span> can do? Explore our comprehensive feature set, including structure extraction,
              annotation, and more.
            </p>
            <button class="btn btn-primary btn-glow" @click="goToFeatures">
              <div class="btn-bg"></div>
              <vue-feather type="layers" class="btn-icon"></vue-feather>
              <span>View Features</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Call to Action with Enhanced Design -->
      <div class="about-cta reveal-animation-delay-6">
        <div class="cta-blob-1"></div>
        <div class="cta-blob-2"></div>
        <div class="cta-content">
          <h3>Ready to Extract Chemical Structures?</h3>
          <p>Experience the power of <span class="marcus-text">MARCUS</span> by uploading your first document</p>
        </div>
        <button class="btn btn-get-started" @click="goHome">
          <div class="btn-bg"></div>
          <vue-feather type="upload-cloud" class="btn-icon"></vue-feather>
          <span>Get Started</span>
        </button>
      </div>

      <!-- Close button for modal view -->
      <button v-if="showCloseButton" class="close-btn" @click="$emit('close')">
        <vue-feather type="x" size="24"></vue-feather>
        <span>Close</span>
      </button>
    </div>
  </section>
</template>

<script>
export default {
  name: 'AboutPage',

  props: {
    showCloseButton: {
      type: Boolean,
      default: false
    }
  },

  mounted() {
    // Initialize animations on mount
    this.initializeAnimations();
  },

  methods: {
    scrollToUpload() {
      // Check if router exists before using it
      if (this.$router) {
        this.$router.push('/');

        // Use setTimeout to ensure navigation is complete before scrolling
        setTimeout(() => {
          const uploadSection = document.querySelector('.pdf-column');
          if (uploadSection) {
            uploadSection.scrollIntoView({ behavior: 'smooth' });
          }
        }, 300);
      } else {
        // If router is not available, try to find the upload section directly
        // This will work if the component is used on the same page as the upload section
        const uploadSection = document.querySelector('.pdf-column');
        if (uploadSection) {
          uploadSection.scrollIntoView({ behavior: 'smooth' });
        } else {
          // If neither router nor direct access works, emit an event that parent components can listen for
          this.$emit('navigate-to-upload');
        }
      }
    },

    goToFeatures() {
      // Show features section
      this.$store.dispatch('showFeatures');
    },

    goHome() {
      // Hide the about page to return to home view without page reload
      this.$store.dispatch('hideAbout');
    },

    initializeAnimations() {
      // Enhanced observer for ultra-smooth reveal animations
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            // Add a small delay to make the animation feel more natural
            setTimeout(() => {
              entry.target.classList.add('visible');
            }, 50);
            observer.unobserve(entry.target);
          }
        });
      }, { 
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px' // Start animation 50px before element is fully visible
      });

      // Enhanced particle performance with requestAnimationFrame
      const particles = document.querySelectorAll('.particle');
      particles.forEach(particle => {
        particle.style.willChange = 'transform, opacity';
        particle.style.backfaceVisibility = 'hidden';
        particle.style.perspective = '1000px';
      });

      // Observe all elements with reveal animations
      document.querySelectorAll('.reveal-animation, .reveal-animation-delay-1, .reveal-animation-delay-2, .reveal-animation-delay-3, .reveal-animation-delay-4, .reveal-animation-delay-5, .reveal-animation-delay-6').forEach(element => {
        observer.observe(element);
      });

      // Preload animations to prevent jank
      this.$nextTick(() => {
        const elementsToPreload = document.querySelectorAll('.team-member, .publication, .content-block');
        elementsToPreload.forEach(el => {
          el.style.willChange = 'transform, box-shadow';
          el.style.backfaceVisibility = 'hidden';
        });
      });
    }
  }
}
</script>

<style lang="scss" scoped>
// About Page Specific Variables - now compatible with theme system
.about-section {
  /* Enhanced ultra-smooth transitions for perfect animations */
  --transition-fast: 0.2s cubic-bezier(0.25, 0.46, 0.45, 0.94);
  --transition-smooth: 0.4s cubic-bezier(0.23, 1, 0.32, 1);
  --transition-elastic: 0.6s cubic-bezier(0.18, 0.89, 0.32, 1.28);
  --transition-ultra-smooth: 0.8s cubic-bezier(0.165, 0.84, 0.44, 1);
  --transition-bounce: 0.5s cubic-bezier(0.68, -0.55, 0.265, 1.55);
  --transition-expo: 0.7s cubic-bezier(0.19, 1, 0.22, 1);

  /* Theme-aware color overrides for special effects */
  --about-accent-color: #4F46E5;
  --about-accent-rgb: 79, 70, 229;
  --about-secondary-color: #EC4899;
  --about-secondary-rgb: 236, 72, 153;
  --about-tertiary-color: #06B6D4;
  --about-tertiary-rgb: 6, 182, 212;
}

// Base styles
.about-section {
  padding: 3rem 0 5rem;
  background: var(--color-bg);
  position: relative;
  overflow-y: auto;
  height: 100vh;
  font-family: var(--font-family);
  transition: background-color var(--transition-smooth), color var(--transition-smooth);

  // Enhanced Background Elements
  .hero-bg {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(135deg,
        rgba(var(--about-accent-rgb), 0.08) 0%,
        rgba(var(--about-secondary-rgb), 0.05) 50%,
        rgba(var(--about-tertiary-rgb), 0.06) 100%);
    z-index: 0;
    overflow: hidden;
    transition: background var(--transition-smooth);

    // Animated particles with ultra-smooth transitions
    .particle {
      position: absolute;
      border-radius: 50%;
      filter: blur(8px);
      opacity: 0.4;
      animation: float-particles 25s infinite var(--transition-ultra-smooth);
      will-change: transform, opacity;
      transform: translateZ(0);
      transition: opacity var(--transition-smooth);

      &.particle-1 {
        width: 150px;
        height: 150px;
        top: 10%;
        right: 15%;
        background: radial-gradient(circle at center,
            rgba(var(--about-accent-rgb), 0.25),
            rgba(var(--about-accent-rgb), 0));
        animation-duration: 40s;
        animation-delay: -5s;
        animation-timing-function: var(--transition-ultra-smooth);
      }

      &.particle-2 {
        width: 200px;
        height: 200px;
        bottom: 15%;
        left: 10%;
        background: radial-gradient(circle at center,
            rgba(var(--about-secondary-rgb), 0.2),
            rgba(var(--about-secondary-rgb), 0));
        animation-duration: 45s;
        animation-delay: -12s;
        animation-timing-function: var(--transition-ultra-smooth);
      }

      &.particle-3 {
        width: 120px;
        height: 120px;
        top: 35%;
        left: 20%;
        background: radial-gradient(circle at center,
            rgba(var(--about-tertiary-rgb), 0.18),
            rgba(var(--about-tertiary-rgb), 0));
        animation-duration: 35s;
        animation-delay: -8s;
        animation-timing-function: var(--transition-ultra-smooth);
      }

      &.particle-4 {
        width: 180px;
        height: 180px;
        bottom: 25%;
        right: 18%;
        background: radial-gradient(circle at center,
            rgba(var(--about-accent-rgb), 0.2),
            rgba(var(--about-accent-rgb), 0));
        animation-duration: 50s;
        animation-delay: -15s;
        animation-timing-function: var(--transition-ultra-smooth);
      }

      &.particle-5 {
        width: 100px;
        height: 100px;
        top: 65%;
        left: 40%;
        background: radial-gradient(circle at center,
            rgba(var(--about-tertiary-rgb), 0.15),
            rgba(var(--about-tertiary-rgb), 0));
        animation-duration: 42s;
        animation-delay: -10s;
        animation-timing-function: var(--transition-ultra-smooth);
      }
    }

    // Glowing circles
    .circle-glow {
      position: absolute;
      border-radius: 50%;
      filter: blur(40px);
      opacity: 0.1;
      transition: opacity var(--transition-smooth);

      &.circle-glow-1 {
        width: 600px;
        height: 600px;
        background: radial-gradient(circle at center,
            rgba(var(--about-accent-rgb), 0.3),
            rgba(var(--about-accent-rgb), 0));
        top: -200px;
        right: -200px;
        animation: pulse-glow 12s infinite alternate var(--transition-ultra-smooth);
      }

      &.circle-glow-2 {
        width: 500px;
        height: 500px;
        background: radial-gradient(circle at center,
            rgba(var(--about-tertiary-rgb), 0.25),
            rgba(var(--about-tertiary-rgb), 0));
        bottom: -200px;
        left: -100px;
        animation: pulse-glow 15s infinite alternate var(--transition-ultra-smooth);
      }
    }

    // Hexagon grid with theme-aware opacity
    .hexagon-grid {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background-image: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M30 5.5l20 10v29l-20 10-20-10v-29l20-10z' stroke='%234F46E5' stroke-opacity='0.06' fill='none' stroke-width='0.5'/%3E%3C/svg%3E");
      background-size: 60px 60px;
      opacity: 0.4;
      transition: opacity var(--transition-smooth);
    }
  }

  .container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 1.5rem;
    position: relative;
    z-index: 1;
  }

  // Animation classes with ultra-smooth transitions and perfect performance
  .reveal-animation,
  .reveal-animation-delay-1,
  .reveal-animation-delay-2,
  .reveal-animation-delay-3,
  .reveal-animation-delay-4,
  .reveal-animation-delay-5,
  .reveal-animation-delay-6 {
    opacity: 0;
    transform: translateY(40px) scale(0.95);
    transition: opacity var(--transition-ultra-smooth), 
                transform var(--transition-ultra-smooth),
                visibility var(--transition-smooth);
    will-change: transform, opacity;
    backface-visibility: hidden;
    perspective: 1000px;
    transform-style: preserve-3d;
    filter: blur(2px);

    &.visible {
      opacity: 1;
      transform: translateY(0) scale(1);
      visibility: visible;
      filter: blur(0px);
    }
  }

  .reveal-animation-delay-1 {
    transition-delay: 0.15s;
  }

  .reveal-animation-delay-2 {
    transition-delay: 0.3s;
  }

  .reveal-animation-delay-3 {
    transition-delay: 0.45s;
  }

  .reveal-animation-delay-4 {
    transition-delay: 0.6s;
  }

  .reveal-animation-delay-5 {
    transition-delay: 0.75s;
  }

  .reveal-animation-delay-6 {
    transition-delay: 0.9s;
  }

  // Enhanced Section header
  .section-header {
    text-align: center;
    margin-bottom: 4rem;
    position: relative;

    .section-tag {
      display: flex;
      justify-content: center;
      align-items: center;
      margin: 0 auto;
      background: rgba(var(--about-accent-rgb), 0.1);
      color: var(--color-primary);
      font-size: 0.875rem;
      font-weight: 600;
      padding: 0.5rem 1.5rem;
      border-radius: 30px;
      margin-bottom: 1.25rem;
      box-shadow: var(--shadow-sm);
      position: relative;
      overflow: hidden;
      max-width: max-content;
      transform: translateZ(0);
      will-change: transform, opacity;
      transition: all var(--transition-smooth);

      &:before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 50%;
        height: 100%;
        background: linear-gradient(90deg,
            rgba(255, 255, 255, 0) 0%,
            rgba(255, 255, 255, 0.4) 50%,
            rgba(255, 255, 255, 0) 100%);
        animation: shimmer 4s var(--transition-ultra-smooth) infinite;
      }
    }

    .section-title {
      font-size: 3rem;
      font-weight: 800;
      line-height: 1.2;
      margin: 0 0 1.25rem;
      background: var(--gradient-primary);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
      position: relative;
      display: inline-block;
      transition: all var(--transition-smooth);

      @media (max-width: 768px) {
        font-size: 2.25rem;
      }

      &:after {
        content: '';
        position: absolute;
        bottom: -10px;
        left: 50%;
        transform: translateX(-50%);
        width: 80px;
        height: 4px;
        border-radius: 2px;
        background: var(--gradient-primary);
        opacity: 0.7;
        transition: opacity var(--transition-smooth);
      }
    }

    .section-description {
      font-size: 1.25rem;
      font-weight: 400;
      color: var(--color-text-light);
      line-height: 1.6;
      max-width: 700px;
      margin: 1.5rem auto 0;
      transition: color var(--transition-smooth);
    }
  }

  // Enhanced content block styling
  .content-block {
    background: var(--color-card-bg);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border-radius: var(--radius-lg);
    padding: 2.5rem;
    box-shadow: var(--shadow-md);
    border: 1px solid var(--color-border);
    margin-bottom: 3.5rem;
    position: relative;
    overflow: hidden;
    transition: transform var(--transition-smooth), 
                box-shadow var(--transition-smooth),
                background-color var(--transition-smooth),
                border-color var(--transition-smooth);

    &:hover {
      transform: translateY(-8px) scale(1.02);
      box-shadow: var(--shadow-lg);

      .block-decoration {
        opacity: 0.7;
        transform: translate(20px, -20px) rotate(15deg) scale(1.1);
      }
    }

    .block-decoration {
      position: absolute;
      top: 0;
      right: 0;
      width: 150px;
      height: 150px;
      background: var(--gradient-primary);
      opacity: 0.08;
      border-radius: 70% 30% 30% 70% / 60% 40% 60% 40%;
      filter: blur(40px);
      z-index: 0;
      transition: all var(--transition-bounce);
      transform: translate(50px, -50px) rotate(0deg);
    }

    .block-title {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      font-size: 1.75rem;
      font-weight: 700;
      margin: 0 0 1.75rem;
      color: var(--color-heading);
      position: relative;
      z-index: 1;
      transition: color var(--transition-smooth);

      .title-icon {
        color: var(--color-primary);
        filter: drop-shadow(0 2px 6px rgba(var(--about-accent-rgb), 0.4));
        animation: pulse-icon 3s infinite alternate;
        transition: color var(--transition-smooth), filter var(--transition-smooth);
      }
    }

    @media (max-width: 768px) {
      padding: 2rem;
    }
  }

  // Glass card effect
  .glass-card {
    background: var(--color-card-bg);
    backdrop-filter: blur(25px);
    -webkit-backdrop-filter: blur(25px);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-lg);
    border: 1px solid var(--color-border);
    position: relative;
    overflow: hidden;
    transition: background-color var(--transition-smooth), 
                border-color var(--transition-smooth),
                box-shadow var(--transition-smooth);

    &:before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 1px;
      background: linear-gradient(90deg,
          rgba(255, 255, 255, 0) 0%,
          rgba(255, 255, 255, 0.6) 50%,
          rgba(255, 255, 255, 0) 100%);
      opacity: 0.8;
      transition: opacity var(--transition-smooth);
    }

    .card-inner {
      position: relative;
      z-index: 2;
      padding: 2.5rem;
    }
  }

  // Hover card effect
  .hover-card {
    position: relative;
    transition: all var(--transition-smooth);
    z-index: 1;

    .card-highlight {
      position: absolute;
      top: -1px;
      left: -1px;
      right: -1px;
      bottom: -1px;
      border-radius: inherit;
      background: transparent;
      border: 2px solid transparent;
      z-index: -1;
      transition: all var(--transition-smooth);
      opacity: 0;
    }      &:hover {
        transform: translateY(-8px) scale(1.02);

        .card-highlight {
          opacity: 1;
          border-color: rgba(var(--about-accent-rgb), 0.4);
          box-shadow:
            0 15px 35px rgba(var(--about-accent-rgb), 0.15),
            0 0 0 4px rgba(var(--about-accent-rgb), 0.08);
        }
      }
  }

  // Enhanced Project overview with ultra-smooth animations
  .overview-block {
    .overview-content {
      display: flex;
      align-items: center;
      gap: 3.5rem;
      position: relative;
      z-index: 1;

      .overview-text {
        flex: 2;

        p {
          margin: 0 0 1.5rem;
          font-size: 1.125rem;
          line-height: 1.7;
          color: var(--color-text);
          transition: color var(--transition-smooth);

          &:last-child {
            margin-bottom: 0;
          }

          strong {
            color: var(--color-primary);
            font-weight: 700;
            position: relative;
            display: inline-block;
            transition: color var(--transition-smooth), transform var(--transition-smooth);
            will-change: transform;

            &:hover {
              transform: translateY(-1px);
            }

            &:after {
              content: '';
              position: absolute;
              bottom: 0;
              left: 0;
              width: 100%;
              height: 2px;
              background: rgba(var(--about-accent-rgb), 0.3);
              border-radius: 1px;
              transition: background var(--transition-smooth);
            }
          }
        }
      }

      .overview-image {
        flex: 1;
        display: flex;
        justify-content: center;
        align-items: center;

        .image-container {
          position: relative;
          will-change: transform;
          transition: transform var(--transition-ultra-smooth);

          &:hover {
            transform: scale(1.05) rotate(2deg);

            .image-glow {
              opacity: 0.9;
              transform: translate(-50%, -50%) scale(1.15);
            }
          }

          .image-glow {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 100%;
            height: 100%;
            background: radial-gradient(circle at center,
                rgba(var(--about-accent-rgb), 0.25) 0%,
                rgba(var(--about-accent-rgb), 0) 70%);
            border-radius: 50%;
            filter: blur(15px);
            animation: pulse-glow 12s var(--transition-ultra-smooth) infinite alternate;
            z-index: -1;
            opacity: 0.6;
            transition: opacity var(--transition-ultra-smooth), transform var(--transition-ultra-smooth);
            will-change: transform, opacity;
          }

          .logo-large {
            width: 220px;
            height: auto;
            filter: drop-shadow(0 10px 20px rgba(var(--about-accent-rgb), 0.3));
            animation: float 12s var(--transition-ultra-smooth) infinite;
            position: relative;
            z-index: 1;
            will-change: transform;
            transition: filter var(--transition-smooth);
          }
        }
      }

      @media (max-width: 768px) {
        flex-direction: column-reverse;
        gap: 2.5rem;

        .overview-image {
          width: 100%;

          .logo-large {
            width: 180px;
          }
        }
      }
    }
  }

  // Enhanced Team section
  .team-block {
    .team-intro {
      font-size: 1.125rem;
      line-height: 1.7;
      color: var(--color-text);
      margin: 0 0 2.5rem;
      text-align: center;
      max-width: 800px;
      margin-left: auto;
      margin-right: auto;
      transition: color var(--transition-smooth);
    }

    .team-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 2.5rem;
      margin-bottom: 3.5rem;

      @media (max-width: 768px) {
        grid-template-columns: 1fr;
      }
    }

    .team-member {
      display: flex;
      gap: 1.5rem;
      background: var(--color-card-bg);
      border-radius: var(--radius-md);
      padding: 1.75rem;
      border: 1px solid var(--color-border);
      will-change: transform, box-shadow, border-color;
      transition: transform var(--transition-ultra-smooth),
        box-shadow var(--transition-ultra-smooth),
        border-color var(--transition-ultra-smooth),
        background-color var(--transition-smooth);

      .member-photo {
        width: 110px;
        height: 110px;
        border-radius: 50%;
        background-color: var(--color-hover-bg);
        background-size: cover;
        background-position: center;
        box-shadow: var(--shadow-md);
        transition: transform var(--transition-elastic),
          box-shadow var(--transition-ultra-smooth);
        position: relative;
        will-change: transform, box-shadow;
        transform: translateZ(0);

        .photo-glow {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          border-radius: 50%;
          background: radial-gradient(circle at center,
              rgba(var(--about-accent-rgb), 0.2) 0%,
              rgba(var(--about-accent-rgb), 0) 70%);
          filter: blur(8px);
          opacity: 0;
          transition: opacity var(--transition-ultra-smooth);
          will-change: opacity;
        }

        &.kohulan {
          background-image: url('https://cheminf.uni-jena.de/wp-content/uploads/2023/05/DSC4286-Enhanced-NR-e1685045988929-260x300.jpg');
        }

        &.christoph {
          background-image: url('https://cheminf.uni-jena.de/wp-content/uploads/2018/04/steinbeck-jena-2017-737x1024.jpg');
        }
      }

      .member-info {
        flex: 1;

        h4 {
          font-size: 1.375rem;
          font-weight: 700;
          margin: 0 0 0.375rem;
          color: var(--color-heading);
          position: relative;
          display: inline-block;
          transition: color var(--transition-smooth);

          &:after {
            content: '';
            position: absolute;
            bottom: -4px;
            left: 0;
            width: 30px;
            height: 2px;
            background: var(--gradient-primary);
            border-radius: 1px;
            transition: width var(--transition-smooth);
          }
        }

        .member-role {
          font-size: 1rem;
          font-weight: 600;
          color: var(--color-primary);
          margin: 0 0 0.875rem;
          transition: color var(--transition-smooth);
        }

        .member-desc {
          font-size: 0.9375rem;
          line-height: 1.6;
          color: var(--color-text-light);
          margin: 0 0 1.125rem;
          transition: color var(--transition-smooth);
        }

        .member-links {
          display: flex;
          gap: 0.875rem;

          .member-link {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background: rgba(var(--about-accent-rgb), 0.1);
            color: var(--color-primary);
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all var(--transition-smooth);
            box-shadow: var(--shadow-sm);

            &:hover {
              background: var(--color-primary);
              color: var(--color-card-bg);
              transform: translateY(-3px);
              box-shadow: 0 5px 15px rgba(var(--about-accent-rgb), 0.3);
            }
          }
        }
      }

      &:hover {
        .member-photo {
          transform: scale(1.08);
          box-shadow: 0 12px 30px rgba(var(--about-accent-rgb), 0.25);

          .photo-glow {
            opacity: 1;
          }
        }

        .member-info h4:after {
          width: 50px;
        }
      }

      @media (max-width: 480px) {
        flex-direction: column;
        align-items: center;
        text-align: center;

        .member-photo {
          width: 130px;
          height: 130px;
          margin-bottom: 1rem;
        }

        .member-info {
          h4:after {
            left: 50%;
            transform: translateX(-50%);
          }

          .member-links {
            justify-content: center;
          }
        }
      }
    }

    .team-cta {
      text-align: center;
      margin-top: 3rem;

      h4 {
        font-size: 1.5rem;
        font-weight: 700;
        margin: 0 0 0.875rem;
        color: var(--color-heading);
        position: relative;
        display: inline-block;
        transition: color var(--transition-smooth);

        &:after {
          content: '';
          position: absolute;
          bottom: -8px;
          left: 50%;
          transform: translateX(-50%);
          width: 40px;
          height: 3px;
          background: var(--gradient-primary);
          border-radius: 1.5px;
        }
      }

      p {
        font-size: 1.125rem;
        line-height: 1.6;
        color: var(--color-text-light);
        margin: 0 0 1.75rem;
        max-width: 600px;
        margin-left: auto;
        margin-right: auto;
        transition: color var(--transition-smooth);
      }

      .team-buttons {
        display: flex;
        gap: 1.25rem;
        justify-content: center;

        @media (max-width: 480px) {
          flex-direction: column;
          align-items: center;
          gap: 1rem;
        }
      }
    }
  }

  // Enhanced Publications
  .publications-block {
    .publications-intro {
      font-size: 1.125rem;
      line-height: 1.7;
      color: var(--color-text, #171747);
      margin: 0 0 2.5rem;
      text-align: center;
      max-width: 800px;
      margin-left: auto;
      margin-right: auto;
    }

    .publications-list {
      display: flex;
      flex-direction: column;
      gap: 1.75rem;
    }

    .publication {
      display: flex;
      gap: 1.5rem;
      background: var(--color-card-bg, rgba(255, 255, 255, 0.7));
      border-radius: var(--border-radius-md, 16px);
      padding: 1.75rem;
      border: 1px solid var(--color-border, rgba(var(--color-primary-rgb, 65, 97, 255), 0.05));
      position: relative;
      backdrop-filter: blur(10px);
      transition: all 0.3s var(--transition-smooth);

      .publication-icon {
        width: 55px;
        height: 55px;
        min-width: 55px;
        border-radius: 12px;
        background: rgba(var(--color-primary-rgb, 65, 97, 255), 0.08);
        color: var(--color-primary, #4161FF);
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.4s var(--transition-elastic);
        position: relative;

        .icon-glow {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          border-radius: 12px;
          background: radial-gradient(circle at center,
              rgba(var(--color-primary-rgb, 65, 97, 255), 0.3) 0%,
              rgba(var(--color-primary-rgb, 65, 97, 255), 0) 70%);
          filter: blur(8px);
          opacity: 0;
          transition: opacity 0.4s var(--transition-smooth);
        }
      }

      .publication-info {
        flex: 1;

        h4 {
          font-size: 1.125rem;
          font-weight: 600;
          margin: 0 0 0.625rem;
          color: var(--color-text, #171747);
          line-height: 1.4;
          transition: color 0.3s var(--transition-smooth);
        }

        .publication-authors {
          font-size: 0.9375rem;
          color: var(--color-text-secondary, #5D6B98);
          margin: 0 0 0.375rem;
          opacity: 0.9;
        }

        .publication-journal {
          font-size: 0.875rem;
          font-style: italic;
          color: var(--color-text-light, #5D6B98);
          margin: 0 0 0.875rem;
        }

        .publication-link {
          display: inline-flex;
          align-items: center;
          gap: 0.375rem;
          font-size: 0.875rem;
          color: var(--color-primary, #4161FF);
          text-decoration: none;
          transition: all 0.3s var(--transition-smooth);
          position: relative;

          &:after {
            content: '';
            position: absolute;
            bottom: -2px;
            left: 0;
            width: 0;
            height: 1px;
            background: var(--color-primary, #4161FF);
            transition: width 0.3s var(--transition-smooth);
          }

          &:hover {
            color: var(--color-primary, #4161FF);

            &:after {
              width: 100%;
            }
          }
        }
      }

      &:hover {
        background: var(--color-card-bg-hover, rgba(255, 255, 255, 0.9));
        transform: translateY(-4px);
        box-shadow: var(--shadow-lg, 0 20px 40px rgba(0, 0, 0, 0.1));
        border-color: var(--color-primary, #4161FF);

        .publication-icon {
          transform: scale(1.1) rotate(-5deg);
          background: var(--color-primary, #4161FF);
          color: white;
          box-shadow: 0 8px 16px rgba(var(--color-primary-rgb, 65, 97, 255), 0.3);

          .icon-glow {
            opacity: 1;
          }
        }

        .publication-info h4 {
          color: var(--color-primary, #4161FF);
        }
      }

      @media (max-width: 480px) {
        flex-direction: column;

        .publication-icon {
          margin-bottom: 1rem;
        }
      }
    }
  }

  // Enhanced Mission section
  .mission-block {
    background: linear-gradient(135deg,
        rgba(var(--color-primary-rgb, 65, 97, 255), 0.05) 0%,
        rgba(var(--color-accent-rgb, 122, 69, 255), 0.08) 100%);
    overflow: hidden;

    .mission-decoration {
      border-radius: 50%;
      background: radial-gradient(circle at center,
          rgba(var(--color-primary-rgb, 65, 97, 255), 0.15) 0%,
          rgba(var(--color-primary-rgb, 65, 97, 255), 0) 70%);
    }

    .mission-overlay {
      position: absolute;
      top: 0;
      right: 0;
      width: 350px;
      height: 350px;
      background: radial-gradient(circle at center,
          rgba(var(--color-tertiary-rgb, 65, 195, 255), 0.15) 0%,
          rgba(var(--color-tertiary-rgb, 65, 195, 255), 0) 70%);
      z-index: 0;
      opacity: 0.8;
      border-radius: 50%;
      filter: blur(40px);
    }

    .mission-content {
      position: relative;
      z-index: 1;
    }

    .mission-quote {
      font-size: 1.75rem;
      font-weight: 300;
      font-style: italic;
      line-height: 1.5;
      color: var(--color-primary, #4161FF);
      margin: 0 0 2.5rem;
      padding: 0 2.5rem;
      text-align: center;
      position: relative;

      .quote-mark {
        font-size: 3.5rem;
        line-height: 0;
        position: absolute;
        color: rgba(var(--color-primary-rgb, 65, 97, 255), 0.25);
        font-family: 'Georgia', serif;
        font-style: normal;
      }

      .quote-open {
        top: 0.5rem;
        left: 0;
      }

      .quote-close {
        bottom: 0;
        right: 0;
      }

      @media (max-width: 768px) {
        font-size: 1.5rem;
        padding: 0 2rem;
      }
    }

    .mission-details {
      font-size: 1.125rem;
      line-height: 1.7;
      color: var(--color-text, #171747);
      text-align: center;
      max-width: 800px;
      margin: 0 auto;
    }
  }

  // Enhanced CTA block
  .cta-block {
    .cta-content-centered {
      text-align: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1.75rem;

      .cta-text {
        font-size: 1.125rem;
        line-height: 1.7;
        color: var(--color-text, #171747);
        max-width: 700px;
        margin: 0 auto;
      }

      .btn {
        min-width: 200px;
      }
    }
  }

  // Enhanced Call to action
  .about-cta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--gradient-primary, linear-gradient(135deg, #3A8CFF 0%, #775FFC 100%));
    border-radius: var(--border-radius-lg, 24px);
    padding: 3rem;
    overflow: hidden;
    position: relative;
    margin-bottom: 1rem;
    box-shadow: 0 15px 40px rgba(var(--color-primary-rgb, 65, 97, 255), 0.25);

    @media (max-width: 768px) {
      flex-direction: column;
      text-align: center;
      gap: 2rem;
      padding: 2.5rem;
    }

    .cta-blob-1,
    .cta-blob-2 {
      position: absolute;
      border-radius: 50%;
      filter: blur(50px);
      z-index: 0;
    }

    .cta-blob-1 {
      width: 300px;
      height: 300px;
      background: rgba(255, 255, 255, 0.2);
      top: -150px;
      right: -50px;
      animation: float-slow 20s infinite ease-in-out;
    }

    .cta-blob-2 {
      width: 250px;
      height: 250px;
      background: rgba(var(--color-accent-rgb, 122, 69, 255), 0.2);
      bottom: -100px;
      left: -50px;
      animation: float-slow 18s infinite ease-in-out reverse;
    }

    .cta-content {
      position: relative;
      z-index: 1;

      h3 {
        font-size: 1.75rem;
        font-weight: 700;
        color: white;
        margin: 0 0 0.75rem;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);

        @media (max-width: 768px) {
          font-size: 1.5rem;
        }
      }

      p {
        font-size: 1.125rem;
        color: rgba(255, 255, 255, 0.9);
        margin: 0;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
      }
    }

    .btn-large {
      padding: 0 2rem;
      height: 56px;
      font-size: 1.125rem;
      font-weight: 600;
      background: white;
      color: var(--color-primary, #4161FF);
      border: none;
      border-radius: 12px;
      cursor: pointer;
      position: relative;
      z-index: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.875rem;
      transition: all 0.4s var(--transition-elastic);
      box-shadow: 0 10px 20px rgba(0, 0, 0, 0.15);

      &:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 30px rgba(0, 0, 0, 0.2);
      }

      .btn-icon {
        color: var(--color-primary, #4161FF);
      }

      .btn-bg {
        background: white;
      }
    }
  }

  // Enhanced Buttons
  .btn {
    height: 48px;
    border-radius: 12px;
    font-weight: 600;
    font-size: 1rem;
    transition: all 0.4s var(--transition-elastic);
    text-decoration: none;
    position: relative;
    overflow: hidden;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    padding: 0 1.5rem;

    .btn-bg {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      border-radius: 12px;
      transition: all 0.3s var(--transition-smooth);
      z-index: -1;
    }

    // Primary button with glow effect
    &.btn-primary {
      color: white;

      .btn-bg {
        background: var(--gradient-primary, linear-gradient(135deg, #3A8CFF 0%, #775FFC 100%));
        box-shadow:
          0 6px 15px rgba(var(--color-primary-rgb, 65, 97, 255), 0.25),
          inset 0 1px 1px rgba(255, 255, 255, 0.2);
      }

      &:hover {
        transform: translateY(-4px);

        .btn-bg {
          box-shadow:
            0 10px 25px rgba(var(--color-primary-rgb, 65, 97, 255), 0.35),
            inset 0 1px 1px rgba(255, 255, 255, 0.3);
          filter: brightness(1.1);
        }
      }

      &:active {
        transform: scale(0.98);
      }

      // Glow effect
      &.btn-glow {
        &:before {
          content: '';
          position: absolute;
          top: -2px;
          left: -2px;
          right: -2px;
          bottom: -2px;
          background: var(--gradient-primary, linear-gradient(135deg, #3A8CFF 0%, #775FFC 100%));
          border-radius: 14px;
          z-index: -2;
          opacity: 0;
          transition: opacity 0.3s var(--transition-smooth);
          filter: blur(8px);
        }

        &:hover:before {
          opacity: 0.7;
          animation: pulse-button 2s infinite;
        }
      }
    }

    // Secondary button with pulse effect
    &.btn-secondary {
      color: var(--color-primary, #4161FF);
      border: 2px solid rgba(var(--color-primary-rgb, 65, 97, 255), 0.3);
      background: rgba(var(--color-primary-rgb, 65, 97, 255), 0.03);
      box-shadow: 0 4px 10px rgba(var(--color-primary-rgb, 65, 97, 255), 0.05);

      &:hover {
        background: rgba(var(--color-primary-rgb, 65, 97, 255), 0.08);
        border-color: rgba(var(--color-primary-rgb, 65, 97, 255), 0.5);
        transform: translateY(-4px);
        box-shadow: 0 8px 20px rgba(var(--color-primary-rgb, 65, 97, 255), 0.1);
      }

      &:active {
        transform: scale(0.98);
      }

      // Pulse effect
      &.btn-pulse {
        position: relative;

        &:after {
          content: '';
          position: absolute;
          top: -6px;
          left: -6px;
          right: -6px;
          bottom: -6px;
          border: 2px solid rgba(var(--color-primary-rgb, 65, 97, 255), 0.3);
          border-radius: 16px;
          animation: pulse-outline 2s infinite;
          opacity: 0;
        }

        &:hover:after {
          opacity: 1;
        }
      }
    }
  }

  // Enhanced Close button
  .close-btn {
    position: fixed;
    top: 1.5rem;
    right: 1.5rem;
    background: rgba(var(--color-primary-rgb, 65, 97, 255), 0.08);
    border: none;
    border-radius: 50%;
    width: 52px;
    height: 52px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    color: var(--color-primary, #4161FF);
    transition: all 0.3s var(--transition-elastic);
    z-index: 10;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);

    span {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border-width: 0;
    }

    &:hover {
      background: var(--color-primary, #4161FF);
      color: white;
      transform: rotate(90deg) scale(1.1);
      box-shadow: 0 8px 20px rgba(var(--color-primary-rgb, 65, 97, 255), 0.2);
    }

    &:active {
      transform: rotate(90deg) scale(0.95);
    }
  }

  // Enhanced Get Started button
  .btn-get-started {
    min-width: 220px;
    height: 60px;
    font-size: 1.25rem;
    font-weight: 700;
    letter-spacing: 0.01em;
    border-radius: var(--radius-lg, 16px);
    background: var(--gradient-primary, linear-gradient(135deg, #3A8CFF 0%, #775FFC 100%));
    color: var(--color-white, #fff);
    box-shadow: var(--shadow-lg, 0 8px 32px rgba(65, 97, 255, 0.25)), 
                0 0 0 4px rgba(var(--color-white-rgb, 255, 255, 255), 0.08);
    position: relative;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    transition: all 0.4s var(--transition-smooth, cubic-bezier(0.34, 1.56, 0.64, 1));
    z-index: 2;

    .btn-bg {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      border-radius: var(--radius-lg, 16px);
      transition: all 0.4s var(--transition-smooth, cubic-bezier(0.25, 0.46, 0.45, 0.94));
      z-index: -1;
      background: var(--gradient-primary, linear-gradient(135deg, #3A8CFF 0%, #775FFC 100%));
      box-shadow: var(--shadow-md, 0 6px 15px rgba(var(--color-primary-rgb, 65, 97, 255), 0.25)),
        inset 0 1px 1px rgba(var(--color-white-rgb, 255, 255, 255), 0.2);
    }

    .btn-icon {
      width: 28px;
      height: 28px;
      color: var(--color-white, #fff);
      filter: drop-shadow(0 2px 5px rgba(var(--color-dark-rgb, 0, 0, 0), 0.2));
      transition: transform 0.4s var(--transition-smooth, cubic-bezier(0.25, 0.46, 0.45, 0.94));
    }

    span {
      font-size: 1.2em;
      font-weight: 700;
      text-shadow: 0 1px 2px rgba(var(--color-dark-rgb, 0, 0, 0), 0.15);
    }

    &:hover {
      transform: translateY(-6px) scale(1.02);

      .btn-bg {
        box-shadow: var(--shadow-xl, 0 10px 25px rgba(var(--color-primary-rgb, 65, 97, 255), 0.35)),
          inset 0 1px 1px rgba(var(--color-white-rgb, 255, 255, 255), 0.3);
        filter: brightness(1.1);
      }

      .btn-icon {
        transform: translateY(-3px) rotate(5deg);
      }
    }

    &:active {
      transform: translateY(-2px) scale(0.98);
    }
  }
}

// Ultra-Smooth Enhanced Animations with Perfect Easing
@keyframes float {
  0% {
    transform: translateY(0px);
  }

  50% {
    transform: translateY(-25px);
  }

  100% {
    transform: translateY(0px);
  }
}

@keyframes float-slow {
  0% {
    transform: translate(0px, 0px) rotate(0deg);
  }

  25% {
    transform: translate(25px, -15px) rotate(1deg);
  }

  50% {
    transform: translate(0px, -30px) rotate(0deg);
  }

  75% {
    transform: translate(-25px, -15px) rotate(-1deg);
  }

  100% {
    transform: translate(0px, 0px) rotate(0deg);
  }
}

@keyframes float-particles {
  0% {
    transform: translate(0px, 0px) scale(1);
    opacity: 0.6;
  }

  25% {
    transform: translate(40px, -30px) scale(1.05);
    opacity: 0.8;
  }

  50% {
    transform: translate(0px, -50px) scale(1.1);
    opacity: 1;
  }

  75% {
    transform: translate(-40px, -30px) scale(1.05);
    opacity: 0.8;
  }

  100% {
    transform: translate(0px, 0px) scale(1);
    opacity: 0.6;
  }
}

@keyframes pulse-glow {
  0% {
    opacity: 0.4;
    transform: scale(1);
  }

  50% {
    opacity: 0.9;
    transform: scale(1.12);
  }

  100% {
    opacity: 0.4;
    transform: scale(1);
  }
}

@keyframes pulse-icon {
  0% {
    filter: drop-shadow(0 2px 6px rgba(var(--color-primary-rgb, 65, 97, 255), 0.3));
    transform: scale(1);
  }

  50% {
    filter: drop-shadow(0 4px 12px rgba(var(--color-primary-rgb, 65, 97, 255), 0.6));
    transform: scale(1.08);
  }

  100% {
    filter: drop-shadow(0 2px 6px rgba(var(--color-primary-rgb, 65, 97, 255), 0.3));
    transform: scale(1);
  }
}

@keyframes pulse-button {
  0% {
    opacity: 0.6;
    transform: scale(0.98);
  }

  50% {
    opacity: 0.3;
    transform: scale(1.05);
  }

  100% {
    opacity: 0.6;
    transform: scale(0.98);
  }
}

@keyframes pulse-outline {
  0% {
    opacity: 0.8;
    transform: scale(0.95);
    border-color: rgba(var(--color-primary-rgb, 65, 97, 255), 0.5);
  }

  50% {
    opacity: 0.3;
    transform: scale(1.08);
    border-color: rgba(var(--color-primary-rgb, 65, 97, 255), 0.3);
  }

  100% {
    opacity: 0;
    transform: scale(1.2);
    border-color: rgba(var(--color-primary-rgb, 65, 97, 255), 0.1);
  }
}

@keyframes shimmer {
  0% {
    left: -120%;
    opacity: 0;
  }
  
  30% {
    opacity: 0.8;
  }

  70% {
    opacity: 0.8;
  }

  100% {
    left: 170%;
    opacity: 0;
  }
}

@keyframes gradientShift {
  0% {
    background-position: 0% 50%;
  }

  50% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0% 50%;
  }
}
</style>