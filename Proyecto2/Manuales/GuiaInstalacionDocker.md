# Guia de Instalacion y Ejecucion en Docker (ParkGuard)

## Objetivo
Esta guia permite levantar el proyecto completo en cualquier maquina del equipo usando Docker.

Servicios incluidos:
- Broker MQTT (Mosquitto)
- Base de datos NoSQL (MongoDB)
- Backend API
- Consumer MQTT
- Frontend

---

## 1. Requisitos previos
Instalar en la maquina:
- Docker Desktop (Windows/Mac) o Docker Engine + Docker Compose (Linux)
- Git

Versiones recomendadas:
- Docker 24+
- Docker Compose v2+

Verificar instalacion en terminal:

```powershell
docker --version
docker compose version
```

---

## 2. Clonar el proyecto

```powershell
git clone <URL_DEL_REPOSITORIO>
cd Proyecto2
```

Si ya tienes el proyecto, solo ubicate en la carpeta raiz donde esta el archivo `docker-compose.yaml`.

---

## 3. Levantar todo el sistema
Desde la raiz del proyecto:

```powershell
docker compose up -d --build
```

Este comando:
- Construye imagenes personalizadas (backend, consumer, frontend)
- Levanta los 5 servicios en contenedores
- Crea la red interna para comunicacion entre servicios

---

## 4. Verificar que todo esta arriba

```powershell
docker compose ps
```

Debes ver en estado `Up`:
- mosquitto
- mongodb
- backend
- consumer
- frontend

Validar backend:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Resultado esperado:

```json
{"status":"ok"}
```

Abrir frontend en navegador:
- http://localhost:3000

Login por defecto:
- Usuario: admin
- Contrasena: admin

---

## 5. Comandos utiles
Parar todo:

```powershell
docker compose down
```

Reiniciar todo:

```powershell
docker compose restart
```

Ver logs de todos los servicios:

```powershell
docker compose logs -f
```

Ver logs de un servicio especifico:

```powershell
docker compose logs -f backend
docker compose logs -f consumer
docker compose logs -f frontend
```

Forzar reconstruccion de imagenes:

```powershell
docker compose up -d --build --force-recreate
```

---

## 6. Puertos usados
- Frontend: 3000
- Backend API: 8000
- MQTT: 1883
- MQTT WebSocket: 9001
- MongoDB: 27017

Si algun puerto esta ocupado, cierra el proceso que lo usa o modifica el mapeo en `docker-compose.yaml`.

---

## 7. Problemas frecuentes
### A) "port is already allocated"
Otro programa usa ese puerto.
- Solucion: liberar puerto o cambiarlo en `docker-compose.yaml`.

### B) Backend no responde en /health
1. Verifica contenedor:
```powershell
docker compose ps backend
```
2. Revisa logs:
```powershell
docker compose logs --tail 100 backend
```
3. Reconstruye backend:
```powershell
docker compose up -d --build backend
```

### C) Frontend no carga
1. Verifica:
```powershell
docker compose ps frontend
```
2. Revisa logs:
```powershell
docker compose logs --tail 100 frontend
```
3. Reconstruye:
```powershell
docker compose up -d --build frontend
```

### D) Cambios no se reflejan
Puede haber cache de imagenes.

```powershell
docker compose down
docker compose up -d --build --force-recreate
```

---

## 8. Flujo recomendado para presentacion
1. Descargar cambios del repo.
2. Ejecutar:

```powershell
docker compose pull
docker compose up -d
```

3. Validar:

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

4. Abrir http://localhost:3000 y hacer login.

---

## 9. Limpieza completa (opcional)
Si quieres borrar contenedores, red y volumen de Mongo:

```powershell
docker compose down -v
```

Esto elimina datos persistidos en MongoDB de este proyecto.
