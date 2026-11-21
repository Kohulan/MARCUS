from types import SimpleNamespace


def view(paper_id=None, page=None, **kw):
    return SimpleNamespace(
        paper_id=paper_id,
        page=page,
        segment_id=kw.get("segment_id"),
        image_job_id=kw.get("image_job_id"),
        engine=kw.get("engine"),
    )
