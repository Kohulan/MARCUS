"""The row lock the planner and its helpers share (SELECT ... FOR UPDATE). Its own module, so
marcus.core.built and marcus.core.pipeline both use it without importing each other (code
scanning py/cyclic-import, 2026-11-26)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session


def lock_row(session: Session, model, row_id: uuid.UUID):
    """SELECT ... FOR UPDATE of one row (fresh attributes), or None."""
    return session.execute(
        select(model)
        .where(model.id == row_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
