import {StrictMode} from 'react'
import {createRoot} from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import {ThemeProvider} from './components/ThemeProvider'
import {registriereServiceWorker} from './lib/pwa'

registriereServiceWorker()

createRoot(document.getElementById('root')!).render(
    <StrictMode>
        <ThemeProvider>
            <App/>
        </ThemeProvider>
    </StrictMode>,
)