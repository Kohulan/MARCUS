import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import "./ui.css";

const MIN_WIDTH = 1024;

/**
 * The tool needs at least 1024 px. Below that it shows one note. Measured in an effect,
 * so the server (and the first client render) shows the children. Used only under /app.
 */
export default function DesktopOnly({ children }: { children: ReactNode }) {
  const [wide, setWide] = useState(true);

  useEffect(() => {
    const measure = () => setWide(window.innerWidth >= MIN_WIDTH);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  if (wide) return <>{children}</>;
  return (
    <main className="desktop-only">
      <p className="desktop-only__note">MARCUS is made for a desktop screen</p>
    </main>
  );
}
