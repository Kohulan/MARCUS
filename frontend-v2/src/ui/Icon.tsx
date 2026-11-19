import type { IconDefinition } from "@fortawesome/free-solid-svg-icons";
import "./ui.css";

/**
 * One Font Awesome Free 6.7.2 icon (CC BY 4.0, https://fontawesome.com/license/free) as an
 * inline <svg>: its viewBox and path from the icon's definition, no web font, no script, no
 * injected CSS, so it pre-renders and keeps the CSP. Always decorative: the words next to it
 * name the thing. Import only the named icons used, so the bundle carries just those.
 */
export default function Icon({ icon, className }: { icon: IconDefinition; className?: string }) {
  const [width, height, , , path] = icon.icon;
  const paths = Array.isArray(path) ? path : [path];
  return (
    <svg
      className={className ? `fa ${className}` : "fa"}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      focusable="false"
    >
      {paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
