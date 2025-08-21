<div align="center">

<p align="center">
  <img src="https://github.com/Kohulan/MARCUS/blob/main/frontend/public/logo_full.png" alt="MARCUS Logo" width="600">
</p>

### **M**olecular **A**nnotation and **R**ecognition for **C**urating **U**nravelled **S**tructures

[![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-1.0-blue.svg?style=for-the-badge)](https://github.com/Kohulan/MARCUS/releases/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.95+-009688.svg?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![Vue.js](https://img.shields.io/badge/Vue.js-3.0+-4FC08D.svg?style=for-the-badge&logo=vue.js)](https://vuejs.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?style=for-the-badge&logo=docker)](https://www.docker.com/)

</div>

---

## 📚 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [Getting Started](#-getting-started)
- [API Reference](#-api-reference)
- [Development](#-development)
- [License](#-license)
- [Contact](#-contact)
- [Acknowledgements](#-acknowledgements)

---

## 🔬 Overview

<div style="background-color: #f0f0f0; padding: 15px; border-radius: 10px;">

Project MARCUS is a comprehensive platform for extracting, recognizing, and processing molecular structures from scientific literature. The system integrates multiple advanced technologies to create an end-to-end pipeline from PDF processing to molecular structure recognition and visualization.

</div>

---

## 🧠 Key Features

<table>
  <tr>
    <td width="50%">
      <h3>📄 PDF Processing</h3>
      <ul>
        <li>Extract DOIs from scientific PDFs</li>
        <li>Segment PDFs to identify chemical structures</li>
        <li>Organize segments hierarchically</li>
      </ul>
    </td>
    <td width="50%">
      <h3>🔬 OCSR Engines</h3>
      <ul>
        <li><b>DECIMER</b>: SMILES generation with hand-drawn support</li>
        <li><b>MolNexTR</b>: SMILES and molfiles with coordinates</li>
        <li><b>MolScribe</b>: Advanced structure recognition</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3>🎨 Chemical Depiction</h3>
      <ul>
        <li>Convert SMILES/molfiles to visualizations</li>
        <li>CDK-powered high-quality rendering</li>
        <li>Multiple formats (SVG, PNG, Base64)</li>
      </ul>
    </td>
    <td width="50%">
      <h3>🤖 Text Analysis</h3>
      <ul>
        <li>Fine-tuned OpenAI model integration</li>
        <li>Extract structured chemical data from text</li>
        <li>Maintain extraction result archives</li>
      </ul>
    </td>
  </tr>
</table>

---

## 🏗️ Architecture

<div style="background-color: #e6f7ff; padding: 15px; border-radius: 10px;">

Project MARCUS follows a modern microservices architecture:

- **Backend**: FastAPI application with versioned API endpoints
- **Frontend**: Vue.js application for user interaction
- **Containerization**: Docker for consistent deployment

</div>

---

## 🚀 Getting Started

### Prerequisites

**Software Requirements:**
- Docker Engine 20.10+ with NVIDIA Container Toolkit
- Docker Compose
- Python 3.10+ (for development)
- Node.js and npm (for frontend development)
- OpenAI API key (required for AI features)
- Stable internet connectivity for OpenAI API integration

**Hardware Requirements:**

- **GPU**: NVIDIA GPU with ~20GB VRAM (development used V100)
- **CPU**: Minimum 8-core (16-core recommended)
- **RAM**: 32GB recommended (minimum requirements may vary)
- **Storage**: ~50GB for container images and processing files
- **Concurrent Users**: Up to 3 users (GPU memory limited, scalable with additional hardware)
- **Container Runtime**: Docker Engine 20.10+ with NVIDIA Container Toolkit

### Environment Configuration

Before running the application, copy the example environment file and configure your settings:

```bash
cp .env.example .env
```

**Required Environment Variables:**
- `OPENAI_API_KEY`: Your OpenAI API key for AI-powered text analysis
- `OPENAI_MODEL_ID`: OpenAI model to use (e.g., `gpt-4`, `gpt-3.5-turbo`)

**Optional Configuration:**
- `MARCUS_MAX_CONCURRENT_USERS`: Maximum concurrent users (default: 3)
- `VUE_APP_BACKEND_URL`: Backend URL for frontend (default: `http://localhost:9000`)

See `.env.example` for all available configuration options.

### Installation

**Step 1: Clone the repository**
```bash
git clone https://github.com/Kohulan/MARCUS.git
cd MARCUS
docker-compose up -d
```

**For Apple Silicon (M1/M2/M3) Mac users:**
```bash
docker-compose -f docker-compose.mac.yml up -d
```

- Access the application
- Frontend: http://localhost:8080
- API documentation: http://localhost:8000/v1/docs


### System Architecture Considerations

- **x86/x64 Systems**: Use the standard `docker-compose.yml` file which includes CUDA dependencies for optimal performance.
- **Apple Silicon Macs**: Use the Mac-specific `docker-compose.mac.yml` file which resolves TensorFlow and CUDA compatibility issues on ARM architecture.

---

## 🔌 API Reference

The API is versioned and provides the following main endpoints:

<table>
  <tr>
    <th>Category</th>
    <th>Endpoints</th>
  </tr>
  <tr>
    <td><b>PDF Processing</b></td>
    <td>
      <code>POST /v1/decimer/extract_doi</code>: Extract DOI from uploaded PDF<br>
      <code>POST /v1/decimer/extract_segments</code>: Extract chemical structure segments
    </td>
  </tr>
  <tr>
    <td><b>OCSR</b></td>
    <td>
      <code>POST /v1/ocsr/generate_smiles</code>: Generate SMILES from structure image<br>
      <code>POST /v1/ocsr/generate_molfile</code>: Generate molfile from structure image<br>
      <code>POST /v1/ocsr/generate_both</code>: Generate both SMILES and molfile
    </td>
  </tr>
  <tr>
    <td><b>Depiction</b></td>
    <td>
      <code>POST /v1/depiction/generate</code>: Generate molecular depiction<br>
      <code>POST /v1/depiction/visualize</code>: Visualize a molecular structure
    </td>
  </tr>
  <tr>
    <td><b>Text Annotation</b></td>
    <td>
      <code>POST /v1/openai/extract_json</code>: Extract structured JSON data from text<br>
      <code>POST /v1/openai/extract_positions</code>: Extract entity positions from text
    </td>
  </tr>
</table>

For complete API documentation, refer to the Swagger UI at `/v1/docs`.

---

## 💻 Development

### Backend Development

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend Development

```bash
cd frontend
npm install
npm run serve
```

---

## 📜 License

<div style="background-color: #f9f9f9; padding: 15px; border-radius: 10px;">

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

</div>

---

## 📧 Contact

- **Kohulan Rajan** - [kohulan.rajan@uni-jena.de](mailto:kohulan.rajan@uni-jena.de)
- **Website**: [https://decimer.ai](https://decimer.ai)
- **Institution**: [Cheminformatics and Computational Metabolomics](https://cheminf.uni-jena.de/)

---

## 🙏 Acknowledgements

<div style="background-color: #f0f0f0; padding: 15px; border-radius: 10px;">

This project utilizes several open-source cheminformatics tools:
- [Chemistry Development Kit (CDK)](https://cdk.github.io/)
- [DECIMER](https://github.com/Kohulan/DECIMER-Image_Transformer)
- [MolNexTR](https://github.com/CYF2000127/MolNexTR)
- [MolScribe](https://github.com/thomas0809/MolScribe)

</div>

---

<div align="center">

<p align="center">
  <a href="https://cheminf.uni-jena.de">
    <img src="https://github.com/Kohulan/DECIMER-Image-to-SMILES/blob/master/assets/CheminfGit.png" width="300">
  </a>
</p>

</div>
