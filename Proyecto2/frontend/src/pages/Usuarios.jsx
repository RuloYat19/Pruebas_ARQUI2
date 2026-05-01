import React, { useState, useEffect, useRef } from 'react'
import { useAuth } from '../context/AuthContext'

const EMPTY_FORM = { nombre: '', rfid: '', saldo: 0, activo: true, placas: [] }

const normalizeUser = (u) => ({
  _id: String(u?._id ?? u?.id ?? ''),
  nombre: u?.nombre ?? u?.name ?? 'Sin nombre',
  rfid: String(u?.rfid ?? u?.card_id ?? ''),
  saldo: Number(u?.saldo ?? u?.balance ?? 0),
  activo: Boolean(u?.activo ?? u?.active ?? true),
  placas: Array.isArray(u?.placas) ? u.placas.map(p => String(p).trim().toUpperCase()).filter(Boolean) : []
})

export default function Usuarios({ state, publish, connected }) {
  const { verifySession } = useAuth()
  const [usuarios, setUsuarios]   = useState([])
  const [loading, setLoading]     = useState(true)
  const [modal, setModal]         = useState(null)
  const [form, setForm]           = useState(EMPTY_FORM)
  const [saving, setSaving]       = useState(false)
  const [search, setSearch]       = useState('')
  const [alertas, setAlertas]     = useState([])
  const [registroMsg, setRegistroMsg] = useState('')
  const [registroError, setRegistroError] = useState('')
  const [editError, setEditError] = useState('')
  const [recarga, setRecarga] = useState(0)
  const [nuevaPlaca, setNuevaPlaca] = useState('')
  const lastRegistrationTsRef = useRef(null)
  const lastUserUpdateTsRef = useRef(null)

  useEffect(() => {
    if (!connected || !publish) return
    publish('/parkguard/users/list/request', {})
  }, [connected, publish])

  useEffect(() => {
    if (!Array.isArray(state?.users)) return
    setUsuarios(state.users.map(normalizeUser))
    setLoading(false)
  }, [state?.users])

  useEffect(() => {
    if (!Array.isArray(state?.alertas)) return
    setAlertas(state.alertas)
  }, [state?.alertas])

  useEffect(() => {
    if (!state?.registration) return
    if (modal !== 'create') return
    setRegistroMsg(state.registration.message || '')
  }, [state?.registration, modal])

  useEffect(() => {
    if (modal !== 'create') return
    if (!state?.registration?.waitingCard) return

    const timer = setTimeout(() => {
      setRegistroError('No se reconocio tarjeta. Acerquela nuevamente o reinicie el modo lector.')
    }, 12000)

    return () => clearTimeout(timer)
  }, [state?.registration?.waitingCard, modal])

  useEffect(() => {
    const result = state?.registrationResult
    if (!result || modal !== 'create') return
    if (lastRegistrationTsRef.current === result.ts) return
    lastRegistrationTsRef.current = result.ts

    if (result.ok && result.user) {
      publish('/parkguard/users/list/request', {})
      setRegistroError('')
      setRegistroMsg(result.message || 'Tarjeta registrada correctamente')
      setModal(null)
      setForm(EMPTY_FORM)
      return
    }

    setRegistroError(result.message || 'No se pudo registrar la tarjeta')
  }, [state?.registrationResult, modal])

  const openCreate = () => {
    setForm(EMPTY_FORM)
    setRecarga(0)
    setNuevaPlaca('')
    setRegistroMsg('')
    setRegistroError('')
    setEditError('')
    setModal('create')
  }
  const openEdit   = (u)  => {
    setForm({ ...EMPTY_FORM, ...u, placas: Array.isArray(u?.placas) ? u.placas : [] })
    setRecarga(0)
    setNuevaPlaca('')
    setEditError('')
    setModal('edit')
  }

  const addPlaca = () => {
    const placa = String(nuevaPlaca || '').trim().toUpperCase()
    if (!placa) return

    if ((Array.isArray(form.placas) ? form.placas : []).includes(placa)) {
      setEditError('La placa ya fue agregada')
      return
    }

    setForm(prev => ({
      ...prev,
      placas: [...(Array.isArray(prev.placas) ? prev.placas : []), placa]
    }))
    setNuevaPlaca('')
    setEditError('')
    setRegistroError('')
  }

  const removePlaca = (placa) => {
    setForm(prev => ({
      ...prev,
      placas: (prev.placas || []).filter(item => item !== placa)
    }))
  }

  const getPlacasParaGuardar = () => {
    const placasActuales = Array.isArray(form.placas) ? form.placas : []
    const placaPendiente = String(nuevaPlaca || '').trim().toUpperCase()

    if (!placaPendiente) {
      return placasActuales
    }

    if (placasActuales.includes(placaPendiente)) {
      return placasActuales
    }

    return [...placasActuales, placaPendiente]
  }

  const startReaderMode = () => {
    if (!publish) return
    if (!verifySession) return
    if (!form.nombre?.trim()) {
      setRegistroError('Debes escribir el nombre antes de iniciar el lector')
      return
    }

    verifySession().then((valid) => {
      if (!valid) {
        setRegistroError('Tu sesión expiró. Inicia sesión nuevamente.')
        return
      }

      setRegistroError('')
      setRegistroMsg('Activando modo lector...')
      const placasParaGuardar = getPlacasParaGuardar()
      console.log('📖 STARTREADERMODE - placasParaGuardar:', placasParaGuardar, 'form.placas:', form.placas, 'nuevaPlaca:', nuevaPlaca)
      publish('/parkguard/registration/start', {
        name: form.nombre.trim(),
        balance: Number(form.saldo || 0),
        active: !!form.activo,
        placas: placasParaGuardar
      })
    })
  }

  const handleSave = async () => {
    if (modal === 'create') {
      await startReaderMode()
      return
    }

    if (modal === 'edit') {
      if (!publish) return
      if (!verifySession) return
      if (!form._id) {
        setEditError('No se pudo identificar el usuario a editar')
        return
      }

      const valid = await verifySession()
      if (!valid) {
        setEditError('Tu sesión expiró. Inicia sesión nuevamente.')
        return
      }

      const saldoFinal = Math.max(0, Number(form.saldo || 0) + Number(recarga || 0))
      const placasParaGuardar = getPlacasParaGuardar()
      console.log('💾 HANDLESA VE - placasParaGuardar:', placasParaGuardar, 'form.placas:', form.placas, 'nuevaPlaca:', nuevaPlaca)
      setSaving(true)
      setEditError('')

      publish('/parkguard/users/update/request', {
        user_id: form._id,
        nombre: String(form.nombre || '').trim(),
        rfid: String(form.rfid || '').trim().toUpperCase(),
        saldo: saldoFinal,
        activo: !!form.activo,
        placas: placasParaGuardar
      })
      return
    }
  }

  useEffect(() => {
    const updateResult = state?.usersOps?.lastUpdate
    if (!updateResult) return
    if (lastUserUpdateTsRef.current === updateResult.ts) return
    lastUserUpdateTsRef.current = updateResult.ts

    setSaving(false)

    if (updateResult.ok) {
      publish('/parkguard/users/list/request', {})
      setModal(null)
      setForm(EMPTY_FORM)
      setRecarga(0)
      setEditError('')
      return
    }

    setEditError(updateResult.message || 'No se pudo guardar los cambios')
  }, [state?.usersOps?.lastUpdate])

  const handleToggle = (u) => {
    if (!publish) return
    if (!verifySession) return

    verifySession().then((valid) => {
      if (!valid) {
        setEditError('Tu sesión expiró. Inicia sesión nuevamente.')
        return
      }

      publish('/parkguard/users/toggle/request', {
        user_id: u._id,
        active: !u.activo
      })
    })
  }

  const handleDelete = (id) => {
    if (!confirm('¿Eliminar este usuario?')) return
    if (!publish) return
    if (!verifySession) return

    verifySession().then((valid) => {
      if (!valid) {
        setEditError('Tu sesión expiró. Inicia sesión nuevamente.')
        return
      }

      publish('/parkguard/users/delete/request', { user_id: id })
    })
  }

  const filtered = usuarios.filter(u =>
    (u.nombre || '').toLowerCase().includes(search.toLowerCase()) ||
    (u.rfid || '').toLowerCase().includes(search.toLowerCase())
  )

  return (
    <>
    <div style={styles.root} className="fade-in">
      <div style={styles.header}>
        <h1 style={styles.title}>Usuarios RFID</h1>
        <button className="btn btn-primary" onClick={openCreate}>+ Nuevo usuario</button>
      </div>

      {alertas.length > 0 && (
        <div style={styles.alertBanner}>
          <span className="dot dot-red pulse" />
          <span style={{ fontSize: 13 }}>
            <strong>{alertas.length}</strong> tarjeta(s) con actividad sospechosa detectada
          </span>
        </div>
      )}

      <div style={{ marginBottom: 16 }}>
        <input
          className="input"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ maxWidth: 340 }}
        />
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <p style={styles.empty}>Cargando...</p>
        ) : filtered.length === 0 ? (
          <p style={styles.empty}>No se encontraron usuarios.</p>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr style={styles.thead}>
                <th>Nombre</th>
                <th>RFID</th>
                <th>Placas</th>
                <th>Saldo</th>
                <th>Estado</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u, i) => {
                const sospechoso = alertas.some(a => a.rfid === u.rfid)
                return (
                  <tr key={u._id ?? i} style={styles.row}>
                    <td style={styles.td}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={styles.avatar}>{(u.nombre?.[0] || '?').toUpperCase()}</div>
                        <div>
                          <div style={{ fontSize: 14, fontWeight: 500 }}>{u.nombre}</div>
                          {sospechoso && (
                            <div style={{ fontSize: 11, color: 'var(--yellow)' }}>Actividad sospechosa</div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td style={styles.td}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text2)' }}>{u.rfid}</span>
                    </td>
                    <td style={styles.td}>
                      {(u.placas || []).length > 0 ? (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {u.placas.map((placa) => (
                            <span key={placa} style={styles.plateChip}>{placa}</span>
                          ))}
                        </div>
                      ) : (
                        <span style={{ color: 'var(--text3)', fontSize: 13 }}>Sin placas</span>
                      )}
                    </td>
                    <td style={styles.td}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>Q{u.saldo?.toFixed(2) ?? '0.00'}</span>
                    </td>
                    <td style={styles.td}>
                      <span className={`badge ${u.activo ? 'badge-green' : 'badge-red'}`}>
                        {u.activo ? 'Activo' : 'Inactivo'}
                      </span>
                    </td>
                    <td style={styles.td}>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button className="btn btn-ghost" style={{ padding: '6px 12px', fontSize: 13 }} onClick={() => openEdit(u)}>Editar</button>
                        <button className="btn btn-ghost" style={{ padding: '6px 12px', fontSize: 13 }} onClick={() => handleToggle(u)}>
                          {u.activo ? 'Desactivar' : 'Activar'}
                        </button>
                        <button className="btn btn-danger" style={{ padding: '6px 12px', fontSize: 13 }} onClick={() => handleDelete(u._id)}>Eliminar</button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

    </div>
      {modal && (
        <div style={styles.overlay} onClick={() => setModal(null)}>
          <div style={styles.modal} onClick={e => e.stopPropagation()} className="fade-in">
            <h2 style={styles.modalTitle}>{modal === 'create' ? 'Nuevo usuario' : 'Editar usuario'}</h2>
            <div style={styles.formGrid}>
              <div>
                <label>Nombre completo</label>
                <input className="input" value={form.nombre} onChange={e => setForm(p => ({ ...p, nombre: e.target.value }))} />
              </div>
              <div>
                <label>ID de tarjeta RFID</label>
                <input
                  className="input"
                  value={form.rfid}
                  onChange={e => setForm(p => ({ ...p, rfid: e.target.value }))}
                  readOnly={modal === 'create'}
                />
              </div>
              <div>
                <label>Saldo (Q)</label>
                <input className="input" type="number" value={form.saldo} onChange={e => setForm(p => ({ ...p, saldo: parseFloat(e.target.value) || 0 }))} />
              </div>
              <div style={{ gridColumn: '1 / -1' }}>
                <label>Placas asociadas</label>
                <div style={{ display: 'flex', gap: 8, marginTop: 6, marginBottom: 10, flexWrap: 'wrap' }}>
                  {(form.placas || []).map((placa) => (
                    <span key={placa} style={styles.plateChip}>
                      {placa}
                      <button
                        type="button"
                        className="btn btn-ghost"
                        style={styles.plateRemove}
                        onClick={() => removePlaca(placa)}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                  {(form.placas || []).length === 0 && (
                    <span style={{ color: 'var(--text3)', fontSize: 13 }}>Sin placas registradas</span>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    className="input"
                    value={nuevaPlaca}
                    onChange={e => setNuevaPlaca(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addPlaca()
                      }
                    }}
                    placeholder="Ej: ABC123"
                    style={{ flex: 1 }}
                  />
                  <button type="button" className="btn btn-ghost" onClick={addPlaca}>
                    Agregar placa
                  </button>
                </div>
              </div>
              {modal === 'edit' && (
                <div>
                  <label>Agregar saldo (Q)</label>
                  <input className="input" type="number" value={recarga} onChange={e => setRecarga(parseFloat(e.target.value) || 0)} />
                </div>
              )}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 20 }}>
                <input type="checkbox" id="activo" checked={form.activo} onChange={e => setForm(p => ({ ...p, activo: e.target.checked }))} />
                <label htmlFor="activo" style={{ margin: 0 }}>Tarjeta activa</label>
              </div>
            </div>
            {modal === 'create' && (
              <div style={{ marginTop: 16 }}>
                <button
                  className="btn btn-primary"
                  onClick={startReaderMode}
                  disabled={!connected || state?.registration?.waitingCard}
                >
                  {state?.registration?.waitingCard ? 'Esperando tarjeta...' : 'Iniciar modo lector RFID'}
                </button>
                {!connected && (
                  <p style={{ color: 'var(--yellow)', fontSize: 12, marginTop: 8 }}>
                    MQTT desconectado, no se puede iniciar el lector.
                  </p>
                )}
                {registroMsg && (
                  <p style={{ color: 'var(--accent)', fontSize: 13, marginTop: 8 }}>
                    {registroMsg}
                  </p>
                )}
                {registroError && (
                  <p style={{ color: 'var(--red)', fontSize: 13, marginTop: 6 }}>
                    {registroError}
                  </p>
                )}
                {modal === 'create' && (form.placas || []).length > 0 && (
                  <p style={{ color: 'var(--text3)', fontSize: 12, marginTop: 8 }}>
                    Placas listas para registrar: {(form.placas || []).join(', ')}
                  </p>
                )}
              </div>
            )}
            {modal === 'edit' && editError && (
              <p style={{ color: 'var(--red)', fontSize: 13, marginTop: 10 }}>
                {editError}
              </p>
            )}
            <div style={{ display: 'flex', gap: 10, marginTop: 20, justifyContent: 'flex-end' }}>
              <button className="btn btn-ghost" onClick={() => setModal(null)}>Cancelar</button>
              <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
                {saving ? 'Guardando...' : 'Guardar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

const styles = {
  root:   { padding: '28px 32px', width: '100%', boxSizing: 'border-box' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 },
  title:  { fontFamily: 'var(--font-head)', fontSize: 26, fontWeight: 800 },
  alertBanner: {
    display: 'flex', alignItems: 'center', gap: 10,
    background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.25)',
    borderRadius: 10, padding: '10px 16px', marginBottom: 16, color: 'var(--yellow)'
  },
  table:  { width: '100%', borderCollapse: 'collapse' },
  thead:  { background: 'var(--bg3)' },
  row:    { borderTop: '1px solid var(--border)' },
  td:     { padding: '14px 18px', fontSize: 14, verticalAlign: 'middle' },
  empty:  { padding: 24, textAlign: 'center', color: 'var(--text3)' },
  avatar: {
    width: 32, height: 32, borderRadius: 8,
    background: 'rgba(61,127,255,0.15)', color: 'var(--accent)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontWeight: 600, fontSize: 13, flexShrink: 0
  },
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100
  },
  modal: {
    background: 'var(--bg2)', border: '1px solid var(--border)',
    borderRadius: 16, padding: 28, width: '100%', maxWidth: 480,
    boxShadow: '0 32px 80px rgba(0,0,0,0.6)'
  },
  modalTitle: { fontFamily: 'var(--font-head)', fontSize: 20, fontWeight: 800, marginBottom: 20 },
  formGrid:   { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 },
  plateChip: {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: '6px 10px', borderRadius: 999,
    background: 'rgba(61,127,255,0.15)', color: 'var(--accent)',
    fontSize: 12, fontFamily: 'var(--font-mono)'
  },
  plateRemove: {
    padding: '0 6px', minWidth: 24, height: 24,
    lineHeight: '22px', borderRadius: 999, fontSize: 14
  }
}
