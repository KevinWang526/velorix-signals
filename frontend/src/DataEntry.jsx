import React, { useState } from 'react'

export default function EntryPage({ onDone }) {
  const [symbol, setSymbol] = useState('')
  const [buyPrice, setBuyPrice] = useState('')
  const [qty, setQty] = useState('')
  const [externalUrl, setExternalUrl] = useState('')
  const [externalFiles, setExternalFiles] = useState([])
  const [entries, setEntries] = useState([])

  async function handleAdd(e) {
    e && e.preventDefault()
    if (!symbol) return
    const entry = { symbol: symbol.toUpperCase(), buyPrice: buyPrice ? parseFloat(buyPrice) : null, qty: qty ? parseInt(qty) : null, external_urls: externalUrl ? [externalUrl] : [] }

    // If user attached files, upload them first and append returned URLs
    if (externalFiles && externalFiles.length > 0) {
      const form = new FormData()
      externalFiles.forEach(f => form.append('files', f))
      try {
        const r = await fetch('/api/upload', { method: 'POST', body: form })
        const jr = await r.json()
        const urls = (jr.files || []).filter(x => x.url).map(x => x.url)
        entry.external_urls = (entry.external_urls || []).concat(urls)
      } catch (err) {
        console.error('upload failed', err)
      }
      setExternalFiles([])
    }

    setEntries(prev => [...prev, entry])
    setSymbol('')
    setBuyPrice('')
    setQty('')
    setExternalUrl('')
  }

  function handleStart() {
    // Persist full entries (including optional external URLs) so the signals
    // request can include user-supplied external inputs for analysis.
    localStorage.setItem('velorix_watchlist', JSON.stringify(entries))
    localStorage.setItem('velorix_portfolio', JSON.stringify(entries))
    if (onDone) onDone()
    else window.location.pathname = '/signals'
  }

  function handleFilesSelected(files) {
    const arr = Array.from(files)
    setExternalFiles(prev => prev.concat(arr))
  }

  function onDrop(e) {
    e.preventDefault()
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesSelected(e.dataTransfer.files)
      e.dataTransfer.clearData()
    }
  }

  function onDragOver(e) {
    e.preventDefault()
  }

  function removeFile(index) {
    setExternalFiles(prev => prev.filter((_, i) => i !== index))
  }

  return (
    <div style={{ minHeight: '100vh', background: '#070b12', color: '#e9f0fb', padding: 24, fontFamily: 'Inter, system-ui, sans-serif' }}>
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ width: 52, height: 52, borderRadius: 16, background: 'linear-gradient(135deg, #ff7a34 0%, #ffb659 100%)', display: 'grid', placeItems: 'center', fontWeight: 800, color: '#08111c' }}>
            AS
          </div>
          <div>
            <p style={{ margin: 0, color: '#7f96c9', textTransform: 'uppercase', letterSpacing: '0.16em', fontSize: 11 }}>Portfolio Entry</p>
            <h1 style={{ margin: '6px 0 0', fontSize: 28 }}>Add Purchased Stocks</h1>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ padding: '10px 16px', borderRadius: 999, background: 'rgba(255,255,255,0.04)', color: '#b7c6e2', fontWeight: 600 }}>Quick: add many, then Start</span>
        </div>
      </header>

      <main style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 20, alignItems: 'start' }}>
        <section style={{ padding: 20, borderRadius: 20, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
          <form onSubmit={handleAdd} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 18, flexWrap: 'nowrap', overflowX: 'auto' }}>
            <input
              placeholder="Symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)', color: '#e9f0fb', minWidth: 120 }}
            />
            <input
              placeholder="Buy"
              value={buyPrice}
              onChange={(e) => setBuyPrice(e.target.value)}
              style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)', color: '#e9f0fb', width: 80 }}
            />
            <input
              placeholder="Qty"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)', color: '#e9f0fb', width: 70 }}
            />
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input
                placeholder="Add URL (optional)"
                value={externalUrl}
                onChange={(e) => setExternalUrl(e.target.value)}
                style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)', color: '#e9f0fb', minWidth: 180 }}
              />
              <div onDrop={onDrop} onDragOver={onDragOver} style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-start' }}>
                <label style={{ padding: '10px 14px', borderRadius: 10, border: '1px dashed rgba(255,255,255,0.08)', cursor: 'pointer', color: '#9fb4db', display: 'inline-block', minWidth: 240, textAlign: 'center', background: 'rgba(255,255,255,0.01)' }}>
                  Drop/upload files (optional) — docx, pdf, xlsx <input type="file" multiple style={{ display: 'none' }} onChange={(e) => handleFilesSelected(e.target.files)} />
                </label>
                {externalFiles.length > 0 ? (
                  <div style={{ display: 'flex', gap: 6, maxWidth: 360, background: 'rgba(255,255,255,0.02)', padding: '6px', borderRadius: 8, alignItems: 'center', overflowX: 'auto' }}>
                    {externalFiles.map((f, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#d6e4ff', fontSize: 12, padding: '4px 8px', background: 'rgba(255,255,255,0.01)', borderRadius: 6 }}>
                        <span style={{ maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                        <button type="button" onClick={() => removeFile(i)} style={{ background: 'transparent', border: 'none', color: '#ff9b9b', cursor: 'pointer', fontSize: 12 }}>×</button>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
              <button onClick={handleAdd} style={{ padding: '12px 16px', borderRadius: 12, background: '#2d6bf6', color: 'white', fontWeight: 700, border: 'none' }}>Add</button>
            </div>
          </form>

          <div style={{ maxHeight: 420, overflow: 'auto' }}>
            {entries.length === 0 ? (
              <div style={{ color: '#9fb4db' }}>No stocks added yet. Add symbols above to build your portfolio.</div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ textAlign: 'left', color: '#9bb0d0', fontSize: 12 }}>
                    <th style={{ padding: '10px 8px' }}>Symbol</th>
                    <th style={{ padding: '10px 8px' }}>Qty</th>
                    <th style={{ padding: '10px 8px' }}>Buy Price</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e, i) => (
                    <tr key={i} style={{ borderTop: '1px solid rgba(255,255,255,0.02)' }}>
                      <td style={{ padding: '12px 8px', fontWeight: 700, color: '#f8fbff' }}>{e.symbol}</td>
                      <td style={{ padding: '12px 8px', color: '#b7c6e2' }}>{e.qty || '-'}</td>
                      <td style={{ padding: '12px 8px', color: '#90d7ab' }}>{e.buyPrice != null ? `$${e.buyPrice}` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div style={{ marginTop: 18, display: 'flex', gap: 10 }}>
            <button onClick={handleStart} style={{ padding: '12px 18px', borderRadius: 12, background: '#1ac18f', color: '#08111c', fontWeight: 800, border: 'none' }}>Start Analyzing</button>
            <button onClick={() => { setEntries([]) }} style={{ padding: '12px 18px', borderRadius: 12, background: 'rgba(255,255,255,0.03)', color: '#a9b9e4', border: 'none' }}>Clear</button>
          </div>
        </section>

        <aside style={{ padding: 20, borderRadius: 20, background: 'linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01))', border: '1px solid rgba(255,255,255,0.04)' }}>
          <h3 style={{ marginTop: 0, color: '#f8fbff' }}>Tips</h3>
          <ul style={{ color: '#9fb4db', marginTop: 8 }}>
            <li>Enter tickers as US or Canadian (e.g., AAPL, SHOP.TO)</li>
            <li>Include buy price and qty to enable portfolio tracking</li>
            <li>Click "Start Analyzing" to fetch signals for your watchlist</li>
          </ul>
        </aside>
      </main>
    </div>
  )
}
