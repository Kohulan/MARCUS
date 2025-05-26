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
    isFeaturesVisible: false,
    isAboutVisible: false,
    isPrivacyPolicyVisible: false
  },
  mutations: {
    ADD_NOTIFICATION(state, notification) {
      const id = Date.now().toString()
      state.notifications.push({
        id,
        ...notification,
      })
      
      // Auto-remove notification after 5 seconds
      setTimeout(() => {
        this.commit('REMOVE_NOTIFICATION', id)
      }, 5000)
    },
    REMOVE_NOTIFICATION(state, id) {
      state.notifications = state.notifications.filter(notification => notification.id !== id)
    },
    SHOW_DISCLAIMER(state) {
      state.isDisclaimerVisible = true
      state.isFeaturesVisible = false
      state.isAboutVisible = false
      state.isPrivacyPolicyVisible = false
    },
    HIDE_DISCLAIMER(state) {
      state.isDisclaimerVisible = false
    },
    TOGGLE_DISCLAIMER(state) {
      state.isDisclaimerVisible = !state.isDisclaimerVisible
      if (state.isDisclaimerVisible) {
        state.isFeaturesVisible = false
        state.isAboutVisible = false
        state.isPrivacyPolicyVisible = false
      }
    },
    // Features-related mutations
    SHOW_FEATURES(state) {
      state.isFeaturesVisible = true
      state.isDisclaimerVisible = false
      state.isAboutVisible = false
      state.isPrivacyPolicyVisible = false
    },
    HIDE_FEATURES(state) {
      state.isFeaturesVisible = false
    },
    TOGGLE_FEATURES(state) {
      state.isFeaturesVisible = !state.isFeaturesVisible
      if (state.isFeaturesVisible) {
        state.isDisclaimerVisible = false
        state.isAboutVisible = false
        state.isPrivacyPolicyVisible = false
      }
    },
    // About-related mutations
    SHOW_ABOUT(state) {
      state.isAboutVisible = true
      state.isDisclaimerVisible = false
      state.isFeaturesVisible = false
      state.isPrivacyPolicyVisible = false
    },
    HIDE_ABOUT(state) {
      state.isAboutVisible = false
    },
    TOGGLE_ABOUT(state) {
      state.isAboutVisible = !state.isAboutVisible
      if (state.isAboutVisible) {
        state.isDisclaimerVisible = false
        state.isFeaturesVisible = false
        state.isPrivacyPolicyVisible = false
      }
    },
    // Privacy Policy-related mutations
    SHOW_PRIVACY_POLICY(state) {
      state.isPrivacyPolicyVisible = true
      state.isDisclaimerVisible = false
      state.isFeaturesVisible = false
      state.isAboutVisible = false
    },
    HIDE_PRIVACY_POLICY(state) {
      state.isPrivacyPolicyVisible = false
    },
    TOGGLE_PRIVACY_POLICY(state) {
      state.isPrivacyPolicyVisible = !state.isPrivacyPolicyVisible
      if (state.isPrivacyPolicyVisible) {
        state.isDisclaimerVisible = false
        state.isFeaturesVisible = false
        state.isAboutVisible = false
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
      commit('SHOW_DISCLAIMER')
    },
    hideDisclaimer({ commit }) {
      commit('HIDE_DISCLAIMER')
    },
    toggleDisclaimer({ commit }) {
      commit('TOGGLE_DISCLAIMER')
    },
    // Features-related actions
    showFeatures({ commit }) {
      commit('SHOW_FEATURES')
    },
    hideFeatures({ commit }) {
      commit('HIDE_FEATURES')
    },
    toggleFeatures({ commit }) {
      commit('TOGGLE_FEATURES')
    },
    // About-related actions
    showAbout({ commit }) {
      commit('SHOW_ABOUT')
    },
    hideAbout({ commit }) {
      commit('HIDE_ABOUT')
    },
    toggleAbout({ commit }) {
      commit('TOGGLE_ABOUT')
    },
    // Privacy Policy-related actions
    showPrivacyPolicy({ commit }) {
      commit('SHOW_PRIVACY_POLICY')
    },
    hidePrivacyPolicy({ commit }) {
      commit('HIDE_PRIVACY_POLICY')
    },
    togglePrivacyPolicy({ commit }) {
      commit('TOGGLE_PRIVACY_POLICY')
    }
  }
})