/**
 * API client for interacting with FastAPI backend endpoints.
 */

const BASE_URL = ''; // Relative path leverages Vite / Nginx reverse proxy

/**
 * Health check endpoint
 */
export async function checkHealth() {
  const res = await fetch(`${BASE_URL}/api/health`);
  if (!res.ok) {
    throw new Error(`Health check failed with status ${res.status}`);
  }
  return res.json();
}

/**
 * Upload a trade document and execute LangGraph pipeline
 * @param {File} file
 * @param {string} docType
 */
export async function uploadDocument(file, docType = 'commercial_invoice') {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('doc_type', docType);

  const res = await fetch(`${BASE_URL}/api/documents/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || `Upload failed with status ${res.status}`);
  }

  return res.json();
}

/**
 * Retrieve unified document bundle (document, extraction, validation, decision, runs)
 * @param {string} documentId
 */
export async function getDocument(documentId) {
  const res = await fetch(`${BASE_URL}/api/documents/${documentId}`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || `Failed to fetch document: ${res.status}`);
  }
  return res.json();
}

/**
 * List uploaded documents
 * @param {number} limit
 * @param {number} offset
 */
export async function listDocuments(limit = 50, offset = 0) {
  const res = await fetch(`${BASE_URL}/api/documents?limit=${limit}&offset=${offset}`);
  if (!res.ok) {
    throw new Error(`Failed to list documents: ${res.status}`);
  }
  return res.json();
}

/**
 * List execution runs and aggregate telemetry metrics
 * @param {number} limit
 * @param {number} offset
 */
export async function getRunsTelemetry(limit = 50, offset = 0) {
  const res = await fetch(`${BASE_URL}/api/runs?limit=${limit}&offset=${offset}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch runs telemetry: ${res.status}`);
  }
  return res.json();
}

/**
 * Execute natural language query via Text-to-SQL
 * @param {string} query
 */
export async function executeNlQuery(query) {
  const res = await fetch(`${BASE_URL}/api/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || `Query failed with status ${res.status}`);
  }

  return res.json();
}
