<template>
    <div class="disclaimer-page">
      <div class="page-header">
        <div class="header-bg"></div>
        <div class="container">
          <h1>Disclaimer</h1>
          <p class="subtitle">Important information about MARCUS</p>
        </div>
        
        <button class="close-button" @click="$emit('close')" aria-label="Close disclaimer">
          <vue-feather type="x" size="24"></vue-feather>
        </button>
      </div>
      
      <div class="container">
        <div class="content-card">
          <div class="disclaimer-section">
            <div class="section-icon">
              <vue-feather type="info" size="24"></vue-feather>
            </div>
            <div class="section-content">
              <h2>About MARCUS</h2>
              <p>
                MARCUS (Molecular Annotation and Recognition for Curating Unravelled Structures) is an experimental system 
                designed for the extraction, recognition, and annotation of chemical structures from scientific literature,
                with a focus on natural products. It combines machine learning models for image processing, chemical structure 
                recognition, and text analysis.
              </p>
            </div>
          </div>
          
          <div class="disclaimer-section">
            <div class="section-icon">
              <vue-feather type="tool" size="24"></vue-feather>
            </div>
            <div class="section-content">
              <h2>Research Tool</h2>
              <p>
                MARCUS is intended to be used as a research tool by scientists and researchers in the field of chemistry, 
                particularly those studying natural products. The system is still under active development and should be 
                considered a research prototype rather than a production-ready service.
              </p>
            </div>
          </div>
          
          <div class="disclaimer-section">
            <div class="section-icon">
              <vue-feather type="alert-triangle" size="24"></vue-feather>
            </div>
            <div class="section-content">
              <h2>Accuracy Limitations</h2>
              <p>
                While we strive for high accuracy, the automatic extraction and recognition of chemical structures 
                and related information from scientific publications is a complex task. The results provided by MARCUS 
                should always be verified by qualified professionals before being used in any critical research, 
                publication, or application.
              </p>
              <p>
                The accuracy of our models may vary depending on:
              </p>
              <ul>
                <li>Image quality in the source document</li>
                <li>Complexity of the chemical structures</li>
                <li>Format and layout of the original publication</li>
                <li>Handwritten versus printed chemical structures</li>
              </ul>
            </div>
          </div>
          
          <div class="disclaimer-section">
            <div class="section-icon">
              <vue-feather type="shield" size="24"></vue-feather>
            </div>
            <div class="section-content">
              <h2>Data Privacy</h2>
              <p>
                When using MARCUS, the documents and images you upload may be temporarily stored on our servers 
                for processing purposes. While we implement reasonable security measures, we recommend not uploading 
                confidential or sensitive unpublished research without taking appropriate precautions.
              </p>
              <p>
                Uploaded files are stored in isolated directories and are not shared with third parties. 
                We may use anonymized data to improve our models and services.
              </p>
            </div>
          </div>
          
          <div class="disclaimer-section">
            <div class="section-icon">
              <vue-feather type="book" size="24"></vue-feather>
            </div>
            <div class="section-content">
              <h2>Citation and Attribution</h2>
              <p>
                If you use MARCUS in your research, please cite our work using the following information:
              </p>
              <div class="citation-box">
                <p>
                  Working on: MARCUS: Molecular Annotation and Recognition for Curating Unravelled Structures.
                <span class="citation-note">(Publication details to be updated)</span>
                </p>
                <button class="btn-copy" @click="copyCitation">
                  <vue-feather type="copy" size="16"></vue-feather>
                  Copy Citation
                </button>
              </div>
              <p>
                MARCUS builds upon several open-source projects, including DECIMER for chemical structure segmentation 
                and recognition. Please also consider citing these underlying technologies when appropriate.
              </p>
            </div>
          </div>
          
          <div class="disclaimer-section">
            <div class="section-icon">
              <vue-feather type="award" size="24"></vue-feather>
            </div>
            <div class="section-content">
              <h2>License</h2>
              <p>
                MARCUS is released under the MIT License. The underlying models and components may be subject 
                to their own licenses and terms of use.
              </p>
              <p>
                While MARCUS is designed to extract information from scientific publications, users are 
                responsible for ensuring their use complies with copyright laws and the terms of access for 
                the publications they analyze.
              </p>
            </div>
          </div>
          
          <div class="disclaimer-section">
            <div class="section-icon">
              <vue-feather type="users" size="24"></vue-feather>
            </div>
            <div class="section-content">
              <h2>Contact Information</h2>
              <p>
                For questions, feedback, or support related to MARCUS, please contact:
              </p>
              <div class="contact-info">
                <p>
                  <vue-feather type="user" size="16"></vue-feather>
                  <span>Kohulan Rajan</span>
                </p>
                <p>
                  <vue-feather type="mail" size="16"></vue-feather>
                  <a href="mailto:kohulan.rajan@uni-jena.de">kohulan.rajan@uni-jena.de</a>
                </p>
                <p>
                  <vue-feather type="globe" size="16"></vue-feather>
                  <a href="https://cheminf.uni-jena.de/" target="_blank">Cheminformatics and Computational Metabolomics</a>
                  <br>
                  <span class="indent">Friedrich Schiller University Jena, Germany</span>
                </p>
              </div>
            </div>
          </div>
          
          <div class="disclaimer-footer">
            <p>Last updated: {{ currentDate }}</p>
            <div class="action-links">
              <button class="btn-secondary" @click="$emit('close')">
                <vue-feather type="arrow-left" size="16"></vue-feather>
                Back to Application
              </button>
              <a href="https://github.com/Kohulan/MARCUS" target="_blank" class="btn-primary">
                <vue-feather type="github" size="16"></vue-feather>
                View on GitHub
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  </template>
  
  <script>
  export default {
    name: 'DisclaimerPage',
    
    data() {
      return {
        currentDate: new Date().toISOString().split('T')[0] // YYYY-MM-DD format
      }
    },
    
    methods: {
      copyCitation() {
        const citation = "Working paper: . MARCUS: Molecular Annotation and Recognition for Curating Unravelled Structures.";
        navigator.clipboard.writeText(citation)
          .then(() => {
            // Show notification using the store
            this.$store.dispatch('showNotification', {
              type: 'success',
              message: 'Citation copied to clipboard'
            });
          })
          .catch(err => {
            console.error('Failed to copy: ', err);
            this.$store.dispatch('showNotification', {
              type: 'error',
              message: 'Failed to copy citation'
            });
          });
      }
    }
  }
  </script>
  
  <style lang="scss" scoped>
  .disclaimer-page {
    min-height: 100vh;
    background-color: var(--color-bg);
    padding-bottom: 4rem;
    
    .container {
      max-width: 900px;
      margin: 0 auto;
      padding: 0 1.5rem;
    }
    
    .page-header {
      position: relative;
      padding: 5rem 0 3rem;
      margin-bottom: 2rem;
      color: white;
      overflow: hidden;
      
      .header-bg {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: var(--gradient-primary);
        z-index: -1;
        
        &:before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          background-image: 
            radial-gradient(circle at 20% 120%, rgba(255, 255, 255, 0.15) 0%, transparent 50%),
            radial-gradient(circle at 80% -20%, rgba(255, 255, 255, 0.2) 0%, transparent 60%);
        }
        
        &:after {
          content: '';
          position: absolute;
          bottom: 0;
          left: 0;
          width: 100%;
          height: 70px;
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1440 70'%3E%3Cpath fill='%23f7f9fc' d='M0,64L60,53.3C120,43,240,21,360,16C480,11,600,21,720,42.7C840,64,960,96,1080,96C1200,96,1320,64,1380,48L1440,32L1440,70L1380,70C1320,70,1200,70,1080,70C960,70,840,70,720,70C600,70,480,70,360,70C240,70,120,70,60,70L0,70Z'%3E%3C/path%3E%3C/svg%3E");
          background-size: cover;
          background-position: center top;
        }
      }
      
      .close-button {
        position: absolute;
        top: 1rem;
        right: 1rem;
        background: rgba(255, 255, 255, 0.2);
        border: none;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        z-index: 10;
        transition: all 0.2s ease;
        color: white;
        
        &:hover {
          background: rgba(255, 255, 255, 0.3);
          transform: rotate(90deg);
        }
      }
      
      h1 {
        font-size: 2.5rem;
        font-weight: 800;
        margin: 0 0 0.5rem;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
      }
      
      .subtitle {
        font-size: 1.1rem;
        font-weight: 400;
        margin: 0;
        opacity: 0.9;
      }
    }
    
    .content-card {
      background: var(--color-panel-bg);
      border-radius: 16px;
      box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.08);
      padding: 2rem;
      border: 1px solid var(--color-border);
      margin-top: -2rem;
      position: relative;
      z-index: 2;
      
      @media (min-width: 768px) {
        padding: 3rem;
      }
    }
    
    .disclaimer-section {
      display: flex;
      gap: 1.5rem;
      margin-bottom: 2.5rem;
      
      &:last-child {
        margin-bottom: 0;
      }
      
      @media (max-width: 767px) {
        flex-direction: column;
        gap: 1rem;
      }
      
      .section-icon {
        flex-shrink: 0;
        width: 48px;
        height: 48px;
        background: rgba(var(--color-primary-rgb), 0.1);
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: var(--color-primary);
        
        @media (max-width: 767px) {
          width: 40px;
          height: 40px;
          margin-bottom: 0.5rem;
        }
      }
      
      .section-content {
        flex: 1;
        
        h2 {
          margin: 0 0 1rem;
          font-size: 1.5rem;
          font-weight: 700;
          color: var(--color-text);
        }
        
        p {
          margin: 0 0 1rem;
          line-height: 1.6;
          color: var(--color-text-light);
          
          &:last-child {
            margin-bottom: 0;
          }
        }
        
        ul {
          margin: 0 0 1rem;
          padding-left: 1.5rem;
          
          li {
            margin-bottom: 0.5rem;
            color: var(--color-text-light);
            
            &:last-child {
              margin-bottom: 0;
            }
          }
        }
      }
    }
    
    .citation-box {
      background: rgba(var(--color-primary-rgb), 0.05);
      border-radius: 8px;
      padding: 1.25rem;
      margin: 1.5rem 0;
      border-left: 3px solid var(--color-primary);
      position: relative;
      
      p {
        margin: 0 !important;
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
        line-height: 1.5;
      }
      
      .citation-note {
        font-style: italic;
        color: var(--color-text-light);
        opacity: 0.8;
      }
      
      .btn-copy {
        position: absolute;
        top: 0.75rem;
        right: 0.75rem;
        background: rgba(var(--color-primary-rgb), 0.1);
        border: none;
        border-radius: 6px;
        color: var(--color-primary);
        font-size: 0.8rem;
        padding: 0.35rem 0.75rem;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        transition: all 0.2s ease;
        
        &:hover {
          background: rgba(var(--color-primary-rgb), 0.2);
        }
        
        &:active {
          transform: scale(0.98);
        }
      }
    }
    
    .contact-info {
      background: rgba(var(--color-primary-rgb), 0.03);
      border-radius: 8px;
      padding: 1.25rem;
      margin: 1rem 0;
      
      p {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0.75rem !important;
        
        &:last-child {
          margin-bottom: 0 !important;
        }
        
        a {
          color: var(--color-primary);
          text-decoration: none;
          transition: all 0.2s ease;
          
          &:hover {
            text-decoration: underline;
          }
        }
        
        .indent {
          margin-left: 1.5rem;
          color: var(--color-text-light);
          opacity: 0.8;
        }
      }
    }
    
    .disclaimer-footer {
      margin-top: 3rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--color-border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      
      @media (max-width: 767px) {
        flex-direction: column;
        gap: 1rem;
        align-items: flex-start;
      }
      
      p {
        margin: 0;
        font-size: 0.875rem;
        color: var(--color-text-light);
        opacity: 0.7;
      }
      
      .action-links {
        display: flex;
        gap: 1rem;
        
        @media (max-width: 767px) {
          width: 100%;
          flex-direction: column;
        }
      }
      
      .btn-primary, .btn-secondary {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.6rem 1.25rem;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.875rem;
        transition: all 0.3s ease;
        text-decoration: none;
        cursor: pointer;
        
        @media (max-width: 767px) {
          justify-content: center;
        }
      }
      
      .btn-primary {
        background: var(--gradient-primary);
        color: white;
        box-shadow: 0 4px 10px rgba(var(--color-primary-rgb), 0.2);
        border: none;
        
        &:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 15px rgba(var(--color-primary-rgb), 0.3);
        }
        
        &:active {
          transform: scale(0.98);
        }
      }
      
      .btn-secondary {
        background: rgba(var(--color-primary-rgb), 0.1);
        color: var(--color-primary);
        border: none;
        
        &:hover {
          background: rgba(var(--color-primary-rgb), 0.2);
        }
        
        &:active {
          transform: scale(0.98);
        }
      }
    }
  }
  </style>