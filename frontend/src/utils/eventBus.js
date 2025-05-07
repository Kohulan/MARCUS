import { reactive } from 'vue'

export const state = reactive({
  selectedSegment: null,
})

class EventBus {
  constructor() {
    this.events = {}
  }

  on(eventName, callback) {
    if (!this.events[eventName]) {
      this.events[eventName] = []
    }
    this.events[eventName].push(callback)
  }

  off(eventName, callback) {
    if (this.events[eventName]) {
      this.events[eventName] = this.events[eventName].filter(cb => cb !== callback)
    }
  }

  emit(eventName, data) {
    if (this.events[eventName]) {
      this.events[eventName].forEach(callback => {
        callback(data)
      })
    }
  }
}

export default new EventBus()