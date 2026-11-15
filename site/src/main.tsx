import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

// Restore path from GitHub Pages SPA fallback (?p=...).
;(function () {
  const params = new URLSearchParams(window.location.search)
  const p = params.get('p')
  if (p) {
    const decoded = decodeURIComponent(p)
    params.delete('p')
    const qs = params.toString()
    window.history.replaceState(null, '', decoded + (qs ? '?' + qs : '') + window.location.hash)
  }
})()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
