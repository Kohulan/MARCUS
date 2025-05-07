<template>
  <div class="coconut-auth-modal-backdrop" @click.self="close">
    <div class="coconut-auth-modal" :class="{ 'loading': isLoading }">
      <!-- Modal Header -->
      <div class="modal-header">
        <div class="modal-title">
          <vue-feather type="lock" class="icon"></vue-feather>
          <h2>COCONUT Database Login</h2>
        </div>
        <button type="button" class="close-button" @click="close" aria-label="Close">
          <vue-feather type="x" size="20"></vue-feather>
        </button>
      </div>
      
      <!-- Modal Content -->
      <div class="modal-content">
        <!-- Logo/Branding -->
        <div class="branding">
          <div class="logo-container">
            <img src="@/assets/coconut-logo.svg" alt="COCONUT Logo" class="logo" 
                 onerror="this.onerror=null; this.src='data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48cGF0aCBmaWxsPSIjMTBiOTgxIiBkPSJNNTAgOTBjMjIuMSAwIDQwLTE3LjkgNDAtNDBTNzIuMSAxMCA1MCAxMCAxMCAyNy45IDEwIDUwczE3LjkgNDAgNDAgNDB6bTE5LjctMzAuOUw1MCQ0OS4yNnYtMjVsMTkuNyAxOC4yNmExLjk5IDEuOTkgMCAwMDIuODIgMCAxLjk5IDEuOTkgMCAwMDAtMi44MWwtMjAuOC0yMC44YTEuOTkgMS45OSAwIDAwLTIuODIgMGwtMjAuOCAyMC44YTEuOTkgMS45OSAwIDAwMCAyLjgxIDEuOTkgMS45OSAwIDAwMi44MiAwTDUwIDQ5LjI2VjcwYTEuOTkgMS45OSAwIDAwMS45OSAxLjk5QTEuOTkgMS45OSAwIDAwNTQgNzBWNDkuMjZsMTkuNyAxOS44NGEyIDIgMCAwMDIuODIgMCAyIDIgMCAwMDAtMi44MXoiLz48L3N2Zz4='" />
          </div>
          <h3>Natural Products Online Database</h3>
          <p>Please log in with your COCONUT account to submit molecules</p>
        </div>
        
        <!-- Error Message -->
        <div v-if="error" class="error-message">
          <vue-feather type="alert-circle" class="error-icon"></vue-feather>
          <span>{{ error }}</span>
        </div>
        
        <!-- Login Form -->
        <form @submit.prevent="login" class="login-form">
          <div class="form-group">
            <label for="email">
              <vue-feather type="mail" class="input-icon"></vue-feather>
              Email Address
            </label>
            <input 
              type="email" 
              id="email" 
              v-model="credentials.email" 
              :disabled="isLoading"
              placeholder="Enter your email"
              autocomplete="email"
              required
            />
          </div>
          
          <div class="form-group">
            <label for="password">
              <vue-feather type="key" class="input-icon"></vue-feather>
              Password
            </label>
            <div class="password-input-wrapper">
              <input 
                :type="showPassword ? 'text' : 'password'" 
                id="password" 
                v-model="credentials.password" 
                :disabled="isLoading"
                placeholder="Enter your password"
                autocomplete="current-password"
                required
              />
              <button 
                type="button" 
                class="toggle-password" 
                @click="showPassword = !showPassword"
                :aria-label="showPassword ? 'Hide password' : 'Show password'"
              >
                <vue-feather :type="showPassword ? 'eye-off' : 'eye'" size="18"></vue-feather>
              </button>
            </div>
          </div>
          
          <div class="actions">
            <button 
              type="submit" 
              class="login-button" 
              :disabled="isLoading || !isFormValid"
            >
              <vue-feather v-if="isLoading" type="loader" class="spin"></vue-feather>
              <vue-feather v-else type="log-in"></vue-feather>
              {{ isLoading ? 'Logging in...' : 'Log In' }}
            </button>
          </div>
        </form>
        
        <!-- Registration Link -->
        <div class="register-link">
          <p>
            Don't have an account? 
            <a href="https://coconut.naturalproducts.net/register" target="_blank" rel="noopener noreferrer">
              Sign up at COCONUT
              <vue-feather type="external-link" size="14"></vue-feather>
            </a>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import coconutService from '@/services/coconutService';

export default {
  name: 'CoconutLoginModal',
  
  data() {
    return {
      credentials: {
        email: '',
        password: ''
      },
      error: null,
      isLoading: false,
      showPassword: false
    };
  },
  
  computed: {
    isFormValid() {
      return this.credentials.email && this.credentials.password;
    }
  },
  
  methods: {
    /**
     * Handle login form submission
     */
    async login() {
      this.error = null;
      this.isLoading = true;
      
      try {
        const result = await coconutService.login(this.credentials);
        
        if (result.success) {
          this.$emit('login-success', result.user);
          this.close();
        } else {
          this.error = result.error || 'Authentication failed. Please check your credentials and try again.';
        }
      } catch (error) {
        console.error('Login error:', error);
        this.error = 'An unexpected error occurred. Please try again later.';
      } finally {
        this.isLoading = false;
      }
    },
    
    /**
     * Close the modal
     */
    close() {
      this.$emit('close');
    }
  }
};
</script>

<style lang="scss" scoped>
.coconut-auth-modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(5px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1300;
  animation: fadeIn 0.3s ease;
}

.coconut-auth-modal {
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.95),
    rgba(240, 240, 245, 0.9)
  );
  border-radius: 16px;
  box-shadow: 
    0 20px 60px rgba(0, 0, 0, 0.3),
    0 0 0 1px rgba(255, 255, 255, 0.1);
  width: 90%;
  max-width: 450px;
  overflow: hidden;
  position: relative;
  animation: slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1);
  transform-origin: center bottom;
  
  @media (prefers-color-scheme: dark) {
    background: linear-gradient(
      135deg,
      rgba(30, 30, 35, 0.95),
      rgba(20, 20, 25, 0.9)
    );
    box-shadow: 
      0 20px 60px rgba(0, 0, 0, 0.5),
      0 0 0 1px rgba(255, 255, 255, 0.05);
  }
  
  &.loading::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(90deg, transparent, rgba(16, 185, 129, 0.2), transparent);
    background-size: 200% 100%;
    animation: shimmer 2s infinite;
    z-index: 10;
    pointer-events: none;
  }
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid rgba(0, 0, 0, 0.1);
  background: rgba(16, 185, 129, 0.15);
  
  @media (prefers-color-scheme: dark) {
    border-bottom-color: rgba(255, 255, 255, 0.1);
    background: rgba(16, 185, 129, 0.2);
  }
}

.modal-title {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  
  h2 {
    font-size: 1.25rem;
    font-weight: 700;
    margin: 0;
    color: #10b981;
    text-shadow: 0 1px 1px rgba(0, 0, 0, 0.1);
  }
  
  .icon {
    color: #10b981;
    filter: drop-shadow(0 1px 1px rgba(0, 0, 0, 0.1));
  }
}

.close-button {
  background: none;
  border: none;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  
  &:hover {
    background: rgba(100, 116, 139, 0.1);
    color: #475569;
    transform: rotate(90deg);
  }
  
  @media (prefers-color-scheme: dark) {
    color: #94a3b8;
    
    &:hover {
      background: rgba(148, 163, 184, 0.1);
      color: #cbd5e1;
    }
  }
}

.modal-content {
  padding: 1.5rem;
}

.branding {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  margin-bottom: 1.5rem;
  
  h3 {
    font-size: 1.25rem;
    font-weight: 600;
    margin: 0.5rem 0 0.25rem;
    background: linear-gradient(to right, #047857, #10b981);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
  }
  
  p {
    font-size: 0.95rem;
    color: #64748b;
    margin: 0.25rem 0;
    max-width: 26rem;
    
    @media (prefers-color-scheme: dark) {
      color: #94a3b8;
    }
  }
}

.logo-container {
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #f8fafc;
  box-shadow: 
    0 10px 15px -3px rgba(16, 185, 129, 0.1),
    0 4px 6px -2px rgba(16, 185, 129, 0.05),
    0 0 0 1px rgba(16, 185, 129, 0.1);
  padding: 1rem;
  margin-bottom: 0.5rem;
  
  @media (prefers-color-scheme: dark) {
    background: #1e293b;
    box-shadow: 
      0 10px 15px -3px rgba(16, 185, 129, 0.15),
      0 4px 6px -2px rgba(16, 185, 129, 0.1),
      0 0 0 1px rgba(16, 185, 129, 0.2);
  }
  
  .logo {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
}

.error-message {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  margin-bottom: 1.25rem;
  border-radius: 8px;
  background-color: rgba(244, 63, 94, 0.1);
  border-left: 3px solid rgb(244, 63, 94);
  color: rgb(244, 63, 94);
  font-size: 0.9rem;
  
  .error-icon {
    flex-shrink: 0;
  }
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  
  label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.95rem;
    font-weight: 500;
    color: #334155;
    
    @media (prefers-color-scheme: dark) {
      color: #cbd5e1;
    }
    
    .input-icon {
      color: #64748b;
      
      @media (prefers-color-scheme: dark) {
        color: #94a3b8;
      }
    }
  }
  
  input {
    padding: 0.75rem 1rem;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    font-size: 1rem;
    background-color: rgba(255, 255, 255, 0.9);
    color: #1e293b;
    transition: all 0.2s ease;
    width: 100%;
    box-sizing: border-box;
    
    &:focus {
      outline: none;
      border-color: #10b981;
      box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);
    }
    
    &:disabled {
      background-color: #f1f5f9;
      cursor: not-allowed;
    }
    
    @media (prefers-color-scheme: dark) {
      background-color: rgba(15, 23, 42, 0.8);
      border-color: #334155;
      color: #e2e8f0;
      
      &:focus {
        border-color: #10b981;
        box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);
      }
      
      &:disabled {
        background-color: #1e293b;
      }
    }
  }
  
  .password-input-wrapper {
    position: relative;
    
    input {
      padding-right: 3rem;
    }
    
    .toggle-password {
      position: absolute;
      right: 0.75rem;
      top: 50%;
      transform: translateY(-50%);
      background: none;
      border: none;
      color: #64748b;
      cursor: pointer;
      transition: all 0.2s ease;
      padding: 0.25rem;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      
      &:hover {
        background-color: rgba(100, 116, 139, 0.1);
        color: #475569;
      }
      
      @media (prefers-color-scheme: dark) {
        color: #94a3b8;
        
        &:hover {
          background-color: rgba(148, 163, 184, 0.1);
          color: #cbd5e1;
        }
      }
    }
  }
}

.actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 0.5rem;
}

.login-button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  font-size: 1rem;
  font-weight: 600;
  border: none;
  border-radius: 8px;
  background: linear-gradient(to right, #047857, #10b981);
  color: white;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 
    0 4px 6px -1px rgba(16, 185, 129, 0.2),
    0 2px 4px -1px rgba(16, 185, 129, 0.1);
  width: 100%;
  position: relative;
  overflow: hidden;
  
  &:hover {
    transform: translateY(-2px);
    box-shadow: 
      0 10px 15px -3px rgba(16, 185, 129, 0.25),
      0 4px 6px -2px rgba(16, 185, 129, 0.1);
  }
  
  &:active {
    transform: translateY(0);
    box-shadow: 
      0 2px 4px -1px rgba(16, 185, 129, 0.2),
      0 1px 2px -1px rgba(16, 185, 129, 0.1);
  }
  
  &:disabled {
    background: linear-gradient(to right, #9ca3af, #d1d5db);
    cursor: not-allowed;
    transform: translateY(0);
    box-shadow: none;
  }
  
  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(255, 255, 255, 0.2),
      transparent
    );
    transition: left 0.7s ease;
  }
  
  &:not(:disabled):hover::before {
    left: 100%;
  }
}

.register-link {
  margin-top: 1.5rem;
  text-align: center;
  
  p {
    font-size: 0.9rem;
    color: #64748b;
    
    @media (prefers-color-scheme: dark) {
      color: #94a3b8;
    }
  }
  
  a {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    color: #10b981;
    font-weight: 600;
    text-decoration: none;
    transition: all 0.2s ease;
    
    &:hover {
      color: #047857;
      text-decoration: underline;
    }
  }
}

.spin {
  animation: spin 1.5s linear infinite;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from { 
    transform: translateY(30px) scale(0.95); 
    opacity: 0;
  }
  to { 
    transform: translateY(0) scale(1); 
    opacity: 1;
  }
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>