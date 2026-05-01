import React, { useEffect, useRef } from 'react'

const DEMO_ESPACIOS = {
  E1: { estado: 'libre',    habilitado: true  },
  E2: { estado: 'ocupado',  habilitado: true  },
  E3: { estado: 'libre',    habilitado: true  },
  E4: { estado: 'ocupado',  habilitado: true  },
  E5: { estado: 'libre',    habilitado: true  },
  E6: { estado: 'libre',    habilitado: false }
}

export default function RealTime({ state, publish, connected }) {
  const p5Ref  = useRef(null)
  const p5Inst = useRef(null)
  const espaciosRef = useRef(DEMO_ESPACIOS)

  const espacios    = Object.keys(state.espacios).length ? state.espacios : DEMO_ESPACIOS
  const libres      = Object.values(espacios).filter(e => e.estado === 'libre' && e.habilitado).length
  const ocupados    = Object.values(espacios).filter(e => e.estado === 'ocupado').length
  const gasPercent  = Math.min(100, state.gasLevel)
  const gasColor    = gasPercent > 70 ? 'var(--red)' : gasPercent > 40 ? 'var(--yellow)' : 'var(--green)'

  useEffect(() => {
    espaciosRef.current = espacios
    p5Inst.current?.redraw()
  }, [espacios])

  useEffect(() => {
    let p5
    import('https://cdn.jsdelivr.net/npm/p5@1.9.4/lib/p5.min.js').then(() => {
      const sketch = (p) => {
        const COLS = 3
        const PAD  = 16
        let W, H, cW, cH

        p.setup = () => {
          const c = p.createCanvas(p5Ref.current.offsetWidth, 10)
          c.parent(p5Ref.current)
          p.noLoop()
          resize()
        }

        p.windowResized = () => {
          resize()
          p.redraw()
        }

        function resize() {
          const rows = Math.max(1, Math.ceil(Object.keys(espaciosRef.current).length / COLS))
          W  = p5Ref.current.offsetWidth
          cW = (W - PAD * (COLS + 1)) / COLS
          cH = cW
          H  = PAD * (rows + 1) + cH * rows
          p.resizeCanvas(W, H)
        }

        p.draw = () => {
          p.clear()
          p.background(17, 21, 32)
          const espaciosActuales = espaciosRef.current
          const keys = Object.keys(espaciosActuales)
          keys.forEach((key, i) => {
            const col = i % COLS
            const row = Math.floor(i / COLS)
            const x   = PAD + col * (cW + PAD)
            const y   = PAD + row * (cH + PAD)
            const esp = espaciosActuales[key]

            const isOcupado     = esp.estado === 'ocupado'
            const isDeshabilitado = !esp.habilitado

            let fillR = isDeshabilitado ? [30, 35, 50] : isOcupado ? [30, 20, 20] : [15, 30, 22]
            let strokeR= isDeshabilitado ? [50, 60, 80] : isOcupado ? [239, 68, 68] : [34, 197, 94]

            p.push()
            p.fill(...fillR)
            p.stroke(...strokeR)
            p.strokeWeight(1.5)
            p.rect(x, y, cW, cH, 10)

            p.noStroke()
            if (!isDeshabilitado) {
              if (isOcupado) {
                p.fill(239, 68, 68, 200)
                drawCar(p, x + cW / 2, y + cH / 2 - 6, cW * 0.55)
              } else {
                p.fill(34, 197, 94, 60)
                p.ellipse(x + cW / 2, y + cH / 2 - 4, cW * 0.35, cH * 0.3)
              }
            }

            p.fill(isDeshabilitado ? 80 : 160)
            p.textAlign(p.CENTER, p.BOTTOM)
            p.textSize(11)
            p.text(key, x + cW / 2, y + cH - 6)
            p.pop()
          })
        }

        function drawCar(p, cx, cy, w) {
          const h = w * 0.45
          p.rect(cx - w / 2, cy - h / 2 + 4, w, h * 0.55, 4)
          p.rect(cx - w * 0.35, cy - h / 2, w * 0.7, h * 0.55, 4)
          p.fill(20, 20, 20)
          p.ellipse(cx - w * 0.28, cy + h * 0.2, w * 0.2, w * 0.2)
          p.ellipse(cx + w * 0.28, cy + h * 0.2, w * 0.2, w * 0.2)
        }

        p5Inst.current = p
      }

      p5 = new window.p5(sketch)
    })
    return () => p5?.remove()
  }, [])

  const sendCmd = (topic, estado) => {
    const ts = new Date().toISOString()

    if (topic === 'ventilador') {
      // Route through consumer so command is logged in Mongo and appears in statistics.
      publish('/parkguard/actuadores/ventilador', { estado, ts })
      return
    }

    if (topic === 'emergencia') {
      // Route through consumer to keep emergency event tracking consistent.
      publish('/parkguard/actuadores/emergencia', { estado, ts })
      return
    }

    publish(`/parkguard/actuadores/${topic}`, { estado, ts })
  }

  const toggleSpace = (spaceKey) => {
    const space = espacios[spaceKey]
    if (!space) return
    const spaceId = Number(spaceKey.replace('E', ''))
    publish('/parkguard/space/manage', {
      space_id: spaceId,
      enabled: !space.habilitado,
      timestamp: new Date().toISOString(),
      source: 'frontend'
    })
  }

  return (
    <div style={styles.root} className="fade-in">
      <h1 style={styles.title}>Tiempo Real</h1>

      <div className="rt-grid">

        <div className="card rt-col-2">
          <div style={styles.cardHeader}>
            <span style={styles.cardTitle}>Espacios de parqueo</span>
            <div style={{ display: 'flex', gap: 16 }}>
              <Stat color="var(--green)" label="Libres"  value={libres} />
              <Stat color="var(--red)"   label="Ocupados" value={ocupados} />
            </div>
          </div>
          <div ref={p5Ref} style={{ borderRadius: 10, overflow: 'hidden', marginTop: 12 }} />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

          <div className="card">
            <div style={styles.cardTitle}>Sensor de gas</div>
            <div style={{ marginTop: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 13, color: 'var(--text2)' }}>Nivel</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: gasColor }}>{gasPercent}%</span>
              </div>
              <div style={styles.progressTrack}>
                <div style={{ ...styles.progressBar, width: `${gasPercent}%`, background: gasColor }} />
              </div>
              {gasPercent > 70 && (
                <p style={{ color: 'var(--red)', fontSize: 12, marginTop: 8 }}>Nivel de gas elevado</p>
              )}
            </div>
          </div>

          <div className="card">
            <div style={styles.cardTitle}>Talanqueras</div>
            <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <StatusRow label="Entrada" on={state.talanqueraEntrada} />
              <StatusRow label="Salida"  on={state.talanqueraSalida} />
            </div>
          </div>

          <div className="card">
            <div style={styles.cardTitle}>Control remoto</div>
            <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <button
                className={`btn ${state.ventilador ? 'btn-success' : 'btn-ghost'}`}
                style={{ justifyContent: 'space-between' }}
                onClick={() => sendCmd('ventilador', !state.ventilador)}
              >
                <span>Ventilador</span>
                <span className={`dot ${state.ventilador ? 'dot-green pulse' : 'dot-gray'}`} />
              </button>
              <button
                className={`btn ${state.emergencia ? 'btn-danger' : 'btn-ghost'}`}
                style={{ justifyContent: 'space-between' }}
                onClick={() => sendCmd('emergencia', !state.emergencia)}
              >
                <span>Emergencia</span>
                <span className={`dot ${state.emergencia ? 'dot-red pulse' : 'dot-gray'}`} />
              </button>
            </div>
          </div>
        </div>

        <div className="card rt-col-3">
          <div style={styles.cardTitle}>Gestion de parqueos</div>
          <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10 }}>
            {Object.keys(espacios).map((key) => {
              const s = espacios[key]
              return (
                <button
                  key={key}
                  className={`btn ${s.habilitado ? 'btn-ghost' : 'btn-danger'}`}
                  style={{ justifyContent: 'space-between' }}
                  onClick={() => toggleSpace(key)}
                >
                  <span>{key}</span>
                  <span style={{ fontSize: 12 }}>{s.habilitado ? 'Habilitado' : 'Deshabilitado'}</span>
                </button>
              )
            })}
          </div>
        </div>

        <div className="card rt-col-3">
          <div style={styles.cardTitle}>Alertas RFID sospechosas</div>
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 160, overflowY: 'auto' }}>
            {state.alertas.length === 0
              ? <p style={{ color: 'var(--text3)', fontSize: 13 }}>Sin alertas sospechosas por ahora.</p>
              : state.alertas.map(a => (
                <div key={a.id} style={styles.eventRow}>
                  <span className="badge badge-red">Alerta</span>
                  <span style={{ fontSize: 13, color: 'var(--text2)', flex: 1 }}>{a.mensaje}</span>
                  <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
                    {new Date(a.ts).toLocaleTimeString()}
                  </span>
                </div>
              ))}
          </div>
        </div>

        <div className="card rt-col-3">
          <div style={styles.cardTitle}>Eventos recientes</div>
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 220, overflowY: 'auto' }}>
            {state.eventos.length === 0
              ? <p style={{ color: 'var(--text3)', fontSize: 13 }}>Sin eventos registrados aún.</p>
              : state.eventos.map(ev => (
                <div key={ev.id} style={styles.eventRow}>
                  <span className={`badge ${ev.tipo === 'autorizado' ? 'badge-green' : ev.tipo === 'denegado' ? 'badge-red' : 'badge-blue'}`}>
                    {ev.tipo ?? 'evento'}
                  </span>
                  <span style={{ fontSize: 13, color: 'var(--text2)', flex: 1 }}>{ev.mensaje ?? ev.topic}</span>
                  <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
                    {new Date(ev.ts).toLocaleTimeString()}
                  </span>
                </div>
              ))
            }
          </div>
        </div>

      </div>
    </div>
  )
}

function Stat({ color, label, value }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 22, fontWeight: 700, color, fontFamily: 'var(--font-head)' }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--text3)' }}>{label}</div>
    </div>
  )
}

function StatusRow({ label, on }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontSize: 13, color: 'var(--text2)' }}>{label}</span>
      <span className={`badge ${on ? 'badge-green' : 'badge-red'}`}>{on ? 'Abierta' : 'Cerrada'}</span>
    </div>
  )
}

const styles = {
  root:  { padding: '28px 32px', width: '100%', boxSizing: 'border-box' },
  title: { fontFamily: 'var(--font-head)', fontSize: 26, fontWeight: 800, marginBottom: 24 },
  grid:  { display: 'grid', gridTemplateColumns: '1fr 1fr 280px', gap: 16 },
  cardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  cardTitle:  { fontSize: 14, fontWeight: 600, color: 'var(--text)' },
  progressTrack: { height: 8, background: 'var(--surface)', borderRadius: 4, overflow: 'hidden' },
  progressBar:   { height: '100%', borderRadius: 4, transition: 'width 0.6s ease, background 0.4s' },
  eventRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '8px 10px',
    background: 'var(--bg3)',
    borderRadius: 8
  }
}
