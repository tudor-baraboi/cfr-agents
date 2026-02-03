import { Component, createSignal, For, Show, onMount } from 'solid-js';
import { AGENT } from './config';

const API_URL = import.meta.env.VITE_API_URL || '';
const MAX_DOCUMENTS = 20;
const MAX_FILE_SIZE_MB = 50;

interface Document {
  id: string;
  title: string;
  filename: string;
  uploaded_at: string;
  page_count: number;
  chunk_count: number;
}

interface MyDocumentsPanelProps {
  token: string;
  fingerprint: string;
}

type UploadState = 'idle' | 'uploading' | 'processing' | 'success' | 'error';

const MyDocumentsPanel: Component<MyDocumentsPanelProps> = (props) => {
  const [isOpen, setIsOpen] = createSignal(false);
  const [documents, setDocuments] = createSignal<Document[]>([]);
  const [isLoading, setIsLoading] = createSignal(false);
  const [uploadState, setUploadState] = createSignal<UploadState>('idle');
  const [uploadError, setUploadError] = createSignal<string | null>(null);
  const [uploadingFile, setUploadingFile] = createSignal<string | null>(null);
  const [uploadProgress, setUploadProgress] = createSignal<{ loaded: number; total: number } | null>(null);
  const [deleteConfirm, setDeleteConfirm] = createSignal<string | null>(null);
  const [isDeleting, setIsDeleting] = createSignal<string | null>(null);
  const [isDragOver, setIsDragOver] = createSignal(false);

  let fileInputRef: HTMLInputElement | undefined;

  const fetchDocuments = async () => {
    setIsLoading(true);
    try {
      const url = `${API_URL}/documents?fingerprint=${encodeURIComponent(props.fingerprint)}&index=${AGENT}-agent`;
      console.log('Fetching documents from:', url);
      console.log('Fingerprint:', props.fingerprint);
      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${props.token}` },
      });
      if (response.ok) {
        const data = await response.json();
        console.log('Fetched documents:', data);
        setDocuments(data.documents || []);
      } else {
        console.error('Failed to fetch documents:', response.status);
      }
    } catch (error) {
      console.error('Error fetching documents:', error);
    } finally {
      setIsLoading(false);
    }
  };

  onMount(() => { fetchDocuments(); });

  const handleOpen = () => { setIsOpen(true); fetchDocuments(); };
  const handleClose = () => { setIsOpen(false); setUploadState('idle'); setUploadError(null); };

  const handleFileSelect = (e: Event) => {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) uploadFile(file);
    input.value = '';
  };

  const handleDragOver = (e: DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragOver(true); };
  const handleDragLeave = (e: DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragOver(false); };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    const file = e.dataTransfer?.files?.[0];
    if (file && file.type === 'application/pdf') {
      uploadFile(file);
    } else if (file) {
      setUploadState('error');
      setUploadError('Please upload a PDF file');
    }
  };

  const uploadFile = async (file: File) => {
    console.log('uploadFile called:', file.name, 'size:', file.size);
    if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      setUploadState('error');
      setUploadError(`File too large. Maximum size is ${MAX_FILE_SIZE_MB}MB.`);
      return;
    }
    if (documents().length >= MAX_DOCUMENTS) {
      setUploadState('error');
      setUploadError(`Maximum ${MAX_DOCUMENTS} documents allowed. Delete one first.`);
      return;
    }

    setUploadState('uploading');
    setUploadingFile(file.name);
    setUploadError(null);
    setUploadProgress({ loaded: 0, total: file.size });

    const formData = new FormData();
    formData.append('file', file);
    formData.append('fingerprint', props.fingerprint);
    formData.append('index', `${AGENT}-agent`);

    console.log('Uploading to:', `${API_URL}/documents`);
    console.log('With fingerprint:', props.fingerprint);

    // Use XMLHttpRequest for upload progress tracking
    const xhr = new XMLHttpRequest();
    
    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) {
        setUploadProgress({ loaded: event.loaded, total: event.total });
      }
    });

    xhr.addEventListener('load', async () => {
      console.log('Upload response status:', xhr.status);
      try {
        const responseData = JSON.parse(xhr.responseText);
        console.log('Upload response data:', responseData);

        if (xhr.status >= 200 && xhr.status < 300) {
          setUploadState('processing');
          // Wait a bit for Azure Search to index
          console.log('Upload successful, waiting for index...');
          await new Promise(resolve => setTimeout(resolve, 2000));
          setUploadState('success');
          await fetchDocuments();
          setTimeout(() => setUploadState('idle'), 2000);
        } else {
          setUploadState('error');
          setUploadError(responseData.detail || 'Upload failed');
        }
      } catch (e) {
        setUploadState('error');
        setUploadError('Invalid response from server');
      } finally {
        setUploadingFile(null);
        setUploadProgress(null);
      }
    });

    xhr.addEventListener('error', () => {
      console.error('Upload error');
      setUploadState('error');
      setUploadError('Network error. Please try again.');
      setUploadingFile(null);
      setUploadProgress(null);
    });

    xhr.open('POST', `${API_URL}/documents`);
    xhr.setRequestHeader('Authorization', `Bearer ${props.token}`);
    xhr.send(formData);
  };

  const handleDelete = async (docId: string) => {
    setIsDeleting(docId);
    try {
      const url = `${API_URL}/documents/${encodeURIComponent(docId)}?fingerprint=${encodeURIComponent(props.fingerprint)}&index=${AGENT}-agent`;
      const response = await fetch(url, { 
        method: 'DELETE', 
        headers: { 'Authorization': `Bearer ${props.token}` } 
      });
      if (response.ok) {
        setDocuments(docs => docs.filter(d => d.id !== docId));
      } else {
        const error = await response.json();
        console.error('Delete failed:', error);
      }
    } catch (error) {
      console.error('Error deleting document:', error);
    } finally {
      setIsDeleting(null);
      setDeleteConfirm(null);
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    } catch { return dateStr; }
  };

  return (
    <>
      {/* FAB Button */}
      <button 
        class={`my-docs-fab ${documents().length > 0 ? 'has-docs' : ''}`}
        onClick={handleOpen}
        title="My Documents"
      >
        <span class="fab-icon">📄</span>
        <Show when={documents().length > 0}>
          <span class="fab-badge">{documents().length}</span>
        </Show>
      </button>

      {/* Drawer/Modal */}
      <Show when={isOpen()}>
        <div class="my-docs-overlay" onClick={handleClose} />
        <div 
          class={`my-docs-drawer ${isDragOver() ? 'drag-over' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {/* Header */}
          <div class="my-docs-header">
            <h2>My Documents</h2>
            <span class="my-docs-count">{documents().length} / {MAX_DOCUMENTS}</span>
            <button class="my-docs-close" onClick={handleClose}>×</button>
          </div>

          {/* Content */}
          <div class="my-docs-content">
            {/* Upload Area */}
            <div class="my-docs-upload">
              <Show
                when={uploadState() === 'idle' || uploadState() === 'error'}
                fallback={
                  <div class="my-docs-upload-status">
                    <Show when={uploadState() === 'uploading'}>
                      <span class="upload-spinner-ring"></span>
                      <span>
                        <Show 
                          when={uploadProgress() && uploadProgress()!.loaded < uploadProgress()!.total}
                          fallback={<>Processing {uploadingFile()} (OCR + indexing)... This may take several minutes for scanned PDFs.</>}
                        >
                          {(() => {
                            const prog = uploadProgress()!;
                            const formatBytes = (bytes: number) => {
                              if (bytes < 1024) return `${bytes} B`;
                              if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
                              return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
                            };
                            return `Uploading ${uploadingFile()} (${formatBytes(prog.loaded)} / ${formatBytes(prog.total)})`;
                          })()}
                        </Show>
                      </span>
                    </Show>
                    <Show when={uploadState() === 'processing'}>
                      <span class="upload-spinner">⚙️</span>
                      <span>Processing & indexing...</span>
                    </Show>
                    <Show when={uploadState() === 'success'}>
                      <span class="upload-success">✓</span>
                      <span>Document added!</span>
                    </Show>
                  </div>
                }
              >
                <div class="my-docs-upload-inner">
                  <div class="upload-icon-large">📤</div>
                  <p>Drag & drop a PDF here</p>
                  <p class="upload-or">or</p>
                  <button 
                    class="my-docs-upload-btn"
                    onClick={() => fileInputRef?.click()}
                    disabled={documents().length >= MAX_DOCUMENTS}
                  >
                    Browse Files
                  </button>
                  <p class="upload-hint">Max {MAX_FILE_SIZE_MB}MB • Text-based PDFs only</p>
                </div>
              </Show>
              <Show when={uploadState() === 'error' && uploadError()}>
                <div class="upload-error">{uploadError()}</div>
              </Show>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              style="display: none"
              onChange={handleFileSelect}
            />

            {/* Documents List */}
            <div class="my-docs-list-section">
              <h3>Your Documents</h3>
              <Show when={isLoading()}>
                <div class="my-docs-loading">Loading...</div>
              </Show>
              <Show when={!isLoading() && documents().length === 0}>
                <div class="my-docs-empty">
                  <p>No documents yet</p>
                  <p class="empty-hint">Upload PDFs to include them in search results</p>
                </div>
              </Show>
              <Show when={!isLoading() && documents().length > 0}>
                <ul class="my-docs-list">
                  <For each={documents()}>
                    {(doc) => (
                      <li class={`my-docs-item ${deleteConfirm() === doc.id ? 'confirming' : ''}`}>
                        <Show when={deleteConfirm() !== doc.id}>
                          <div class="my-docs-item-icon">📄</div>
                          <div class="my-docs-item-info">
                            <span class="my-docs-item-name" title={doc.filename}>{doc.filename}</span>
                            <span class="my-docs-item-meta">{doc.page_count} pages • {formatDate(doc.uploaded_at)}</span>
                          </div>
                          <button
                            class="my-docs-item-delete"
                            onClick={() => setDeleteConfirm(doc.id)}
                            title="Delete"
                          >
                            🗑️
                          </button>
                        </Show>
                        <Show when={deleteConfirm() === doc.id}>
                          <span class="my-docs-confirm-text">Delete this document?</span>
                          <div class="my-docs-confirm-buttons">
                            <button 
                              class="my-docs-confirm-cancel" 
                              onClick={() => setDeleteConfirm(null)}
                            >
                              Cancel
                            </button>
                            <button 
                              class="my-docs-confirm-delete" 
                              onClick={() => handleDelete(doc.id)}
                              disabled={isDeleting() === doc.id}
                            >
                              {isDeleting() === doc.id ? 'Deleting...' : 'Delete'}
                            </button>
                          </div>
                        </Show>
                      </li>
                    )}
                  </For>
                </ul>
              </Show>
            </div>
          </div>
        </div>
      </Show>
    </>
  );
};

export default MyDocumentsPanel;
