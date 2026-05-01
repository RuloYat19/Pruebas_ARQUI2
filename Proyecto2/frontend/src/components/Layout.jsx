import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const NAV = [
  { to: '/dashboard',            label: 'Tiempo Real',  icon: IconLive },
  { to: '/dashboard/usuarios',   label: 'Usuarios RFID', icon: IconUsers },
  { to: '/dashboard/estadisticas', label: 'Estadísticas', icon: IconStats },
]

export default function Layout({ children, connected }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div style={styles.root}>
      <aside style={styles.sidebar}>
        <div style={styles.brand}>
          <div style={styles.brandIcon} />
          <span style={styles.brandText}>
            Park <span style={{ color: 'var(--accent)' }}>Guard</span>
          </span>
        </div>

        <div style={styles.mqttStatus}>
          <span className={`dot ${connected ? 'dot-green pulse' : 'dot-red'}`} />
          <span style={{ fontSize: 12, color: 'var(--text3)' }}>
            {connected ? 'MQTT conectado' : 'Sin conexión'}
          </span>
        </div>

        <nav style={styles.nav}>
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/dashboard'}
              style={({ isActive }) => ({
                ...styles.navItem,
                ...(isActive ? styles.navItemActive : {})
              })}
            >
              <Icon size={17} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div style={styles.footer}>
          <div style={styles.userInfo}>
            <div style={styles.avatar}>{user?.username?.[0]?.toUpperCase() ?? 'A'}</div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 500 }}>{user?.username ?? 'Admin'}</div>
              <div style={{ fontSize: 11, color: 'var(--text3)' }}>Administrador</div>
            </div>
          </div>
          <button className="btn btn-ghost" style={{ width: '100%', justifyContent: 'center', marginTop: 8 }} onClick={handleLogout}>
            Cerrar sesión
          </button>
        </div>
      </aside>

      <main style={styles.main}>{children}</main>
    </div>
  )
}

const styles = {
  root:   { display: 'flex', minHeight: '100vh' },
  main:   { flex: 1, minWidth: 0, overflowY: 'auto' },
  sidebar: {
    width: 220,
    flexShrink: 0,
    background: 'var(--bg2)',
    borderRight: '1px solid var(--border)',
    display: 'flex',
    flexDirection: 'column',
    padding: '24px 16px',
    gap: 6,
    position: 'sticky',
    top: 0,
    height: '100vh',
    overflowY: 'auto'
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginBottom: 20,
    paddingLeft: 4
  },
  brandIcon: {
    width: 26,
    height: 26,
    borderRadius: 6,
    background: 'var(--accent)',
  },
  brandText: {
    fontFamily: 'var(--font-head)',
    fontSize: 18,
    fontWeight: 800
  },
  mqttStatus: {
    display: 'flex',
    alignItems: 'center',
    gap: 7,
    padding: '7px 10px',
    background: 'var(--bg3)',
    borderRadius: 8,
    marginBottom: 16
  },
  nav:  { flex: 1, display: 'flex', flexDirection: 'column', gap: 2 },
  navItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '10px 12px',
    borderRadius: 9,
    color: 'var(--text2)',
    fontSize: 14,
    fontWeight: 500,
    transition: 'all 0.15s'
  },
  navItemActive: {
    background: 'rgba(61,127,255,0.12)',
    color: 'var(--accent)'
  },
  footer: { marginTop: 'auto' },
  userInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '10px 4px',
    borderTop: '1px solid var(--border)',
    marginBottom: 4
  },
  avatar: {
    width: 34,
    height: 34,
    borderRadius: 8,
    background: 'var(--surface)',
    border: '1px solid var(--border2)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 600,
    fontSize: 14,
    flexShrink: 0
  }
}

function IconLive({ size = 18 }) {
  return (
    <svg width={size} height={size} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" d="M3.5 12a8.5 8.5 0 1117 0 8.5 8.5 0 01-17 0z" />
      <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" />
    </svg>
  )
}
function IconUsers({ size = 18 }) {
  return (
    <svg width={size} height={size} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" />
    </svg>
  )
}
function IconStats({ size = 18 }) {
  return (
    <svg width={size} height={size} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 3v18h18M7 16l4-4 4 4 4-6" />
    </svg>
  )
}
