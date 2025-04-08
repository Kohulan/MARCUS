# ChemStructX: Chemical Structure Extraction

A modern web application for extracting text and chemical structures from scientific papers.

![ChemStructX Logo](src/assets/logo.svg)

## Features

### 📄 PDF Processing
- Upload and visualize PDF documents
- Extract text content from papers
- Automatically segment chemical structure diagrams

### 🧠 Text Analysis
- Extract chemical compound entities from text
- Annotate and highlight chemical entities
- Download extracted text and annotations

### ⚗️ Chemical Structure Recognition
- Process segmented chemical images
- Convert images to SMILES notation
- Support for both DECIMER and MolNexTR engines
- Option for hand-drawn structures
- Export as molfiles with atom coordinates

## Tech Stack

- **Frontend**: Vue.js 3, Vuex 4, Sass
- **Backend**: FastAPI (Python)
- **Libraries**:
  - vue-pdf-embed: PDF rendering
  - vue-feather: Icon components
  - axios: API communication

## Getting Started

### Prerequisites

- Node.js (v14+)
- npm (v6+)
- Backend API running (see [Backend Setup](#backend-setup))

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/chem-structure-extractor.git
   cd chem-structure-extractor
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Create a `.env` file in the project root:
   ```
   VUE_APP_API_URL=http://localhost:9000
   ```

4. Start the development server:
   ```bash
   npm run serve
   ```

5. Access the application at `http://localhost:8080`

### Production Build

To create a production build:

```bash
npm run build
```

The build files will be generated in the `dist/` directory.

## Backend Setup

The application requires a backend API running at the URL specified in the `.env` file:

1. Ensure you have the NP data extraction service running. The API should be available at http://localhost:9000/latest/docs
2. The backend should implement the following API endpoints:
   - `/v1/docling_conversion/extract_text` - Extract text from PDFs
   - `/v1/decimer/extract_segments` - Extract chemical structure segments
   - `/v1/openai/extract_all` - Extract annotations
   - `/v1/ocsr/generate_smiles` - Generate SMILES from images
   - `/v1/ocsr/generate_molfile` - Generate molfiles from images
   - `/v1/ocsr/generate_both` - Generate both SMILES and molfiles

## Project Structure

```
chem-structure-extractor/
├── public/                 # Static files
├── src/
│   ├── assets/             # Images, fonts, and styles
│   ├── components/         # Vue components
│   │   ├── common/         # Shared components
│   │   ├── pdf-viewer/     # PDF handling components
│   │   ├── text-extraction/# Text extraction components
│   │   └── structure-extraction/ # Chemical structure components
│   ├── services/           # API service modules
│   ├── store/              # Vuex store modules
│   ├── utils/              # Utility functions
│   ├── views/              # Page components
│   ├── App.vue             # Root component
│   └── main.js             # Entry point
├── .env                    # Environment variables
└── package.json            # Project dependencies
```

## API Documentation

The backend API documentation is available at http://localhost:9000/latest/docs when the backend server is running.

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -am 'Add new feature'`
4. Push to the branch: `git push origin feature/my-feature`
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [Kohulan Rajan](https://github.com/Kohulan) - Project Lead
- [University of Jena](https://cheminf.uni-jena.de/) - Cheminformatics Research Group
- [DECIMER Project](https://decimer.ai) - Deep learning based Chemical Image Recognition

## Contact

For questions or support, please contact:
- **Email**: kohulan.rajan@uni-jena.de
- **Website**: https://cheminf.uni-jena.de/