<template>
  <footer class="app-footer">
    <div class="footer-wave">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 80" preserveAspectRatio="none">
        <path d="M0,32L60,37.3C120,43,240,53,360,48C480,43,600,27,720,24C840,21,960,32,1080,36.7L1200,32L1320,37.3L1440,32L1440,80L1320,80C1200,80,1080,80,960,80C840,80,720,80,600,80C480,80,360,80,240,80C120,80,0,80,0,80Z" fill="var(--color-panel-bg)"></path>
      </svg>
    </div>
    
    <div class="container">
      <div class="footer-content">
        <div class="footer-logo">
          <div class="logo-container">
            <h3>MARCUS</h3>
            <div class="logo-badge">NP</div>
          </div>
          <p class="tagline">Molecular Annotation and Recognition for Curating Unravelled Structures</p>
          
          <div class="social-links">
            <a href="https://github.com/Kohulan/MARCUS" target="_blank" aria-label="GitHub">
              <vue-feather type="github" class="icon"></vue-feather>
            </a>
            <a href="mailto:kohulan.rajan@uni-jena.de" aria-label="Email">
              <vue-feather type="mail" class="icon"></vue-feather>
            </a>
            <a href="https://cheminf.uni-jena.de/" target="_blank" aria-label="Website">
              <vue-feather type="globe" class="icon"></vue-feather>
            </a>
          </div>
        </div>
        
        <div class="footer-links">
          <h4>Resources</h4>
          <ul>
            <li>
              <vue-feather type="code" class="list-icon"></vue-feather>
              <a href="https://decimer.ai" target="_blank">DECIMER</a>
            </li>
            <li>
              <vue-feather type="database" class="list-icon"></vue-feather>
              <a href="https://coconut.naturalproducts.net/" target="_blank">COCONUT</a>
            </li>
            <li>
              <vue-feather type="server" class="list-icon"></vue-feather>
              <a href="https://naturalprducts.net/" target="_blank">Natural Products Services</a>
            </li>
            <li>
              <vue-feather type="github" class="list-icon"></vue-feather>
              <a href="https://github.com/Kohulan/MARCUS" target="_blank">Source Code</a>
              <span class="badge">Coming Soon</span>
            </li>
          </ul>
        </div>
      </div>
      
      <div class="footer-bottom">
        <div class="copyright">
          <p>&copy; {{ currentYear }} MARCUS </p>
        </div>
        <div class="credits">
          <p>Crafted with <vue-feather type="coffee" class="coffee-icon"></vue-feather> by <a href="https://kohulanr.com" target="_blank">Kohulan Rajan</a> @ <a href="https://github.com/Steinbeck-Lab" target="_blank">Steinbeck Lab</a></p>
        </div>
        <div class="license">
          <p><vue-feather type="award" class="license-icon"></vue-feather> <a href="https://opensource.org/license/MIT" target="_blank">MIT License</a></p>
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
.app-footer {
  position: relative;
  background-color: var(--color-panel-bg);
  padding: 2rem 1rem 0.75rem;
  margin-top: 3.5rem;
  
  .footer-wave {
    position: absolute;
    top: -60px;
    left: 0;
    width: 100%;
    height: 60px;
    overflow: hidden;
    filter: drop-shadow(0 -2px 2px rgba(0,0,0,0.04));
    
    svg {
      width: 100%;
      height: 100%;
      transform: translateY(3px);
      transition: transform 0.5s ease-out;
    }
    
    &:hover svg {
      transform: translateY(0);
    }
  }
  
  .container {
    max-width: 1100px;
    margin: 0 auto;
  }
  
  .footer-content {
    display: grid;
    grid-template-columns: 1fr;
    gap: 1.5rem;
    margin-bottom: 1.5rem;
    
    @media (min-width: 768px) {
      grid-template-columns: 2fr 1fr;
      gap: 2rem;
    }
  }
  
  .footer-logo {
    .logo-container {
      display: flex;
      align-items: center;
      margin-bottom: 0.5rem;
      
      h3 {
        font-size: 1.5rem;
        font-weight: 800;
        letter-spacing: 1px;
        margin: 0;
        background: var(--gradient-primary);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        transform: translateZ(0);
        text-shadow: 0 1px 3px rgba(0,0,0,0.06);
      }
      
      .logo-badge {
        background: var(--gradient-primary);
        color: white;
        font-size: 0.6rem;
        font-weight: bold;
        padding: 0.1rem 0.3rem;
        border-radius: 4px;
        margin-left: 0.4rem;
        box-shadow: 0 2px 5px rgba(var(--color-primary-rgb), 0.2);
      }
    }
    
    .tagline {
      font-size: 0.8rem;
      font-weight: 500;
      margin-bottom: 0.7rem;
      color: var(--color-text);
      opacity: 0.85;
      max-width: 90%;
    }
    
    .social-links {
      display: flex;
      gap: 0.6rem;
      margin-top: 0.75rem;
      
      a {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 30px;
        height: 30px;
        border-radius: 6px;
        background-color: rgba(var(--color-primary-rgb), 0.08);
        transition: all 0.3s cubic-bezier(0.17, 0.67, 0.83, 0.67);
        
        &:hover {
          background-color: var(--color-primary);
          transform: translateY(-2px) scale(1.05);
          box-shadow: 0 3px 6px rgba(var(--color-primary-rgb), 0.25);
          
          .icon {
            color: white;
            transform: rotate(360deg);
          }
        }
        
        .icon {
          color: var(--color-primary);
          width: 14px;
          height: 14px;
          transition: all 0.5s ease;
        }
      }
    }
  }
  
  .footer-links {
    h4 {
      font-size: 0.95rem;
      margin-bottom: 0.9rem;
      position: relative;
      display: inline-block;
      
      &:after {
        content: '';
        position: absolute;
        bottom: -4px;
        left: 0;
        width: 30px;
        height: 2px;
        background: var(--gradient-primary);
        border-radius: 2px;
        transition: width 0.3s ease;
      }
      
      &:hover:after {
        width: 100%;
      }
    }
    
    ul {
      list-style: none;
      padding: 0;
      
      li {
        margin-bottom: 0.5rem;
        display: flex;
        align-items: center;
        
        .list-icon {
          width: 13px;
          height: 13px;
          color: var(--color-primary);
          margin-right: 0.5rem;
          opacity: 0.8;
          transition: all 0.2s ease;
        }
        
        a {
          color: var(--color-text-light);
          font-weight: 500;
          font-size: 0.8rem;
          transition: all 0.2s ease;
          display: inline-flex;
          align-items: center;
          
          &:hover {
            color: var(--color-primary);
            transform: translateX(2px);
            
            & + .list-icon, & ~ .list-icon {
              opacity: 1;
              transform: translateX(2px);
            }
          }
        }
        
        .badge {
          font-size: 0.6rem;
          background-color: var(--color-primary);
          color: white;
          padding: 0.05rem 0.3rem;
          border-radius: 3px;
          margin-left: 0.4rem;
          box-shadow: 0 1px 3px rgba(var(--color-primary-rgb), 0.2);
          transform: translateY(-1px);
        }
      }
    }
  }
  
  .footer-bottom {
    border-top: 1px solid var(--color-border);
    padding-top: 1rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 0.25rem;
    
    @media (min-width: 768px) {
      flex-direction: row;
      justify-content: space-between;
      text-align: left;
      flex-wrap: wrap;
      gap: 0;
    }
    
    p {
      font-size: 0.7rem;
      color: var(--color-text-light);
      opacity: 0.85;
      margin: 0;
      display: flex;
      align-items: center;
      
      a {
        color: var(--color-primary);
        text-decoration: none;
        transition: all 0.2s ease;
        
        &:hover {
          text-decoration: underline;
          opacity: 0.85;
          text-shadow: 0 0 5px rgba(var(--color-primary-rgb), 0.15);
        }
      }
      
      .license-icon {
        width: 12px;
        height: 12px;
        color: var(--color-primary);
        margin-right: 0.3rem;
      }
      
      .coffee-icon {
        width: 12px;
        height: 12px;
        color: #6f4e37;
        margin: 0 0.2rem;
        animation: steam 3s infinite ease-in-out;
        filter: drop-shadow(0 1px 1px rgba(0,0,0,0.1));
      }
      
      @keyframes steam {
        0%, 100% { transform: translateY(0) rotate(0); }
        50% { transform: translateY(-2px) rotate(5deg); }
      }
    }
  }
}

/* Add these CSS variables to your app's global styles if not already present */
:root {
  --gradient-primary: linear-gradient(135deg, #4a6cf7 0%, #2254e2 100%);
  --color-primary: #3461ff;
  --color-primary-rgb: 52, 97, 255;
  --color-panel-bg: #f7f9fc;
  --color-panel-bg-rgb: 247, 249, 252;
  --color-border: #e4e9f2;
  --color-text: #3b4863;
  --color-text-light: #8392ab;
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