import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate  = useNavigate()
  const [form, setForm]     = useState({ username: '', password: '' })
  const [error, setError]   = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(form.username, form.password)
      navigate('/dashboard')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.root}>
      <div style={styles.bg} />
      <div style={styles.card} className="fade-in">
        <div style={styles.logo}>
          <div style={styles.logoIcon} />
          <span style={styles.logoText}>Park<span style={{ color: 'var(--accent)' }}>Guard</span></span>
          <span style={styles.version}>2.0</span>
        </div>

        <p style={styles.subtitle}>Sistema IoT de gestión de parqueos</p>

        <form onSubmit={handleSubmit} style={styles.form}>
          <div>
            <label>Usuario</label>
            <input
              className="input"
              type="text"
              placeholder="admin"
              value={form.username}
              onChange={e => setForm(p => ({ ...p, username: e.target.value }))}
              required
            />
          </div>
          <div>
            <label>Contraseña</label>
            <input
              className="input"
              type="password"
              placeholder="••••••••"
              value={form.password}
              onChange={e => setForm(p => ({ ...p, password: e.target.value }))}
              required
            />
          </div>

          {error && <p style={styles.error}>{error}</p>}

          <button
            className="btn btn-primary"
            type="submit"
            disabled={loading}
            style={{ width: '100%', justifyContent: 'center', padding: '12px' }}
          >
            {loading ? 'Ingresando...' : 'Ingresar'}
          </button>
        </form>
      </div>
    </div>
  )
}

const styles = {
  root: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
    overflow: 'hidden'
  },
  bg: {
    position: 'fixed',
    inset: 0,
    background: 'radial-gradient(ellipse 80% 60% at 50% -10%, rgba(61,127,255,0.15) 0%, transparent 70%)',
    pointerEvents: 'none'
  },
  card: {
    background: 'var(--bg2)',
    border: '1px solid var(--border)',
    borderRadius: 20,
    padding: '40px 36px',
    width: '100%',
    maxWidth: 400,
    boxShadow: '0 32px 80px rgba(0,0,0,0.6)',
    zIndex: 1
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    marginBottom: 6
  },
  logoIcon: {
    width: 32,
    height: 32,
    borderRadius: 8,
    background: 'var(--accent)',
  },
  logoText: {
    fontFamily: 'var(--font-head)',
    fontSize: 22,
    fontWeight: 800,
    color: 'var(--text)'
  },
  version: {
    background: 'var(--surface)',
    color: 'var(--text3)',
    fontSize: 11,
    padding: '2px 7px',
    borderRadius: 6,
    fontFamily: 'var(--font-mono)'
  },
  subtitle: {
    color: 'var(--text3)',
    fontSize: 13,
    marginBottom: 28
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16
  },
  error: {
    color: 'var(--red)',
    fontSize: 13,
    background: 'rgba(239,68,68,0.08)',
    padding: '8px 12px',
    borderRadius: 8
  }
}