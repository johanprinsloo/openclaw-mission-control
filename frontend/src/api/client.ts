import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

// CSRF token handling
function getCsrfToken(): string | null {
  const match = document.cookie.match(/mc_csrf=([^;]+)/)
  return match ? match[1] : null
}

// Add CSRF token to non-GET requests
api.interceptors.request.use((config) => {
  if (config.method && config.method.toLowerCase() !== 'get') {
    const csrfToken = getCsrfToken()
    if (csrfToken) {
      config.headers['X-CSRF-Token'] = csrfToken
    }
  }
  return config
})

export default api
