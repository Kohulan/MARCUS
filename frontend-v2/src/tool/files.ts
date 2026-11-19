// What the backend takes (marcus/api/uploads.py): a PDF, or one PNG, JPEG, TIFF or WebP
// image, at most 20 MB. Checked in the browser before anything is sent, by the tool's drop
// zone and by the landing's; the server checks the bytes either way. No CSS, no React: the
// pre-rendered landing imports it without pulling in the tool.

export const MAX_BYTES = 20 * 1024 * 1024;

export type FileKind = "pdf" | "image";

const BY_TYPE: Record<string, FileKind> = {
  "application/pdf": "pdf",
  "image/png": "image",
  "image/jpeg": "image",
  "image/tiff": "image",
  "image/webp": "image",
};

// Some systems give no type for a TIFF or WebP: then the extension decides.
const BY_EXTENSION: Record<string, FileKind> = {
  pdf: "pdf",
  png: "image",
  jpg: "image",
  jpeg: "image",
  tif: "image",
  tiff: "image",
  webp: "image",
};

/** The file input's accept list for every kind the backend takes. */
export const ACCEPT = [
  ...Object.keys(BY_TYPE),
  ...Object.keys(BY_EXTENSION).map((e) => `.${e}`),
].join(",");

/** "pdf", "image", or null for a type the backend refuses. */
export function fileKind(file: File): FileKind | null {
  const byType = BY_TYPE[file.type];
  if (byType) return byType;
  if (file.type !== "" && file.type !== "application/octet-stream") return null;
  const ext = file.name.toLowerCase().split(".").pop() ?? "";
  return BY_EXTENSION[ext] ?? null;
}
