import { GlassButton } from "../ui/GlassButton";
import { FILTERS, shownFilter, type GridFilter } from "./cardState";
import "./grid.css";

type GridFiltersProps = {
  filter: GridFilter;
  counts: Record<GridFilter, number>;
  onFilter: (filter: GridFilter) => void;
  /** Disabled when nothing is shown. */
  onSelectAll: () => void;
  shown: number;
  /** Opens focus mode (one structure at a time, with the review keys); null: no structures. */
  onReview: (() => void) | null;
};

/** The grid's filters (each with its count), the way into focus mode, and "Select all shown". */
export default function GridFilters({
  filter,
  counts,
  onFilter,
  onSelectAll,
  shown,
  onReview,
}: GridFiltersProps) {
  return (
    <div className="rg-filters">
      <div className="rg-filters__lead">
        <div className="rg-filters__set" role="group" aria-label="Filter">
          {FILTERS.filter(({ filter: f }) => shownFilter(f, filter, counts)).map(({ filter: f, label }) => (
            <button
              key={f}
              type="button"
              className="rg-filters__button"
              aria-pressed={filter === f}
              onClick={() => onFilter(f)}
            >
              {label}
              <span className="rg-filters__count">{counts[f]}</span>
            </button>
          ))}
        </div>
        <GlassButton
          tint="clear"
          size="sm"
          disabled={onReview === null}
          onClick={() => onReview?.()}
        >
          Review one by one
        </GlassButton>
      </div>
      <button
        type="button"
        className="rg-filters__all"
        disabled={shown === 0}
        onClick={onSelectAll}
      >
        Select all shown
      </button>
    </div>
  );
}
