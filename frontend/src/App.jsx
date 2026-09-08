import React, { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import SignalTable from './SignalTable'

const cards = [
  { label: 'Buy Signals', key: 'buy' },
  { label: 'Sell Signals', key: 'sell' },
  { label: 'Hold Signals', key: 'hold' },
  { label: 'Avg Momentum', key: 'avgMomentum' },
]

export default function App() {
  const [rows, setRows] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeFilter, setActiveFilter] = useState('All')
  const [tradeStatus, setTradeStatus] = useState('')
  const [tradeOrders, setTradeOrders] = useState([])
  const [alpacaConnected, setAlpacaConnected] = useState(false)
  const [execConnected, setExecConnected] = useState(false)
  const [execError, setExecError] = useState(null)
  

  useEffect(() => {
    async function load() {
      try {
        // If a watchlist was provided via the entry page, use it
        const raw = localStorage.getItem('velorix_watchlist')
        if (raw) {
          let tickers = []
          let parsed = []
          try { parsed = JSON.parse(raw) } catch (e) { parsed = [] }
          // parsed can be either an array of symbol strings (legacy) or an
          // array of entry objects with optional `external_urls`.
          if (Array.isArray(parsed) && parsed.length > 0) {
            let tickersArr = []
            let externalMap = {}
            if (typeof parsed[0] === 'string') {
              tickersArr = parsed
            } else {
              tickersArr = parsed.map(p => p.symbol).filter(Boolean)
              parsed.forEach(p => {
                if (p.external_urls && p.external_urls.length > 0) externalMap[p.symbol] = p.external_urls
              })
            }
            if (tickersArr.length > 0) {
              console.log('Velorix: loading signals for', tickersArr)
              // send tickers and optional external urls mapping to backend
              const payload = { tickers: tickersArr }
              if (Object.keys(externalMap).length > 0) payload.external_urls = externalMap
              const r = await axios.post('/api/trade/signals', payload)
              const initial = r.data.signals || []
            setRows(initial)
            // fetch missing per-symbol prices when backend returned 0.0
            fetchMissingPrices(initial, setRows)
            setSummary(r.data.summary || null)
            setAlpacaConnected(Boolean(r.data.summary && r.data.summary.alpacaConnected))
            setLoading(false)
            return
          }
        }
      }
        const resp = await axios.get('/api/signals')
        const initial = resp.data.signals || []
        setRows(initial)
        fetchMissingPrices(initial, setRows)
        setSummary(resp.data.summary || null)
        setAlpacaConnected(Boolean(resp.data.summary && resp.data.summary.alpacaConnected))
      } catch (err) {
        console.error(err)
        setError('Failed to load signals. Refresh the page or check the backend.')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  async function fetchMissingPrices(initialRows, setRowsState) {
    if (!initialRows || initialRows.length === 0) return
    // Fetch price info for rows that lack a price or lack session metadata
    const need = initialRows.filter(r => !r.price || Number(r.price) === 0 || !r.session)
    if (need.length === 0) return
    try {
      const promises = need.map(r => axios.get('/api/price', { params: { symbol: r.symbol } }).then(res => ({ symbol: r.symbol, price: res.data.price, price_time: res.data.price_time, session: res.data.session })).catch(() => null))
      const results = await Promise.all(promises)
      const priceMap = {}
      results.forEach(p => { if (p && p.symbol) priceMap[p.symbol] = p })
      const updated = initialRows.map(r => {
        const p = priceMap[r.symbol]
        const priceVal = (r.price && Number(r.price) !== 0) ? r.price : (p && p.price != null ? Number(p.price).toFixed(2) : r.price)
        return ({ ...r, price: priceVal, price_time: p ? p.price_time : r.price_time, session: p ? p.session : r.session })
      })
      setRowsState(updated)
    } catch (e) {
      // ignore
    }
  }

  async function handleTradeConnect() {
    setTradeStatus('connecting')
    try {
      const r = await axios.post('/api/trade/connect')
      setAlpacaConnected(Boolean(r.data.alpacaConnected))
      setExecConnected(Boolean(r.data.execConnected))
      setExecError(r.data.execError || null)
      // Provide clearer, actionable status messages for Alpaca connection
      if (!r.data.alpacaEnabled) {
        setTradeStatus('Alpaca not configured')
      } else if (r.data.alpacaConnected) {
        setTradeStatus('connected')
      } else if (r.data.alpacaError) {
        setTradeStatus(`Alpaca error: ${r.data.alpacaError}`)
      } else {
        setTradeStatus('Alpaca detected but not connected')
      }
    } catch (e) {
      setTradeStatus(`failed: ${e.message}`)
    }
  }

  async function handleRunOnce() {
    setTradeStatus('running')
    try {
      // Use the currently displayed rows' symbols as the run_once tickers so
      // orders correspond to the visible watchlist rather than the backend default.
      const currentTickers = rows && rows.length > 0 ? rows.map(r => r.symbol) : null
      const payload = { window: 50, interval: '1d' }
      if (currentTickers) payload.tickers = currentTickers
      const r = await axios.post('/api/trade/run_once', payload)
      setTradeOrders(r.data.orders || [])
      setTradeStatus('completed')
    } catch (e) {
      setTradeStatus(`failed: ${e.message}`)
    }
  }

  const filteredRows = useMemo(() => {
    if (activeFilter === 'All') return rows
    return rows.filter((row) => row.action === activeFilter)
  }, [rows, activeFilter])

  return (
    <div style={{ minHeight: '100vh', background: '#070b12', color: '#e9f0fb', padding: 24, fontFamily: 'Inter, system-ui, sans-serif' }}>
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ width: 52, height: 52, borderRadius: 16, background: 'linear-gradient(135deg, #ff7a34 0%, #ffb659 100%)', display: 'grid', placeItems: 'center', fontWeight: 800, color: '#08111c' }}>
            AS
          </div>
          <div>
            <p style={{ margin: 0, color: '#7f96c9', textTransform: 'uppercase', letterSpacing: '0.16em', fontSize: 11 }}>Signal Dashboard</p>
            <h1 style={{ margin: '6px 0 0', fontSize: 32 }}>Alpha-style Signals</h1>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ padding: '10px 16px', borderRadius: 999, background: 'rgba(255,255,255,0.05)', color: '#b7c6e2', fontWeight: 600 }}>Data Source: {summary?.dataSource || 'loading...'}</span>
          <span style={{ padding: '10px 16px', borderRadius: 999, background: 'rgba(0, 135, 255, 0.14)', color: '#b7d5ff', fontWeight: 600 }}>Updated: {summary?.updatedAt ? new Date(summary.updatedAt).toLocaleString() : '...'}</span>
          
          <span style={{ alignSelf: 'center', marginLeft: 8, color: execConnected ? '#9ef0c8' : '#ffcbcb', fontWeight: 700 }}>{execConnected ? 'Exec OK' : (execError ? `Exec error` : 'Exec: —')}</span>
        </div>
      </header>

      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16, marginBottom: 24 }}>
        {cards.map((card) => {
          const value = summary ? summary[card.key] : '...'
          const display = card.key === 'avgMomentum' ? value : summary ? value : '...'
          return (
            <div key={card.key} style={{ padding: 20, borderRadius: 22, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', minHeight: 120 }}>
              <p style={{ margin: 0, color: '#9bb0d0', textTransform: 'uppercase', fontSize: 12, letterSpacing: '0.14em' }}>{card.label}</p>
              <p style={{ margin: '18px 0 0', fontSize: 34, fontWeight: 700, color: '#f8fbff' }}>{display}</p>
              {card.key === 'buy' && summary ? (
                <small style={{ color: '#90d7ab' }}>{Math.round((summary.buy / Math.max(summary.total, 1)) * 100)}% of watchlist</small>
              ) : null}
            </div>
          )
        })}
      </section>
      {/* Entry page is served separately; this is the signals page only. */}
      {summary?.warning ? (
        <div style={{ marginBottom: 18, padding: 16, borderRadius: 18, background: 'rgba(220, 70, 70, 0.12)', color: '#ffd4d4', border: '1px solid rgba(220, 70, 70, 0.25)' }}>
          {summary.warning}
        </div>
      ) : null}

      {tradeStatus ? (
        <div style={{ marginBottom: 12, padding: 12, borderRadius: 12, background: 'rgba(255,255,255,0.03)', color: '#d6e4ff' }}>
          <strong>Trade status:</strong> {tradeStatus}
          {tradeOrders && tradeOrders.length > 0 ? (
            <div style={{ marginTop: 8 }}>
              <strong>Orders:</strong>
              <pre style={{ whiteSpace: 'pre-wrap', margin: 0, color: '#a7b7d1' }}>{JSON.stringify(tradeOrders, null, 2)}</pre>
            </div>
          ) : null}
        </div>
      ) : null}

      <section style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, marginBottom: 18, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 24 }}>Live Signal Feed</h2>
          <p style={{ margin: '8px 0 0', color: '#9fb4db' }}>Real-time momentum signals from your watchlist.</p>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {['All', 'Buy', 'Sell', 'Hold'].map((filter) => (
            <button
              key={filter}
              onClick={() => setActiveFilter(filter)}
              style={{
                padding: '10px 18px',
                borderRadius: 999,
                border: 'none',
                cursor: 'pointer',
                background: filter === activeFilter ? '#2d6bf6' : 'rgba(255,255,255,0.05)',
                color: filter === activeFilter ? 'white' : '#a9b9e4',
                fontWeight: 700,
              }}
            >
              {filter}
            </button>
          ))}
        </div>
      </section>

      <main>
        <div style={{ borderRadius: 24, overflow: 'hidden', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)' }}>
          {loading ? (
            <div style={{ padding: 40, textAlign: 'center', color: '#9fb4db' }}>Loading signals…</div>
          ) : error ? (
            <div style={{ padding: 40, textAlign: 'center', color: '#f36c6c' }}>{error}</div>
          ) : (
            <SignalTable rows={filteredRows} />
          )}
        </div>
      </main>
    </div>
  )
}
