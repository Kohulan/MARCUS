import decimerService from "@/services/decimerService";
import ocsrService from "@/services/ocsrService";
import similarityService from "@/services/similarityService";

/**
 * Vuex module for handling chemical structure extraction and processing
 */
export default {
  namespaced: true,

  state: {
    segments: [], // Array of extracted structure segments
    segmentsDirectory: null, // Directory path for segments
    convertedStructures: [], // Array of converted chemical structures
    isLoading: false, // Loading state
    isConverting: false, // Structure conversion loading state
    error: null, // Error information
    segmentInfo: null, // Metadata about the segments
    processingOptions: {
      // Options for structure processing
      engine: "decimer", // Default engine: 'decimer', 'molnextr', or 'molscribe'
      handDrawn: false,
      includeMolfile: false,
    },
    currentPdfId: null, // ID of the current PDF being processed
    processedStructuresCache: new Map(), // Cache map for structure lookup by filename
    selectedSegments: new Map(), // Map to track selected segments (id -> boolean)
    hideIncorrectSegments: false, // Flag to hide/show incorrect segments
    onlyProcessSelected: false, // Flag to only process selected segments
  },

  mutations: {
    SET_SEGMENTS(state, segments) {
      state.segments = segments;
    },
    SET_SEGMENTS_DIRECTORY(state, directory) {
      state.segmentsDirectory = directory;
    },
    SET_CONVERTED_STRUCTURES(state, structures) {
      state.convertedStructures = structures;
    },
    ADD_CONVERTED_STRUCTURE(state, structure) {
      state.convertedStructures.push(structure);
    },
    SET_LOADING(state, isLoading) {
      state.isLoading = isLoading;
    },
    SET_CONVERTING(state, isConverting) {
      state.isConverting = isConverting;
    },
    SET_ERROR(state, error) {
      state.error = error;
    },
    CLEAR_ERROR(state) {
      state.error = null;
    },
    SET_SEGMENT_INFO(state, info) {
      state.segmentInfo = info;
    },
    SET_PROCESSING_OPTIONS(state, options) {
      state.processingOptions = { ...state.processingOptions, ...options };
    },
    SET_CURRENT_PDF_ID(state, pdfId) {
      state.currentPdfId = pdfId;
    },
    SET_PROCESSED_STRUCTURES_CACHE(state, cache) {
      state.processedStructuresCache = cache;
    },
    // New mutations for segment selection
    SET_SEGMENT_SELECTION(state, { segmentId, selected }) {
      state.selectedSegments.set(segmentId, selected);
    },
    CLEAR_SEGMENT_SELECTIONS(state) {
      state.selectedSegments = new Map();
    },
    SET_HIDE_INCORRECT_SEGMENTS(state, hide) {
      state.hideIncorrectSegments = hide;
    },
    SET_ONLY_PROCESS_SELECTED(state, onlySelected) {
      state.onlyProcessSelected = onlySelected;
    },
    // Add a new mutation for updating a structure with a selected prediction
    UPDATE_STRUCTURE_WITH_PREDICTION(state, { segmentId, newStructure }) {
      // Find the index of the structure to update
      const index = state.convertedStructures.findIndex(
        (s) => s.segmentId === segmentId
      );

      if (index !== -1) {
        // Replace the structure with the updated one
        state.convertedStructures.splice(index, 1, newStructure);

        // Also update the cache
        if (newStructure.name) {
          const newCache = new Map(state.processedStructuresCache);
          newCache.set(newStructure.name, newStructure);
          if (newStructure.uniqueKey) {
            newCache.set(newStructure.uniqueKey, newStructure);
          }
          state.processedStructuresCache = newCache;
        }
      } else {
        // If not found, add as a new structure
        state.convertedStructures.push(newStructure);

        // Add to cache
        if (newStructure.name) {
          const newCache = new Map(state.processedStructuresCache);
          newCache.set(newStructure.name, newStructure);
          if (newStructure.uniqueKey) {
            newCache.set(newStructure.uniqueKey, newStructure);
          }
          state.processedStructuresCache = newCache;
        }
      }
    },
  },

  actions: {
    /**
     * Set the current PDF ID
     * @param {Object} context - Vuex action context
     * @param {string} pdfId - The PDF ID to set
     */
    setCurrentPdfId({ commit }, pdfId) {
      commit("SET_CURRENT_PDF_ID", pdfId);
    },

    /**
     * Clear all structures and state when a new PDF is loaded
     * @param {Object} context - Vuex action context
     */
    clearStructuresForNewPdf({ commit }) {
      console.log("Clearing all structures for new PDF upload");

      // Reset all structure-related state
      commit("SET_SEGMENTS", []);
      commit("SET_SEGMENTS_DIRECTORY", null);
      commit("SET_CONVERTED_STRUCTURES", []);
      commit("SET_SEGMENT_INFO", null);
      commit("CLEAR_ERROR");

      // Clear the structures cache
      commit("SET_PROCESSED_STRUCTURES_CACHE", new Map());

      // Clear segment selections
      commit("CLEAR_SEGMENT_SELECTIONS");
    },

    /**
     * Toggle the selection state of a segment
     * @param {Object} context - Vuex action context
     * @param {string} segmentId - The ID of the segment to toggle
     */
    toggleSegmentSelection({ commit, state }, segmentId) {
      const currentValue = state.selectedSegments.get(segmentId) || false;
      commit("SET_SEGMENT_SELECTION", { segmentId, selected: !currentValue });
    },

    /**
     * Set the selection state of a segment
     * @param {Object} context - Vuex action context
     * @param {Object} payload - Selection payload
     * @param {string} payload.segmentId - The ID of the segment
     * @param {boolean} payload.selected - The selection state
     */
    setSegmentSelection({ commit }, { segmentId, selected }) {
      commit("SET_SEGMENT_SELECTION", { segmentId, selected });
    },

    /**
     * Toggle visibility of incorrect segments
     * @param {Object} context - Vuex action context
     * @param {boolean} hide - Whether to hide incorrect segments
     */
    setHideIncorrectSegments({ commit }, hide) {
      commit("SET_HIDE_INCORRECT_SEGMENTS", hide);
    },

    /**
     * Toggle whether to only process selected segments
     * @param {Object} context - Vuex action context
     * @param {boolean} onlySelected - Whether to only process selected segments
     */
    setOnlyProcessSelected({ commit }, onlySelected) {
      commit("SET_ONLY_PROCESS_SELECTED", onlySelected);
    },

    /**
     * Fetch chemical structure segments from a PDF file
     * @param {Object} context - Vuex action context
     * @param {File} pdfFile - The PDF file to process
     * @param {Object} options - Optional extraction parameters
     */
    async fetchSegments({ commit, dispatch, state }, pdfFile, options = {}) {
      if (!pdfFile) {
        commit("SET_ERROR", "No PDF file provided");
        return;
      }

      // Clear previous structures when processing a new PDF
      if (pdfFile !== state.currentPdfFile) {
        await dispatch("clearStructuresForNewPdf");

        // Generate and set a new PDF ID
        const pdfId = `pdf-${Date.now()}`;
        commit("SET_CURRENT_PDF_ID", pdfId);

        // Store the current PDF file reference
        state.currentPdfFile = pdfFile;
      }

      commit("SET_LOADING", true);
      commit("CLEAR_ERROR");

      try {
        console.log("Extracting segments from PDF file:", pdfFile.name);

        // Call the API to extract segments
        const response = await decimerService.extractSegments(pdfFile, {
          collectAll:
            options.collectAll !== undefined ? options.collectAll : true,
        });

        // Check if segments were successfully extracted
        if (response && response.segments_count) {
          console.log("Segments extracted successfully:", response);

          // Store segment info
          commit("SET_SEGMENT_INFO", {
            count: response.segments_count,
            directory: response.segments_directory,
            alreadyExisted: response.segments_already_existed,
            pdfFilename: response.pdf_filename,
            pdfId: state.currentPdfId, // Store PDF ID with segment info
          });

          // Set the segments directory - remove 'all_segments' if needed
          let directory = response.segments_directory;
          if (directory && directory.includes("/all_segments")) {
            directory = directory.split("/all_segments")[0];
          }

          commit("SET_SEGMENTS_DIRECTORY", directory);

          try {
            // Get actual segment files instead of creating mock data
            const segments = await decimerService.listSegmentFiles(directory);
            console.log(`Fetched ${segments.length} segments from server`);

            // Add PDF ID to each segment
            const segmentsWithPdfId = segments.map((segment) => ({
              ...segment,
              pdfId: state.currentPdfId, // Add PDF ID to each segment
            }));

            // Set segments with PDF ID
            commit("SET_SEGMENTS", segmentsWithPdfId);

            if (segments.length === 0 && response.segments_count > 0) {
              console.warn(
                "No segments returned from listSegmentFiles despite segments_count > 0"
              );
              commit(
                "SET_ERROR",
                "No segment files found despite successful extraction"
              );
            }
          } catch (listError) {
            console.error("Error listing segment files:", listError);
            commit(
              "SET_ERROR",
              `Error listing segment files: ${listError.message}`
            );
          }

          dispatch(
            "showNotification",
            {
              type: "success",
              message: `Extracted ${response.segments_count} chemical structure segments`,
            },
            { root: true }
          );
        } else {
          throw new Error("Invalid segment extraction response");
        }
      } catch (error) {
        commit("SET_ERROR", error.message || "Failed to extract segments");

        dispatch(
          "showNotification",
          {
            type: "error",
            message: error.message || "Failed to extract segments",
          },
          { root: true }
        );
      } finally {
        commit("SET_LOADING", false);
      }
    },

    /**
     * Process segments to extract chemical structures
     * @param {Object} context - Vuex action context
     * @param {Object} options - Processing options
     */
    async processStructures({ commit, state, dispatch }, options = {}) {
      if (!state.segments || state.segments.length === 0) {
        commit("SET_ERROR", "No segments to process");
        return;
      }

      commit("SET_CONVERTING", true);
      commit("CLEAR_ERROR");

      // Update processing options
      if (options.model) {
        // Validate model/engine value
        const validEngines = ["decimer", "molnextr", "molscribe"];
        const engine = validEngines.includes(options.model)
          ? options.model
          : "decimer";

        // Auto-enable includeMolfile for molnextr and molscribe engines
        const includeMolfile =
          options.includeMolfile ||
          engine === "molnextr" ||
          engine === "molscribe";

        commit("SET_PROCESSING_OPTIONS", {
          engine: engine,
          handDrawn: options.handDrawn || false,
          includeMolfile: includeMolfile,
        });
      }

      try {
        // Get processing options
        const processingOptions = {
          engine: state.processingOptions.engine,
          handDrawn: state.processingOptions.handDrawn,
          includeMolfile: state.processingOptions.includeMolfile,
          pdfId: state.currentPdfId, // IMPORTANT: Pass the PDF ID to ocsrService
        };

        // Use segments provided in options if available, otherwise use state segments
        let segmentsToProcess = options.segments || state.segments;

        // Filter segments if onlyProcessSelected is enabled
        if (state.onlyProcessSelected && state.selectedSegments.size > 0) {
          segmentsToProcess = segmentsToProcess.filter(
            (segment) => state.selectedSegments.get(segment.id) === true
          );

          if (segmentsToProcess.length === 0) {
            commit("SET_ERROR", "No segments selected for processing");
            commit("SET_CONVERTING", false);

            // Show error notification
            dispatch(
              "showNotification",
              {
                type: "warning",
                message:
                  "No segments selected for processing. Please select at least one segment.",
              },
              { root: true }
            );

            return;
          }
        }

        console.log(
          `Processing ${segmentsToProcess.length} segments with options:`,
          processingOptions
        );

        // Use a mock implementation during development if needed
        let results;
        if (
          process.env.NODE_ENV === "development" &&
          process.env.VUE_APP_USE_MOCK_DATA === "true"
        ) {
          // Create mock results for fast UI testing with PDF ID
          results = segmentsToProcess.map((segment) => ({
            segmentId: segment.id,
            imageUrl: segment.imageUrl || segment.path,
            smiles: `C1=CC=C(C=C1)C=O${segment.id.split("-")[1]}`,
            engine: processingOptions.engine,
            name: segment.filename,
            pdfId: state.currentPdfId, // Add PDF ID to mock results
            error: null,
          }));
        } else {
          // Call the real OCSR service
          results = await ocsrService.processSegments(
            segmentsToProcess,
            processingOptions
          );
        }

        // Format and store the results
        const convertedStructures = results.map((result) => {
          // Extract segment ID from the path if not available directly
          const segmentId =
            result.segmentId ||
            `segment-${result.image_name?.split("_")[2] || "0"}`;

          return {
            segmentId: segmentId,
            filename: result.filename || result.name,
            imageUrl: result.segmentUrl || result.imageUrl,
            smiles: result.smiles || "",
            molfile: result.molfile || null,
            engine: result.engine || processingOptions.engine,
            error: result.error || null,
            pdfId: result.pdfId || state.currentPdfId, // Ensure PDF ID is set
            pageIndex: result.pageIndex || 0,
            segmentIndex: result.segmentIndex || 0,
            uniqueKey:
              result.uniqueKey || `pdf-${state.currentPdfId}-${segmentId}`,
            // Use the result's name or fallback to a default - FIX FOR UNDEFINED SEGMENT
            name:
              result.name ||
              result.filename ||
              (segmentId.split("-")[1]
                ? `Compound ${segmentId.split("-")[1]}`
                : "Unknown Compound"),
            timestamp: new Date().toISOString(),
          };
        });

        // Update the processed structures cache
        const newCache = new Map(state.processedStructuresCache);
        convertedStructures.forEach((structure) => {
          if (structure.name) {
            newCache.set(structure.name, structure);
            if (structure.uniqueKey) {
              newCache.set(structure.uniqueKey, structure);
            }
          }
        });
        commit("SET_PROCESSED_STRUCTURES_CACHE", newCache);

        // Set the converted structures
        commit("SET_CONVERTED_STRUCTURES", convertedStructures);

        const successCount = convertedStructures.filter((s) => !s.error).length;

        // Show success notification
        dispatch(
          "showNotification",
          {
            type: "success",
            message: `Converted ${successCount} of ${convertedStructures.length} structures`,
          },
          { root: true }
        );
      } catch (error) {
        commit("SET_ERROR", error.message || "Failed to process segments");

        // Show error notification
        dispatch(
          "showNotification",
          {
            type: "error",
            message: error.message || "Failed to process segments",
          },
          { root: true }
        );
      } finally {
        commit("SET_CONVERTING", false);
      }
    },

    /**
     * Alias for processStructures to maintain backward compatibility
     * @param {Object} context - Vuex action context
     * @param {Object} options - Processing options
     */
    async processSegments(context, options = {}) {
      // Simply forward to processStructures
      return context.dispatch("processStructures", options);
    },

    /**
     * Add a single converted structure
     * @param {Object} context - Vuex action context
     * @param {Object} structure - The structure to add
     */
    addConvertedStructure({ commit, state }, structure) {
      // Ensure the structure has the current PDF ID
      const structureWithPdfId = {
        ...structure,
        pdfId: structure.pdfId || state.currentPdfId,
      };

      // Add to the converted structures
      commit("ADD_CONVERTED_STRUCTURE", structureWithPdfId);

      // Update the cache
      const newCache = new Map(state.processedStructuresCache);
      if (structureWithPdfId.name) {
        newCache.set(structureWithPdfId.name, structureWithPdfId);
        if (structureWithPdfId.uniqueKey) {
          newCache.set(structureWithPdfId.uniqueKey, structureWithPdfId);
        }
      }
      commit("SET_PROCESSED_STRUCTURES_CACHE", newCache);
    },

    /**
     * Clear the current segments and structures
     * @param {Object} context - Vuex action context
     */
    clearSegments({ commit }) {
      commit("SET_SEGMENTS", []);
      commit("SET_SEGMENTS_DIRECTORY", null);
      commit("SET_CONVERTED_STRUCTURES", []);
      commit("SET_SEGMENT_INFO", null);
      commit("CLEAR_ERROR");
    },

    /**
     * Compare SMILES across multiple OCSR engines
     * @param {Object} context - Vuex action context
     * @param {Object} options - Comparison options
     * @param {string} options.segmentId - Segment ID to compare (optional, uses first segment if not provided)
     * @returns {Promise<Object|null>} - The comparison result or null on error
     */
    async compareSmiles({ state, dispatch }, options = {}) {
      // If no structures, we can't do a comparison
      if (
        !state.convertedStructures ||
        state.convertedStructures.length === 0
      ) {
        dispatch(
          "showNotification",
          {
            type: "error",
            message: "No structures available for comparison",
          },
          { root: true }
        );
        return null;
      }

      // Get current PDF ID to filter correctly
      const pdfId = state.currentPdfId;

      // Set default segmentId if not provided (use first segment)
      let segmentId = options.segmentId;
      if (!segmentId && state.segments.length > 0) {
        segmentId = state.segments[0].id;
      }

      if (!segmentId) {
        dispatch(
          "showNotification",
          {
            type: "error",
            message: "No segments available for comparison",
          },
          { root: true }
        );
        return null;
      }

      // Get engines to compare
      const engines = ["decimer", "molnextr", "molscribe"];
      const smilesList = [];
      const engineNames = [];

      for (const engine of engines) {
        // Find structure for this segment processed by this engine
        const structure = state.convertedStructures.find(
          (s) =>
            s.segmentId === segmentId &&
            s.engine === engine &&
            (!pdfId || s.pdfId === pdfId)
        );

        if (structure && structure.smiles) {
          smilesList.push(structure.smiles);
          engineNames.push(engine);
        }
      }

      // Make sure we have at least 2 engines with SMILES
      if (smilesList.length < 2) {
        dispatch(
          "showNotification",
          {
            type: "warning",
            message: "Need at least 2 engines with valid SMILES for comparison",
          },
          { root: true }
        );
        return null;
      }

      try {
        // Call the comparison API
        const result = await similarityService.compareSmiles(
          smilesList,
          engineNames
        );

        // Show notification based on result
        if (result.identical) {
          dispatch(
            "showNotification",
            {
              type: "success",
              message: "All OCSR engines generated identical SMILES",
            },
            { root: true }
          );
        } else {
          const agreement =
            result.agreement_summary.agreement_percentage.toFixed(1);
          dispatch(
            "showNotification",
            {
              type: "info",
              message: `OCSR engines have ${agreement}% agreement on structure`,
            },
            { root: true }
          );
        }

        return result;
      } catch (error) {
        console.error("Error comparing SMILES:", error);

        dispatch(
          "showNotification",
          {
            type: "error",
            message: error.message || "Error comparing SMILES",
          },
          { root: true }
        );

        return null;
      }
    },

    // Add a new action to update a structure with a selected prediction
    updateStructureWithPrediction({ commit }, { segmentId, newStructure }) {
      commit("UPDATE_STRUCTURE_WITH_PREDICTION", { segmentId, newStructure });
    },
  },

  getters: {
    hasSegments: (state) => state.segments && state.segments.length > 0,
    hasConvertedStructures: (state) =>
      state.convertedStructures && state.convertedStructures.length > 0,
    segmentCount: (state) => (state.segments ? state.segments.length : 0),
    convertedCount: (state) =>
      state.convertedStructures ? state.convertedStructures.length : 0,

    /**
     * Get visible segments based on selection filters
     */
    visibleSegments: (state) => {
      if (!state.segments) return [];
      if (!state.hideIncorrectSegments || state.selectedSegments.size === 0)
        return state.segments;

      // If hide incorrect segments is enabled, filter out unselected segments
      return state.segments.filter(
        (segment) => state.selectedSegments.get(segment.id) !== false
      );
    },

    /**
     * Check if a segment is selected
     */
    isSegmentSelected: (state) => (segmentId) => {
      return state.selectedSegments.get(segmentId) === true;
    },

    /**
     * Get number of selected segments
     */
    selectedSegmentCount: (state) => {
      let count = 0;
      state.selectedSegments.forEach((value) => {
        if (value === true) count++;
      });
      return count;
    },

    /**
     * Get structure for a segment, ensuring it matches the current PDF
     */
    getStructureForSegment: (state) => (segmentId) => {
      if (!state.convertedStructures || !segmentId) return null;

      // Try to look up in our cache first (faster)
      if (
        state.processedStructuresCache &&
        state.processedStructuresCache.has(segmentId)
      ) {
        const cachedStructure = state.processedStructuresCache.get(segmentId);
        // Only return if it matches the current PDF
        if (
          !state.currentPdfId ||
          cachedStructure.pdfId === state.currentPdfId
        ) {
          return cachedStructure;
        }
      }

      // Otherwise search through all structures
      // Only return structures that match the current PDF ID
      return state.convertedStructures.find(
        (s) =>
          s.segmentId === segmentId &&
          (!state.currentPdfId || s.pdfId === state.currentPdfId)
      );
    },

    /**
     * Get structure by filename
     */
    getStructureByFilename: (state) => (filename) => {
      if (!state.convertedStructures || !filename) return null;

      // Try to look up in our cache first
      if (
        state.processedStructuresCache &&
        state.processedStructuresCache.has(filename)
      ) {
        const cachedStructure = state.processedStructuresCache.get(filename);
        // Only return if it matches the current PDF
        if (
          !state.currentPdfId ||
          cachedStructure.pdfId === state.currentPdfId
        ) {
          return cachedStructure;
        }
      }

      // Find by name or filename
      return state.convertedStructures.find(
        (s) =>
          (s.name === filename || s.filename === filename) &&
          (!state.currentPdfId || s.pdfId === state.currentPdfId)
      );
    },

    /**
     * Get structure by unique key
     */
    getStructureByUniqueKey: (state) => (uniqueKey) => {
      if (!state.convertedStructures || !uniqueKey) return null;

      // Try to look up in our cache first
      if (
        state.processedStructuresCache &&
        state.processedStructuresCache.has(uniqueKey)
      ) {
        return state.processedStructuresCache.get(uniqueKey);
      }

      // Find by uniqueKey
      return state.convertedStructures.find((s) => s.uniqueKey === uniqueKey);
    },

    /**
     * Get all structures for the current PDF
     */
    getCurrentPdfStructures: (state) => {
      if (!state.convertedStructures) return [];
      if (!state.currentPdfId) return state.convertedStructures;

      return state.convertedStructures.filter(
        (s) => s.pdfId === state.currentPdfId
      );
    },

    /**
     * Get structure by segment ID and engine name
     */
    getStructureByEngine: (state) => (segmentId, engine) => {
      if (!state.convertedStructures || !segmentId || !engine) return null;

      return state.convertedStructures.find(
        (s) =>
          s.segmentId === segmentId &&
          s.engine === engine &&
          (!state.currentPdfId || s.pdfId === state.currentPdfId)
      );
    },
  },
};
