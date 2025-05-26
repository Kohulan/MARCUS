<template>
    <div class="disclaimer-page">
      <div class="page-header">
        <div class="header-bg"></div>
        <div class="container">
          <h1>Disclaimer</h1>
          <p class="subtitle">Important information about <span class="marcus-text">MARCUS</span></p>
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
              <h2>About <span class="marcus-text">MARCUS</span></h2>
              <p>
                <span class="marcus-text">MARCUS</span> (Molecular Annotation and Recognition for Curating Unravelled Structures) is an experimental system 
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
                <span class="marcus-text">MARCUS</span> is intended to be used as a research tool by scientists and researchers in the field of chemistry, 
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
                and related information from scientific publications is a complex task. The results provided by <span class="marcus-text">MARCUS</span> 
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
                When using <span class="marcus-text">MARCUS</span>, the documents and images you upload may be temporarily stored on our servers 
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
                If you use <span class="marcus-text">MARCUS</span> in your research, please cite our work using the following information:
              </p>
              <div class="citation-box">
                <p>
                  Working on: <span class="marcus-text">MARCUS</span>: Molecular Annotation and Recognition for Curating Unravelled Structures.
                <span class="citation-note">(Publication details to be updated)</span>
                </p>
                <button class="btn-copy" @click="copyCitation">
                  <vue-feather type="copy" size="16"></vue-feather>
                  Copy Citation
                </button>
              </div>
              <p>
                <span class="marcus-text">MARCUS</span> builds upon several open-source projects, including DECIMER for chemical structure segmentation 
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
                <span class="marcus-text">MARCUS</span> is released under the MIT License. The underlying models and components may be subject 
                to their own licenses and terms of use.
              </p>
              <p>
                While <span class="marcus-text">MARCUS</span> is designed to extract information from scientific publications, users are 
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
                For questions, feedback, or support related to <span class="marcus-text">MARCUS</span>, please contact:
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
    height: 100vh;
    background: var(--color-bg);
    position: relative;
    overflow-x: hidden;
    overflow-y: auto;
    
    // Add sophisticated background pattern
    &:before {
      content: '';
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: 
        radial-gradient(circle at 20% 30%, rgba(var(--color-primary-rgb, 65, 97, 255), 0.03) 0%, transparent 50%),
        radial-gradient(circle at 80% 70%, rgba(var(--color-accent-rgb, 122, 69, 255), 0.04) 0%, transparent 50%),
        radial-gradient(circle at 50% 90%, rgba(var(--color-primary-rgb, 65, 97, 255), 0.02) 0%, transparent 50%);
      z-index: -1;
      pointer-events: none;
    }
    
    .container {
      max-width: 1200px;
      margin: 0 auto;
      padding: 0 2rem;
      
      @media (max-width: 768px) {
        padding: 0 1.5rem;
      }
    }
    
    .page-header {
      position: relative;
      padding: 6rem 0 4rem;
      margin-bottom: 3rem;
      background: linear-gradient(135deg, 
        rgba(var(--color-primary-rgb, 65, 97, 255), 0.12) 0%, 
        rgba(var(--color-accent-rgb, 122, 69, 255), 0.16) 50%,
        rgba(var(--color-primary-rgb, 65, 97, 255), 0.08) 100%);
      overflow: hidden;
      border-radius: 0 0 2rem 2rem;
      box-shadow: 0 20px 40px -10px rgba(var(--color-primary-rgb, 65, 97, 255), 0.1);
      
      // Enhanced background pattern
      &:before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-image: 
          radial-gradient(circle at 30% 120%, rgba(255, 255, 255, 0.1) 0%, transparent 50%),
          radial-gradient(circle at 70% -20%, rgba(255, 255, 255, 0.08) 0%, transparent 60%),
          radial-gradient(circle at 90% 80%, rgba(var(--color-accent-rgb, 122, 69, 255), 0.1) 0%, transparent 40%);
        z-index: 0;
      }
      
      // Floating decorative elements
      &:after {
        content: '';
        position: absolute;
        top: 20%;
        right: 10%;
        width: 200px;
        height: 200px;
        background: radial-gradient(circle, 
          rgba(var(--color-primary-rgb, 65, 97, 255), 0.08) 0%, 
          transparent 70%);
        border-radius: 50%;
        filter: blur(30px);
        animation: float-gentle 20s ease-in-out infinite;
        z-index: 0;
      }
      
      .container {
        position: relative;
        z-index: 1;
        text-align: center;
      }
      
      h1 {
        font-size: 3.5rem;
        font-weight: 900;
        background: linear-gradient(135deg, 
          var(--color-text) 0%, 
          rgba(var(--color-primary-rgb, 65, 97, 255), 0.9) 50%,
          var(--color-text) 100%);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        margin: 0 0 1.5rem;
        letter-spacing: -0.02em;
        position: relative;
        
        @media (max-width: 768px) {
          font-size: 2.8rem;
        }
        
        @media (max-width: 480px) {
          font-size: 2.4rem;
        }
      }
      
      .subtitle {
        font-size: 1.35rem;
        font-weight: 500;
        color: var(--color-text-light);
        margin: 0;
        opacity: 0.85;
        max-width: 600px;
        margin: 0 auto;
        line-height: 1.5;
      }
      
      .close-button {
        position: absolute;
        top: 2rem;
        right: 2rem;
        background: rgba(var(--color-text-rgb, 23, 23, 71), 0.08);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(var(--color-text-rgb, 23, 23, 71), 0.1);
        border-radius: 12px;
        width: 56px;
        height: 56px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        color: var(--color-text);
        transition: all 0.4s cubic-bezier(0.23, 1, 0.32, 1);
        z-index: 10;
        
        &:hover {
          background: rgba(var(--color-text-rgb, 23, 23, 71), 0.15);
          transform: rotate(90deg) scale(1.05);
          box-shadow: 0 8px 25px rgba(var(--color-text-rgb, 23, 23, 71), 0.15);
        }
        
        &:active {
          transform: rotate(90deg) scale(0.95);
        }
        
        @media (max-width: 768px) {
          top: 1.5rem;
          right: 1.5rem;
          width: 48px;
          height: 48px;
        }
      }
    }
    
    .content-card {
      background: var(--color-panel-bg);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border-radius: 24px;
      box-shadow: 
        0 20px 60px -10px rgba(0, 0, 0, 0.1),
        0 8px 25px -5px rgba(var(--color-primary-rgb, 65, 97, 255), 0.06),
        inset 0 1px 0 rgba(255, 255, 255, 0.1);
      padding: 3rem;
      border: 1px solid var(--color-border);
      margin-top: -3rem;
      position: relative;
      z-index: 2;
      overflow: hidden;
      
      // Subtle inner glow
      &:before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 1px;
        background: linear-gradient(90deg, 
          transparent 0%, 
          rgba(var(--color-primary-rgb, 65, 97, 255), 0.3) 50%, 
          transparent 100%);
      }
      
      @media (max-width: 768px) {
        padding: 2.5rem 2rem;
        margin-top: -2rem;
        border-radius: 20px;
      }
      
      @media (max-width: 480px) {
        padding: 2rem 1.5rem;
      }
    }
    
    .disclaimer-section {
      display: flex;
      gap: 2rem;
      margin-bottom: 3.5rem;
      position: relative;
      
      &:last-child {
        margin-bottom: 0;
      }
      
      @media (max-width: 768px) {
        flex-direction: column;
        gap: 1.5rem;
        margin-bottom: 3rem;
      }
      
      // Subtle hover effect
      &:hover {
        .section-icon {
          transform: translateY(-2px) scale(1.05);
          box-shadow: 0 8px 25px rgba(var(--color-primary-rgb, 65, 97, 255), 0.2);
        }
      }
      
      .section-icon {
        flex-shrink: 0;
        width: 64px;
        height: 64px;
        border-radius: 16px;
        background: linear-gradient(135deg, 
          rgba(var(--color-primary-rgb, 65, 97, 255), 0.08) 0%, 
          rgba(var(--color-primary-rgb, 65, 97, 255), 0.12) 100%);
        border: 2px solid rgba(var(--color-primary-rgb, 65, 97, 255), 0.1);
        display: flex;
        align-items: center;
        justify-content: center;
        color: var(--color-primary);
        position: relative;
        transition: all 0.4s cubic-bezier(0.23, 1, 0.32, 1);
        
        // Inner glow effect
        &:before {
          content: '';
          position: absolute;
          inset: 2px;
          border-radius: 14px;
          background: linear-gradient(135deg, 
            rgba(255, 255, 255, 0.1) 0%, 
            transparent 100%);
          pointer-events: none;
        }
        
        @media (max-width: 768px) {
          width: 56px;
          height: 56px;
          border-radius: 14px;
          
          &:before {
            border-radius: 12px;
          }
        }
      }
      
      .section-content {
        flex: 1;
        
        h2 {
          margin: 0 0 1.5rem;
          font-size: 1.75rem;
          font-weight: 700;
          color: var(--color-text);
          position: relative;
          
          // Elegant underline
          &:after {
            content: '';
            position: absolute;
            bottom: -8px;
            left: 0;
            width: 60px;
            height: 3px;
            background: linear-gradient(90deg, 
              var(--color-primary) 0%, 
              rgba(var(--color-primary-rgb, 65, 97, 255), 0.3) 100%);
            border-radius: 2px;
          }
          
          @media (max-width: 768px) {
            font-size: 1.5rem;
          }
        }
        
        p {
          margin: 0 0 1.5rem;
          line-height: 1.7;
          color: var(--color-text-light);
          font-size: 1rem;
          
          &:last-child {
            margin-bottom: 0;
          }
        }
        
        ul {
          margin: 0 0 1.5rem;
          padding-left: 0;
          list-style: none;
          
          li {
            margin-bottom: 0.75rem;
            line-height: 1.7;
            color: var(--color-text-light);
            font-size: 1rem;
            position: relative;
            padding-left: 1.5rem;
            
            // Enhanced bullet points
            &:before {
              content: '';
              position: absolute;
              left: 0;
              top: 0.6em;
              width: 6px;
              height: 6px;
              background: linear-gradient(135deg, 
                var(--color-primary) 0%, 
                rgba(var(--color-primary-rgb, 65, 97, 255), 0.6) 100%);
              border-radius: 50%;
              transform: translateY(-50%);
            }
            
            &:last-child {
              margin-bottom: 0;
            }
          }
        }
      }
    }
    
    .citation-box {
      background: linear-gradient(135deg, 
        rgba(var(--color-primary-rgb, 65, 97, 255), 0.08) 0%, 
        rgba(var(--color-primary-rgb, 65, 97, 255), 0.04) 100%);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      border-radius: 16px;
      padding: 2rem;
      margin: 2rem 0;
      border: 1px solid rgba(var(--color-primary-rgb, 65, 97, 255), 0.15);
      position: relative;
      overflow: hidden;
      box-shadow: 
        0 8px 25px -5px rgba(var(--color-primary-rgb, 65, 97, 255), 0.1),
        inset 0 1px 0 rgba(255, 255, 255, 0.1);
      
      // Enhanced border accent
      &:before {
        content: '';
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 4px;
        background: linear-gradient(180deg, 
          var(--color-primary) 0%, 
          rgba(var(--color-primary-rgb, 65, 97, 255), 0.6) 100%);
        border-radius: 0 2px 2px 0;
      }
      
      // Subtle glow effect
      &:after {
        content: '';
        position: absolute;
        top: -50%;
        right: -50%;
        width: 100%;
        height: 200%;
        background: radial-gradient(circle, 
          rgba(var(--color-primary-rgb, 65, 97, 255), 0.03) 0%, 
          transparent 70%);
        pointer-events: none;
      }
      
      p {
        margin: 0 !important;
        font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
        font-size: 0.95rem;
        line-height: 1.6;
        color: var(--color-text);
        position: relative;
        z-index: 1;
        background: linear-gradient(135deg, 
          var(--color-text) 0%, 
          rgba(var(--color-primary-rgb, 65, 97, 255), 0.8) 100%);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
      }
      
      .citation-note {
        font-style: italic;
        color: var(--color-text-light) !important;
        opacity: 0.8;
        font-size: 0.875rem;
        margin-top: 1rem !important;
        background: none !important;
        -webkit-background-clip: unset !important;
        background-clip: unset !important;
      }
      
      .btn-copy {
        position: absolute;
        top: 1rem;
        right: 1rem;
        background: rgba(var(--color-primary-rgb, 65, 97, 255), 0.12);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(var(--color-primary-rgb, 65, 97, 255), 0.2);
        border-radius: 10px;
        color: var(--color-primary);
        font-size: 0.8rem;
        font-weight: 600;
        padding: 0.5rem 0.875rem;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
        z-index: 2;
        
        &:hover {
          background: rgba(var(--color-primary-rgb, 65, 97, 255), 0.18);
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(var(--color-primary-rgb, 65, 97, 255), 0.2);
        }
        
        &:active {
          transform: translateY(-1px) scale(0.98);
        }
      }
    }
    
    .contact-info {
      background: linear-gradient(135deg, 
        rgba(var(--color-primary-rgb, 65, 97, 255), 0.05) 0%, 
        rgba(var(--color-accent-rgb, 122, 69, 255), 0.03) 100%);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      border-radius: 16px;
      padding: 2rem;
      margin: 2rem 0;
      border: 1px solid rgba(var(--color-primary-rgb, 65, 97, 255), 0.1);
      position: relative;
      overflow: hidden;
      box-shadow: 
        0 8px 25px -5px rgba(var(--color-primary-rgb, 65, 97, 255), 0.08),
        inset 0 1px 0 rgba(255, 255, 255, 0.08);
      
      // Subtle background pattern
      &:before {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle, 
          rgba(var(--color-primary-rgb, 65, 97, 255), 0.02) 0%, 
          transparent 50%);
        pointer-events: none;
      }
      
      p {
        display: flex;
        align-items: center;
        gap: 0.875rem;
        margin-bottom: 1rem !important;
        position: relative;
        z-index: 1;
        padding: 0.5rem 0;
        
        &:last-child {
          margin-bottom: 0 !important;
        }
        
        // Icon styling
        .feather {
          flex-shrink: 0;
          color: var(--color-primary);
          opacity: 0.8;
          transition: all 0.3s ease;
        }
        
        &:hover .feather {
          opacity: 1;
          transform: scale(1.1);
        }
        
        a {
          color: var(--color-primary);
          text-decoration: none;
          font-weight: 600;
          transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
          position: relative;
          
          // Enhanced hover underline
          &:before {
            content: '';
            position: absolute;
            bottom: -2px;
            left: 0;
            width: 0;
            height: 2px;
            background: linear-gradient(90deg, 
              var(--color-primary) 0%, 
              rgba(var(--color-primary-rgb, 65, 97, 255), 0.6) 100%);
            border-radius: 1px;
            transition: width 0.3s cubic-bezier(0.23, 1, 0.32, 1);
          }
          
          &:hover {
            color: rgba(var(--color-primary-rgb, 65, 97, 255), 0.8);
            transform: translateY(-1px);
            
            &:before {
              width: 100%;
            }
          }
        }
        
        .indent {
          margin-left: 2rem;
          color: var(--color-text-light);
          opacity: 0.75;
          font-size: 0.95rem;
          font-style: italic;
        }
      }
    }
    
    .disclaimer-footer {
      margin-top: 4rem;
      padding-top: 2.5rem;
      border-top: 1px solid rgba(var(--color-primary-rgb, 65, 97, 255), 0.1);
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: relative;
      
      // Subtle top border accent
      &:before {
        content: '';
        position: absolute;
        top: 0;
        left: 50%;
        transform: translateX(-50%);
        width: 120px;
        height: 1px;
        background: linear-gradient(90deg, 
          transparent 0%, 
          var(--color-primary) 50%, 
          transparent 100%);
      }
      
      @media (max-width: 767px) {
        flex-direction: column;
        gap: 1.5rem;
        align-items: flex-start;
        text-align: center;
      }
      
      p {
        margin: 0;
        font-size: 0.875rem;
        color: var(--color-text-light);
        opacity: 0.7;
        font-weight: 500;
        
        @media (max-width: 767px) {
          width: 100%;
        }
      }
      
      .action-links {
        display: flex;
        gap: 1rem;
        
        @media (max-width: 767px) {
          width: 100%;
          flex-direction: column;
          gap: 0.75rem;
        }
      }
      
      .btn-primary, .btn-secondary {
        display: inline-flex;
        align-items: center;
        gap: 0.6rem;
        padding: 0.75rem 1.5rem;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.875rem;
        transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
        text-decoration: none;
        cursor: pointer;
        position: relative;
        overflow: hidden;
        
        // Icon styling
        .feather {
          transition: transform 0.3s cubic-bezier(0.23, 1, 0.32, 1);
        }
        
        @media (max-width: 767px) {
          justify-content: center;
          padding: 0.875rem 1.5rem;
        }
      }
      
      .btn-primary {
        background: linear-gradient(135deg, 
          var(--color-primary) 0%, 
          rgba(var(--color-primary-rgb, 65, 97, 255), 0.9) 100%);
        color: white;
        box-shadow: 
          0 8px 25px -5px rgba(var(--color-primary-rgb, 65, 97, 255), 0.3),
          inset 0 1px 0 rgba(255, 255, 255, 0.2);
        border: none;
        
        // Subtle shine effect
        &:before {
          content: '';
          position: absolute;
          top: 0;
          left: -100%;
          width: 100%;
          height: 100%;
          background: linear-gradient(90deg, 
            transparent 0%, 
            rgba(255, 255, 255, 0.2) 50%, 
            transparent 100%);
          transition: left 0.6s ease;
        }
        
        &:hover {
          transform: translateY(-3px);
          box-shadow: 
            0 12px 35px -5px rgba(var(--color-primary-rgb, 65, 97, 255), 0.4),
            inset 0 1px 0 rgba(255, 255, 255, 0.3);
          
          &:before {
            left: 100%;
          }
          
          .feather {
            transform: translateX(2px);
          }
        }
        
        &:active {
          transform: translateY(-1px) scale(0.98);
        }
      }
      
      .btn-secondary {
        background: rgba(var(--color-primary-rgb, 65, 97, 255), 0.08);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        color: var(--color-primary);
        border: 1px solid rgba(var(--color-primary-rgb, 65, 97, 255), 0.15);
        
        &:hover {
          background: rgba(var(--color-primary-rgb, 65, 97, 255), 0.15);
          transform: translateY(-2px);
          box-shadow: 0 8px 25px rgba(var(--color-primary-rgb, 65, 97, 255), 0.15);
          
          .feather {
            transform: translateX(-2px);
          }
        }
        
        &:active {
          transform: translateY(-1px) scale(0.98);
        }
      }
    }
  }
  
  // Animation keyframes
  @keyframes float-gentle {
    0%, 100% {
      transform: translateY(0px) rotate(0deg);
    }
    25% {
      transform: translateY(-10px) rotate(1deg);
    }
    50% {
      transform: translateY(-20px) rotate(0deg);
    }
    75% {
      transform: translateY(-10px) rotate(-1deg);
    }
  }
  </style>