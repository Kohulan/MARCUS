<template>
    <div class="similarity-comparison">
      <div v-if="isLoading" class="loading-container">
        <div class="spinner"></div>
        <p>Calculating similarities...</p>
      </div>
      
      <div v-else-if="error" class="error-container">
        <ErrorMessage 
          :message="error"
          title="Comparison Error"
          type="error"
        />
      </div>
      
      <div v-else-if="comparisonResult" class="comparison-results">
        <!-- Identical SMILES notice -->
        <div v-if="comparisonResult.identical" class="identical-notice">
          <div class="identical-icon">
            <vue-feather type="check-circle" class="icon success-icon"></vue-feather>
          </div>
          <div class="identical-text">
            <h4>Perfect Match</h4>
            <p>All OCSR engines generated identical SMILES strings.</p>
          </div>
        </div>
        
        <!-- Agreement Summary -->
        <div class="agreement-summary">
          <h4 class="section-title">Agreement Summary</h4>
          <div v-if="!comparisonResult.identical" class="agreement-stats">
            <div class="agreement-stat">
              <div class="stat-value">
                {{ formatPercentage(comparisonResult.agreement_summary.agreement_percentage) }}
              </div>
              <div class="stat-label">Agreement</div>
            </div>
            
            <div class="agreement-stat">
              <div class="stat-value">
                {{ comparisonResult.agreement_summary.total_agreements }} / {{ comparisonResult.agreement_summary.total_comparisons }}
              </div>
              <div class="stat-label">Matching Pairs</div>
            </div>
          </div>
        </div>
        
        <!-- SMILES Comparison Table -->
        <div class="smiles-table">
          <h4 class="section-title">SMILES Comparison</h4>
          <table>
            <thead>
              <tr>
                <th>Engine</th>
                <th>SMILES</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(engine, index) in comparisonResult.engine_names" :key="index">
                <td class="engine-name">{{ formatEngineName(engine) }}</td>
                <td class="smiles-cell">
                  <div class="smiles-text">{{ getSmilesForEngine(index) }}</div>
                </td>
                <td class="status-cell">
                  <span 
                    class="status-badge"
                    :class="isValidSmiles(index) ? 'valid' : 'invalid'"
                  >
                    {{ isValidSmiles(index) ? 'Valid' : 'Invalid' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        
        <!-- Similarity Matrix -->
        <div v-if="!comparisonResult.identical && shouldShowMatrix" class="similarity-matrix">
          <h4 class="section-title">Similarity Matrix (Tanimoto / ECFP4)</h4>
          <table>
            <thead>
              <tr>
                <th></th>
                <th v-for="(engine, index) in comparisonResult.engine_names" :key="'header-'+index">
                  {{ formatEngineName(engine) }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(engine, rowIndex) in comparisonResult.engine_names" :key="'row-'+rowIndex">
                <th>{{ formatEngineName(engine) }}</th>
                <td 
                  v-for="(similarity, colIndex) in comparisonResult.matrix[rowIndex]" 
                  :key="'cell-'+rowIndex+'-'+colIndex"
                  :class="getCellClass(similarity, rowIndex, colIndex)"
                >
                  {{ formatSimilarity(similarity) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        
        <!-- Pair Details -->
        <div v-if="!comparisonResult.identical && hasPairAgreements" class="pair-details">
          <h4 class="section-title">Pair Details</h4>
          <div class="pair-list">
            <div 
              v-for="(pair, index) in pairAgreements" 
              :key="'pair-'+index"
              class="pair-item"
              :class="pair.agrees ? 'agrees' : 'disagrees'"
            >
              <vue-feather 
                :type="pair.agrees ? 'check' : 'x'" 
                class="icon"
                :class="pair.agrees ? 'success-icon' : 'error-icon'"
              ></vue-feather>
              <span>
                <strong>{{ formatEngineName(pair.engine1) }}</strong> and 
                <strong>{{ formatEngineName(pair.engine2) }}</strong>
                {{ pair.agrees ? 'agree' : 'disagree' }}
              </span>
            </div>
          </div>
        </div>
        
        <!-- Invalid SMILES Warning -->
        <div v-if="hasInvalidSmiles" class="invalid-smiles-warning">
          <ErrorMessage 
            :message="invalidSmilesMessage"
            title="Invalid SMILES Detected"
            type="warning"
          />
        </div>
      </div>
      
      <!-- No data available -->
      <div v-else class="no-data">
        <p>No comparison data available.</p>
      </div>
    </div>
  </template>
  
  <script>
  import ErrorMessage from './ErrorMessage.vue'
  
  export default {
    name: 'SimilarityComparison',
    components: {
      ErrorMessage
    },
    props: {
      comparisonResult: {
        type: Object,
        default: null
      },
      isLoading: {
        type: Boolean,
        default: false
      },
      error: {
        type: String,
        default: ''
      },
      originalSmilesList: {
        type: Array,
        default: () => []
      }
    },
    computed: {
      // Check if we should show the matrix (only if we have valid engines)
      shouldShowMatrix() {
        return this.comparisonResult && 
               this.comparisonResult.matrix && 
               this.comparisonResult.matrix.length > 1;
      },
      
      // Process pair agreements into a more usable format
      pairAgreements() {
        if (!this.comparisonResult || 
            !this.comparisonResult.agreement_summary || 
            !this.comparisonResult.agreement_summary.pair_agreements) {
          return [];
        }
        
        const pairAgreements = this.comparisonResult.agreement_summary.pair_agreements;
        return Object.entries(pairAgreements).map(([pairKey, agrees]) => {
          const [engine1, engine2] = pairKey.split('-');
          return { engine1, engine2, agrees };
        });
      },
      
      // Check if we have any pair agreements
      hasPairAgreements() {
        return this.pairAgreements.length > 0;
      },
      
      // Check if there are any invalid SMILES
      hasInvalidSmiles() {
        return this.comparisonResult && 
               this.comparisonResult.agreement_summary && 
               this.comparisonResult.agreement_summary.invalid_smiles && 
               this.comparisonResult.agreement_summary.invalid_smiles.length > 0;
      },
      
      // Message for invalid SMILES
      invalidSmilesMessage() {
        if (!this.hasInvalidSmiles) return '';
        
        const invalidCount = this.comparisonResult.agreement_summary.invalid_smiles.length;
        const invalidEngines = this.comparisonResult.agreement_summary.invalid_smiles
          .map(item => item.engine)
          .map(this.formatEngineName)
          .join(', ');
        
        return `${invalidCount} engine${invalidCount > 1 ? 's' : ''} produced invalid SMILES: ${invalidEngines}`;
      }
    },
    methods: {
      // Format engine name for display
      formatEngineName(engine) {
        if (!engine) return '';
        
        const engineMap = {
          'decimer': 'DECIMER',
          'molnextr': 'MolNexTR',
          'molscribe': 'MolScribe'
        };
        
        return engineMap[engine.toLowerCase()] || engine;
      },
      
      // Get the cell CSS class based on similarity value
      getCellClass(similarity, rowIndex, colIndex) {
        if (rowIndex === colIndex) return 'self-similarity';
        
        if (similarity > 0.99) return 'high-similarity';
        if (similarity > 0.8) return 'medium-similarity';
        if (similarity > 0.5) return 'low-similarity';
        return 'very-low-similarity';
      },
      
      // Format similarity value for display
      formatSimilarity(value) {
        if (value === 1) return '1.00';
        return value.toFixed(2);
      },
      
      // Format percentage for display
      formatPercentage(value) {
        if (value === 100) return '100%';
        return `${value.toFixed(1)}%`;
      },
      
      // Check if a SMILES is valid
      isValidSmiles(engineIndex) {
        if (!this.comparisonResult || 
            !this.comparisonResult.agreement_summary || 
            !this.comparisonResult.agreement_summary.invalid_smiles) {
          return true;
        }
        
        const engineName = this.comparisonResult.engine_names[engineIndex];
        return !this.comparisonResult.agreement_summary.invalid_smiles
          .some(item => item.engine === engineName);
      },
      
      // Get SMILES for an engine (by index)
      getSmilesForEngine(engineIndex) {
        if (!this.comparisonResult || 
            !this.comparisonResult.engine_names || 
            engineIndex >= this.comparisonResult.engine_names.length) {
          return '';
        }
        
        const engineName = this.comparisonResult.engine_names[engineIndex];
        const invalidEngine = this.comparisonResult.agreement_summary.invalid_smiles.find(
          item => item.engine === engineName
        );
        
        if (invalidEngine) {
          return invalidEngine.smiles || '';
        }
        
        // For valid SMILES, find the correct index in the smiles list 
        // based on the engines that were valid
        const validEngines = this.comparisonResult.engine_names.filter(
          engine => !this.comparisonResult.agreement_summary.invalid_smiles.some(
            item => item.engine === engine
          )
        );
        
        const indexInValid = validEngines.indexOf(engineName);
        if (indexInValid !== -1 && indexInValid < this.originalSmilesList.length) {
          return this.originalSmilesList[indexInValid];
        }
        
        return '';
      }
    }
  }
  </script>
  
  <style lang="scss" scoped>
  .similarity-comparison {
    padding: 1rem;
    
    .section-title {
      font-size: 1.1rem;
      font-weight: 600;
      margin-bottom: 0.75rem;
      color: var(--color-text);
    }
    
    .loading-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 2rem;
      
      .spinner {
        width: 40px;
        height: 40px;
        border: 3px solid rgba(var(--color-primary-rgb), 0.3);
        border-radius: 50%;
        border-top-color: var(--color-primary);
        animation: spin 1s linear infinite;
        margin-bottom: 1rem;
      }
      
      p {
        color: var(--color-text-light);
      }
    }
    
    .error-container, .no-data {
      padding: 1rem;
    }
    
    .comparison-results {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }
    
    .identical-notice {
      display: flex;
      align-items: center;
      gap: 1rem;
      background-color: rgba(0, 200, 83, 0.1);
      border-radius: 8px;
      padding: 1rem;
      border-left: 4px solid var(--color-success);
      
      .identical-icon {
        color: var(--color-success);
        
        .icon {
          width: 32px;
          height: 32px;
        }
      }
      
      .identical-text {
        h4 {
          font-size: 1.1rem;
          margin-bottom: 0.25rem;
          color: var(--color-success);
        }
        
        p {
          margin: 0;
          color: var(--color-text);
        }
      }
    }
    
    .agreement-summary {
      background-color: var(--color-card-bg);
      border-radius: 8px;
      padding: 1rem;
      box-shadow: var(--shadow-sm);
      
      .agreement-stats {
        display: flex;
        align-items: center;
        justify-content: space-around;
        gap: 1rem;
        
        .agreement-stat {
          text-align: center;
          
          .stat-value {
            font-size: 1.75rem;
            font-weight: 700;
            color: var(--color-primary);
          }
          
          .stat-label {
            font-size: 0.875rem;
            color: var(--color-text-light);
          }
        }
      }
    }
    
    .smiles-table, .similarity-matrix {
      background-color: var(--color-card-bg);
      border-radius: 8px;
      padding: 1rem;
      box-shadow: var(--shadow-sm);
      overflow-x: auto;
      
      table {
        width: 100%;
        border-collapse: collapse;
        min-width: 500px;
        
        th, td {
          padding: 0.75rem 0.5rem;
          text-align: left;
          border-bottom: 1px solid var(--color-border);
        }
        
        th {
          font-weight: 600;
          color: var(--color-text);
          font-size: 0.9rem;
        }
        
        td {
          color: var(--color-text-light);
          font-size: 0.875rem;
        }
        
        tbody tr:last-child th,
        tbody tr:last-child td {
          border-bottom: none;
        }
        
        .engine-name {
          font-weight: 600;
          color: var(--color-text);
        }
        
        .smiles-cell {
          max-width: 350px;
          
          .smiles-text {
            font-family: monospace;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }
        }
        
        .status-cell {
          text-align: center;
          
          .status-badge {
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            
            &.valid {
              background-color: rgba(0, 200, 83, 0.1);
              color: var(--color-success);
            }
            
            &.invalid {
              background-color: rgba(255, 61, 113, 0.1);
              color: var(--color-error);
            }
          }
        }
        
        .self-similarity {
          background-color: rgba(var(--color-primary-rgb), 0.1);
          color: var(--color-primary);
          font-weight: 600;
        }
        
        .high-similarity {
          background-color: rgba(0, 200, 83, 0.15);
          color: var(--color-success);
          font-weight: 600;
        }
        
        .medium-similarity {
          background-color: rgba(0, 149, 255, 0.15);
          color: var(--color-info);
        }
        
        .low-similarity {
          background-color: rgba(255, 171, 0, 0.15);
          color: var(--color-warning);
        }
        
        .very-low-similarity {
          background-color: rgba(255, 61, 113, 0.15);
          color: var(--color-error);
        }
      }
    }
    
    .pair-details {
      background-color: var(--color-card-bg);
      border-radius: 8px;
      padding: 1rem;
      box-shadow: var(--shadow-sm);
      
      .pair-list {
        display: grid;
        grid-template-columns: 1fr;
        gap: 0.75rem;
        
        @media (min-width: 640px) {
          grid-template-columns: repeat(2, 1fr);
        }
        
        .pair-item {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.75rem;
          border-radius: 6px;
          
          &.agrees {
            background-color: rgba(0, 200, 83, 0.1);
            
            .icon {
              color: var(--color-success);
            }
          }
          
          &.disagrees {
            background-color: rgba(255, 61, 113, 0.1);
            
            .icon {
              color: var(--color-error);
            }
          }
          
          .icon {
            width: 18px;
            height: 18px;
          }
          
          span {
            font-size: 0.875rem;
            color: var(--color-text);
          }
        }
      }
    }
    
    .invalid-smiles-warning {
      margin-top: 1rem;
    }
  }
  
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  </style>