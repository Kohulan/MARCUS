import type { CSSProperties } from "react";
import type { SegmentOut } from "../api/types";

const pct = (v: number, total: number) => `${+((v * 100) / total).toFixed(3)}%`;
const clamp = (v: number, max: number) => Math.min(Math.max(v, 0), max);

/**
 * Where a segment's marker sits on its page, for both page views (the Paper view and focus
 * mode): `bbox` is [x0, y0, x1, y1] in pixels of the 300 DPI page PNG, which is the image
 * served, so the box is placed in percent of the image's natural size (`w` × `h`): CSS vars
 * `--l --t --w --h` the marker classes read. No measuring: the box follows the shown size.
 */
export function boxStyle(bbox: SegmentOut["bbox"], w: number, h: number): CSSProperties {
  const [a, b, c, d] = bbox;
  const left = clamp(Math.min(a, c), w);
  const top = clamp(Math.min(b, d), h);
  const right = clamp(Math.max(a, c), w);
  const bottom = clamp(Math.max(b, d), h);
  return {
    "--l": pct(left, w),
    "--t": pct(top, h),
    "--w": pct(right - left, w),
    "--h": pct(bottom - top, h),
  } as CSSProperties;
}
