import type { ReactNode } from "react";

/** A key, as shown beside an action ("Accept A"). */
export default function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}
