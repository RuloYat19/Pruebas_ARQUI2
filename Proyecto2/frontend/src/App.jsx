import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { useMQTT } from './hooks/useMQTT'
import ProtectedRoute from './components/ProtectedRoute'
import Layout from './components/Layout'
import Login from './pages/Login'
import RealTime from './pages/RealTime'
import Usuarios from './pages/Usuarios'
import Estadisticas from './pages/Estadisticas'

function Dashboard() {
  const { connected, state, publish } = useMQTT()

  return (
    <Layout connected={connected}>
      <Routes>
        <Route index            element={<RealTime state={state} publish={publish} connected={connected} />} />
        <Route path="usuarios"  element={<Usuarios state={state} publish={publish} connected={connected} />} />
        <Route path="estadisticas" element={<Estadisticas state={state} publish={publish} connected={connected} />} />
      </Routes>
    </Layout>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/dashboard/*"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  )
}