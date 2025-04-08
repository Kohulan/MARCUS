import { createStore } from 'vuex'

import pdf from './modules/pdf'
import text from './modules/text'
import annotations from './modules/annotations'
import structures from './modules/structures'
import theme from './modules/theme'

export default createStore({
  modules: {
    pdf,
    text,
    annotations,
    structures,
    theme
  },
  state: {
    notifications: [],
    isDisclaimerVisible: false,
    isFeaturesVisible: false
  },
  mutations: {
    ADD_NOTIFICATION(state, notification) {
      const id = Date.now().toString()
      state.notifications.push({
        id,
        type: notification.type || 'info',
        message: notification.message,
        duration: notification.duration || 5000
      })
      
      // Auto-remove notification after duration
      if (notification.duration !== 0) {
        setTimeout(() => {
          this.commit('REMOVE_NOTIFICATION', id)
        }, notification.duration || 5000)
      }
    },
    REMOVE_NOTIFICATION(state, id) {
      state.notifications = state.notifications.filter(notification => notification.id !== id)
    },
    SHOW_DISCLAIMER(state) {
      state.isDisclaimerVisible = true;
      // Hide features when showing disclaimer
      state.isFeaturesVisible = false;
    },
    HIDE_DISCLAIMER(state) {
      state.isDisclaimerVisible = false;
    },
    TOGGLE_DISCLAIMER(state) {
      state.isDisclaimerVisible = !state.isDisclaimerVisible;
      // Hide features if showing disclaimer
      if (state.isDisclaimerVisible) {
        state.isFeaturesVisible = false;
      }
    },
    // Features-related mutations
    SHOW_FEATURES(state) {
      state.isFeaturesVisible = true;
      // Hide disclaimer when showing features
      state.isDisclaimerVisible = false;
    },
    HIDE_FEATURES(state) {
      state.isFeaturesVisible = false;
    },
    TOGGLE_FEATURES(state) {
      state.isFeaturesVisible = !state.isFeaturesVisible;
      // Hide disclaimer if showing features
      if (state.isFeaturesVisible) {
        state.isDisclaimerVisible = false;
      }
    }
  },
  actions: {
    showNotification({ commit }, notification) {
      commit('ADD_NOTIFICATION', notification)
    },
    removeNotification({ commit }, id) {
      commit('REMOVE_NOTIFICATION', id)
    },
    showDisclaimer({ commit }) {
      commit('SHOW_DISCLAIMER');
    },
    hideDisclaimer({ commit }) {
      commit('HIDE_DISCLAIMER');
    },
    toggleDisclaimer({ commit }) {
      commit('TOGGLE_DISCLAIMER');
    },
    // Features-related actions
    showFeatures({ commit }) {
      commit('SHOW_FEATURES');
    },
    hideFeatures({ commit }) {
      commit('HIDE_FEATURES');
    },
    toggleFeatures({ commit }) {
      commit('TOGGLE_FEATURES');
    },
    // Special actions for the OCSR module and other features - fixed to avoid unused parameter error
    showOcsrInfo({ dispatch }) {
      dispatch('showNotification', {
        type: 'info',
        message: 'OCSR (Optical Chemical Structure Recognition) extracts chemical structures from images using deep learning',
        duration: 8000
      });
    },
    showBatchInfo({ dispatch }) {
      dispatch('showNotification', {
        type: 'info',
        message: 'Batch processing allows you to process multiple documents and structures simultaneously',
        duration: 8000
      });
    }
  },
  getters: {
    isDisclaimerVisible: state => state.isDisclaimerVisible,
    isFeaturesVisible: state => state.isFeaturesVisible
  }
})