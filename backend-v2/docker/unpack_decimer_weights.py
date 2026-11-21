"""Build step of docker/Dockerfile.tf: unpack the checksummed DECIMER OCSR model zips.

Lays them out exactly as decimer's `utils.ensure_models()` leaves a download: one directory
`<name>_model/` per model under pystow's `DECIMER-V2/`, with the source URL in `.model_url`
(ensure_models() re-downloads when that marker names another URL, and never when it matches).

  python unpack_decimer_weights.py <dir with DECIMER.zip, DECIMER_HandDrawn.zip> <DECIMER-V2 dir>
"""

import sys
import zipfile
from pathlib import Path

# decimer 2.8.0 `DECIMER.decimer.model_urls`
MODEL_URLS = {
    "DECIMER": "https://zenodo.org/record/8300489/files/models.zip",
    "DECIMER_HandDrawn": "https://zenodo.org/records/10781330/files/DECIMER_HandDrawn_model.zip",
}


def main(zips: Path, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, url in MODEL_URLS.items():
        with zipfile.ZipFile(zips / f"{name}.zip") as archive:
            prefix = f"{name}_model/"
            for member in archive.namelist():
                if not member.startswith(prefix) or ".." in Path(member).parts:
                    raise SystemExit(f"unexpected member {member!r} in {name}.zip")
            archive.extractall(root)
        model = root / f"{name}_model"
        if not (model / "saved_model.pb").is_file():
            raise SystemExit(f"{model}/saved_model.pb missing")
        (model / ".model_url").write_text(url)
        print(f"{model}: ok")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
