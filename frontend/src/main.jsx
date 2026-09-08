import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import EntryPage from './DataEntry'
import './index.css'

const pathname = window.location.pathname || '/'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {pathname === '/signals' ? <App /> : <EntryPage onDone={() => { window.location.pathname = '/signals' }} />}
  </React.StrictMode>
)
