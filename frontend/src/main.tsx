import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/noto-sans-kr/index.css'

import App from './App'
import './styles/tokens.css'
import './styles/globals.css'
import './styles/components.css'
import './styles/live-class.css'
import './styles/public-auth.css'
import './styles/home-account.css'
import './styles/course-workspace.css'
import './styles/class-ready.css'
import './styles/processing-class.css'

const rootElement = document.getElementById('root')

if (!rootElement) {
  throw new Error('Root element was not found')
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
