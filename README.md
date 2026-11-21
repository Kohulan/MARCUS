<div align="center">

<p align="center">
  <img src="docs/assets/logo_full.png" alt="MARCUS Logo" width="600">
</p>

### **M**olecular **A**nnotation and **R**ecognition for **C**urating **U**nravelled **S**tructures

[![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-2.0-blue.svg?style=for-the-badge)](https://github.com/Kohulan/MARCUS/releases/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?style=for-the-badge&logo=docker)](https://www.docker.com/)

</div>

---

## 📚 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [Getting Started](#-getting-started)
- [Development](#-development)
- [License](#-license)
- [Contact](#-contact)
- [Acknowledgements](#-acknowledgements)

---

## 🔬 Overview

<div style="## 🔬 Overview

MARCUS extracts, recognises and curates molecular structures from scientific literature: from a
PDF to segmented structure images, SMILES and molfiles, a curated annotation of the paper, and a
submission to [COCONUT](https://coconut.naturalproducts.net). It runs at
[marcus.decimer.ai](https://marcus.decimer.ai).

---

## 🧠 Key Features

<table>
  <tr>
    <td width="50%">
      <h3>📄 PDF Processing</h3>
      <ul>
        <li>Paper text and layout with Docling, DOI lookup</li>
        <li>DECIMER Segmentation finds every structure on every page</li>
        <li>Pages, segments and results kept per paper</li>
      </ul>
    </td>
    <td width="50%">
      <h3>🔬 OCSR Engines</h3>
      <ul>
        <li><b>DECIMER</b>, with a model for hand-drawn structures</li>
        <li><b>MolNexTR</b>: SMILES and molfiles with coordinates</li>
        <li><b>MolScribe</b>: structure recognition with atom positions</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3>✏️ Review and Curation</h3>
      <ul>
        <li>Compare engines side by side, edit in the Ketcher editor</li>
        <li>CDK depictions, structure lookups</li>
        <li>Submit curated structures to COCONUT</li>
      </ul>
    </td>
    <td width="50%">
      <h3>🤖 Paper Annotation</h3>
      <ul>
        <li>The local MARCUS model (llama.cpp on the server's GPU)</li>
        <li>No paper text leaves the server</li>
        <li>Every value located in the paper's text</li>
      </ul>
    </td>
  </tr>
</table>

---

## 🏗️ Architecture

- **Web UI** (`frontend-v2/`): React 18, TypeScript and Vite, served by nginx.
- **API** (`backend-v2/`): FastAPI on Postgres, with the OpenAPI schema at `/api/v2/openapi.json`.
- **Workers**: Celery queues on Redis, one per kind of work (CPU, tools, TensorFlow, PyTorch,
  the MARCUS model), so a slow engine never blocks the others.
- **Containers**: Docker Compose; nginx is the only published port.

---

## 🚀 Getting Started

**Requirements:** Docker Engine with Docker Compose. For the real engines: an NVIDIA GPU with
about 20 GB of memory (production uses a V100) and the NVIDIA Container Toolkit.

```bash
git clone https://github.com/Kohulan/MARCUS.git
cd MARCUS/backend-v2
cp .env.example .env    # set POSTGRES_PASSWORD and REDIS_PASSWORD

# CPU stack with fake engines (fast, no GPU)
docker compose -p marcus-v2 -f docker-compose.yml -f docker-compose.fake.yml up -d --build

# or the real engines on a GPU host (the MARCUS model file: MARCUS_LLM_GGUF=/path/to/model.gguf)
docker compose -p marcus-v2 -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

The app is at http://localhost:18090/. [`backend-v2/README.md`](backend-v2/README.md) has the
details: the GPU stack, the MARCUS model, the COCONUT relay, monitoring and API keys.

---

## 💻 Development

```bash
# Backend: tests need the test Postgres and Redis
cd backend-v2
docker compose -f docker-compose.test.yml up -d
uv sync --extra api --extra tools --extra dev
uv run pytest tests -m "not ml and not e2e"

# Web UI
cd frontend-v2
npm ci
npm run dev
```

---

ackground-color: #f9f9f9; padding: 15px; border-radius: 10px;">

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
- [Docling](https://github.com/docling-project/docling)
- [DECIMER Segmentation](https://github.com/Kohulan/DECIMER-Image-Segmentation)
- [Ketcher](https://github.com/epam/ketcher)
- [llama.cpp](https://github.com/ggml-org/llama.cpp)
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
