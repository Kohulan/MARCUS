# MARCUS Frontend

Vue.js 3 application for molecular structure extraction and recognition.

## Overview

The frontend provides an interactive web interface for:
- **PDF Processing**: Upload and segment scientific PDFs
- **Structure Recognition**: Extract chemical structures using multiple OCSR engines
- **Molecular Visualization**: Generate and view molecular depictions
- **Text Analysis**: AI-powered extraction of structured chemical data
- **Session Management**: Real-time user queue and concurrency control

## Architecture

- **Framework**: Vue.js 3 with Composition API
- **State Management**: Vuex for application state
- **HTTP Client**: Axios for API communication
- **Styling**: SCSS with custom variables
- **PDF Handling**: PDF.js for document processing
- **Real-time**: WebSocket connections for session updates

## Key Components

```
src/
├── components/
│   ├── common/           # Shared UI components
│   ├── pdf-viewer/       # PDF display and interaction
│   ├── structure-extraction/  # OCSR interface
│   ├── text-extraction/  # AI text analysis
│   └── SessionManager.vue     # User session control
├── services/             # API communication layers
├── store/               # Vuex state management
└── views/               # Main application pages
```

## Development Setup

```bash
# Install dependencies
npm install

# Start development server
npm run serve

# Build for production
npm run build

# Lint code
npm run lint
```

## Environment Variables

Create a `.env.local` file:
```env
VUE_APP_BACKEND_URL=http://localhost:9000
VUE_APP_API_URL=http://localhost:9000/latest
```

## API Integration

The frontend communicates with the backend through RESTful APIs:
- **Session Management**: WebSocket + REST for user queuing
- **File Upload**: Multipart form data for PDFs and images
- **Real-time Updates**: WebSocket for progress and status
- **Error Handling**: Centralized error management

## Requirements

- Node.js ≥18.0.0
- npm ≥8.0.0
- Modern browser with ES2020 support
