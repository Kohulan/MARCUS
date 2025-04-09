<template>
  <div class="ocsr-comparison">
    <div class="comparison-header">
      <h3 class="comparison-title">
        <vue-feather type="bar-chart-2" class="icon"></vue-feather>
        OCSR Engine Comparison
      </h3>
      <div class="original-segment">
        <span class="segment-label">Original Segment:</span>
        <img :src="segment.imageUrl" alt="Original segment" class="segment-image" />
      </div>
    </div>

    <div class="comparison-content" :class="{ 'is-loading': isLoading }">
      <div v-if="isLoading" class="loading-overlay">
        <div class="spinner"></div>
        <p>Processing with all engines...</p>
      </div>
      
      <div v-else-if="findingMCS" class="loading-overlay">
        <div class="spinner"></div>
        <p>Finding maximum common substructure...</p>
      </div>
      
      <div v-else class="comparison-grid">
        <div v-for="(result, index) in results" :key="index" class="comparison-item">
          <div class="engine-header" :class="engineClass(result.engine)">
            <vue-feather :type="engineIcon(result.engine)" class="engine-icon"></vue-feather>
            <h4 class="engine-title">{{ result.engine }}</h4>
          </div>
          
          <div class="result-content">
            <div v-if="result.error" class="error-message">
              <vue-feather type="alert-circle" class="error-icon"></vue-feather>
              <p>{{ result.error }}</p>
            </div>
            <div v-else>
              <improved-chemical-structure-viewer
                :smiles="result.smiles"
                :molfile="result.molfile"
                :name="segment.filename"
                :source-engine="result.engine"
                :use-coordinates="shouldUseCoordinates(result)"
                :highlight="mcsSmarts"
                class="structure-viewer"
              />
              
              <div class="result-details">
                <div class="detail-row">
                  <span class="detail-label">Processing Time:</span>
                  <span class="detail-value">{{ result.processingTime || 'N/A' }}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">SMILES Length:</span>
                  <span class="detail-value">{{ result.smiles ? result.smiles.length : 'N/A' }}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">Has Coordinates:</span>
                  <span class="detail-value">{{ result.molfile ? 'Yes' : 'No' }}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">Using Coordinates:</span>
                  <span class="detail-value">{{ shouldUseCoordinates(result) ? 'Yes' : 'No' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <div v-if="mcsResult" class="mcs-info">
      <div class="mcs-header">
        <h4>
          <vue-feather type="target" class="mcs-icon"></vue-feather>
          Maximum Common Substructure
        </h4>
        <button class="btn btn-icon" @click="clearMCS" title="Clear MCS Highlight">
          <vue-feather type="x"></vue-feather>
        </button>
      </div>
      <div class="mcs-stats">
        <div class="stat-item">
          <span class="stat-label">Atoms:</span>
          <span class="stat-value">{{ mcsResult.atom_count }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Bonds:</span>
          <span class="stat-value">{{ mcsResult.bond_count }}</span>
        </div>
      </div>
    </div>
    
    <div class="comparison-footer">
      <div class="comparison-options">
        <label class="checkbox-container">
          <input 
            type="checkbox" 
            v-model="useCoordinatesForDepiction"
            :disabled="isLoading"
          />
          <span class="checkmark"></span>
          <span class="checkbox-label">Use Coordinates for Depiction</span>
        </label>
      </div>
      
      <div class="action-buttons">
        <button 
          class="btn btn-highlight" 
          @click="findMCS" 
          :disabled="isLoading || findingMCS || !canFindMCS"
          v-tooltip="!canFindMCS ? 'Need at least 2 valid structures with molfiles' : ''"
        >
          <vue-feather type="target" class="btn-icon"></vue-feather>
          Highlight Common Structure
        </button>
        <button class="btn btn-secondary" @click="$emit('close')">
          <vue-feather type="x" class="btn-icon"></vue-feather>
          Close
        </button>
        <button class="btn btn-primary" @click="runComparison" :disabled="isLoading || findingMCS">
          <vue-feather type="refresh-cw" class="btn-icon"></vue-feather>
          {{ isLoading ? 'Processing...' : 'Run Comparison Again' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import ImprovedChemicalStructureViewer from './ImprovedChemicalStructureViewer.vue';
import ocsrService from '@/services/ocsrService';
import depictionService from '@/services/depictionService';
import similarityService from '@/services/similarityService';

export default {
  name: 'OCSRComparison',
  components: {
    ImprovedChemicalStructureViewer
  },
  props: {
    segment: {
      type: Object,
      required: true
    }
  },
  emits: ['close'],
  data() {
    return {
      isLoading: true,
      findingMCS: false,
      useCoordinatesForDepiction: true, // Default to using coordinates for better depiction
      results: [
        { engine: 'decimer', smiles: '', molfile: null, error: null, processingTime: null, useCoordinates: false },
        { engine: 'molnextr', smiles: '', molfile: null, error: null, processingTime: null, useCoordinates: true },
        { engine: 'molscribe', smiles: '', molfile: null, error: null, processingTime: null, useCoordinates: true }
      ],
      mcsResult: null,
      mcsSmarts: '',
      mcsError: null
    };
  },
  computed: {
    canFindMCS() {
      // Need at least two valid results with either molfiles or SMILES to find MCS
      const validResults = this.results.filter(r => 
        (!r.error) && (r.molfile || r.smiles)
      );
      return validResults.length >= 2;
    }
  },
  mounted() {
    this.runComparison();
  },
  methods: {
    engineClass(engine) {
      return {
        'decimer-engine': engine === 'decimer',
        'molnextr-engine': engine === 'molnextr',
        'molscribe-engine': engine === 'molscribe'
      };
    },
    engineIcon(engine) {
      if (engine === 'decimer') return 'cpu';
      if (engine === 'molnextr') return 'grid';
      if (engine === 'molscribe') return 'edit-3';
      return 'box';
    },
    shouldUseCoordinates(result) {
      // Don't use coordinates for DECIMER (it doesn't provide any)
      if (result.engine === 'decimer') {
        return false;
      }
      
      // Otherwise, use coordinates if:
      // 1. We have a molfile
      // 2. The global useCoordinatesForDepiction flag is true
      return this.useCoordinatesForDepiction && !!result.molfile;
    },
    async findMCS() {
      if (this.findingMCS || !this.canFindMCS) return;
      
      this.findingMCS = true;
      this.mcsError = null;
      
      try {
        // Collect valid molfiles and their engine names
        const molfiles = [];
        const engineNames = [];
        
        // First pass: collect all results with direct molfiles
        const hasValidMolfiles = this.results.filter(result => 
          result.molfile && !result.error
        ).length >= 2;
        
        // If we don't have at least 2 valid molfiles, but we have valid SMILES,
        // convert SMILES to molfiles using the depiction service first
        if (!hasValidMolfiles) {
          // Generate molfiles for engines that only provide SMILES (like DECIMER)
          for (const result of this.results) {
            if (!result.error && result.smiles && !result.molfile) {
              try {
                console.log(`Converting SMILES to molfile for ${result.engine}...`);
                
                // Call the depiction service to generate a molfile from SMILES
                const response = await depictionService.generateMolfileFromSmiles(result.smiles);
                
                if (response && response.molfile) {
                  // Store the generated molfile
                  result.molfile = response.molfile;
                  console.log(`Successfully generated molfile for ${result.engine}`);
                }
              } catch (error) {
                console.error(`Error generating molfile for ${result.engine}:`, error);
              }
            }
          }
        }
        
        // Now collect all valid molfiles after conversion
        this.results.forEach(result => {
          if (result.molfile && !result.error) {
            molfiles.push(result.molfile);
            engineNames.push(result.engine);
          }
        });
        
        if (molfiles.length < 2) {
          throw new Error('Need at least 2 valid structures to find maximum common substructure');
        }
        
        // Call the MCS service
        const result = await similarityService.findMCS(molfiles, engineNames);
        this.mcsResult = result;
        this.mcsSmarts = result.mcs_smarts;
        
        // Update all the viewers with the new highlight
        await this.regenerateDepictionsWithHighlight();
        
      } catch (error) {
        console.error('Error finding MCS:', error);
        this.mcsError = error.message || 'Failed to find maximum common substructure';
        this.mcsResult = null;
        this.mcsSmarts = '';
      } finally {
        this.findingMCS = false;
      }
    },
    clearMCS() {
      this.mcsResult = null;
      this.mcsSmarts = '';
      this.mcsError = null;
      // Regenerate depictions without highlight
      this.regenerateDepictionsWithHighlight();
    },
    async regenerateDepictionsWithHighlight() {
      // Regenerate all depictions with the current highlight status
      try {
        for (let i = 0; i < this.results.length; i++) {
          const result = this.results[i];
          if (result.error || (!result.smiles && !result.molfile)) continue;
          
          const useCoords = this.shouldUseCoordinates(result);
          
          const depictionOptions = {
            engine: 'cdk', // Always use CDK for depiction
            smiles: result.smiles,
            molfile: useCoords ? result.molfile : null,
            useMolfileDirectly: useCoords,
            format: 'svg',
            highlight: this.mcsSmarts // Apply the highlight if we have one
          };
          
          const svg = await depictionService.generateDepiction(depictionOptions);
          this.results[i].svg = svg;
        }
      } catch (error) {
        console.error('Error regenerating depictions:', error);
      }
    },
    async runComparison() {
      if (this.isLoading) return;
      
      this.isLoading = true;
      
      // Clear any previous MCS result
      this.mcsResult = null;
      this.mcsSmarts = '';
      this.mcsError = null;
      
      // Reset results
      this.results.forEach(result => {
        result.smiles = '';
        result.molfile = null;
        result.error = null;
        result.processingTime = null;
        // Set default useCoordinates based on engine
        result.useCoordinates = result.engine !== 'decimer';
      });
      
      try {
        // Process segment with all three engines in parallel
        const engines = ['decimer', 'molnextr', 'molscribe'];
        const processPromises = engines.map(engine => this.processWithEngine(engine));
        
        await Promise.all(processPromises);
      } catch (error) {
        console.error('Error during comparison:', error);
      } finally {
        this.isLoading = false;
      }
    },
    async processWithEngine(engine) {
      const resultIndex = this.results.findIndex(r => r.engine === engine);
      if (resultIndex === -1) return;
      
      const startTime = performance.now();
      
      try {
        // Determine image path format
        const segmentsDirectory = this.segment.path?.split('/all_segments/')[0];
        const imagePath = segmentsDirectory ? 
          `${segmentsDirectory}/all_segments/${this.segment.filename}` : 
          this.segment.filename;
        
        console.log(`Processing segment with ${engine} engine: ${imagePath}`);
        
        // Always include molfile for MolNexTR and MolScribe for comparison purposes
        const includeMolfile = engine !== 'decimer';
        
        // Process the segment using ocsrService
        const options = {
          engine: engine,
          handDrawn: engine === 'decimer' ? false : undefined,
          includeMolfile: includeMolfile,
          depictEngine: 'rdkit', // Use RDKit for immediate visualization
          depictFormat: 'svg'
        };
        
        let response;
        try {
          // Try with the full path first
          response = await ocsrService.generateWithDepiction(null, imagePath, options);
        } catch (apiError) {
          console.warn(`Error with full path, trying fallback with filename: ${this.segment.filename}`);
          
          // Try with just the filename as fallback
          response = await ocsrService.generateWithDepiction(null, this.segment.filename, options);
        }
        
        // Generate better depiction using CDK for more consistent comparison
        let svg = null;
        try {
          // Use the appropriate input based on settings
          const useCoords = engine !== 'decimer' && this.useCoordinatesForDepiction;
          
          const depictionOptions = {
            engine: 'cdk', // Always use CDK for depiction
            smiles: response.smiles,
            molfile: useCoords ? response.molfile : null,
            useMolfileDirectly: useCoords,
            format: 'svg',
            highlight: this.mcsSmarts // Apply highlight if we have one
          };
          
          // Only create a new depiction if we have the necessary input
          if (response.smiles || (useCoords && response.molfile)) {
            const svgResponse = await depictionService.generateDepiction(depictionOptions);
            svg = svgResponse;
          }
        } catch (depError) {
          console.error(`Error generating depiction for ${engine}:`, depError);
          // Fall back to the depiction from the response if available
          if (response.depiction && response.depiction.svg) {
            svg = response.depiction.svg;
          }
        }
        
        // Update the result
        const endTime = performance.now();
        const processingTime = ((endTime - startTime) / 1000).toFixed(2) + 's';
        
        this.results[resultIndex].smiles = response.smiles || '';
        this.results[resultIndex].molfile = response.molfile || null;
        this.results[resultIndex].svg = svg;
        this.results[resultIndex].processingTime = processingTime;
        this.results[resultIndex].error = null;
        this.results[resultIndex].useCoordinates = engine !== 'decimer' && this.useCoordinatesForDepiction;
      } catch (error) {
        console.error(`Error processing with ${engine}:`, error);
        
        // Update with error
        const endTime = performance.now();
        const processingTime = ((endTime - startTime) / 1000).toFixed(2) + 's';
        
        this.results[resultIndex].processingTime = processingTime;
        this.results[resultIndex].error = error.message || `Failed to process with ${engine}`;
      }
    }
  },
  watch: {
    useCoordinatesForDepiction(newValue) {
      // Update the useCoordinates property of each result when the global setting changes
      this.results.forEach(result => {
        // Only change for MolNexTR and MolScribe
        if (result.engine !== 'decimer') {
          result.useCoordinates = newValue;
        }
      });
      
      // If we had an MCS result, regenerate the depictions with the highlight
      if (this.mcsSmarts) {
        this.regenerateDepictionsWithHighlight();
      }
    }
  }
};
</script>

<style lang="scss" scoped>
.ocsr-comparison {
  width: 100%;
  display: flex;
  flex-direction: column;
  height: 100%;
  
  .comparison-header {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--color-border);
    
    .comparison-title {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin: 0;
      font-size: 1.25rem;
      
      .icon {
        color: var(--color-primary);
      }
    }
    
    .original-segment {
      display: flex;
      align-items: center;
      gap: 1rem;
      
      .segment-label {
        font-weight: 500;
      }
      
      .segment-image {
        max-height: 80px;
        max-width: 120px;
        object-fit: contain;
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        padding: 0.25rem;
        background: white;
      }
    }
  }
  
  .comparison-content {
    flex: 1;
    position: relative;
    padding: 1rem 0;
    overflow-y: auto;
    
    &.is-loading {
      min-height: 200px;
    }
    
    .loading-overlay {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background-color: rgba(255, 255, 255, 0.8);
      z-index: 10;
      
      .spinner {
        width: 48px;
        height: 48px;
        border: 4px solid var(--color-primary);
        border-top-color: transparent;
        border-radius: 50%;
        animation: spinner 1s linear infinite;
        margin-bottom: 1rem;
      }
      
      p {
        font-size: 1rem;
        color: var(--color-text);
      }
    }
    
    .comparison-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 1.5rem;
      
      @media (min-width: 768px) {
        grid-template-columns: repeat(2, 1fr);
      }
      
      @media (min-width: 1200px) {
        grid-template-columns: repeat(3, 1fr);
      }
    }
    
    .comparison-item {
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      overflow: hidden;
      
      .engine-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.75rem;
        
        &.decimer-engine {
          background-color: rgba(255, 149, 0, 0.1);
          
          .engine-icon {
            color: #ff9500;
          }
        }
        
        &.molnextr-engine {
          background-color: rgba(0, 122, 255, 0.1);
          
          .engine-icon {
            color: #007aff;
          }
        }
        
        &.molscribe-engine {
          background-color: rgba(175, 82, 222, 0.1);
          
          .engine-icon {
            color: #af52de;
          }
        }
        
        .engine-title {
          margin: 0;
          font-size: 1rem;
          font-weight: 600;
        }
      }
      
      .result-content {
        padding: 1rem;
        
        .error-message {
          display: flex;
          align-items: flex-start;
          gap: 0.5rem;
          color: var(--color-error);
          
          .error-icon {
            flex-shrink: 0;
            margin-top: 0.125rem;
          }
          
          p {
            margin: 0;
          }
        }
        
        .structure-viewer {
          margin-bottom: 1rem;
        }
        
        .result-details {
          border-top: 1px solid var(--color-border-light);
          padding-top: 0.75rem;
          
          .detail-row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 0.5rem;
            font-size: 0.875rem;
            
            .detail-label {
              color: var(--color-text-light);
            }
            
            .detail-value {
              font-weight: 500;
            }
          }
        }
      }
    }
  }
  
  .mcs-info {
    margin-top: 1rem;
    padding: 1rem;
    background-color: rgba(0, 122, 255, 0.05);
    border: 1px solid rgba(0, 122, 255, 0.2);
    border-radius: var(--radius-md);
    
    .mcs-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.5rem;
      
      h4 {
        margin: 0;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 1rem;
        
        .mcs-icon {
          color: #007aff;
        }
      }
      
      .btn-icon {
        padding: 0.25rem;
        background: transparent;
        border: none;
        cursor: pointer;
        color: var(--color-text-light);
        border-radius: 50%;
        transition: all 0.2s ease;
        
        &:hover {
          background-color: rgba(0, 0, 0, 0.05);
          color: var(--color-text);
        }
      }
    }
    
    .mcs-stats {
      display: flex;
      gap: 1rem;
      
      .stat-item {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        
        .stat-label {
          font-size: 0.875rem;
          color: var(--color-text-light);
        }
        
        .stat-value {
          font-weight: 600;
          font-size: 0.875rem;
        }
      }
    }
  }
  
  .comparison-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--color-border);
    
    .comparison-options {
      .checkbox-container {
        display: flex;
        align-items: center;
        position: relative;
        padding-left: 28px;
        cursor: pointer;
        user-select: none;
        
        input {
          position: absolute;
          opacity: 0;
          cursor: pointer;
          height: 0;
          width: 0;
          
          &:checked ~ .checkmark {
            background-color: var(--color-primary);
            border-color: var(--color-primary);
            
            &:after {
              display: block;
            }
          }
          
          &:disabled ~ .checkmark,
          &:disabled ~ .checkbox-label {
            opacity: 0.6;
            cursor: not-allowed;
          }
        }
        
        .checkmark {
          position: absolute;
          top: 0;
          left: 0;
          height: 18px;
          width: 18px;
          background-color: var(--color-card-bg);
          border: 1px solid var(--color-border);
          border-radius: 4px;
          transition: all 0.2s ease;
          
          &:after {
            content: "";
            position: absolute;
            display: none;
            left: 5px;
            top: 2px;
            width: 5px;
            height: 9px;
            border: solid white;
            border-width: 0 2px 2px 0;
            transform: rotate(45deg);
          }
        }
        
        &:hover input:not(:disabled) ~ .checkmark {
          border-color: var(--color-primary-light);
        }
        
        .checkbox-label {
          font-size: 0.875rem;
          color: var(--color-text);
          cursor: pointer;
          user-select: none;
        }
      }
    }
    
    .action-buttons {
      display: flex;
      gap: 1rem;
    }
    
    .btn {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 1rem;
      border-radius: var(--radius-md);
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
      
      .btn-icon {
        width: 16px;
        height: 16px;
      }
      
      &.btn-primary {
        background-color: var(--color-primary);
        color: white;
        border: none;
        
        &:hover:not(:disabled) {
          background-color: var(--color-primary-dark);
        }
        
        &:disabled {
          opacity: 0.7;
          cursor: not-allowed;
        }
      }
      
      &.btn-secondary {
        background-color: transparent;
        color: var(--color-text);
        border: 1px solid var(--color-border);
        
        &:hover {
          background-color: var(--color-card-bg);
          border-color: var(--color-text-light);
        }
      }
      
      &.btn-highlight {
        background-color: #007aff;
        color: white;
        border: none;
        
        &:hover:not(:disabled) {
          background-color: #0062cc;
        }
        
        &:disabled {
          opacity: 0.7;
          cursor: not-allowed;
        }
      }
    }
  }
  
  @media (max-width: 768px) {
    .comparison-footer {
      flex-direction: column;
      gap: 1rem;
      
      .comparison-options {
        width: 100%;
      }
      
      .action-buttons {
        width: 100%;
        justify-content: flex-end;
        flex-wrap: wrap;
      }
    }
  }
}

@keyframes spinner {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>