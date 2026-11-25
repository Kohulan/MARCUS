"""papers.ocsr_mode ask and pick: "all pages or pick a structure"

Revision ID: 0022
Revises: 0021

Owner decision 2026-11-25: after a web upload the paper page asks whether to read all pages or
to pick a structure. `ask`: no segmentation until the answer; `pick`: a page is segmented and a
box read only when the user asks (marcus.core.pipeline). Only the CHECK changes.

Downgrade: only while no paper is in `ask` or `pick`.
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def _check(values) -> None:
    op.drop_constraint("ck_papers_ocsr_mode", "papers", type_="check")
    op.create_check_constraint(
        "ck_papers_ocsr_mode",
        "papers",
        "ocsr_mode IN (" + ", ".join(f"'{v}'" for v in values) + ")",
    )


def upgrade() -> None:
    _check(("auto", "off", "ask", "pick"))


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM papers WHERE ocsr_mode IN ('ask', 'pick')) THEN
                RAISE EXCEPTION 'papers in ask or pick mode exist: restore the database dump';
            END IF;
        END
        $$
        """
    )
    _check(("auto", "off"))
