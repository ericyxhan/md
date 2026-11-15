// Configurable endpoints. Override at build time via Vite env vars.
export const APP_URL = (import.meta.env.VITE_APP_URL as string) || 'https://server.tailfe0663.ts.net'
export const API_URL = (import.meta.env.VITE_API_URL as string) || APP_URL
export const CONTACT_EMAIL = (import.meta.env.VITE_CONTACT_EMAIL as string) || 'hello@lattice.md'
export const GITHUB_URL = (import.meta.env.VITE_GITHUB_URL as string) || ''
