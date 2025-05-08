<template>
  <div class="segment-viewer" :class="{ 'fullscreen-mode': isFullscreen }">
    <div v-if="!segment" class="empty-state">
      <vue-feather type="image" size="32" class="empty-icon"></vue-feather>
      <p>No segment selected</p>
    </div>

    <div v-else class="segment-content">
      <div v-if="!comparisonMode" class="normal-view">
        <div class="segment-header">
          <div class="segment-title-section">
            <h3 class="segment-title">Segment #{{ segmentNumber }}</h3>

            <!-- Add segment selection checkbox -->
            <div class="segment-selection-control">
              <label class="selection-checkbox">
                <input type="checkbox" :checked="isSelected" @change="toggleSelection">
                <span class="checkbox-label" v-if="isSelected">Marked as correct</span>
                <span class="checkbox-label" v-else>Mark as correct</span>
              </label>
            </div>
          </div>

          <div class="segment-actions">
            <button class="view-context-btn" @click="showInContext">
              <div class="btn-content">
                <vue-feather type="file-text" size="16" class="context-icon"></vue-feather>
                <span>View in PDF Context</span>
              </div>
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
              <img v-if="segmentUrl" :src="segmentUrl" alt="Chemical structure segment" class="segment-image"
                @load="handleImageLoaded" @error="handleImageError" />
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
                <ImprovedChemicalStructureViewer :smiles="processedStructure.smiles"
                  :molfile="processedStructure.molfile" :name="processedStructure.name || `Compound ${segmentNumber}`"
                  :source-engine="processedStructure.engine" :use-coordinates="shouldUseCoordinates"
                  @copied="handleCopied" @error="handleStructureError" @download-complete="handleDownloadComplete"
                  hide-controls />
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
              <!-- Add selection status tag -->
              <div v-if="isSelected" class="tag selection-tag">
                <vue-feather type="check-square" size="14" class="tag-icon"></vue-feather>
                <span>Marked as correct</span>
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
          <div class="header-actions">
            <!-- Added coordinate display option here -->
            <label class="coordinate-display-option">
              <input type="checkbox" v-model="useCoordinatesForDisplay" :disabled="isComparing">
              <span class="option-label">Use coordinates when available</span>
            </label>
            <button class="back-btn" @click="comparisonMode = false">
              <vue-feather type="arrow-left" size="14"></vue-feather>
              <span>Back to Details</span>
            </button>
          </div>
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
                <img v-if="segmentUrl" :src="segmentUrl" alt="Original chemical structure segment"
                  class="original-img" />
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
                <div class="engine-result-card" :class="{ 'result-selected': selectedEngine === 'decimer' }">
                  <div class="engine-header decimer">
                    <div class="engine-icon-container">
                      <vue-feather type="cpu" class="engine-icon"></vue-feather>
                    </div>
                    <h4 class="engine-name">DECIMER</h4>
                  </div>
                  <div class="engine-content">
                    <!-- Structure visualization -->
                    <div class="structure-preview">
                      <img v-if="decimerResult && decimerResult.svg"
                        :src="'data:image/svg+xml;utf8,' + encodeURIComponent(decimerResult.svg)" class="result-image"
                        alt="DECIMER result" />
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

                    <!-- Selection button -->
                    <div v-if="decimerResult && decimerResult.smiles && !decimerResult.error" class="selection-actions">
                      <button class="select-prediction-btn" :class="{ 'active': selectedEngine === 'decimer' }"
                        @click="selectPrediction('decimer')">
                        <template v-if="selectedEngine === 'decimer'">
                          <vue-feather type="check-circle" size="16" class="btn-icon"></vue-feather>
                          <span>Selected</span>
                        </template>
                        <template v-else>
                          <vue-feather type="check" size="16" class="btn-icon"></vue-feather>
                          <span>Select This Result</span>
                        </template>
                      </button>
                    </div>
                  </div>
                </div>

                <!-- MolNexTR Result Card -->
                <div class="engine-result-card" :class="{ 'result-selected': selectedEngine === 'molnextr' }">
                  <div class="engine-header molnextr">
                    <div class="engine-icon-container">
                      <vue-feather type="cpu" class="engine-icon"></vue-feather>
                    </div>
                    <h4 class="engine-name">MolNexTR</h4>
                  </div>
                  <div class="engine-content">
                    <!-- Structure visualization -->
                    <div class="structure-preview">
                      <img v-if="molnextrResult && molnextrResult.svg"
                        :src="'data:image/svg+xml;utf8,' + encodeURIComponent(molnextrResult.svg)" class="result-image"
                        alt="MolNexTR result" />
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

                    <!-- Selection button -->
                    <div v-if="molnextrResult && molnextrResult.smiles && !molnextrResult.error"
                      class="selection-actions">
                      <button class="select-prediction-btn" :class="{ 'active': selectedEngine === 'molnextr' }"
                        @click="selectPrediction('molnextr')">
                        <template v-if="selectedEngine === 'molnextr'">
                          <vue-feather type="check-circle" size="16" class="btn-icon"></vue-feather>
                          <span>Selected</span>
                        </template>
                        <template v-else>
                          <vue-feather type="check" size="16" class="btn-icon"></vue-feather>
                          <span>Select This Result</span>
                        </template>
                      </button>
                    </div>
                  </div>
                </div>

                <!-- MolScribe Result Card -->
                <div class="engine-result-card" :class="{ 'result-selected': selectedEngine === 'molscribe' }">
                  <div class="engine-header molscribe">
                    <div class="engine-icon-container">
                      <vue-feather type="cpu" class="engine-icon"></vue-feather>
                    </div>
                    <h4 class="engine-name">MolScribe</h4>
                  </div>
                  <div class="engine-content">
                    <!-- Structure visualization -->
                    <div class="structure-preview">
                      <img v-if="molscribeResult && molscribeResult.svg"
                        :src="'data:image/svg+xml;utf8,' + encodeURIComponent(molscribeResult.svg)" class="result-image"
                        alt="MolScribe result" />
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

                    <!-- Selection button -->
                    <div v-if="molscribeResult && molscribeResult.smiles && !molscribeResult.error"
                      class="selection-actions">
                      <button class="select-prediction-btn" :class="{ 'active': selectedEngine === 'molscribe' }"
                        @click="selectPrediction('molscribe')">
                        <template v-if="selectedEngine === 'molscribe'">
                          <vue-feather type="check-circle" size="16" class="btn-icon"></vue-feather>
                          <span>Selected</span>
                        </template>
                        <template v-else>
                          <vue-feather type="check" size="16" class="btn-icon"></vue-feather>
                          <span>Select This Result</span>
                        </template>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Apply Selection button -->
          <div class="apply-selection-bar" v-if="selectedEngine && !isComparing">
            <div class="selection-message">
              <vue-feather type="info" size="16" class="message-icon"></vue-feather>
              <span>You've selected the prediction from <strong>{{ getEngineDisplayName(selectedEngine) }}</strong>.
                Click apply
                to update the structure.</span>
            </div>
            <button class="apply-selection-btn" @click="applySelectedPrediction">
              <vue-feather type="check-square" size="16" class="btn-icon"></vue-feather>
              <span>Apply Selection</span>
            </button>
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
              <vue-feather :type="showSimilarityDetails ? 'chevron-up' : 'chevron-down'" size="16"
                class="toggle-icon"></vue-feather>
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
            <button class="highlight-common-btn" @click="findMCS" :disabled="!canFindMCS || findingMCS">
              <vue-feather type="target" size="16" class="btn-icon"></vue-feather>
              <span>{{ findingMCS ? 'Finding MCS...' : 'Highlight Common Structure' }}</span>
            </button>

            <button class="analyze-btn" @click="compareAcrossEngines" 
        :disabled="!canCompare || isComparing">
  <vue-feather :type="isComparing ? 'loader' : 'activity'" 
               :class="{'spin': isComparing}" size="16" class="btn-icon"></vue-feather>
  <span>{{ isComparing ? 'Running Analysis...' : 'Run Analysis' }}</span>
</button>
          </div>

          <!-- Detailed Similarity Section (Collapsible) -->
          <div v-if="showSimilarityDetails" class="similarity-details">
            <div class="details-content" v-if="comparisonResult">
              <SimilarityComparison :comparison-result="comparisonResult" :is-loading="isComparing"
                :error="comparisonError" :original-smiles-list="smilesListForComparison" />
            </div>
            <div v-else-if="!hasRunFullAnalysis && !isComparing" class="run-analysis-prompt">
              <vue-feather type="loader" class="loading-icon spin" size="24"></vue-feather>
              <p>Analysis will run automatically when all engines have loaded...</p>
            </div>
            <div v-else-if="isComparing" class="run-analysis-prompt">
              <vue-feather type="loader" class="loading-icon spin" size="24"></vue-feather>
              <p>Running detailed similarity analysis...</p>
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
        <img v-else-if="contextImageUrl" :src="contextImageUrl" alt="Segment in context" class="context-image"
          @load="contextImageLoaded" @error="handleContextImageError" />
        <div v-else class="context-error">
          <vue-feather type="alert-triangle" size="24"></vue-feather>
          <p>Failed to load page context</p>
        </div>
      </div>
    </div>

    <!-- Comparison Modal (Full Analysis) -->
    <ComparisonModal v-if="showComparisonModal" :comparison-result="comparisonResult" :is-loading="isComparing"
      :error="comparisonError" :smiles-list="smilesListForComparison" @close="closeComparisonModal" />
  </div>
</template>

<script>
import ImprovedChemicalStructureViewer from './ImprovedChemicalStructureViewer.vue'
import ComparisonModal from './ComparisonModal.vue'
import SimilarityComparison from './SimilarityComparison.vue'
import ocsrService from '@/services/ocsrService'
import depictionService from '@/services/depictionService'
import similarityService from '@/services/similarityService'
import { getApiImageUrl } from '@/services/api'
import eventBus from '@/utils/eventBus';

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
    },
    // Add prop for segment selection state
    isSelected: {
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
      findingMCS: false, // Property for MCS finding
      // New properties for engine selection
      selectedEngine: null, // Will store 'decimer', 'molnextr', or 'molscribe'
      // New property to enable/disable auto analysis
      autoAnalysisEnabled: true
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
    // Watch for engine results to calculate similarity stats and auto-run full analysis
    allEnginesLoaded: {
      handler(allLoaded) {
        if (allLoaded && !this.hasRunFullAnalysis) {
          this.calculateQuickSimilarity();
          
          // Automatically run the full analysis when in comparison mode and engines are loaded
          if (this.comparisonMode && this.canCompare && this.autoAnalysisEnabled) {
            // Add a small delay to ensure UI is responsive
            setTimeout(() => {
              this.compareAcrossEngines();
            }, 300);
          }
        }
      }
    },
    // Watch for when user enters comparison mode to automatically run analysis
    comparisonMode: {
      handler(newValue) {
        if (newValue && this.allEnginesLoaded && !this.hasRunFullAnalysis && this.canCompare && this.autoAnalysisEnabled) {
          // If user just entered comparison mode and engines are already loaded, run analysis
          setTimeout(() => {
            this.compareAcrossEngines();
          }, 300);
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
      this.selectedEngine = null; // Reset selected engine

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
      if (this.decimerResult?.smiles) validSmiles.push({ engine: 'decimer', smiles: this.decimerResult.smiles });
      if (this.molnextrResult?.smiles) validSmiles.push({ engine: 'molnextr', smiles: this.molnextrResult.smiles });
      if (this.molscribeResult?.smiles) validSmiles.push({ engine: 'molscribe', smiles: this.molscribeResult.smiles });

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
      // Instead of showing context directly in the SegmentViewer,
      // emit an event that will be caught by the parent component and relayed to the PDF viewer
      if (!this.segment) return;
      
      // Emit to the parent that we want to show this segment in context
      this.$emit('show-in-context', this.segment);
      
      // Also emit a global event using our custom EventBus that the PDF viewer component can listen for
      eventBus.emit('show-segment-in-context', this.segment);
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

        // FIXED: Construct the URL with the proper format for both development and production
        // Instead of using /api path directly, construct the path correctly with getApiImageUrl
        const apiPath = `/decimer/get_highlighted_page/${encodeURIComponent(segmentFilename)}?pdf_filename=${encodeURIComponent(pdfFilename)}`;
        const url = getApiImageUrl(apiPath);

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

      // No need to explicitly call compareAcrossEngines() here as it will be triggered 
      // automatically by the watcher when engines are loaded

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
        // Apply the URL conversion to ensure it works in both development and production
        this.segmentUrl = getApiImageUrl(this.segment.imageUrl);
        this.isLoading = false;
        return;
      }

      try {
        if (this.segment.path) {
          // Pass just the segment path to getApiImageUrl - it will construct the right URL
          // The helper will detect the "all_segments" path pattern and add the necessary prefix
          this.segmentUrl = getApiImageUrl(this.segment.path);
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
      this.hasRunFullAnalysis = true; // Set this to true to prevent duplicate runs

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
          message: 'Full analysis completed automatically'
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
    },
    // Add method for toggling segment selection
    toggleSelection() {
      this.$emit('toggle-selection')
    },
    // New methods for engine selection
    selectPrediction(engine) {
      // Toggle selection if clicking the same engine
      if (this.selectedEngine === engine) {
        this.selectedEngine = null;
      } else {
        this.selectedEngine = engine;
      }
    },

    getEngineDisplayName(engine) {
      const displayNames = {
        'decimer': 'DECIMER',
        'molnextr': 'MolNexTR',
        'molscribe': 'MolScribe'
      };
      return displayNames[engine] || engine;
    },

    applySelectedPrediction() {
      if (!this.selectedEngine || !this.segment) return;

      let selectedResult = null;

      // Get the selected result object
      if (this.selectedEngine === 'decimer' && this.decimerResult) {
        selectedResult = this.decimerResult;
      } else if (this.selectedEngine === 'molnextr' && this.molnextrResult) {
        selectedResult = this.molnextrResult;
      } else if (this.selectedEngine === 'molscribe' && this.molscribeResult) {
        selectedResult = this.molscribeResult;
      }

      if (!selectedResult || !selectedResult.smiles) {
        this.$emit('error', 'No valid structure in the selected prediction');
        return;
      }

      // Create structure object with the correct metadata
      const updatedStructure = {
        segmentId: this.segment.id,
        imageUrl: this.segment.imageUrl || this.segment.path,
        filename: this.segment.filename,
        smiles: selectedResult.smiles,
        molfile: selectedResult.molfile || null,
        engine: this.selectedEngine,
        name: this.segment.filename,
        pdfId: this.segment.pdfId,
        useCoordinates: this.shouldUseCoordinates,
        selectedFromComparison: true, // Mark that this was chosen from comparison
        timestamp: new Date().toISOString()
      };

      // Emit event with the selected structure
      this.$emit('prediction-selected', updatedStructure);

      // Automatically mark this segment as correct since the user selected the best prediction
      if (!this.isSelected) {
        this.$emit('toggle-selection');
      }

      // Show success notification
      this.$emit('notification', {
        type: 'success',
        message: `Updated structure with ${this.getEngineDisplayName(this.selectedEngine)} prediction`
      });

      // Exit comparison mode and go back to normal view
      this.comparisonMode = false;
    },
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
  border-radius: 20px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.08), 0 6px 12px rgba(0, 0, 0, 0.04);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
  position: relative;
  border: 1px solid rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(10px);

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
    border-radius: 20px;

    .empty-icon {
      margin-bottom: 1.5rem;
      color: #94a3b8;
      filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.1));
      animation: float 3s ease-in-out infinite;
    }

    p {
      font-size: 1.25rem;
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
      padding: 1.75rem;

      /* Header styling */
      .segment-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 1.75rem;

        .segment-title-section {
          display: flex;
          flex-direction: column;
          gap: 0.625rem;

          .segment-title {
            font-size: 1.75rem;
            font-weight: 700;
            margin: 0;
            background: linear-gradient(90deg, #1e293b 0%, #334155 100%);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            letter-spacing: -0.01em;
            text-shadow: 0 1px 1px rgba(255, 255, 255, 0.7);
          }

          /* Selection checkbox styling */
          .segment-selection-control {
            display: flex;
            align-items: center;

            .selection-checkbox {
              display: flex;
              align-items: center;
              gap: 0.625rem;
              font-size: 0.9375rem;
              color: #334155;
              cursor: pointer;
              transition: all 0.2s ease;

              input[type="checkbox"] {
                cursor: pointer;
                width: 20px;
                height: 20px;
                margin: 0;
                appearance: none;
                -webkit-appearance: none;
                background-color: white;
                border: 2px solid #cbd5e1;
                border-radius: 6px;
                transition: all 0.2s ease;
                position: relative;

                &:checked {
                  background-color: #4f46e5;
                  border-color: #4f46e5;
                  box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.2);
                }

                &:hover {
                  border-color: #4f46e5;
                }
              }

              .checkbox-label {
                font-weight: 500;
                transition: color 0.2s ease;
              }

              &:hover .checkbox-label {
                color: #4f46e5;
              }
            }
          }
        }

        .segment-actions {
          display: flex;
          gap: 0.625rem;

          .view-context-btn {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 0.75rem;
            border-radius: 10px;
            font-weight: 500;
            font-size: 0.875rem;
            border: none;
            cursor: pointer;
            background: linear-gradient(135deg, #ffdd43 0%, #ffb70f 100%);
            box-shadow: 0 2px 5px rgba(100, 116, 139, 0.3);
            transition: all 0.3s ease;
            color: white;

            .btn-content {
              display: flex;
              align-items: center;
              gap: 0.5rem;
            }

            .context-icon {
              opacity: 0.9;
            }

            &:hover {
              transform: translateY(-2px);
              box-shadow: 0 4px 8px rgba(100, 116, 139, 0.4);
              background: linear-gradient(135deg, #fff4d0 0%, #c9af44 100%);
              color: #1e293b;
            }

            &:active {
              transform: translateY(0);
              box-shadow: 0 2px 4px rgba(100, 116, 139, 0.3);
            }
          }

          .btn-action {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 38px;
            height: 38px;
            border: none;
            border-radius: 10px;
            background-color: rgba(241, 245, 249, 0.7);
            color: #64748b;
            cursor: pointer;
            transition: all 0.3s ease;
            backdrop-filter: blur(4px);
            border: 1px solid rgba(226, 232, 240, 0.6);
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);

            &:hover {
              background-color: white;
              color: #334155;
              transform: translateY(-2px);
              box-shadow: 0 4px 8px rgba(0, 0, 0, 0.08);
              border-color: rgba(226, 232, 240, 0.8);
            }

            &:active {
              transform: translateY(0px);
            }

            &.btn-close:hover {
              background-color: #fee2e2;
              color: #ef4444;
              border-color: rgba(254, 202, 202, 0.8);
            }
          }
        }
      }

      /* Section headers */
      .section-headers {
        display: flex;
        justify-content: space-between;
        margin-bottom: 1.25rem;
        padding: 0 1rem;

        .header-item {
          display: flex;
          align-items: center;
          gap: 0.625rem;

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
            letter-spacing: -0.01em;
          }
        }
      }

      /* Content panels */
      .content-panels {
        display: flex;
        gap: 1.75rem;
        height: 100%;
        margin-bottom: 1.75rem;

        @media (max-width: 768px) {
          flex-direction: column;
        }

        .panel {
          flex: 1;
          display: flex;
          flex-direction: column;
          border-radius: 16px;
          background-color: rgba(255, 255, 255, 0.9);
          box-shadow: 0 6px 18px rgba(0, 0, 0, 0.06);
          overflow: hidden;
          height: fit-content;
          transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.4s cubic-bezier(0.16, 1, 0.3, 1);
          border: 1px solid rgba(255, 255, 255, 0.4);
         
          &:hover {
            transform: translateY(-4px);
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.1);
          }

          /* Original panel specific styling */
          &.original-panel {
            .download-container {
              display: flex;
              justify-content: flex-end;
              padding: 0.875rem 1.125rem;
              border-bottom: 1px solid rgba(226, 232, 240, 0.7);

              .download-btn {
                display: flex;
                align-items: center;
                gap: 0.5rem;
                border: none;
                background-color: rgba(241, 245, 249, 0.8);
                color: #334155;
                font-size: 0.875rem;
                font-weight: 500;
                padding: 0.5rem 0.75rem;
                               border-radius: 8px;
                cursor: pointer;
                transition: all 0.25s ease;
                border: 1px solid rgba(226, 232, 240, 0.8);
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
                backdrop-filter: blur(4px);

                .download-icon {
                  color: #64748b;
                  transition: color 0.2s ease;
                }

                &:hover {
                  background-color: white;
                  border-color: #cbd5e1;
                  box-shadow: 0 3px 6px rgba(0, 0, 0, 0.08);
                  transform: translateY(-1px);

                  .download-icon {
                    color: #4f46e5;
                  }
                }

                &:active {
                  transform: translateY(0);
                }
              }
            }

            .image-container {
              display: flex;
              align-items: center;
              justify-content: center;
              padding: 1.75rem;
              background-color: white;
              min-height: 300px;
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
                backdrop-filter: blur(6px);

                .loader-pulse {
                  width: 60px;
                  height: 60px;
                  border-radius: 50%;
                  background-color: rgba(79, 70, 229, 0.2);
                  box-shadow: 0 0 20px rgba(79, 70, 229, 0.4);
                  animation: pulse 1.5s ease-in-out infinite;

                  &:before,
                  &:after {
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
                max-height: 300px;
                object-fit: contain;
                border-radius: 8px;
                transition: all 0.3s ease;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);

                &:hover {
                  transform: scale(1.02);
                  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.12);
                }
              }
            }

            .metadata-container {
              padding: 1.25rem;
              border-top: 1px solid rgba(226, 232, 240, 0.7);
              background: linear-gradient(135deg, #f8fafc 0%, rgba(255, 255, 255, 0.9) 100%);

              .metadata-section,
              .processing-info {
                margin-bottom: 0.875rem;

                &:last-child {
                  margin-bottom: 0;
                }
              }

              .processing-info {
                border-top: 1px dashed #e2e8f0;
                padding-top: 0.875rem;
                margin-top: 0.875rem;
              }

              .info-row {
                display: flex;
                align-items: center;
                margin-bottom: 0.625rem;

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
                    background-color: rgba(79, 70, 229, 0.1);
                    padding: 0.125rem 0.5rem;
                    border-radius: 4px;
                    font-size: 0.8125rem;
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
              padding: 0.875rem 1.125rem;
              border-bottom: 1px solid rgba(226, 232, 240, 0.7);
              background: linear-gradient(to right, rgba(79, 70, 229, 0.02), rgba(79, 70, 229, 0.08));

              .structure-title {
                               font-weight: 600;
                color: #0f172a;
                font-size: 1.0625rem;
              }

              .structure-actions {
                display: flex;
                align-items: center;
                gap: 0.625rem;

                .action-btn {
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  width: 32px;
                  height: 32px;
                  border-radius: 8px;
                  border: none;
                  background-color: rgba(241, 245, 249, 0.8);
                  color: #64748b;
                  cursor: pointer;
                  transition: all 0.2s ease;
                  border: 1px solid rgba(226, 232, 240, 0.8);

                  &:hover {
                    background-color: white;
                    color: #4f46e5;
                    transform: translateY(-1px);
                    box-shadow: 0 3px 6px rgba(0, 0, 0, 0.08);
                  }

                  &:active {
                    transform: translateY(0);
                  }
                }

                .download-btn {
                  display: flex;
                  align-items: center;
                  gap: 0.5rem;
                  border: none;
                  background-color: rgba(241, 245, 249, 0.8);
                  color: #334155;
                  font-size: 0.875rem;
                  font-weight: 500;
                  padding: 0.5rem 0.75rem;
                  border-radius: 8px;
                  cursor: pointer;
                  transition: all 0.25s ease;
                  border: 1px solid rgba(226, 232, 240, 0.8);

                  .download-icon {
                    color: #64748b;
                    transition: color 0.2s ease;
                  }

                  &:hover {
                    background-color: white;
                    border-color: #cbd5e1;
                    box-shadow: 0 3px 6px rgba(0, 0, 0, 0.08);
                    transform: translateY(-1px);

                    .download-icon {
                      color: #4f46e5;
                    }
                  }

                  &:active {
                    transform: translateY(0);
                  }
                }
              }
            }

            .structure-visualization {
              position: relative;
              padding: 1.75rem;
              background-color: white;
              min-height: 300px;

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
                      max-height: 300px;
                      filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.1));
                      transition: filter 0.3s ease, transform 0.3s ease;

                      &:hover {
                        filter: drop-shadow(0 8px 16px rgba(0, 0, 0, 0.15));
                        transform: scale(1.02);
                      }
                    }
                  }
                }
              }
            }

            .smiles-container {
              padding: 1.5rem 1.25rem;
              border-top: 1px solid rgba(226, 232, 240, 0.7);
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
                    box-shadow: 0 0 10px rgba(79, 70, 229, 0.6);
                  }
                }
              }

              .smiles-content {
                .smiles-box {
                  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
                  background-color: white;
                  padding: 1.25rem;
                  border-radius: 12px;
                  font-size: 0.9rem;
                  color: #334155;
                  overflow-x: auto;
                  white-space: pre-wrap;
                  word-break: break-all;
                  border: 1px solid rgba(226, 232, 240, 0.8);
                  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04), inset 0 1px 0 rgba(255, 255, 255, 0.8);
                  transition: all 0.3s ease;
                  position: relative;

                  &:hover {
                    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.8);
                    border-color: rgba(79, 70, 229, 0.3);
                    transform: translateY(-2px);
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
              gap: 0.625rem;
              padding: 0.875rem 1.25rem;
              border-top: 1px solid rgba(226, 232, 240, 0.7);
              background-color: #f8fafc;

              .tag {
                display: flex;
                align-items: center;
                gap: 0.375rem;
                font-size: 0.75rem;
                padding: 0.375rem 0.625rem;
                border-radius: 6px;
                font-weight: 500;
                transition: all 0.2s ease;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);

                &:hover {
                  transform: translateY(-1px);
                  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.08);
                }

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

                &.selection-tag {
                  background-color: rgba(16, 185, 129, 0.1);
                  color: #10b981;
                  border: 1px solid rgba(16, 185, 129, 0.3);
                }
              }
            }
          }
        }
      }

      /* Compare callout */
      .compare-callout {
        display: flex;
        align-items: center;
        padding: 1.5rem;
        background: linear-gradient(135deg, rgba(79, 70, 229, 0.05) 0%, rgba(79, 70, 229, 0.12) 100%);
        border-radius: 16px;
        border: 1px solid rgba(79, 70, 229, 0.2);
        box-shadow: 0 6px 12px rgba(79, 70, 229, 0.06);
        margin-top: auto;
        position: relative;
        overflow: hidden;

        &::before {
          content: '';
          position: absolute;
          top: -10px;
          right: -10px;
          width: 80px;
          height: 80px;
          border-radius: 50%;
          background: radial-gradient(circle, rgba(79, 70, 229, 0.3) 0%, transparent 70%);
          opacity: 0.6;
          z-index: 0;
        }

        .callout-icon {
          flex-shrink: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 44px;
          height: 44px;
          background-color: rgba(79, 70, 229, 0.12);
          border-radius: 12px;
          margin-right: 1.25rem;
          position: relative;
          z-index: 1;
          border: 1px solid rgba(79, 70, 229, 0.2);
          box-shadow: 0 4px 8px rgba(79, 70, 229, 0.1);
          backdrop-filter: blur(4px);

          .info-icon {
            color: #4f46e5;
            filter: drop-shadow(0 1px 2px rgba(79, 70, 229, 0.3));
          }
        }

        .callout-text {
          flex: 1;
          position: relative;
          z-index: 1;

          p {
            margin: 0;
            color: #334155;
            font-weight: 500;
            font-size: 1rem;
          }
        }

        .compare-btn {
          flex-shrink: 0;
          display: flex;
          align-items: center;
          gap: 0.625rem;
          background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);
          color: white;
          border: none;
          padding: 0.75rem 1.25rem;
          border-radius: 12px;
          font-weight: 500;
          font-size: 0.9375rem;
          cursor: pointer;
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          box-shadow: 0 4px 10px rgba(79, 70, 229, 0.25);
          position: relative;
          z-index: 1;
          overflow: hidden;

          &::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.2) 0%, rgba(255, 255, 255, 0) 100%);
            opacity: 0;
            transition: opacity 0.3s ease;
            z-index: -1;
          }

          .btn-icon {
            opacity: 0.9;
          }

          &:hover {
            background: linear-gradient(135deg, #4338ca 0%, #4f46e5 100%);
            transform: translateY(-2px);
            box-shadow: 0 8px 16px rgba(79, 70, 229, 0.3);
          }

          &:active {
            transform: translateY(0);
          }

          &.pulse-effect {
            animation: subtle-pulse 3s infinite;
          }
        }
      }
    }

    /* IMPROVED Comparison mode styling */
    .comparison-mode {
      padding: 1.75rem;
      display: flex;
      flex-direction: column;
      height: 100%;
      overflow-y: auto;

      &::-webkit-scrollbar {
        width: 8px;
      }

      &::-webkit-scrollbar-track {
        background: rgba(241, 245, 249, 0.6);
        border-radius: 8px;
      }

      &::-webkit-scrollbar-thumb {
        background: rgba(148, 163, 184, 0.5);
        border-radius: 8px;

        &:hover {
          background: rgba(100, 116, 139, 0.6);
        }
      }

      .comparison-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1.75rem;
        padding-bottom: 1.25rem;
        border-bottom: 1px solid rgba(226, 232, 240, 0.7);

        .comparison-title-section {
          .comparison-title {
            display: flex;
            align-items: center;
            gap: 0.625rem;
            font-size: 1.625rem;
            font-weight: 700;
            color: #0f172a;
            margin: 0 0 0.375rem 0;
            letter-spacing: -0.01em;

            .title-icon {
              color: #4f46e5;
              filter: drop-shadow(0 2px 4px rgba(79, 70, 229, 0.3));
            }
          }

          .comparison-description {
            color: #64748b;
            margin: 0;
            font-size: 0.9375rem;
          }
        }

        .header-actions {
          display: flex;
          align-items: center;
          gap: 1rem;

          .coordinate-display-option {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.875rem;
            color: #475569;
            cursor: pointer;
            user-select: none;

            input[type="checkbox"] {
              appearance: none;
              -webkit-appearance: none;
              width: 20px;
              height: 20px;
              border: 2px solid #cbd5e1;
              border-radius: 6px;
              margin: 0;
              position: relative;
              cursor: pointer;
              transition: all 0.2s ease;
              background-color: white;

              &:checked {
                background-color: #4f46e5;
                border-color: #4f46e5;
                box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.2);
              }

              &:hover {
                border-color: #4f46e5;
              }
            }

            .option-label {
              font-weight: 500;
              cursor: pointer;
              transition: color 0.2s ease;

              &:hover {
                color: #334155;
              }
            }
          }

          .back-btn {
            display: flex;
            align-items: center;
            gap: 0.625rem;
            background-color: white;
            border: 1px solid rgba(226, 232, 240, 0.8);
            color: #334155;
            font-size: 0.875rem;
            font-weight: 500;
            padding: 0.625rem 1.125rem;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.02);

            &:hover {
              background-color: #f8fafc;
              border-color: #cbd5e1;
              transform: translateY(-1px);
              box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05);
            }

            &:active {
              transform: translateY(0);
            }
          }
        }
      }

      .comparison-content {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 1.75rem;

        /* Comparison layout styling */
        .comparison-layout {
          display: grid;
          grid-template-columns: 250px 1fr;
          gap: 1.75rem;

          @media (max-width: 768px) {
            grid-template-columns: 1fr;
          }

          .column-title {
            font-size: 1.125rem;
            font-weight: 600;
            margin: 0 0 1.125rem 0;
            display: flex;
            align-items: center;
            gap: 0.625rem;
            color: #334155;
            letter-spacing: -0.01em;

            .column-icon {
              color: #4f46e5;
              filter: drop-shadow(0 1px 2px rgba(79, 70, 229, 0.2));
            }
          }

          /* Original segment styling */
          .original-segment-column {
            .segment-preview {
              background: white;
              border-radius: 16px;
              overflow: hidden;
              box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
              display: flex;
              flex-direction: column;
              border: 1px solid rgba(255, 255, 255, 0.6);

              .original-img {
                max-width: 100%;
                max-height: 220px;
                object-fit: contain;
                padding: 1.25rem;
                background: white;
                transition: transform 0.3s ease;

                &:hover {
                  transform: scale(1.05);
                }
              }

              .segment-file-info {
                background: linear-gradient(to bottom, #f8fafc, rgba(241, 245, 249, 0.7));
                padding: 1rem;
                border-top: 1px solid rgba(226, 232, 240, 0.7);

                .file-info-row {
                  margin-bottom: 0.625rem;
                  display: flex;
                  gap: 0.625rem;
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
              min-height: 300px;
              padding: 2rem;
              background: rgba(255, 255, 255, 0.6);
              border-radius: 16px;
              box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
              border: 1px solid rgba(226, 232, 240, 0.8);
              backdrop-filter: blur(8px);

              .fancy-spinner {
                position: relative;
                width: 64px;
                height: 64px;
                margin-bottom: 1.5rem;

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
                  width: 16px;
                  height: 16px;
                  border-radius: 50%;
                  background-color: #4f46e5;
                  box-shadow: 0 0 10px rgba(79, 70, 229, 0.6);
                  animation: pulse 1s ease infinite alternate;
                }
              }

              .loading-text {
                font-weight: 500;
                color: #334155;
                font-size: 1.0625rem;
                text-align: center;
                max-width: 300px;
              }
            }

            .engine-results-grid {
              display: grid;
              grid-template-columns: repeat(3, 1fr);
              gap: 1.5rem;

              @media (max-width: 1200px) {
                grid-template-columns: repeat(2, 1fr);
              }

              @media (max-width: 767px) {
                grid-template-columns: 1fr;
              }

              .engine-result-card {
                background: rgba(255, 255, 255, 0.8);
                border-radius: 20px;
                overflow: hidden;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
                display: flex;
                flex-direction: column;
                backdrop-filter: blur(10px);
                transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
                border: 1px solid rgba(255, 255, 255, 0.7);
                position: relative;

                &:hover {
                  transform: translateY(-6px);
                  box-shadow: 0 16px 32px rgba(0, 0, 0, 0.12);
                }

                &.result-selected {
                  border: 2px solid #10b981;
                  box-shadow: 0 12px 28px rgba(16, 185, 129, 0.2);
                  transform: translateY(-6px) scale(1.02);

                  .engine-content {
                    background-color: rgba(16, 185, 129, 0.05);
                  }
                }

                .engine-header {
                  display: flex;
                  align-items: center;
                  gap: 1rem;
                  padding: 1.25rem;
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
                    width: 44px;
                    height: 44px;
                    border-radius: 12px;
                    background-color: rgba(255, 255, 255, 0.9);
                    box-shadow: 0 6px 12px rgba(0, 0, 0, 0.1);
                    position: relative;
                    z-index: 1;
                    border: 1px solid rgba(255, 255, 255, 0.8);
                  }

                  .engine-name {
                    font-size: 1.25rem;
                    font-weight: 700;
                    margin: 0;
                    color: #0f172a;
                    position: relative;
                    z-index: 1;
                    text-shadow: 0 1px 2px rgba(255, 255, 255, 0.5);
                    letter-spacing: -0.01em;
                  }
                }

                .engine-content {
                  padding: 1.25rem;
                  display: flex;
                  flex-direction: column;
                  gap: 1rem;

                  .structure-preview {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 200px;
                    background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
                    border: 1px solid rgba(226, 232, 240, 0.8);
                    border-radius: 16px;
                    padding: 1.25rem;
                    position: relative;
                    overflow: hidden;
                    transition: transform 0.3s ease, box-shadow 0.3s ease;
                    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.04), inset 0 1px 0 rgba(255, 255, 255, 0.9);

                    &:hover {
                      transform: translateY(-3px);
                      box-shadow: 0 12px 24px rgba(0, 0, 0, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.9);
                    }

                    .result-image {
                      max-width: 100%;
                      max-height: 160px;
                      object-fit: contain;
                      filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.15));
                      transition: transform 0.3s ease, filter 0.3s ease;

                      &:hover {
                        transform: scale(1.05);
                        filter: drop-shadow(0 8px 16px rgba(0, 0, 0, 0.2));
                      }
                    }

                    .error-result {
                      padding: 1.5rem;
                      background: linear-gradient(145deg, #fee2e2 0%, #fecaca 100%);
                      border-radius: 12px;
                      color: #b91c1c;
                      font-size: 0.9375rem;
                      text-align: center;
                      display: flex;
                      flex-direction: column;
                      align-items: center;
                      gap: 0.75rem;
                      box-shadow: 0 6px 16px rgba(239, 68, 68, 0.15);
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
                        width: 60px;
                        height: 60px;
                        border-radius: 50%;
                        background: radial-gradient(circle, rgba(79, 70, 229, 0.2) 0%, rgba(79, 70, 229, 0.01) 70%);
                        animation: pulse 1.5s ease-in-out infinite;
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
                    border-radius: 10px;
                    padding: 0.75rem 1rem;
                    font-size: 0.875rem;
                    border: 1px solid #e2e8f0;

                    .smiles-label {
                      font-weight: 600;
                      margin-right: 0.625rem;
                      color: #334155;
                      white-space: nowrap;
                    }

                    .smiles-value {
                      font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
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
                      padding: 0.375rem;
                      border-radius: 6px;
                      transition: all 0.2s ease;

                      &:hover {
                        background: rgba(0, 0, 0, 0.05);
                        color: #4f46e5;
                      }
                    }
                  }

                  .engine-stats {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 0.875rem;
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
                          gap: 0.375rem;
                          color: #10b981;
                          background: rgba(16, 185, 129, 0.1);
                          border: 1px solid rgba(16, 185, 129, 0.3);
                          padding: 0.375rem 0.75rem;
                          border-radius: 12px;
                          font-size: 0.75rem;
                          transition: all 0.2s ease;

                          &:hover {
                            background: rgba(16, 185, 129, 0.15);
                            box-shadow: 0 2px 5px rgba(16, 185, 129, 0.2);
                          }

                          .coordinate-icon {
                            color: inherit;
                          }
                        }
                      }
                    }
                  }

                  // Selection button styles
                  .selection-actions {
                    margin-top: 1.25rem;

                    .select-prediction-btn {
                      display: flex;
                      align-items: center;
                      justify-content: center;
                      gap: 0.625rem;
                      width: 100%;
                      padding: 0.75rem;
                      border-radius: 12px;
                      border: none;
                      background-color: #f1f5f9;
                      color: #334155;
                      font-weight: 500;
                      font-size: 0.9375rem;
                      cursor: pointer;
                      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
                      position: relative;
                      overflow: hidden;
                      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);

                      &::before {
                        content: '';
                        position: absolute;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        background: linear-gradient(135deg, rgba(255, 255, 255, 0.2) 0%, rgba(255, 255, 255, 0) 100%);
                        opacity: 0;
                        transition: opacity 0.3s ease;
                        z-index: 1;
                      }

                      &:hover {
                        background-color: #e2e8f0;
                        transform: translateY(-2px);
                        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.08);

                        &::before {
                          opacity: 1;
                        }
                      }

                      &.active {
                        background: linear-gradient(135deg, #10b981 0%, #0d9488 100%);
                        color: white;
                        box-shadow: 0 4px 10px rgba(16, 185, 129, 0.2);
                      }

                      .btn-icon {
                        opacity: 0.9;
                        position: relative;
                        z-index: 2;
                      }

                      span {
                        position: relative;
                        z-index: 2;
                      }
                    }
                  }
                }
              }
            }
          }
        }

        /* Apply selection bar styling */
        .apply-selection-bar {
          margin-top: 1.5rem;
          padding: 1.25rem;
          background: linear-gradient(135deg, rgba(16, 185, 129, 0.04) 0%, rgba(16, 185, 129, 0.12) 100%);
          border: 1px solid rgba(16, 185, 129, 0.3);
          border-radius: 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 1rem;
          box-shadow: 0 6px 12px rgba(16, 185, 129, 0.1);
          position: relative;
          overflow: hidden;

          &::before {
            content: '';
            position: absolute;
            top: -20px;
            right: -20px;
            width: 100px;
            height: 100px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(16, 185, 129, 0.3) 0%, transparent 70%);
            opacity: 0.4;
            z-index: 0;
          }

          @media (max-width: 768px) {
            flex-direction: column;
          }

          .selection-message {
            display: flex;
            align-items: center;
            gap: 0.875rem;
            color: #065f46;
            font-size: 1rem;
            position: relative;
            z-index: 1;

            .message-icon {
              color: #10b981;
              flex-shrink: 0;
              filter: drop-shadow(0 1px 2px rgba(16, 185, 129, 0.3));
            }

            strong {
              font-weight: 600;
              background: linear-gradient(90deg, #065f46, #059669);
              -webkit-background-clip: text;
              background-clip: text;
              color: transparent;
            }
          }

          .apply-selection-btn {
            display: flex;
            align-items: center;
            gap: 0.625rem;
            background: linear-gradient(135deg, #10b981 0%, #0d9488 100%);
            color: white;
            border: none;
            padding: 0.875rem 1.5rem;
            border-radius: 12px;
            font-weight: 500;
            font-size: 1rem;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            white-space: nowrap;
            position: relative;
            z-index: 1;
            overflow: hidden;
            box-shadow: 0 4px 10px rgba(16, 185, 129, 0.25);

            @media (max-width: 768px) {
              width: 100%;
              justify-content: center;
            }

            &::before {
              content: '';
              position: absolute;
              top: 0;
              left: 0;
              width: 100%;
              height: 100%;
              background: linear-gradient(135deg, rgba(255, 255, 255, 0.2) 0%, rgba(255, 255, 255, 0) 100%);
              opacity: 0;
              transition: opacity 0.3s ease;
              z-index: -1;
            }

            &:hover {
              background: linear-gradient(135deg, #059669 0%, #0f766e 100%);
              transform: translateY(-2px);
              box-shadow: 0 8px 16px rgba(16, 185, 129, 0.3);

              &::before {
                opacity: 1;
              }
            }

            &:active {
              transform: translateY(0);
            }

            .btn-icon {
              opacity: 0.9;
            }
          }
        }
      }

      /* Similarity Summary styling */
      .similarity-summary {
        background: white;
        border-radius: 20px;
        overflow: hidden;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
        margin-top: 1.5rem;
        border: 1px solid rgba(255, 255, 255, 0.8);
        backdrop-filter: blur(8px);

        .summary-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 1.25rem 1.5rem;
          border-bottom: 1px solid rgba(226, 232, 240, 0.7);
          background: linear-gradient(to right, rgba(79, 70, 229, 0.02), rgba(79, 70, 229, 0.08));

          .summary-title {
            display: flex;
            align-items: center;
            gap: 0.625rem;
            margin: 0;
            font-size: 1.125rem;
            font-weight: 600;
            color: #334155;
            letter-spacing: -0.01em;

            .summary-icon {
              color: #4f46e5;
              filter: drop-shadow(0 1px 2px rgba(79, 70, 229, 0.3));
            }
          }

          .summary-toggle {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: #64748b;
            font-size: 0.875rem;
            cursor: pointer;
            padding: 0.375rem 0.75rem;
            border-radius: 8px;
            transition: all 0.2s ease;

            &:hover {
              background-color: rgba(241, 245, 249, 0.8);
              color: #334155;
            }

            .toggle-icon {
              color: inherit;
            }
          }
        }

        .quick-summary {
          padding: 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 1.5rem;

          .summary-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 1.25rem;

            .stat-card {
              background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
              border-radius: 16px;
              padding: 1.5rem;
              text-align: center;
              transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
              box-shadow: 0 4px 10px rgba(0, 0, 0, 0.04);
              border: 1px solid rgba(226, 232, 240, 0.8);
              position: relative;
              overflow: hidden;

              &::before {
                content: '';
                position: absolute;
                top: -10px;
                right: -10px;
                width: 60px;
                height: 60px;
                border-radius: 50%;
                background: radial-gradient(circle, rgba(0, 0, 0, 0.03) 0%, transparent 70%);
                opacity: 0.6;
                z-index: 0;
              }

              &:hover {
                transform: translateY(-4px);
                box-shadow: 0 10px 20px rgba(0, 0, 0, 0.08);
              }

              .stat-value {
                font-size: 2rem;
                font-weight: 700;
                margin-bottom: 0.75rem;
                color: #334155;
                position: relative;
                z-index: 1;

                &.identical {
                  color: #10b981;
                  display: flex;
                  align-items: center;
                  justify-content: center;

                  .identical-icon {
                    color: inherit;
                    filter: drop-shadow(0 2px 4px rgba(16, 185, 129, 0.3));
                  }
                }
              }

              .stat-label {
                font-size: 0.9375rem;
                color: #64748b;
                font-weight: 500;
                position: relative;
                z-index: 1;
              }

              &.high-agreement {
                .stat-value {
                  color: #10b981;
                  text-shadow: 0 1px 2px rgba(16, 185, 129, 0.2);
                }

                &::before {
                  background: radial-gradient(circle, rgba(16, 185, 129, 0.1) 0%, transparent 70%);
                }
              }

              &.medium-agreement {
                .stat-value {
                  color: #0ea5e9;
                  text-shadow: 0 1px 2px rgba(14, 165, 233, 0.2);
                }

                &::before {
                  background: radial-gradient(circle, rgba(14, 165, 233, 0.1) 0%, transparent 70%);
                }
              }

              &.low-agreement {
                .stat-value {
                  color: #f97316;
                  text-shadow: 0 1px 2px rgba(249, 115, 22, 0.2);
                }

                &::before {
                  background: radial-gradient(circle, rgba(249, 115, 22, 0.1) 0%, transparent 70%);
                }
              }
            }
          }
        }

        /* Analysis Action Buttons */
        .analysis-action-buttons {
          display: flex;
          flex-wrap: wrap;
          gap: 1rem;
          padding: 0 1.5rem 1.5rem;

          .highlight-common-btn,
          .analyze-btn {
            flex: 1;
            min-width: 200px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.625rem;
            padding: 0.875rem 1.25rem;
            border-radius: 12px;
            border: none;
            font-weight: 500;
            font-size: 0.9375rem;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.08);
            position: relative;
            overflow: hidden;

            &::before {
              content: '';
              position: absolute;
              top: 0;
              left: 0;
              width: 100%;
              height: 100%;
              background: linear-gradient(135deg, rgba(255, 255, 255, 0.2) 0%, rgba(255, 255, 255, 0) 100%);
              opacity: 0;
              transition: opacity 0.3s ease;
              z-index: 1;
            }

            &:hover:not(:disabled) {
              transform: translateY(-3px);

              &::before {
                opacity: 1;
              }
            }

            &:active:not(:disabled) {
              transform: translateY(0);
            }

            &:disabled {
              opacity: 0.6;
              cursor: not-allowed;
            }

            .btn-icon {
              opacity: 0.9;
              position: relative;
              z-index: 2;
            }

            span {
              position: relative;
              z-index: 2;
            }
          }

          .highlight-common-btn {
            background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%);
            color: white;

            &:hover:not(:disabled) {
              box-shadow: 0 8px 16px rgba(14, 165, 233, 0.3);
            }

            &:disabled {
              background: linear-gradient(135deg, #7dd3fc 0%, #38bdf8 100%);
            }
          }

          .analyze-btn {
            background: linear-gradient(135deg, #4f46e5 0%, #4338ca 100%);
            color: white;

            &:hover:not(:disabled) {
              box-shadow: 0 8px 16px rgba(79, 70, 229, 0.3);
            }

            &:disabled {
              background: linear-gradient(135deg, #a5b4fc 0%, #818cf8 100%);
            }
          }
        }

        .similarity-details {
          border-top: 1px solid rgba(226, 232, 240, 0.7);
          padding: 1.5rem;

          .run-analysis-prompt {
            text-align: center;
            color: #64748b;
            font-size: 1rem;
            padding: 2.5rem 0;
            background: linear-gradient(145deg, #f8fafc 0%, #f1f5f9 100%);
            border-radius: 12px;
            border: 1px dashed #cbd5e1;
            font-weight: 500;
          }

          .analysis-error {
            display: flex;
            align-items: center;
            gap: 0.875rem;
            color: #ef4444;
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            padding: 1.25rem;
            border-radius: 12px;

            .error-icon {
              color: inherit;
              flex-shrink: 0;
              filter: drop-shadow(0 1px 2px rgba(239, 68, 68, 0.3));
            }

            p {
              margin: 0;
              font-weight: 500;
            }
          }
        }
      }

      /* Footer actions */
      .comparison-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 1.75rem;
        padding-top: 1.75rem;
        border-top: 1px solid rgba(226, 232, 240, 0.7);

        @media (max-width: 768px) {
          flex-direction: column;
          gap: 1.25rem;
          align-items: stretch;
        }

        .refresh-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 0.625rem;
          background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);
          color: white;
          border: none;
          padding: 0.875rem 1.5rem;
          border-radius: 12px;
          font-weight: 500;
          font-size: 0.9375rem;
          cursor: pointer;
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          box-shadow: 0 4px 10px rgba(79, 70, 229, 0.25);
          position: relative;
          overflow: hidden;

          &::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.2) 0%, rgba(255, 255, 255, 0) 100%);
            opacity: 0;
            transition: opacity 0.3s ease;
          }

          &:hover:not(:disabled)::before {
            opacity: 1;
          }

          .refresh-icon {
            opacity: 0.9;
          }

          &:hover:not(:disabled) {
            background: linear-gradient(135deg, #4338ca 0%, #4f46e5 100%);
            transform: translateY(-3px);
            box-shadow: 0 8px 16px rgba(79, 70, 229, 0.3);
          }

          &:active:not(:disabled) {
            transform: translateY(0);
            box-shadow: 0 4px 8px rgba(79, 70, 229, 0.2);
          }

          &:disabled {
            background: linear-gradient(135deg, #a5b4fc 0%, #818cf8 100%);
            opacity: 0.7;
            cursor: not-allowed;
          }

          @media (max-width: 768px) {
            width: 100%;
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
  background-color: rgba(0, 0, 0, 0.85);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(8px);
  animation: fadeIn 0.3s ease;

  .context-view-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.25rem 1.5rem;
    background-color: rgba(255, 255, 255, 0.95);
    border-bottom: 1px solid #e2e8f0;
    backdrop-filter: blur(8px);

    h3 {
      margin: 0;
      font-size: 1.25rem;
      color: #0f172a;
      font-weight: 600;
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
      transition: all 0.2s ease;

      &:hover {
        background-color: #fee2e2;
        color: #ef4444;
        transform: rotate(90deg);
      }
    }
  }

  .context-view-content {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
    overflow: auto;

    .loading-context {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;

      .loader-pulse {
        width: 70px;
        height: 70px;
        border-radius: 50%;
        background-color: rgba(255, 255, 255, 0.2);
        animation: pulse 1.5s ease-in-out infinite;
        margin-bottom: 1.5rem;
        box-shadow: 0 0 30px rgba(255, 255, 255, 0.3);
      }
    }

    .context-image {
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      background-color: white;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
      border-radius: 4px;
      transition: transform 0.3s ease;

      &:hover {
        transform: scale(1.02);
      }
    }

    .context-error {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 1.25rem;
      color: white;

      svg {
        filter: drop-shadow(0 2px 8px rgba(255, 255, 255, 0.2));
      }

      p {
        margin: 0;
        font-size: 1.125rem;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
      }
    }
  }
}
</style>