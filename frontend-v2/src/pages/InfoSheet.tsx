import type { ReactNode } from "react";
import { usePageTitle } from "./meta";
import "./info.css";

type InfoSheetProps = {
  title: string;
  /** The page's document title (pageMeta(url).title). */
  docTitle: string;
  lede?: string;
  /** "18 November 2026": when the text was last changed. */
  updated?: string;
  children: ReactNode;
};

/**
 * The reading layout of About, Privacy, Disclaimer and the not-found page (Read mode): the
 * title cell on the left, ruled sections at a reading measure on the right.
 */
export function InfoSheet({ title, docTitle, lede, updated, children }: InfoSheetProps) {
  usePageTitle(docTitle);
  return (
    <main className="info">
      <div className="info__head">
        <div className="info__head-inner">
          <h1>{title}</h1>
          {lede && <p className="info__lede">{lede}</p>}
          {updated && <p className="mono-label info__updated">Updated {updated}</p>}
        </div>
      </div>
      <div className="info__body">{children}</div>
    </main>
  );
}

type InfoSectionProps = {
  title: string;
  /** An anchor other pages link to ("/about#cite"). */
  id?: string;
  /** A drawing that takes the reading column's full width (the example review grid). */
  figure?: boolean;
  children: ReactNode;
};

export function InfoSection({ title, id, figure, children }: InfoSectionProps) {
  return (
    <section id={id} className={figure ? "info__section info__section--figure" : "info__section"}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}
