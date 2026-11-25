import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, errorText } from "../api/client";
import { refreshPaper } from "../api/queries";
import { GlassButton } from "../ui/GlassButton";
import { useToast } from "../ui/Toasts";
import "./pick.css";

/**
 * Mode `ask` (a web upload; owner decision 2026-11-25): the paper's pages and text are read,
 * nothing is segmented yet. Two choices, no more copy: every page, or pick a structure.
 */
export default function ModePrompt({ paperId }: { paperId: string }) {
  const client = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const choose = (mode: "auto" | "pick") => {
    setBusy(true);
    api
      .setMode(paperId, mode)
      .then(() => refreshPaper(client, paperId))
      .catch((err: unknown) => toast(`Not started: ${errorText(err)}`, "error"))
      .finally(() => setBusy(false));
  };
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
