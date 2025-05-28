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
            <div class="title-with-badge">
              <h3 class="segment-title">Segment #{{ segmentNumber }}</h3>
              <div class="status-badge" :class="{ 'status-selected': isSelected, 'status-processed': hasStructure }">
                <vue-feather 
                  :type="isSelected ? 'check-circle' : hasStructure ? 'cpu' : 'circle'" 
                  :size="14" 
                  class="status-icon"
                ></vue-feather>
                <span class="status-text">
                  {{ isSelected ? 'Verified' : hasStructure ? 'Processed' : 'Pending' }}
                </span>
              </div>
            </div>

            <!-- Improved selection control -->
            <div class="segment-selection-control">
              <div class="modern-toggle" @click="toggleSelection">
                <div class="toggle-track" :class="{ active: isSelected }">
                  <div class="toggle-thumb">
                    <vue-feather 
                      :type="isSelected ? 'check' : 'circle'" 
                      :size="12" 
                      class="toggle-icon"
                    ></vue-feather>
                  </div>
                </div>
                <span class="toggle-label">
                  {{ isSelected ? 'Verified as correct' : 'Mark as correct' }}
                </span>
              </div>
            </div>
          </div>

          <div class="segment-actions">
            <button class="action-btn context-btn" @click="showInContext" title="View in PDF Context">
              <vue-feather type="file-text" size="16" class="btn-icon"></vue-feather>
              <span class="btn-text">Context</span>
            </button>
            <button class="action-btn close-btn" @click="$emit('close')" title="Close">
              <vue-feather type="x" size="16"></vue-feather>
            </button>
          </div>
        </div>

        <div class="section-headers">
          <div class="header-item">
            <h4 class="section-title">Original Image</h4>
          </div>
          <div class="header-item processed" v-if="displayedStructure">
            <vue-feather type="check-circle" size="16" class="success-icon"></vue-feather>
            <h4 class="section-title">Processed Structure</h4>
          </div>
        </div>

        <div class="content-panels">
          <div class="panel original-panel">
            <div class="download-container">
              <button class="download-btn" @click="downloadSegmentImage">
                <vue-feather type="download" size="14" class="download-icon"></vue-feather>
                <span>Download</span>
              </button>
            </div>

            <div class="image-container">
              <div v-if="isLoading" class="loading-overlay">
                <div class="loading-spinner">
                  <div class="spinner-ring"></div>
                  <div class="spinner-ring"></div>
                  <div class="spinner-ring"></div>
                </div>
                <span class="loading-text">Loading segment...</span>
              </div>
              <img v-if="segmentUrl" :src="segmentUrl" alt="Chemical structure segment" class="segment-image"
                @load="handleImageLoaded" @error="handleImageError" />
            </div>

            <div class="metadata-container">
              <div class="metadata-section">
                <div class="info-grid">
                  <div class="info-item">
                    <div class="info-icon">
                      <vue-feather type="hash" size="14" class="icon"></vue-feather>
                    </div>
                    <div class="info-content">
                      <span class="info-label">Page</span>
                      <span class="info-value">{{ segment.pageNumber || '1' }}</span>
                    </div>
                  </div>
                  <div class="info-item">
                    <div class="info-icon">
                      <vue-feather type="file" size="14" class="icon"></vue-feather>
                    </div>
                    <div class="info-content">
                      <span class="info-label">Filename</span>
                      <span class="info-value truncate" :title="segment.filename">{{ segment.filename }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div v-if="displayedStructure" class="processing-info">
                <div class="processing-header">
                  <vue-feather type="zap" size="14" class="processing-icon"></vue-feather>
                  <span class="processing-title">Processing Details</span>
                </div>
                <div class="info-grid">
                  <div class="info-item">
                    <div class="info-icon engine-icon" :class="engineTagClass">
                      <vue-feather type="cpu" size="14" class="icon"></vue-feather>
                    </div>
                    <div class="info-content">
                      <span class="info-label">Engine</span>
                      <span class="info-value engine-badge" :class="engineTagClass">{{ displayedStructure.engine || 'Unknown' }}</span>
                    </div>
                  </div>
                  <div class="info-item">
                    <div class="info-icon">
                      <vue-feather type="clock" size="14" class="icon"></vue-feather>
                    </div>
                    <div class="info-content">
                      <span class="info-label">Processed</span>
                      <span class="info-value">{{ formatTimestamp(displayedStructure.timestamp) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Enhanced Edit Structure button -->
            <div v-if="displayedStructure" class="action-footer">
              <button class="edit-structure-btn" @click="showStructureEditor = true">
                <vue-feather type="edit-3" size="16" class="btn-icon" />
                <span>Edit Structure</span>
              </button>
            </div>
          </div>

          <div v-if="displayedStructure" class="panel structure-panel">
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
                <ImprovedChemicalStructureViewer v-if="hasStructure" :key="forceUpdateKey"
                  :smiles="displayedStructure.smiles" :molfile="displayedStructure.molfile"
                  :name="displayedStructure.name || `Compound ${segmentNumber}`"
                  :source-engine="displayedStructure.engine" :use-coordinates="shouldUseCoordinates"
                  @copied="handleCopied" @error="handleStructureError" @download-complete="handleDownloadComplete"
                  hide-controls />
              </div>
            </div>

            <div class="smiles-container">
              <div class="smiles-header">
                <span class="smiles-label">SMILES:</span>
              </div>
              <div class="smiles-content">
                <div class="smiles-box">{{ displayedStructure.smiles }}</div>
              </div>
            </div>

            <div class="tags-row">
              <div class="tag smiles-tag">
                <vue-feather type="code" size="14" class="tag-icon"></vue-feather>
                <span>Using SMILES</span>
              </div>
              <div class="tag engine-tag" :class="engineTagClass">
                <vue-feather type="cpu" size="14" class="tag-icon"></vue-feather>
                <span>{{ displayedStructure.engine || 'Unknown' }}</span>
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

            <button class="analyze-btn" @click="compareAcrossEngines" :disabled="!canCompare || isComparing">
              <vue-feather :type="isComparing ? 'loader' : 'activity'" :class="{ 'spin': isComparing }" size="16"
                class="btn-icon"></vue-feather>
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

    <!-- Structure Editor Modal -->
    <KetcherEditorModal :visible="showStructureEditor" :initialSmiles="displayedStructure?.smiles"
      :initialMolfile="displayedStructure?.molfile" @close="showStructureEditor = false"
      @apply="onStructureEditApply" />
  </div>
</template>

<script>
import ImprovedChemicalStructureViewer from './ImprovedChemicalStructureViewer.vue'
import ComparisonModal from './ComparisonModal.vue'
import SimilarityComparison from './SimilarityComparison.vue'
import KetcherEditorModal from './KetcherEditorModal.vue'
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
    SimilarityComparison,
    KetcherEditorModal
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
      autoAnalysisEnabled: true,
      // Structure editor modal state
      showStructureEditor: false,
      // New properties for structure updating fix
      currentStructure: null,
      forceUpdateKey: Date.now(),
    }
  },
  computed: {
    segmentNumber() {
      if (!this.segment) return 0
      return this.segment.segmentNumber || this.segment.id?.split('-')[1] || '?'
    },
    engineTagClass() {
      if (!this.displayedStructure || !this.displayedStructure.engine) return ''

      const engine = this.displayedStructure.engine.toLowerCase()
      if (engine.includes('decimer')) return 'decimer-tag'
      if (engine.includes('molnextr')) return 'molnextr-tag'
      if (engine.includes('molscribe')) return 'molscribe-tag'

      return ''
    },
    displayedStructure() {
      // Use the local edited structure if available, otherwise use the prop
      return this.currentStructure || this.processedStructure || null;
    },
    hasStructure() {
      return !!this.displayedStructure;
    },
    shouldUseCoordinates() {
      if (!this.displayedStructure) return false;

      // Check if useCoordinates flag is explicitly set
      if (this.displayedStructure.useCoordinates === true) {
        return true;
      }

      // Otherwise, use coordinates if:
      // 1. We have a molfile
      // 2. The engine is MolNexTR or MolScribe
      return !!this.displayedStructure.molfile &&
        (this.displayedStructure.engine === 'molnextr' ||
          this.displayedStructure.engine === 'molscribe');
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
    // Watch processedStructure prop to update local state
    processedStructure: {
      immediate: true,
      handler(newValue) {
        if (newValue) {
          // Make a deep copy to avoid reference issues
          this.currentStructure = JSON.parse(JSON.stringify(newValue));
        } else {
          this.currentStructure = null;
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
      this.currentStructure = null;

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
      if (!this.displayedStructure || !this.displayedStructure.smiles) return;

      try {
        navigator.clipboard.writeText(this.displayedStructure.smiles)
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
      if (!this.displayedStructure) return;

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

      // Update local state immediately
      this.currentStructure = updatedStructure;

      // Update force key to trigger re-render
      this.forceUpdateKey = Date.now();

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

    // FIXED: Improved onStructureEditApply method to properly update UI and ensure changes persist
    onStructureEditApply(payload) {
      // payload: { smiles: '...', molfile?: '...' }
      if (!payload || !payload.smiles) {
        this.$emit('error', 'No structure returned from editor');
        this.showStructureEditor = false;
        return;
      }

      // Create updated structure object
      if (!this.processedStructure) {
        this.$emit('error', 'Cannot update: no base structure available');
        this.showStructureEditor = false;
        return;
      }

      // Update local state immediately to reflect changes in the UI
      const updatedStructure = {
        ...this.processedStructure,
        smiles: payload.smiles,
        molfile: payload.molfile || this.processedStructure.molfile,
        engine: 'manual-edit',
        timestamp: new Date().toISOString(),
        name: this.processedStructure.name || `Edited Compound ${this.segmentNumber}`,
        editedFromOriginal: true
      };

      // Update local state
      this.currentStructure = updatedStructure;

      // Force component to re-render by updating the key
      this.forceUpdateKey = Date.now();

      console.log('Updated structure:', this.currentStructure);

      // Emit structure-edited event for parent component to update its stored structure
      this.$emit('structure-edited', updatedStructure);

      // Also emit prediction-selected event which is more consistently handled by parent components
      this.$emit('prediction-selected', updatedStructure);

      // Automatically mark this segment as correct since the user edited the structure
      if (!this.isSelected) {
        this.$emit('toggle-selection');
      }

      this.showStructureEditor = false;
      this.$emit('notification', {
        type: 'success',
        message: 'Structure updated from editor'
      });
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
        padding: 1.5rem;
        background: rgba(255, 255, 255, 0.8);
        border-radius: 16px;
        border: 1px solid rgba(226, 232, 240, 0.6);
        backdrop-filter: blur(8px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);

        .segment-title-section {
          display: flex;
          flex-direction: column;
          gap: 1rem;

          .title-with-badge {
            display: flex;
            align-items: center;
            gap: 1rem;

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

            .status-badge {
              display: flex;
              align-items: center;
              gap: 0.5rem;
              padding: 0.375rem 0.75rem;
              border-radius: 20px;
              font-size: 0.75rem;
              font-weight: 600;
              text-transform: uppercase;
              letter-spacing: 0.025em;
              transition: all 0.3s ease;
              border: 1px solid transparent;

              &.status-pending {
                background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
                color: #64748b;
                border-color: rgba(100, 116, 139, 0.2);
              }

              &.status-processed {
                background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
                color: #1d4ed8;
                border-color: rgba(29, 78, 216, 0.2);
                box-shadow: 0 2px 4px rgba(29, 78, 216, 0.1);
              }

              &.status-selected {
                background: linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%);
                color: #15803d;
                border-color: rgba(21, 128, 61, 0.2);
                box-shadow: 0 2px 4px rgba(21, 128, 61, 0.1);
              }

              .status-icon {
                filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.1));
              }
            }
          }

          /* Modern toggle switch styling */
          .segment-selection-control {
            .modern-toggle {
              display: flex;
              align-items: center;
              gap: 0.75rem;
              cursor: pointer;
              padding: 0.5rem;
              border-radius: 8px;
              transition: background-color 0.2s ease;

              &:hover {
                background-color: rgba(248, 250, 252, 0.8);
              }

              .toggle-track {
                position: relative;
                width: 2.75rem;
                height: 1.5rem;
                background: #e5e7eb;
                border-radius: 0.75rem;
                transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
                box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.1);

                .toggle-thumb {
                  position: absolute;
                  top: 0.125rem;
                  left: 0.125rem;
                  width: 1.25rem;
                  height: 1.25rem;
                  background: white;
                  border-radius: 50%;
                  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
                  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
                  display: flex;
                  align-items: center;
                  justify-content: center;

                  .toggle-icon {
                    transition: all 0.3s ease;
                    color: #9ca3af;
                  }
                }

                &.active {
                  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);

                  .toggle-thumb {
                    transform: translateX(1.25rem);
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.25);

                    .toggle-icon {
                      color: #10b981;
                    }
                  }
                }
              }

              .toggle-label {
                font-weight: 500;
                color: #374151;
                font-size: 0.875rem;
                transition: color 0.2s ease;
              }

              &:hover .toggle-label {
                color: #1f2937;
              }
            }
          }
        }

        .segment-actions {
          display: flex;
          gap: 0.75rem;
          align-items: flex-start;


          .action-btn {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.75rem 1rem;
            border: none;
            border-radius: 12px;
            font-weight: 500;
            font-size: 0.875rem;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06);
            backdrop-filter: blur(8px);

            &.context-btn {
              background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
              color: white;
              border: 1px solid rgba(59, 130, 246, 0.3);

              &:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 16px rgba(59, 130, 246, 0.3);
                background: linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%);
              }

              .btn-icon {
                filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.2));
              }
            }

            &.close-btn {
              width: 40px;
              height: 40px;
              justify-content: center;
              background: rgba(241, 245, 249, 0.8);
              color: #64748b;
              border: 1px solid rgba(226, 232, 240, 0.6);

              &:hover {
                background: #fee2e2;
                color: #ef4444;
                border-color: rgba(254, 202, 202, 0.8);
                transform: translateY(-2px) rotate(90deg);
                box-shadow: 0 8px 16px rgba(239, 68, 68, 0.2);
              }
            }

            &:active {
              transform: translateY(0);
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
                /* Material Design Blue - Professional styling */
                --download-primary: #E3F2FD;    /* Material Blue 50 */
                --download-secondary: #BBDEFB;  /* Material Blue 100 */
                --download-accent: #90CAF9;     /* Material Blue 200 */
                --download-text: #1565C0;       /* Material Blue 800 */
                --download-rgb: 21, 101, 192;

                display: flex;
                align-items: center;
                gap: 0.375rem;
                border: none;
                background: var(--download-secondary); /* Flat pastel blue */
                color: var(--download-text);
                font-size: 0.75rem;
                font-weight: 600;
                padding: 0.375rem 0.625rem;
                border-radius: 6px;
                cursor: pointer;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                border: 1px solid rgba(var(--download-rgb), 0.2);
                box-shadow: 0 2px 6px rgba(var(--download-rgb), 0.12);
                backdrop-filter: blur(8px);
                position: relative;
                overflow: hidden;

                /* Shine effect */
                &::before {
                  content: '';
                  position: absolute;
                  top: 0;
                  left: -100%;
                  width: 100%;
                  height: 100%;
                  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.3), transparent);
                  transition: left 0.6s;
                }

                .download-icon {
                  color: var(--download-text);
                  transition: all 0.3s ease;
                  width: 14px;
                  height: 14px;
                }

                span {
                  font-weight: 600;
                  letter-spacing: 0.01em;
                }

                &:hover {
                  background: var(--download-accent); /* Flat pastel hover */
                  box-shadow: 0 4px 12px rgba(var(--download-rgb), 0.2);
                  transform: translateY(-2px) scale(1.02);

                  &::before {
                    left: 100%;
                  }

                  .download-icon {
                    transform: scale(1.1);
                    filter: brightness(1.1);
                  }
                }

                &:active {
                  transform: translateY(-1px) scale(1.01);
                  box-shadow: 0 2px 6px rgba(var(--download-rgb), 0.15);
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
                flex-direction: column;
                align-items: center;
                justify-content: center;
                background: rgba(255, 255, 255, 0.95);
                z-index: 2;
                backdrop-filter: blur(8px);
                border-radius: 8px;

                .loading-spinner {
                  position: relative;
                  width: 60px;
                  height: 60px;
                  margin-bottom: 1.25rem;

                  .spinner-ring {
                    position: absolute;
                    width: 100%;
                    height: 100%;
                    border: 3px solid transparent;
                    border-radius: 50%;
                    animation: loading-spinner 1.2s linear infinite;

                    &:nth-child(1) {
                      border-top-color: #3b82f6;
                      animation-delay: 0s;
                    }

                    &:nth-child(2) {
                      border-right-color: #8b5cf6;
                      animation-delay: -0.4s;
                      width: 80%;
                      height: 80%;
                      top: 10%;
                      left: 10%;
                    }

                    &:nth-child(3) {
                      border-bottom-color: #06b6d4;
                      animation-delay: -0.8s;
                      width: 60%;
                      height: 60%;
                      top: 20%;
                      left: 20%;
                    }
                  }
                }

                .loading-text {
                  font-weight: 500;
                  color: #64748b;
                  font-size: 0.875rem;
                  text-align: center;
                  animation: subtle-pulse 2s ease-in-out infinite;
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
              padding: 1.5rem;
              border-top: 1px solid rgba(226, 232, 240, 0.7);
              background: linear-gradient(135deg, #f8fafc 0%, rgba(255, 255, 255, 0.95) 100%);
              backdrop-filter: blur(8px);

              .metadata-section,
              .processing-info {
                margin-bottom: 1.25rem;

                &:last-child {
                  margin-bottom: 0;
                }
              }

              .processing-info {
                border-top: 1px dashed #e2e8f0;
                padding-top: 1.25rem;
                margin-top: 1.25rem;

                .processing-header {
                  display: flex;
                  align-items: center;
                  gap: 0.5rem;
                  margin-bottom: 0.875rem;

                  .processing-icon {
                    color: #f59e0b;
                    filter: drop-shadow(0 1px 2px rgba(245, 158, 11, 0.3));
                  }

                  .processing-title {
                    font-weight: 600;
                    color: #374151;
                    font-size: 0.875rem;
                    text-transform: uppercase;
                    letter-spacing: 0.025em;
                  }
                }
              }

              .info-grid {
                display: grid;
                gap: 0.875rem;

                .info-item {
                  display: flex;
                  align-items: center;
                  gap: 0.75rem;
                  padding: 0.75rem;
                  background: rgba(255, 255, 255, 0.8);
                  border-radius: 10px;
                  border: 1px solid rgba(226, 232, 240, 0.5);
                  transition: all 0.3s ease;

                  &:hover {
                    background: rgba(255, 255, 255, 0.95);
                    border-color: rgba(79, 70, 229, 0.2);
                    transform: translateY(-1px);
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.08);
                  }

                  .info-icon {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    width: 32px;
                    height: 32px;
                    background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
                    border-radius: 8px;
                    border: 1px solid rgba(148, 163, 184, 0.2);
                    flex-shrink: 0;

                    &.engine-icon {
                      background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
                      border-color: rgba(59, 130, 246, 0.3);

                      &.decimer-tag {
                        background: linear-gradient(135deg, #fed7aa 0%, #fdba74 100%);
                        border-color: rgba(249, 115, 22, 0.3);
                      }

                      &.molnextr-tag {
                        background: linear-gradient(135deg, #a7f3d0 0%, #6ee7b7 100%);
                        border-color: rgba(16, 185, 129, 0.3);
                      }

                      &.molscribe-tag {
                        background: linear-gradient(135deg, #e9d5ff 0%, #d8b4fe 100%);
                        border-color: rgba(123, 31, 162, 0.3);
                      }
                    }

                    .icon {
                      color: #64748b;
                      filter: drop-shadow(0 1px 1px rgba(0, 0, 0, 0.1));
                    }
                  }

                  .info-content {
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                    gap: 0.25rem;

                    .info-label {
                      font-weight: 600;
                      color: #374151;
                      font-size: 0.75rem;
                      text-transform: uppercase;
                      letter-spacing: 0.025em;
                      opacity: 0.8;
                    }

                    .info-value {
                      color: #1f2937;
                      font-size: 0.875rem;
                      font-weight: 500;

                      &.truncate {
                        white-space: nowrap;
                        overflow: hidden;
                        text-overflow: ellipsis;
                        max-width: 200px;
                      }

                      &.engine-badge {
                        display: inline-flex;
                        align-items: center;
                        padding: 0.25rem 0.625rem;
                        border-radius: 6px;
                        font-size: 0.75rem;
                        font-weight: 600;
                        text-transform: uppercase;
                        letter-spacing: 0.025em;

                        &.decimer-tag {
                          background: rgba(249, 115, 22, 0.1);
                          color: #ea580c;
                          border: 1px solid rgba(249, 115, 22, 0.3);
                        }

                        &.molnextr-tag {
                          background: rgba(16, 185, 129, 0.1);
                          color: #059669;
                          border: 1px solid rgba(16, 185, 129, 0.3);
                        }

                        &.molscribe-tag {
                          background: rgba(123, 31, 162, 0.1);
                          color: #7c2d92;
                          border: 1px solid rgba(123, 31, 162, 0.3);
                        }
                      }
                    }
                  }
                }
              }
            }

            /* Enhanced action footer styling */
            .action-footer {
              padding: 1.25rem;
              border-top: 1px solid rgba(226, 232, 240, 0.7);
              background: linear-gradient(135deg, #f8fafc 0%, rgba(255, 255, 255, 0.9) 100%);
              display: flex;
              justify-content: center;

              .edit-structure-btn {
                display: flex;
                align-items: center;
                gap: 0.625rem;
                padding: 0.875rem 1.5rem;
                background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
                color: white;
                border: none;
                border-radius: 12px;
                font-weight: 600;
                font-size: 0.9375rem;
                cursor: pointer;
                transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
                box-shadow: 0 4px 12px rgba(59, 130, 246, 0.25);
                border: 1px solid rgba(59, 130, 246, 0.3);
                backdrop-filter: blur(8px);
                position: relative;
                overflow: hidden;

                /* Shine effect */
                &::before {
                  content: '';
                  position: absolute;
                  top: 0;
                  left: -100%;
                  width: 100%;
                  height: 100%;
                  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.3), transparent);
                  transition: left 0.6s;
                }

                .btn-icon {
                  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.2));
                  transition: transform 0.3s ease;
                }

                &:hover {
                  background: linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%);
                  transform: translateY(-2px) scale(1.02);
                  box-shadow: 0 8px 20px rgba(59, 130, 246, 0.35);

                  &::before {
                    left: 100%;
                  }

                  .btn-icon {
                    transform: scale(1.1) rotate(5deg);
                  }
                }

                &:active {
                  transform: translateY(-1px) scale(1.01);
                  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
                }

                /* Pulsing animation for attention */
                &:not(:hover) {
                  animation: subtle-glow 4s ease-in-out infinite;
                }
              }
            }
          }

          /* Enhanced structure panel styling */
          &.structure-panel {
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(248, 250, 252, 0.9) 100%);
            border: 1px solid rgba(226, 232, 240, 0.8);

            .structure-header-container {
              display: flex;
              justify-content: space-between;
              align-items: center;
              padding: 1.25rem 1.5rem;
              border-bottom: 1px solid rgba(226, 232, 240, 0.7);
              background: linear-gradient(135deg, rgba(79, 70, 229, 0.03) 0%, rgba(79, 70, 229, 0.08) 100%);
              backdrop-filter: blur(8px);

              .structure-title {
                font-weight: 700;
                color: #1e293b;
                font-size: 1.125rem;
                letter-spacing: -0.01em;
                display: flex;
                align-items: center;
                gap: 0.5rem;

                &::before {
                  content: '';
                  width: 8px;
                  height: 8px;
                  border-radius: 50%;
                  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
                  box-shadow: 0 0 8px rgba(59, 130, 246, 0.5);
                }
              }

              .structure-actions {
                display: flex;
                align-items: center;
                gap: 0.75rem;

                .action-btn {
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  width: 36px;
                  height: 36px;
                  border-radius: 10px;
                  border: none;
                  background: rgba(255, 255, 255, 0.8);
                  color: #64748b;
                  cursor: pointer;
                  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
                  border: 1px solid rgba(226, 232, 240, 0.8);
                  backdrop-filter: blur(4px);

                  &:hover {
                    background: white;
                    color: #3b82f6;
                    transform: translateY(-2px) scale(1.05);
                    box-shadow: 0 6px 12px rgba(59, 130, 246, 0.15);
                    border-color: rgba(59, 130, 246, 0.3);
                  }

                  &:active {
                    transform: translateY(-1px) scale(1.02);
                  }
                }

                .download-btn {
                  /* Material Design Teal - Enhanced professional styling */
                  --download-primary: #E0F2F1;    /* Material Teal 50 */
                  --download-secondary: #B2DFDB;  /* Material Teal 100 */
                  --download-accent: #80CBC4;     /* Material Teal 200 */
                  --download-text: #00695C;       /* Material Teal 800 */
                  --download-rgb: 0, 105, 92;

                  display: flex;
                  align-items: center;
                  gap: 0.5rem;
                  border: none;
                  background: var(--download-secondary); /* Flat pastel teal */
                  color: var(--download-text);
                  font-size: 0.8125rem;
                  font-weight: 600;
                  padding: 0.5rem 0.875rem;
                  border-radius: 8px;
                  cursor: pointer;
                  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                  border: 1px solid rgba(var(--download-rgb), 0.2);
                  box-shadow: 0 3px 8px rgba(var(--download-rgb), 0.15);
                  backdrop-filter: blur(8px);
                  position: relative;
                  overflow: hidden;

                  /* Enhanced shine effect */
                  &::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: -100%;
                    width: 100%;
                    height: 100%;
                    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.4), transparent);
                    transition: left 0.6s;
                  }

                  .download-icon {
                    color: var(--download-text);
                    transition: all 0.3s ease;
                    width: 16px;
                    height: 16px;
                  }

                  span {
                    font-weight: 600;
                    letter-spacing: 0.015em;
                  }

                  &:hover {
                    background: var(--download-accent); /* Flat pastel hover */
                    box-shadow: 0 6px 16px rgba(var(--download-rgb), 0.25);
                    transform: translateY(-2px) scale(1.03);

                    &::before {
                      left: 100%;
                    }

                    .download-icon {
                      transform: scale(1.15) rotate(-5deg);
                      filter: brightness(1.2);
                    }
                  }

                  &:active {
                    transform: translateY(-1px) scale(1.02);
                    box-shadow: 0 3px 8px rgba(var(--download-rgb), 0.2);
                  }
                }
              }
            }

            .structure-visualization {
              position: relative;
              padding: 2rem;
              background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
              min-height: 320px;
              backdrop-filter: blur(4px);

              .structure-container {
                height: 100%;
                width: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;

                /* Enhanced chemical structure viewer styling */
                :deep(.chemical-structure-viewer) {
                  height: 100%;
                  width: 100%;

                  .structure-display {
                    background: rgba(255, 255, 255, 0.95) !important;
                    border-radius: 12px;
                    border: 1px solid rgba(226, 232, 240, 0.6);
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
                    backdrop-filter: blur(8px);
                  }

                  .svg-container {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 1rem;

                    svg {
                      max-width: 100%;
                      max-height: 300px;
                      filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.08));
                      transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
                      border-radius: 8px;

                      &:hover {
                        filter: drop-shadow(0 8px 20px rgba(0, 0, 0, 0.12));
                        transform: scale(1.03);
                      }
                    }
                  }

                  /* Loading state styling */
                  .loading-state {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 200px;
                    background: rgba(255, 255, 255, 0.8);
                    border-radius: 12px;

                    .loading-spinner {
                      width: 40px;
                      height: 40px;
                      border: 3px solid rgba(59, 130, 246, 0.2);
                      border-top-color: #3b82f6;
                      border-radius: 50%;
                      animation: spin 1.5s linear infinite;
                    }
                  }

                  /* Error state styling */
                  .error-state {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    min-height: 200px;
                    background: rgba(254, 242, 242, 0.8);
                    border-radius: 12px;
                    color: #dc2626;
                    padding: 1.5rem;
                    text-align: center;

                    .error-icon {
                      margin-bottom: 0.75rem;
                      color: #ef4444;
                    }

                    .error-message {
                      font-weight: 500;
                      font-size: 0.875rem;
                    }
                  }
                }
              }
            }

            .smiles-container {
              padding: 1.75rem 1.5rem;
              border-top: 1px solid rgba(226, 232, 240, 0.7);
              position: relative;
              background: linear-gradient(120deg, rgba(248, 250, 252, 0.8), rgba(255, 255, 255, 0.95));
              overflow: hidden;

              /* Enhanced top border accent */
              &::before {
                content: "";
                position: absolute;
                top: -2px;
                left: 0;
                right: 0;
                height: 3px;
                background: linear-gradient(90deg, #3b82f6 0%, #8b5cf6 50%, #06b6d4 100%);
                opacity: 0.8;
                border-radius: 0 0 2px 2px;
              }

              .smiles-header {
                margin-bottom: 1rem;
                display: flex;
                align-items: center;

                .smiles-label {
                  font-weight: 700;
                  color: #1e293b;
                  font-size: 1rem;
                  display: flex;
                  align-items: center;
                  gap: 0.625rem;
                  letter-spacing: -0.01em;

                  &::before {
                    content: "";
                    display: block;
                    width: 14px;
                    height: 14px;
                    border-radius: 50%;
                    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
                    box-shadow: 0 0 12px rgba(59, 130, 246, 0.6), 0 2px 4px rgba(59, 130, 246, 0.3);
                    animation: subtle-pulse 3s ease-in-out infinite;
                  }
                }
              }

              .smiles-content {
                .smiles-box {
                  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
                  background: rgba(255, 255, 255, 0.95);
                  padding: 1.5rem;
                  border-radius: 14px;
                  font-size: 0.9375rem;
                  color: #1e293b;
                  overflow-x: auto;
                  white-space: pre-wrap;
                  word-break: break-all;
                  border: 1px solid rgba(226, 232, 240, 0.8);
                  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.9);
                  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
                  position: relative;
                  backdrop-filter: blur(8px);
                  line-height: 1.6;

                  &:hover {
                    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.9);
                    border-color: rgba(59, 130, 246, 0.4);
                    transform: translateY(-2px);
                    background: white;
                  }

                  /* Enhanced copy button */
                  &::after {
                    content: "📋 Copy";
                    position: absolute;
                    top: 0.75rem;
                    right: 0.75rem;
                    background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(59, 130, 246, 0.15) 100%);
                    color: #3b82f6;
                    font-size: 0.75rem;
                    padding: 0.375rem 0.625rem;
                    border-radius: 8px;
                    opacity: 0;
                    transition: all 0.3s ease;
                    cursor: pointer;
                    font-family: system-ui, sans-serif;
                    font-weight: 600;
                    border: 1px solid rgba(59, 130, 246, 0.2);
                    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.1);
                    backdrop-filter: blur(4px);
                  }

                  &:hover::after {
                    opacity: 1;
                    transform: translateY(-1px) scale(1.02);
                  }

                  /* Scrollbar styling */
                  &::-webkit-scrollbar {
                    height: 6px;
                  }

                  &::-webkit-scrollbar-track {
                    background: rgba(241, 245, 249, 0.6);
                    border-radius: 3px;
                  }

                  &::-webkit-scrollbar-thumb {
                    background: rgba(148, 163, 184, 0.4);
                    border-radius: 3px;

                    &:hover {
                      background: rgba(100, 116, 139, 0.6);
                    }
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
                  background-color: rgba(33, 150, 243, 0.1);
                  color: #2196F3;
                  border: 1px solid rgba(33, 150, 243, 0.3);
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
                    background-color: rgba(7, 150, 112, 0.1);
                    color: #05742c;
                    border: 1px solid rgba(14, 165, 233, 0.3);
                  }

                  &.molscribe-tag {
                    background-color: rgba(123, 31, 162, 0.1);
                    color: #7B1FA2;
                    border: 1px solid rgba(123, 31, 162, 0.3);
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
            color: #2196F3;
            filter: drop-shadow(0 1px 2px rgba(33, 150, 243, 0.3));
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
          background: #2196F3;
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
            background: #1976D2;
            transform: translateY(-2px);
            box-shadow: 0 8px 16px rgba(25, 118, 210, 0.3);
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
        background: linear-gradient(135deg, rgba(148, 163, 184, 0.6) 0%, rgba(100, 116, 139, 0.8) 100%);
        border-radius: 8px;
        border: 2px solid rgba(255, 255, 255, 0.3);

        &:hover {
          background: linear-gradient(135deg, rgba(100, 116, 139, 0.8) 0%, rgba(71, 85, 105, 0.9) 100%);
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
                    background: linear-gradient(135deg, rgba(12, 255, 158, 0.15) 0%, rgba(14, 233, 182, 0.25) 100%);
                    border-bottom: 2px solid rgba(14, 233, 171, 0.4);

                    &:before {
                      background: radial-gradient(circle at top right, rgba(14, 233, 153, 0.3), transparent 70%);
                    }

                    .engine-icon {
                      color: #0ee9a7;
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
                      transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
                      border-radius: 8px;

                      &:hover {
                        filter: drop-shadow(0 8px 16px rgba(0, 0, 0, 0.2));
                        transform: scale(1.03);
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
                    gap: 0.75rem;
                    padding: 1rem;
                    background: linear-gradient(135deg, rgba(248, 250, 252, 0.8) 0%, rgba(255, 255, 255, 0.9) 100%);
                    border-radius: 12px;
                    border: 1px solid rgba(226, 232, 240, 0.6);
                    backdrop-filter: blur(4px);

                    .smiles-label {
                      font-weight: 600;
                      color: #374151;
                      font-size: 0.8125rem;
                      text-transform: uppercase;
                      letter-spacing: 0.025em;
                      flex-shrink: 0;
                    }

                    .smiles-value {
                      font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
                      background: rgba(255, 255, 255, 0.9);
                      padding: 0.5rem 0.75rem;
                      border-radius: 8px;
                      font-size: 0.8125rem;
                      color: #1e293b;
                      flex: 1;
                      border: 1px solid rgba(226, 232, 240, 0.5);
                      box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.04);
                      transition: all 0.3s ease;

                      &:hover {
                        background: white;
                        border-color: rgba(59, 130, 246, 0.3);
                        box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.04), 0 0 0 2px rgba(59, 130, 246, 0.1);
                      }
                    }

                    .copy-btn {
                      display: flex;
                      align-items: center;
                      justify-content: center;
                      width: 32px;
                      height: 32px;
                      border: none;
                      background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(59, 130, 246, 0.15) 100%);
                      color: #3b82f6;
                      border-radius: 8px;
                      cursor: pointer;
                      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
                      border: 1px solid rgba(59, 130, 246, 0.2);
                      backdrop-filter: blur(4px);
                      flex-shrink: 0;

                      &:hover {
                        background: linear-gradient(135deg, rgba(59, 130, 246, 0.15) 0%, rgba(59, 130, 246, 0.25) 100%);
                        transform: translateY(-1px) scale(1.05);
                        box-shadow: 0 4px 8px rgba(59, 130, 246, 0.2);
                      }

                      &:active {
                        transform: translateY(0) scale(1.02);
                      }
                    }
                  }

                  .engine-stats {
                    display: flex;
                    flex-direction: column;
                    gap: 0.625rem;
                    padding: 0.875rem;
                    background: linear-gradient(135deg, rgba(248, 250, 252, 0.6) 0%, rgba(255, 255, 255, 0.8) 100%);
                    border-radius: 10px;
                    border: 1px solid rgba(226, 232, 240, 0.5);

                    .stat-item {
                      display: flex;
                      justify-content: space-between;
                      align-items: center;
                      font-size: 0.8125rem;

                      .stat-label {
                        font-weight: 500;
                        color: #64748b;
                      }

                      .stat-value {
                        font-weight: 600;
                        color: #1e293b;
                        background: rgba(255, 255, 255, 0.8);
                        padding: 0.25rem 0.5rem;
                        border-radius: 6px;
                        border: 1px solid rgba(226, 232, 240, 0.6);
                      }

                      &.coordinates-badge {
                        .coordinate-label {
                          display: flex;
                          align-items: center;
                          gap: 0.375rem;
                          font-weight: 600;
                          color: #059669;
                          background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(16, 185, 129, 0.15) 100%);
                          padding: 0.375rem 0.625rem;
                          border-radius: 8px;
                          border: 1px solid rgba(16, 185, 129, 0.2);
                          font-size: 0.75rem;
                          text-transform: uppercase;
                          letter-spacing: 0.025em;

                          .coordinate-icon {
                            color: #10b981;
                            filter: drop-shadow(0 1px 1px rgba(16, 185, 129, 0.3));
                          }
                        }
                      }
                    }
                  }

                  .selection-actions {
                    .select-prediction-btn {
                      width: 100%;
                      display: flex;
                      align-items: center;
                      justify-content: center;
                      gap: 0.625rem;
                      padding: 0.875rem 1.25rem;
                      border: none;
                      background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
                      color: #475569;
                      font-weight: 600;
                      font-size: 0.875rem;
                      border-radius: 12px;
                      cursor: pointer;
                      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
                      border: 1px solid rgba(203, 213, 225, 0.8);
                      text-transform: uppercase;
                      letter-spacing: 0.025em;

                      .btn-icon {
                        transition: transform 0.3s ease;
                      }

                      &:hover:not(:disabled) {
                        background: linear-gradient(135deg, #e2e8f0 0%, #cbd5e1 100%);
                        transform: translateY(-2px);
                        box-shadow: 0 4px 8px rgba(100, 116, 139, 0.15);
                        border-color: rgba(148, 163, 184, 0.6);

                        .btn-icon {
                          transform: scale(1.1);
                        }
                      }

                      &.active {
                        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                        color: white;
                        border-color: rgba(16, 185, 129, 0.3);
                        box-shadow: 0 4px 10px rgba(16, 185, 129, 0.2);
                      }

                      &:active {
                        transform: translateY(-1px);
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
  }
}

/* Modern CSS Animations and Utilities */

/* Enhanced loading animations */
@keyframes loading-spinner {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.loading-spinner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;

  .spinner-ring {
    width: 40px;
    height: 40px;
    border: 3px solid rgba(59, 130, 246, 0.2);
    border-radius: 50%;
    border-top-color: #3b82f6;
    animation: loading-spinner 1s linear infinite;

    &:nth-child(2) {
      width: 30px;
      height: 30px;
      border-width: 2px;
      animation-duration: 1.5s;
      animation-direction: reverse;
      position: absolute;
    }

    &:nth-child(3) {
      width: 20px;
      height: 20px;
      border-width: 2px;
      animation-duration: 0.8s;
      position: absolute;
    }
  }

  .loading-text {
    font-weight: 500;
    color: #64748b;
    font-size: 0.875rem;
    text-align: center;
  }
}

/* Pulse animations */
@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.8;
    transform: scale(1.05);
  }
}

@keyframes subtle-pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.95;
    transform: scale(1.02);
  }
}

@keyframes subtle-glow {
  0%, 100% {
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.25);
  }
  50% {
    box-shadow: 0 4px 20px rgba(59, 130, 246, 0.4);
  }
}

/* Floating animation */
@keyframes float {
  0%, 100% {
    transform: translateY(0px);
  }
  50% {
    transform: translateY(-10px);
  }
}

/* Spin animation */
@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* Enhanced hover effects */
.hover-lift {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 16px rgba(0, 0, 0, 0.12);
  }
}

.hover-scale {
  transition: transform 0.3s ease;

  &:hover {
    transform: scale(1.02);
  }
}

/* Glass morphism utility */
.glass-morphism {
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

/* Enhanced gradient backgrounds */
.gradient-bg-primary {
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
}

.gradient-bg-success {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
}

.gradient-bg-warning {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
}

.gradient-bg-error {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
}

/* Text gradients */
.text-gradient-primary {
  background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.text-gradient-success {
  background: linear-gradient(90deg, #10b981 0%, #059669 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

/* Enhanced scrollbar styling */
.custom-scrollbar {
  &::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }

  &::-webkit-scrollbar-track {
    background: rgba(241, 245, 249, 0.8);
    border-radius: 8px;
  }

  &::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, rgba(148, 163, 184, 0.6) 0%, rgba(100, 116, 139, 0.8) 100%);
    border-radius: 8px;
    border: 2px solid rgba(255, 255, 255, 0.3);

    &:hover {
      background: linear-gradient(135deg, rgba(100, 116, 139, 0.8) 0%, rgba(71, 85, 105, 0.9) 100%);
    }
  }

  &::-webkit-scrollbar-corner {
    background: rgba(241, 245, 249, 0.8);
  }
}

/* Responsive design improvements */
@media (max-width: 768px) {
  .segment-viewer {
    border-radius: 16px;
    margin: 0.5rem;

    .normal-view {
      padding: 1.25rem;

      .segment-header {
        flex-direction: column;
        gap: 1rem;
        padding: 1.25rem;

        .segment-title-section {
          width: 100%;

          .title-with-badge {
            flex-direction: column;
            align-items: flex-start;
            gap: 0.75rem;

            .segment-title {
              font-size: 1.5rem;
            }
          }

          .segment-selection-control {
            margin-top: 0.75rem;
          }
        }

        .segment-actions {
          flex-direction: row;
          justify-content: flex-end;
          width: 100%;
        }
      }

      .content-panels {
        flex-direction: column;
        gap: 1.25rem;

        .panel {
          min-height: auto;
        }
      }
    }

    .comparison-mode {
      padding: 1.25rem;

      .comparison-header {
        flex-direction: column;
        gap: 1rem;
        align-items: flex-start;

        .header-actions {
          flex-direction: column;
          align-items: flex-start;
          width: 100%;
          gap: 0.75rem;
        }
      }

      .comparison-layout {
        grid-template-columns: 1fr;
        gap: 1.25rem;
      }

      .engine-results-grid {
        grid-template-columns: 1fr;
        gap: 1rem;
      }
    }
  }
}

@media (max-width: 480px) {
  .segment-viewer {
    margin: 0.25rem;
    border-radius: 12px;

    .normal-view {
      padding: 1rem;

      .segment-header {
        padding: 1rem;

        .segment-title {
          font-size: 1.375rem;
        }
      }

      .content-panels {
        gap: 1rem;
      }
    }

    .comparison-mode {
      padding: 1rem;
    }
  }
}

/* Accessibility improvements */
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}

/* High contrast mode support */
@media (prefers-contrast: high) {
  .segment-viewer {
    border: 2px solid #000;

    .status-badge {
      border-width: 2px;
    }

    .modern-toggle .toggle-track {
      border: 2px solid #000;
    }

    .action-btn {
      border: 2px solid #000;
    }
  }
}

/* Focus styles for accessibility */
.segment-viewer {
  button:focus,
  input:focus,
  [tabindex]:focus {
    outline: 2px solid #3b82f6;
    outline-offset: 2px;
    border-radius: 4px;
  }
}

/* Similarity Summary Section */
.similarity-summary {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 24px;
  margin-top: 32px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  
  .summary-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
    padding-bottom: 16px;
    border-bottom: 1px solid #f3f4f6;
    
    .summary-title {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      font-size: 18px;
      font-weight: 600;
      color: #374151;
      
      .summary-icon {
        color: #6b7280;
      }
    }
    
    .summary-toggle {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 8px 12px;
      background: #f9fafb;
      border: 1px solid #d1d5db;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 500;
      color: #6b7280;
      transition: all 0.2s ease;
      
      &:hover {
        background: #f3f4f6;
        border-color: #9ca3af;
        color: #374151;
      }
      
      .toggle-icon {
        transition: transform 0.2s ease;
      }
    }
  }
}

/* Quick Summary Stats */
.quick-summary {
  margin-bottom: 24px;
  
  .summary-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    
    @media (max-width: 768px) {
      grid-template-columns: 1fr;
      gap: 12px;
    }
    
    .stat-card {
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 20px;
      text-align: center;
      transition: all 0.2s ease;
      
      &:hover {
        border-color: #d1d5db;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
      }
      
      &.high-agreement {
        border-color: #d1fae5;
        background: #f0fdf4;
        
        .stat-value {
          color: #059669;
        }
      }
      
      &.medium-agreement {
        border-color: #fef3c7;
        background: #fffbeb;
        
        .stat-value {
          color: #d97706;
        }
      }
      
      &.low-agreement {
        border-color: #fee2e2;
        background: #fef2f2;
        
        .stat-value {
          color: #dc2626;
        }
      }
      
      .stat-value {
        font-size: 24px;
        font-weight: 700;
        color: #1f2937;
        margin-bottom: 4px;
        
        &.identical {
          display: flex;
          align-items: center;
          justify-content: center;
          
          .identical-icon {
            color: #059669;
          }
        }
      }
      
      .stat-label {
        font-size: 14px;
        font-weight: 500;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
    }
  }
}

/* Analysis Action Buttons */
.analysis-action-buttons {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  flex-wrap: wrap;
  justify-content: center; /* Center the buttons */
  
  @media (max-width: 768px) {
    flex-direction: column;
    gap: 8px;
  }
}

.highlight-common-btn,
.analyze-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  border: 1px solid transparent;
  border-radius: 6px;
  font-weight: 500;
  font-size: 14px;
  transition: all 0.2s ease;
  cursor: pointer;
  position: relative;
  
  .btn-icon {
    transition: transform 0.2s ease;
  }
  
  &:hover:not(:disabled) .btn-icon {
    transform: scale(1.05);
  }
  
  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    
    &:hover .btn-icon {
      transform: none;
    }
  }
  
  &:focus {
    outline: 2px solid #3b82f6;
    outline-offset: 2px;
  }
}

.highlight-common-btn {
  background: #f8fafc;
  border-color: #e2e8f0;
  color: #475569;
  
  &:hover:not(:disabled) {
    background: #f1f5f9;
    border-color: #cbd5e1;
    color: #334155;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }
  
  &:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  }
}

.analyze-btn {
  background: #f0f9ff;
  border-color: #e0f2fe;
  color: #0369a1;
  
  &:hover:not(:disabled) {
    background: #e0f2fe;
    border-color: #bae6fd;
    color: #0284c7;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(3, 105, 161, 0.1);
  }
  
  &:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: 0 1px 2px rgba(3, 105, 161, 0.1);
  }
}

/* Similarity Details Section */
.similarity-details {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 20px;
  margin-top: 16px;
  
  .details-content {
    animation: fadeInUp 0.3s ease-out;
  }
}

.run-analysis-prompt {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
  text-align: center;
  justify-content: center;
  color: #6b7280;
  font-weight: 500;
  
  .loading-icon {
    color: #3b82f6;
  }
  
  p {
    margin: 0;
    font-size: 15px;
  }
}

.analysis-error {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  color: #dc2626;
  font-weight: 500;
  
  .error-icon {
    flex-shrink: 0;
    color: #ef4444;
  }
  
  p {
    margin: 0;
    font-size: 14px;
  }
}

/* Comparison Footer */
.comparison-footer {
  margin-top: 32px;
  padding-top: 20px;
  border-top: 1px solid #e5e7eb;
  display: flex;
  justify-content: center;
  
  @media (max-width: 768px) {
    margin-top: 24px;
    padding-top: 16px;
  }
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: #f0fdf4;
  color: #166534;
  border: 1px solid #bbf7d0;
  border-radius: 6px;
  font-weight: 500;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
  
  &:hover:not(:disabled) {
    background: #dcfce7;
    border-color: #86efac;
    color: #14532d;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(22, 101, 52, 0.1);
    
    .refresh-icon {
      transform: rotate(-180deg);
    }
  }
  
  &:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: 0 1px 2px rgba(22, 101, 52, 0.1);
  }
  
  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
  }
  
  &:focus {
    outline: 2px solid #3b82f6;
    outline-offset: 2px;
  }
  
  .refresh-icon {
    transition: transform 0.3s ease;
  }
}

/* Animation Keyframes */
@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.spin {
  animation: spin 1s linear infinite;
}

.loading-icon.spin {
  animation: spin 1s linear infinite;
}

/* Apply Selection Section */
.apply-selection-bar {
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
  border: 1px solid #bae6fd;
  border-radius: 12px;
  padding: 16px 20px;
  margin: 20px 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  box-shadow: 0 2px 8px rgba(14, 165, 233, 0.08);
  animation: slideInUp 0.3s ease-out;
  
  @media (max-width: 768px) {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
    padding: 16px;
  }
}

.selection-message {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #0369a1;
  font-weight: 500;
  font-size: 14px;
  line-height: 1.5;
  
  .message-icon {
    color: #0284c7;
    flex-shrink: 0;
  }
  
  strong {
    color: #1e40af;
    font-weight: 600;
  }
  
  @media (max-width: 768px) {
    font-size: 13px;
    gap: 10px;
  }
}

.apply-selection-btn {
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
  border: 1px solid #93c5fd;
  border-radius: 8px;
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #1e40af;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
  white-space: nowrap;
  box-shadow: 0 1px 3px rgba(59, 130, 246, 0.1);
  
  .btn-icon {
    transition: transform 0.2s ease;
  }
  
  &:hover {
    background: linear-gradient(135deg, #bfdbfe 0%, #93c5fd 100%);
    border-color: #60a5fa;
    transform: translateY(-1px);
    box-shadow: 0 2px 6px rgba(59, 130, 246, 0.15);
    
    .btn-icon {
      transform: scale(1.1);
    }
  }
  
  &:active {
    transform: translateY(0);
    box-shadow: 0 1px 3px rgba(59, 130, 246, 0.1);
  }
  
  &:focus {
    outline: 2px solid #3b82f6;
    outline-offset: 2px;
  }
  
  @media (max-width: 768px) {
    padding: 12px 16px;
    justify-content: center;
    font-size: 13px;
  }
}

@keyframes slideInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Responsive design improvements */
@media (max-width: 640px) {
  .analysis-action-buttons {
    .highlight-common-btn,
    .analyze-btn {
      padding: 9px 14px;
      font-size: 13px;
      
      .btn-icon {
        width: 14px;
        height: 14px;
      }
    }
  }
  
  .refresh-btn {
    padding: 9px 16px;
    font-size: 13px;
    
    .refresh-icon {
      width: 16px;
      height: 16px;
    }
  }
  
  .similarity-details {
    padding: 16px;
    margin-top: 12px;
  }
  
  .run-analysis-prompt {
    padding: 16px;
    flex-direction: column;
    gap: 8px;
    
    p {
      font-size: 14px;
    }
  }
  
  .similarity-summary {
    padding: 16px;
    margin-top: 24px;
    
    .summary-header {
      margin-bottom: 16px;
      
      .summary-title {
        font-size: 16px;
      }
      
      .summary-toggle {
        padding: 6px 10px;
        font-size: 13px;
      }
    }
  }
  
  .quick-summary .summary-stats .stat-card {
    padding: 16px;
    
    .stat-value {
      font-size: 20px;
    }
    
    .stat-label {
      font-size: 12px;
    }
  }
}

/* Similarity Summary Section */
.similarity-summary {
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border: 2px solid #e2e8f0;
  border-radius: 16px;
  margin-top: 32px;
  padding: 0;
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.08);
  overflow: hidden;
  position: relative;
  
  &:before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, #8b5cf6, #06b6d4, #10b981, #f59e0b, #ef4444);
  }
}

.summary-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px 28px;
  background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
  border-bottom: 2px solid #e2e8f0;
  
  .summary-title {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 0;
    font-size: 20px;
    font-weight: 700;
    color: #1e293b;
    
    .summary-icon {
      color: #3b82f6;
      background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
      padding: 8px;
      border-radius: 8px;
      box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
    }
  }
  
  .summary-toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    
    &:hover {
      background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
    }
    
    .toggle-icon {
      transition: transform 0.3s ease;
    }
  }
}

/* Quick Summary Stats */
.quick-summary {
  padding: 28px;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
}

.summary-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  
  @media (max-width: 768px) {
    grid-template-columns: 1fr;
    gap: 16px;
  }
}

.stat-card {
  background: linear-gradient(135deg, #ffffff 0%, #f9fafb 100%);
  border: 2px solid #e5e7eb;
  border-radius: 12px;
  padding: 24px;
  text-align: center;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
  
  &:before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, #6b7280, #9ca3af);
    transition: all 0.3s ease;
  }
  
  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 24px rgba(0, 0, 0, 0.1);
    border-color: #d1d5db;
    
    &:before {
      height: 6px;
    }
  }
  
  .stat-value {
    font-size: 32px;
    font-weight: 800;
    color: #1f2937;
    margin-bottom: 8px;
    line-height: 1;
    
    &.identical {
      display: flex;
      justify-content: center;
      align-items: center;
      
      .identical-icon {
        color: #10b981;
        filter: drop-shadow(0 2px 4px rgba(16, 185, 129, 0.3));
      }
    }
  }
  
  .stat-label {
    font-size: 14px;
    font-weight: 600;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  
  /* Agreement level styling */
  &.high-agreement {
    border-color: #10b981;
    background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
    
    &:before {
      background: linear-gradient(90deg, #10b981, #059669);
    }
    
    .stat-value {
      color: #065f46;
    }
    
    .stat-label {
      color: #047857;
    }
  }
  
  &.medium-agreement {
    border-color: #f59e0b;
    background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
    
    &:before {
      background: linear-gradient(90deg, #f59e0b, #d97706);
    }
    
    .stat-value {
      color: #92400e;
    }
    
    .stat-label {
      color: #b45309;
    }
  }
  
  &.low-agreement {
    border-color: #ef4444;
    background: linear-gradient(135deg, #fef2f2 0%, #fecaca 100%);
    
    &:before {
      background: linear-gradient(90deg, #ef4444, #dc2626);
    }
    
    .stat-value {
      color: #991b1b;
    }
    
    .stat-label {
      color: #b91c1c;
    }
  }
  
  &.perfect-agreement {
    border-color: #8b5cf6;
    background: linear-gradient(135deg, #f3e8ff 0%, #e9d5ff 100%);
    
    &:before {
      background: linear-gradient(90deg, #8b5cf6, #7c3aed);
    }
    
    .stat-value {
      color: #581c87;
    }
    
    .stat-label {
      color: #6b21a8;
    }
  }
}

/* Responsive design for summary stats */
@media (max-width: 640px) {
  .similarity-summary {
    margin-top: 24px;
    border-radius: 12px;
  }
  
  .summary-header {
    padding: 20px;
    flex-direction: column;
    gap: 16px;
    text-align: center;
    
    .summary-title {
      font-size: 18px;
      
      .summary-icon {
        padding: 6px;
      }
    }
    
    .summary-toggle {
      padding: 8px 14px;
      font-size: 14px;
    }
  }
  
  .quick-summary {
    padding: 20px;
  }
  
  .stat-card {
    padding: 20px;
    
    .stat-value {
      font-size: 28px;
    }
    
    .stat-label {
      font-size: 13px;
    }
  }
}

/* Enhanced animations for stat cards */
@keyframes statPulse {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.02);
  }
}

.stat-card.perfect-agreement .stat-value,
.stat-card.high-agreement .stat-value {
  animation: statPulse 2s ease-in-out infinite;
}

/* Loading state for summary stats */
.summary-stats.loading {
  .stat-card {
    opacity: 0.6;
    pointer-events: none;
    
    .stat-value {
      background: linear-gradient(90deg, #e5e7eb, #f3f4f6, #e5e7eb);
      background-size: 200% 100%;
      animation: shimmer 1.5s ease-in-out infinite;
      color: transparent;
      border-radius: 4px;
      height: 40px;
      margin-bottom: 12px;
    }
  }
}

@keyframes shimmer {
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
}
</style>