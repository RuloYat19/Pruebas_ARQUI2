import { useEffect, useRef, useState, useCallback } from 'react'
import mqtt from 'mqtt'

const BROKER_WS = import.meta.env.VITE_MQTT_BROKER_WS || 'ws://localhost:9001'

const TOPICS = [
  '/parkguard/occupancy/change',
  '/parkguard/access/response',
  '/parkguard/status/gas',
  '/parkguard/actuadores/#',
  '/parkguard/fan/control',
  '/parkguard/emergency/command',
  '/parkguard/exit/command',
  '/parkguard/space/status',
  '/parkguard/registration/status',
  '/parkguard/registration/result',
  '/parkguard/users/list/response',
  '/parkguard/users/toggle/response',
  '/parkguard/users/delete/response',
  '/parkguard/users/update/response',
  '/parkguard/stats/response'
]

export function useMQTT() {
  const clientRef = useRef(null)
  const [connected, setConnected] = useState(false)
  const [state, setState] = useState({
    espacios: {},
    gasLevel: 0,
    ventilador: false,
    emergencia: false,
    talanqueraEntrada: false,
    talanqueraSalida: false,
    eventos: [],
    alertas: [],
    registration: {
      active: false,
      waitingCard: false,
      message: ''
    },
    registrationResult: null,
    users: [],
    usersOps: {
      lastToggle: null,
      lastDelete: null,
      lastUpdate: null
    },
    stats: {
      ingresos: [],
      espacios: [],
      gas: [],
      resumen: {
        ingresos: 0,
        salidas: 0,
        emergencias: 0,
        ventilador: 0,
        sospechosas: 0
      },
      alertas: []
    }
  })

  useEffect(() => {
    const client = mqtt.connect(BROKER_WS, {
      clientId: `pg-frontend-${Math.random().toString(16).slice(2, 8)}`,
      clean: true,
      reconnectPeriod: 3000
    })

    client.on('connect', () => {
      setConnected(true)
      TOPICS.forEach(t => client.subscribe(t))
    })

    client.on('disconnect', () => setConnected(false))
    client.on('error', () => setConnected(false))

    client.on('message', (topic, payload) => {
      try {
        const msg = JSON.parse(payload.toString())

        setState(prev => {
          const next = { ...prev }

          if (topic.endsWith('/occupancy/change')) {
            const spaceKey = `E${msg.space_id}`
            const prevSpace = prev.espacios[spaceKey] || {}
            next.espacios = {
              ...prev.espacios,
              [spaceKey]: {
                estado: msg.status === 'free' ? 'libre' : 'ocupado',
                habilitado: prevSpace.habilitado ?? true
              }
            }
            next.eventos = [
              {
                id: Date.now(),
                ts: new Date().toISOString(),
                topic,
                tipo: 'ocupacion',
                mensaje: `Espacio ${msg.space_id}: ${msg.status === 'free' ? 'libre' : 'ocupado'}`
              },
              ...prev.eventos
            ].slice(0, 50)
          } else if (topic.endsWith('/status/gas')) {
            next.gasLevel = Number(msg.value ?? 0)
          } else if (topic.endsWith('/actuadores/ventilador')) {
            next.ventilador = !!msg.estado
          } else if (topic.endsWith('/actuadores/emergencia')) {
            next.emergencia = !!msg.estado
          } else if (topic.endsWith('/actuadores/talanquera-entrada')) {
            next.talanqueraEntrada = !!msg.estado
          } else if (topic.endsWith('/actuadores/talanquera-salida')) {
            next.talanqueraSalida = !!msg.estado
          } else if (topic.endsWith('/fan/control')) {
            next.ventilador = msg.action === 'on'
            next.eventos = [
              {
                id: Date.now(),
                ts: new Date().toISOString(),
                topic,
                tipo: 'control',
                mensaje: `Ventilador ${msg.action === 'on' ? 'encendido' : 'apagado'}`
              },
              ...prev.eventos
            ].slice(0, 50)
          } else if (topic.endsWith('/emergency/command')) {
            next.emergencia = msg.action === 'activate'
            next.eventos = [
              {
                id: Date.now(),
                ts: new Date().toISOString(),
                topic,
                tipo: 'emergencia',
                mensaje: msg.action === 'activate' ? 'Emergencia activada' : 'Emergencia desactivada'
              },
              ...prev.eventos
            ].slice(0, 50)
          } else if (topic.endsWith('/exit/command')) {
            next.talanqueraSalida = msg.action === 'open'
            next.eventos = [
              {
                id: Date.now(),
                ts: new Date().toISOString(),
                topic,
                tipo: 'salida',
                mensaje: msg.action === 'open' ? 'Talanquera de salida abierta' : 'Comando de salida recibido'
              },
              ...prev.eventos
            ].slice(0, 50)
          } else if (topic.endsWith('/space/status')) {
            const spaceKey = `E${msg.space_id}`
            const prevSpace = prev.espacios[spaceKey] || { estado: 'libre' }
            const enabled = !!msg.enabled
            next.espacios = {
              ...prev.espacios,
              [spaceKey]: {
                ...prevSpace,
                habilitado: enabled
              }
            }
            next.eventos = [
              {
                id: Date.now(),
                ts: new Date().toISOString(),
                topic,
                tipo: 'parqueo',
                mensaje: `Espacio ${msg.space_id} ${enabled ? 'habilitado' : 'deshabilitado'}`
              },
              ...prev.eventos
            ].slice(0, 50)
          } else if (topic.endsWith('/registration/status')) {
            next.registration = {
              active: msg.ok === true,
              waitingCard: msg.state === 'waiting_card',
              message: msg.message || ''
            }
          } else if (topic.endsWith('/registration/result')) {
            next.registrationResult = {
              ...msg,
              ts: new Date().toISOString()
            }
            next.registration = {
              active: false,
              waitingCard: false,
              message: msg.message || ''
            }

            next.eventos = [
              {
                id: Date.now(),
                ts: new Date().toISOString(),
                topic,
                tipo: msg.ok ? 'registro' : 'error',
                mensaje: msg.message || (msg.ok ? 'Tarjeta registrada' : 'Error de registro')
              },
              ...prev.eventos
            ].slice(0, 50)
          } else if (topic.endsWith('/users/list/response')) {
            if (msg.ok) {
              next.users = Array.isArray(msg.users) ? msg.users : []
            }
          } else if (topic.endsWith('/users/toggle/response')) {
            next.usersOps = {
              ...prev.usersOps,
              lastToggle: {
                ...msg,
                ts: new Date().toISOString()
              }
            }

            if (msg.ok && msg.user) {
              next.users = prev.users.map(u => u._id === msg.user._id ? msg.user : u)
            }
          } else if (topic.endsWith('/users/delete/response')) {
            next.usersOps = {
              ...prev.usersOps,
              lastDelete: {
                ...msg,
                ts: new Date().toISOString()
              }
            }

            if (msg.ok && msg.user_id) {
              next.users = prev.users.filter(u => u._id !== msg.user_id)
            }
          } else if (topic.endsWith('/users/update/response')) {
            next.usersOps = {
              ...prev.usersOps,
              lastUpdate: {
                ...msg,
                ts: new Date().toISOString()
              }
            }

            if (msg.ok && msg.user) {
              next.users = prev.users.map(u => u._id === msg.user._id ? msg.user : u)
            }
          }

          if (topic.endsWith('/access/response')) {
            next.eventos = [
              {
                id: Date.now(),
                ts: new Date().toISOString(),
                topic,
                tipo: msg.granted ? 'autorizado' : 'denegado',
                mensaje: msg.message || (msg.granted ? 'Acceso permitido' : 'Acceso denegado')
              },
              ...prev.eventos
            ].slice(0, 50)

            if (msg.alert && msg.alert.type === 'suspicious') {
              next.alertas = [
                {
                  id: `${Date.now()}-${msg.alert.rfid}`,
                  ts: msg.alert.timestamp || new Date().toISOString(),
                  tipo: 'sospechosa',
                  mensaje: msg.alert.message || `Actividad sospechosa detectada para ${msg.alert.rfid}`,
                  rfid: msg.alert.rfid,
                  attempts: msg.alert.attempts
                },
                ...prev.alertas
              ].slice(0, 20)

              next.eventos = [
                {
                  id: Date.now() + 1,
                  ts: new Date().toISOString(),
                  topic: '/parkguard/alerts/suspicious',
                  tipo: 'alerta',
                  mensaje: msg.alert.message || `Actividad sospechosa detectada para ${msg.alert.rfid}`
                },
                ...next.eventos
              ].slice(0, 50)
            }
          }

          if (topic.endsWith('/stats/response')) {
            if (msg.ok) {
              next.stats = {
                ingresos: Array.isArray(msg.ingresos) ? msg.ingresos : [],
                espacios: Array.isArray(msg.espacios) ? msg.espacios : [],
                gas: Array.isArray(msg.gas) ? msg.gas : [],
                resumen: {
                  ingresos: Number(msg?.resumen?.ingresos || 0),
                  salidas: Number(msg?.resumen?.salidas || 0),
                  emergencias: Number(msg?.resumen?.emergencias || 0),
                  ventilador: Number(msg?.resumen?.ventilador || 0),
                  sospechosas: Number(msg?.resumen?.sospechosas || 0)
                },
                alertas: Array.isArray(msg.alertas) ? msg.alertas : []
              }
            }
          }

          return next
        })
      } catch (_) {}
    })

    clientRef.current = client
    return () => client.end()
  }, [])

  const publish = useCallback((topic, payload) => {
    if (!clientRef.current) return

    if (topic.endsWith('/actuadores/ventilador')) {
      clientRef.current.publish(
        '/parkguard/fan/command',
        JSON.stringify({ action: payload.estado ? 'on' : 'off', source: 'frontend' })
      )
      return
    }

    if (topic.endsWith('/actuadores/emergencia')) {
      clientRef.current.publish(
        '/parkguard/emergency/trigger',
        JSON.stringify({ triggered: !!payload.estado, gas_level: payload.estado ? 100 : 0 })
      )
      return
    }

    if (topic.endsWith('/registration/start')) {
      clientRef.current.publish('/parkguard/registration/start', JSON.stringify(payload))
      return
    }

    if (topic.endsWith('/users/list/request')) {
      clientRef.current.publish('/parkguard/users/list/request', JSON.stringify(payload || {}))
      return
    }

    if (topic.endsWith('/users/toggle/request')) {
      clientRef.current.publish('/parkguard/users/toggle/request', JSON.stringify(payload || {}))
      return
    }

    if (topic.endsWith('/users/delete/request')) {
      clientRef.current.publish('/parkguard/users/delete/request', JSON.stringify(payload || {}))
      return
    }

    if (topic.endsWith('/users/update/request')) {
      clientRef.current.publish('/parkguard/users/update/request', JSON.stringify(payload || {}))
      return
    }

    if (topic.endsWith('/stats/request')) {
      clientRef.current.publish('/parkguard/stats/request', JSON.stringify(payload || {}))
      return
    }

    const normalizedTopic = topic.startsWith('/') ? topic : `/${topic}`
    clientRef.current.publish(normalizedTopic, JSON.stringify(payload))
  }, [])

  return { connected, state, publish }
}
