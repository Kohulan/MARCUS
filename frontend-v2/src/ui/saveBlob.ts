/** Saves `blob` as `filename` through a temporary download link. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.append(a);
  a.click();
  a.remove();
  // Some browsers start reading the blob after click() returns.
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
