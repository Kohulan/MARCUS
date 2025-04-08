// store/modules/theme.js
export default {
  namespaced: true,
  
  state: {
    isDarkMode: false // Default to light mode
  },
  
  mutations: {
    SET_DARK_MODE(state, isDark) {
      state.isDarkMode = isDark;
    }
  },
  
  actions: {
    /**
     * Toggle between dark and light mode
     * @param {Object} context - Vuex action context
     */
    toggleDarkMode({ commit, state }) {
      // Block transitions temporarily to prevent flash
      document.documentElement.classList.add('theme-transition');
      
      // Toggle theme
      const newMode = !state.isDarkMode;
      commit('SET_DARK_MODE', newMode);
      
      // Set data-theme attribute on the document element (root)
      document.documentElement.setAttribute('data-theme', newMode ? 'dark' : 'light');
      
      // Store theme preference in localStorage
      localStorage.setItem('darkMode', newMode ? 'true' : 'false');
      
      // Remove transition blocker after theme change
      setTimeout(() => {
        document.documentElement.classList.remove('theme-transition');
      }, 100);
    },
    
    /**
     * Initialize theme based on user preference or system setting
     * @param {Object} context - Vuex action context
     */
    initTheme({ commit }) {
      // Check if user has a stored preference
      const storedTheme = localStorage.getItem('darkMode');
      let isDark;
      
      if (storedTheme !== null) {
        // Use stored preference
        isDark = storedTheme === 'true';
      } else {
        // Check system preference
        isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      }
      
      // Apply theme
      commit('SET_DARK_MODE', isDark);
      document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
      
      // Listen for system preference changes
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        // Only update if user has no stored preference
        if (localStorage.getItem('darkMode') === null) {
          const systemIsDark = e.matches;
          commit('SET_DARK_MODE', systemIsDark);
          document.documentElement.setAttribute('data-theme', systemIsDark ? 'dark' : 'light');
        }
      });
    }
  },
  
  getters: {
    isDarkMode: state => state.isDarkMode
  }
};