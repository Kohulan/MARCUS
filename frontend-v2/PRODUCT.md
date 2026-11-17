# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Decided with the owner on 2026-11-17: Vite + React + TypeScript, React Router with the static pages (landing, about, privacy, disclaimer) pre-rendered to HTML at build time, TanStack Query for server state. Served as static files by the MARCUS v2 nginx on the same domain as the API (`/api/v2`). Full product design: `../docs/superpowers/specs/2026-11-17-marcus-frontend-v2-design.md`.

## Users

- **Natural-product researchers and students** who now and then add compounds from a paper to COCONUT. Often first-time visitors, arriving from the MARCUS paper or a talk; they try one paper.
- **Database curators** (COCONUT / NFDI4Chem) who process papers as their job, review hundreds of structures, and submit accepted ones to COCONUT in bulk.
- Both work on a desktop screen. The tool is desktop-only (minimum 1024 px); on a phone only the landing page needs to work.
- Script users exist (API keys) but have no web page.

## Product Purpose

MARCUS (Molecular Annotation and Recognition for Curating Unravelled Structures) turns a journal article (PDF) into checked chemical structures for COCONUT. It finds the structure drawings on each page (segmentation), turns each drawing into a structure (OCSR: image to SMILES/molfile), extracts the text, and lets a person check, fix, accept or reject each structure and submit the accepted ones to COCONUT. Success: a curator gets from PDF to submitted, trustworthy structures fast, and a first-time visitor understands and trusts the tool within a minute.

## Positioning

The whole pipeline in one open tool: segment, recognise with several engines (DECIMER by default, MolNexTR, MolScribe, DECIMER hand-drawn) and compare them, curate with a human in the loop, and submit to COCONUT. Open source (MIT), free, no login, runs on the group's own GPU, and sends no paper data to outside AI services.

## Operating Context

- Input: a scientific PDF (max 20 MB) or a single structure image.
- Work happens while the backend processes: results arrive one by one (live), with a queue position while waiting and a reason for every failed page.
- Review: a grid of structure cards with bulk accept/reject, a keyboard focus mode for one structure, and a "paper view" with the page image, boxes around each structure, and the extracted text.
- Tools used during review: the Ketcher structure editor, engine comparison (similarity, common substructure), PubChem and COCONUT lookups.
- Output: JSON, CSV and SDF export; COCONUT batch submission with the curator's own COCONUT login.
- No accounts: each browser owns its papers through a secret cookie; papers are deleted after 30 days.

## Capabilities and Constraints

- Terminology (keep): paper, page, segment, structure, engine, SMILES, molfile, curation (accepted / rejected), COCONUT.
- English only. Desktop only for the tool.
- No server data or user text may be injected as HTML; strict CSP (self, COCONUT, PubChem, Matomo).
- Analytics: the existing Matomo tracker (`https://matomo.nfdi4chem.de/`, site id 7).
- Annotation of the text by a local LLM comes later; the UI reserves a place for it.

## Brand Commitments

- Name: MARCUS. The logo stays: navy stacked papers with a green hexagonal magnifying lens (`../frontend/public/logo.png`, `logo.svg`).
- The wordmark font stays: Gmarket Sans Light (`../frontend/public/GmarketSansLight.otf`).
- A fresh visual style is built around the logo and wordmark; the v1 look (blue tokens, Inter) is not binding.
- Family: part of the DECIMER project (decimer.ai) and connected to COCONUT, Steinbeck group, Friedrich Schiller University Jena.

## Evidence on Hand

- Publication to cite: Rajan K., Weißenborn V., Lederer L., Zielesny A., Steinbeck C. "MARCUS: molecular annotation and recognition for curating unravelled structures." Digital Discovery 2025, 4(11), 3137–3148. https://doi.org/10.1039/d5dd00313j
- Example material for the landing page: our own synthetic fixture pages (`../judges/load/data`, synth_015, 15 structures), free of copyright.
- Source code: https://github.com/Kohulan/MARCUS (MIT).
- No user testimonials, usage numbers or benchmark claims are on hand. Do not invent any. Accuracy numbers may be shown only from the paper or from our own judge results, with their source.

## Product Principles

1. The structure is the hero: every screen puts the crop, the recognised structure and its state where the eye lands first.
2. Never hide a failure: a failed page, engine or submission is shown with its reason, never as "no structures".
3. Speed for experts, clarity for newcomers: keyboard paths and bulk actions for curators; one obvious next step for a first-time visitor.
4. Trust through openness: show where results come from (engine, version, page), and that data stays on our servers.

## Accessibility & Inclusion

WCAG 2.2 AA for landing and tool; full keyboard path through review; visible focus; light and dark mode both first-class; respect reduced motion.
