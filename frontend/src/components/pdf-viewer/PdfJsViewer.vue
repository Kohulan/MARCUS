<template>
    <div class="pdfjs-viewer">
        <div class="pdfjs-toolbar">
            <button class="pdfjs-btn" @click="scrollToPage(pageNum - 1)" :disabled="pageNum <= 1" title="Previous Page">
                <vue-feather type="chevron-left" size="18" />
            </button>
            <span class="pdfjs-page-info">
                Page <strong>{{ pageNum }}</strong> / {{ numPages }}
            </span>
            <button class="pdfjs-btn" @click="scrollToPage(pageNum + 1)" :disabled="pageNum >= numPages" title="Next Page">
                <vue-feather type="chevron-right" size="18" />
            </button>
            <div class="pdfjs-toolbar-divider"></div>
            <button class="pdfjs-btn" @click="zoomOut" :disabled="scale <= minScale" title="Zoom Out">
                <vue-feather type="zoom-out" size="18" />
            </button>
            <span class="pdfjs-zoom">{{ (scale * 100).toFixed(0) }}%</span>
            <button class="pdfjs-btn" @click="zoomIn" :disabled="scale >= maxScale" title="Zoom In">
                <vue-feather type="zoom-in" size="18" />
            </button>
            <div class="pdfjs-toolbar-spacer"></div>
            <button class="pdfjs-btn" @click="printPdf" :disabled="isLoading" title="Print PDF">
                <vue-feather type="printer" size="18" />
            </button>
            <button class="pdfjs-btn" @click="downloadPdf" :disabled="isLoading" title="Download PDF">
                <vue-feather type="download" size="18" />
            </button>
            <div class="pdfjs-menu-wrapper">
                <button class="pdfjs-btn pdfjs-hamburger" @click="toggleMenu" :aria-expanded="showMenu"
                    title="Document Properties">
                    <vue-feather type="menu" size="18" />
                </button>
                <div v-if="showMenu" class="pdfjs-menu">
                    <div class="pdfjs-menu-title">Document Properties</div>
                    <div class="pdfjs-menu-item"><strong>Title:</strong> {{ docTitle || 'N/A' }}</div>
                    <div class="pdfjs-menu-item"><strong>Pages:</strong> {{ numPages }}</div>
                    <div class="pdfjs-menu-item"><strong>File Size:</strong> {{ fileSizeDisplay }}</div>
                </div>
            </div>
        </div>
        <div v-if="isLoading" class="loading">Loading PDF...</div>
        <div ref="pdfContainer" class="pdfjs-container" @scroll="handleContainerScroll">
            <!-- Pages will be rendered here -->
        </div>
        <div v-if="error" class="error">{{ error }}</div>
    </div>
</template>

<script>
import { ref, onMounted, watch, nextTick, computed } from 'vue';
import * as pdfjsLib from 'pdfjs-dist/webpack';
import 'pdfjs-dist/web/pdf_viewer.css';
import VueFeather from 'vue-feather';

export default {
    name: 'PdfJsViewer',
    components: { VueFeather },
    props: {
        pdfUrl: {
            type: String,
            required: true
        },
        pdfFile: {
            type: Object,
            required: false
        }
    },
    setup(props) {
        const pdfContainer = ref(null);
        const isLoading = ref(true);
        const error = ref(null);
        const pageNum = ref(1);
        const numPages = ref(1);
        const scale = ref(1.0); // Default zoom 100%
        const minScale = 0.5;
        const maxScale = 3.0;
        const showMenu = ref(false);
        const docTitle = ref('');
        const fileSize = ref(null);
        const pagePositions = ref([]);
        let pdfDocument = null;

        const fileSizeDisplay = computed(() => {
            // Use pdfFile prop if available
            if (props.pdfFile && props.pdfFile.size) {
                const bytes = props.pdfFile.size;
                if (bytes < 1024) return bytes + ' bytes';
                if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
                return (bytes / 1048576).toFixed(1) + ' MB';
            }
            if (fileSize.value && !isNaN(fileSize.value)) {
                const bytes = fileSize.value;
                if (bytes < 1024) return bytes + ' bytes';
                if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
                return (bytes / 1048576).toFixed(1) + ' MB';
            }
            // Try to get file size from the File API if the URL is a local blob
            if (props.pdfUrl.startsWith('blob:')) {
                try {
                    const allBlobs = Object.values(window.performance.getEntriesByType('resource'));
                    const blobEntry = allBlobs.find(e => e.name === props.pdfUrl);
                    if (blobEntry && blobEntry.encodedBodySize) {
                        const bytes = blobEntry.encodedBodySize;
                        if (bytes < 1024) return bytes + ' bytes';
                        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
                        return (bytes / 1048576).toFixed(1) + ' MB';
                    }
                } catch (e) { /* ignore */ }
            }
            return 'Unknown';
        });

        // Render all pages in continuous mode
        const renderAllPages = async () => {
            isLoading.value = true;
            error.value = null;
            if (!pdfDocument) return;
            
            try {
                if (pdfContainer.value) pdfContainer.value.innerHTML = '';
                pagePositions.value = [];
                let currentPosition = 0;
                
                // Loop through all pages and render them
                for (let i = 1; i <= numPages.value; i++) {
                    const page = await pdfDocument.getPage(i);
                    const viewport = page.getViewport({ scale: scale.value });
                    
                    // Create a wrapper div for each page with page number
                    const pageDiv = document.createElement('div');
                    pageDiv.className = 'pdfjs-page-wrapper';
                    pageDiv.setAttribute('data-page-number', i);
                    
                    // Page number indicator
                    const pageNumberDiv = document.createElement('div');
                    pageNumberDiv.className = 'pdfjs-page-number';
                    pageNumberDiv.textContent = i;
                    pageDiv.appendChild(pageNumberDiv);

                    // Create canvas for the page
                    const canvas = document.createElement('canvas');
                    canvas.height = viewport.height;
                    canvas.width = viewport.width;
                    const context = canvas.getContext('2d');
                    
                    // Add to page wrapper
                    pageDiv.appendChild(canvas);
                    
                    // Add page separator (except for the first page)
                    if (i > 1) {
                        const separator = document.createElement('div');
                        separator.className = 'pdfjs-page-separator';
                        pdfContainer.value.appendChild(separator);
                        
                        // Add separator height to current position
                        currentPosition += 40; // Height of separator
                    }
                    
                    // Add page div to container
                    pdfContainer.value.appendChild(pageDiv);
                    
                    // Store position info for this page
                    pagePositions.value.push({
                        pageNumber: i,
                        top: currentPosition,
                        bottom: currentPosition + viewport.height
                    });
                    
                    // Update current position for next page
                    currentPosition += viewport.height;
                    
                    // Render the page content
                    await page.render({ canvasContext: context, viewport }).promise;
                    
                    // Render annotations (except links)
                    const annotations = await page.getAnnotations();
                    annotations.forEach(annotation => {
                        if (annotation.subtype === 'Link') return;
                        // Additional annotation rendering code could go here
                    });
                }
                
                isLoading.value = false;
            } catch (e) {
                console.error('Render error:', e);
                error.value = 'Failed to render pages.';
                isLoading.value = false;
            }
        };

        // Handle container scrolling to update current page
        const handleContainerScroll = () => {
            if (!pdfContainer.value || pagePositions.value.length === 0) return;
            
            const containerTop = pdfContainer.value.scrollTop;
            const containerHeight = pdfContainer.value.clientHeight;
            const containerCenter = containerTop + (containerHeight / 2);
            
            // Find which page is most visible
            let mostVisiblePage = 1;
            let maxVisibleArea = 0;
            
            pagePositions.value.forEach(position => {
                const pageTop = position.top;
                const pageBottom = position.bottom;
                
                // Calculate visible area of this page
                const visibleTop = Math.max(pageTop, containerTop);
                const visibleBottom = Math.min(pageBottom, containerTop + containerHeight);
                
                if (visibleBottom > visibleTop) {
                    const visibleArea = visibleBottom - visibleTop;
                    if (visibleArea > maxVisibleArea) {
                        maxVisibleArea = visibleArea;
                        mostVisiblePage = position.pageNumber;
                    }
                }
                
                // Alternative approach: which page contains the center of the viewport
                if (containerCenter >= pageTop && containerCenter <= pageBottom) {
                    mostVisiblePage = position.pageNumber;
                }
            });
            
            pageNum.value = mostVisiblePage;
        };

        // Scroll to specific page
        const scrollToPage = (page) => {
            if (page < 1 || page > numPages.value || !pdfContainer.value) return;
            
            const targetPosition = pagePositions.value[page - 1]?.top || 0;
            pdfContainer.value.scrollTo({
                top: targetPosition,
                behavior: 'smooth'
            });
            
            pageNum.value = page;
        };

        // Load document and render all pages
        const loadDocument = async () => {
            isLoading.value = true;
            error.value = null;
            try {
                if (pdfContainer.value) pdfContainer.value.innerHTML = '';
                pdfjsLib.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.js`;
                pdfDocument = await pdfjsLib.getDocument(props.pdfUrl).promise;
                numPages.value = pdfDocument.numPages;
                pageNum.value = 1;
                
                // Get document metadata
                const meta = await pdfDocument.getMetadata();
                docTitle.value = meta.info?.Title || '';
                
                // Try to get file size from HEAD request
                fetch(props.pdfUrl, { method: 'HEAD' })
                    .then(r => {
                        const size = parseInt(r.headers.get('content-length'));
                        if (!isNaN(size)) fileSize.value = size;
                    })
                    .catch(() => fileSize.value = null);
                
                // Render all pages in continuous mode
                await renderAllPages();
            } catch (e) {
                console.error('Load error:', e);
                error.value = 'Failed to load PDF.';
                isLoading.value = false;
            }
        };

        const zoomIn = async () => {
            if (scale.value < maxScale) {
                scale.value += 0.1;
                await renderAllPages();
            }
        };
        
        const zoomOut = async () => {
            if (scale.value > minScale) {
                scale.value -= 0.1;
                await renderAllPages();
            }
        };
        
        const printPdf = () => {
            window.open(props.pdfUrl, '_blank').print();
        };
        
        const downloadPdf = () => {
            const link = document.createElement('a');
            link.href = props.pdfUrl;
            link.download = docTitle.value ? docTitle.value + '.pdf' : 'document.pdf';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        };
        
        const toggleMenu = () => {
            showMenu.value = !showMenu.value;
        };

        onMounted(() => {
            loadDocument();
        });
        
        watch(() => props.pdfUrl, async () => {
            await nextTick();
            await loadDocument();
        });

        return {
            pdfContainer,
            isLoading,
            error,
            pageNum,
            numPages,
            scale,
            minScale,
            maxScale,
            scrollToPage,
            zoomIn,
            zoomOut,
            printPdf,
            downloadPdf,
            showMenu,
            toggleMenu,
            docTitle,
            fileSizeDisplay,
            handleContainerScroll
        };
    }
};
</script>

<style scoped>
.pdfjs-viewer {
    width: 100%;
    height: 100%;
    position: relative;
}

.pdfjs-toolbar {
    display: flex;
    align-items: center;
    gap: 1.2rem;
    padding: 0.75rem 1.5rem;
    background: var(--color-card-bg, #f8fafc);
    border-bottom: 1px solid var(--color-border, #e0e0e0);
    box-shadow: 0 2px 8px rgba(80, 120, 200, 0.04);
    border-radius: 16px 16px 0 0;
    font-family: inherit;
    position: relative;
    z-index: 2;
    transition: background 0.2s, border-color 0.2s;
}

.pdfjs-btn {
    background: var(--color-primary, #6366f1);
    color: var(--color-btn-text, #fff);
    border: none;
    border-radius: 10px;
    padding: 0.45rem 1.1rem;
    font-size: 1.1rem;
    font-weight: 600;
    box-shadow: 0 2px 8px rgba(80, 120, 200, 0.08);
    cursor: pointer;
    transition: background 0.2s, transform 0.1s, box-shadow 0.2s, color 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    outline: none;
}

.pdfjs-btn:disabled {
    background: var(--color-btn-disabled, #e0e7ef);
    color: var(--color-btn-disabled-text, #b0b8c9);
    cursor: not-allowed;
    box-shadow: none;
}

.pdfjs-btn:not(:disabled):hover {
    background: var(--color-primary-dark, #4f46e5);
    color: var(--color-btn-text, #fff);
    transform: translateY(-2px) scale(1.05);
    box-shadow: 0 4px 16px rgba(80, 120, 200, 0.12);
}

.pdfjs-toolbar-divider {
    width: 2px;
    height: 28px;
    background: var(--color-border, #e0e7ef);
    border-radius: 2px;
    margin: 0 1.2rem;
}

.pdfjs-toolbar-spacer {
    flex: 1;
}

.pdfjs-menu-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    margin-left: auto;
}

.pdfjs-hamburger {
    padding: 0.45rem 0.7rem;
    font-size: 1.2rem;
    background: var(--color-secondary, #64748b);
    color: var(--color-btn-text, #fff);
    border-radius: 10px;
    margin-left: 0.5rem;
}

.pdfjs-menu {
    position: absolute;
    top: 120%;
    right: 0;
    min-width: 220px;
    background: var(--color-card-bg, #fff);
    border: 1px solid var(--color-border, #e0e7ef);
    border-radius: 8px;
    box-shadow: 0 4px 24px rgba(80, 120, 200, 0.13);
    padding: 1rem 1.2rem;
    z-index: 10;
    animation: fadeIn 0.2s;
    color: var(--color-text, #334155);
    transition: background 0.2s, border-color 0.2s, color 0.2s;
}

.pdfjs-menu-title {
    font-weight: 700;
    color: var(--color-heading, #334155);
    margin-bottom: 0.7rem;
    font-size: 1.08rem;
}

.pdfjs-menu-item {
    font-size: 0.98rem;
    color: var(--color-text, #475569);
    margin-bottom: 0.4rem;
}

.pdfjs-menu-item:last-child {
    margin-bottom: 0;
}

@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(10px);
    }

    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.pdfjs-container {
    width: 100%;
    height: calc(100% - 48px);
    overflow: auto;
    background: var(--color-bg, #f8f8f8);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    transition: background 0.2s;
    padding: 1rem 0;
}

.loading {
    text-align: center;
    padding: 1rem;
    color: var(--color-text, #334155);
}

.error {
    color: var(--color-error, red);
    text-align: center;
    padding: 1rem;
}

canvas {
    display: block;
    margin: 0;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

/* Page wrapper styles */
.pdfjs-page-wrapper {
    position: relative;
    margin: 0 auto;
    padding: 0;
    display: flex;
    justify-content: center;
}

/* Page separator styles */
.pdfjs-page-separator {
    width: 100%;
    height: 40px;
    background: linear-gradient(to bottom, rgba(0,0,0,0.03), rgba(0,0,0,0.07), rgba(0,0,0,0.03));
    position: relative;
    margin: 0 auto;
    display: flex;
    align-items: center;
    justify-content: center;
    border-top: 1px dashed rgba(0,0,0,0.1);
    border-bottom: 1px dashed rgba(0,0,0,0.1);
}

.pdfjs-page-separator::after {
    content: '';
    position: absolute;
    height: 1px;
    width: 80%;
    background: rgba(0,0,0,0.1);
    top: 50%;
    left: 10%;
}

/* Page number styles */
.pdfjs-page-number {
    position: absolute;
    top: 5px;
    right: 5px;
    background: rgba(0,0,0,0.5);
    color: white;
    border-radius: 12px;
    padding: 3px 8px;
    font-size: 12px;
    font-weight: bold;
    opacity: 0.7;
    z-index: 1;
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
    .pdfjs-toolbar {
        background: var(--color-card-bg, #23272f);
        border-bottom: 1px solid var(--color-border, #23272f);
    }

    .pdfjs-btn {
        background: var(--color-primary, #6366f1);
        color: var(--color-btn-text, #fff);
    }

    .pdfjs-btn:not(:disabled):hover {
        background: var(--color-primary-dark, #4338ca);
        color: var(--color-btn-text, #fff);
    }

    .pdfjs-hamburger {
        background: var(--color-secondary, #334155);
        color: var(--color-btn-text, #fff);
    }

    .pdfjs-menu {
        background: var(--color-card-bg, #23272f);
        border: 1px solid var(--color-border, #334155);
        color: var(--color-text, #e0e7ef);
    }

    .pdfjs-menu-title {
        color: var(--color-heading, #e0e7ef);
    }

    .pdfjs-menu-item {
        color: var(--color-text, #cbd5e1);
    }

    .pdfjs-container {
        background: var(--color-bg, #181a20);
    }

    .loading {
        color: var(--color-text, #e0e7ef);
    }

    .error {
        color: var(--color-error, #ff6b6b);
    }

    .pdfjs-page-separator {
        background: linear-gradient(to bottom, rgba(255,255,255,0.03), rgba(255,255,255,0.07), rgba(255,255,255,0.03));
        border-top: 1px dashed rgba(255,255,255,0.1);
        border-bottom: 1px dashed rgba(255,255,255,0.1);
    }

    .pdfjs-page-separator::after {
        background: rgba(255,255,255,0.1);
    }
}
</style>