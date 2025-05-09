<template>
  <div v-if="visible" class="ketcher-modal-overlay">
    <div class="ketcher-modal">
      <div class="modal-header">
        <h3>Edit Structure</h3>
        <button class="close-btn" @click="$emit('close')">
          <span>&times;</span>
        </button>
      </div>
      <div class="modal-body">
        <iframe
          ref="ketcherFrame"
          :src="ketcherUrl"
          class="ketcher-iframe"
          @load="onKetcherLoad"
        ></iframe>
      </div>
      <div class="modal-footer">
        <button class="apply-btn" @click="applyEdits">Apply</button>
        <button class="cancel-btn" @click="$emit('close')">Cancel</button>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'KetcherEditorModal',
  props: {
    visible: { type: Boolean, default: false },
    initialSmiles: { type: String, default: '' },
    initialMolfile: { type: String, default: '' },
    ketcherPath: { type: String, default: '/ketcher/index.html' }
  },
  data() {
    return {
      ketcherLoaded: false
    }
  },
  computed: {
    ketcherUrl() {
      // Use a cache-busting param to ensure fresh load
      return this.ketcherPath + '?v=1.0';
    }
  },
  watch: {
    visible(val) {
      if (val) {
        this.ketcherLoaded = false;
      }
    }
  },
  methods: {
    onKetcherLoad() {
      this.ketcherLoaded = true;
      console.log('Ketcher iframe loaded, initial SMILES:', this.initialSmiles ? this.initialSmiles.substring(0, 30) + '...' : 'none');
      console.log('Initial molfile present:', !!this.initialMolfile);
      
      // Give Ketcher time to fully initialize
      setTimeout(() => {
        this.setStructure();
      }, 800);
    },
    
    setStructure() {
      const frame = this.$refs.ketcherFrame;
      if (!frame || !frame.contentWindow) {
        console.error('Ketcher iframe reference not available');
        return;
      }
      
      try {
        console.log('Setting structure in Ketcher');
        // Attempt to use Ketcher's API directly if available
        if (frame.contentWindow.ketcher) {
          console.log('Using direct Ketcher API');
          if (this.initialMolfile) {
            frame.contentWindow.ketcher.setMolecule(this.initialMolfile);
          } else if (this.initialSmiles) {
            frame.contentWindow.ketcher.setMolecule(this.initialSmiles);
          }
          return;
        }
        
        // Fall back to postMessage API
        if (this.initialMolfile) {
          frame.contentWindow.postMessage({
            type: 'ketcher:set-structure',
            payload: { molfile: this.initialMolfile }
          }, '*');
          console.log('Sent molfile to Ketcher via postMessage');
        } else if (this.initialSmiles) {
          frame.contentWindow.postMessage({
            type: 'ketcher:set-structure',
            payload: { smiles: this.initialSmiles }
          }, '*');
          console.log('Sent SMILES to Ketcher via postMessage');
        }
      } catch (error) {
        console.error('Error setting structure in Ketcher:', error);
      }
    },
    
    applyEdits() {
      const frame = this.$refs.ketcherFrame;
      if (!frame || !frame.contentWindow) {
        console.error('Ketcher iframe reference not available');
        return;
      }
      
      try {
        // Direct API approach (for standalone Ketcher)
        if (frame.contentWindow.ketcher) {
          console.log('Using direct Ketcher API to get structure');
          Promise.all([
            frame.contentWindow.ketcher.getSmiles(),
            frame.contentWindow.ketcher.getMolfile()
          ]).then(([smiles, molfile]) => {
            console.log('Got structure from Ketcher API:', smiles ? smiles.substring(0, 30) + '...' : 'none');
            const result = { smiles, molfile };
            this.$emit('apply', result);
          }).catch(error => {
            console.error('Error getting structure from Ketcher API:', error);
          });
          return;
        }
        
        // postMessage approach (for iframe communication)
        console.log('Using postMessage to get structure from Ketcher');
        // Create a response handler for Ketcher's reply
        const onMessage = (event) => {
          if (event.data && event.data.type === 'ketcher:structure') {
            console.log('Received structure from Ketcher:', event.data.payload);
            this.$emit('apply', event.data.payload);
            window.removeEventListener('message', onMessage);
          }
        };
        
        window.addEventListener('message', onMessage);
        
        // Request structure format that includes both SMILES and molfile
        frame.contentWindow.postMessage({ 
          type: 'ketcher:get-structure', 
          payload: { format: 'chemical' } 
        }, '*');
      } catch (error) {
        console.error('Error getting structure from Ketcher:', error);
      }
    },
    
    beforeDestroy() {
      // Clean up message listener when component is destroyed
      window.removeEventListener('message', this.handleKetcherMessages);
    }
  }
}
</script>

<style scoped>
.ketcher-modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.35);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ketcher-modal {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.18);
  width: 800px;
  max-width: 98vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem 0.5rem 1.5rem;
  border-bottom: 1px solid #eee;
}
.close-btn {
  background: none;
  border: none;
  font-size: 2rem;
  color: #888;
  cursor: pointer;
}
.modal-body {
  flex: 1;
  padding: 0;
  overflow: hidden;
}
.ketcher-iframe {
  width: 100%;
  height: 480px;
  border: none;
  background: #f8fafc;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid #eee;
}
.apply-btn {
  background: #4f46e5;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 0.5rem 1.25rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}
.apply-btn:hover {
  background: #4338ca;
}
.cancel-btn {
  background: #f3f4f6;
  color: #374151;
  border: none;
  border-radius: 8px;
  padding: 0.5rem 1.25rem;
  font-weight: 500;
  cursor: pointer;
}
</style>
