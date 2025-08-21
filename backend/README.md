# MARCUS Backend

FastAPI application providing molecular structure extraction and recognition services.

## Overview

The backend offers RESTful APIs for:
- **PDF Processing**: DOI extraction and chemical structure segmentation
- **OCSR Engines**: Multiple optical chemical structure recognition models
- **Molecular Depiction**: Structure visualization and format conversion
- **Text Analysis**: AI-powered chemical data extraction from literature
- **Session Management**: User concurrency control and resource management

## Architecture

- **Framework**: FastAPI with automatic API documentation
- **Versioning**: API versioning for backward compatibility
- **ML/AI**: PyTorch, TensorFlow, and OpenAI integration
- **Chemistry**: CDK (Chemistry Development Kit) for molecular operations
- **Session Control**: WebSocket-based real-time session management
- **Containerization**: Docker with NVIDIA GPU support

## API Endpoints

### PDF Processing (`/v1/decimer/`)
- `POST /extract_doi` - Extract DOI from PDF documents
- `POST /extract_segments` - Segment PDFs to identify chemical structures

### OCSR Engines (`/v1/ocsr/`)
- `POST /generate_smiles` - Convert structure images to SMILES
- `POST /generate_molfile` - Generate molfile with coordinates
- `POST /generate_both` - Generate both SMILES and molfile

### Molecular Depiction (`/v1/depiction/`)
- `POST /generate` - Create molecular visualizations
- `POST /visualize` - Render structures in various formats

### Text Analysis (`/v1/openai/`)
- `POST /extract_json` - Extract structured data from text
- `POST /extract_positions` - Identify chemical entities in text

### Session Management (`/session/`)
- WebSocket endpoints for real-time session updates
- REST endpoints for session status and queue management

## Core Modules

```
app/
├── routers/              # API endpoint definitions
├── modules/              # Core business logic
│   ├── ocsr_wrapper.py       # DECIMER, MolNexTR, MolScribe
│   ├── depiction.py          # CDK molecular visualization
│   ├── openai_wrapper.py     # AI text analysis
│   ├── session_manager.py    # User concurrency control
│   └── decimer_segmentation_wrapper.py  # PDF processing
├── middleware/           # Session validation and CORS
├── schemas/             # Pydantic data models
└── config.py           # Application configuration
```

## OCSR Engines

1. **DECIMER**: Deep learning for chemical structure recognition
2. **MolNexTR**: Transformer-based structure extraction
3. **MolScribe**: Advanced handwritten structure support

## Development Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 9000

# API documentation available at:
# http://localhost:9000/v1/docs
```

## Environment Variables

Required configuration in `.env`:
```env
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL_ID=gpt-4
MARCUS_MAX_CONCURRENT_USERS=3
MARCUS_SESSION_TIMEOUT=3600
```

## Docker Deployment

```bash
# Standard deployment
docker-compose up -d

# Apple Silicon Macs
docker-compose -f docker-compose.mac.yml up -d
```

## Requirements

- Python 3.10+
- NVIDIA GPU with ~20GB VRAM
- Docker Engine 20.10+ with NVIDIA Container Toolkit
- CUDA support for optimal performance

## Session Management

- **Concurrent Users**: Configurable limit (default: 3)
- **Queue System**: Automatic waiting queue for excess users
- **Real-time Updates**: WebSocket notifications for queue status
- **Timeout Handling**: Automatic cleanup of inactive sessions

## Performance Notes

- GPU memory constraints limit concurrent users
- TensorFlow and PyTorch models require significant VRAM
- Apple Silicon Macs use CPU-only versions for compatibility
