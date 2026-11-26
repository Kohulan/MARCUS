import { useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { api, errorText } from "../api/client";
import { refreshPaper } from "../api/queries";
import { GlassButton } from "../ui/GlassButton";
import { Modal } from "../ui/modal";
import { useToast } from "../ui/Toasts";
import "./pick.css";

type Mode = "auto" | "pick";

/**
 * Mode `ask` (a web upload; owner decisions 2026-11-25 and 2026-11-26): the paper's pages and
 * text are read, nothing is segmented yet. A dialog asks at once (so the pick path is seen):
 * every page, or pick a structure. Closed without a choice, the same two buttons stay on the
 * page.
 */
export default function ModePrompt({
  paperId,
  name,
  pages,
  reconnect,
}: {
  paperId: string;
  /** The file name, printed as the dialog's readout. */
  name?: string | null;
  pages?: number | null;
  /** Reopens the live stream: a paper waiting for the choice is done and its stream has ended. */
  reconnect: () => void;
}) {
  const client = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(true);
  const choose = (mode: Mode) => {
    setBusy(true);
    api
      .setMode(paperId, mode)
      .then(() => {
        setAsking(false);
        reconnect();
        refreshPaper(client, paperId);
      })
      .catch((err: unknown) => toast(`Not started: ${errorText(err)}`, "error"))
      .finally(() => setBusy(false));
  };
  if (asking) {
    return (
      <ModeDialog
        name={name}
        pages={pages}
        busy={busy}
        onChoose={choose}
        onClose={() => setAsking(false)}
      />
    );
  }
  return (
    <section className="pick-ask glassbed" aria-label="What to read">
      <GlassButton tint="orange" disabled={busy} onClick={() => choose("auto")}>
        Read all pages
      </GlassButton>
      <GlassButton tint="clear" disabled={busy} onClick={() => choose("pick")}>
        Pick a structure
      </GlassButton>
    </section>
  );
}

function ModeDialog({
  name,
  pages,
  busy,
  onChoose,
  onClose,
}: {
  name?: string | null | undefined;
  pages?: number | null | undefined;
  busy: boolean;
  onChoose: (mode: Mode) => void;
  onClose: () => void;
}) {
  const id = useId();
  const first = useRef<HTMLButtonElement>(null);
  const readout = [name, pages ? `${pages} ${pages === 1 ? "page" : "pages"}` : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <Modal className="mode-ask" labelledBy={`${id}-title`} onClose={onClose} first={first} busy={busy}>
      <div className="mode-ask__head">
        <div>
          <h2 id={`${id}-title`} className="mode-ask__title">
            How should MARCUS read it?
          </h2>
          {readout && <p className="mode-ask__readout">{readout}</p>}
        </div>
        <GlassButton tint="clear" size="sm" onClick={onClose}>
          Close
        </GlassButton>
      </div>
      <div className="mode-ask__choices">
        <div className="mode-ask__choice mode-ask__choice--all">
          <button
            ref={first}
            type="button"
            className="mode-ask__go"
            disabled={busy}
            aria-describedby={`${id}-all-line`}
            onClick={() => onChoose("auto")}
          >
            <AllPagesDrawing />
            <span className="mode-ask__name">Read all pages</span>
          </button>
          <p id={`${id}-all-line`} className="mode-ask__line">
            Every structure on every page.
          </p>
        </div>
        <div className="mode-ask__choice mode-ask__choice--pick">
          <button
            type="button"
            className="mode-ask__go"
            disabled={busy}
            aria-describedby={`${id}-pick-line`}
            onClick={() => onChoose("pick")}
          >
            <PickDrawing />
            <span className="mode-ask__name">Pick a structure</span>
          </button>
          <p id={`${id}-pick-line`} className="mode-ask__line">
            Choose a page, then a box. Faster.
          </p>
        </div>
      </div>
      <p className="mode-ask__foot">You can switch later.</p>
    </Modal>
  );
}

/** Text lines and boxes of a drawn page (viewBox units). */
const LINES = [18, 26, 34, 92, 100, 108, 116, 124];
const BOXES = [
  { x: 14, y: 44, w: 40, h: 38 },
  { x: 62, y: 44, w: 44, h: 38 },
  { x: 14, y: 132, w: 50, h: 20 },
];

function Sheet({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect className="mode-art__sheet" width="120" height="164" />
      {LINES.map((ly, i) => (
        <rect key={ly} className="mode-art__text" x="14" y={ly} width={i % 3 === 2 ? 56 : 92} height="3" />
      ))}
    </g>
  );
}

/** Three pages; on the front one every box lights up in turn (the "reading" outline). */
function AllPagesDrawing() {
  return (
    <svg className="mode-art" viewBox="0 0 200 196" aria-hidden="true" focusable="false">
      <g className="mode-art__back">
        <Sheet x={62} y={6} />
      </g>
      <g className="mode-art__mid">
        <Sheet x={48} y={16} />
      </g>
      <g className="mode-art__front">
        <Sheet x={34} y={26} />
        {BOXES.map((b, i) => (
          <rect
            key={i}
            className={`mode-art__box mode-art__box--read mode-art__box--${i + 1}`}
            x={34 + b.x}
            y={26 + b.y}
            width={b.w}
            height={b.h}
          />
        ))}
      </g>
    </svg>
  );
}

/** One page; a pointer goes to one box, and that box is chosen (green). */
function PickDrawing() {
  return (
    <svg className="mode-art" viewBox="0 0 200 196" aria-hidden="true" focusable="false">
      <Sheet x={40} y={16} />
      {BOXES.map((b, i) => (
        <rect
          key={i}
          className={i === 1 ? "mode-art__box mode-art__box--chosen" : "mode-art__box mode-art__box--idle"}
          x={40 + b.x}
          y={16 + b.y}
          width={b.w}
          height={b.h}
        />
      ))}
      <g className="mode-art__hand">
        <path
          className="mode-art__pointer"
          d="M0 0 L0 22 L6 16.5 L10.5 26 L14 24.4 L9.6 15 L17 15 Z"
          transform="translate(124 74)"
        />
      </g>
    </svg>
  );
}

/**
 * A paper reading all pages can go back to picking (owner, 2026-11-26): the work not started
 * yet stops on the server (choose_mode auto -> pick); the structures read stay. "Read all
 * pages" on the pick page goes forward again.
 */
export function BackToPick({ paperId, reconnect }: { paperId: string; reconnect: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const back = () => {
    setBusy(true);
    api
      .setMode(paperId, "pick")
      .then(() => {
        reconnect();
        refreshPaper(client, paperId);
      })
      .catch((err: unknown) => toast(`Not switched: ${errorText(err)}`, "error"))
      .finally(() => setBusy(false));
  };
  return (
    <div className="pick-back">
      <GlassButton tint="clear" size="sm" disabled={busy} onClick={back}>
        Pick a structure
      </GlassButton>
    </div>
  );
}
