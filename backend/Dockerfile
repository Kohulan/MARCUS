FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04 AS cheminf-python-ms

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    WORKERS=2 \
    DEBIAN_FRONTEND=noninteractive \
    # Default values that will be overridden by runtime environment
    OPENAI_API_KEY="" \
    OPENAI_MODEL_ID="" \
    RELEASE_VERSION="1.0" \
    HOMEPAGE_URL="/latest/docs" \
    JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64/ \
    # Path to Docling models inside the container
    DOCLING_MODELS_PATH="/app/models/docling" \
    # CUDA environment variables
    CUDA_HOME=/usr/local/cuda \
    PATH=${PATH}:/usr/local/cuda/bin \
    LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:/usr/local/cuda/lib64

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3.10 \
    python3.10-dev \
    python3.10-venv \
    python3-pip \
    libpq-dev \
    poppler-utils \
    gcc \
    libgomp1 \
    openjdk-11-jre \
    git \
    # OpenGL libraries for transformers/PyTorch
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    # Additional libraries that might be needed
    curl \
    ffmpeg \
    libfontconfig1 \
    libxcb1 \
    libpoppler-cpp-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python3.10 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install base dependencies
RUN pip install --upgrade pip

# Install PyTorch with CUDA support
RUN pip install torch==2.1.0 torchvision==0.16.0 --index-url https://download.pytorch.org/whl/cu118

# Install the rest of the requirements
RUN pip install --no-cache-dir -r requirements.txt

# Install specialized packages
RUN pip install docling && \
    pip install decimer --no-deps && \
    pip install git+https://github.com/Kohulan/MolNexTR.git --no-deps && \
    pip install git+https://github.com/CrystalEye42/MolScribe.git@250f683f52f5050eb624870ccfd04bccbcaa27e1 --no-deps && \
    pip install git+https://github.com/Kohulan/DECIMER-Image-Segmentation.git@bbox --no-deps

RUN pip install numpy==1.24.3


# Create necessary directories
RUN mkdir -p /app/uploads/pdfs \
    /app/uploads/segments \
    /app/uploads/chem_images \
    /app/uploads/openai_results \
    /app/models/docling

# Copy prefetched models if they exist
COPY ./models/docling /app/models/docling

COPY .env* /app/

# Copy project files
COPY . .

EXPOSE 9000

# Command to run the application
CMD python -m uvicorn app.main:app --host 0.0.0.0 --port 9000