import { FILTERS, type GridFilter } from "./cardState";
import "./grid.css";

type GridFiltersProps = {
  filter: GridFilter;
  counts: Record<GridFilter, number>;
  onFilter: (filter: GridFilter) => void;
  /** Disabled when nothing is shown. */
  onSelectAll: () => void;
  shown: number;
};

/** The grid's filters (each with its count) and "Select all shown". */
export default function GridFilters({ filter, counts, onFilter, onSelectAll, shown }: GridFiltersProps) {
  return (
    <div className="rg-filters">
      <div className="rg-filters__set" role="group" aria-label="Filter">
        {FILTERS.map(({ filter: f, label }) => (
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
