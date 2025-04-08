<template>
    <div class="cosmic-loading-screen" :class="{ 'dark-mode': isDarkMode, 'light-mode': !isDarkMode, 'loaded': isLoaded }" ref="loadingScreen">
      <!-- Particle canvas background with interactive connections -->
      <canvas ref="particleCanvas" class="particle-canvas"></canvas>
      
      <!-- Dynamic 3D background with multiple layers -->
      <div class="animated-background">
        <div class="gradient-sphere sphere-1"></div>
        <div class="gradient-sphere sphere-2"></div>
        <div class="gradient-sphere sphere-3"></div>
        <div class="star-field">
          <div v-for="n in 30" :key="`star-${n}`" class="star" :style="getStarStyle(n)"></div>
        </div>
      </div>
      
      <!-- Animated grid background -->
      <div class="grid-container">
        <div class="grid"></div>
      </div>
      
      <!-- 3D perspective container -->
      <div class="perspective-container">
        <!-- 3D transform wrapper with physics-based animations -->
        <div class="transform-wrapper" :class="{ 'animate-complete': isLoaded }">
          <!-- DNA helix animation -->
          <div class="dna-container">
            <div class="dna-strand">
              <div v-for="n in 10" :key="`strand-${n}`" class="dna-step">
                <div class="dna-base left-base"></div>
                <div class="dna-base right-base"></div>
                <div class="dna-connector"></div>
              </div>
            </div>
          </div>
          
          <!-- Logo and visual elements -->
          <div class="logo-showcase">
            <!-- Orbital rings with animated particles -->
            <div class="orbital-ring ring-1">
              <div v-for="n in 6" :key="`orb1-${n}`" class="orbital-particle" :style="getOrbitalStyle(n, 1)"></div>
            </div>
            <div class="orbital-ring ring-2">
              <div v-for="n in 8" :key="`orb2-${n}`" class="orbital-particle" :style="getOrbitalStyle(n, 2)"></div>
            </div>
            <div class="orbital-ring ring-3">
              <div v-for="n in 10" :key="`orb3-${n}`" class="orbital-particle" :style="getOrbitalStyle(n, 3)"></div>
            </div>
            
            <!-- Energy field effect -->
            <div class="energy-field"></div>
            
            <!-- Pulsating core -->
            <div class="logo-core-wrapper">
              <div class="logo-pulse-rings">
                <div class="pulse-ring"></div>
                <div class="pulse-ring"></div>
              </div>
              
              <!-- Logo container with 3D holographic effect -->
              <div class="logo-container" :style="getLogoRotation()">
                <div class="logo-hologram-effect"></div>
                <div class="logo-reflection"></div>
                <div class="logo-glow"></div>
                <div class="logo-shadow"></div>
                <img src="@/assets/logo.png" alt="MARCUS" class="logo" />
                
                <!-- Advanced light effects -->
                <div class="lens-flare"></div>
                <div class="sparkles">
                  <div v-for="n in 3" :key="`sparkle-${n}`" class="sparkle" :style="getSparkleStyle(n)"></div>
                </div>
              </div>
            </div>
            
            <!-- Floating molecular elements with connections -->
            <div class="floating-elements">
              <div v-for="n in 8" :key="`molecule-${n}`" class="floating-molecule" :style="getMoleculeStyle(n)">
                <div class="molecule-node"></div>
              </div>
              <svg class="molecule-connections" viewBox="0 0 300 300" width="300" height="300">
                <line v-for="(connection, idx) in moleculeConnections" 
                      :key="`connection-${idx}`" 
                      :x1="connection.x1" 
                      :y1="connection.y1" 
                      :x2="connection.x2" 
                      :y2="connection.y2" 
                      class="connection-line" />
              </svg>
            </div>
          </div>
          
          <!-- Text elements with advanced animations -->
          <div class="text-elements" :class="{ 'text-visible': titleVisible }">
            <div class="title-container">
              <h1 class="title">MARCUS</h1>
              <div class="badge-wrapper">
                <span class="badge">Beta</span>
                <span class="badge-shine"></span>
              </div>
            </div>
            
            <div class="tagline-wrapper">
              <div class="tagline-glow"></div>
              <p class="tagline">Molecular Annotation and Recognition for Curating Unravelled Structures</p>
            </div>
          </div>
        </div>
        
        <!-- Loading elements with advanced effects -->
        <div class="loading-elements" v-if="!isLoaded">
          <!-- Progress tracking with animated counter -->
          <div class="loading-track">
            <div class="loading-progress-container">
              <!-- Animated loading bar with gradient and particles -->
              <div class="loading-bar">
                <div class="loading-progress" :style="{ width: `${loadingProgress}%` }"></div>
                <div class="loading-glow" :style="{ left: `${loadingProgress}%` }"></div>
                <div class="loading-particles">
                  <div v-for="n in 5" :key="`load-particle-${n}`" 
                       class="loading-particle" 
                       :style="getLoadingParticleStyle(n, loadingProgress)"></div>
                </div>
              </div>
            </div>
            
            <!-- Status message with dynamic typing effect -->
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
    // Disable ESLint for this file to prevent any issues
    /* eslint-disable */
    
    data() {
      return {
        loadingProgress: 0,
        titleVisible: false,
        isLoaded: false,
        particles: [],
        animationFrame: null,
        canvasContext: null,
        canvasWidth: 0,
        canvasHeight: 0,
        mouseX: 0,
        mouseY: 0,
        moleculeConnections: [],
        loadingMessages: [
          'Initializing quantum patterns...',
          'Loading molecular engines...',
          'Calibrating structure detection...',
          'Systems operational'
        ],
        currentMessageIndex: 0,
        // Maximum loading time in milliseconds
        maxLoadTime: 5000
      };
    },
    
    computed: {
      ...mapState({
        isDarkMode: state => state.theme?.isDarkMode || false
      }),
      
      loadingMessage() {
        return this.loadingMessages[this.currentMessageIndex];
      },
      
      // Compute theme colors based on dark/light mode
      themeColors() {
        if (this.isDarkMode) {
          return {
            primary: '74, 77, 231', // Deep blue
            secondary: '78, 13, 177', // Purple
            accent: '29, 78, 216', // Blue
            highlight: '228, 55, 113', // Pink
            background: '7, 11, 26', // Dark blue
            surface: '15, 23, 42', // Midnight blue
            text: '255, 255, 255', // White
            textSecondary: '203, 213, 225' // Light gray
          };
        } else {
          return {
            primary: '23, 90, 219', // Blue
            secondary: '110, 54, 231', // Purple
            accent: '15, 118, 110', // Teal
            highlight: '220, 38, 38', // Red
            background: '240, 245, 255', // Light blue-gray
            surface: '255, 255, 255', // White
            text: '15, 23, 42', // Dark blue
            textSecondary: '71, 85, 105' // Slate gray
          };
        }
      }
    },
    
    mounted() {
      // Initialize particles and canvas
      this.initParticles();
      
      // Track mouse movement for interactive effects
      window.addEventListener('mousemove', this.handleMouseMove);
      
      // Listen for theme changes
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', this.detectColorScheme);
      
      // Start staggered animations
      setTimeout(() => {
        this.titleVisible = true;
      }, 800);
      
      // Generate molecule connections
      this.generateMoleculeConnections();
      
      // Simulate loading progress with 5-second maximum
      this.simulateLoading();
    },
    
    beforeUnmount() {
      // Clean up animation frame and event listeners
      if (this.animationFrame) {
        cancelAnimationFrame(this.animationFrame);
      }
      
      window.removeEventListener('mousemove', this.handleMouseMove);
      window.matchMedia('(prefers-color-scheme: dark)').removeEventListener('change', this.detectColorScheme);
    },
    
    methods: {
      // Detect system color scheme preference
      detectColorScheme(e) {
        if (e.matches) {
          // Dark mode preferred
          if (!this.$store.state.theme.userSelectedTheme) {
            this.$store.commit('theme/SET_DARK_MODE', true);
          }
        } else {
          // Light mode preferred
          if (!this.$store.state.theme.userSelectedTheme) {
            this.$store.commit('theme/SET_DARK_MODE', false);
          }
        }
      },
      
      handleMouseMove(e) {
        // Track mouse position for particle and element interactions
        this.mouseX = e.clientX;
        this.mouseY = e.clientY;
      },
      
      initParticles() {
        const canvas = this.$refs.particleCanvas;
        if (!canvas) return;
        
        this.canvasContext = canvas.getContext('2d');
        
        // Set canvas size and adjust for device pixel ratio
        const updateCanvasSize = () => {
          const pixelRatio = window.devicePixelRatio || 1;
          this.canvasWidth = window.innerWidth;
          this.canvasHeight = window.innerHeight;
          
          canvas.width = this.canvasWidth * pixelRatio;
          canvas.height = this.canvasHeight * pixelRatio;
          canvas.style.width = `${this.canvasWidth}px`;
          canvas.style.height = `${this.canvasHeight}px`;
          
          this.canvasContext.scale(pixelRatio, pixelRatio);
        };
        
        updateCanvasSize();
        window.addEventListener('resize', updateCanvasSize);
        
        // Create particles - limit number for performance
        this.particles = [];
        const particleCount = Math.min(80, Math.floor((this.canvasWidth * this.canvasHeight) / 12000));
        
        for (let i = 0; i < particleCount; i++) {
          this.particles.push({
            x: Math.random() * this.canvasWidth,
            y: Math.random() * this.canvasHeight,
            radius: Math.random() * 2 + 1,
            density: Math.random() * 30 + 10,
            speed: Math.random() * 0.5 + 0.2,
            angle: Math.random() * Math.PI * 2,
            opacity: Math.random() * 0.5 + 0.3,
            color: this.getRandomParticleColor()
          });
        }
        
        // Start animation loop
        this.animateParticles();
      },
      
      getRandomParticleColor() {
        // Use theme colors
        const { primary, secondary, accent, highlight } = this.themeColors;
        const colors = [primary, secondary, accent, highlight];
        
        return colors[Math.floor(Math.random() * colors.length)];
      },
      
      animateParticles() {
        if (!this.canvasContext) return;
        
        // Clear canvas
        this.canvasContext.clearRect(0, 0, this.canvasWidth, this.canvasHeight);
        
        // Update and draw each particle
        for (let i = 0; i < this.particles.length; i++) {
          const p = this.particles[i];
          
          // Move particle
          p.x += Math.cos(p.angle) * p.speed;
          p.y += Math.sin(p.angle) * p.speed;
          
          // Bounce off edges
          if (p.x < 0 || p.x > this.canvasWidth) {
            p.angle = Math.PI - p.angle;
          }
          
          if (p.y < 0 || p.y > this.canvasHeight) {
            p.angle = -p.angle;
          }
          
          // Interactive effect - particles gravitate toward mouse
          if (this.mouseX && this.mouseY) {
            const dx = this.mouseX - p.x;
            const dy = this.mouseY - p.y;
            const distance = Math.sqrt(dx * dx + dy * dy);
            
            if (distance < 120) {
              // Apply gravitational pull toward mouse
              p.angle = Math.atan2(dy, dx);
              p.speed = Math.min(p.speed + 0.1, 2);
            } else {
              p.speed = Math.max(p.speed * 0.99, p.speed / 2);
            }
          }
          
          // Draw particle with custom color
          this.canvasContext.globalAlpha = p.opacity * (this.loadingProgress / 100);
          this.canvasContext.fillStyle = `rgba(${p.color}, ${p.opacity})`;
          this.canvasContext.beginPath();
          this.canvasContext.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
          this.canvasContext.fill();
        }
        
        // Draw connections between nearby particles - limit for performance
        for (let i = 0; i < this.particles.length; i+=2) {
          for (let j = i + 2; j < this.particles.length; j+=2) {
            const p1 = this.particles[i];
            const p2 = this.particles[j];
            
            const dx = p1.x - p2.x;
            const dy = p1.y - p2.y;
            const distance = Math.sqrt(dx * dx + dy * dy);
            
            if (distance < 100) {
              // Create gradient for connection line
              const gradient = this.canvasContext.createLinearGradient(p1.x, p1.y, p2.x, p2.y);
              gradient.addColorStop(0, `rgba(${p1.color}, ${(1 - distance / 100) * 0.5})`);
              gradient.addColorStop(1, `rgba(${p2.color}, ${(1 - distance / 100) * 0.5})`);
              
              this.canvasContext.globalAlpha = (1 - distance / 100) * 0.4 * (this.loadingProgress / 100);
              this.canvasContext.strokeStyle = gradient;
              this.canvasContext.lineWidth = 1;
              this.canvasContext.beginPath();
              this.canvasContext.moveTo(p1.x, p1.y);
              this.canvasContext.lineTo(p2.x, p2.y);
              this.canvasContext.stroke();
            }
          }
        }
        
        // Continue animation loop
        this.animationFrame = requestAnimationFrame(this.animateParticles);
      },
      
      generateMoleculeConnections() {
        this.moleculeConnections = [];
        
        // Define coordinates for the molecules (key positions)
        const molecules = [
          { x: 60, y: 60 },   // 0: Top left
          { x: 45, y: 210 },  // 1: Bottom left
          { x: 255, y: 90 },  // 2: Top right
          { x: 240, y: 225 }, // 3: Bottom right
          { x: 90, y: 120 },  // 4: Middle left
          { x: 165, y: 75 },  // 5: Middle top
          { x: 225, y: 165 }, // 6: Middle right
          { x: 150, y: 120 }  // 7: Center
        ];
        
        // Create connections between molecules
        const connections = [
          [0, 4], [0, 5], [1, 4], [2, 5], [2, 6], 
          [3, 6], [4, 7], [5, 7], [6, 7]
        ];
        
        // Build the connection objects
        connections.forEach(([from, to]) => {
          this.moleculeConnections.push({
            x1: molecules[from].x,
            y1: molecules[from].y,
            x2: molecules[to].x,
            y2: molecules[to].y
          });
        });
      },
      
      simulateLoading() {
        const startTime = performance.now();
        const totalDuration = this.maxLoadTime;
        
        // Define thresholds for message changes (evenly distributed)
        const messageThresholds = [0, 33, 66, 90];
        
        const updateLoading = () => {
          const elapsedTime = performance.now() - startTime;
          const progress = Math.min((elapsedTime / totalDuration) * 100, 100);
          
          // Set loading progress
          this.loadingProgress = progress;
          
          // Update message based on progress
          for (let i = 0; i < messageThresholds.length; i++) {
            if (progress >= messageThresholds[i] && this.currentMessageIndex !== i) {
              this.currentMessageIndex = i;
            }
          }
          
          if (progress < 100) {
            // Continue updating until we reach 100%
            requestAnimationFrame(updateLoading);
          } else {
            // Loading complete
            setTimeout(() => {
              this.isLoaded = true;
              
              // Emit completion event after animation finishes
              setTimeout(() => {
                this.$emit('loading-complete');
              }, 1200);
            }, 200);
          }
        };
        
        // Start the loading animation
        updateLoading();
      },
      
      // Dynamic styles for animations and effects
      getMoleculeStyle(index) {
        // Define fixed positions for molecules to match SVG connections
        const positions = [
          { top: '20%', left: '20%' },  // 0: Top left
          { top: '70%', left: '15%' },  // 1: Bottom left
          { top: '30%', left: '85%' },  // 2: Top right
          { top: '75%', left: '80%' },  // 3: Bottom right
          { top: '40%', left: '30%' },  // 4: Middle left
          { top: '25%', left: '55%' },  // 5: Middle top
          { top: '55%', left: '75%' },  // 6: Middle right
          { top: '40%', left: '50%' }   // 7: Center
        ];
        
        // Make sure we don't try to access beyond the array bounds
        const safeIndex = index % positions.length;
        const position = positions[safeIndex];
        
        const delay = 0.8 + (safeIndex * 0.1);
        const duration = 6 + (safeIndex % 3) * 2;
        const size = 6 + (safeIndex % 4) * 2;
        
        // Get different colors for molecules using theme colors
        const { primary, secondary, accent, highlight } = this.themeColors;
        const colors = [
          `rgba(${primary}, 0.9)`,
          `rgba(${secondary}, 0.9)`,
          `rgba(${accent}, 0.9)`,
          `rgba(${highlight}, 0.9)`
        ];
        
        const color = colors[safeIndex % colors.length];
        
        return {
          top: position.top,
          left: position.left,
          animationDelay: `${delay}s`,
          animationDuration: `${duration}s`,
          width: `${size}px`,
          height: `${size}px`,
          backgroundColor: color,
          boxShadow: `0 0 10px ${color}, 0 0 20px ${color.replace('0.9', '0.5')}`
        };
      },
      
      getOrbitalStyle(index, ringNum) {
        const angle = (index / (ringNum === 1 ? 6 : ringNum === 2 ? 8 : 10)) * 360;
        const delay = index * 0.1;
        
        // Different colors for each ring using theme colors
        const { primary, secondary, accent } = this.themeColors;
        const colors = [
          `rgba(${primary}, 0.9)`,
          `rgba(${secondary}, 0.9)`,
          `rgba(${accent}, 0.9)`
        ];
        
        return {
          transform: `rotateZ(${angle}deg) translateX(${ringNum === 1 ? 80 : ringNum === 2 ? 110 : 140}px)`,
          animationDelay: `${delay}s`,
          backgroundColor: colors[ringNum - 1]
        };
      },
      
      getSparkleStyle(index) {
        const size = 5 + (index * 2);
        const top = 20 + (index * 15);
        const left = 20 + (index * 12);
        const delay = index * 0.3;
        
        return {
          width: `${size}px`,
          height: `${size}px`,
          top: `${top}%`,
          left: `${left}%`,
          animationDelay: `${delay}s`
        };
      },
      
      getStarStyle(index) {
        const size = 1 + Math.random() * 2;
        const top = Math.random() * 100;
        const left = Math.random() * 100;
        const animationDuration = 3 + Math.random() * 4;
        const delay = Math.random() * 2;
        
        return {
          width: `${size}px`,
          height: `${size}px`,
          top: `${top}%`,
          left: `${left}%`,
          animationDuration: `${animationDuration}s`,
          animationDelay: `${delay}s`
        };
      },
      
      getLogoRotation() {
        // Only apply 3D rotation effect if mouse position is available
        if (!this.mouseX || !this.mouseY) return {};
        
        // Calculate rotation based on mouse position
        const rotateX = (this.mouseY / window.innerHeight * 10) - 5;
        const rotateY = (this.mouseX / window.innerWidth * 10) - 5;
        
        return {
          transform: `rotateX(${rotateX}deg) rotateY(${rotateY}deg)`
        };
      },
      
      getLoadingParticleStyle(particleIndex, progress) {
        const offset = (progress / 100) * 100;
        const basePos = (particleIndex / 5) * 100;
        const pos = (basePos + offset) % 100;
        
        // Use theme colors
        const { primary, secondary } = this.themeColors;
        
        return {
          left: `${pos}%`,
          animationDelay: `${particleIndex * 0.1}s`,
          backgroundColor: particleIndex % 2 === 0 ? 
            `rgba(${primary}, 0.8)` : 
            `rgba(${secondary}, 0.8)`
        };
      }
    }
  };
  </script>
  
  <style lang="scss">
  /* Dynamic color theme variables */
  .cosmic-loading-screen {
    /* Dark mode (default) */
    --color-primary: 74, 77, 231; /* Deep blue */
    --color-secondary: 78, 13, 177; /* Purple */
    --color-accent: 29, 78, 216; /* Blue */
    --color-highlight: 228, 55, 113; /* Pink */
    --color-background: 7, 11, 26; /* Dark blue */
    --color-surface: 15, 23, 42; /* Midnight blue */
    --color-text: 255, 255, 255; /* White */
    --color-text-secondary: 203, 213, 225; /* Light gray */
    
    /* Base gradient definitions */
    --gradient-primary: linear-gradient(135deg, rgba(var(--color-primary), 1) 0%, rgba(var(--color-highlight), 1) 100%);
    --gradient-secondary: linear-gradient(135deg, rgba(var(--color-secondary), 1) 0%, rgba(var(--color-accent), 1) 100%);
    
    /* Light mode overrides */
    &.light-mode {
      --color-primary: 23, 90, 219; /* Blue */
      --color-secondary: 110, 54, 231; /* Purple */
      --color-accent: 15, 118, 110; /* Teal */
      --color-highlight: 220, 38, 38; /* Red */
      --color-background: 240, 245, 255; /* Light blue-gray */
      --color-surface: 255, 255, 255; /* White */
      --color-text: 15, 23, 42; /* Dark blue */
      --color-text-secondary: 71, 85, 105; /* Slate gray */
    }
  }
  
  /* Base container with advanced 3D perspective */
  .cosmic-loading-screen {
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
    transform-style: preserve-3d;
    transition: opacity 1s cubic-bezier(0.65, 0, 0.35, 1);
    
    /* Transition when loading completes */
    &.loaded {
      opacity: 0;
      pointer-events: none;
      
      .logo-container {
        animation: logoZoomOut 1.2s cubic-bezier(0.16, 1, 0.3, 1) forwards;
      }
      
      .floating-elements {
        opacity: 0;
        transition: opacity 0.8s ease;
      }
      
      .orbital-ring {
        animation: ringExpand 1.2s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
      }
      
      .dna-container {
        transform: translateZ(500px);
        transition: transform 1s cubic-bezier(0.16, 1, 0.3, 1);
      }
    }
  }
  
  /* Advanced Particle Canvas */
  .particle-canvas {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 1;
    opacity: 0;
    animation: fadeIn 1.5s ease forwards 0.3s;
  }
  
  /* Star field background */
  .star-field {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 0;
  }
  
  .star {
    position: absolute;
    background-color: rgba(var(--color-text), 0.8);
    border-radius: 50%;
    animation: twinkle 3s infinite alternate;
  }
  
  /* Animated Background Gradient Spheres */
  .animated-background {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 0;
    overflow: hidden;
  }
  
  .gradient-sphere {
    position: absolute;
    border-radius: 50%;
    filter: blur(80px);
    opacity: 0;
    background: radial-gradient(circle at center, rgba(var(--color-primary), 0.5) 0%, rgba(var(--color-primary), 0) 70%);
    animation: spherePulse 12s infinite alternate ease-in-out, fadeIn 2s ease-out forwards;
    
    &.sphere-1 {
      top: 25%;
      left: 20%;
      width: 60vw;
      height: 60vw;
      animation-delay: 0s, 0.2s;
      transform: translate(-30%, -30%);
    }
    
    &.sphere-2 {
      bottom: 10%;
      right: 10%;
      width: 45vw;
      height: 45vw;
      animation-delay: 3s, 0.4s;
      background: radial-gradient(circle at center, rgba(var(--color-secondary), 0.5) 0%, rgba(var(--color-secondary), 0) 70%);
      transform: translate(20%, 20%);
    }
    
    &.sphere-3 {
      top: 60%;
      left: 50%;
      width: 50vw;
      height: 50vw;
      animation-delay: 5s, 0.6s;
      background: radial-gradient(circle at center, rgba(var(--color-accent), 0.4) 0%, rgba(var(--color-accent), 0) 70%);
      transform: translate(-50%, -50%);
    }
  }
  
  /* Grid background */
  .grid-container {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 0;
    overflow: hidden;
    perspective: 1000px;
  }
  
  .grid {
    position: absolute;
    top: 0;
    left: 0;
    width: 200%;
    height: 200%;
    transform-style: preserve-3d;
    transform: rotateX(60deg) translateZ(-100px) translateY(-50%) translateX(-25%);
    background-size: 40px 40px;
    background-image: 
      linear-gradient(rgba(var(--color-primary), 0.1) 1px, transparent 1px),
      linear-gradient(90deg, rgba(var(--color-primary), 0.1) 1px, transparent 1px);
    opacity: 0;
    animation: fadeIn 1.5s ease forwards 0.5s, gridMove 60s linear infinite;
  }
  
  /* Main perspective container with improved 3D effect */
  .perspective-container {
    position: relative;
    perspective: 1200px;
    transform-style: preserve-3d;
    z-index: 3;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100%;
    max-width: 800px;
    padding: 2rem;
  }
  
  .transform-wrapper {
    transform-style: preserve-3d;
    transition: transform 1.2s cubic-bezier(0.16, 1, 0.3, 1);
    transform: translateZ(0) rotateX(0);
    
    &.animate-complete {
      transform: translateZ(-800px) rotateX(20deg);
    }
  }
  
  /* DNA helix animation */
  .dna-container {
    position: absolute;
    top: -30%;
    left: 50%;
    width: 80px;
    height: 300px;
    transform: translateX(-50%) translateZ(-200px) rotateX(60deg);
    transform-style: preserve-3d;
    transition: transform 1s ease;
    opacity: 0;
    animation: fadeIn 1s ease forwards 0.9s;
    z-index: 0;
  }
  
  .dna-strand {
    position: relative;
    width: 100%;
    height: 100%;
    transform-style: preserve-3d;
    animation: dnaRotate 12s linear infinite;
  }
  
  .dna-step {
    position: absolute;
    width: 100%;
    height: 30px;
    transform-style: preserve-3d;
    
    &:nth-child(1) { top: 0px; transform: rotateY(0deg); }
    &:nth-child(2) { top: 30px; transform: rotateY(36deg); }
    &:nth-child(3) { top: 60px; transform: rotateY(72deg); }
    &:nth-child(4) { top: 90px; transform: rotateY(108deg); }
    &:nth-child(5) { top: 120px; transform: rotateY(144deg); }
    &:nth-child(6) { top: 150px; transform: rotateY(180deg); }
    &:nth-child(7) { top: 180px; transform: rotateY(216deg); }
    &:nth-child(8) { top: 210px; transform: rotateY(252deg); }
    &:nth-child(9) { top: 240px; transform: rotateY(288deg); }
    &:nth-child(10) { top: 270px; transform: rotateY(324deg); }
  }
  
  .dna-base {
    position: absolute;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: rgba(var(--color-primary), 0.8);
    
    &.left-base {
      left: 0;
      box-shadow: 0 0 10px rgba(var(--color-primary), 0.5);
    }
    
    &.right-base {
      right: 0;
      background: rgba(var(--color-secondary), 0.8);
      box-shadow: 0 0 10px rgba(var(--color-secondary), 0.5);
    }
  }
  
  .dna-connector {
    position: absolute;
    width: 80px;
    height: 2px;
    top: 5px;
    left: 0;
    background: linear-gradient(
      90deg,
      rgba(var(--color-primary), 0.8) 0%,
      rgba(var(--color-secondary), 0.8) 100%
    );
    transform-origin: center;
  }
  
  /* Logo showcase with advanced visual elements */
  .logo-showcase {
    position: relative;
    width: 280px;
    height: 280px;
    margin: 0 auto;
    transform-style: preserve-3d;
  }
  
  /* Energy field effect */
  .energy-field {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 220px;
    height: 220px;
    transform: translate(-50%, -50%);
    border-radius: 50%;
    background: radial-gradient(
      circle at center,
      rgba(var(--color-primary), 0.05) 0%,
      rgba(var(--color-primary), 0.1) 40%,
      rgba(var(--color-primary), 0.05) 80%,
      rgba(var(--color-primary), 0) 100%
    );
    box-shadow: inset 0 0 30px rgba(var(--color-primary), 0.2);
    opacity: 0;
    animation: energyPulse 6s ease-in-out infinite alternate, fadeIn 0.8s ease forwards 0.7s;
    z-index: 1;
  }
  
  /* Orbital rings with animated particles */
  .orbital-ring {
    position: absolute;
    top: 50%;
    left: 50%;
    border-radius: 50%;
    border: 1px solid rgba(var(--color-primary), 0.5);
    transform: translate(-50%, -50%) rotateX(75deg);
    opacity: 0;
    animation: ringRotate 30s linear infinite, fadeIn 0.8s ease forwards;
    
    &.ring-1 {
      width: 160px;
      height: 160px;
      animation-delay: 0s, 0.6s;
      border-width: 2px;
    }
    
    &.ring-2 {
      width: 220px;
      height: 220px;
      animation-delay: 4s, 0.8s;
      animation-direction: reverse;
      border-color: rgba(var(--color-secondary), 0.5);
    }
    
    &.ring-3 {
      width: 280px;
      height: 280px;
      animation-delay: 2s, 1s;
      border-color: rgba(var(--color-accent), 0.5);
    }
  }
  
  .orbital-particle {
    position: absolute;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    top: 50%;
    left: 50%;
    margin-top: -3px;
    margin-left: -3px;
    box-shadow: 0 0 10px currentColor;
    filter: blur(1px);
    animation: particlePulse 2s infinite alternate;
  }
  
  /* Core logo wrapper */
  .logo-core-wrapper {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    transform-style: preserve-3d;
    z-index: 2;
  }
  
  /* Pulse effect rings with enhanced visuals */
  .logo-pulse-rings {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 1;
  }
  
  .pulse-ring {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    border-radius: 50%;
    border: 2px solid transparent;
    width: 100px;
    height: 100px;
    background: linear-gradient(
      45deg,
      rgba(var(--color-primary), 0.7) 0%,
      rgba(var(--color-secondary), 0.4) 100%
    );
    opacity: 0;
    filter: blur(1px);
    
    &:nth-child(1) {
      animation: pulsate 3s ease-out infinite;
      animation-delay: 0s;
    }
    
    &:nth-child(2) {
      animation: pulsate 3s ease-out infinite;
      animation-delay: 1.5s;
    }
  }
  
  /* Main logo container with interactive 3D effect */
  .logo-container {
    position: relative;
    width: 120px;
    height: 120px;
    display: flex;
    align-items: center;
    justify-content: center;
    transform: translateZ(0) scale(0);
    animation: logoReveal 1s cubic-bezier(0.34, 1.56, 0.64, 1) forwards 0.3s;
    transform-style: preserve-3d;
    transition: transform 0.2s ease-out;
    
    .logo {
      width: 100%;
      height: 100%;
      object-fit: contain;
      position: relative;
      z-index: 2;
      transform: translateZ(10px);
      filter: drop-shadow(0 8px 20px rgba(0, 0, 0, 0.3));
      animation: logoHover 8s ease-in-out infinite alternate;
    }
  }
  
  /* Holographic effect for logo */
  .logo-hologram-effect {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      45deg,
      rgba(255, 255, 255, 0) 0%,
      rgba(255, 255, 255, 0.1) 30%,
      rgba(255, 255, 255, 0.15) 47%,
      rgba(255, 255, 255, 0.1) 70%,
      rgba(255, 255, 255, 0) 100%
    );
    animation: hologramShift 8s infinite linear;
    transform: translateZ(12px);
    z-index: 3;
    filter: blur(0.5px);
    opacity: 0;
    animation: hologramShift 8s infinite linear, fadeIn 0.5s ease forwards 1.2s;
  }
  
  /* Logo glow effect with enhanced depth */
  .logo-glow {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 150%;
    height: 150%;
    transform: translate(-50%, -50%) translateZ(-5px);
    background: radial-gradient(
      circle at center,
      rgba(var(--color-primary), 0.8) 0%,
      rgba(var(--color-primary), 0.4) 30%,
      rgba(var(--color-primary), 0) 70%
    );
    border-radius: 50%;
    filter: blur(20px);
    opacity: 0;
    z-index: 1;
    animation: glowPulse 4s infinite alternate, fadeIn 0.8s ease forwards 0.6s;
  }
  
  /* Logo reflection with improved realism */
  .logo-reflection {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      135deg,
      rgba(255, 255, 255, 0.85) 0%,
      rgba(255, 255, 255, 0) 50%
    );
    border-radius: 30%;
    transform: translateZ(15px) scale(0.85);
    filter: blur(1px);
    opacity: 0;
    z-index: 3;
    animation: reflectionMove 6s ease-in-out infinite alternate, fadeIn 0.5s ease forwards 0.9s;
  }
  
  /* Advanced lens flare effect */
  .lens-flare {
    position: absolute;
    top: -20%;
    right: -20%;
    width: 80px;
    height: 80px;
    background: radial-gradient(
      circle at center,
      rgba(255, 255, 255, 0.9) 0%,
      rgba(255, 255, 255, 0.5) 30%,
      rgba(255, 255, 255, 0) 70%
    );
    transform: translateZ(20px);
    opacity: 0;
    z-index: 4;
    filter: blur(2px);
    animation: flarePulse 6s ease-in-out infinite alternate, fadeIn 0.5s ease forwards 1.2s;
  }
  
  /* Sparkle effects */
  .sparkles {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    transform-style: preserve-3d;
    z-index: 5;
  }
  
  .sparkle {
    position: absolute;
    width: 8px;
    height: 8px;
    background: rgba(255, 255, 255, 0.9);
    transform: translateZ(25px);
    border-radius: 50%;
    clip-path: polygon(
      50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%,
      50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%
    );
    animation: sparkleEffect 3s infinite alternate;
    opacity: 0;
    animation-fill-mode: both;
  }
  
  /* Logo shadow with realistic depth */
  .logo-shadow {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 110%;
    height: 110%;
    transform: translate(-50%, -50%) translateZ(-20px) scale(0.9);
    background: radial-gradient(
      circle at center,
      rgba(0, 0, 0, 0.7) 0%,
      rgba(0, 0, 0, 0.2) 50%,
      rgba(0, 0, 0, 0) 70%
    );
    border-radius: 50%;
    filter: blur(15px);
    opacity: 0;
    z-index: 0;
    animation: fadeIn 0.8s ease forwards 0.7s, shadowPulse 4s ease-in-out infinite alternate;
  }
  
  /* Floating molecular elements with connections */
  .floating-elements {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 0;
    transform-style: preserve-3d;
  }
  
  .floating-molecule {
    position: absolute;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: rgba(var(--color-primary), 0.8);
    box-shadow: 0 0 10px rgba(var(--color-primary), 0.8);
    opacity: 0;
    animation: moleculePulse 3s infinite alternate, fadeIn 0.3s ease forwards;
    transform-style: preserve-3d;
    transform: translateZ(5px);
    
    .molecule-node {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: 100%;
      height: 100%;
      border-radius: 50%;
      animation: pulseBrightness 3s ease-in-out infinite;
    }
  }
  
  .molecule-connections {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    opacity: 0;
    animation: fadeIn 1.2s ease forwards 1.2s;
    transform: translateZ(3px);
    pointer-events: none;
  }
  
  .connection-line {
    stroke: rgba(var(--color-primary), 0.3);
    stroke-width: 1;
    stroke-dasharray: 5, 3;
    animation: connectionPulse 3s infinite alternate;
  }
  
  /* Text elements container with improved animations */
  .text-elements {
    margin-top: 2rem;
    text-align: center;
    opacity: 0;
    transform: translateY(20px);
    transition: all 0.8s cubic-bezier(0.34, 1.56, 0.64, 1);
    
    &.text-visible {
      opacity: 1;
      transform: translateY(0);
    }
  }
  
  /* Title styling with advanced visual effects */
  .title-container {
    display: inline-flex;
    align-items: center;
    margin-bottom: 1rem;
  }
  
  .title {
    font-size: 3.5rem;
    font-weight: 800;
    background: var(--gradient-primary);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    margin: 0;
    display: inline-flex;
    filter: drop-shadow(0 2px 10px rgba(var(--color-primary), 0.3));
  }
  
  /* Badge styling with enhanced effects */
  .badge-wrapper {
    position: relative;
    margin-left: 0.5rem;
    overflow: hidden;
  }
  
  .badge {
    font-size: 1.2rem;
    background: var(--gradient-primary);
    color: rgb(var(--color-text));
    padding: 0.2rem 0.6rem;
    border-radius: 0.35rem;
    font-weight: 700;
    box-shadow: 0 4px 15px rgba(var(--color-primary), 0.5);
    position: relative;
    
    &::before {
      content: '';
      position: absolute;
      top: -2px;
      left: -2px;
      right: -2px;
      bottom: -2px;
      background: var(--gradient-primary);
      opacity: 0.5;
      filter: blur(8px);
      border-radius: 0.45rem;
      z-index: -1;
      animation: pulseShadow 3s infinite alternate;
    }
  }
  
  .badge-shine {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      90deg,
      rgba(255, 255, 255, 0) 0%,
      rgba(255, 255, 255, 0.5) 50%,
      rgba(255, 255, 255, 0) 100%
    );
    transform: translateX(-100%);
    animation: shineBadge 3s ease-in-out infinite 2s;
  }
  
  /* Tagline styling with improved readability */
  .tagline-wrapper {
    position: relative;
    overflow: hidden;
    max-width: 600px;
    margin: 0 auto;
  }
  
  .tagline-glow {
    position: absolute;
    top: 0;
    left: 10%;
    width: 80%;
    height: 100%;
    background: radial-gradient(
      ellipse at center,
      rgba(var(--color-primary), 0.1) 0%,
      rgba(var(--color-primary), 0) 70%
    );
    filter: blur(10px);
    opacity: 0;
    animation: fadeIn 0.8s ease forwards 1.5s, taglineGlowPulse 6s infinite alternate 1.5s;
  }
  
  .tagline {
    font-size: 1.1rem;
    color: rgba(var(--color-text-secondary), 1);
    margin: 0;
    line-height: 1.4;
  }
  
  /* Loading elements styling with enhanced visuals */
  .loading-elements {
    margin-top: 3rem;
    width: 100%;
    max-width: 400px;
    z-index: 5;
    opacity: 0;
    animation: fadeIn 0.5s ease forwards 0.5s;
  }
  
  .loading-track {
    position: relative;
  }
  
  .loading-progress-container {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
  }
  
  .loading-bar {
    flex: 1;
    height: 8px;
    background: rgba(var(--color-primary), 0.1);
    border-radius: 4px;
    overflow: hidden;
    position: relative;
    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.1);
    
    .loading-progress {
      height: 100%;
      background: var(--gradient-primary);
      border-radius: 4px;
      transition: width 0.3s ease;
      box-shadow: 0 0 15px rgba(var(--color-primary), 0.7);
    }
    
    .loading-glow {
      position: absolute;
      top: 0;
      width: 180px;
      height: 100%;
      background: linear-gradient(
        90deg,
        rgba(255, 255, 255, 0) 0%,
        rgba(255, 255, 255, 0.3) 10%,
        rgba(255, 255, 255, 0.7) 50%,
        rgba(255, 255, 255, 0.3) 90%,
        rgba(255, 255, 255, 0) 100%
      );
      transform: translateX(-50%);
      filter: blur(3px);
      pointer-events: none;
    }
  }
  
  .loading-particles {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    pointer-events: none;
  }
  
  .loading-particle {
    position: absolute;
    top: 0;
    width: 3px;
    height: 100%;
    background: rgba(255, 255, 255, 0.8);
    filter: blur(1px);
    border-radius: 2px;
    animation: particleRise 1.5s infinite;
  }
  
  .loading-message-container {
    margin-top: 1rem;
    height: 24px;
    position: relative;
    overflow: hidden;
  }
  
  .loading-message {
    font-size: 1rem;
    color: rgba(var(--color-text-secondary), 1);
    margin: 0;
    text-align: center;
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 0.5rem;
    
    .message-text {
      display: inline-block;
    }
    
    .loading-dots {
      span {
        display: inline-block;
        animation: loadingDots 1.4s infinite;
        
        &:nth-child(2) {
          animation-delay: 0.2s;
        }
        
        &:nth-child(3) {
          animation-delay: 0.4s;
        }
      }
    }
  }
  
  /* Complex Animations */
  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  
  @keyframes logoReveal {
    0% {
      transform: translateZ(0) scale(0);
    }
    60% {
      transform: translateZ(0) scale(1.1);
    }
    100% {
      transform: translateZ(0) scale(1);
    }
  }
  
  @keyframes logoZoomOut {
    0% {
      transform: translateZ(0) scale(1);
    }
    100% {
      transform: translateZ(1500px) scale(30);
      opacity: 0;
    }
  }
  
  @keyframes logoHover {
    0% {
      transform: translateZ(10px) rotateY(0deg) rotateX(0deg);
    }
    100% {
      transform: translateZ(30px) rotateY(5deg) rotateX(-5deg);
    }
  }
  
  @keyframes glowPulse {
    0% {
      transform: translate(-50%, -50%) scale(1);
      opacity: 0.8;
    }
    100% {
      transform: translate(-50%, -50%) scale(1.2);
      opacity: 1;
    }
  }
  
  @keyframes reflectionMove {
    0% {
      transform: translateZ(15px) scale(0.85) rotate(0deg);
    }
    100% {
      transform: translateZ(15px) scale(0.85) rotate(180deg);
    }
  }
  
  @keyframes flarePulse {
    0% {
      transform: translateZ(20px) scale(1);
      opacity: 0.7;
    }
    100% {
      transform: translateZ(20px) scale(1.3);
      opacity: 0.9;
    }
  }
  
  @keyframes pulsate {
    0% {
      transform: translate(-50%, -50%) scale(0.6);
      opacity: 0.8;
    }
    50% {
      opacity: 0;
    }
    100% {
      transform: translate(-50%, -50%) scale(2.2);
      opacity: 0;
    }
  }
  
  @keyframes ringRotate {
    0% {
      transform: translate(-50%, -50%) rotateX(75deg) rotateZ(0deg);
    }
    100% {
      transform: translate(-50%, -50%) rotateX(75deg) rotateZ(360deg);
    }
  }
  
  @keyframes ringExpand {
    0% {
      transform: translate(-50%, -50%) rotateX(75deg) scale(1);
    }
    100% {
      transform: translate(-50%, -50%) rotateX(75deg) scale(20);
      opacity: 0;
    }
  }
  
  @keyframes spherePulse {
    0% {
      transform: translate(-30%, -30%) scale(1);
    }
    100% {
      transform: translate(-30%, -30%) scale(1.3);
    }
  }
  
  @keyframes moleculePulse {
    0% {
      transform: translateZ(5px) scale(1);
      box-shadow: 0 0 10px currentColor;
    }
    100% {
      transform: translateZ(15px) scale(1.3);
      box-shadow: 0 0 20px currentColor, 0 0 40px currentColor;
    }
  }
  
  @keyframes pulseBrightness {
    0% {
      filter: brightness(1);
    }
    50% {
      filter: brightness(1.5);
    }
    100% {
      filter: brightness(1);
    }
  }
  
  @keyframes pulseShadow {
    0% {
      opacity: 0.3;
      filter: blur(8px);
    }
    100% {
      opacity: 0.6;
      filter: blur(12px);
    }
  }
  
  @keyframes shineBadge {
    0% {
      transform: translateX(-100%);
    }
    20%, 100% {
      transform: translateX(100%);
    }
  }
  
  @keyframes twinkle {
    0% {
      opacity: 0.3;
      box-shadow: 0 0 0 rgba(var(--color-text), 0.8);
    }
    50% {
      opacity: 0.8;
      box-shadow: 0 0 3px rgba(var(--color-text), 0.8);
    }
    100% {
      opacity: 0.3;
      box-shadow: 0 0 0 rgba(var(--color-text), 0.8);
    }
  }
  
  @keyframes energyPulse {
    0% {
      transform: translate(-50%, -50%) scale(1);
      opacity: 0.6;
    }
    100% {
      transform: translate(-50%, -50%) scale(1.1);
      opacity: 0.8;
    }
  }
  
  @keyframes gridMove {
    0% {
      transform: rotateX(60deg) translateZ(-100px) translateY(-50%) translateX(-25%);
    }
    100% {
      transform: rotateX(60deg) translateZ(-100px) translateY(-50%) translateX(0%);
    }
  }
  
  @keyframes dnaRotate {
    0% {
      transform: rotateY(0deg);
    }
    100% {
      transform: rotateY(360deg);
    }
  }
  
  @keyframes particlePulse {
    0% {
      transform: scale(1);
      opacity: 0.7;
    }
    100% {
      transform: scale(1.5);
      opacity: 1;
    }
  }
  
  @keyframes sparkleEffect {
    0% {
      transform: translateZ(25px) scale(0.5) rotate(0deg);
      opacity: 0;
    }
    50% {
      opacity: 1;
    }
    100% {
      transform: translateZ(25px) scale(1.2) rotate(180deg);
      opacity: 0;
    }
  }
  
  @keyframes shadowPulse {
    0% {
      opacity: 0.4;
      transform: translate(-50%, -50%) translateZ(-20px) scale(0.9);
    }
    100% {
      opacity: 0.6;
      transform: translate(-50%, -50%) translateZ(-20px) scale(1);
    }
  }
  
  @keyframes connectionPulse {
    0% {
      stroke-opacity: 0.2;
      stroke-dasharray: 5, 3;
    }
    100% {
      stroke-opacity: 0.5;
      stroke-dasharray: 8, 2;
    }
  }
  
  @keyframes taglineGlowPulse {
    0% {
      transform: translateX(-5%) scale(0.95);
      opacity: 0.4;
    }
    100% {
      transform: translateX(5%) scale(1.05);
      opacity: 0.7;
    }
  }
  
  @keyframes particleRise {
    0% {
      transform: translateY(0) scale(0.5);
      opacity: 0.5;
    }
    50% {
      opacity: 1;
    }
    100% {
      transform: translateY(-100%) scale(1);
      opacity: 0;
    }
  }
  
  @keyframes hologramShift {
    0% {
      background-position: -100% 0;
    }
    100% {
      background-position: 200% 0;
    }
  }
  
  @keyframes loadingDots {
    0%, 20% {
      transform: translateY(0);
      opacity: 0.2;
    }
    50% {
      transform: translateY(-5px);
      opacity: 1;
    }
    80%, 100% {
      transform: translateY(0);
      opacity: 0.2;
    }
  }
  
  /* Responsive adjustments */
  @media (max-width: 768px) {
    .logo-showcase {
      width: 240px;
      height: 240px;
    }
    
    .logo-container {
      width: 100px;
      height: 100px;
    }
    
    .orbital-ring {
      &.ring-1 {
        width: 140px;
        height: 140px;
      }
      
      &.ring-2 {
        width: 180px;
        height: 180px;
      }
      
      &.ring-3 {
        width: 220px;
        height: 220px;
      }
    }
    
    .title {
      font-size: 2.8rem;
    }
    
    .badge {
      font-size: 1rem;
    }
    
    .tagline {
      font-size: 0.9rem;
    }
    
    .dna-container {
      transform: translateX(-50%) translateZ(-150px) rotateX(60deg) scale(0.8);
    }
  }
  
  @media (max-width: 480px) {
    .logo-showcase {
      width: 200px;
      height: 200px;
    }
    
    .logo-container {
      width: 80px;
      height: 80px;
    }
    
    .orbital-ring {
      &.ring-1 {
        width: 120px;
        height: 120px;
      }
      
      &.ring-2 {
        width: 150px;
        height: 150px;
      }
      
      &.ring-3 {
        width: 180px;
        height: 180px;
      }
    }
    
    .title {
      font-size: 2.4rem;
    }
    
    .perspective-container {
      padding: 1rem;
    }
    
    .dna-container {
      display: none;
    }
  }
  </style>