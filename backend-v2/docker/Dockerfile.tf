# syntax=docker/dockerfile:1.7
# MARCUS v2 TensorFlow worker image (extra "tf"), one image for both TF workers: segment_page
# with DECIMER Segmentation (worker-segment, the default CMD) and the DECIMER OCSR engines
# `decimer` and `decimer-hand` (worker-decimer, q.decimer).
#
# Model stack = what the shipped v1 image runs (its `pip freeze`, controller ruling R10; table
# in docker/MODEL_PINS.md). The "tf" extra comes from uv.lock; the model stack is installed over
# it with every package pinned, including the transitive closure (resolved against the v1
# freeze for Python 3.11). Where both pin a package (numpy, pillow, packaging, click) the v1
# version wins; typing-extensions stays at the lock's 4.16.0 (pydantic needs >=4.16, TF any).
# decimer_segmentation is installed --no-deps, as in v1 (backend/Dockerfile), at the commit
# v1's `development` branch resolved to. decimer==2.8.0 (OCSR) is installed --no-deps from
# PyPI as in v1, with the packages it imports pinned from the v1 freeze (efficientnet,
# Keras-Applications, pillow_heif, selfies, PyYAML). The dependency check allows exactly the
# declared-but-unused requirements: opencv-python for both packages (we ship the headless build
# of the same version), ipython and numba (never imported by decimer_segmentation).
#
# VARIANT (build arg) selects the base and the CUDA libraries; the Python packages are the same:
#   cpu  (default) python:3.11-slim-bookworm, no CUDA libraries; TF runs on CPU.
#   cuda v1's runtime (docker-compose.gpu.yml, image marcus-v2-tf:cuda). TF 2.15.1 is a CUDA 12.2 /
#        cuDNN 8 build that loads its CUDA libraries at runtime: LD_LIBRARY_PATH first, then the
#        RUNPATH of libtensorflow_framework.so.2 (site-packages/nvidia/*/lib), then ld.so.cache.
#        In v1 (base nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04, LD_LIBRARY_PATH incl.
#        /usr/local/cuda/lib64) that resolves to: cudart 12.8.90, cuBLAS 12.8.4.1, cuFFT 11.3.3.83,
#        cuSPARSE 12.5.8.93, NCCL 2.27.5 from the nvidia-*-cu12 wheels, but cuSOLVER 11.4.1.48
#        (CUDA 11.8, LD_LIBRARY_PATH) and cuDNN 8.9.6.50 (ld.so.cache) from the base image; ptxas
#        from nvidia-cuda-nvcc-cu12 12.2.140. The cuda variant therefore uses the same base image,
#        the same LD_LIBRARY_PATH and those wheels at the v1 versions (measured with a loader probe,
#        docker/MODEL_PINS.md). Python 3.11 is not in Ubuntu 22.04, so uv installs CPython 3.11.14
#        (python-build-standalone) under /opt/python. The wheels TF never loads (torch's cuDNN 9,
#        cuSPARSELt, cuFile, NVSHMEM, ...) are not installed.
#
# Weights are downloaded at BUILD time with a pinned sha256 under PYSTOW_HOME=/opt/pystow, where
# the packages look for them (pystow). Runtime needs no network; the root filesystem stays
# read-only.
# - Mask R-CNN weights (mask_rcnn_molecule.h5, 273 MB, Zenodo record 10663579) into
#   /opt/pystow/DECIMER-Segmentation_model/.
# - DECIMER OCSR SavedModels (Zenodo 8300489 models.zip and 10781330
#   DECIMER_HandDrawn_model.zip, 285 MB each) unpacked into /opt/pystow/DECIMER-V2/ with the
#   `.model_url` marker that decimer's ensure_models() writes after a download, so it finds them
#   and downloads nothing. The unpacked files are identical to v1's runtime-downloaded cache.
#
# Targets: `runtime` (the worker, default for compose) and `test` (+ pytest and tests/, for
# `pytest -m ml` in this image). Build context: backend-v2/.

ARG VARIANT=cpu

FROM ghcr.io/astral-sh/uv:0.10.0 AS uv

# Python 3.11 base per variant; MARCUS_PYTHON is the interpreter the venv is built on.
FROM python:3.11-slim-bookworm AS base-cpu
ENV MARCUS_PYTHON=/usr/local/bin/python3.11

FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04 AS base-cuda
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    UV_PYTHON_INSTALL_DIR=/opt/python uv python install 3.11.14 \
    && chmod -R a+rX /opt/python \
    && /opt/python/cpython-3.11.14-linux-x86_64-gnu/bin/python3.11 -c "import ssl, sqlite3, ctypes"
# As v1 (backend/Dockerfile): the CUDA 11.8 libraries are searched before TF's RUNPATH.
ENV MARCUS_PYTHON=/opt/python/cpython-3.11.14-linux-x86_64-gnu/bin/python3.11 \
    LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/cuda/lib64

FROM base-${VARIANT} AS base

FROM base AS builder
ARG VARIANT
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 UV_COMPILE_BYTECODE_TIMEOUT=600 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-editable --extra tf --python "$MARCUS_PYTHON"
# cuda: the nvidia-*-cu12 wheels TF loads in v1, at the v1 versions (pip check below covers them).
RUN --mount=type=cache,target=/root/.cache/uv \
    case "$VARIANT" in \
      cpu) ;; \
      cuda) uv pip install --python /app/.venv/bin/python \
              nvidia-cuda-runtime-cu12==12.8.90 nvidia-cublas-cu12==12.8.4.1 \
              nvidia-cufft-cu12==11.3.3.83 nvidia-cusparse-cu12==12.5.8.93 \
              nvidia-nvjitlink-cu12==12.8.93 nvidia-nccl-cu12==2.27.5 \
              nvidia-cuda-nvcc-cu12==12.2.140 ;; \
      *) echo "VARIANT must be cpu or cuda" >&2; exit 1 ;; \
    esac
# Model stack, pinned from the v1 image freeze (closure resolved for Python 3.11).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /app/.venv/bin/python \
      tensorflow==2.15.1 keras==2.15.0 tensorflow-estimator==2.15.0 \
      tensorflow-io-gcs-filesystem==0.37.1 tensorboard==2.15.2 tensorboard-data-server==0.7.2 \
      numpy==1.24.3 ml-dtypes==0.3.2 h5py==3.15.1 protobuf==4.25.8 \
      absl-py==2.4.0 astunparse==1.6.3 flatbuffers==25.12.19 gast==0.7.0 google-pasta==0.2.0 \
      grpcio==1.76.0 libclang==18.1.1 opt-einsum==3.4.0 termcolor==3.3.0 wrapt==1.14.2 \
      six==1.17.0 packaging==26.0 setuptools==84.2.1 wheel==0.48.0 \
      google-auth==2.48.0 google-auth-oauthlib==1.2.4 oauthlib==3.3.1 requests-oauthlib==2.0.0 \
      pyasn1==0.6.2 pyasn1-modules==0.4.2 rsa==4.9.1 \
      cryptography==46.0.4 cffi==2.0.0 pycparser==3.0 \
      markdown==3.10.1 markupsafe==2.1.5 werkzeug==3.1.5 \
      requests==2.32.5 urllib3==1.26.13 idna==3.4 certifi==2026.1.4 charset-normalizer==2.1.1 \
      PyMuPDF==1.26.7 opencv-python-headless==4.11.0.86 pillow==11.3.0 \
      scikit-image==0.24.0 scipy==1.13.1 imageio==2.37.2 tifffile==2025.5.10 \
      lazy-loader==0.4 networkx==3.4.2 \
      matplotlib==3.9.0 contourpy==1.3.2 cycler==0.12.1 fonttools==4.61.1 kiwisolver==1.4.9 \
      pyparsing==3.2.1 python-dateutil==2.9.0.post0 \
      pystow==0.7.0 click==8.3.1 tqdm==4.67.1 \
      efficientnet==1.1.1 keras-applications==1.0.8 pillow-heif==0.21.0 selfies==2.2.0 \
      pyyaml==6.0.2 \
    && uv pip install --python /app/.venv/bin/python --no-deps \
      "decimer_segmentation @ git+https://github.com/Kohulan/DECIMER-Image-Segmentation.git@d0045d9ef4b29a2a8d865eae55399ba1b14481bf" \
      decimer==2.8.0 \
    && { uv pip check --python /app/.venv/bin/python > /tmp/pip-check.txt 2>&1 || true; } \
    && cat /tmp/pip-check.txt \
    && ! grep -E "requires|not installed|incompatib" /tmp/pip-check.txt \
         | grep -vE "^Found [0-9]+ incompatibilit" \
         | grep -vE "decimer-segmentation\` requires \`(opencv-python|ipython|numba)\`, but it's not installed" \
         | grep -vE "decimer\` requires \`opencv-python\`, but it's not installed"

# DECIMER OCSR weights: checksummed zips, unpacked as decimer's ensure_models() would do.
FROM python:3.11-slim-bookworm AS decimer-weights
ADD --checksum=sha256:8ebc7db18fffac7e71a2cf8487708053620d124846bc9502eddac1283b431d2b \
    https://zenodo.org/record/8300489/files/models.zip /tmp/DECIMER.zip
ADD --checksum=sha256:91c70fee79b7d64c09d433ff82e2216d16070e4d098b83da2c13d34c52439fde \
    https://zenodo.org/records/10781330/files/DECIMER_HandDrawn_model.zip /tmp/DECIMER_HandDrawn.zip
COPY docker/unpack_decimer_weights.py /tmp/unpack_decimer_weights.py
RUN python /tmp/unpack_decimer_weights.py /tmp /opt/pystow/DECIMER-V2 \
    && chmod -R a+rX /opt/pystow

FROM base AS runtime
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libgomp1 tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 marcus \
    && useradd --system --uid 10001 --gid marcus --home-dir /nonexistent --shell /usr/sbin/nologin marcus \
    && mkdir -p /data && chown marcus:marcus /data
ADD --checksum=sha256:329120facb69e88add819a3216db0fbfef57e9a37d6b6db0f6149819a11d46a5 --chmod=644 \
    https://zenodo.org/record/10663579/files/mask_rcnn_molecule.h5?download=1 \
    /opt/pystow/DECIMER-Segmentation_model/mask_rcnn_molecule.h5
COPY --from=decimer-weights /opt/pystow/DECIMER-V2 /opt/pystow/DECIMER-V2
COPY --from=builder /app/.venv /app/.venv
# pystow writes /opt/pystow/README.md on first import: create it now (read-only root at runtime)
# and make the weights directory readable (ADD creates its parents root-only).
RUN chmod -R a+rX /opt/pystow \
    && PYSTOW_HOME=/opt/pystow /app/.venv/bin/python -c "import pystow" \
    && test -f /opt/pystow/README.md && chmod a+r /opt/pystow/README.md
# The project is not copied into the venv: a .pth file puts /app/src on sys.path (like an
# editable install), so a code change rebuilds only this small layer, never the dependency
# layer above. A .pth also works for `python -I` children (PYTHONPATH would be ignored there).
COPY src /app/src
RUN echo /app/src > /app/.venv/lib/python3.11/site-packages/marcus.pth \
    && /app/.venv/bin/python -m compileall -q /app/src
WORKDIR /app
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    MARCUS_DATA_ROOT=/data HOME=/tmp MPLCONFIGDIR=/tmp/matplotlib \
    PYSTOW_HOME=/opt/pystow TF_CPP_MIN_LOG_LEVEL=2 MARCUS_WORKER_PROC_ALIVE_TIMEOUT=300
USER marcus
# q.segment, ONE process (= SLOTS["q.segment"]): one model per process. Prefork: soft time
# limits need it. The model loads when the pool process starts (after the fork, ~32 s on CPU:
# hence the 300 s proc-alive timeout), never in the parent; a failed load stops the worker.
CMD ["celery", "-A", "marcus.core.celery_app:celery_app", "worker", "-Q", "q.segment", "-c", "1", \
     "--pool", "prefork", "--include", "marcus.workers.segment", "--max-tasks-per-child", "200", \
     "-n", "segment@%h", "--loglevel", "INFO"]

FROM runtime AS test
USER root
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv pip install --python /app/.venv/bin/python --no-cache \
      pytest==9.2.0 pytest-asyncio==1.5.0 iniconfig==2.3.1 pluggy==1.7.0 pygments==2.21.0
COPY pyproject.toml /app/pyproject.toml
COPY tests /app/tests
USER marcus
# The root filesystem is read-only: no pytest cache, no bytecode.
ENV PYTEST_ADDOPTS="-p no:cacheprovider"
CMD ["pytest", "-m", "ml", "tests/workers/test_decimer_segmenter.py", "-q"]

FROM runtime
