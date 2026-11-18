/**
 * The numbered tag of structure `n` (1-based, in (page, idx) order): `[01]` … `[99]`,
 * three digits from `[100]`. The same tag marks the card, its page marker and focus mode.
 */
export function structureTag(n: number): string {
  return `[${String(n).padStart(2, "0")}]`;
}
