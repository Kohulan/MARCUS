import type { ReactNode } from "react";
import "./ui.css";

type SpecimenLabelProps = {
  title: string;
  rows?: [string, ReactNode][];
  /** "failed" lays the rows on the hatched failed ground. */
  tone?: "ink" | "failed";
};

/**
 * The specimen label kept from Field Sheet: a charcoal header bar in on-charcoal mono
 * uppercase, then ruled key/value rows. A table, so each value is read with its key.
 */
export default function SpecimenLabel({ title, rows = [], tone = "ink" }: SpecimenLabelProps) {
  return (
    <table className={tone === "failed" ? "specimen specimen--failed" : "specimen"}>
      <caption className="specimen__head">{title}</caption>
      {rows.length > 0 && (
        <tbody>
          {rows.map(([key, value]) => (
            <tr key={key}>
              <th scope="row">{key}</th>
              <td>{value}</td>
            </tr>
          ))}
        </tbody>
      )}
    </table>
  );
}
