<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/hero-dark.svg">
  <img src="docs/assets/readme/hero-light.svg" width="100%" alt="MARCUS: Molecular Annotation and Recognition for Curating Unravelled Structures. A page's structure drawing, boxed in orange, becomes a SMILES string and is accepted.">
</picture>

<p align="center">
  <a href="https://marcus.decimer.ai"><b>Open MARCUS</b></a>
  &nbsp;·&nbsp;
  <a href="https://doi.org/10.1039/d5dd00313j">Read the paper</a>
  &nbsp;·&nbsp;
  <a href="#run-it-yourself">Run it yourself</a>
  &nbsp;·&nbsp;
  <a href="#cite">Cite</a>
</p>

<p align="center">
  <a href="https://doi.org/10.1039/d5dd00313j"><img alt="DOI 10.1039/d5dd00313j" src="https://img.shields.io/badge/DOI-10.1039%2Fd5dd00313j-1E4D33?style=flat-square&labelColor=1C211D"></a>
  <a href="LICENSE"><img alt="Licence: MIT" src="https://img.shields.io/badge/licence-MIT-1E4D33?style=flat-square&labelColor=1C211D"></a>
  <a href="https://marcus.decimer.ai"><img alt="Live at marcus.decimer.ai" src="https://img.shields.io/badge/live-marcus.decimer.ai-FA3600?style=flat-square&labelColor=1C211D"></a>
  <img alt="Version 2.0" src="https://img.shields.io/badge/version-2.0-1E4D33?style=flat-square&labelColor=1C211D">
</p>

<br>

MARCUS turns a journal article into checked chemical structures for
[COCONUT](https://coconut.naturalproducts.net). It finds every structure drawing in the PDF,
reads each one with several recognition engines, and puts a person in charge of the result:
accept, fix or reject, then submit. It is open source, free, needs no login, and runs on the
group's own GPU. No paper data goes to an outside AI service.

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/pipeline-dark.svg">
  <img src="docs/assets/readme/pipeline-light.svg" width="100%" alt="PDF, then Segment (DECIMER Segmentation finds every structure drawing), Recognise (four engines turn each drawing into SMILES), Curate (you accept, fix or reject), and Submit (accepted structures go to COCONUT).">
</picture>

Results arrive one by one while the paper is still being read. A failed page or engine is
shown with its reason, never as "no structures".

## See it

<img src="docs/assets/readme/screens/review.webp" width="100%" alt="The review grid: fifteen structure cards from the sample paper, each with its drawing, its SMILES and its state (to check, accepted or rejected).">

<p align="center"><sub>THE REVIEW GRID · every structure with its SMILES, its engine and its state; bulk accept and reject</sub></p>

<table>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/assets/readme/screens/focus.webp" width="100%" alt="Focus mode: one structure large, its crop from the page, the page itself with the structure boxed, and the accept, reject, edit and compare actions with their keys.">
      <p align="center"><sub>FOCUS MODE · one structure, its crop and its page, a key for every action</sub></p>
    </td>
    <td width="50%" valign="top">
      <img src="docs/assets/readme/screens/paper.webp" width="100%" alt="Paper view: the page images with every structure boxed, the extracted text, and the structure list side by side.">
      <p align="center"><sub>PAPER VIEW · the pages, the extracted text and the structures side by side</sub></p>
    </td>
  </tr>
</table>

<sub>Screenshots of [marcus.decimer.ai](https://marcus.decimer.ai) on the built-in sample paper,
a synthetic article made for MARCUS (no copyrighted content).</sub>

## What is inside

| Step | What does it | What you get |
| :--- | :--- | :--- |
| Find the structures | [DECIMER Segmentation](https://github.com/Kohulan/DECIMER-Image-Segmentation) | a crop of every structure drawing, with its page and box |
| Read them | [DECIMER](https://github.com/Kohulan/DECIMER-Image_Transformer) (default), DECIMER hand-drawn, [MolNexTR](https://github.com/CYF2000127/MolNexTR), [MolScribe](https://github.com/thomas0809/MolScribe) | SMILES and molfiles; run all four and compare them side by side |
| Read the text | [Docling](https://github.com/docling-project/docling) | the paper's text and layout, and its DOI |
| Annotate | the MARCUS model, on [llama.cpp](https://github.com/ggml-org/llama.cpp) on the server's GPU | organism, part, place and compound names, each found in the text |
| Check and fix | [Ketcher](https://github.com/epam/ketcher), [CDK](https://cdk.github.io/) depictions, PubChem and COCONUT lookups | a structure you have looked at, edited where it was wrong |
| Hand over | JSON, CSV and SDF export; COCONUT batch submission with your own COCONUT login | the accepted structures, where they belong |

## Your data

- **No account.** Each browser owns its papers through a secret cookie.
- **Kept 30 days.** Papers and their results are deleted after that.
- **Stays on our servers.** Recognition and annotation run on the group's own GPU; no paper
  text or image goes to an outside AI service.
- **Your COCONUT login stays yours.** It goes to COCONUT through the MARCUS relay; the
  server never stores it.

## Run it yourself

You need Docker Engine with Docker Compose. For the real engines, you also need an NVIDIA GPU
with about 20 GB of memory (production uses a V100) and the NVIDIA Container Toolkit.

```bash
git clone https://github.com/Kohulan/MARCUS.git
cd MARCUS/backend-v2
cp .env.example .env    # set POSTGRES_PASSWORD and REDIS_PASSWORD

# CPU stack with fake engines (fast, no GPU)
docker compose -p marcus-v2 -f docker-compose.yml -f docker-compose.fake.yml up -d --build

# or the real engines on a GPU host (the MARCUS model file: MARCUS_LLM_GGUF=/path/to/model.gguf)
docker compose -p marcus-v2 -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

Then open http://localhost:18090/. [`backend-v2/README.md`](backend-v2/README.md) covers the GPU
stack, the MARCUS model, the COCONUT relay, monitoring and API keys.

## Architecture

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/architecture-dark.svg">
  <img src="docs/assets/readme/architecture-light.svg" width="100%" alt="The browser talks to nginx, which serves the web UI and passes /api/v2 to FastAPI on Postgres and Redis. Celery workers, one queue per kind of work, run the engines: segmentation, DECIMER, MolNexTR, MolScribe and the MARCUS model on the GPU.">
</picture>

- **Web UI** ([`frontend-v2/`](frontend-v2)): React 18, TypeScript and Vite; the static pages are
  pre-rendered, and nginx serves it all on the same domain as the API.
- **API** ([`backend-v2/`](backend-v2)): FastAPI on Postgres, with the OpenAPI schema at
  `/api/v2/openapi.json`. Scripts can use it with an API key.
- **Workers:** one Celery queue on Redis per kind of work, so a slow engine never holds up the
  others.

## Development

```bash
# Backend: the tests need the test Postgres and Redis
cd backend-v2
docker compose -f docker-compose.test.yml up -d
uv sync --extra api --extra tools --extra dev
uv run pytest tests -m "not ml and not e2e"

# Web UI
cd frontend-v2
npm ci
npm run dev
```

The README graphics are drawn by [`docs/assets/readme/build.py`](docs/assets/readme/build.py).

## Cite

If MARCUS helps your work, please cite:

> Rajan K., Weißenborn V., Lederer L., Zielesny A., Steinbeck C.
> **MARCUS: molecular annotation and recognition for curating unravelled structures.**
> *Digital Discovery* 2025, 4(11), 3137–3148.
> [doi:10.1039/d5dd00313j](https://doi.org/10.1039/d5dd00313j)

<details>
<summary>BibTeX</summary>

```bibtex
@article{rajan2025marcus,
  title   = {{MARCUS}: molecular annotation and recognition for curating unravelled structures},
  author  = {Rajan, Kohulan and Wei{\ss}enborn, Viktor and Lederer, Laurin and Zielesny, Achim and Steinbeck, Christoph},
  journal = {Digital Discovery},
  year    = {2025},
  volume  = {4},
  number  = {11},
  pages   = {3137--3148},
  doi     = {10.1039/d5dd00313j}
}
```

</details>

## Thanks

MARCUS stands on open tools:
[CDK](https://cdk.github.io/) ·
[DECIMER](https://github.com/Kohulan/DECIMER-Image_Transformer) ·
[DECIMER Segmentation](https://github.com/Kohulan/DECIMER-Image-Segmentation) ·
[Docling](https://github.com/docling-project/docling) ·
[Ketcher](https://github.com/epam/ketcher) ·
[llama.cpp](https://github.com/ggml-org/llama.cpp) ·
[MolNexTR](https://github.com/CYF2000127/MolNexTR) ·
[MolScribe](https://github.com/thomas0809/MolScribe) ·
[RDKit](https://www.rdkit.org/)

Part of the [DECIMER](https://decimer.ai) project, connected to
[COCONUT](https://coconut.naturalproducts.net) and [NFDI4Chem](https://www.nfdi4chem.de).

## Licence and contact

MIT, see [LICENSE](LICENSE). Questions:
[Kohulan Rajan](mailto:kohulan.rajan@uni-jena.de) ·
[decimer.ai](https://decimer.ai) ·
[Cheminformatics and Computational Metabolomics](https://cheminf.uni-jena.de/)

<br>

<p align="center">
  <a href="https://cheminf.uni-jena.de">
    <img src="https://github.com/Kohulan/DECIMER-Image-to-SMILES/blob/master/assets/CheminfGit.png?raw=true" width="260" alt="Cheminformatics and Computational Metabolomics, Friedrich Schiller University Jena">
  </a>
</p>
