import { useState } from "react";
import "./ui.css";

type StructureProps = {
  /** The drawing: a blob: URL from useDepiction (null while it loads) or a static URL. */
  src: string | null;
  alt: string;
  /** Rejected: crossed by one diagonal charcoal line, the drawing dimmed. */
  crossed?: boolean;
  /** The drawing cannot be had (useDepiction().failed). */
  failed?: boolean;
};

/**
 * A structure drawing. Always a plain <img> (never inlined SVG: server data is never
 * markup). A quiet "+" stands in while it loads; "No drawing" when there is none.
 */
export default function Structure({ src, alt, crossed = false, failed = false }: StructureProps) {
  // Keyed by src, so a new drawing gets a fresh chance to load.
  const [brokenSrc, setBrokenSrc] = useState<string | null>(null);
  const broken = failed || (src !== null && brokenSrc === src);
  const classes = ["structure"];
  if (crossed) classes.push("structure--crossed", "strike");

  if (broken) {
    return (
      <div className={`${classes.join(" ")} structure--none`}>
        <span className="structure__note">No drawing</span>
      </div>
    );
  }
  if (src === null) {
    return (
      <div className={`${classes.join(" ")} structure--wait`} aria-busy="true">
        <span className="structure__wait" aria-hidden="true">
          +
        </span>
        <span className="visually-hidden">Loading drawing</span>
      </div>
    );
  }
  return (
    <div className={classes.join(" ")}>
      <img
        className="structure__img"
        src={src}
        alt={alt}
        loading="lazy"
        decoding="async"
        onError={() => setBrokenSrc(src)}
      />
    </div>
  );
}
