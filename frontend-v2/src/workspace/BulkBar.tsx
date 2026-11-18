import { GlassButton } from "../ui/GlassButton";
import "./grid.css";

type BulkBarProps = {
  count: number;
  /** Selected cards that are "Not read yet", and the engine that would read them. */
  notRead: number;
  engineLabel: string;
  busy: boolean;
  onAccept: () => void;
  onReject: () => void;
  onRead: () => void;
  onClear: () => void;
};

/** The actions on the selected cards; it sits at the bottom of the window while you scroll. */
export default function BulkBar({
  count,
  notRead,
  engineLabel,
  busy,
  onAccept,
  onReject,
  onRead,
  onClear,
}: BulkBarProps) {
  return (
    <div className="rg-bulk glassbed" role="group" aria-label="Selected">
      <GlassButton tint="green" disabled={busy} onClick={onAccept}>
        {`Accept ${count}`}
      </GlassButton>
      <GlassButton tint="clear" disabled={busy} onClick={onReject}>
        {`Reject ${count}`}
      </GlassButton>
      {notRead > 0 && (
        <GlassButton tint="clear" disabled={busy} onClick={onRead}>
          {`Read ${notRead} with ${engineLabel}`}
        </GlassButton>
      )}
      <GlassButton tint="clear" onClick={onClear}>
        Clear
      </GlassButton>
    </div>
  );
}
