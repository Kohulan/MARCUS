<template>
  <section id="features" class="features-section">
    <!-- Hero Section - Added from previous implementation -->
    <section class="hero-section" v-if="showHero">
      <div class="hero-bg"></div>
      <div class="container hero-container">
        <div class="hero-content">
          <h1 class="hero-title">
            Molecular Annotation and Recognition for Curating Unravelled Structures
          </h1>
          <p class="hero-description">
            Extract, recognize, and annotate chemical structures from scientific literature with unprecedented accuracy using AI-powered tools.
          </p>
          <div class="hero-actions">
            <button class="btn btn-primary" @click="scrollToUpload">
              <div class="btn-bg"></div>
              <vue-feather type="upload" class="btn-icon"></vue-feather>
              <span>Upload Document</span>
            </button>
            <button class="btn btn-secondary" @click="scrollToFeatures">
              <vue-feather type="info" class="btn-icon"></vue-feather>
              <span>Learn More</span>
            </button>
          </div>
        </div>
        <div class="hero-image">
          <img src="@/assets/hero-illustration.svg" alt="MARCUS Illustration" />
        </div>
      </div>
    </section>

    <div class="container">
      <div class="section-header">
        <div class="section-tag">Key Capabilities</div>
        <h2 class="section-title">MARCUS Features</h2>
        <p class="section-description">
          Powerful tools for extracting, analyzing, and curating chemical structures from scientific literature
        </p>
      </div>
      
      <div class="features-grid">
        <!-- Feature 1: PDF Structure Extraction -->
        <div class="feature-card">
          <div class="feature-icon-wrapper">
            <div class="feature-icon-bg"></div>
            <vue-feather type="file-text" class="feature-icon"></vue-feather>
          </div>
          <h3 class="feature-title">Chemical Structure Extraction</h3>
          <p class="feature-description">
            Extract chemical structures from PDF documents with high precision. Our advanced segmentation technology identifies and isolates structures from complex scientific documents.
          </p>
          <div class="feature-footer">
            <button class="feature-link" @click="scrollToUpload">
              <span>Upload a PDF</span>
              <vue-feather type="arrow-right" size="16"></vue-feather>
            </button>
          </div>
        </div>
        
        <!-- Feature 2: OCSR Technology -->
        <div class="feature-card">
          <div class="feature-icon-wrapper">
            <div class="feature-icon-bg"></div>
            <vue-feather type="eye" class="feature-icon"></vue-feather>
          </div>
          <h3 class="feature-title">Optical Chemical Structure Recognition</h3>
          <p class="feature-description">
            Convert visual chemical structures into machine-readable formats (SMILES, molfiles) using state-of-the-art OCSR engines including DECIMER, MolScribe and MolNexTR.
          </p>
          <div class="feature-footer">
            <button class="feature-link" @click="showOcsrInfo">
              <span>Learn about OCSR</span>
              <vue-feather type="arrow-right" size="16"></vue-feather>
            </button>
          </div>
        </div>
        
        <!-- Feature 3: Text Extraction -->
        <div class="feature-card">
          <div class="feature-icon-wrapper">
            <div class="feature-icon-bg"></div>
            <vue-feather type="align-left" class="feature-icon"></vue-feather>
          </div>
          <h3 class="feature-title">Text & Metadata Extraction</h3>
          <p class="feature-description">
            Extract and analyze text surrounding chemical structures to capture valuable metadata, including compound names, properties, and biological activities.
          </p>
          <div class="feature-footer">
            <button class="feature-link" @click="scrollToTextTools">
              <span>Text Extraction Tools</span>
              <vue-feather type="arrow-right" size="16"></vue-feather>
            </button>
          </div>
        </div>
        
        <!-- Feature 4: Annotation -->
        <div class="feature-card">
          <div class="feature-icon-wrapper">
            <div class="feature-icon-bg"></div>
            <vue-feather type="tag" class="feature-icon"></vue-feather>
          </div>
          <h3 class="feature-title">Automated Annotation</h3>
          <p class="feature-description">
            AI-powered annotation tools identify and extract key compound information including molecular properties, source organisms, and bioactivity data from scientific text.
          </p>
          <div class="feature-footer">
            <button class="feature-link" @click="scrollToAnnotation">
              <span>Annotation Tools</span>
              <vue-feather type="arrow-right" size="16"></vue-feather>
            </button>
          </div>
        </div>
        
        <!-- Feature 5: Integration -->
        <div class="feature-card">
          <div class="feature-icon-wrapper">
            <div class="feature-icon-bg"></div>
            <vue-feather type="database" class="feature-icon"></vue-feather>
          </div>
          <h3 class="feature-title">COCONUT Integration</h3>
          <p class="feature-description">
            Seamlessly import extracted and annotated structures to the COCONUT database, the most comprehensive open collection of natural products.
          </p>
          <div class="feature-footer">
            <a href="https://coconut.naturalproducts.net/" target="_blank" class="feature-link external">
              <span>Visit COCONUT</span>
              <vue-feather type="external-link" size="16"></vue-feather>
            </a>
          </div>
        </div>
        
        <!-- Feature 6: Batch Processing -->
        <div class="feature-card">
          <div class="feature-icon-wrapper">
            <div class="feature-icon-bg"></div>
            <vue-feather type="layers" class="feature-icon"></vue-feather>
          </div>
          <h3 class="feature-title">Batch Processing</h3>
          <p class="feature-description">
            Process multiple documents and structures at once with efficient batch processing capabilities, saving time and streamlining workflows.
          </p>
          <div class="feature-footer">
            <button class="feature-link" @click="showBatchInfo">
              <span>Batch Processing Tips</span>
              <vue-feather type="arrow-right" size="16"></vue-feather>
            </button>
          </div>
        </div>
      </div>
      
      <!-- Technology showcase -->
      <div class="technology-showcase">
        <div class="showcase-header">
          <h3>Powered by Advanced AI Technologies</h3>
          <p>MARCUS leverages cutting-edge models and algorithms for accurate structure recognition</p>
        </div>
        
        <div class="tech-logos">
          <div class="tech-logo">
            <span class="tech-img decimer-logo"></span>
            <span class="tech-name">DECIMER</span>
          </div>
          <div class="tech-logo">
            <span class="tech-img molscribe-logo"></span>
            <span class="tech-name">MolScribe</span>
          </div>
          <div class="tech-logo">
            <span class="tech-img molnextr-logo"></span>
            <span class="tech-name">MolNexTR</span>
          </div>
          <div class="tech-logo">
            <span class="tech-img openai-logo"></span>
            <span class="tech-name">OpenAI</span>
          </div>
          <div class="tech-logo">
            <span class="tech-img docling-logo"></span>
            <span class="tech-name">Docling</span>
          </div>
        </div>
      </div>
      
      <!-- Workflow Diagram - New addition -->
      <div class="workflow-section">
        <h3 class="workflow-title">Seamless Processing Workflow</h3>
        <div class="workflow-diagram">
          <div class="workflow-step">
            <div class="workflow-step-icon">
              <vue-feather type="upload-cloud" size="28"></vue-feather>
            </div>
            <h4>Upload Document</h4>
            <p>Upload your scientific PDF with chemical structures</p>
          </div>
          <div class="workflow-arrow">
            <vue-feather type="arrow-right" size="20"></vue-feather>
          </div>
          <div class="workflow-step">
            <div class="workflow-step-icon">
              <vue-feather type="image" size="28"></vue-feather>
            </div>
            <h4>Extract Structures</h4>
            <p>Automatically identify and extract chemical structures</p>
          </div>
          <div class="workflow-arrow">
            <vue-feather type="arrow-right" size="20"></vue-feather>
          </div>
          <div class="workflow-step">
            <div class="workflow-step-icon">
              <vue-feather type="code" size="28"></vue-feather>
            </div>
            <h4>Convert to SMILES</h4>
            <p>Translate images to machine-readable formats</p>
          </div>
          <div class="workflow-arrow">
            <vue-feather type="arrow-right" size="20"></vue-feather>
          </div>
          <div class="workflow-step">
            <div class="workflow-step-icon">
              <vue-feather type="database" size="28"></vue-feather>
            </div>
            <h4>Store & Export</h4>
            <p>Save to COCONUT or export in your preferred format</p>
          </div>
        </div>
      </div>
      
      <!-- Call to action -->
      <div class="features-cta">
        <div class="cta-content">
          <h3>Ready to Streamline Your Chemical Structure Curation?</h3>
          <p>Upload your first document and explore the power of MARCUS</p>
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
  name: 'FeaturesSection',
  
  props: {
    showCloseButton: {
      type: Boolean,
      default: false
    },
    showHero: {
      type: Boolean,
      default: true
    }
  },
  
  methods: {
    scrollToUpload() {
      // Find upload section and scroll to it
      const uploadSection = document.getElementById('document-upload');
      if (uploadSection) {
        uploadSection.scrollIntoView({ behavior: 'smooth' });
      } else {
        // If section not found, emit close event to go back to main page
        this.$emit('close');
      }
    },
    
    scrollToFeatures() {
      // Scroll to features section
      const featuresSection = document.getElementById('features');
      if (featuresSection) {
        // Find the features grid to scroll to (it's below the hero section)
        const featuresGrid = featuresSection.querySelector('.features-grid');
        if (featuresGrid) {
          featuresGrid.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
          // Fallback to section header
          const sectionHeader = featuresSection.querySelector('.section-header');
          if (sectionHeader) {
            sectionHeader.scrollIntoView({ behavior: 'smooth', block: 'start' });
          } else {
            // Fallback to section itself
            featuresSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }
        }
      }
    },
    
    scrollToTextTools() {
      // Scroll to text extraction tools
      const textSection = document.getElementById('text-extraction');
      if (textSection) {
        textSection.scrollIntoView({ behavior: 'smooth' });
      } else {
        this.scrollToUpload();
      }
    },
    
    scrollToAnnotation() {
      // Scroll to annotation section
      const annotationSection = document.getElementById('annotations');
      if (annotationSection) {
        annotationSection.scrollIntoView({ behavior: 'smooth' });
      } else {
        this.scrollToUpload();
      }
    },
    
    showOcsrInfo() {
      // Show OCSR information notification
      this.$store.dispatch('showOcsrInfo');
    },
    
    showBatchInfo() {
      // Show batch processing information notification
      this.$store.dispatch('showBatchInfo');
    }
  }
}
</script>

<style lang="scss" scoped>
.features-section {
  padding: 2rem 0 5rem;
  background: var(--color-bg, #f8fafc);
  position: relative;
  overflow: hidden;
  
  &:before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: radial-gradient(circle at top right, 
      rgba(var(--color-primary-rgb, 52, 97, 255), 0.05) 0%, 
      rgba(var(--color-primary-rgb, 52, 97, 255), 0) 60%
    );
    opacity: 0.8;
    z-index: 0;
  }
  
  /* Hero Section Styles */
  .hero-section {
    padding: 4rem 0;
    position: relative;
    overflow: hidden;
    margin-bottom: 2rem;
    
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
    
    .hero-container {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 3rem;
      
      @media (max-width: 1024px) {
        flex-direction: column;
        text-align: center;
      }
    }
    
    .hero-content {
      flex: 1;
      max-width: 600px;
      
      @media (max-width: 1024px) {
        max-width: 100%;
      }
    }
    
    .hero-title {
      font-size: 3rem;
      font-weight: 800;
      line-height: 1.2;
      margin: 0 0 1.5rem;
      background: var(--gradient-primary, linear-gradient(135deg, #4a6cf7 0%, #2254e2 100%));
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
      
      @media (max-width: 768px) {
        font-size: 2.25rem;
      }
      
      @media (max-width: 480px) {
        font-size: 1.75rem;
      }
    }
    
    .hero-description {
      font-size: 1.25rem;
      color: var(--color-text-light, #8392ab);
      line-height: 1.6;
      margin: 0 0 2rem;
      
      @media (max-width: 768px) {
        font-size: 1.125rem;
      }
    }
    
    .hero-actions {
      display: flex;
      gap: 1rem;
      
      @media (max-width: 1024px) {
        justify-content: center;
      }
      
      @media (max-width: 480px) {
        flex-direction: column;
        width: 100%;
        max-width: 300px;
        margin: 0 auto;
      }
    }
    
    .hero-image {
      flex: 1;
      max-width: 500px;
      display: flex;
      align-items: center;
      justify-content: center;
      
      img {
        width: 100%;
        height: auto;
        max-width: 100%;
        filter: drop-shadow(0 10px 30px rgba(var(--color-primary-rgb, 52, 97, 255), 0.2));
        animation: float 6s ease-in-out infinite;
      }
      
      @keyframes float {
        0% {
          transform: translateY(0px);
        }
        50% {
          transform: translateY(-20px);
        }
        100% {
          transform: translateY(0px);
        }
      }
      
      @media (max-width: 1024px) {
        max-width: 400px;
      }
    }
  }
  
  .container {
    position: relative;
    z-index: 1;
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 1.5rem;
  }
  
  .section-header {
    text-align: center;
    max-width: 800px;
    margin: 0 auto 4rem;
  }
  
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
  
  .features-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 2rem;
    margin-bottom: 4rem;
    
    @media (max-width: 1024px) {
      grid-template-columns: repeat(2, 1fr);
    }
    
    @media (max-width: 640px) {
      grid-template-columns: 1fr;
    }
  }
  
  .feature-card {
    background: rgba(var(--color-bg-card-rgb, 255, 255, 255), 0.5);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-radius: 16px;
    padding: 2rem;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
    border: 1px solid rgba(var(--color-primary-rgb, 52, 97, 255), 0.08);
    transition: all 0.3s ease;
    display: flex;
    flex-direction: column;
    height: 100%;
    
    &:hover {
      transform: translateY(-8px);
      box-shadow: 0 12px 30px rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
      border-color: rgba(var(--color-primary-rgb, 52, 97, 255), 0.2);
      
      .feature-icon-wrapper {
        transform: scale(1.05);
        
        .feature-icon-bg {
          opacity: 1;
        }
      }
      
      .feature-icon {
        transform: scale(1.1);
      }
    }
  }
  
  .feature-icon-wrapper {
    width: 64px;
    height: 64px;
    border-radius: 16px;
    background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 1.5rem;
    position: relative;
    transition: all 0.3s ease;
    
    .feature-icon-bg {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: var(--gradient-primary, linear-gradient(135deg, #4a6cf7 0%, #2254e2 100%));
      opacity: 0.2;
      border-radius: 16px;
      transition: opacity 0.3s ease;
    }
  }
  
  .feature-icon {
    width: 28px;
    height: 28px;
    color: var(--color-primary, #3461ff);
    position: relative;
    z-index: 1;
    transition: transform 0.3s ease;
  }
  
  .feature-title {
    font-size: 1.25rem;
    font-weight: 700;
    margin: 0 0 1rem;
    color: var(--color-text, #3b4863);
  }
  
  .feature-description {
    font-size: 0.95rem;
    color: var(--color-text-light, #8392ab);
    line-height: 1.6;
    margin: 0 0 1.5rem;
    flex-grow: 1;
  }
  
  .feature-footer {
    margin-top: auto;
  }
  
  .feature-link {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--color-primary, #3461ff);
    background: none;
    border: none;
    padding: 0.5rem 0;
    cursor: pointer;
    transition: all 0.3s ease;
    text-decoration: none;
    
    &:hover {
      gap: 0.75rem;
      
      svg {
        transform: translateX(4px);
      }
    }
    
    svg {
      transition: transform 0.3s ease;
    }
    
    &.external:hover svg {
      transform: translateY(-4px) translateX(4px);
    }
  }
  
  /* Technology showcase section */
  .technology-showcase {
    background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.03);
    border-radius: 20px;
    padding: 3rem 2rem;
    margin-bottom: 4rem;
    text-align: center;
    
    .showcase-header {
      margin-bottom: 2rem;
      
      h3 {
        font-size: 1.5rem;
        font-weight: 700;
        margin: 0 0 0.75rem;
        color: var(--color-text, #3b4863);
      }
      
      p {
        font-size: 1rem;
        color: var(--color-text-light, #8392ab);
        max-width: 600px;
        margin: 0 auto;
      }
    }
    
    .tech-logos {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      align-items: center;
      gap: 2.5rem;
      
      @media (max-width: 640px) {
        gap: 1.5rem;
      }
    }
    
    .tech-logo {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.5rem;
      
      .tech-img {
        height: 48px;
        width: 48px;
        display: block;
        filter: grayscale(50%);
        opacity: 0.7;
        transition: all 0.3s ease;
        background-position: center;
        background-repeat: no-repeat;
        background-size: contain;
        
        &.decimer-logo {
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'%3E%3Ccircle cx='24' cy='24' r='20' fill='%233461ff'/%3E%3Cpath d='M16 16 L32 16 L32 32 L16 32 Z' fill='none' stroke='white' stroke-width='2'/%3E%3Cpath d='M20 20 L28 20 L28 28 L20 28 Z' fill='white'/%3E%3C/svg%3E");
        }
        
        &.molscribe-logo {
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'%3E%3Ccircle cx='24' cy='24' r='20' fill='%233461ff'/%3E%3Cpath d='M20 18 L28 18 L32 28 L24 32 L16 28 Z' fill='none' stroke='white' stroke-width='2'/%3E%3Cpath d='M24 16 L24 32' stroke='white' stroke-width='2'/%3E%3Cpath d='M36 16 L32 20 L32 28' stroke='white' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E");
        }
        
        &.molnextr-logo {
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'%3E%3Ccircle cx='24' cy='24' r='20' fill='%233461ff'/%3E%3Cpath d='M16 24 L24 16 L32 24 L24 32 Z' fill='white'/%3E%3C/svg%3E");
        }
        
        &.openai-logo {
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'%3E%3Ccircle cx='24' cy='24' r='20' fill='%233461ff'/%3E%3Cpath d='M24 14 L34 24 L24 34 L14 24 Z' fill='none' stroke='white' stroke-width='2'/%3E%3Ccircle cx='24' cy='24' r='6' fill='white'/%3E%3C/svg%3E");
        }
        
        &.docling-logo {
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'%3E%3Ccircle cx='24' cy='24' r='20' fill='%233461ff'/%3E%3Cpath d='M18 16 L30 16 L30 32 L18 32 Z' fill='none' stroke='white' stroke-width='2'/%3E%3Cpath d='M18 20 L30 20 M18 24 L26 24 M18 28 L28 28' stroke='white' stroke-width='2'/%3E%3C/svg%3E");
        }
        
        @media (max-width: 640px) {
          height: 40px;
          width: 40px;
        }
      }
      
      .tech-name {
        font-size: 0.8rem;
        font-weight: 600;
        color: var(--color-text-light, #8392ab);
        transition: color 0.3s ease;
      }
      
      &:hover {
        .tech-img {
          filter: grayscale(0%);
          opacity: 1;
        }
        
        .tech-name {
          color: var(--color-primary, #3461ff);
        }
      }
    }
  }
  
  /* New Workflow Diagram Section */
  .workflow-section {
    margin-bottom: 4rem;
    text-align: center;
    padding: 2rem;
    background: rgba(var(--color-bg-card-rgb, 255, 255, 255), 0.7);
    border-radius: 20px;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.05);
    backdrop-filter: blur(10px);
    
    .workflow-title {
      font-size: 1.5rem;
      font-weight: 700;
      margin: 0 0 2.5rem;
      color: var(--color-text, #3b4863);
    }
    
    .workflow-diagram {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 1rem;
      flex-wrap: wrap;
      
      @media (max-width: 768px) {
        flex-direction: column;
        
        .workflow-arrow {
          transform: rotate(90deg);
          margin: 0.5rem 0;
        }
      }
    }
    
    .workflow-step {
      flex: 1;
      min-width: 180px;
      padding: 1.5rem 1rem;
      background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.05);
      border-radius: 12px;
      text-align: center;
      border: 1px solid rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
      transition: all 0.3s ease;
      
      &:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 20px rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
        background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.08);
        
        .workflow-step-icon {
          background: var(--color-primary, #3461ff);
          color: white;
        }
      }
      
      .workflow-step-icon {
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
        color: var(--color-primary, #3461ff);
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto 1rem;
        transition: all 0.3s ease;
      }
      
      h4 {
        font-size: 1.1rem;
        font-weight: 600;
        margin: 0 0 0.5rem;
        color: var(--color-text, #3b4863);
      }
      
      p {
        font-size: 0.9rem;
        color: var(--color-text-light, #8392ab);
        margin: 0;
        line-height: 1.4;
      }
      
      @media (max-width: 768px) {
        min-width: 250px;
      }
    }
    
    .workflow-arrow {
      color: var(--color-primary, #3461ff);
      opacity: 0.7;
      
      @media (max-width: 768px) {
        margin: 0.5rem 0;
      }
    }
  }
  
  /* Call to action section */
  .features-cta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--gradient-primary, linear-gradient(135deg, #4a6cf7 0%, #2254e2 100%));
    border-radius: 20px;
    padding: 2.5rem;
    overflow: hidden;
    position: relative;
    
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
  
  /* General button styles */
  .btn {
    height: 48px;
    padding: 0 1.5rem;
    border-radius: 10px;
    font-weight: 600;
    font-size: 1rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    transition: all 0.3s ease;
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
      background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.05);
      
      &:hover {
        background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
        transform: translateY(-3px);
      }
      
      &:active {
        transform: scale(0.98);
      }
    }
    
    .btn-icon {
      width: 20px;
      height: 20px;
    }
  }
  
  // Close button for modal view
  .close-btn {
    position: fixed;
    top: 1rem;
    right: 1rem;
    background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.1);
    color: var(--color-primary, #3461ff);
    border: none;
    border-radius: 50%;
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.3s ease;
    z-index: 10;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
    
    span {
      display: none;
    }
    
    &:hover {
      background: rgba(var(--color-primary-rgb, 52, 97, 255), 0.2);
      transform: rotate(90deg);
    }
  }
}
</style>