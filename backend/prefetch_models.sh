#!/bin/bash
# Script to prefetch Docling models for deployment

# Create models directory if it doesn't exist
mkdir -p ./models/docling

# Prefetch models using docling-tools
echo "Prefetching Docling models to ./models/docling..."
pip install docling
docling-tools models download --directory ./models/docling

echo "Docling models prefetched successfully. You can now build your Docker image."