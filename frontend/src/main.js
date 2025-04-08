import { createApp } from 'vue'
import App from './App.vue'
import store from './store'
import './assets/styles/main.scss'

// Import third-party libraries
import VueFeather from 'vue-feather'

// Configure feature flags to avoid Vue warnings
if (import.meta?.env?.MODE === 'development') {
  window.__VUE_OPTIONS_API__ = true
  window.__VUE_PROD_DEVTOOLS__ = true
  window.__VUE_PROD_HYDRATION_MISMATCH_DETAILS__ = true
}

// Create app instance
const app = createApp(App)

// Register global components
app.component(VueFeather.name, VueFeather)

// Use store
app.use(store)

// Mount app
app.mount('#app')