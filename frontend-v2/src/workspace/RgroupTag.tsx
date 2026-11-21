import { rgroupTag } from "./rgroups";

/**
 * "R-groups: R1, R2" beside the state badge (card, Paper view list): a structure that stands
 * for several compounds. Words in a square ink outline, never colour alone; real text, so a
 * screen reader reads it with the card. Nothing for a structure without R-groups.
 */
export default function RgroupTag({ labels }: { labels: readonly string[] }) {
  if (labels.length === 0) return null;
  const text = rgroupTag(labels);
  return (
    <span className="state tag tag--rgroups" title={text}>
      {text}
    </span>
  );
}
