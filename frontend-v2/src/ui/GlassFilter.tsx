import "./glass.css";

/**
 * The refraction filter of the glass buttons (`backdrop-filter: url(#marcus-glass)` in
 * glass.css; Chromium applies it, other browsers keep blur + saturate). Rendered once, by
 * App, so every pre-rendered page and the /app shell carry it. Hidden by its class (and by
 * the SVG size attributes), never by a style attribute (CSP style-src 'self').
 */
export default function GlassFilter() {
  return (
    <svg className="glass-defs" width="0" height="0" aria-hidden="true" focusable="false">
      <filter id="marcus-glass" x="0" y="0" width="100%" height="100%">
        <feTurbulence
          type="fractalNoise"
          baseFrequency="0.012 0.03"
          numOctaves={2}
          seed={7}
          result="noise"
        />
        <feGaussianBlur in="noise" stdDeviation={2} result="soft" />
        <feDisplacementMap
          in="SourceGraphic"
          in2="soft"
          scale={18}
          xChannelSelector="R"
          yChannelSelector="G"
        />
      </filter>
    </svg>
  );
}
