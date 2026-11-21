# Model pins

## TF image (`docker/Dockerfile.tf`)

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
| tensorflow | 2.15.1 (no `[and-cuda]` extra; the CUDA libraries of the `cuda` variant are listed below) | v1 image freeze |
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

Segmentation cache version: `MARCUS_SEG_VERSION` in `docker-compose.yml` (anchor `x-seg-version`,
set on api, worker-cpu and worker-segment) is the same decimer_segmentation commit
`d0045d9ef4b29a2a8d865eae55399ba1b14481bf` (= `DecimerSegmenter.version`). The planner stores a
paper's segmentation under `<segmenter version>|dpi300` and reuses it for the same PDF bytes only
while `MARCUS_SEG_VERSION` names the running segmenter: change it together with the pin above
(`tests/deploy/test_compose_config.py` checks they match). Unset = the cache is never used.

Runtime difference from v1 (same weights, same calls): v1 loads both DECIMER OCSR models when
`DECIMER` is imported; v2 loads the hand-drawn model on its first `decimer-hand` request
(`marcus.workers.ocsr.decimer`).


## Torch image (`docker/Dockerfile.torch`)

Same rule (R10): the shipped v1 image's `pip freeze`. Installed are torch/torchvision, the two
OCSR packages (`--no-deps`, as v1's `backend/Dockerfile`) and exactly the packages they import at
runtime (measured in the v1 image: `sys.modules` after importing both and their predict modules),
with the closure resolved for Python 3.11 against the v1 freeze (`uv pip compile`). Every version
is the v1 one.

| package | version / commit | source |
|---|---|---|
| MolNexTR (engine `molnextr`, version `fb7505b`) | git `Kohulan/MolNexTR` @ `fb7505bed4774d13e8feae2aafbb57da22114512` (v1's unpinned `git+...MolNexTR.git` resolved to this), `--no-deps` | v1 image freeze |
| MolNexTR checkpoint `molnextr_best.pth` | Hugging Face dataset `CYF200127/MolNexTR` revision `9ac2da6fa553e1d053af3d8d534b8a6c74b79749`, sha256 `5990bc19aaafa5cf44e9d04e06fb8e2b5aea50c66e1e925f662bdff7d2a6422c` (1,134,334,833 bytes), baked at `/opt/pystow/molnextr/` | the URL `MolNexTRSingleton._initialize_model` downloads at runtime (`.../resolve/main/molnextr_best.pth`); identical (sha256) to v1's runtime-downloaded file in `judges/stack/data/cache/molnextr/` |
| MolScribe (engine `molscribe`, version `250f683`) | git `CrystalEye42/MolScribe` @ `250f683f52f5050eb624870ccfd04bccbcaa27e1`, `--no-deps` | v1 Dockerfile and freeze |
| MolScribe checkpoint `swin_base_char_aux_1m.pth` | Hugging Face model `yujieq/MolScribe` revision `a0189776b7415b82795c7ee81eed311bf5c8724b`, sha256 `6f0df56fa32b5ffc21f8c7f311ef333da522f590bf5622e966c6bcb1f2d9ea1d` (1,134,940,406 bytes), baked at `/opt/pystow/molscribe/` | v1's `hf_hub_download("yujieq/MolScribe", "swin_base_char_aux_1m.pth")`; identical (sha256, same revision) to v1's Hugging Face cache in `judges/stack/data/hf/` |
| torch / torchvision | 2.10.0 / 0.25.0 | v1 image freeze |
| OpenNMT-py / SmilesPE | 2.2.0 / 0.0.3, `--no-deps` (their other requirements are never imported) | v1 image freeze |
| timm / albumentations / qudida / torchtext / sentencepiece | 0.4.12 / 1.1.0 / 0.0.4 / 0.5.0 / 0.2.1 | v1 image freeze |
| rdkit | 2024.9.5 (both libraries build SMILES and molfile with RDKit) | v1 image freeze |
| numpy / opencv-python-headless / pillow | 1.24.3 / 4.11.0.86 / 11.3.0 | v1 image freeze |
| scipy / scikit-image / scikit-learn / pandas / matplotlib | 1.13.1 / 0.24.0 / 1.7.2 / 2.2.3 / 3.9.0 | v1 image freeze |
| pystow / opt-einsum / sympy / networkx | 0.7.0 / 3.4.0 / 1.14.0 / 3.4.2 | v1 image freeze |
| rest of the closure (joblib, threadpoolctl, imageio, tifffile, ...; 46 pinned packages plus torch and torchvision) | as listed in the Dockerfile | v1 image freeze |

**torch build variant** (build arg `VARIANT`; `docker-compose.gpu.yml` builds `cuda`):

- `cpu` (default, the image built and tested in B3): `torch==2.10.0+cpu`, `torchvision==0.25.0+cpu`
  from `download.pytorch.org/whl/cpu`; no CUDA libraries. `marcus-v2-torch:local` is this build.
- `cuda` (torch 2.10.0+cu128): the build v1 runs (`torch.__version__` `2.10.0+cu128`, `torch.version.cuda` `12.8` in
  `marcus-backend:latest`). Installed as v1 did, from PyPI (`torch==2.10.0`, `torchvision==0.25.0`,
  `--no-deps`; the default PyPI wheel is the CUDA 12.8 build, and v1's torch has no
  `direct_url.json`, i.e. it came from PyPI), plus the CUDA wheels at the v1 versions, checked by
  the dependency check: nvidia-cublas-cu12 12.8.4.1, nvidia-cuda-cupti-cu12 12.8.90, nvidia-cuda-nvrtc-cu12
  12.8.93, nvidia-cuda-runtime-cu12 12.8.90, nvidia-cudnn-cu12 9.10.2.21, nvidia-cufft-cu12
  11.3.3.83, nvidia-cufile-cu12 1.13.1.3, nvidia-curand-cu12 10.3.9.90, nvidia-cusolver-cu12
  11.7.3.90, nvidia-cusparse-cu12 12.5.8.93, nvidia-cusparselt-cu12 0.7.1, nvidia-nccl-cu12 2.27.5,
  nvidia-nvjitlink-cu12 12.8.93, nvidia-nvshmem-cu12 3.4.5, nvidia-nvtx-cu12 12.8.90, triton 3.6.0,
  cuda-bindings 12.9.4, cuda-pathfinder 1.3.3. Same `python:3.11-slim-bookworm` base as `cpu`: no
  system CUDA is needed (see "CUDA libraries" below). Built in C4 as `marcus-v2-torch:cuda`.

Not installed although declared (never imported at runtime; the build's dependency check allows
exactly these): MolNexTR's `pytorch-lightning`, `pyonmttok` and `opencv-python`; MolScribe's
`opencv-python` and `rdkit-pypi` (the headless build of the same OpenCV and `rdkit` provide them);
OpenNMT-py's `configargparse`, `tensorboard`, `flask`, `waitress`, `pyonmttok`; SmilesPE's
`fastprogress` and `gensim`. MolScribe declares `torch<2.0`; v1 runs it with torch 2.10.0 as well.
Also not installed: `huggingface-hub` (v1 used it only for `hf_hub_download`; timm imports it
optionally and, with v1's 0.36.0, treats it as absent anyway). `typing-extensions` stays at the
uv.lock version 4.16.0, as in the TF image.

Runtime differences from v1 (same weights, same library calls):

- Both libraries convert the decoded graph to SMILES/molfile with
  `convert_graph_to_smiles(..., num_workers=16)`, a `multiprocessing.Pool` per prediction. That
  raises `AssertionError: daemonic processes are not allowed to have children` inside a Celery
  prefork pool process (checked). v2 runs the same per-structure function
  (`_convert_graph_to_smiles`) in-process, in the same order, then the same `zip` / `np.mean`
  (`marcus.workers.ocsr.torch_common.serial_graph_conversion`). MolNexTR's own `num_workers <= 1`
  branch would do the same but raises `NameError: itertools` at the pinned commit (never imported
  in `MolNexTR/chemical.py`).
- torch CPU threads are capped (`MARCUS_TORCH_THREADS`, default 4 in settings and compose, inter-op
  1); v1 used torch's default (every core).
- An empty molfile (v1 returns `""` when the graph could not be converted) is stored as no molfile.

- MolNexTR is called one level below v1's `get_predictions`:
  `MolNexTRSingleton.get_instance().predict_final_results(path, return_atoms_bonds=False)`, reading
  `predicted_smiles` / `predicted_molfile` (`get_predictions` only filters those keys, so the output
  is byte-identical). `get_predictions` wraps the prediction in `except Exception`: it resets the
  singleton, loads the model again (re-detecting the hardware, so on CUDA again when visible) and
  predicts again. That would swallow Celery's soft time limit (a step at 30 s would reload and run
  into the 45 s hard kill) and, on a GPU, hold two models or fall back to CPU for good. In v2 an
  error reaches the step, which is retried once. If the singleton's own model setup falls back to
  CPU ("CPU (fallback)") while CUDA is visible, the load is refused and the worker stops.

Kept from v1 as is (library behaviour): MolNexTR logs `name 'rdFMCS' is not defined` for some
structures (an unimported name in an exception path of its post-processing; output unchanged).


## CUDA libraries of the `cuda` variants (Task C4)

Neither image can use a GPU on the build host; what was checked is which library file each
framework would load, with a loader probe run in v1's `marcus-backend:latest` and in the v2 image
(`--network none`, no GPU). The probe emulates the dynamic loader's search for every library the
framework asks for (DT_RPATH, `LD_LIBRARY_PATH`, the caller's DT_RUNPATH with `$ORIGIN` expanded,
ld.so.cache, default dirs), loads each hit with ctypes and asks it for its version where a call
works without a driver; for torch it also lists the CUDA libraries mapped after `import torch`
(`/proc/self/maps`). Result: **identical in v1 and v2, library by library.**

TensorFlow 2.15.1 (`tf.sysconfig.get_build_info()`: `cuda_version` 12.2, `cudnn_version` 8,
`is_cuda_build` True; compute capabilities sm_50, sm_60, sm_70, sm_75, compute_80). TF dlopens its
CUDA libraries from `libtensorflow_framework.so.2`, whose RUNPATH points into
`site-packages/nvidia/*/lib`; `LD_LIBRARY_PATH` (which v1 extends by `/usr/local/cuda/lib64`) comes
first and ld.so.cache last:

| library TF asks for | found via | file / package | version reported |
|---|---|---|---|
| libcudart.so.12 | RUNPATH | nvidia-cuda-runtime-cu12 12.8.90 | cudaRuntimeGetVersion 12080 |
| libcublas.so.12, libcublasLt.so.12 | RUNPATH | nvidia-cublas-cu12 12.8.4.1 | 12.8.4 |
| libcufft.so.11 | RUNPATH | nvidia-cufft-cu12 11.3.3.83 | cufftGetVersion 11303 |
| libcusolver.so.11 | LD_LIBRARY_PATH | base image CUDA 11.8 `libcusolver.so.11.4.1.48` | 11.4.1 |
| libcusparse.so.12 | RUNPATH | nvidia-cusparse-cu12 12.5.8.93 | 12.5.8 |
| libcudnn.so.8 (+ ops/cnn/adv_infer) | ld.so.cache | base image `libcudnn8` 8.9.6.50 (CUDA 11.8 build) | cudnnGetVersion 8906 |
| libnccl.so.2 | RUNPATH (`_pywrap_tensorflow_internal.so`) | nvidia-nccl-cu12 2.27.5 | 22705 |
| libcupti.so.12, libnvinfer.so.8 | not found (as in v1) | - | - |
| ptxas (XLA) | `site-packages/nvidia/cuda_nvcc/bin` | nvidia-cuda-nvcc-cu12 12.2.140 | - |

So `marcus-v2-tf:cuda` uses v1's base image `nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04` (for
cuDNN 8.9.6 and cuSOLVER 11.4.1, which TF really takes from there), the same `LD_LIBRARY_PATH`, and
exactly the wheels above (+ nvidia-nvjitlink-cu12 12.8.93, which cuFFT/cuSPARSE need). Python: 3.11
is not packaged for Ubuntu 22.04, so uv installs CPython 3.11.14 (python-build-standalone) under
`/opt/python` (the CPU image has Debian's python:3.11-slim 3.11.18). Not installed, because TF
never loads them: the torch-only wheels of v1's shared environment (nvidia-cudnn-cu12 9.x, which
has no `libcudnn.so.8`; nvidia-cusolver-cu12, shadowed by `LD_LIBRARY_PATH`; cuSPARSELt, cuFile,
cuRAND, NVSHMEM, NVTX, NVRTC, CUPTI).

torch 2.10.0+cu128 (`torch.version.cuda` 12.8, `torch.backends.cudnn.version()` 91002): its CUDA
libraries carry a DT_RPATH to `site-packages/nvidia/*/lib`, searched before `LD_LIBRARY_PATH`, so
v1's CUDA 11.8 base image plays no part. Loaded after `import torch` (21 files, same in v1 and v2):
cuBLAS/cuBLASLt 12.8.4.1, CUPTI 12.8.90, NVRTC 12.8.93, cudart 12.8.90, cuDNN 9.10.2.21 (libcudnn,
libcudnn_graph), cuFFT 11.3.3.83, cuFile 1.13.1.3, cuRAND 10.3.9.90, cuSOLVER 11.7.3.90, cuSPARSE
12.5.8.93, cuSPARSELt 0.7.1, NCCL 2.27.5, nvJitLink 12.8.93, NVSHMEM 3.4.5, NVTX 12.8.90 and torch's
own libc10_cuda / libtorch_cuda / libtorch_nvshmem; the NEEDED entries of libtorch_cuda,
libtorch_cuda_linalg, libtorch_global_deps and libc10_cuda (20) resolve identically.

Images (built locally, never pushed):

| image | base | disk (`docker images`) | content size |
|---|---|---|---|
| `marcus-v2-tf:cuda` | nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04 + CPython 3.11.14 | 14.8 GB | 5.34 GB |
| `marcus-v2-torch:cuda` | python:3.11-slim-bookworm (3.11.18) | 17.3 GB | 6.61 GB |

Host needs: an NVIDIA driver that supports CUDA 12.8 (torch cu128; the same holds for v1 today)
and a card TF 2.15 can run (built for sm_50-sm_75 + compute_80 PTX, JIT via ptxas 12.2 for newer
cards). Both are D4 checks on the production host.


## CPU worker image (`docker/Dockerfile.cpu`)

torch / torchvision for docling are the CPU-only builds (`2.15.0+cpu` / `0.29.2+cpu` from
`download.pytorch.org/whl/cpu`, uv source for the `cpu` extra; ruling R9) and PyMuPDF is 1.26.7, v1's
page renderer (R12; the `api` extra pins the same, the universal lock has one PyMuPDF). The relock
also dropped PyMuPDF 2.x's `pymupdf4llm` / `pymupdf-layout` and with them `onnxruntime`: docling's
automatic OCR then selects RapidOCR on its torch backend, which is also what v1 (docling 2.70.0, no
onnxruntime) selects. Image `marcus-v2-cpu:local`: 13.4 GB -> 5.67 GB on disk (content 4.80 GB ->
1.93 GB).
