// A single choice between a few options: a porcelain pill with a knob that slides to the chosen
// one (the Review/Paper switch's look, workspace.css .ws-toggle). A radio group: arrow keys,
// Home and End move the choice. Each option may carry its own knob colour (`tone`) and a dot of
// that colour beside its label, so the control is its own legend (Compare's marks).
import { useLayoutEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import "./segmented.css";

export interface SegmentedOption<T extends string> {
  value: T;
  label: ReactNode;
  /** The knob's fill when this option is chosen (a CSS colour); its text colour in `ink`. */
  tone?: { fill: string; ink: string; dot?: string };
}

export default function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
  disabled = false,
}: {
  /** The group's accessible name. */
  label: string;
  value: T;
  options: readonly SegmentedOption<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
}) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const at = Math.max(0, options.findIndex((o) => o.value === value));
  const chosen = options[at];

  function move(event: KeyboardEvent, index: number) {
    const to: Record<string, number> = {
      ArrowRight: index + 1,
      ArrowDown: index + 1,
      ArrowLeft: index - 1,
      ArrowUp: index - 1,
      Home: 0,
      End: options.length - 1,
    };
    if (!(event.key in to)) return;
    event.preventDefault();
    const next = (to[event.key]! + options.length) % options.length;
    onChange(options[next]!.value);
    buttons.current[next]?.focus();
  }

  // the knob's place and tone as CSS custom properties (inline style props are not used here)
  const group = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = group.current;
    if (!el) return;
    el.style.setProperty("--seg-count", String(options.length));
    el.style.setProperty("--seg-at", String(at));
    for (const [name, v] of [["--seg-fill", chosen?.tone?.fill], ["--seg-ink", chosen?.tone?.ink]] as const) {
      if (v) el.style.setProperty(name, v);
      else el.style.removeProperty(name);
    }
    // each dot its option's colour (set here once, not by a ref on every render)
    el.querySelectorAll<HTMLElement>(".seg__dot").forEach((dot) => {
      const tone = options.find((o) => o.value === dot.dataset.value)?.tone;
      if (tone?.dot) dot.style.setProperty("--seg-dot", tone.dot);
    });
  }, [options, at, chosen]);

  return (
    <div ref={group} className="seg" role="radiogroup" aria-label={label} aria-disabled={disabled || undefined}>
      <span className="seg__knob" aria-hidden="true" />
      {options.map((option, index) => {
        const on = index === at;
        return (
          <button
            key={option.value}
            ref={(node) => {
              buttons.current[index] = node;
            }}
            type="button"
            role="radio"
            className="seg__option"
            aria-checked={on && !disabled}
            tabIndex={on ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            onKeyDown={(event) => move(event, index)}
          >
            {option.tone?.dot && (
              <span className="seg__dot" data-value={option.value} aria-hidden="true" />
            )}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
