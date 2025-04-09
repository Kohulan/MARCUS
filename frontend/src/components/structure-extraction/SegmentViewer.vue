<template>
  <div class="segment-viewer" :class="{ 'fullscreen-mode': isFullscreen }">
    <div v-if="!segment" class="empty-state">
      <vue-feather type="image" size="32" class="empty-icon"></vue-feather>
      <p>No segment selected</p>
    </div>

    <div v-else class="segment-content">
      <div v-if="!comparisonMode" class="normal-view">
        <div class="segment-header">
          <h3 class="segment-title">Segment #{{ segmentNumber }}</h3>
          <div class="segment-actions">
            <button class="btn-action btn-context" @click="showInContext" title="View in PDF context">
              <vue-feather type="file-text" size="16"></vue-feather>
            </button>
            <button class="btn-action btn-close" @click="$emit('close')" title="Close">
              <vue-feather type="x" size="16"></vue-feather>
            </button>
          </div>
        </div>

        <div class="section-headers">
          <div class="header-item">
            <h4 class="section-title">Original Image</h4>
          </div>
          <div class="header-item processed" v-if="processedStructure">
            <vue-feather type="check-circle" size="16" class="success-icon"></vue-feather>
            <h4 class="section-title">Processed Structure</h4>
          </div>
        </div>

        <div class="content-panels">
          <div class="panel original-panel">
            <div class="download-container">
              <button class="download-btn" @click="downloadSegmentImage">
                <vue-feather type="download" size="16" class="download-icon"></vue-feather>
                <span>Download Image</span>
              </button>
            </div>

            <div class="image-container">
              <div v-if="isLoading" class="loading-overlay">
                <div class="loader-pulse"></div>
              </div>
              <img
                v-if="segmentUrl"
                :src="segmentUrl"
                alt="Chemical structure segment"
                class="segment-image"
                @load="handleImageLoaded"
                @error="handleImageError"
              />
            </div>

            <div class="metadata-container">
              <div class="metadata-section">
                <div class="info-row">
                  <span class="info-label">Page:</span>
                  <span class="info-value">{{ segment.pageNumber || '1' }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Filename:</span>
                  <span class="info-value truncate" :title="segment.filename">{{ segment.filename }}</span>
                </div>
              </div>

              <div v-if="processedStructure" class="processing-info">
                <div class="info-row">
                  <span class="info-label">Engine:</span>
                  <span class="info-value engine-tag">{{ processedStructure.engine || 'Unknown' }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Processed:</span>
                  <span class="info-value">{{ formatTimestamp(processedStructure.timestamp) }}</span>
                </div>
              </div>
            </div>
          </div>

          <div v-if="processedStructure" class="panel structure-panel">
            <div class="structure-header-container">
              <div class="structure-title">Compound {{ segmentNumber }}</div>
              <div class="structure-actions">
                <button class="action-btn" @click="copySmilesToClipboard" title="Copy SMILES">
                  <vue-feather type="copy" size="16"></vue-feather>
                </button>
                <button class="download-btn" @click="downloadStructureImage">
                  <vue-feather type="download" size="16" class="download-icon"></vue-feather>
                  <span>Download Structure</span>
                </button>
              </div>
            </div>

            <div class="structure-visualization">
              <div class="structure-container">
                <ImprovedChemicalStructureViewer
                  :smiles="processedStructure.smiles"
                  :molfile="processedStructure.molfile"
                  :name="processedStructure.name || `Compound ${segmentNumber}`"
                  :source-engine="processedStructure.engine"
                  :use-coordinates="shouldUseCoordinates"
                  @copied="handleCopied"
                  @error="handleStructureError"
                  @download-complete="handleDownloadComplete"
                  hide-controls
                />
              </div>
            </div>

            <div class="smiles-container">
              <div class="smiles-header">
                <span class="smiles-label">SMILES:</span>
              </div>
              <div class="smiles-content">
                <div class="smiles-box">{{ processedStructure.smiles }}</div>
              </div>
            </div>

            <div class="tags-row">
              <div class="tag smiles-tag">
                <vue-feather type="code" size="14" class="tag-icon"></vue-feather>
                <span>Using SMILES</span>
              </div>
              <div class="tag engine-tag" :class="engineTagClass">
                <vue-feather type="cpu" size="14" class="tag-icon"></vue-feather>
                <span>{{ processedStructure.engine || 'Unknown' }}</span>
              </div>
              <div class="tag tool-tag">
                <vue-feather type="tool" size="14" class="tag-icon"></vue-feather>
                <span>CDK engine</span>
              </div>
            </div>
          </div>
        </div>

        <div class="compare-callout">
          <div class="callout-icon">
            <vue-feather type="info" size="18" class="info-icon"></vue-feather>
          </div>
          <div class="callout-text">
            <p>Want to see how different engines perform on this structure?</p>
          </div>
          <button class="compare-btn pulse-effect" @click="runComparison">
            <vue-feather type="bar-chart-2" size="16" class="btn-icon"></vue-feather>
            <span>Compare Across All Engines</span>
          </button>
        </div>
      </div>

      <!-- IMPROVED COMPARISON MODE VIEW -->
      <div v-else class="comparison-mode">
        <div class="comparison-header">
          <div class="comparison-title-section">
            <h3 class="comparison-title">
              <vue-feather type="bar-chart-2" class="title-icon"></vue-feather>
              <span class="title-text">Engine Comparison: Segment #{{ segmentNumber }}</span>
            </h3>
            <p class="comparison-description">Compare structure recognition results across all available engines</p>
          </div>
          <button class="back-btn" @click="comparisonMode = false">
            <vue-feather type="arrow-left" size="14"></vue-feather>
            <span>Back to Details</span>
          </button>
        </div>

        <div class="comparison-content">
          <!-- Comparison Layout with Original Segment -->
          <div class="comparison-layout">
            <!-- Original Segment Column -->
            <div class="original-segment-column">
              <h4 class="column-title">
                <vue-feather type="image" class="column-icon"></vue-feather>
                Original Segment
              </h4>
              <div class="segment-preview">
                <img
                  v-if="segmentUrl"
                  :src="segmentUrl"
                  alt="Original chemical structure segment"
                  class="original-img"
                />
                <div class="segment-file-info">
                  <div class="file-info-row">
                    <span class="info-key">Filename:</span>
                    <span class="info-value truncate" :title="segment.filename">{{ segment.filename }}</span>
                  </div>
                  <div class="file-info-row">
                    <span class="info-key">Page:</span>
                    <span class="info-value">{{ segment.pageNumber || '1' }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Results Column -->
            <div class="engines-results-column">
              <h4 class="column-title">
                <vue-feather type="cpu" class="column-icon"></vue-feather>
                Engine Results
              </h4>

              <!-- Loading spinner when processing -->
              <div v-if="isComparing" class="engine-loading">
                <div class="fancy-spinner">
                  <div class="ring"></div>
                  <div class="ring"></div>
                  <div class="dot"></div>
                </div>
                <p class="loading-text">Processing with all engines...</p>
              </div>

              <!-- Engines results grid -->
              <div v-else class="engine-results-grid">
                <!-- DECIMER Result Card -->
                <div class="engine-result-card">
                  <div class="engine-header decimer">
                    <div class="engine-icon-container">
                      <vue-feather type="cpu" class="engine-icon"></vue-feather>
                    </div>
                    <h4 class="engine-name">DECIMER</h4>
                  </div>
                  <div class="engine-content">
                    <!-- Structure visualization -->
                    <div class="structure-preview">
                      <img
                        v-if="decimerResult && decimerResult.svg"
                        :src="'data:image/svg+xml;utf8,' + encodeURIComponent(decimerResult.svg)"
                        class="result-image"
                        alt="DECIMER result"
                      />
                      <div v-else-if="decimerResult && decimerResult.error" class="error-result">
                        <vue-feather type="alert-circle" class="error-icon"></vue-feather>
                        <p>{{ decimerResult.error }}</p>
                      </div>
                      <div v-else class="loading-structure">
                        <vue-feather type="loader" class="loading-icon spin"></vue-feather>
                      </div>
                    </div>
                    
                    <!-- SMILES data -->
                    <div v-if="decimerResult && decimerResult.smiles" class="smiles-data">
                      <div class="smiles-label">SMILES:</div>
                      <div class="smiles-value">{{ truncateText(decimerResult.smiles, 20) }}</div>
                      <button class="copy-btn" @click="copyEngineSmiles(decimerResult.smiles)" title="Copy SMILES">
                        <vue-feather type="copy" size="14"></vue-feather>
                      </button>
                    </div>

                    <!-- Processing time -->
                    <div v-if="decimerResult && decimerResult.processingTime" class="engine-stats">
                      <div class="stat-item">
                        <span class="stat-label">Processing Time:</span>
                        <span class="stat-value">{{ decimerResult.processingTime }}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- MolNexTR Result Card -->
                <div class="engine-result-card">
                  <div class="engine-header molnextr">
                    <div class="engine-icon-container">
                      <vue-feather type="grid" class="engine-icon"></vue-feather>
                    </div>
                    <h4 class="engine-name">MolNexTR</h4>
                  </div>
                  <div class="engine-content">
                    <!-- Structure visualization -->
                    <div class="structure-preview">
                      <img
                        v-if="molnextrResult && molnextrResult.svg"
                        :src="'data:image/svg+xml;utf8,' + encodeURIComponent(molnextrResult.svg)"
                        class="result-image"
                        alt="MolNexTR result"
                      />
                      <div v-else-if="molnextrResult && molnextrResult.error" class="error-result">
                        <vue-feather type="alert-circle" class="error-icon"></vue-feather>
                        <p>{{ molnextrResult.error }}</p>
                      </div>
                      <div v-else class="loading-structure">
                        <vue-feather type="loader" class="loading-icon spin"></vue-feather>
                      </div>
                    </div>
                    
                    <!-- SMILES data -->
                    <div v-if="molnextrResult && molnextrResult.smiles" class="smiles-data">
                      <div class="smiles-label">SMILES:</div>
                      <div class="smiles-value">{{ truncateText(molnextrResult.smiles, 20) }}</div>
                      <button class="copy-btn" @click="copyEngineSmiles(molnextrResult.smiles)" title="Copy SMILES">
                        <vue-feather type="copy" size="14"></vue-feather>
                      </button>
                    </div>

                    <!-- Processing time -->
                    <div v-if="molnextrResult && molnextrResult.processingTime" class="engine-stats">
                      <div class="stat-item">
                        <span class="stat-label">Processing Time:</span>
                        <span class="stat-value">{{ molnextrResult.processingTime }}</span>
                      </div>
                      <div class="stat-item coordinates-badge" v-if="molnextrResult.molfile">
                        <span class="coordinate-label">
                          <vue-feather type="map-pin" size="12" class="coordinate-icon"></vue-feather>
                          Coordinates Available
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- MolScribe Result Card -->
                <div class="engine-result-card">
                  <div class="engine-header molscribe">
                    <div class="engine-icon-container">
                      <vue-feather type="edit-3" class="engine-icon"></vue-feather>
                    </div>
                    <h4 class="engine-name">MolScribe</h4>
                  </div>
                  <div class="engine-content">
                    <!-- Structure visualization -->
                    <div class="structure-preview">
                      <img
                        v-if="molscribeResult && molscribeResult.svg"
                        :src="'data:image/svg+xml;utf8,' + encodeURIComponent(molscribeResult.svg)"
                        class="result-image"
                        alt="MolScribe result"
                      />
                      <div v-else-if="molscribeResult && molscribeResult.error" class="error-result">
                        <vue-feather type="alert-circle" class="error-icon"></vue-feather>
                        <p>{{ molscribeResult.error }}</p>
                      </div>
                      <div v-else class="loading-structure">
                        <vue-feather type="loader" class="loading-icon spin"></vue-feather>
                      </div>
                    </div>
                    
                    <!-- SMILES data -->
                    <div v-if="molscribeResult && molscribeResult.smiles" class="smiles-data">
                      <div class="smiles-label">SMILES:</div>
                      <div class="smiles-value">{{ truncateText(molscribeResult.smiles, 20) }}</div>
                      <button class="copy-btn" @click="copyEngineSmiles(molscribeResult.smiles)" title="Copy SMILES">
                        <vue-feather type="copy" size="14"></vue-feather>
                      </button>
                    </div>

                    <!-- Processing time -->
                    <div v-if="molscribeResult && molscribeResult.processingTime" class="engine-stats">
                      <div class="stat-item">
                        <span class="stat-label">Processing Time:</span>
                        <span class="stat-value">{{ molscribeResult.processingTime }}</span>
                      </div>
                      <div class="stat-item coordinates-badge" v-if="molscribeResult.molfile">
                        <span class="coordinate-label">
                          <vue-feather type="map-pin" size="12" class="coordinate-icon"></vue-feather>
                          Coordinates Available
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Similarity Summary Section -->
          <div class="similarity-summary" v-if="allEnginesLoaded">
            <div class="summary-header">
              <h4 class="summary-title">
                <vue-feather type="bar-chart-2" class="summary-icon"></vue-feather>
                Similarity Analysis
              </h4>
              <div class="summary-toggle" @click="toggleSimilarityDetails">
                <span>{{ showSimilarityDetails ? 'Hide Details' : 'Show Details' }}</span>
                <vue-feather 
                  :type="showSimilarityDetails ? 'chevron-up' : 'chevron-down'"
                  size="16" 
                  class="toggle-icon"
                ></vue-feather>
              </div>
            </div>

            <!-- Quick Summary Stats -->
            <div class="quick-summary">
              <div class="summary-stats">
                <div class="stat-card" :class="getAgreementClass(similarityScore)">
                  <div class="stat-value">{{ formatPercentage(similarityScore) }}</div>
                  <div class="stat-label">Overall Agreement</div>
                </div>
                
                <div class="stat-card">
                  <div class="stat-value">{{ validEngineCount }}/3</div>
                  <div class="stat-label">Valid Results</div>
                </div>
                
                <div class="stat-card" v-if="hasIdenticalResults">
                  <div class="stat-value identical">
                    <vue-feather type="check-circle" size="20" class="identical-icon"></vue-feather>
                  </div>
                  <div class="stat-label">Identical Structures</div>
                </div>
                <div class="stat-card" v-else>
                  <div class="stat-value">{{ matchingPairs }}/{{ totalPairs }}</div>
                  <div class="stat-label">Matching Pairs</div>
                </div>
              </div>
            </div>
            
            <!-- Enhanced Action Button Area -->
            <div class="analysis-action-buttons">
              <button class="highlight-btn" @click="findMCS" :disabled="!canFindMCS || findingMCS">
                <vue-feather type="target" size="16" class="btn-icon"></vue-feather>
                <span>{{ findingMCS ? 'Finding MCS...' : 'Highlight Common Structure' }}</span>
              </button>
              
              <button class="analyze-btn" @click="compareAcrossEngines" :disabled="!canCompare">
                <vue-feather type="activity" size="16" class="btn-icon"></vue-feather>
                <span>Run Full Analysis</span>
              </button>
            </div>

            <!-- Detailed Similarity Section (Collapsible) -->
            <div v-if="showSimilarityDetails" class="similarity-details">
              <div class="details-content" v-if="comparisonResult">
                <SimilarityComparison
                  :comparison-result="comparisonResult"
                  :is-loading="isComparing"
                  :error="comparisonError"
                  :original-smiles-list="smilesListForComparison"
                />
              </div>
              <div v-else-if="!hasRunFullAnalysis" class="run-analysis-prompt">
                <p>Click "Run Full Analysis" above to see detailed similarity metrics between engines</p>
              </div>
              <div v-else-if="comparisonError" class="analysis-error">
                <vue-feather type="alert-circle" size="20" class="error-icon"></vue-feather>
                <p>{{ comparisonError }}</p>
              </div>
            </div>
          </div>

          <!-- Footer Actions -->
          <div class="comparison-footer">
            <button class="refresh-btn" @click="runComparisonAgain" :disabled="isComparing">
              <vue-feather type="refresh-cw" class="refresh-icon"></vue-feather>
              <span>Process All Engines Again</span>
            </button>

            <div class="view-options">
              <label class="option-checkbox">
                <input type="checkbox" v-model="useCoordinatesForDisplay" :disabled="isComparing">
                <span class="checkbox-label">Use coordinates for display when available</span>
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Context View (Page View) -->
    <div v-if="showContextView" class="context-view-container">
      <div class="context-view-header">
        <h3>Original Context - Page {{ segment.pageNumber || 1 }}</h3>
        <button class="btn-close" @click="closeContextView">
          <vue-feather type="x" size="16"></vue-feather>
        </button>
      </div>

      <div class="context-view-content">
        <div v-if="isLoadingContext" class="loading-context">
          <div class="loader-pulse"></div>
        </div>
        <img
          v-else-if="contextImageUrl"
          :src="contextImageUrl"
          alt="Segment in context"
          class="context-image"
          @load="contextImageLoaded"
          @error="handleContextImageError"
        />
        <div v-else class="context-error">
          <vue-feather type="alert-triangle" size="24"></vue-feather>
          <p>Failed to load page context</p>
        </div>
      </div>
    </div>

    <!-- Comparison Modal (Full Analysis) -->
    <ComparisonModal
      v-if="showComparisonModal"
      :comparison-result="comparisonResult"
      :is-loading="isComparing"
      :error="comparisonError"
      :smiles-list="smilesListForComparison"
      @close="closeComparisonModal"
    />
  </div>
</template>

<script>
import ImprovedChemicalStructureViewer from './ImprovedChemicalStructureViewer.vue'
import ComparisonModal from './ComparisonModal.vue'
import SimilarityComparison from './SimilarityComparison.vue'
import ocsrService from '@/services/ocsrService'
import depictionService from '@/services/depictionService'
import similarityService from '@/services/similarityService'

export default {
  name: 'SegmentViewer',
  components: {
    ImprovedChemicalStructureViewer,
    ComparisonModal,
    SimilarityComparison
  },
  props: {
    segment: {
      type: Object,
      default: null
    },
    processedStructure: {
      type: Object,
      default: null
    },
    isProcessing: {
      type: Boolean,
      default: false
    }
  },
  data() {
    return {
      isLoading: true,
      hasError: false,
      errorMessage: '',
      segmentUrl: null,
      comparisonMode: false,
      isComparing: false,
      decimerResult: null,
      molnextrResult: null,
      molscribeResult: null,
      isFullscreen: false,
      showContextView: false,
      contextImageUrl: null,
      isLoadingContext: false,
      hasContextError: false,
      // Comparison modal properties
      showComparisonModal: false,
      comparisonResult: null,
      comparisonError: '',
      smilesListForComparison: [],
      // Enhanced comparison properties
      showSimilarityDetails: false,
      useCoordinatesForDisplay: false,
      hasRunFullAnalysis: false,
      similarityScore: 0,  // 0-100 percentage
      matchingPairs: 0,
      totalPairs: 0,
      hasIdenticalResults: false,
      findingMCS: false // Property for MCS finding
    }
  },
  computed: {
    segmentNumber() {
      if (!this.segment) return 0
      return this.segment.segmentNumber || this.segment.id?.split('-')[1] || '?'
    },
    engineTagClass() {
      if (!this.processedStructure || !this.processedStructure.engine) return ''

      const engine = this.processedStructure.engine.toLowerCase()
      if (engine.includes('decimer')) return 'decimer-tag'
      if (engine.includes('molnextr')) return 'molnextr-tag'
      if (engine.includes('molscribe')) return 'molscribe-tag'

      return ''
    },
    shouldUseCoordinates() {
      if (!this.processedStructure) return false;

      // Check if useCoordinates flag is explicitly set
      if (this.processedStructure.useCoordinates === true) {
        return true;
      }

      // Otherwise, use coordinates if:
      // 1. We have a molfile
      // 2. The engine is MolNexTR or MolScribe
      return !!this.processedStructure.molfile &&
        (this.processedStructure.engine === 'molnextr' ||
          this.processedStructure.engine === 'molscribe');
    },
    // Check if all engines have loaded (either with success or error)
    allEnginesLoaded() {
      return this.decimerResult && this.molnextrResult && this.molscribeResult;
    },
    // Count engines with valid results
    validEngineCount() {
      let count = 0;
      if (this.decimerResult?.smiles && !this.decimerResult.error) count++;
      if (this.molnextrResult?.smiles && !this.molnextrResult.error) count++;
      if (this.molscribeResult?.smiles && !this.molscribeResult.error) count++;
      return count;
    },
    // Check if we can compare (need at least 2 valid engines)
    canCompare() {
      return this.validEngineCount >= 2;
    },
    // Check if we can find MCS (need at least 2 valid engines)
    canFindMCS() {
      return this.validEngineCount >= 2;
    }
  },
  watch: {
    segment: {
      immediate: true,
      handler(newSegment) {
        if (newSegment) {
          this.loadSegmentImage()
        } else {
          this.resetState()
        }
      }
    },
    // Watch for engine results to calculate similarity stats
    allEnginesLoaded: {
      handler(allLoaded) {
        if (allLoaded && !this.hasRunFullAnalysis) {
          this.calculateQuickSimilarity();
        }
      }
    },
    // Update depiction when coordinates preference changes
    useCoordinatesForDisplay: {
      handler() {
        if (this.allEnginesLoaded) {
          // Regenerate depictions with the new setting
          this.updateEnginePicturesWithCoordinates();
        }
      }
    }
  },
  methods: {
    resetState() {
      this.isLoading = true;
      this.hasError = false;
      this.errorMessage = '';
      this.comparisonMode = false;
      this.isComparing = false;
      this.decimerResult = null;
      this.molnextrResult = null;
      this.molscribeResult = null;
      this.showContextView = false;
      this.contextImageUrl = null;
      this.isLoadingContext = false;
      this.hasContextError = false;
      this.showComparisonModal = false;
      this.comparisonResult = null;
      this.comparisonError = '';
      this.smilesListForComparison = [];
      this.showSimilarityDetails = false;
      this.hasRunFullAnalysis = false;
      this.similarityScore = 0;
      this.matchingPairs = 0;
      this.totalPairs = 0;
      this.hasIdenticalResults = false;
      this.findingMCS = false;
      
      if (this.segmentUrl) {
        URL.revokeObjectURL(this.segmentUrl);
        this.segmentUrl = null;
      }
      if (this.contextImageUrl) {
        URL.revokeObjectURL(this.contextImageUrl);
        this.contextImageUrl = null;
      }
    },
    
    // Calculate quick similarity stats for the dashboard
    calculateQuickSimilarity() {
      // Default values
      this.similarityScore = 0;
      this.matchingPairs = 0;
      this.totalPairs = 0;
      this.hasIdenticalResults = false;
      
      // Get valid SMILES strings
      const validSmiles = [];
      if (this.decimerResult?.smiles) validSmiles.push({engine: 'decimer', smiles: this.decimerResult.smiles});
      if (this.molnextrResult?.smiles) validSmiles.push({engine: 'molnextr', smiles: this.molnextrResult.smiles});
      if (this.molscribeResult?.smiles) validSmiles.push({engine: 'molscribe', smiles: this.molscribeResult.smiles});
      
      // Need at least 2 engines with SMILES to compare
      if (validSmiles.length < 2) return;
      
      // Check if all SMILES are identical
      const allIdentical = validSmiles.every(item => item.smiles === validSmiles[0].smiles);
      this.hasIdenticalResults = allIdentical;
      
      if (allIdentical) {
        this.similarityScore = 100;
        this.matchingPairs = validSmiles.length * (validSmiles.length - 1) / 2; // All pairs match
        this.totalPairs = this.matchingPairs;
        return;
      }
      
      // Calculate number of pairs
      this.totalPairs = validSmiles.length * (validSmiles.length - 1) / 2;
      
      // Calculate matching pairs (simplified - just check exact matches)
      let matches = 0;
      for (let i = 0; i < validSmiles.length; i++) {
        for (let j = i + 1; j < validSmiles.length; j++) {
          if (validSmiles[i].smiles === validSmiles[j].smiles) {
            matches++;
          }
        }
      }
      
      this.matchingPairs = matches;
      
      // Calculate similarity score (percentage of matches)
      this.similarityScore = (matches / this.totalPairs) * 100;
    },
    
    // Update depictions when useCoordinatesForDisplay changes
    async updateEnginePicturesWithCoordinates() {
      // Only update if all engines have loaded
      if (!this.allEnginesLoaded || this.isComparing) return;
      
      try {
        // Update MolNexTR result
        if (this.molnextrResult?.smiles && this.molnextrResult?.molfile) {
          const useCoords = this.useCoordinatesForDisplay;
          const depictionOptions = {
            engine: 'cdk',
            smiles: this.molnextrResult.smiles,
            molfile: useCoords ? this.molnextrResult.molfile : null,
            useMolfileDirectly: useCoords,
            format: 'svg'
          };
          
          const svg = await depictionService.generateDepiction(depictionOptions);
          this.molnextrResult.svg = svg;
        }
        
        // Update MolScribe result
        if (this.molscribeResult?.smiles && this.molscribeResult?.molfile) {
          const useCoords = this.useCoordinatesForDisplay;
          const depictionOptions = {
            engine: 'cdk',
            smiles: this.molscribeResult.smiles,
            molfile: useCoords ? this.molscribeResult.molfile : null,
            useMolfileDirectly: useCoords,
            format: 'svg'
          };
          
          const svg = await depictionService.generateDepiction(depictionOptions);
          this.molscribeResult.svg = svg;
        }
      } catch (error) {
        console.error('Error updating depictions:', error);
      }
    },
    
    // Toggle showing detailed similarity information
    toggleSimilarityDetails() {
      this.showSimilarityDetails = !this.showSimilarityDetails;
    },
    
    // Get CSS class for agreement level
    getAgreementClass(score) {
      if (score >= 90) return 'high-agreement';
      if (score >= 60) return 'medium-agreement';
      return 'low-agreement';
    },
    
    // Format percentage value
    formatPercentage(value) {
      return value.toFixed(0) + '%';
    },
    
    // Copy SMILES from engine result
    copyEngineSmiles(smiles) {
      if (!smiles) return;
      
      try {
        navigator.clipboard.writeText(smiles)
          .then(() => {
            this.$emit('copy-complete', 'SMILES copied to clipboard');
          })
          .catch(err => {
            console.error('Could not copy SMILES:', err);
            this.$emit('error', 'Failed to copy SMILES');
          });
      } catch (error) {
        console.error('Error copying to clipboard:', error);
        this.$emit('error', 'Failed to copy to clipboard');
      }
    },
    
    showInContext() {
      this.showContextView = true;
      this.loadContextImage();
    },
    
    closeContextView() {
      this.showContextView = false;
      if (this.contextImageUrl) {
        URL.revokeObjectURL(this.contextImageUrl);
        this.contextImageUrl = null;
      }
    },
    
    async loadContextImage() {
      if (!this.segment) return;

      this.isLoadingContext = true;
      this.hasContextError = false;

      try {
        // Log the segment object to debug
        console.log('Segment object:', this.segment);

        // Get segment filename
        const segmentFilename = this.segment.filename;

        if (!segmentFilename) {
          throw new Error('Could not determine segment filename from metadata');
        }

        // Extract PDF filename from the path if pdfFilename is not available
        let pdfFilename;

        if (this.segment.pdfFilename) {
          pdfFilename = this.segment.pdfFilename;
        } else if (this.segment.path) {
          // Extract the directory name from the path which should be the PDF name
          const pathParts = this.segment.path.split('/');
          if (pathParts.length >= 2) {
            // Get the directory name (first part)
            pdfFilename = pathParts[0] + '.pdf';
            console.log('Extracted PDF filename from path:', pdfFilename);
          }
        }

        if (!pdfFilename) {
          throw new Error('Could not determine PDF filename from segment metadata');
        }

        // Get page number from filename
        let pageNumber = 0;
        if (this.segment.pageNumber !== undefined) {
          pageNumber = this.segment.pageNumber;
        } else if (segmentFilename && segmentFilename.startsWith('page_')) {
          const parts = segmentFilename.split('_');
          if (parts.length >= 2) {
            pageNumber = parseInt(parts[1], 10);
            console.log('Extracted page number:', pageNumber);
          }
        }

        // Construct the URL for the highlighted page endpoint using relative API path
        const url = `/api/decimer/get_highlighted_page/${encodeURIComponent(segmentFilename)}?pdf_filename=${encodeURIComponent(pdfFilename)}`;

        console.log('Requesting highlighted page:', url);

        // Fetch the highlighted image
        const response = await fetch(url);

        if (!response.ok) {
          // If highlighted page fails, check the response for details
          const errorData = await response.json().catch(() => ({}));
          console.error('Highlighted page error:', errorData);

          // Fall back to getting the segment image at a larger size
          console.log('Falling back to segment image');

          if (this.segmentUrl) {
            this.contextImageUrl = this.segmentUrl;
            this.$emit('notification', {
              type: 'warning',
              message: 'Showing segment only - page context is not available'
            });
          } else {
            throw new Error(`Failed to load page context: ${errorData.detail || response.statusText}`);
          }
        } else {
          const blob = await response.blob();
          this.contextImageUrl = URL.createObjectURL(blob);
        }
      } catch (error) {
        console.error('Error loading context image:', error);
        this.hasContextError = true;

        // As a last resort, if we have the segment image, just show that
        if (this.segmentUrl) {
          this.contextImageUrl = this.segmentUrl;
          this.$emit('notification', {
            type: 'warning',
            message: 'Showing segment only - full page context not available'
          });
        } else {
          this.$emit('error', `Failed to load context image: ${error.message}`);
        }
      } finally {
        this.isLoadingContext = false;
      }
    },
    
    contextImageLoaded() {
      this.isLoadingContext = false;
    },
    
    handleContextImageError() {
      this.isLoadingContext = false;
      this.hasContextError = true;
      this.$emit('error', 'Failed to load page context image');
    },
    
    runComparisonAgain() {
      this.runComparisonManual();
    },
    
    truncateText(text, maxLength) {
      if (!text) return '';
      return text.length > maxLength ? text.substring(0, maxLength - 3) + '...' : text;
    },
    
    runComparison() {
      // Switch to comparison mode
      this.comparisonMode = true;
      
      // Reset analysis state
      this.hasRunFullAnalysis = false;
      this.comparisonResult = null;
      
      // Run the comparison with all engines
      this.runComparisonManual();
      
      // Emit an event to notify parent component
      this.$emit('run-comparison', this.segment);
    },
    
    async runComparisonManual() {
      if (!this.segment || this.isComparing) return;

      this.isComparing = true;

      // Reset results
      this.decimerResult = null;
      this.molnextrResult = null;
      this.molscribeResult = null;

      // Reset similarity metrics
      this.similarityScore = 0;
      this.matchingPairs = 0;
      this.totalPairs = 0;
      this.hasIdenticalResults = false;

      // Determine image path format
      const segmentsDirectory = this.segment.path ? this.segment.path.split('/all_segments/')[0] : '';
      const imagePath = segmentsDirectory ? `${segmentsDirectory}/all_segments/${this.segment.filename}` : this.segment.filename;

      console.log('Segment path for comparison:', imagePath);

      try {
        // Process all engines in parallel
        await Promise.all([
          this.processEngine('decimer', imagePath),
          this.processEngine('molnextr', imagePath),
          this.processEngine('molscribe', imagePath)
        ]);
        
        // Calculate quick similarity metrics once all engines have processed
        if (this.allEnginesLoaded) {
          this.calculateQuickSimilarity();
        }
      } catch (error) {
        console.error('Error initiating comparisons:', error);
      } finally {
        this.isComparing = false;
      }
    },
    
    async processEngine(engine, imagePath) {
      const startTime = performance.now();
      
      try {
        console.log(`Processing with ${engine}...`);

        const options = {
          engine: engine,
          handDrawn: false,
          includeMolfile: true
        };

        // Get SMILES and molfile
        const response = await ocsrService.generateBoth(null, imagePath, options);

        console.log(`${engine} response:`, response);

        // Create a depiction
        let svg = null;
        try {
          const useCoords = this.useCoordinatesForDisplay && 
                          engine !== 'decimer' && 
                          response.molfile;
                          
          const depictionOptions = {
            engine: 'cdk',
            smiles: response.smiles,
            molfile: useCoords ? response.molfile : null,
            useMolfileDirectly: useCoords,
            format: 'svg'
          };

          const svgResponse = await depictionService.generateDepiction(depictionOptions);
          svg = svgResponse;
        } catch (depError) {
          console.error(`Error generating depiction for ${engine}:`, depError);
        }

        // Calculate processing time
        const endTime = performance.now();
        const processingTime = ((endTime - startTime) / 1000).toFixed(2) + 's';
        
        // Store the results based on the engine
        const result = {
          smiles: response.smiles,
          molfile: response.molfile,
          svg: svg,
          error: null,
          processingTime: processingTime
        };

        if (engine === 'decimer') {
          this.decimerResult = result;
        } else if (engine === 'molnextr') {
          this.molnextrResult = result;
        } else if (engine === 'molscribe') {
          this.molscribeResult = result;
        }
      } catch (error) {
        console.error(`Error processing with ${engine}:`, error);

        // Calculate processing time even for errors
        const endTime = performance.now();
        const processingTime = ((endTime - startTime) / 1000).toFixed(2) + 's';
        
        // Store error in the appropriate result
        const errorResult = {
          smiles: null,
          molfile: null,
          svg: null,
          error: error.message || `Failed to process with ${engine}`,
          processingTime: processingTime
        };

        if (engine === 'decimer') {
          this.decimerResult = errorResult;
        } else if (engine === 'molnextr') {
          this.molnextrResult = errorResult;
        } else if (engine === 'molscribe') {
          this.molscribeResult = errorResult;
        }
      }
    },
    
    async loadSegmentImage() {
      if (!this.segment) return;

      this.resetState();

      // If the segment already has a URL, use it
      if (this.segment.imageUrl) {
        console.log('Using existing segment image URL:', this.segment.imageUrl);
        this.segmentUrl = this.segment.imageUrl;
        this.isLoading = false;
        return;
      }

      try {
        if (this.segment.path) {
          // Use relative URL path through the API proxy
          this.segmentUrl = `/api/decimer/get_segment_image/${this.segment.path}`;
          console.log('Created segment URL from path:', this.segmentUrl);
        } else {
          throw new Error('No image URL or path provided');
        }
      } catch (error) {
        this.hasError = true;
        this.errorMessage = error.message || 'Failed to load segment image';
        this.isLoading = false;

        // Notify parent component
        this.$emit('error', this.errorMessage);
      }
    },
    
    handleImageLoaded() {
      this.isLoading = false;
      this.hasError = false;
    },
    
    handleImageError() {
      this.isLoading = false;
      this.hasError = true;
      this.errorMessage = 'Failed to load image';

      // Notify parent component
      this.$emit('error', this.errorMessage);
    },
    
    copySmilesToClipboard() {
      if (!this.processedStructure || !this.processedStructure.smiles) return;

      try {
        navigator.clipboard.writeText(this.processedStructure.smiles)
          .then(() => {
            // Show success message
            this.$emit('copy-complete', 'SMILES copied to clipboard');
          })
          .catch(err => {
            console.error('Could not copy SMILES:', err);
            this.$emit('error', 'Failed to copy SMILES');
          });
      } catch (error) {
        console.error('Error copying to clipboard:', error);
        this.$emit('error', 'Failed to copy to clipboard');
      }
    },
    
    async downloadSegmentImage() {
      if (!this.segmentUrl) return;

      try {
        // Fetch the image as a blob
        const response = await fetch(this.segmentUrl);
        const blob = await response.blob();

        // Create a download link
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `segment-${this.segmentNumber}.png`;
        a.click();

        // Clean up
        URL.revokeObjectURL(url);

        // Notify parent component
        this.$emit('download-complete', 'Segment image downloaded');
      } catch (error) {
        console.error('Error downloading image:', error);

        // Notify parent component
        this.$emit('error', 'Failed to download image');
      }
    },
    
    async downloadStructureImage() {
      if (!this.processedStructure) return;

      try {
        // Use the structure viewer's download method or implement your own
        // Here we're creating a simple SVG download
        const svgElement = document.querySelector('.structure-container .svg-container svg');

        if (svgElement) {
          // Create a clone of the SVG element
          const svgClone = svgElement.cloneNode(true);

          // Set necessary attributes for standalone SVG
          svgClone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
          svgClone.setAttribute('version', '1.1');

          // Create blob from SVG string
          const svgString = new XMLSerializer().serializeToString(svgClone);
          const blob = new Blob([svgString], { type: 'image/svg+xml' });

          // Create download link
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `compound-${this.segmentNumber}.svg`;
          a.click();

          // Clean up
          URL.revokeObjectURL(url);

          // Notify parent component
          this.$emit('download-complete', 'Structure image downloaded');
        } else {
          throw new Error('SVG element not found');
        }
      } catch (error) {
        console.error('Error downloading structure image:', error);
        this.$emit('error', 'Failed to download structure image');
      }
    },
    
    handleCopied(message) {
      // Forward the copied event to parent
      this.$emit('copy-complete', message);
    },
    
    handleStructureError(message) {
      // Forward the error event to parent
      this.$emit('error', message);
    },
    
    handleDownloadComplete(message) {
      // Forward the download-complete event to parent
      this.$emit('download-complete', message);
    },

    async compareAcrossEngines() {
      if (!this.segment || this.isComparing) return;

      this.isComparing = true;
      this.comparisonError = '';
      this.hasRunFullAnalysis = true;

      try {
        // Make sure all engines have completed processing
        if (!this.allEnginesLoaded) {
          await this.runComparisonManual();
        }

        // Define the engines we want to compare
        const engines = ['decimer', 'molnextr', 'molscribe'];
        const smilesList = [];
        const engineNames = [];

        // Collect SMILES from each engine
        if (this.decimerResult && this.decimerResult.smiles) {
          smilesList.push(this.decimerResult.smiles);
          engineNames.push(engines[0]); // decimer
        }

        if (this.molnextrResult && this.molnextrResult.smiles) {
          smilesList.push(this.molnextrResult.smiles);
          engineNames.push(engines[1]); // molnextr
        }

        if (this.molscribeResult && this.molscribeResult.smiles) {
          smilesList.push(this.molscribeResult.smiles);
          engineNames.push(engines[2]); // molscribe
        }

        // Make sure we have at least 2 engines with valid SMILES
        if (smilesList.length < 2) {
          throw new Error('Need at least 2 engines with valid SMILES for comparison');
        }

        // Store the SMILES list
        this.smilesListForComparison = smilesList;

        // Call the comparison API
        const result = await similarityService.compareSmiles(smilesList, engineNames);
        this.comparisonResult = result;

        // Show detailed analysis
        this.showSimilarityDetails = true;
        
        // Update quick stats with the actual data from the comparison
        if (result.agreement_summary) {
          this.similarityScore = result.agreement_summary.agreement_percentage;
          this.matchingPairs = result.agreement_summary.total_agreements;
          this.totalPairs = result.agreement_summary.total_comparisons;
          this.hasIdenticalResults = result.identical;
        }
        
        // Notify the user with a success message
        this.$emit('notification', {
          type: 'success',
          message: 'Full analysis completed successfully'
        });
      } catch (error) {
        console.error('Error comparing SMILES:', error);
        this.comparisonError = error.message || 'Error comparing SMILES';

        // Notify parent component
        this.$emit('error', this.comparisonError);
      } finally {
        this.isComparing = false;
      }
    },

    async findMCS() {
      if (!this.segment || this.findingMCS || !this.canFindMCS) return;

      this.findingMCS = true;

      try {
        // Make sure all engines have completed processing
        if (!this.allEnginesLoaded) {
          await this.runComparisonManual();
        }

        // Collect all valid results with SMILES
        const validResults = [];
        
        if (this.decimerResult?.smiles && !this.decimerResult.error) {
          validResults.push({
            engine: 'decimer',
            smiles: this.decimerResult.smiles,
            molfile: this.decimerResult.molfile
          });
        }
        
        if (this.molnextrResult?.smiles && !this.molnextrResult.error) {
          validResults.push({
            engine: 'molnextr', 
            smiles: this.molnextrResult.smiles,
            molfile: this.molnextrResult.molfile
          });
        }
        
        if (this.molscribeResult?.smiles && !this.molscribeResult.error) {
          validResults.push({
            engine: 'molscribe',
            smiles: this.molscribeResult.smiles,
            molfile: this.molscribeResult.molfile
          });
        }

        // Need at least 2 valid structures
        if (validResults.length < 2) {
          throw new Error('Need at least 2 valid structures to find common substructure');
        }
        
        // Initialize arrays for molfiles and engine names
        const molfiles = [];
        const engineNames = [];
        
        // Convert ALL results to molfiles if needed (including DECIMER)
        for (const result of validResults) {
          try {
            if (result.molfile) {
              // If molfile exists, use it
              molfiles.push(result.molfile);
              engineNames.push(result.engine);
            } else if (result.smiles) {
              // If only SMILES exists, convert to molfile
              console.log(`Converting SMILES to molfile for ${result.engine}`);
              const depictionResponse = await depictionService.generateMolfileFromSmiles(result.smiles);
              
              if (depictionResponse && depictionResponse.molfile) {
                molfiles.push(depictionResponse.molfile);
                engineNames.push(result.engine);
                console.log(`Successfully converted SMILES to molfile for ${result.engine}`);
              } else {
                console.warn(`Failed to convert SMILES to molfile for ${result.engine}`);
              }
            }
          } catch (error) {
            console.error(`Error processing molfile for ${result.engine}:`, error);
          }
        }

        // Make sure we have at least 2 molfiles after conversion
        if (molfiles.length < 2) {
          throw new Error('Need at least 2 valid structures to find common substructure');
        }

        // Call the MCS API with molfiles and engineNames
        console.log(`Finding MCS with ${molfiles.length} valid structures`);
        const mcsResult = await similarityService.findMCS(molfiles, engineNames);
        console.log('MCS Result:', mcsResult);
        
        if (!mcsResult.mcs_smarts) {
          throw new Error('No common structure found');
        }
        
        // Generate new depictions with highlighted MCS for each valid result
        const mcsSmarts = mcsResult.mcs_smarts;
        
        // Update each result with a new depiction that highlights the MCS
        const updatePromises = validResults.map(async (result) => {
          try {
            const depictionOptions = {
              engine: 'cdk',
              smiles: result.smiles,
              molfile: this.useCoordinatesForDisplay && result.molfile ? result.molfile : null,
              useMolfileDirectly: this.useCoordinatesForDisplay && result.molfile ? true : false,
              format: 'svg',
              highlight: mcsSmarts
            };
            
            // Generate the new SVG with MCS highlight
            const svgResult = await depictionService.generateDepiction(depictionOptions);
            
            // Update the appropriate result based on engine
            if (result.engine === 'decimer' && this.decimerResult) {
              this.decimerResult.svg = svgResult;
            } else if (result.engine === 'molnextr' && this.molnextrResult) {
              this.molnextrResult.svg = svgResult;
            } else if (result.engine === 'molscribe' && this.molscribeResult) {
              this.molscribeResult.svg = svgResult;
            }
          } catch (error) {
            console.error(`Error updating depiction for ${result.engine}:`, error);
          }
        });
        
        // Wait for all depiction updates to complete
        await Promise.all(updatePromises);
        
        // Show success notification
        this.$emit('notification', {
          type: 'success',
          message: 'Common substructure highlighted across all engines'
        });
        
      } catch (error) {
        console.error('Error finding MCS:', error);
        // Show error notification
        this.$emit('error', error.message || 'Error finding common substructure');
        this.comparisonError = error.message;
        this.$emit('error', this.comparisonError);
      } finally {
        this.findingMCS = false;
      }
    },

    closeComparisonModal() {
      this.showComparisonModal = false;
    },
    
    formatTimestamp(timestamp) {
      if (!timestamp) return 'Unknown';

      try {
        const date = new Date(timestamp);
        return date.toLocaleString();
      } catch (e) {
        return timestamp;
      }
    }
  }
}
</script>

<style lang="scss" scoped>
.segment-viewer {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: linear-gradient(145deg, #f8fafc 0%, #eef2ff 100%);
  border-radius: 16px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.08), 0 4px 8px rgba(0, 0, 0, 0.04);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  transition: all 0.3s ease;
  position: relative;

  /* Empty state styling */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    padding: 2rem;
    color: #64748b;
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);

    .empty-icon {
      margin-bottom: 1rem;
      color: #94a3b8;
      filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
    }

    p {
      font-size: 1.125rem;
      font-weight: 500;
    }
  }

  .segment-content {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;

    /* Normal view styling */
    .normal-view {
      display: flex;
      flex-direction: column;
      height: 100%;
      padding: 1.5rem;

      /* Header styling */
      .segment-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1.5rem;

        .segment-title {
          font-size: 1.625rem;
          font-weight: 700;
          color: #0f172a;
          margin: 0;
          background: linear-gradient(90deg, #1e293b 0%, #334155 100%);
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
        }

        .segment-actions {
          display: flex;
          gap: 0.5rem;

          .btn-action {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 36px;
            height: 36px;
            border: none;
            border-radius: 8px;
            background-color: #f1f5f9;
            color: #64748b;
            cursor: pointer;
            transition: all 0.2s ease;

            &:hover {
              background-color: #e2e8f0;
              color: #334155;
              transform: translateY(-1px);
              box-shadow: 0 2px 5px rgba(0, 0, 0, 0.08);
            }

            &:active {
              transform: translateY(0px);
            }

            &.btn-close:hover {
              background-color: #fee2e2;
              color: #ef4444;
            }

            &.btn-context:hover {
              background-color: #e6f7ff;
              color: #0081ff;
            }
          }
        }
      }

      /* Section headers */
      .section-headers {
        display: flex;
        justify-content: space-between;
        margin-bottom: 1rem;
        padding: 0 1rem;

        .header-item {
          display: flex;
          align-items: center;
          gap: 0.5rem;

          &.processed {
            .success-icon {
              color: #10b981;
              filter: drop-shadow(0 1px 2px rgba(16, 185, 129, 0.2));
            }
          }

          .section-title {
            margin: 0;
            font-size: 1.125rem;
            font-weight: 600;
            color: #334155;
          }
        }
      }

      /* Content panels */
      .content-panels {
        display: flex;
        gap: 1.5rem;
        height: 100%;
        margin-bottom: 1.5rem;

        @media (max-width: 768px) {
          flex-direction: column;
        }

        .panel {
          flex: 1;
          display: flex;
          flex-direction: column;
          border-radius: 12px;
          background-color: white;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
          overflow: hidden;
          height: fit-content;
          transition: transform 0.3s ease, box-shadow 0.3s ease;

          &:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 16px rgba(0, 0, 0, 0.08);
          }

          /* Original panel specific styling */
          &.original-panel {
            .download-container {
              display: flex;
              justify-content: flex-end;
              padding: 0.75rem 1rem;
              border-bottom: 1px solid #e2e8f0;
            }

            .image-container {
              display: flex;
              align-items: center;
              justify-content: center;
              padding: 1.5rem;
              background-color: white;
              min-height: 280px;
              position: relative;

              .loading-overlay {
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                background-color: rgba(255, 255, 255, 0.9);
                z-index: 2;

                .loader-pulse {
                  width: 60px;
                  height: 60px;
                  border-radius: 50%;
                  background-color: rgba(79, 70, 229, 0.2);
                  animation: pulse 1.5s ease-in-out infinite;

                  &:before, &:after {
                    content: '';
                    position: absolute;
                    height: 100%;
                    width: 100%;
                    background-color: rgba(79, 70, 229, 0.2);
                    border-radius: 50%;
                    z-index: -1;
                    opacity: 0.7;
                  }

                  &:before {
                    animation: pulse 1.5s ease-in-out infinite;
                    animation-delay: 0.3s;
                  }

                  &:after {
                    animation: pulse 1.5s ease-in-out infinite;
                    animation-delay: 0.6s;
                  }
                }
              }

              .segment-image {
                max-width: 100%;
                max-height: 280px;
                object-fit: contain;
                border-radius: 4px;
                transition: all 0.2s ease;
              }
            }

            .metadata-container {
              padding: 1rem;
              border-top: 1px solid #e2e8f0;
              background-color: #f8fafc;

              .metadata-section, .processing-info {
                margin-bottom: 0.75rem;

                &:last-child {
                  margin-bottom: 0;
                }
              }

              .processing-info {
                border-top: 1px dashed #e2e8f0;
                padding-top: 0.75rem;
                margin-top: 0.75rem;
              }

              .info-row {
                display: flex;
                align-items: center;
                margin-bottom: 0.5rem;

                &:last-child {
                  margin-bottom: 0;
                }

                .info-label {
                  font-weight: 600;
                  color: #334155;
                  width: 80px;
                  flex-shrink: 0;
                  font-size: 0.875rem;
                }

                .info-value {
                  color: #64748b;
                  font-size: 0.875rem;

                  &.truncate {
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                  }

                  &.engine-tag {
                    font-weight: 500;
                    color: #4f46e5;
                  }
                }
              }
            }
          }

          /* Structure panel specific styling */
          &.structure-panel {
            .structure-header-container {
              display: flex;
              justify-content: space-between;
              align-items: center;
              padding: 0.75rem 1rem;
              border-bottom: 1px solid #e2e8f0;

              .structure-title {
                font-weight: 600;
                color: #0f172a;
                font-size: 1rem;
              }

              .structure-actions {
                display: flex;
                align-items: center;
                gap: 0.5rem;

                .action-btn {
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  width: 32px;
                  height: 32px;
                  border: none;
                  border-radius: 6px;
                  background-color: #f1f5f9;
                  color: #64748b;
                  cursor: pointer;
                  transition: all 0.2s ease;

                  &:hover {
                    background-color: #e2e8f0;
                    color: #334155;
                  }
                }
              }
            }

            .structure-visualization {
              position: relative;
              padding: 1.5rem;
              background-color: white;
              min-height: 280px;

              .structure-title-overlay {
                position: absolute;
                top: 1rem;
                left: 1rem;
                font-size: 0.875rem;
                font-weight: 600;
                color: #64748b;
                background-color: rgba(255, 255, 255, 0.9);
                padding: 0.25rem 0.5rem;
                border-radius: 4px;
                z-index: 1;
                display: none; /* Hidden by default */
              }

              .structure-container {
                height: 100%;
                width: 100%;
                display: flex;
                align-items: center;
                justify-content: center;

                /* Deep selectors for chemical structure viewer */
                :deep(.chemical-structure-viewer) {
                  height: 100%;
                  width: 100%;

                  .structure-display {
                    background-color: white !important;
                  }

                  .svg-container {
                    display: flex;
                    align-items: center;
                    justify-content: center;

                    svg {
                      max-width: 100%;
                      max-height: 280px;
                    }
                  }
                }
              }
            }

            .smiles-container {
              padding: 1.25rem;
              border-top: 1px solid #e2e8f0;
              position: relative;
              background: linear-gradient(120deg, rgba(248, 250, 252, 0.7), rgba(255, 255, 255, 0.9));
              overflow: hidden;
              
              &::before {
                content: "";
                position: absolute;
                top: -2px;
                left: 0;
                right: 0;
                height: 2px;
                background: linear-gradient(90deg, #4f46e5, #a855f7);
                opacity: 0.7;
              }

              .smiles-header {
                margin-bottom: 0.75rem;
                display: flex;
                align-items: center;

                .smiles-label {
                  font-weight: 600;
                  color: #334155;
                  font-size: 0.95rem;
                  display: flex;
                  align-items: center;
                  gap: 0.5rem;
                  
                  &::before {
                    content: "";
                    display: block;
                    width: 12px;
                    height: 12px;
                    border-radius: 50%;
                    background-color: #4f46e5;
                    box-shadow: 0 0 8px rgba(79, 70, 229, 0.5);
                  }
                }
              }

              .smiles-content {
                .smiles-box {
                  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
                  background-color: white;
                  padding: 1rem;
                  border-radius: 8px;
                  font-size: 0.9rem;
                  color: #334155;
                  overflow-x: auto;
                  white-space: pre-wrap;
                  word-break: break-all;
                  border: 1px solid rgba(226, 232, 240, 0.8);
                  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04), inset 0 1px 0 rgba(255, 255, 255, 0.8);
                  transition: all 0.3s ease;
                  position: relative;
                  
                  &:hover {
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.8);
                    border-color: rgba(79, 70, 229, 0.3);
                  }
                  
                  &::after {
                    content: "Copy";
                    position: absolute;
                    top: 0.5rem;
                    right: 0.5rem;
                    background: rgba(79, 70, 229, 0.1);
                    color: #4f46e5;
                    font-size: 0.7rem;
                    padding: 0.2rem 0.5rem;
                    border-radius: 4px;
                    opacity: 0;
                    transition: opacity 0.2s ease;
                    cursor: pointer;
                    font-family: system-ui, sans-serif;
                    font-weight: 500;
                  }
                  
                  &:hover::after {
                    opacity: 1;
                  }
                }
              }
            }

            .tags-row {
              display: flex;
              flex-wrap: wrap;
              gap: 0.5rem;
              padding: 0.75rem 1rem;
              border-top: 1px solid #e2e8f0;
              background-color: #f8fafc;

              .tag {
                display: flex;
                align-items: center;
                gap: 0.375rem;
                font-size: 0.75rem;
                padding: 0.25rem 0.5rem;
                border-radius: 4px;
                font-weight: 500;

                .tag-icon {
                  opacity: 0.8;
                }

                &.smiles-tag {
                  background-color: rgba(79, 70, 229, 0.1);
                  color: #4f46e5;
                  border: 1px solid rgba(79, 70, 229, 0.3);
                }

                &.engine-tag {
                  background-color: rgba(20, 184, 166, 0.1);
                  color: #14b8a6;
                  border: 1px solid rgba(20, 184, 166, 0.3);

                  &.decimer-tag {
                    background-color: rgba(249, 115, 22, 0.1);
                    color: #f97316;
                    border: 1px solid rgba(249, 115, 22, 0.3);
                  }

                  &.molnextr-tag {
                    background-color: rgba(14, 165, 233, 0.1);
                    color: #0ea5e9;
                    border: 1px solid rgba(14, 165, 233, 0.3);
                  }

                  &.molscribe-tag {
                    background-color: rgba(168, 85, 247, 0.1);
                    color: #a855f7;
                    border: 1px solid rgba(168, 85, 247, 0.3);
                  }
                }

                &.tool-tag {
                  background-color: rgba(100, 116, 139, 0.1);
                  color: #64748b;
                  border: 1px solid rgba(100, 116, 139, 0.3);
                }
              }
            }
          }
        }
      }

      /* Download button styling */
      .download-btn {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        border: none;
        background-color: white;
        color: #334155;
        font-size: 0.875rem;
        font-weight: 500;
        padding: 0.5rem 0.75rem;
        border-radius: 6px;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
        border: 1px solid #e2e8f0;

        .download-icon {
          color: #64748b;
        }

        &:hover {
          border-color: #cbd5e1;
          background-color: #f8fafc;
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);

          .download-icon {
            color: #4f46e5;
          }
        }
      }

      /* Compare callout */
      .compare-callout {
        display: flex;
        align-items: center;
        padding: 1.25rem;
        background: linear-gradient(135deg, rgba(79, 70, 229, 0.05) 0%, rgba(79, 70, 229, 0.1) 100%);
        border-radius: 12px;
        border: 1px solid rgba(79, 70, 229, 0.2);
        box-shadow: 0 4px 6px rgba(79, 70, 229, 0.05);
        margin-top: auto;

        .callout-icon {
          flex-shrink: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 38px;
          height: 38px;
          background-color: rgba(79, 70, 229, 0.1);
          border-radius: 50%;
          margin-right: 1rem;

          .info-icon {
            color: #4f46e5;
          }
        }

        .callout-text {
          flex: 1;

          p {
            margin: 0;
            color: #334155;
            font-weight: 500;
            font-size: 0.9375rem;
          }
        }

        .compare-btn {
          flex-shrink: 0;
          display: flex;
          align-items: center;
          gap: 0.5rem;
          background-color: #4f46e5;
          color: white;
          border: none;
          padding: 0.625rem 1rem;
          border-radius: 8px;
          font-weight: 500;
          font-size: 0.9375rem;
          cursor: pointer;
          transition: all 0.3s ease;
          box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2);

          .btn-icon {
            opacity: 0.9;
          }

          &:hover {
            background-color: #4338ca;
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(79, 70, 229, 0.3);
          }

          &:active {
            transform: translateY(0px);
          }

          &.pulse-effect {
            animation: subtle-pulse 3s infinite;
          }
        }
      }
    }

    /* IMPROVED Comparison mode styling */
    .comparison-mode {
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      height: 100%;
      overflow-y: auto;

      .comparison-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid #e2e8f0;

        .comparison-title-section {
          .comparison-title {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 1.5rem;
            font-weight: 700;
            color: #0f172a;
            margin: 0 0 0.3rem 0;

            .title-icon {
              color: #4f46e5;
            }
          }
          
          .comparison-description {
            color: #64748b;
            margin: 0;
            font-size: 0.9rem;
          }
        }

        .back-btn {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          background-color: white;
          border: 1px solid #e2e8f0;
          color: #334155;
          font-size: 0.875rem;
          font-weight: 500;
          padding: 0.5rem 1rem;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s ease;

          &:hover {
            background-color: #f8fafc;
            border-color: #cbd5e1;
          }
        }
      }

      .comparison-content {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 1.5rem;
        
        /* Comparison layout styling */
        .comparison-layout {
          display: grid;
          grid-template-columns: 250px 1fr;
          gap: 1.5rem;
          
          @media (max-width: 768px) {
            grid-template-columns: 1fr;
          }
          
          .column-title {
            font-size: 1.1rem;
            font-weight: 600;
            margin: 0 0 1rem 0;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: #334155;
            
            .column-icon {
              color: #4f46e5;
            }
          }
          
          /* Original segment styling */
          .original-segment-column {
            .segment-preview {
              background: white;
              border-radius: 12px;
              overflow: hidden;
              box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
              display: flex;
              flex-direction: column;
              
              .original-img {
                max-width: 100%;
                max-height: 200px;
                object-fit: contain;
                padding: 1rem;
                background: white;
              }
              
              .segment-file-info {
                background: #f8fafc;
                padding: 0.75rem;
                border-top: 1px solid #e2e8f0;
                
                .file-info-row {
                  margin-bottom: 0.5rem;
                  display: flex;
                  gap: 0.5rem;
                  font-size: 0.875rem;
                  
                  &:last-child {
                    margin-bottom: 0;
                  }
                  
                  .info-key {
                    font-weight: 600;
                    color: #334155;
                  }
                  
                  .info-value {
                    color: #64748b;
                    
                    &.truncate {
                      white-space: nowrap;
                      overflow: hidden;
                      text-overflow: ellipsis;
                    }
                  }
                }
              }
            }
          }
          
          /* Engine results styling */
          .engines-results-column {
            .engine-loading {
              display: flex;
              flex-direction: column;
              align-items: center;
              justify-content: center;
              min-height: 200px;
              
              .fancy-spinner {
                position: relative;
                width: 64px;
                height: 64px;
                margin-bottom: 1rem;
                
                .ring {
                  position: absolute;
                  width: 100%;
                  height: 100%;
                  border-radius: 50%;
                  border: 3px solid transparent;
                  border-top-color: #4f46e5;
                  animation: spin 1.5s linear infinite;
                  
                  &:nth-child(2) {
                    border: 3px solid transparent;
                    border-bottom-color: #4f46e5;
                    animation: spin 2s linear infinite;
                  }
                }
                
                .dot {
                  position: absolute;
                  top: 50%;
                  left: 50%;
                  transform: translate(-50%, -50%);
                  width: 15px;
                  height: 15px;
                  border-radius: 50%;
                  background-color: #4f46e5;
                  animation: pulse 1s ease infinite alternate;
                }
              }
              
              .loading-text {
                font-weight: 500;
                color: #334155;
                font-size: 1rem;
              }
            }
            
            .engine-results-grid {
              display: grid;
              grid-template-columns: repeat(3, 1fr);
              gap: 1.25rem;
              
              @media (max-width: 900px) {
                grid-template-columns: repeat(3, 1fr);
              }
              
              @media (max-width: 767px) {
                grid-template-columns: 1fr;
              }
              
              .engine-result-card {
                background: rgba(255, 255, 255, 0.95);
                border-radius: 16px;
                overflow: hidden;
                box-shadow: 0 8px 20px rgba(0, 0, 0, 0.07);
                display: flex;
                flex-direction: column;
                backdrop-filter: blur(8px);
                transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
                border: 1px solid rgba(255, 255, 255, 0.6);
                
                &:hover {
                  transform: translateY(-5px);
                  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.12);
                }
                
                .engine-header {
                  display: flex;
                  align-items: center;
                  gap: 1rem;
                  padding: 1rem;
                  position: relative;
                  overflow: hidden;
                  
                  &:before {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    opacity: 0.7;
                    z-index: 0;
                  }
                  
                  &.decimer {
                    background: linear-gradient(135deg, rgba(249, 115, 22, 0.15) 0%, rgba(249, 115, 22, 0.25) 100%);
                    border-bottom: 2px solid rgba(249, 115, 22, 0.4);
                    
                    &:before {
                      background: radial-gradient(circle at top right, rgba(249, 115, 22, 0.3), transparent 70%);
                    }
                    
                    .engine-icon {
                      color: #f97316;
                      filter: drop-shadow(0 2px 4px rgba(249, 115, 22, 0.3));
                    }
                  }
                  
                  &.molnextr {
                    background: linear-gradient(135deg, rgba(14, 165, 233, 0.15) 0%, rgba(14, 165, 233, 0.25) 100%);
                    border-bottom: 2px solid rgba(14, 165, 233, 0.4);
                    
                    &:before {
                      background: radial-gradient(circle at top right, rgba(14, 165, 233, 0.3), transparent 70%);
                    }
                    
                    .engine-icon {
                      color: #0ea5e9;
                      filter: drop-shadow(0 2px 4px rgba(14, 165, 233, 0.3));
                    }
                  }
                  
                  &.molscribe {
                    background: linear-gradient(135deg, rgba(168, 85, 247, 0.15) 0%, rgba(168, 85, 247, 0.25) 100%);
                    border-bottom: 2px solid rgba(168, 85, 247, 0.4);
                    
                    &:before {
                      background: radial-gradient(circle at top right, rgba(168, 85, 247, 0.3), transparent 70%);
                    }
                    
                    .engine-icon {
                      color: #a855f7;
                      filter: drop-shadow(0 2px 4px rgba(168, 85, 247, 0.3));
                    }
                  }
                  
                  .engine-icon-container {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    width: 40px;
                    height: 40px;
                    border-radius: 12px;
                    background-color: rgba(255, 255, 255, 0.9);
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                    position: relative;
                    z-index: 1;
                  }
                  
                  .engine-name {
                    font-size: 1.125rem;
                    font-weight: 700;
                    margin: 0;
                    color: #0f172a;
                    position: relative;
                    z-index: 1;
                    text-shadow: 0 1px 2px rgba(255, 255, 255, 0.5);
                  }
                }
                
                .engine-content {
                  padding: 1rem;
                  display: flex;
                  flex-direction: column;
                  gap: 0.75rem;
                  
                  .structure-preview {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 180px;
                    background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
                    border: 1px solid rgba(226, 232, 240, 0.8);
                    border-radius: 12px;
                    padding: 1rem;
                    position: relative;
                    overflow: hidden;
                    transition: transform 0.3s ease, box-shadow 0.3s ease;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03), inset 0 1px 0 rgba(255, 255, 255, 0.9);
                    
                    &:hover {
                      transform: translateY(-2px);
                      box-shadow: 0 8px 16px rgba(0, 0, 0, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.9);
                    }
                    
                    .result-image {
                      max-width: 100%;
                      max-height: 150px;
                      object-fit: contain;
                      filter: drop-shadow(0 2px 6px rgba(0, 0, 0, 0.12));
                      transition: transform 0.3s ease, filter 0.3s ease;
                      
                      &:hover {
                        transform: scale(1.03);
                        filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.18));
                      }
                    }
                    
                    .error-result {
                      padding: 1.25rem;
                      background: linear-gradient(145deg, #fee2e2 0%, #fecaca 100%);
                      border-radius: 12px;
                      color: #b91c1c;
                      font-size: 0.875rem;
                      text-align: center;
                      display: flex;
                      flex-direction: column;
                      align-items: center;
                      gap: 0.625rem;
                      box-shadow: 0 4px 10px rgba(239, 68, 68, 0.15);
                      border: 1px solid rgba(239, 68, 68, 0.2);
                      
                      .error-icon {
                        color: #ef4444;
                        filter: drop-shadow(0 1px 2px rgba(239, 68, 68, 0.3));
                      }
                      
                      p {
                        margin: 0;
                        font-weight: 500;
                      }
                    }
                    
                    .loading-structure {
                      display: flex;
                      align-items: center;
                      justify-content: center;
                      position: relative;
                      
                      &:before {
                        content: '';
                        position: absolute;
                        width: 48px;
                        height: 48px;
                        border-radius: 50%;
                        background: radial-gradient(circle, rgba(79, 70, 229, 0.2) 0%, rgba(79, 70, 229, 0.01) 70%);
                        animation: pulse 1.5s ease-in-out infinite alternate;
                      }
                      
                      .loading-icon {
                        color: #4f46e5;
                        filter: drop-shadow(0 1px 2px rgba(79, 70, 229, 0.4));
                        position: relative;
                        z-index: 1;
                        
                        &.spin {
                          animation: spin 1.2s cubic-bezier(0.5, 0.1, 0.5, 0.9) infinite;
                        }
                      }
                    }
                  }
                  
                  .smiles-data {
                    display: flex;
                    align-items: center;
                    background: #f8fafc;
                    border-radius: 6px;
                    padding: 0.5rem 0.75rem;
                    font-size: 0.875rem;
                    border: 1px solid #e2e8f0;
                    
                    .smiles-label {
                      font-weight: 600;
                      margin-right: 0.5rem;
                      color: #334155;
                      white-space: nowrap;
                    }
                    
                    .smiles-value {
                      font-family: monospace;
                      color: #64748b;
                      overflow: hidden;
                      text-overflow: ellipsis;
                      white-space: nowrap;
                      flex: 1;
                    }
                    
                    .copy-btn {
                      background: none;
                      border: none;
                      color: #64748b;
                      cursor: pointer;
                      padding: 0.25rem;
                      border-radius: 4px;
                      
                      &:hover {
                        background: rgba(0, 0, 0, 0.05);
                        color: #334155;
                      }
                    }
                  }
                  
                  .engine-stats {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 0.75rem;
                    font-size: 0.8125rem;
                    
                    .stat-item {
                      display: flex;
                      align-items: center;
                      gap: 0.5rem;
                      
                      .stat-label {
                        color: #64748b;
                      }
                      
                      .stat-value {
                        font-weight: 600;
                        color: #334155;
                      }
                      
                      &.coordinates-badge {
                        .coordinate-label {
                          display: flex;
                          align-items: center;
                          gap: 0.25rem;
                          color: #10b981;
                          background: rgba(16, 185, 129, 0.1);
                          border: 1px solid rgba(16, 185, 129, 0.3);
                          padding: 0.25rem 0.5rem;
                          border-radius: 12px;
                          font-size: 0.75rem;
                          
                          .coordinate-icon {
                            color: inherit;
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        
        /* Similarity Summary styling */
        .similarity-summary {
          background: white;
          border-radius: 12px;
          overflow: hidden;
          box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
          margin-top: 1rem;
          
          .summary-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 1.25rem;
            border-bottom: 1px solid #e2e8f0;
            cursor: pointer;
            
            &:hover {
              background: #f8fafc;
            }
            
            .summary-title {
              display: flex;
              align-items: center;
              gap: 0.5rem;
              margin: 0;
              font-size: 1.1rem;
              font-weight: 600;
              color: #334155;
              
              .summary-icon {
                color: #4f46e5;
              }
            }
            
            .summary-toggle {
              display: flex;
              align-items: center;
              gap: 0.5rem;
              color: #64748b;
              font-size: 0.875rem;
              
              .toggle-icon {
                color: inherit;
              }
            }
          }
          
          .quick-summary {
            padding: 1.25rem;
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
            
            .summary-stats {
              display: flex;
              flex-wrap: wrap;
              gap: 1rem;
              justify-content: center;
              
              .stat-card {
                background: #f8fafc;
                border-radius: 8px;
                padding: 1.25rem;
                min-width: 120px;
                text-align: center;
                transition: all 0.3s ease;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
                border: 1px solid #e2e8f0;
                flex: 1;
                
                &:hover {
                  transform: translateY(-3px);
                  box-shadow: 0 6px 12px rgba(0, 0, 0, 0.08);
                }
                
                .stat-value {
                  font-size: 1.75rem;
                  font-weight: 700;
                  margin-bottom: 0.5rem;
                  color: #334155;
                  
                  &.identical {
                    color: #10b981;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    
                    .identical-icon {
                      color: inherit;
                    }
                  }
                }
                
                .stat-label {
                  font-size: 0.875rem;
                  color: #64748b;
                }
                
                &.high-agreement .stat-value {
                  color: #10b981;
                }
                
                &.medium-agreement .stat-value {
                  color: #0ea5e9;
                }
                
                &.low-agreement .stat-value {
                  color: #f97316;
                }
              }
            }
          }
          
          /* IMPROVED: Enhanced Action Button area styling */
          .analysis-action-buttons {
            padding: 1.25rem;
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
            justify-content: center;
            background: linear-gradient(135deg, rgba(243, 244, 246, 0.5) 0%, rgba(255, 255, 255, 0.5) 100%);
            border-top: 1px solid #e2e8f0;

            .highlight-btn,
            .analyze-btn {
              display: flex;
              align-items: center;
              gap: 0.5rem;
              background-color: #4f46e5;
              color: white;
              border: none;
              padding: 0.75rem 1.25rem;
              border-radius: 8px;
              font-weight: 500;
              font-size: 0.9375rem;
              cursor: pointer;
              transition: all 0.3s ease;
              flex: 1;
              justify-content: center;
              max-width: 280px;
              box-shadow: 0 4px 6px rgba(79, 70, 229, 0.2);

              .btn-icon {
                opacity: 0.9;
              }

              &:hover:not(:disabled) {
                background-color: #4338ca;
                transform: translateY(-1px);
                box-shadow: 0 8px 16px rgba(79, 70, 229, 0.3);
              }

              &:disabled {
                background-color: #818cf8;
                opacity: 0.7;
                cursor: not-allowed;
              }
            }

            .highlight-btn {
              background-color: #0ea5e9;
              box-shadow: 0 4px 6px rgba(14, 165, 233, 0.2);
              
              &:hover:not(:disabled) {
                background-color: #0284c7;
                box-shadow: 0 8px 16px rgba(14, 165, 233, 0.3);
              }
              
              &:disabled {
                background-color: #7dd3fc;
              }
            }
          }
          
          .similarity-details {
            border-top: 1px solid #e2e8f0;
            padding: 1.25rem;
            
            .run-analysis-prompt {
              text-align: center;
              color: #64748b;
              font-size: 0.9375rem;
              padding: 2rem 0;
              background: #f8fafc;
              border-radius: 8px;
              border: 1px dashed #cbd5e1;
            }
            
            .analysis-error {
              display: flex;
              align-items: center;
              gap: 0.75rem;
              color: #ef4444;
              background: rgba(239, 68, 68, 0.1);
              border: 1px solid rgba(239, 68, 68, 0.3);
              padding: 1rem;
              border-radius: 8px;
              
              .error-icon {
                color: inherit;
              }
              
              p {
                margin: 0;
              }
            }
          }
        }

        /* Footer actions */
        .comparison-footer {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 1.5rem;
          padding-top: 1.5rem;
          border-top: 1px solid #e2e8f0;
          
          @media (max-width: 768px) {
            flex-direction: column;
            gap: 1rem;
            align-items: stretch;
          }
          
          .refresh-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            background-color: #4f46e5;
            color: white;
            border: none;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            font-weight: 500;
            font-size: 0.9375rem;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 2px 8px rgba(79, 70, 229, 0.25);
            
            .refresh-icon {
              opacity: 0.9;
            }
            
            &:hover:not(:disabled) {
              background-color: #4338ca;
              transform: translateY(-1px);
              box-shadow: 0 4px 8px rgba(79, 70, 229, 0.3);
            }
            
            &:disabled {
              background-color: #818cf8;
              opacity: 0.7;
              cursor: not-allowed;
            }
          }
          
          .view-options {
            .option-checkbox {
              display: flex;
              align-items: center;
              position: relative;
              cursor: pointer;
              user-select: none;
              
              input[type="checkbox"] {
                margin-right: 0.5rem;
              }
              
              .checkbox-label {
                font-size: 0.875rem;
                color: #334155;
              }
            }
          }
        }
      }
    }
  }
}

/* Context view styling */
.context-view-container {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.75);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(5px);
  
  .context-view-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    background-color: white;
    border-bottom: 1px solid #e2e8f0;
    
    h3 {
      margin: 0;
      font-size: 1.25rem;
      color: #334155;
    }
    
    .btn-close {
      background: none;
      border: none;
      color: #64748b;
      cursor: pointer;
      padding: 0.5rem;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      
      &:hover {
        background-color: #f1f5f9;
        color: #ef4444;
      }
    }
  }
  
  .context-view-content {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
    overflow: auto;
    
    .loading-context {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      
      .loader-pulse {
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background-color: rgba(255, 255, 255, 0.2);
        animation: pulse 1.5s ease-in-out infinite;
        margin-bottom: 1rem;
      }
    }
    
    .context-image {
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      background-color: white;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    }
    
    .context-error {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 1rem;
      color: white;
      
      p {
        margin: 0;
      }
    }
  }
}

/* Animations */
@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@keyframes pulse {
  0% { transform: scale(0.8); opacity: 0.7; }
  100% { transform: scale(1.2); opacity: 1; }
}

@keyframes subtle-pulse {
  0% { transform: scale(1); box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2); }
  50% { transform: scale(1.03); box-shadow: 0 4px 8px rgba(79, 70, 229, 0.4); }
  100% { transform: scale(1); box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2); }
}

/* Mobile specific styling */
@media (max-width: 768px) {
  .segment-viewer {
    .compare-callout {
      flex-direction: column;
      text-align: center;
      
      .callout-icon {
        margin-right: 0;
        margin-bottom: 0.5rem;
      }
      
      .callout-text {
        margin-bottom: 1rem;
      }
      
      .compare-btn {
        width: 100%;
        justify-content: center;
      }
    }
    
    .comparison-mode {
      .comparison-header {
        flex-direction: column;
        align-items: flex-start;
        gap: 1rem;
        
        .back-btn {
          align-self: flex-start;
        }
      }
      
      .quick-summary {
        flex-direction: column;
        
        .summary-stats {
          justify-content: center;
        }
        
        .action-buttons {
          width: 100%;
          justify-content: center;
          
          .highlight-btn,
          .analyze-btn {
            flex: 1;
          }
        }
      }
    }
    
    .content-panels {
      flex-direction: column;
      
      .panel {
        width: 100%;
      }
    }
    
    .section-headers {
      flex-direction: column;
      gap: 0.5rem;
      
      .header-item {
        justify-content: center;
      }
    }
  }
  
  .context-view-container {
    .context-view-content {
      padding: 0.5rem;
    }
  }
}

</style>