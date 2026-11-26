// A paper layout molfile for tests (backend marcus.core.paper_layout): a printed benzene, every
// bond one length (a computed layout by the bond-length rule, were it not for the title line).
const RING = [0, 1, 2, 3, 4, 5].map((i) => {
  const a = ((60 * i + 30) * Math.PI) / 180;
  return [200 + 40 * Math.cos(a), -(200 + 40 * Math.sin(a))] as const;
});
const num = (v: number) => v.toFixed(4).padStart(10);
const idx = (v: number) => String(v).padStart(3);

export function paperLayout(fit = 0.5, bond = 40): string {
  return [
    `MARCUS layout fit=${fit.toFixed(2)} bond=${bond.toFixed(1)} size=400x300`,
    "     RDKit          2D",
    "",
    "  6  6  0  0  0  0  0  0  0  0999 V2000",
    ...RING.map(([x, y]) => `${num(x)}${num(y)}${num(0)} C   0  0  0  0  0  0  0  0  0  0  0  0`),
    ...RING.map((_, i) => `${idx(i + 1)}${idx(((i + 1) % 6) + 1)}  4  0`),
    "M  END",
    "",
  ].join("\n");
}
