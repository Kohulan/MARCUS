import uuid

import pytest

from marcus.core import storage
from marcus.core.settings import get_settings

U = uuid.UUID("12345678-1234-5678-1234-567812345678")
V = uuid.UUID("87654321-4321-8765-4321-876543218765")


def test_storage_paths_are_under_data_root():
    root = get_settings().data_root.resolve()
    paths = [
        storage.pdf_path(U),
        storage.page_image_path(U, 3),
        storage.image_job_path(V),
        storage.paper_dir(U),
    ]
    for p in paths:
        assert p.resolve().is_relative_to(root)


def test_storage_layout():
    root = get_settings().data_root
    assert storage.pdf_path(U) == root / "papers" / str(U) / "source.pdf"
    assert storage.page_image_path(U, 3) == root / "papers" / str(U) / "pages" / "0003.png"
    assert storage.image_job_path(V) == root / "images" / f"{V}.png"


def test_storage_rejects_non_uuid():
    with pytest.raises(TypeError):
        storage.pdf_path("../../etc/passwd")
    with pytest.raises(TypeError):
        storage.page_image_path(U, "1")
    with pytest.raises(TypeError):
        storage.image_job_path("x")
    with pytest.raises(TypeError):
        storage.paper_dir("x")


def test_depiction_paths_are_per_owner():
    root = get_settings().data_root
    sha = "ab" + "0" * 62
    owner = uuid.UUID(int=7)
    base = root / "depictions" / str(owner) / "ab"
    assert storage.depiction_path(owner, sha) == base / f"{sha}.svg"
    assert storage.depiction_marker_path(owner, sha) == base / f"{sha}.nodraw"
    other = uuid.UUID(int=8)
    assert storage.depiction_path(other, sha) != storage.depiction_path(owner, sha)
    with pytest.raises(TypeError):
        storage.depiction_path(str(owner), sha)
    with pytest.raises(TypeError):
        storage.depiction_marker_path("../x", sha)


@pytest.mark.parametrize(
    "bad",
    ["A" * 64, "a" * 63, "a" * 65, "../" + "a" * 61, "g" * 64, "a" * 63 + "\n", b"a" * 64, None],
)
def test_depiction_path_rejects_bad_sha(bad):
    with pytest.raises(ValueError):
        storage.depiction_path(uuid.UUID(int=7), bad)
    with pytest.raises(ValueError):
        storage.depiction_marker_path(uuid.UUID(int=7), bad)
