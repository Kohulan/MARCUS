# Model pins (TF image, `docker/Dockerfile.tf`)

Controller ruling R10: the model stack is pinned to what the shipped v1 image (`marcus-backend:latest`,
Python 3.10.12) actually runs, from its `pip freeze`. v2 runs Python 3.11; the transitive closure was
resolved for 3.11 with the v1 freeze as constraints (`uv pip compile`), and every package of it is
pinned in the Dockerfile. All versions below are identical to the v1 freeze.

| package | version / commit | source |
|---|---|---|
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
| rest of the closure (absl-py, grpcio, wrapt, gast, ... 62 packages in all) | as listed in the Dockerfile | v1 image freeze |

Deviations: `typing-extensions` stays at the uv.lock version 4.16.0 (pydantic needs >= 4.16; v1 has
4.15.0; TensorFlow accepts both). Not installed although decimer_segmentation declares them: `ipython`,
`numba` (never imported by the package) and `opencv-python` (the headless build of the same version
provides `cv2`).
