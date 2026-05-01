import React, { createContext, useContext, useState, useEffect } from 'react'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const verifySession = async () => {
    try {
      const res = await fetch('/api/auth/me', {
        credentials: 'include'
      })

      if (!res.ok) {
        setUser(null)
        return false
      }

      const data = await res.json()
      setUser(data.user || null)
      return true
    } catch {
      setUser(null)
      return false
    }
  }

  useEffect(() => {
    const restoreSession = async () => {
      await verifySession()
      setLoading(false)
    }

    restoreSession()
  }, [])

  useEffect(() => {
    if (loading) return

    const onFocus = () => {
      verifySession()
    }

    const intervalId = setInterval(() => {
      verifySession()
    }, 10000)

    window.addEventListener('focus', onFocus)

    return () => {
      clearInterval(intervalId)
      window.removeEventListener('focus', onFocus)
    }
  }, [loading])

  const login = async (username, password) => {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username, password })
    })
    if (!res.ok) throw new Error('Credenciales incorrectas')
    const data = await res.json()
    setUser(data.user)
  }

  const logout = async () => {
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include'
      })
    } catch {
      // Ignorado para no bloquear el cierre de sesión local
    }
    setUser(null)
  }

  const getToken = () => null

  return (
    <AuthContext.Provider value={{ user, login, logout, getToken, verifySession, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)