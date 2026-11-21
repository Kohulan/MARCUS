/**
 * The numbered tag of structure `n` (1-based, in (page, idx) order): `[01]` … `[99]`,
 * three digits from `[100]`. The same tag marks the card, its page marker and focus mode.
 */
export function structureTag(n: number): string {
  return `[${String(n).padStart(2, "0")}]`;
}

/** A paper's shown name: its title when it has one, else its file name. */
export function paperName(p: { title: string | null; display_name: string }): string {
  return p.title?.trim() || p.display_name;
}
