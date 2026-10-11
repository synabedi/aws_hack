import React from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/outfit'
import '@fontsource/anek-devanagari/400.css'
import '@fontsource/anek-devanagari/600.css'
import 'leaflet/dist/leaflet.css'
import './styles.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(<App />)
