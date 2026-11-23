// The editor's left panel: the crop the engines read, so the curator sees what the paper
// shows while drawing. "Find on paper" swaps the crop for the page with only this
// structure's box marked (pageBox, as the paper view places it), "Back" returns. Ketcher on
// the right is untouched by either.
import { useRef, useState } from "react";
import { GlassButton } from "../ui/GlassButton";
import { boxStyle } from "./pageBox";

export type EditorSourceInfo = {
  /** The crop (a segment's image, or the uploaded single image). */
  image: string;
  /** The structure's page: 300 DPI page PNG, bbox in its pixels, 0-based page. Null: no page. */
  page: { url: string; bbox: [number, number, number, number]; page0: number } | null;
};

export function EditorSource({ source }: { source: EditorSourceInfo }) {
  const page = source.page;
  const [onPage, setOnPage] = useState(false);
  // The page's natural size, from its load: the marker waits for it.
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  // One button for "Find on paper" and "Back": the same element keeps the focus (focused on
  // click too: Safari and tests do not focus a clicked button).
  const button = useRef<HTMLButtonElement>(null);
  const toggle = () => {
    setOnPage((v) => !v);
    button.current?.focus();
  };
  return (
    <div className="editor-src">
      <div className="editor-src__view">
        {onPage && page ? (
          <div className="editor-src__sheet">
            <img
              className="editor-src__img"
              src={page.url}
              alt={`Page ${page.page0 + 1}`}
              onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
            />
            {size && size.w > 0 && size.h > 0 ? (
              <span className="editor-src__mark" aria-hidden="true" style={boxStyle(page.bbox, size.w, size.h)} />
            ) : null}
          </div>
        ) : (
          <img
            className="editor-src__img editor-src__crop"
            src={source.image}
            alt={page ? "Crop the engines read" : "Uploaded image"}
          />
        )}
      </div>
      {page ? (
        <div className="editor-src__bar">
          <GlassButton ref={button} tint="clear" size="sm" onClick={toggle}>
            {onPage ? "Back" : "Find on paper"}
          </GlassButton>
        </div>
      ) : null}
    </div>
  );
}
