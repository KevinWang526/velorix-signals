import React from 'react'

function Badge({ action }) {
  const styles = {
    Buy: { background: '#1ac18f', color: 'white', padding: '8px 12px', borderRadius: 999, fontWeight: 700 },
    Sell: { background: '#d04460', color: 'white', padding: '8px 12px', borderRadius: 999, fontWeight: 700 },
    Hold: { background: 'rgba(255,255,255,0.08)', color: '#e9f0fb', padding: '8px 12px', borderRadius: 999, fontWeight: 700 },
  }
  return <span style={styles[action] || styles.Hold}>{action}</span>
}

export default function SignalTable({ rows }) {
  if (!rows || rows.length === 0) {
    return <div style={{ padding: 28, textAlign: 'center', color: '#9fb4db' }}>No signals available yet.</div>
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
        <thead>
          <tr style={{ textAlign: 'left', color: '#8ca7d9', fontSize: 13, letterSpacing: '0.02em' }}>
            <th style={{ padding: '18px 16px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>Asset</th>
            <th style={{ padding: '18px 16px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>Action</th>
            <th style={{ padding: '18px 16px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>Price</th>
            <th style={{ padding: '18px 16px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>Trend</th>
            <th style={{ padding: '18px 16px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>Momentum</th>
            <th style={{ padding: '18px 16px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>Detail</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.symbol} style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
              <td style={{ padding: '16px', verticalAlign: 'middle' }}>
                <div style={{ fontWeight: 700, fontSize: 15 }}>{row.symbol}</div>
                <div style={{ color: '#9fb4db', fontSize: 12, marginTop: 4 }}>{row.detail || 'Signal detail unavailable'}</div>
              </td>
              <td style={{ padding: '16px', verticalAlign: 'middle' }}><Badge action={row.action} /></td>
              <td style={{ padding: '16px', verticalAlign: 'middle', fontWeight: 700 }}>
                ${Number(row.price || 0).toFixed(2)} {row.session && row.session.session ? <small style={{ marginLeft: 8, color: '#9fb4db', fontWeight: 600 }}>({row.session.session})</small> : null}
              </td>
              <td style={{ padding: '16px', verticalAlign: 'middle', textTransform: 'capitalize', color: row.trend === 'bullish' ? '#8ce99a' : row.trend === 'bearish' ? '#ff8fa3' : '#cfe6ff' }}>
                {row.trend}
              </td>
              <td style={{ padding: '16px', verticalAlign: 'middle', color: row.momentum?.startsWith('+') ? '#8ce99a' : row.momentum?.startsWith('-') ? '#ff8fa3' : '#cfe6ff', fontWeight: 700 }}>
                {row.momentum}
              </td>
              <td style={{ padding: '16px', verticalAlign: 'middle', color: '#a7b7d1', fontSize: 13 }}>
                <div style={{ fontWeight: 600, color: '#e9f0fb' }}>{row.explain || row.detail}</div>
                {row.detail && row.detail !== row.explain ? (
                  <div style={{ marginTop: 6, color: '#9fb4db', fontSize: 12 }}>{row.detail}</div>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
