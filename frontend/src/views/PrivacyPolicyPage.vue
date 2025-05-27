<template>
  <div class="privacy-policy-page">
    <div class="page-header">
      <div class="header-bg"></div>
      <div class="container">
        <h1>Privacy Policy</h1>
        <p class="subtitle">How we handle your data and protect your privacy</p>
      </div>
      
      <button class="close-button" @click="$emit('close')" aria-label="Close privacy policy">
        <vue-feather type="x" size="24"></vue-feather>
      </button>
    </div>
    
    <div class="container">
      <div class="content-card">
        <!-- Last Updated -->
        <div class="privacy-section">
          <div class="section-icon">
            <vue-feather type="calendar" size="24"></vue-feather>
          </div>
          <div class="section-content">
            <h2>Last Updated</h2>
            <p>{{ lastUpdated }}</p>
          </div>
        </div>

        <!-- Introduction -->
        <div class="privacy-section">
          <div class="section-icon">
            <vue-feather type="shield" size="24"></vue-feather>
          </div>
          <div class="section-content">
            <h2>Our Commitment to Privacy</h2>
            <p>
              At MARCUS (Molecular Annotation and Recognition for Curating Unravelled Structures), 
              we are committed to protecting your privacy and ensuring the security of your data. 
              This Privacy Policy explains how we collect, use, and safeguard information when you 
              use our chemical structure extraction and annotation platform.
            </p>
          </div>
        </div>

        <!-- Information We Collect -->
        <div class="privacy-section">
          <div class="section-icon">
            <vue-feather type="database" size="24"></vue-feather>
          </div>
          <div class="section-content">
            <h2>Information We Collect</h2>
            <h3>Document Processing Data</h3>
            <ul>
              <li>PDF documents you upload for chemical structure extraction</li>
              <li>Extracted text and chemical structures from your documents</li>
              <li>Annotations and metadata generated during processing</li>
              <li>Processing preferences and settings</li>
            </ul>
            
            <h3>Technical Data</h3>
            <ul>
              <li>Browser type and version information</li>
              <li>Device and operating system information</li>
              <li>IP address and general location data</li>
              <li>Usage patterns and application performance metrics</li>
            </ul>

            <h3>Optional Account Data</h3>
            <ul>
              <li>Information provided when creating COCONUT database accounts</li>
              <li>Research collaboration and publication data (if submitted)</li>
              <li>User preferences and configuration settings</li>
            </ul>
          </div>
        </div>

        <!-- How We Use Information -->
        <div class="privacy-section">
          <div class="section-icon">
            <vue-feather type="cpu" size="24"></vue-feather>
          </div>
          <div class="section-content">
            <h2>How We Use Your Information</h2>
            <p>We use the collected information for the following purposes:</p>
            <ul>
              <li><strong>Document Processing:</strong> To extract, recognize, and annotate chemical structures from your uploaded documents</li>
              <li><strong>Service Improvement:</strong> To enhance our AI models and improve extraction accuracy</li>
              <li><strong>Technical Support:</strong> To troubleshoot issues and provide user assistance</li>
              <li><strong>Research Advancement:</strong> To contribute to open science and chemical informatics research (with appropriate anonymization)</li>
              <li><strong>Database Integration:</strong> To facilitate submissions to external databases like COCONUT when explicitly requested</li>
            </ul>
          </div>
        </div>

        <!-- Data Storage and Security -->
        <div class="privacy-section">
          <div class="section-icon">
            <vue-feather type="lock" size="24"></vue-feather>
          </div>
          <div class="section-content">
            <h2>Data Storage and Security</h2>
            <h3>Security Measures</h3>
            <ul>
              <li>All data transmissions are encrypted using industry-standard TLS protocols</li>
              <li>Documents are processed in secure, isolated environments</li>
              <li>Access to user data is restricted to authorized personnel only</li>
              <li>Regular security audits and updates are performed</li>
            </ul>

            <h3>Data Retention</h3>
            <ul>
              <li>Uploaded documents are temporarily stored during processing and deleted after completion</li>
              <li>Extracted structures and metadata may be retained for research purposes (anonymized)</li>
              <li>Technical logs are retained for a limited period for troubleshooting purposes</li>
              <li>Users can request deletion of their data at any time</li>
            </ul>
          </div>
        </div>

        <!-- Data Sharing -->
        <div class="privacy-section">
          <div class="section-icon">
            <vue-feather type="share-2" size="24"></vue-feather>
          </div>
          <div class="section-content">
            <h2>Data Sharing and Third Parties</h2>
            <p>We are committed to not selling or renting your personal information. We may share data only in the following circumstances:</p>
            <ul>
              <li><strong>COCONUT Database:</strong> When you explicitly choose to submit structures to the COCONUT database</li>
              <li><strong>Research Collaboration:</strong> Anonymized data for legitimate research purposes with academic institutions</li>
              <li><strong>Legal Requirements:</strong> When required by law or to protect our rights and safety</li>
              <li><strong>Service Providers:</strong> With trusted third-party services that help us operate the platform (under strict confidentiality agreements)</li>
            </ul>
          </div>
        </div>

        <!-- Your Rights -->
        <div class="privacy-section">
          <div class="section-icon">
            <vue-feather type="user-check" size="24"></vue-feather>
          </div>
          <div class="section-content">
            <h2>Your Privacy Rights</h2>
            <p>You have the following rights regarding your data:</p>
            <ul>
              <li><strong>Access:</strong> Request information about what data we have collected about you</li>
              <li><strong>Correction:</strong> Request correction of inaccurate or incomplete data</li>
              <li><strong>Deletion:</strong> Request deletion of your personal data</li>
              <li><strong>Portability:</strong> Request a copy of your data in a machine-readable format</li>
              <li><strong>Objection:</strong> Object to certain uses of your data</li>
              <li><strong>Consent Withdrawal:</strong> Withdraw consent for data processing where applicable</li>
            </ul>
          </div>
        </div>

        <!-- Cookies and Tracking -->
        <div class="privacy-section">
          <div class="section-icon">
            <vue-feather type="eye" size="24"></vue-feather>
          </div>
          <div class="section-content">
            <h2>Cookies and Tracking</h2>
            <p>
              MARCUS uses minimal tracking technologies to enhance your experience:
            </p>
            <ul>
              <li><strong>Essential Cookies:</strong> Required for basic functionality (session management, preferences)</li>
              <li><strong>Functional Cookies:</strong> Remember your settings and preferences</li>
              <li><strong>No Advertising Cookies:</strong> We do not use cookies for advertising or marketing purposes</li>
              <li><strong>Local Storage:</strong> Browser storage for temporary data and user preferences</li>
            </ul>
            <p>
              You can control cookie settings through your browser preferences. Note that disabling 
              essential cookies may affect the functionality of the platform.
            </p>
          </div>
        </div>

        <!-- International Data Transfers -->
        <div class="privacy-section">
          <div class="section-icon">
            <vue-feather type="globe" size="24"></vue-feather>
          </div>
          <div class="section-content">
            <h2>International Data Transfers</h2>
            <p>
              MARCUS is developed and operated by the Steinbeck Lab. Data processing may occur 
              across different jurisdictions. We ensure that appropriate safeguards are in place 
              for any international data transfers, including:
            </p>
            <ul>
              <li>Adherence to GDPR principles for EU users</li>
              <li>Appropriate data transfer agreements</li>
              <li>Regular assessment of data protection laws in relevant jurisdictions</li>
            </ul>
          </div>
        </div>

        <!-- Children's Privacy -->
        <div class="privacy-section">
          <div class="section-icon">
            <vue-feather type="heart" size="24"></vue-feather>
          </div>
          <div class="section-content">
            <h2>Children's Privacy</h2>
            <p>
              MARCUS is designed for use by researchers, academics, and professionals. We do not 
              knowingly collect personal information from children under 13 years of age. If we 
              become aware that we have collected such information, we will take steps to delete it promptly.
            </p>
          </div>
        </div>

        <!-- Changes to This Policy -->
        <div class="privacy-section">
          <div class="section-icon">
            <vue-feather type="edit-3" size="24"></vue-feather>
          </div>
          <div class="section-content">
            <h2>Changes to This Privacy Policy</h2>
            <p>
              We may update this Privacy Policy from time to time to reflect changes in our 
              practices, technology, legal requirements, or other factors. When we do, we will:
            </p>
            <ul>
              <li>Update the "Last Updated" date at the top of this policy</li>
              <li>Notify users of significant changes through the application interface</li>
              <li>Provide a clear summary of any material changes</li>
              <li>Obtain consent where required by applicable law</li>
            </ul>
          </div>
        </div>

        <!-- Contact Information -->
        <div class="privacy-section">
          <div class="section-icon">
            <vue-feather type="mail" size="24"></vue-feather>
          </div>
          <div class="section-content">
            <h2>Contact Us</h2>
            <p>
              If you have questions about this Privacy Policy or how we handle your data, 
              please contact us:
            </p>
            <div class="contact-info">
              <p>
                <vue-feather type="user" size="16"></vue-feather>
                <strong>Data Protection Officer:</strong> Prof. Dr. Christoph Steinbeck
              </p>
              <p>
                <vue-feather type="home" size="16"></vue-feather>
                <strong>Institution:</strong> Friedrich Schiller University Jena
              </p>
              <p>
                <vue-feather type="mail" size="16"></vue-feather>
                <strong>Email:</strong> 
                <a href="mailto:chrsitoph.steinbeck@uni-jena.de">chrsitoph.steinbeck@uni-jena.de</a>
              </p>
              <p>
                <vue-feather type="github" size="16"></vue-feather>
                <strong>GitHub:</strong> 
                <a href="https://github.com/Kohulan/MARCUS" target="_blank">https://github.com/Kohulan/MARCUS</a>
              </p>
            </div>
          </div>
        </div>

        <!-- Footer Actions -->
        <div class="privacy-footer">
          <p>Effective Date: {{ lastUpdated }}</p>
          <div class="action-links">
            <button class="btn-secondary" @click="$emit('close')">
              <vue-feather type="arrow-left" size="16"></vue-feather>
              Back to Application
            </button>
            <button class="btn-copy" @click="copyPolicyLink">
              <vue-feather type="link" size="16"></vue-feather>
              Copy Link
            </button>
            <a href="https://github.com/Kohulan/MARCUS" target="_blank" class="btn-primary">
              <vue-feather type="github" size="16"></vue-feather>
              View Source
            </a>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'PrivacyPolicyPage',
  
  data() {
    return {
      lastUpdated: new Date().toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric' 
      })
    }
  },
  
  methods: {
    copyPolicyLink() {
      // In a real application, this would copy the full URL to the privacy policy
      const url = `${window.location.origin}/#/privacy-policy`;
      navigator.clipboard.writeText(url)
        .then(() => {
          // Show notification using the store
          this.$store.dispatch('showNotification', {
            type: 'success',
            message: 'Privacy policy link copied to clipboard'
          });
        })
        .catch(err => {
          console.error('Failed to copy: ', err);
          this.$store.dispatch('showNotification', {
            type: 'error',
            message: 'Failed to copy link'
          });
        });
    }
  }
}
</script>

<style lang="scss" scoped>
.privacy-policy-page {
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
      
      // Subtle glow effect
      &:after {
        content: attr(data-text);
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(135deg, 
          transparent 0%, 
          rgba(var(--color-primary-rgb, 65, 97, 255), 0.1) 50%,
          transparent 100%);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        filter: blur(20px);
        z-index: -1;
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
  
  .privacy-section {
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
      
      h3 {
        margin: 2rem 0 1rem;
        font-size: 1.25rem;
        font-weight: 600;
        color: var(--color-text);
        position: relative;
        padding-left: 1rem;
        
        &:first-child {
          margin-top: 0;
        }
        
        // Stylish bullet point
        &:before {
          content: '';
          position: absolute;
          left: 0;
          top: 50%;
          transform: translateY(-50%);
          width: 4px;
          height: 4px;
          background: var(--color-primary);
          border-radius: 50%;
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
          
          strong {
            color: var(--color-text);
            font-weight: 600;
          }
        }
      }
      
      a {
        color: var(--color-primary);
        text-decoration: none;
        font-weight: 500;
        transition: all 0.3s ease;
        position: relative;
        
        &:hover {
          color: rgba(var(--color-primary-rgb, 65, 97, 255), 0.8);
          
          &:after {
            width: 100%;
          }
        }
        
        // Elegant underline animation
        &:after {
          content: '';
          position: absolute;
          bottom: -2px;
          left: 0;
          width: 0;
          height: 1px;
          background: var(--color-primary);
          transition: width 0.3s ease;
        }
      }
    }
    
    .contact-info {
      background: linear-gradient(135deg, 
        rgba(var(--color-primary-rgb, 65, 97, 255), 0.04) 0%, 
        rgba(var(--color-primary-rgb, 65, 97, 255), 0.08) 100%);
      border-radius: 16px;
      padding: 2rem;
      margin: 2rem 0;
      border: 1px solid rgba(var(--color-primary-rgb, 65, 97, 255), 0.1);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      
      p {
        display: flex;
        align-items: center;
        gap: 1rem;
        margin-bottom: 1rem !important;
        font-size: 1rem;
        
        &:last-child {
          margin-bottom: 0 !important;
        }
        
        a {
          color: var(--color-primary);
          text-decoration: none;
          font-weight: 500;
          
          &:hover {
            color: rgba(var(--color-primary-rgb, 65, 97, 255), 0.8);
          }
        }
        
        strong {
          color: var(--color-text);
          font-weight: 600;
        }
      }
    }
  }
  
  .privacy-footer {
    margin-top: 4rem;
    padding: 2rem 0;
    border-top: 1px solid var(--color-border);
    background: linear-gradient(135deg, 
      rgba(var(--color-primary-rgb, 65, 97, 255), 0.02) 0%, 
      transparent 100%);
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    
    @media (max-width: 768px) {
      flex-direction: column;
      gap: 1.5rem;
      align-items: flex-start;
      padding: 1.5rem;
    }
    
    p {
      margin: 0;
      font-size: 0.9rem;
      color: var(--color-text-light);
      opacity: 0.8;
      font-weight: 500;
    }
    
    .action-links {
      display: flex;
      gap: 1rem;
      
      @media (max-width: 768px) {
        width: 100%;
        flex-direction: column;
      }
      
      @media (max-width: 480px) {
        gap: 0.75rem;
      }
      
      .btn-primary, .btn-secondary, .btn-copy {
        display: inline-flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.8rem 1.5rem;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.9rem;
        transition: all 0.4s cubic-bezier(0.23, 1, 0.32, 1);
        text-decoration: none;
        cursor: pointer;
        position: relative;
        overflow: hidden;
        
        // Subtle hover glow
        &:before {
          content: '';
          position: absolute;
          top: 50%;
          left: 50%;
          width: 0;
          height: 0;
          background: radial-gradient(circle, rgba(255, 255, 255, 0.2) 0%, transparent 70%);
          transition: all 0.4s ease;
          transform: translate(-50%, -50%);
          border-radius: 50%;
          pointer-events: none;
        }
        
        &:hover:before {
          width: 200px;
          height: 200px;
        }
        
        @media (max-width: 768px) {
          justify-content: center;
        }
      }
      
      .btn-primary {
        background: linear-gradient(135deg, 
          var(--color-primary) 0%, 
          rgba(var(--color-primary-rgb, 65, 97, 255), 0.9) 100%);
        color: white;
        box-shadow: 
          0 4px 15px rgba(var(--color-primary-rgb, 65, 97, 255), 0.3),
          0 2px 8px rgba(var(--color-primary-rgb, 65, 97, 255), 0.2);
        border: none;
        
        &:hover {
          transform: translateY(-3px);
          box-shadow: 
            0 8px 25px rgba(var(--color-primary-rgb, 65, 97, 255), 0.4),
            0 4px 15px rgba(var(--color-primary-rgb, 65, 97, 255), 0.3);
        }
        
        &:active {
          transform: translateY(-1px);
        }
      }
      
      .btn-secondary {
        background: rgba(var(--color-text-rgb, 23, 23, 71), 0.06);
        color: var(--color-text);
        border: 1px solid rgba(var(--color-text-rgb, 23, 23, 71), 0.1);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        
        &:hover {
          background: rgba(var(--color-text-rgb, 23, 23, 71), 0.12);
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(var(--color-text-rgb, 23, 23, 71), 0.1);
        }
        
        &:active {
          transform: translateY(0);
        }
      }
      
      .btn-copy {
        background: rgba(var(--color-primary-rgb, 65, 97, 255), 0.08);
        color: var(--color-primary);
        border: 1px solid rgba(var(--color-primary-rgb, 65, 97, 255), 0.2);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        
        &:hover {
          background: rgba(var(--color-primary-rgb, 65, 97, 255), 0.15);
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(var(--color-primary-rgb, 65, 97, 255), 0.2);
        }
        
        &:active {
          transform: translateY(0);
        }
      }
    }
  }
  
  // Smooth animations
  @keyframes float-gentle {
    0%, 100% {
      transform: translate(0, 0) rotate(0deg);
    }
    33% {
      transform: translate(30px, -30px) rotate(120deg);
    }
    66% {
      transform: translate(-20px, 20px) rotate(240deg);
    }
  }
  
  // Enhanced scrollbar for better UX
  &::-webkit-scrollbar {
    width: 8px;
  }
  
  &::-webkit-scrollbar-track {
    background: rgba(var(--color-border-rgb, 0, 0, 0), 0.1);
    border-radius: 4px;
  }
  
  &::-webkit-scrollbar-thumb {
    background: rgba(var(--color-primary-rgb, 65, 97, 255), 0.3);
    border-radius: 4px;
    
    &:hover {
      background: rgba(var(--color-primary-rgb, 65, 97, 255), 0.5);
    }
  }
}
</style>
