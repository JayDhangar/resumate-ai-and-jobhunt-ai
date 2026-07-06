// Thin typed-ish client for the Resume Builder backend.
const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch { /* not json */ }
    throw new Error(detail)
  }
  const type = res.headers.get('content-type') || ''
  return type.includes('application/json') ? res.json() : res
}

export const api = {
  health: () => request('/health'),

  // resumes
  uploadResume: (file, onProgress) => uploadWithProgress('/resumes/upload', file, onProgress),
  createResume: (title) => request('/resumes', { method: 'POST', body: JSON.stringify({ title }) }),
  listResumes: () => request('/resumes'),
  getResume: (id) => request(`/resumes/${id}`),
  updateResume: (id, data, saveVersion = false, note = '') =>
    request(`/resumes/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ data, save_version: saveVersion, change_note: note }),
    }),
  deleteResume: (id) => request(`/resumes/${id}`, { method: 'DELETE' }),
  editResume: (id, instructions) =>
    request(`/resumes/${id}/edit`, { method: 'POST', body: JSON.stringify({ instructions }) }),
  selectTemplate: (id, templateId) =>
    request(`/resumes/${id}/select-template`, {
      method: 'POST',
      body: JSON.stringify({ template_id: templateId }),
    }),
  versions: (id) => request(`/resumes/${id}/versions`),
  restoreVersion: (id, version) =>
    request(`/resumes/${id}/versions/${version}/restore`, { method: 'POST' }),
  scores: (id, jobDescription = '') =>
    request(`/resumes/${id}/scores?job_description=${encodeURIComponent(jobDescription)}`),
  generate: (id, payload) =>
    request(`/resumes/${id}/generate`, { method: 'POST', body: JSON.stringify(payload) }),
  previewUrl: (id, templateId = '', instructions = '') =>
    `${BASE}/resumes/${id}/preview?template_id=${encodeURIComponent(templateId)}&template_instructions=${encodeURIComponent(instructions)}`,
  downloadUrl: (id, fmt) => `${BASE}/resumes/${id}/download/${fmt}`,

  // templates
  listTemplates: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/templates${qs ? `?${qs}` : ''}`)
  },
  refreshTemplates: () => request('/templates/refresh', { method: 'POST' }),
  uploadTemplate: (file, name, onProgress) =>
    uploadWithProgress('/templates/upload', file, onProgress, { name }),
  templatePreviewUrl: (id) => `${BASE}/templates/${id}/preview`,
  templateSampleUrl: (id) => `${BASE}/templates/${id}/render-sample`,
  deleteTemplate: (id) => request(`/templates/${id}`, { method: 'DELETE' }),
  toggleSaveTemplate: (id) => request(`/templates/${id}/save`, { method: 'POST' }),
}

function uploadWithProgress(path, file, onProgress, extraFields = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const form = new FormData()
    form.append('file', file)
    for (const [key, value] of Object.entries(extraFields)) form.append(key, value)
    xhr.open('POST', `${BASE}${path}`)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      try {
        const body = JSON.parse(xhr.responseText)
        if (xhr.status >= 200 && xhr.status < 300) resolve(body)
        else reject(new Error(body.detail || `Upload failed (${xhr.status})`))
      } catch {
        reject(new Error(`Upload failed (${xhr.status})`))
      }
    }
    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.send(form)
  })
}
