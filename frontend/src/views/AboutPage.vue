<template>
  <section id="about" class="about-section">
    <div class="hero-bg"></div>
    
    <!-- Main Content Container -->
    <div class="container">
      <!-- Section Header -->
      <div class="section-header">
        <div class="section-tag">About MARCUS</div>
        <h2 class="section-title">Unraveling Chemical Structures with AI</h2>
        <p class="section-description">
          Discover the story, mission, and team behind MARCUS - Molecular Annotation and Recognition for Curating Unravelled Structures
        </p>
      </div>
      
      <!-- Project Overview -->
      <div class="content-block">
        <h3 class="block-title">
          <vue-feather type="info" class="title-icon"></vue-feather>
          Project Overview
        </h3>
        <div class="overview-content">
          <div class="overview-text">
            <p>
              <strong>MARCUS</strong> (Molecular Annotation and Recognition for Curating Unravelled Structures) is an advanced computational platform designed to revolutionize the extraction and annotation of chemical structures from scientific literature. By leveraging cutting-edge AI technologies, MARCUS automates the previously labor-intensive process of manually identifying, extracting, and digitizing chemical structures from research papers.
            </p>
            <p>
              Developed at the Steinbeck Lab, MARCUS bridges the gap between the vast knowledge hidden in the scientific literature and the digital representation required for computational analysis, database integration, and further research applications.
            </p>
          </div>
          <div class="overview-image">
            <img src="@/assets/logo.png" alt="MARCUS Logo" class="logo-large" />
          </div>
        </div>
      </div>
      
      <!-- Mission Statement -->
      <div class="content-block mission-block">
        <div class="mission-overlay"></div>
        <h3 class="block-title">
          <vue-feather type="target" class="title-icon"></vue-feather>
          Our Mission
        </h3>
        <div class="mission-content">
          <blockquote class="mission-quote">
            To accelerate chemical structure knowledge extraction from scientific literature using AI, making it accessible for research, drug discovery, and chemical database enrichment
          </blockquote>
          <div class="mission-points">
            <div class="mission-point">
              <div class="point-icon-wrapper">
                <vue-feather type="zap" class="point-icon"></vue-feather>
              </div>
              <div class="point-content">
                <h4>Automating Structure Extraction</h4>
                <p>Transform the labor-intensive process of manual structure drawing into an efficient automated workflow</p>
              </div>
            </div>
            <div class="mission-point">
              <div class="point-icon-wrapper">
                <vue-feather type="database" class="point-icon"></vue-feather>
              </div>
              <div class="point-content">
                <h4>Enhancing Natural Products Databases</h4>
                <p>Contribute to the growth of the COCONUT database and other chemical knowledge repositories</p>
              </div>
            </div>
            <div class="mission-point">
              <div class="point-icon-wrapper">
                <vue-feather type="share-2" class="point-icon"></vue-feather>
              </div>
              <div class="point-content">
                <h4>Democratizing Chemical Knowledge</h4>
                <p>Make chemical structures from literature accessible to researchers worldwide</p>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Technology Stack -->
      <div class="content-block">
        <h3 class="block-title">
          <vue-feather type="cpu" class="title-icon"></vue-feather>
          Technology Stack
        </h3>
        <div class="tech-stack-content">
          <p class="tech-intro">
            MARCUS combines state-of-the-art Optical Chemical Structure Recognition (OCSR) engines with advanced text mining technologies to provide a comprehensive solution for processing scientific publications.
          </p>
          
          <div class="tech-categories">
            <div class="tech-category">
              <h4 class="category-title">
                <vue-feather type="eye" class="category-icon"></vue-feather>
                Structure Recognition
              </h4>
              <div class="tech-grid">
                <div class="tech-item">
                  <div class="tech-logo decimer-logo"></div>
                  <h5>DECIMER</h5>
                  <p>Deep learning model for optical chemical structure recognition</p>
                </div>
                <div class="tech-item">
                  <div class="tech-logo molnextr-logo"></div>
                  <h5>MolNexTR</h5>
                  <p>Transformer-based model for accurate structure interpretation</p>
                </div>
                <div class="tech-item">
                  <div class="tech-logo molscribe-logo"></div>
                  <h5>MolScribe</h5>
                  <p>Advanced recognition of complex molecular structures</p>
                </div>
              </div>
            </div>
            
            <div class="tech-category">
              <h4 class="category-title">
                <vue-feather type="align-left" class="category-icon"></vue-feather>
                Text Processing
              </h4>
              <div class="tech-grid">
                <div class="tech-item">
                  <div class="tech-logo openai-logo"></div>
                  <h5>OpenAI</h5>
                  <p>Advanced language models for text extraction and annotation</p>
                </div>
                <div class="tech-item">
                  <div class="tech-logo docling-logo"></div>
                  <h5>Docling</h5>
                  <p>Document processing for scientific PDF analysis</p>
                </div>
              </div>
            </div>
            
            <div class="tech-category">
              <h4 class="category-title">
                <vue-feather type="code" class="category-icon"></vue-feather>
                Application Framework
              </h4>
              <div class="tech-grid">
                <div class="tech-item">
                  <div class="tech-logo vue-logo"></div>
                  <h5>Vue.js</h5>
                  <p>Progressive JavaScript framework for the frontend interface</p>
                </div>
                <div class="tech-item">
                  <div class="tech-logo python-logo"></div>
                  <h5>Python</h5>
                  <p>Powerful backend implementation with FastAPI</p>
                </div>
                <div class="tech-item">
                  <div class="tech-logo docker-logo"></div>
                  <h5>Docker</h5>
                  <p>Containerized deployment for consistent performance</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Team Section -->
      <div class="content-block team-block">
        <h3 class="block-title">
          <vue-feather type="users" class="title-icon"></vue-feather>
          Meet the Team
        </h3>
        <div class="team-content">
          <p class="team-intro">
            MARCUS is developed by an interdisciplinary team of researchers at the Steinbeck Lab, bringing together expertise in cheminformatics, artificial intelligence, and software engineering.
          </p>
          
          <div class="team-grid">
            <div class="team-member">
              <div class="member-photo kohulan"></div>
              <div class="member-info">
                <h4>Kohulan Rajan</h4>
                <p class="member-role">Lead Developer</p>
                <p class="member-desc">Cheminformatics researcher specializing in deep learning and chemical structure recognition</p>
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
            
            <div class="team-member">
              <div class="member-photo christoph"></div>
              <div class="member-info">
                <h4>Christoph Steinbeck</h4>
                <p class="member-role">Project Lead</p>
                <p class="member-desc">Professor of Analytical Chemistry, Cheminformatics and Chemometrics at Friedrich-Schiller-University Jena</p>
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
          
          <div class="team-cta">
            <h4>Join the Community</h4>
            <p>MARCUS is an open-source project and we welcome contributions from the community.</p>
            <div class="team-buttons">
              <a href="https://github.com/Kohulan/MARCUS" target="_blank" class="btn btn-primary">
                <div class="btn-bg"></div>
                <vue-feather type="github" class="btn-icon"></vue-feather>
                <span>GitHub Repository</span>
              </a>
              <a href="https://github.com/Steinbeck-Lab" target="_blank" class="btn btn-secondary">
                <vue-feather type="users" class="btn-icon"></vue-feather>
                <span>Steinbeck Lab</span>
              </a>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Publications -->
      <div class="content-block publications-block">
        <h3 class="block-title">
          <vue-feather type="book-open" class="title-icon"></vue-feather>
          Research & Publications
        </h3>
        <div class="publications-content">
          <p class="publications-intro">
            Learn more about the research behind MARCUS and related technologies through our publications.
          </p>
          
          <div class="publications-list">
            <div class="publication">
              <div class="publication-icon">
                <vue-feather type="file-text" size="24"></vue-feather>
              </div>
              <div class="publication-info">
                <h4>DECIMER - Hand-drawn Molecule Images to Machine-readable Structures</h4>
                <p class="publication-authors">Rajan K, Zielesny A, Steinbeck C</p>
                <p class="publication-journal">Journal of Cheminformatics</p>
                <a href="https://doi.org/10.1186/s13321-021-00538-8" target="_blank" class="publication-link">
                  <vue-feather type="external-link" size="14"></vue-feather>
                  <span>doi.org/10.1186/s13321-021-00538-8</span>
                </a>
              </div>
            </div>
            
            <div class="publication">
              <div class="publication-icon">
                <vue-feather type="file-text" size="24"></vue-feather>
              </div>
              <div class="publication-info">
                <h4>DECIMER 1.0: Deep Learning for Chemical Image Recognition using Transformers</h4>
                <p class="publication-authors">Rajan K, Brinkhaus HO, Zielesny A, Steinbeck C</p>
                <p class="publication-journal">Journal of Cheminformatics</p>
                <a href="https://doi.org/10.1186/s13321-021-00538-8" target="_blank" class="publication-link">
                  <vue-feather type="external-link" size="14"></vue-feather>
                  <span>doi.org/10.1186/s13321-021-00538-8</span>
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Call to Action -->
      <div class="about-cta">
        <div class="cta-content">
          <h3>Ready to Extract Chemical Structures?</h3>
          <p>Experience the power of MARCUS by uploading your first document</p>
        </div>
        <button class="btn btn-primary btn-large" @click="scrollToUpload">
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
  
  methods: {
    scrollToUpload() {
      // Find the HomeView component and scroll to the upload section
      this.$router.push('/');
      
      // Use setTimeout to ensure navigation is complete before scrolling
      setTimeout(() => {
        const uploadSection = document.querySelector('.pdf-column');
        if (uploadSection) {
          uploadSection.scrollIntoView({ behavior: 'smooth' });
        }
      }, 300);
    }
  }
}
</script>

<style lang="scss" scoped>
.about-section {
  padding: 2rem 0 5rem;
  background: var(--color-bg, #f8fafc);
  position: relative;
  overflow: hidden;
  
  // Background elements
  .hero-bg {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(135deg, 
      rgba(var(--color-primary-rgb, 52, 97, 255), 0.05) 0%, 
      rgba(var(--color-primary-rgb, 52, 97, 255), 0.02) 100%
    );
    z-index: 0;
    
    &:before {
      content: '';
      position: absolute;
      top: -150px;
      right: -150px;
      width: 400px;
      height: 400px;
      background: radial-gradient(
        circle at center,
        rgba(var(--color-primary-rgb, 52, 97, 255), 0.12) 0%, 
        rgba(var(--color-primary-rgb, 52, 97, 255), 0) 70%
      );
      border-radius: 50%;
    }
    
    &:after {
      content: '';
      position: absolute;
      bottom: -100px;
      left: -100px;
      width: 300px;
      height: 300px;
      background: radial-gradient(
        circle at center,
        rgba(var(--color-primary-rgb, 52, 97, 255), 0.08) 0%, 
        rgba(var(--color-primary-rgb, 52, 97, 255), 0) 70%
      );
      border-radius: 50%;
    }
  }
  
  .container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 1.5rem;
    position: relative;
    z-index: 1;
  }
  
  // Section header
  .section-header {
    text-align: center;
    margin-bottom: 3rem;
    
    .section-tag {
      display: inline-block;
      background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
      color: var(--color-primary, #3461ff);
      font-size: 0.875rem;
      font-weight: 600;
      padding: 0.5rem 1rem;
      border-radius: 30px;
      margin-bottom: 1rem;
    }
    
    .section-title {
      font-size: 2.5rem;
      font-weight: 800;
      margin: 0 0 1rem;
      background: var(--gradient-primary, linear-gradient(135deg, #4a6cf7 0%, #2254e2 100%));
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
      
      @media (max-width: 768px) {
        font-size: 2rem;
      }
    }
    
    .section-description {
      font-size: 1.125rem;
      color: var(--color-text-light, #8392ab);
      line-height: 1.5;
      max-width: 700px;
      margin: 0 auto;
    }
  }
  
  // General content block styling
  .content-block {
    background: rgba(var(--color-bg-card-rgb, 255, 255, 255), 0.5);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-radius: 20px;
    padding: 2.5rem;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.05);
    border: 1px solid rgba(var(--color-primary-rgb, 52, 97, 255), 0.08);
    margin-bottom: 3rem;
    position: relative;
    overflow: hidden;
    
    .block-title {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      font-size: 1.5rem;
      font-weight: 700;
      margin: 0 0 1.5rem;
      color: var(--color-text, #3b4863);
      
      .title-icon {
        color: var(--color-primary, #3461ff);
        filter: drop-shadow(0 2px 4px rgba(var(--color-primary-rgb, 52, 97, 255), 0.3));
      }
    }
    
    @media (max-width: 768px) {
      padding: 1.5rem;
    }
  }
  
  // Project overview
  .overview-content {
    display: flex;
    align-items: center;
    gap: 3rem;
    
    .overview-text {
      flex: 2;
      
      p {
        margin: 0 0 1.25rem;
        font-size: 1.0625rem;
        line-height: 1.7;
        color: var(--color-text, #3b4863);
        
        &:last-child {
          margin-bottom: 0;
        }
        
        strong {
          color: var(--color-primary, #3461ff);
          font-weight: 700;
        }
      }
    }
    
    .overview-image {
      flex: 1;
      display: flex;
      justify-content: center;
      align-items: center;
      
      .logo-large {
        width: 180px;
        height: auto;
        filter: drop-shadow(0 8px 16px rgba(var(--color-primary-rgb, 52, 97, 255), 0.2));
        animation: float 6s ease-in-out infinite;
      }
    }
    
    @media (max-width: 768px) {
      flex-direction: column-reverse;
      gap: 2rem;
      
      .overview-image {
        width: 100%;
        
        .logo-large {
          width: 140px;
        }
      }
    }
  }
  
  // Mission section
  .mission-block {
    background: linear-gradient(135deg, 
      rgba(var(--color-primary-rgb, 52, 97, 255), 0.07) 0%, 
      rgba(var(--color-primary-rgb, 52, 97, 255), 0.12) 100%
    );
    overflow: hidden;
    
    .mission-overlay {
      position: absolute;
      top: 0;
      right: 0;
      width: 300px;
      height: 300px;
      background: radial-gradient(
        circle at center,
        rgba(var(--color-primary-rgb, 52, 97, 255), 0.15) 0%, 
        rgba(var(--color-primary-rgb, 52, 97, 255), 0) 70%
      );
      z-index: 0;
      opacity: 0.8;
      border-radius: 50%;
    }
    
    .mission-content {
      position: relative;
      z-index: 1;
    }
    
    .mission-quote {
      font-size: 1.5rem;
      font-weight: 300;
      font-style: italic;
      line-height: 1.5;
      color: var(--color-primary, #3461ff);
      margin: 0 0 2.5rem;
      padding: 0 2rem;
      text-align: center;
      position: relative;
      
      &:before, &:after {
        content: '"';
        font-size: 3rem;
        line-height: 0;
        position: absolute;
        opacity: 0.3;
      }
      
      &:before {
        top: 0.5rem;
        left: 0;
      }
      
      &:after {
        bottom: 0;
        right: 0;
      }
      
      @media (max-width: 768px) {
        font-size: 1.25rem;
        padding: 0 1rem;
      }
    }
    
    .mission-points {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 2rem;
      
      @media (max-width: 992px) {
        grid-template-columns: repeat(2, 1fr);
      }
      
      @media (max-width: 640px) {
        grid-template-columns: 1fr;
      }
    }
    
    .mission-point {
      display: flex;
      gap: 1rem;
      
      .point-icon-wrapper {
        width: 46px;
        height: 46px;
        min-width: 46px;
        border-radius: 12px;
        background: var(--color-primary, #3461ff);
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 6px 15px rgba(var(--color-primary-rgb, 52, 97, 255), 0.25);
        
        .point-icon {
          color: white;
          width: 22px;
          height: 22px;
        }
      }
      
      .point-content {
        h4 {
          font-size: 1.125rem;
          font-weight: 600;
          margin: 0 0 0.5rem;
          color: var(--color-text, #3b4863);
        }
        
        p {
          font-size: 0.9375rem;
          line-height: 1.6;
          color: var(--color-text-light, #8392ab);
          margin: 0;
        }
      }
    }
  }
  
  // Technology stack
  .tech-stack-content {
    .tech-intro {
      font-size: 1.0625rem;
      line-height: 1.7;
      color: var(--color-text, #3b4863);
      margin: 0 0 2rem;
      text-align: center;
      max-width: 800px;
      margin-left: auto;
      margin-right: auto;
    }
    
    .tech-categories {
      display: flex;
      flex-direction: column;
      gap: 2.5rem;
    }
    
    .tech-category {
      .category-title {
        display: flex;
        align-items: center;
        gap: 0.625rem;
        font-size: 1.25rem;
        font-weight: 600;
        margin: 0 0 1.5rem;
        color: var(--color-text, #3b4863);
        padding-bottom: 0.75rem;
        border-bottom: 1px solid rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
        
        .category-icon {
          color: var(--color-primary, #3461ff);
        }
      }
    }
    
    .tech-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 1.5rem;
      
      @media (max-width: 992px) {
        grid-template-columns: repeat(2, 1fr);
      }
      
      @media (max-width: 640px) {
        grid-template-columns: 1fr;
      }
    }
    
    .tech-item {
      background: rgba(255, 255, 255, 0.6);
      border-radius: 16px;
      padding: 1.5rem;
      text-align: center;
      border: 1px solid rgba(var(--color-primary-rgb, 52, 97, 255), 0.05);
      transition: all 0.3s ease;
      
      &:hover {
        transform: translateY(-5px);
        box-shadow: 0 12px 24px rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
        border-color: rgba(var(--color-primary-rgb, 52, 97, 255), 0.15);
      }
      
      .tech-logo {
        height: 64px;
        width: 64px;
        margin: 0 auto 1rem;
        background-position: center;
        background-size: contain;
        background-repeat: no-repeat;
        transition: transform 0.3s ease;
        
        &.decimer-logo {
          background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill="%234a6cf7" d="M40,20 L60,20 L80,50 L60,80 L40,80 L20,50 L40,20 Z M50,30 A20,20 0 1 0 50,70 A20,20 0 1 0 50,30 Z"/></svg>');
        }
        
        &.molnextr-logo {
          background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill="%230ea5e9" d="M30,20 L70,20 L90,50 L70,80 L30,80 L10,50 L30,20 Z M20,50 L40,30 L60,30 L80,50 L60,70 L40,70 Z"/></svg>');
        }
        
        &.molscribe-logo {
          background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill="%23a855f7" d="M50,10 L90,30 L90,70 L50,90 L10,70 L10,30 L50,10 Z M30,40 L50,50 L70,40 M50,50 L50,80"/></svg>');
        }
        
        &.openai-logo {
          background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle fill="%2310b981" cx="50" cy="50" r="40"/><path fill="%23ffffff" d="M30,35 L70,35 L70,40 L30,40 Z M30,45 L70,45 L70,50 L30,50 Z M30,55 L70,55 L70,60 L30,60 Z M30,65 L50,65 L50,70 L30,70 Z"/></svg>');
        }
        
        &.docling-logo {
          background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill="%23f97316" d="M30,20 L70,20 L70,80 L30,80 Z M40,30 L60,30 M40,40 L60,40 M40,50 L60,50 M40,60 L60,60 M40,70 L50,70"/></svg>');
        }
        
        &.vue-logo {
          background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill="%2341b883" d="M50,20 L62,40 L74,20 L100,20 L50,100 L0,20 L26,20 L38,40 L50,20 Z"/></svg>');
        }
        
        &.python-logo {
          background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill="%233776ab" d="M50,15 C30,15 30,25 30,35 L30,45 L70,45 L70,50 L20,50 C10,50 10,60 10,70 C10,80 10,90 30,90 C40,90 40,85 50,85 C60,85 60,90 70,90 C90,90 90,80 90,70 L90,60 L50,60 C40,60 40,55 40,50 L40,35 C40,25 40,25 50,25 C60,25 60,25 60,35 L70,35 C70,25 70,15 50,15 Z M35,70 A5,5 0 1 1 35,80 A5,5 0 1 1 35,70 Z"/></svg>');
        }
        
        &.docker-logo {
          background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill="%232496ed" d="M60,45 L70,45 L70,55 L60,55 Z M45,45 L55,45 L55,55 L45,55 Z M30,45 L40,45 L40,55 L30,55 Z M45,30 L55,30 L55,40 L45,40 Z M30,30 L40,30 L40,40 L30,40 Z M95,50 C95,47 93,45 89,43 C88,38 85,35 80,33 L78,32 L77,34 C75,38 75,42 76,45 C76,46 77,48 78,49 C75,50 70,50 68,50 L10,50 C7,55 7,65 10,70 C13,73 16,75 21,75 C35,75 45,65 49,58 C52,58 57,58 61,57 C66,57 71,56 75,53 C76,52 77,52 78,51 C83,55 90,55 94,50 L95,50 Z"/></svg>');
        }
      }
      
      h5 {
        font-size: 1.125rem;
        font-weight: 600;
        margin: 0 0 0.625rem;
        color: var(--color-text, #3b4863);
      }
      
      p {
        font-size: 0.875rem;
        line-height: 1.5;
        color: var(--color-text-light, #8392ab);
        margin: 0;
      }
    }
  }
  
  // Team section
  .team-block {
    .team-intro {
      font-size: 1.0625rem;
      line-height: 1.7;
      color: var(--color-text, #3b4863);
      margin: 0 0 2rem;
      text-align: center;
    }
    
    .team-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 2rem;
      margin-bottom: 3rem;
      
      @media (max-width: 768px) {
        grid-template-columns: 1fr;
      }
    }
    
    .team-member {
      display: flex;
      gap: 1.5rem;
      background: rgba(255, 255, 255, 0.7);
      border-radius: 16px;
      padding: 1.5rem;
      border: 1px solid rgba(var(--color-primary-rgb, 52, 97, 255), 0.05);
      transition: all 0.3s ease;
      
      &:hover {
        transform: translateY(-5px);
        box-shadow: 0 12px 24px rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
        border-color: rgba(var(--color-primary-rgb, 52, 97, 255), 0.15);
        
        .member-photo {
          transform: scale(1.05);
        }
      }
      
      .member-photo {
        width: 100px;
        height: 100px;
        border-radius: 50%;
        background-color: #e2e8f0;
        background-size: cover;
        background-position: center;
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
        transition: transform 0.3s ease;
        
        &.kohulan {
          background-image: url('https://via.placeholder.com/100?text=KR');
        }
        
        &.christoph {
          background-image: url('https://via.placeholder.com/100?text=CS');
        }
      }
      
      .member-info {
        flex: 1;
        
        h4 {
          font-size: 1.25rem;
          font-weight: 600;
          margin: 0 0 0.25rem;
          color: var(--color-text, #3b4863);
        }
        
        .member-role {
          font-size: 0.9375rem;
          font-weight: 500;
          color: var(--color-primary, #3461ff);
          margin: 0 0 0.75rem;
        }
        
        .member-desc {
          font-size: 0.875rem;
          line-height: 1.5;
          color: var(--color-text-light, #8392ab);
          margin: 0 0 1rem;
        }
        
        .member-links {
          display: flex;
          gap: 0.75rem;
          
          .member-link {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
            color: var(--color-primary, #3461ff);
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
            
            &:hover {
              background: var(--color-primary, #3461ff);
              color: white;
              transform: translateY(-3px);
            }
          }
        }
      }
      
      @media (max-width: 480px) {
        flex-direction: column;
        align-items: center;
        text-align: center;
        
        .member-photo {
          width: 120px;
          height: 120px;
        }
        
        .member-info {
          .member-links {
            justify-content: center;
          }
        }
      }
    }
    
    .team-cta {
      text-align: center;
      background: linear-gradient(135deg, 
        rgba(var(--color-primary-rgb, 52, 97, 255), 0.05) 0%, 
        rgba(var(--color-primary-rgb, 52, 97, 255), 0.1) 100%
      );
      border-radius: 16px;
      padding: 2rem;
      margin-top: 2rem;
      
      h4 {
        font-size: 1.375rem;
        font-weight: 600;
        margin: 0 0 0.75rem;
        color: var(--color-text, #3b4863);
      }
      
      p {
        font-size: 1rem;
        line-height: 1.6;
        color: var(--color-text-light, #8392ab);
        margin: 0 0 1.5rem;
        max-width: 600px;
        margin-left: auto;
        margin-right: auto;
      }
      
      .team-buttons {
        display: flex;
        gap: 1rem;
        justify-content: center;
        
        @media (max-width: 480px) {
          flex-direction: column;
          align-items: center;
        }
      }
    }
  }
  
  // Publications
  .publications-block {
    .publications-intro {
      font-size: 1.0625rem;
      line-height: 1.7;
      color: var(--color-text, #3b4863);
      margin: 0 0 2rem;
      text-align: center;
    }
    
    .publications-list {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }
    
    .publication {
      display: flex;
      gap: 1.25rem;
      background: rgba(255, 255, 255, 0.7);
      border-radius: 16px;
      padding: 1.5rem;
      border: 1px solid rgba(var(--color-primary-rgb, 52, 97, 255), 0.05);
      transition: all 0.3s ease;
      
      &:hover {
        transform: translateY(-5px);
        box-shadow: 0 12px 24px rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
        border-color: rgba(var(--color-primary-rgb, 52, 97, 255), 0.15);
        
        .publication-icon {
          transform: scale(1.1);
          background: var(--color-primary, #3461ff);
          color: white;
        }
      }
      
      .publication-icon {
        width: 48px;
        height: 48px;
        min-width: 48px;
        border-radius: 12px;
        background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
        color: var(--color-primary, #3461ff);
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.3s ease;
      }
      
      .publication-info {
        flex: 1;
        
        h4 {
          font-size: 1.125rem;
          font-weight: 600;
          margin: 0 0 0.5rem;
          color: var(--color-text, #3b4863);
        }
        
        .publication-authors {
          font-size: 0.9375rem;
          color: var(--color-text, #3b4863);
          margin: 0 0 0.25rem;
        }
        
        .publication-journal {
          font-size: 0.875rem;
          font-style: italic;
          color: var(--color-text-light, #8392ab);
          margin: 0 0 0.75rem;
        }
        
        .publication-link {
          display: inline-flex;
          align-items: center;
          gap: 0.375rem;
          font-size: 0.8125rem;
          color: var(--color-primary, #3461ff);
          text-decoration: none;
          transition: all 0.3s ease;
          
          &:hover {
            text-decoration: underline;
          }
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
  
  // Call to action
  .about-cta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--gradient-primary, linear-gradient(135deg, #4a6cf7 0%, #2254e2 100%));
    border-radius: 20px;
    padding: 2.5rem;
    overflow: hidden;
    position: relative;
    margin-bottom: 1rem;
    
    @media (max-width: 768px) {
      flex-direction: column;
      text-align: center;
      gap: 2rem;
      padding: 2rem;
    }
    
    &:before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: radial-gradient(circle at bottom right, 
        rgba(255, 255, 255, 0.2) 0%, 
        rgba(255, 255, 255, 0) 70%
      );
      opacity: 0.8;
      z-index: 0;
    }
    
    .cta-content {
      position: relative;
      z-index: 1;
      
      h3 {
        font-size: 1.5rem;
        font-weight: 700;
        color: white;
        margin: 0 0 0.5rem;
        
        @media (max-width: 768px) {
          font-size: 1.25rem;
        }
      }
      
      p {
        font-size: 1rem;
        color: rgba(255, 255, 255, 0.8);
        margin: 0;
      }
    }
    
    .btn-large {
      padding: 0 1.5rem;
      height: 50px;
      font-size: 1rem;
      font-weight: 600;
      background: white;
      color: var(--color-primary, #3461ff);
      border: none;
      border-radius: 10px;
      cursor: pointer;
      position: relative;
      z-index: 1;
      display: flex;
      align-items: center;
      gap: 0.75rem;
      transition: all 0.3s ease;
      box-shadow: 0 6px 15px rgba(0, 0, 0, 0.15);
      
      &:hover {
        transform: translateY(-4px);
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
      }
      
      .btn-icon {
        color: var(--color-primary, #3461ff);
      }
      
      .btn-bg {
        background: white;
      }
    }
  }
  
  // Buttons
  .btn {
    height: 48px;
    border-radius: 10px;
    font-weight: 600;
    font-size: 0.9375rem;
    transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
    text-decoration: none;
    position: relative;
    overflow: hidden;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.625rem;
    padding: 0 1.25rem;
    
    .btn-bg {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      border-radius: 10px;
      transition: all 0.3s ease;
      z-index: -1;
    }
    
    &.btn-primary {
      color: white;
      
      .btn-bg {
        background: var(--gradient-primary, linear-gradient(135deg, #4a6cf7 0%, #2254e2 100%));
        box-shadow: 
          0 4px 10px rgba(var(--color-primary-rgb, 52, 97, 255), 0.2),
          inset 0 0 0 1px rgba(255, 255, 255, 0.1);
      }
      
      &:hover {
        transform: translateY(-3px);
        
        .btn-bg {
          box-shadow: 
            0 6px 15px rgba(var(--color-primary-rgb, 52, 97, 255), 0.3),
            inset 0 0 0 1px rgba(255, 255, 255, 0.2);
        }
      }
      
      &:active {
        transform: scale(0.98);
      }
    }
    
    &.btn-secondary {
      color: var(--color-primary, #3461ff);
      border: 1px solid rgba(var(--color-primary-rgb, 52, 97, 255), 0.3);
      background: transparent;
      
      &:hover {
        background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.05);
        border-color: var(--color-primary, #3461ff);
        transform: translateY(-3px);
      }
      
      &:active {
        transform: scale(0.98);
      }
    }
  }
  
  // Close button
  .close-btn {
    position: fixed;
    top: 1.5rem;
    right: 1.5rem;
    background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
    border: none;
    border-radius: 50%;
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    color: var(--color-primary, #3461ff);
    transition: all 0.3s ease;
    z-index: 10;
    
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
      background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.2);
      transform: rotate(90deg);
    }
  }
}

// Animations
@keyframes float {
  0% {
    transform: translateY(0px);
  }
  50% {
    transform: translateY(-10px);
  }
  100% {
    transform: translateY(0px);
  }
}
</style>