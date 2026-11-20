// What a screen reader is told while structures are sent to COCONUT: the start, each quarter
// crossed and the end, never every count (200 structures would be 200 announcements). The
// visible "Sent n of m" and the bar still move with every chunk.

/** The quarters of the send reached so far (0 to 4). */
export function quarterOf(done: number, total: number): number {
  if (total <= 0) return 4;
  return Math.min(4, Math.floor((done * 4) / total));
}

/** The words for a chunk that reached `done`, or null when it crossed no new quarter (or the end, said by `endNews`). */
export function chunkNews(before: number, done: number, total: number): string | null {
  const q = quarterOf(done, total);
  if (q <= quarterOf(before, total) || q >= 4) return null;
  return `Sent ${done} of ${total}`;
}

export const startNews = (total: number) => `Sending ${total} to COCONUT`;

export const endNews = (ok: number, total: number) => `Sent ${ok} of ${total}`;
