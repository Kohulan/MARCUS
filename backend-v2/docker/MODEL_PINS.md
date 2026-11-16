# Model pins (TF image, `docker/Dockerfile.tf`)

Controller ruling R10: the model stack is pinned to what the shipped v1 image (`marcus-backend:latest`,
Python 3.10.12) actually runs, from its `pip freeze`. v2 runs Python 3.11; the transitive closure was
resolved for 3.11 with the v1 freeze as constraints (`uv pip compile`), and every package of it is
pinned in the Dockerfile. All versions below are identical to the v1 freeze.

| package | version / commit | source |
|---|---|---|
| decimer (OCSR: engines `decimer`, `decimer-hand`) | 2.8.0 from PyPI, `--no-deps` | v1 image freeze |
| DECIMER OCSR weights `DECIMER_model/` | Zenodo record 8300489 `models.zip`, sha256 `8ebc7db18fffac7e71a2cf8487708053620d124846bc9502eddac1283b431d2b`, unpacked at `/opt/pystow/DECIMER-V2/` with `.model_url` | the URL decimer 2.8.0 downloads at runtime (`model_urls` in `DECIMER/decimer.py`); unpacked files identical (sha256) to v1's runtime cache |
| DECIMER hand-drawn weights `DECIMER_HandDrawn_model/` | Zenodo record 10781330 `DECIMER_HandDrawn_model.zip`, sha256 `91c70fee79b7d64c09d433ff82e2216d16070e4d098b83da2c13d34c52439fde`, same place | same as above |
| efficientnet / Keras-Applications / pillow_heif / selfies / PyYAML | 1.1.1 / 1.0.8 / 0.21.0 / 2.2.0 / 6.0.2 (what decimer imports or declares) | v1 image freeze |
| decimer_segmentation | git `Kohulan/DECIMER-Image-Segmentation` @ `d0045d9ef4b29a2a8d865eae55399ba1b14481bf` (1.5.1, v1's `development` branch), `--no-deps` | v1 image freeze |
| Mask R-CNN weights `mask_rcnn_molecule.h5` | Zenodo record 10663579, sha256 `329120facb69e88add819a3216db0fbfef57e9a37d6b6db0f6149819a11d46a5`, baked at `/opt/pystow/DECIMER-Segmentation_model/` | same file v1 downloads at runtime (`MODEL_DOWNLOAD_URL` in the package) |
| tensorflow | 2.15.1 (CPU wheel, no `[and-cuda]`) | v1 image freeze |
| keras | 2.15.0 | v1 image freeze |
| tensorflow-estimator / tensorboard / tensorboard-data-server / tensorflow-io-gcs-filesystem | 2.15.0 / 2.15.2 / 0.7.2 / 0.37.1 | v1 image freeze |
| numpy | 1.24.3 | v1 image freeze |
| ml-dtypes / h5py / protobuf | 0.3.2 / 3.15.1 / 4.25.8 | v1 image freeze |
| PyMuPDF | 1.26.7 | v1 image freeze |
| opencv-python-headless | 4.11.0.86 (v1 also has `opencv-python` 4.11.0.86; same version, headless build only here) | v1 image freeze |
| pillow | 11.3.0 | v1 image freeze |
| scikit-image / scipy / matplotlib | 0.24.0 / 1.13.1 / 3.9.0 | v1 image freeze |
| pystow | 0.7.0 | v1 image freeze |
| requests / urllib3 | 2.32.5 / 1.26.13 | v1 image freeze |
| rest of the closure (absl-py, grpcio, wrapt, gast, ... 67 packages in all) | as listed in the Dockerfile | v1 image freeze |

Deviations: `typing-extensions` stays at the uv.lock version 4.16.0 (pydantic needs >= 4.16; v1 has
4.15.0; TensorFlow accepts both). Not installed although decimer_segmentation declares them: `ipython`,
`numba` (never imported by the package) and `opencv-python` (the headless build of the same version
provides `cv2`; decimer declares `opencv-python` too).

Runtime difference from v1 (same weights, same calls): v1 loads both DECIMER OCSR models when
`DECIMER` is imported; v2 loads the hand-drawn model on its first `decimer-hand` request
(`marcus.workers.ocsr.decimer`).
