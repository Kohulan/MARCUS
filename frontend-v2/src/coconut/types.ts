// Wire types of the COCONUT reports API (shape from v1 frontend/src/services/coconutService.js:123-150)
// and the shapes the batch submit form works with.

export type Organism = {
  name: string;
  parts: string[];
  locations: { name: string; ecosystems: string[] }[];
};

export type ReportCreate = {
  title: string;
  evidence: string;
  comment: string;
  suggested_changes: {
    new_molecule_data: {
      canonical_smiles: string;
      reference_id: string;
      name: string;
      link: string;
      structural_comments: string;
      references: { doi: string; organisms: Organism[] }[];
    };
  };
};

export type SubmitItem = { segmentId: string; report: ReportCreate };

/** `reportId` is null when COCONUT accepted the batch but sent no id we could read. */
export type SubmitResult =
  | { segmentId: string; ok: true; reportId: string | null }
  | { segmentId: string; ok: false; error: string };

/** One organism as the curator types it: parts and ecosystems are comma-separated. */
export type OrganismDraft = {
  name: string;
  parts: string;
  location: string;
  ecosystems: string;
};

/** Filled once per paper; every structure inherits it. */
export type PaperFields = {
  title: string;
  doi: string;
  evidence: string;
  comment: string;
  organisms: OrganismDraft[];
};

/** Per structure. `comment` and `organism` are overrides: undefined or blank inherits. */
export type StructureFields = {
  name: string;
  comment?: string;
  structuralComments: string;
  organism?: OrganismDraft;
};

/** What the caller hands the form for each accepted structure. */
export type SubmitStructure = {
  segmentId: string;
  /** 1-based number in (page, idx) order, shown as the [nn] tag. */
  n: number;
  smiles: string;
  /** A starting name (for example from PubChem). */
  name?: string;
  /** A link for the structure (for example its PubChem page). */
  link?: string;
};
