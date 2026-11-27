// An on/off switch in porcelain: a rocker of two halves, the side that holds raised (green for On),
// the other pressed in. role="switch"; Space and Enter flip it (a native button).
import "./switch.css";

export default function Switch({
  label,
  checked,
  onChange,
  disabled = false,
  on = "On",
  off = "Off",
}: {
  /** Its name, shown before the rocker. */
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  on?: string;
  off?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      className="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    >
      <span className="switch__name" aria-hidden="true">
        {label}
      </span>
      <span className="switch__rocker" aria-hidden="true">
        <span className="switch__half switch__half--on">{on}</span>
        <span className="switch__half switch__half--off">{off}</span>
      </span>
    </button>
  );
}
