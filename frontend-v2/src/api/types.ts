// Wire types of /api/v2, mirroring backend-v2/src/marcus/api/schemas.py (after F0).
// Ids are UUID strings; datetimes are ISO 8601 strings. Pages are 0-based.

export type Engine = "decimer" | "decimer-hand" | "molnextr" | "molscribe";
export type CurationStatus = "unchecked" | "accepted" | "rejected";
export type ErrorClass = "timeout" | "worker_lost" | "bad_input" | "engine_error";
export type OcsrMode = "auto" | "off";
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
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface StepList {
  steps: StepOut[];
}

export interface PaperDetail extends PaperSummary {
  counts: Counts;
  segments: SegmentOut[];
}

export interface StepAccepted {
  step_id: string;
}

/** A present `note` key (string or null) replaces the note; an absent one keeps it. */
export interface BulkCurationItem {
  segment_id: string;
  status: CurationStatus;
  note?: string | null;
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
};

/** Only the fields the UI reads of Docling's export_to_dict() (GET /papers/{id}/text). */
export type DoclingDoc = {
  body?: { children: { $ref: string }[] };
  texts: { self_ref: string; text: string; label: string; children?: { $ref: string }[] }[];
  groups?: { self_ref: string; children: { $ref: string }[] }[];
};
