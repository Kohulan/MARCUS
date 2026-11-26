// "Browse your history" on the landing page (owner request 2026-11-26): only for a browser that
// already has papers or images. Asked after the page is up (the page is pre-rendered without
// it); /api/v2/history never makes a browser owner, so a first visit leaves no trace. Any
// failure: no link.
import { faClockRotateLeft } from "@fortawesome/free-solid-svg-icons";
import { useEffect, useState } from "react";
// plain fetch, not api.*: a 200 here sets no cookie, so it must not mark the owner as ready
import { BASE } from "../api/client";
import type { HistoryReply } from "../api/types";
import { GlassLink } from "../ui/GlassButton";
import Icon from "../ui/Icon";

export default function HistoryLink() {
  const [has, setHas] = useState(false);
  useEffect(() => {
    let live = true;
    fetch(`${BASE}/history`, { credentials: "same-origin" })
      .then((r) => (r.ok ? (r.json() as Promise<Partial<HistoryReply>>) : null))
      .then((body) => {
        if (live && typeof body?.items === "number" && body.items > 0) setHas(true);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  if (!has) return null;
  return (
    <p className="act__sample act__history">
      <GlassLink tint="clear" to="/app">
        <Icon icon={faClockRotateLeft} />
        Browse your history
      </GlassLink>
    </p>
  );
}
