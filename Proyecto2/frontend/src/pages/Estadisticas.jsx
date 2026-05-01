import React, { useState, useEffect } from 'react'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell
} from 'recharts'

const DEMO_INGRESOS = [
  { hora: '06:00', ingresos: 3, salidas: 1 },
  { hora: '08:00', ingresos: 12, salidas: 5 },
  { hora: '10:00', ingresos: 8,  salidas: 9 },
  { hora: '12:00', ingresos: 15, salidas: 11 },
  { hora: '14:00', ingresos: 6,  salidas: 8 },
  { hora: '16:00', ingresos: 11, salidas: 7 },
  { hora: '18:00', ingresos: 5,  salidas: 14 },
]

const DEMO_ESPACIOS = [
  { espacio: 'E1', usos: 24 },
  { espacio: 'E2', usos: 31 },
  { espacio: 'E3', usos: 18 },
  { espacio: 'E4', usos: 27 },
  { espacio: 'E5', usos: 9  },
]

const DEMO_RESUMEN = { ingresos: 60, salidas: 55, emergencias: 2, ventilador: 5 }

const DEMO_GAS = [
  { hora: '06:00', activaciones: 0 },
  { hora: '08:00', activaciones: 1 },
  { hora: '10:00', activaciones: 0 },
  { hora: '12:00', activaciones: 2 },
  { hora: '14:00', activaciones: 0 },
  { hora: '16:00', activaciones: 1 },
  { hora: '18:00', activaciones: 0 }
]

export default function Estadisticas({ state, publish, connected }) {
  const [data, setData]       = useState({ ingresos: DEMO_INGRESOS, espacios: DEMO_ESPACIOS, gas: DEMO_GAS, resumen: { ...DEMO_RESUMEN, sospechosas: 0 }, alertas: [] })
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  const [historicalRange, setHistoricalRange] = useState(24)
  const [loadingHistorical, setLoadingHistorical] = useState(false)
  const [historicalData, setHistoricalData] = useState(null)
  const [viewingHistorical, setViewingHistorical] = useState(false)

  useEffect(() => {
    if (!publish) return
    publish('/parkguard/stats/request', { hours: 12, ts: new Date().toISOString() })
  }, [publish])

  useEffect(() => {
    if (!publish || !connected || viewingHistorical) return
    const id = setInterval(() => {
      publish('/parkguard/stats/request', { hours: 12, ts: new Date().toISOString() })
    }, 15000)
    return () => clearInterval(id)
  }, [publish, connected, viewingHistorical])

  useEffect(() => {
    if (!state?.stats) return
    const stats = state.stats
    
    if (viewingHistorical) {
      // Si estamos viendo datos históricos, actualizar historicalData
      setHistoricalData(stats)
      setLoadingHistorical(false)
    } else {
      // Si no, actualizar datos normales (últimas 12 horas)
      setData({
        ingresos: stats.ingresos?.length ? stats.ingresos : DEMO_INGRESOS,
        espacios: stats.espacios?.length ? stats.espacios : DEMO_ESPACIOS,
        gas: stats.gas?.length ? stats.gas : DEMO_GAS,
        resumen: {
          ingresos: Number(stats?.resumen?.ingresos || 0),
          salidas: Number(stats?.resumen?.salidas || 0),
          emergencias: Number(stats?.resumen?.emergencias || 0),
          ventilador: Number(stats?.resumen?.ventilador || 0),
          sospechosas: Number(stats?.resumen?.sospechosas || 0)
        },
        alertas: Array.isArray(stats.alertas) ? stats.alertas : []
      })
    }
  }, [state?.stats, viewingHistorical])

  const exportPDF = async () => {
    try {
      setExporting(true)
      setExportError('')
      const { jsPDF } = await import('jspdf')
      const autoTableModule = await import('jspdf-autotable')
      const exportedAutoTable = autoTableModule.default || autoTableModule.autoTable

      const doc = new jsPDF()
      const now = new Date().toLocaleString('es-GT')

      const runAutoTable = (options) => {
        if (typeof exportedAutoTable === 'function') {
          return exportedAutoTable(doc, options)
        }
        if (typeof doc.autoTable === 'function') {
          return doc.autoTable(options)
        }
        throw new Error('No se pudo cargar jspdf-autotable')
      }

    doc.setFont('helvetica', 'bold')
    doc.setFontSize(20)
    doc.text('Park-Guard 2.0', 14, 20)

    doc.setFont('helvetica', 'normal')
    doc.setFontSize(10)
    doc.setTextColor(120)
    doc.text(`Reporte generado: ${now}`, 14, 28)

    doc.setTextColor(0)
    doc.setFontSize(14)
    doc.setFont('helvetica', 'bold')
    doc.text('Resumen del dia', 14, 42)

    runAutoTable({
      startY: 48,
      head: [['Metrica', 'Valor']],
      body: [
        ['Total ingresos',          data.resumen.ingresos],
        ['Total salidas',           data.resumen.salidas],
        ['Activaciones emergencia', data.resumen.emergencias],
        ['Activaciones ventilador', data.resumen.ventilador],
        ['Alertas sospechosas RFID', data.resumen.sospechosas]
      ],
      styles: { fontSize: 11 },
      headStyles: { fillColor: [37, 99, 235] }
    })

    doc.addPage()
    doc.setFontSize(14)
    doc.setFont('helvetica', 'bold')
    doc.text('Uso por espacio', 14, 20)

    runAutoTable({
      startY: 26,
      head: [['Espacio', 'Usos']],
      body: data.espacios.map(e => [e.espacio, e.usos]),
      styles: { fontSize: 11 },
      headStyles: { fillColor: [37, 99, 235] }
    })

    doc.setFontSize(14)
    doc.setFont('helvetica', 'bold')
    const y2 = (doc.lastAutoTable?.finalY ?? 26) + 16
    doc.text('Ingresos y salidas por hora', 14, y2)

    runAutoTable({
      startY: y2 + 6,
      head: [['Hora', 'Ingresos', 'Salidas']],
      body: data.ingresos.map(r => [r.hora, r.ingresos, r.salidas]),
      styles: { fontSize: 11 },
      headStyles: { fillColor: [37, 99, 235] }
    })

    doc.addPage()
    doc.setFontSize(14)
    doc.setFont('helvetica', 'bold')
    doc.text('Activaciones de sensor de gas', 14, 20)

    runAutoTable({
      startY: 26,
      head: [['Hora', 'Activaciones']],
      body: data.gas.map(r => [r.hora, r.activaciones]),
      styles: { fontSize: 11 },
      headStyles: { fillColor: [239, 68, 68] }
    })

      doc.save(`parkguard-reporte-${Date.now()}.pdf`)
    } catch (e) {
      console.error('Error generando PDF:', e)
      setExportError('No se pudo generar el reporte PDF. Intente nuevamente.')
    } finally {
      setExporting(false)
    }
  }

  const requestHistoricalData = () => {
    if (!publish) return
    setLoadingHistorical(true)
    setViewingHistorical(true)
    setExportError('')
    publish('/parkguard/stats/request', { hours: historicalRange, ts: new Date().toISOString(), historical: true })
  }

  const backToRealtime = () => {
    setViewingHistorical(false)
    setHistoricalData(null)
    setExportError('')
    if (publish) {
      publish('/parkguard/stats/request', { hours: 12, ts: new Date().toISOString() })
    }
  }

  const exportHistoricalPDF = async () => {
    if (!historicalData) {
      setExportError('No hay datos históricos para exportar. Solicite los datos primero.')
      return
    }

    try {
      setExporting(true)
      setExportError('')
      const { jsPDF } = await import('jspdf')
      const autoTableModule = await import('jspdf-autotable')
      const exportedAutoTable = autoTableModule.default || autoTableModule.autoTable

      const doc = new jsPDF()
      const now = new Date().toLocaleString('es-GT')
      const periodText = historicalRange < 24 ? `${historicalRange} horas` : historicalRange < 720 ? `${Math.round(historicalRange / 24)} días` : `${Math.round(historicalRange / 24)} días`

      const runAutoTable = (options) => {
        if (typeof exportedAutoTable === 'function') {
          return exportedAutoTable(doc, options)
        }
        if (typeof doc.autoTable === 'function') {
          return doc.autoTable(options)
        }
        throw new Error('No se pudo cargar jspdf-autotable')
      }

      doc.setFont('helvetica', 'bold')
      doc.setFontSize(20)
      doc.text('Park-Guard 2.0', 14, 20)

      doc.setFont('helvetica', 'normal')
      doc.setFontSize(10)
      doc.setTextColor(120)
      doc.text(`Reporte Histórico - Últimos ${periodText}`, 14, 28)
      doc.text(`Generado: ${now}`, 14, 34)

      doc.setTextColor(0)
      doc.setFontSize(14)
      doc.setFont('helvetica', 'bold')
      doc.text('Resumen Histórico', 14, 48)

      runAutoTable({
        startY: 54,
        head: [['Métrica', 'Total']],
        body: [
          ['Total ingresos',          historicalData.resumen?.ingresos || 0],
          ['Total salidas',           historicalData.resumen?.salidas || 0],
          ['Activaciones emergencia', historicalData.resumen?.emergencias || 0],
          ['Activaciones ventilador', historicalData.resumen?.ventilador || 0],
          ['Alertas sospechosas RFID', historicalData.resumen?.sospechosas || 0]
        ],
        styles: { fontSize: 11 },
        headStyles: { fillColor: [37, 99, 235] }
      })

      doc.addPage()
      doc.setFontSize(14)
      doc.setFont('helvetica', 'bold')
      doc.text('Uso por Espacio', 14, 20)

      runAutoTable({
        startY: 26,
        head: [['Espacio', 'Usos']],
        body: (historicalData.espacios || []).map(e => [e.espacio, e.usos]),
        styles: { fontSize: 11 },
        headStyles: { fillColor: [37, 99, 235] }
      })

      doc.addPage()
      doc.setFontSize(14)
      doc.setFont('helvetica', 'bold')
      doc.text('Ingresos y Salidas por Hora', 14, 20)

      const ingresoBody = (historicalData.ingresos || []).map(r => [r.hora, r.ingresos, r.salidas])
      runAutoTable({
        startY: 26,
        head: [['Hora', 'Ingresos', 'Salidas']],
        body: ingresoBody.length > 0 ? ingresoBody : [['Sin datos', '0', '0']],
        styles: { fontSize: 10 },
        headStyles: { fillColor: [37, 99, 235] }
      })

      doc.addPage()
      doc.setFontSize(14)
      doc.setFont('helvetica', 'bold')
      doc.text('Activaciones de Sensor de Gas', 14, 20)

      runAutoTable({
        startY: 26,
        head: [['Hora', 'Activaciones']],
        body: (historicalData.gas || []).map(r => [r.hora, r.activaciones]),
        styles: { fontSize: 11 },
        headStyles: { fillColor: [239, 68, 68] }
      })

      if (historicalData.alertas && historicalData.alertas.length > 0) {
        doc.addPage()
        doc.setFontSize(14)
        doc.setFont('helvetica', 'bold')
        doc.text('Alertas Sospechosas RFID', 14, 20)

        const alertBody = historicalData.alertas.slice(0, 50).map(a => [
          new Date(a.timestamp).toLocaleString('es-GT'),
          a.rfid || 'N/A',
          a.attempts || 0,
          a.message || 'Actividad sospechosa'
        ])

        runAutoTable({
          startY: 26,
          head: [['Fecha/Hora', 'RFID', 'Intentos', 'Mensaje']],
          body: alertBody,
          styles: { fontSize: 9 },
          headStyles: { fillColor: [239, 68, 68] }
        })
      }

      doc.save(`parkguard-reporte-historico-${Date.now()}.pdf`)
    } catch (e) {
      console.error('Error generando PDF histórico:', e)
      setExportError('No se pudo generar el reporte histórico. Intente nuevamente.')
    } finally {
      setExporting(false)
    }
  }

  useEffect(() => {
    if (!state?.stats) return
    const stats = state.stats
    setHistoricalData(stats)
    setLoadingHistorical(false)
  }, [state?.stats])

  const maxUso = data.espacios.reduce((m, e) => e.usos > m.usos ? e : m, data.espacios[0])

  // Usar datos históricos si estamos viendo datos históricos
  const displayData = viewingHistorical && historicalData 
    ? {
        ingresos: historicalData.ingresos?.length ? historicalData.ingresos : data.ingresos,
        espacios: historicalData.espacios?.length ? historicalData.espacios : data.espacios,
        gas: historicalData.gas?.length ? historicalData.gas : data.gas,
        resumen: historicalData.resumen || data.resumen,
        alertas: historicalData.alertas || data.alertas
      }
    : data

  const maxUsoDisplay = displayData.espacios.reduce((m, e) => e.usos > m.usos ? e : m, displayData.espacios[0])

  const tooltipStyle = {
    contentStyle: { background: '#1e2436', border: '1px solid #252c3f', borderRadius: 8, fontSize: 12 },
    itemStyle:    { color: '#e8eaf0' },
    labelStyle:   { color: '#8a91a8' }
  }

  return (
    <div style={styles.root} className="fade-in">
      <div style={styles.header}>
        <h1 style={styles.title}>Estadísticas</h1>
      </div>
      {exportError && (
        <p style={{ color: 'var(--red)', fontSize: 13, marginBottom: 10 }}>{exportError}</p>
      )}

      <div style={styles.historicalSection}>
        <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Descargar Reporte Histórico</h3>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text3)', marginBottom: 6 }}>Período de tiempo</label>
            <select 
              value={historicalRange} 
              onChange={(e) => setHistoricalRange(Number(e.target.value))}
              disabled={loadingHistorical}
              style={{
                padding: '8px 12px',
                borderRadius: 6,
                border: '1px solid var(--border)',
                background: 'var(--bg2)',
                color: 'var(--text1)',
                fontSize: 13,
                cursor: loadingHistorical ? 'not-allowed' : 'pointer'
              }}
            >
              <option value={24}>Últimas 24 horas</option>
              <option value={168}>Últimos 7 días</option>
              <option value={336}>Últimos 14 días</option>
              <option value={720}>Últimos 30 días</option>
              <option value={1440}>Últimos 60 días</option>
              <option value={2880}>Últimos 120 días</option>
            </select>
          </div>
          <button 
            className="btn btn-secondary" 
            onClick={requestHistoricalData}
            disabled={loadingHistorical}
            style={{ minWidth: 140 }}
          >
            {loadingHistorical ? 'Cargando...' : 'Cargar datos'}
          </button>
          <button 
            className="btn btn-primary" 
            onClick={exportHistoricalPDF}
            disabled={!historicalData || loadingHistorical || exporting}
            style={{ minWidth: 140 }}
          >
            {exporting ? 'Generando...' : 'Descargar PDF'}
          </button>
          {viewingHistorical && (
            <button 
              className="btn btn-secondary" 
              onClick={backToRealtime}
              style={{ minWidth: 140 }}
            >
              Volver a Tiempo Real
            </button>
          )}
        </div>
      </div>

      <div style={styles.kpis}>
        <KPI label="Total ingresos"          value={displayData.resumen.ingresos}   color="var(--accent)" />
        <KPI label="Total salidas"           value={displayData.resumen.salidas}    color="var(--green)"  />
        <KPI label="Emergencias"             value={displayData.resumen.emergencias} color="var(--red)"   />
        <KPI label="Activaciones ventilador" value={displayData.resumen.ventilador} color="var(--yellow)" />
        <KPI label="Alertas RFID sospechosas" value={displayData.resumen.sospechosas} color="var(--yellow)" />
      </div>

      <div style={styles.grid}>
        <div className="card">
          <div style={styles.cardHeader}>
            <span style={styles.cardTitle}>Ingresos y salidas por hora</span>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={displayData.ingresos} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#252c3f" />
              <XAxis dataKey="hora" tick={{ fill: '#8a91a8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#8a91a8', fontSize: 11 }} />
              <Tooltip {...tooltipStyle} />
              <Line type="monotone" dataKey="ingresos" stroke="#3d7fff" strokeWidth={2} dot={{ r: 3 }} name="Ingresos" />
              <Line type="monotone" dataKey="salidas"  stroke="#22c55e" strokeWidth={2} dot={{ r: 3 }} name="Salidas"  />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div style={styles.cardHeader}>
            <span style={styles.cardTitle}>Uso por espacio</span>
            {maxUsoDisplay && (
              <span className="badge badge-blue">Más usado: {maxUsoDisplay.espacio}</span>
            )}
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={displayData.espacios} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#252c3f" />
              <XAxis dataKey="espacio" tick={{ fill: '#8a91a8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#8a91a8', fontSize: 11 }} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="usos" radius={[4, 4, 0, 0]} name="Usos">
                {displayData.espacios.map((entry, i) => (
                  <Cell key={i} fill={entry.espacio === maxUsoDisplay?.espacio ? '#3d7fff' : '#252c3f'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div style={styles.cardHeader}>
            <span style={styles.cardTitle}>Activaciones de sensor de gas</span>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={displayData.gas} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#252c3f" />
              <XAxis dataKey="hora" tick={{ fill: '#8a91a8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#8a91a8', fontSize: 11 }} />
              <Tooltip {...tooltipStyle} />
              <Line type="monotone" dataKey="activaciones" stroke="#ef4444" strokeWidth={2} dot={{ r: 3 }} name="Gas" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div style={styles.cardHeader}>
            <span style={styles.cardTitle}>Alertas sospechosas RFID</span>
          </div>
          <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 220, overflowY: 'auto' }}>
            {displayData.alertas?.length
              ? displayData.alertas.map((a, i) => (
                  <div key={`${a.timestamp}-${i}`} style={{ padding: '8px 10px', borderRadius: 8, background: 'var(--bg3)', display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                    <span style={{ fontSize: 12, color: 'var(--text2)' }}>{a.message || `RFID ${a.rfid} con ${a.attempts} intentos`}</span>
                    <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>{new Date(a.timestamp).toLocaleTimeString()}</span>
                  </div>
                ))
              : <p style={{ color: 'var(--text3)', fontSize: 13 }}>Sin alertas sospechosas registradas.</p>
            }
          </div>
        </div>
      </div>
    </div>
  )
}

function KPI({ label, value, color }) {
  return (
    <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
      <div style={{ width: 4, height: 40, borderRadius: 2, background: color, flexShrink: 0 }} />
      <div>
        <div style={{ fontSize: 28, fontWeight: 800, fontFamily: 'var(--font-head)', color }}>{value}</div>
        <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 1 }}>{label}</div>
      </div>
    </div>
  )
}

const styles = {
  root:   { padding: '28px 32px', maxWidth: 1100, margin: '0 auto' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 },
  title:  { fontFamily: 'var(--font-head)', fontSize: 26, fontWeight: 800 },
  kpis:   { display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 14, marginBottom: 16 },
  grid:   { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 },
  cardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  cardTitle:  { fontSize: 14, fontWeight: 600 },
  historicalSection: { background: 'var(--bg2)', padding: 16, borderRadius: 8, marginBottom: 20, border: '1px solid var(--border)' }
}
