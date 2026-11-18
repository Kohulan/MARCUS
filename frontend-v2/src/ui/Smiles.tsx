import { useToast } from "./Toasts";
import "./ui.css";

type SmilesProps = {
  value: string;
  /** Rejected: struck through in muted. */
  struck?: boolean;
};

/** A SMILES string in mono, wrapping anywhere, with a Copy button. */
export default function Smiles({ value, struck = false }: SmilesProps) {
  const toast = useToast();

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      toast("SMILES copied");
    } catch {
      toast("Could not copy", "error");
    }
  };

  return (
    <div className={struck ? "smiles smiles--struck" : "smiles"}>
      <code className="smiles__value">{value}</code>
      <button
        type="button"
        className="smiles__copy"
        aria-label="Copy SMILES"
        onClick={() => void copy()}
      >
        Copy
      </button>
    </div>
  );
}
