"""Pick-mode candidates (owner decision 2026-11-25, "all pages or pick a structure").

In ocsr_mode `pick` a page is segmented when the user opens it, and a segment is read only when
the user picks its box (marcus.core.pipeline.read_segment). Until then the segment is a
*candidate*: a box the page draws, nothing more. It is no card, counts in no number, and is left
out of exports, bulk curation, the main figure and the repeat links. One rule, no column: a
segment of a pick paper that has no OCSR step (a cancelled one aside: "Pick a structure" while
all pages were read stops the boxes not started yet). "Read all pages" (choose_mode auto) gives every
candidate its steps, so all count from then on.
"""

from sqlalchemy import and_, select

from marcus.core.built import built_clause
from marcus.core.enums import StepKind, StepStatus
from marcus.core.models import Paper, Segment, Step


def candidate_clause():
    """SQL condition, true for a Segment row that is a candidate (correlated on Segment)."""
    of_pick_paper = (
        select(Paper.id).where(Paper.id == Segment.paper_id, Paper.ocsr_mode == "pick").exists()
    )
    read = (
        select(Step.id)
        .where(
            Step.segment_id == Segment.id,
            Step.kind == StepKind.OCSR.value,
            Step.status != StepStatus.CANCELLED.value,  # stopped by a switch back to pick
        )
        .exists()
    )
    return and_(of_pick_paper, ~read, ~built_clause())  # a built structure is no box to pick
