// Wire types of /api/v2, mirroring backend-v2/src/marcus/api/schemas.py (after F0).
// Ids are UUID strings; datetimes are ISO 8601 strings. Pages are 0-based.

/** An engine the UI offers (upload, Compare, re-read). */
export type Engine = "decimer" | "decimer-hand" | "molparser" | "molscribe";
/**
 * An engine no longer offered whose results old papers still hold (retention 30 days): the
 * server refuses it for new requests (422). MolParser replaced MolNexTR.
 */
export type LegacyEngine = "molnextr";
export type CurationStatus = "unchecked" | "accepted" | "rejected";
export type ErrorClass = "timeout" | "worker_lost" | "bad_input" | "engine_error";
/**
 * auto: every page read; off: every page segmented, nothing read; ask: the paper page asks
 * "Read all pages" / "Pick a structure"; pick: pages segmented and boxes read when the user asks.
 */
export type OcsrMode = "auto" | "off" | "ask" | "pick";
export type ExportFormat = "json" | "csv" | "sdf";
export type ExportStatus = "accepted" | "all";

// Known values of the `status` / `kind` strings (marcus/core/enums.py). The schemas send
// plain strings, so fields stay `string` and these are for comparisons.
export type PaperStatus = "checking" | "processing" | "done" | "failed" | "deleted";
export type ImageJobStatus = "queued" | "processing" | "done" | "failed" | "deleted";
export type StepStatus = "pending" | "queued" | "running" | "done" | "failed" | "cancelled";
export type StepKind =
  | "check_pdf"
  | "render_page"
  | "segment_page"
  | "ocsr"
  | "docling"
  | "doi"
  | "annotate";

export interface PaperSummary {
  id: string;
  display_name: string;
  status: string;
  pages: number | null;
  doi: string | null;
  title: string | null;
  /** The first author's family name, found with the DOI. */
  first_author: string | null;
  /** The publication year, found with the DOI. */
  year: number | null;
  engine: string;
  ocsr_mode: string;
  created_at: string;
  expires_at: string;
  structures: number;
  accepted: number;
  rejected: number;
  to_review: number;
  failed_pages: number;
  /** Undecided structures whose read failed (not in to_review). */
  failed: number;
  /** Busy only with its annotation (its only step in flight is annotate). */
  /**
   * The read's coarse progress, as the workspace reads it from the steps (readCounts): pages
   * whose newest page step ended, structures with an OCSR step and those read (or with nothing
   * in flight), the text read, a PDF check started, busy only re-reading read structures.
   */
  pages_read: number;
  structures_total: number;
  structures_read: number;
  text_read: boolean;
  check_started: boolean;
  rereading: boolean;
}

export interface PaperList {
  papers: PaperSummary[];
}

export interface Counts {
  steps_by_status: Record<string, number>;
}

export interface CurationOut {
  status: CurationStatus;
  smiles: string | null;
  molfile: string | null;
  note: string | null;
  /**
   * R-group labels of the curated structure (R1, X, Ar…), [] for none. Optional: absent in an
   * optimistic update until the server answers, and from an older server. In a paper: those
   * the page's text names (all of them when it names none).
   */
  rgroups?: string[];
  /** The structure has R-group placeholder atoms, whatever labels are shown (COCONUT holds it). */
  placeholder?: boolean;
}

/** PUT /segments/{id}/curation replaces the whole record: all four keys, always. */
export interface CurationIn {
  status: CurationStatus;
  smiles: string | null;
  molfile: string | null;
  note: string | null;
}

export interface PredictionOut {
  id: string;
  engine: string;
  engine_version: string;
  smiles: string;
  molfile: string | null;
  valid: boolean;
  ms: number;
  cached: boolean;
  created_at: string;
  /**
   * R-group labels (R1, X, Ar…): a scaffold that stands for several compounds. [] for none. In a
   * paper: those the page's text names (all of them when it names none).
   */
  rgroups?: string[];
  /** The structure has R-group placeholder atoms, whatever labels are shown (COCONUT holds it). */
  placeholder?: boolean;
}

export interface SegmentOut {
  id: string;
  /** 0-based; the UI shows page + 1. */
  page: number;
  idx: number;
  /** [x0, y0, x1, y1] in pixels of the 300 DPI page PNG. */
  bbox: [number, number, number, number];
  curation: CurationOut | null;
  predictions: PredictionOut[];
  /** Pick mode: a box the user has not picked. Drawn on its page only: no card, in no count. */
  candidate?: boolean;
  /** Markush Phase 3: a built structure's scaffold segment id (null otherwise). */
  built_from?: string | null;
  /** On a scaffold that was built: the rows that could not be (null when never built). */
  build_failures?: BuildFailure[] | null;
  /**
   * The main-figure structure this one repeats (the same compound on another page: same
   * InChIKey). Null or absent for every other structure, and without a main figure.
   */
  repeat_of?: string | null;
  /**
   * The crop is not a clean drawing (NMR marks, an X-ray or 3D picture): "Check this drawing".
   * False or absent when not flagged, and for structures read before the check existed.
   */
  check_drawing?: boolean;
  /**
   * The engines' agreement (backend core/agreement.py): 3 or 2 engines agree on the structure
   * (same InChIKey first block), 0 they differ. Null or absent while an engine is still
   * reading, or with fewer than two engines read.
   */
  agree?: number | null;
  /** Of how many engines that read: 3, or 2 when only two did. Null with `agree` null. */
  agree_of?: number | null;
  /** The engines that agree ([] none), in DECIMER, MolParser (old papers: MolNexTR), MolScribe order. */
  agree_engines?: string[];
  /**
   * The prediction shown when nothing is curated: the engines' majority, else the newest valid
   * one of the paper's engine, else of any engine. The server's one rule (exports, COCONUT).
   */
  default_prediction_id?: string | null;
  /** The compound ID printed by the drawing ("12", "8a"); null or absent without one. */
  compound_id?: string | null;
  /** The name the paper's text gives that compound ("salsubstolin A (12)"); null without. */
  compound_name?: string | null;
  /**
   * Pages (0-based) of structures with the same compound ID but another structure, not linked
   * (the main-figure one, or its look-alikes): the card asks to check. [] or absent: none.
   */
  same_id_pages?: number[];
}

export interface SegmentList {
  segments: SegmentOut[];
}

/** One pipeline step. No error text: only the coarse `error_class`. */
export interface StepOut {
  id: string;
  kind: string;
  page: number | null;
  segment_id: string | null;
  status: string;
  attempts: number;
  error_class: string | null;
  /** Set for ocsr steps. */
  engine: string | null;
  /**
   * A background OCSR step: another engine reading beside the paper's own. It never counts in
   * the paper's read, and its failure is no failure of the structure.
   */
  background?: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface StepList {
  steps: StepOut[];
}

export interface PaperDetail extends PaperSummary {
  /** The page (0-based) marked as the main figure, the paper's compound list; null: none. */
  main_figure_page?: number | null;
  /**
   * False when the server could not link the main figure's repeats this time (busy): no
   * segment has repeat_of, so nothing may go to COCONUT until a read says true. Absent: true.
   */
  links_ready?: boolean;
  counts: Counts;
  segments: SegmentOut[];
}

/** A scaffold row that was not built, and why ("Could not build"). */
export interface BuildFailure {
  compound: string;
  reason: string;
}

/** POST /segments/{id}/build: new or refreshed cards, kept, removed, and the rows not built. */
export interface BuildOut {
  built: number;
  kept: number;
  removed: number;
  failures: BuildFailure[];
}

export interface ModeOut {
  ocsr_mode: OcsrMode;
}

/** A page opened in pick mode: its segment step, or null when its boxes are there. */
export interface SegmentAccepted {
  step_id: string | null;
}

/** A box picked in pick mode: its three engines' steps. */
export interface ReadAccepted {
  step_ids: string[];
}

export interface StepAccepted {
  step_id: string;
}

/** A present `note` key (string or null) replaces the note; an absent one keeps it. */
export interface BulkCurationItem {
  segment_id: string;
  status: CurationStatus;
  note?: string | null;
  /** The prediction the card showed: kept as the decided structure. Absent: the server's pick. */
  shown_prediction_id?: string;
}

export interface MainFigureOut {
  main_figure_page: number | null;
}

export interface BulkCurationOut {
  updated: number;
}

export interface QueuePaper {
  id: string;
  steps_ahead_by_queue: Record<string, number>;
  estimate_s: number;
}

export interface QueueOut {
  papers: QueuePaper[];
  estimate_s: number;
}

export interface ImageStepOut {
  engine: string;
  status: string;
  error_class: string | null;
}

export interface ImageJobSummary {
  id: string;
  display_name: string;
  status: string;
  engine: string;
  created_at: string;
  expires_at: string;
}

export interface ImageJobList {
  jobs: ImageJobSummary[];
}

// The API also sends `error` (raw worker text, kept for API compatibility). It is left out
// of this type on purpose: raw error text is never shown (Global Constraints). It also sends
// `prediction`, the newest of ANY engine (a Compare engine that finished last included); the
// page derives the job engine's result from `predictions` instead (ImageResult mainPrediction).
export interface ImageJobOut {
  id: string;
  status: string;
  engine: string;
  display_name: string;
  created_at: string;
  expires_at: string;
  /** All predictions, newest first. */
  predictions: PredictionOut[];
  /** Of the newest failed step. */
  error_class: string | null;
  /** Newest first. */
  steps: ImageStepOut[];
}

export type UploadPaperReply = { paper_id: string; status: string };
export type UploadImageReply = { image_job_id: string; status: string };
export type DepictReply = { format: "svg"; data: string };

export type CompareReply = {
  tanimoto: number;
  identical: boolean;
  same_structure: boolean;
  agree: boolean;
};

export type McsReply = {
  mcs_smarts: string;
  atom_count: number;
  bond_count: number;
  original_molecules: { atom_count: number; bond_count: number }[];
  /** What /tools/depict needs to draw `mcs_smarts` in one of these molecules; null without one. */
  highlight_token: string | null;
};

/** Only the fields the UI reads of Docling's export_to_dict() (GET /papers/{id}/text). */
export type DoclingDoc = {
  body?: { children: { $ref: string }[] };
  texts: {
    self_ref: string;
    text: string;
    label: string;
    children?: { $ref: string }[];
    /** Where the item is: `page_no` counts from 1 (read defensively, rgroups.ts). */
    prov?: unknown;
  }[];
  groups?: { self_ref: string; children: { $ref: string }[] }[];
  /** Tables (skipped by the Paper view's text; read for R-group definitions, rgroups.ts). */
  tables?: { prov?: unknown; data?: { table_cells?: { text?: unknown }[] } }[];
};

// Paper annotation (GET /papers/{id}/annotation, backend-v2 api/schemas.py AnnotationOut).

/** [block, start, end]: block = index into doclingBlocks(text); offsets in UTF-16 units, end exclusive. */
export type AnnotationHit = [number, number, number];
/** field → value → its occurrences in the text, in text order ([] = not in the text). */
export type AnnotationPositions = Record<string, Record<string, AnnotationHit[]>>;
/** field → values ([] = none); all 11 fields. */
export type AnnotationValues = Record<string, string[]>;

export interface AnnotationField {
  key: string;
  label: string;
  /** The longest value a curation may hold in this field (the model's maxLength). */
  max_length: number;
}

/** What one curation save may hold (PUT answers 422 beyond it). */
export interface AnnotationLimits {
  max_values_per_field: number;
  max_total_values: number;
}

/** The COCONUT form's organisms (coconut OrganismDraft); COCONUT has no kingdom field. */
export interface AnnotationCoconut {
  organisms: { name: string; parts: string; location: string; ecosystems: string }[];
  kingdom: string[];
}

export interface AnnotationOut {
  /** False: this deployment cannot annotate (POST answers 503). */
  available: boolean;
  /** The newest annotate step's status, or "none" (never asked for). */
  status: string;
  step: StepOut | null;
  fields: AnnotationField[];
  limits: AnnotationLimits;
  model: string | null;
  model_version: string | null;
  output: AnnotationValues | null;
  positions: AnnotationPositions | null;
  curated: AnnotationValues | null;
  curated_positions: AnnotationPositions | null;
  /** What is shown and exported: curated if not null, else output; null before the first run. */
  values: AnnotationValues | null;
  coconut: AnnotationCoconut | null;
  created_at: string | null;
  updated_at: string | null;
  curated_at: string | null;
  /** GET: the annotation starts by itself within seconds (read GET again). */
  auto_pending?: boolean;
}

/** step_id null: the paper already has an annotation and no re-run was asked for. */
export interface AnnotationStarted {
  step_id: string | null;
}

// R-group rows of a scaffold read by the local R-group model (backend-v2 api/schemas.py
// RgroupExtractionOut; routes marcus.api.routes.rgroups). Model output: values are plain text.

/** One compound the scaffold stands for: its label, and the substituent per R-group label. */
export interface RgroupRow {
  compound: string;
  groups: Record<string, string>;
}

/** none: never asked for; queued and running: in flight; done; failed (`error`: its class). */
export type RgroupState = "none" | "queued" | "running" | "done" | "failed";

export interface RgroupExtractionOut {
  prediction_id: string;
  segment_id: string;
  status: RgroupState;
  /** The table's columns, in order. */
  labels: string[];
  /** Of the newest run that ended well (kept while a re-run runs or after one fails). */
  rows: RgroupRow[] | null;
  /** The token limit cut the answer: rows after the cut are missing. */
  truncated: boolean;
  /** The failed run's error class (timeout, engine_error, bad_input, worker_lost). */
  error: string | null;
  model: string | null;
  model_version: string | null;
  created_at: string | null;
  updated_at: string | null;
  finished_at: string | null;
}

export interface RgroupList {
  /** False: this deployment cannot read R-groups (POST answers 503). */
  available: boolean;
  extractions: RgroupExtractionOut[];
  /** Predictions whose reading starts by itself within seconds (read the list again). */
  auto_pending?: string[];
}

/** step_id null: the scaffold already has rows and no re-run was asked for. */
export interface RgroupStarted {
  step_id: string | null;
}
