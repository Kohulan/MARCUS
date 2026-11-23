// The editor's left panel: the crop the engines read, so the curator sees what the paper
// shows while drawing. "Find on paper" swaps the crop for the page with only this
// structure's box marked (pageBox, as the paper view places it), "Back" returns. Ketcher on
// the right is untouched by either.
import { useEffect, useRef, useState } from "react";
import { GlassButton } from "../ui/GlassButton";
import { boxStyle } from "./pageBox";

export type EditorSourceInfo = {
  /** The crop (a segment's image, or the uploaded single image). */
  image: string;
  /** The structure's page: 300 DPI page PNG, bbox in its pixels, 0-based page. Null: no page. */
  page: { url: string; bbox: [number, number, number, number]; page0: number } | null;
};

export function EditorSource({ source }: { source: EditorSourceInfo }) {
  const [view, setView] = useState<"crop" | "page">("crop");
  // The page's natural size, from its load: the marker waits for it.
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const find = useRef<HTMLButtonElement>(null);
  const back = useRef<HTMLButtonElement>(null);

  // Focus follows the switch (not on opening: the dialog puts it in the SMILES field).
  const switched = useRef(false);
  useEffect(() => {
    if (!switched.current) return;
    (view === "page" ? back : find).current?.focus();
  }, [view]);
  const show = (next: "crop" | "page") => {
    switched.current = true;
    setView(next);
  };

  const page = source.page;
  return (
    <div className="editor-src">
      {view === "page" && page ? (
        <>
          <div className="editor-src__view">
            <div className="editor-src__sheet">
              <img
                className="editor-src__img"
                src={page.url}
                alt={`Page ${page.page0 + 1}`}
                onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
              />
              {size && size.w > 0 && size.h > 0 ? (
                <span
                  className="editor-src__mark"
                  aria-hidden="true"
                  style={boxStyle(page.bbox, size.w, size.h)}
                />
              ) : null}
            </div>
          </div>
          <div className="editor-src__bar">
            <GlassButton ref={back} tint="clear" size="sm" onClick={() => show("crop")}>
              Back
            </GlassButton>
          </div>
        </>
      ) : (
        <>
          <div className="editor-src__view">
            <img className="editor-src__img editor-src__crop" src={source.image} alt={source.page ? "Crop the engines read" : "Uploaded image"} />
          </div>
          {page ? (
            <div className="editor-src__bar">
              <GlassButton ref={find} tint="clear" size="sm" onClick={() => show("page")}>
                Find on paper
              </GlassButton>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
