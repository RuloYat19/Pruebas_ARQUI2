from pymongo import MongoClient
from pymongo import ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database
from bson import ObjectId
from bson.errors import InvalidId
import os
from typing import Dict, Any
from datetime import datetime, timedelta
from utils.logger import setup_logger

logger = setup_logger(__name__)

class MongoDBClient:
    def __init__(self):
        self.mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
        self.db_name = os.getenv("MONGO_DB", "parkguard_db")
        self.client: MongoClient = None
        self.db: Database = None
        
        # Colecciones
        self.users: Collection = None
        self.events: Collection = None
        self.spaces: Collection = None
        self.logs: Collection = None
        self.stats: Collection = None
    
    def connect(self):
        # Se establece la conexión con MongoDB
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client[self.db_name]
            
            # Se inicializan las colecciones
            self.users = self.db["users"]
            self.events = self.db["events"]
            self.spaces = self.db["spaces"]
            self.logs = self.db["logs"]
            self.stats = self.db["statistics"]
            
            # Se crean los índices
            self._create_indexes()
            
            logger.info(f"Se ha conectado a MongoDB con éxito: {self.db_name}")
            return True
        except Exception as e:
            logger.error(f"Hubo problemas conectando a MongoDB: {e}")
            return False
    
    def _create_indexes(self):
        # Se crean índices para poder optimizar las consultas
        self.events.create_index("timestamp")
        self.events.create_index("type")
        self.events.create_index([("user_id", 1), ("timestamp", -1)])
        
        self.users.create_index("rfid", unique=True)
        self.users.create_index("card_id", unique=True)
        
        self.spaces.create_index("space_id", unique=True)
    
    def insert_event(self, event: Dict[str, Any]) -> bool:
        # Se inserta un evento a la colección que le corresponde
        try:
            # Se agrega la metadata
            event["_id"] = f"{event['type']}_{datetime.utcnow().timestamp()}"
            
            result = self.events.insert_one(event)
            logger.debug(f"Evento insertado: {event['type']}")
            return True
        except Exception as e:
            logger.error(f"Hubo problemas al insertar un evento: {e}")
            return False
    
    def get_user_by_rfid(self, rfid: str) -> Dict[str, Any]:
        # Se busca un usuario por su RFID
        try:
            user = self.users.find_one({"rfid": rfid, "active": True})
            return user
        except Exception as e:
            logger.error(f"Hubo problemas al buscar un usuario {rfid}: {e}")
            return None

    def get_user_by_rfid_any(self, rfid: str) -> Dict[str, Any]:
        # Se busca un usuario por su RFID sin importar si está activo o no
        try:
            return self.users.find_one({"rfid": rfid})
        except Exception as e:
            logger.error(f"Hubo problemas al buscar un usuario por RFID {rfid}: {e}")
            return None

    def get_user_by_plate(self, plate: str) -> Dict[str, Any]:
        # Se busca un usuario por una placa vehicular asociada
        try:
            plate_clean = str(plate).strip().upper()
            if not plate_clean:
                return None
            return self.users.find_one({"placas": plate_clean})
        except Exception as e:
            logger.error(f"Hubo problemas al buscar un usuario por placa {plate}: {e}")
            return None

    def create_user(self, name: str, rfid: str, balance: float = 0, active: bool = True, placas: list = None) -> Dict[str, Any]:
        # Se crea un usuario nuevo para registro por RFID
        try:
            placas = placas if isinstance(placas, list) else []
            placas = [str(placa).strip().upper() for placa in placas if str(placa).strip()]
            doc = {
                "name": name,
                "nombre": name,
                "rfid": rfid,
                "card_id": rfid,
                "balance": float(balance),
                "saldo": float(balance),
                "active": bool(active),
                "activo": bool(active),
                "placas": placas,
                "created_at": datetime.utcnow().isoformat()
            }
            result = self.users.insert_one(doc)
            doc["_id"] = str(result.inserted_id)
            return doc
        except Exception as e:
            logger.error(f"Hubo problemas al crear usuario RFID: {e}")
            return None

    def update_user_balance(self, user_id: str, new_balance: float) -> Dict[str, Any]:
        # Se actualiza el saldo del usuario luego de un acceso
        try:
            safe_balance = max(0.0, float(new_balance))
            result = self.users.find_one_and_update(
                {"_id": ObjectId(user_id)},
                {"$set": {"saldo": safe_balance, "balance": safe_balance}},
                return_document=ReturnDocument.AFTER
            )
            if not result:
                return None
            return {
                "_id": str(result.get("_id")),
                "nombre": result.get("nombre", result.get("name", "Sin nombre")),
                "rfid": result.get("rfid", result.get("card_id", "")),
                "saldo": float(result.get("saldo", result.get("balance", 0)) or 0),
                "activo": bool(result.get("activo", result.get("active", True))),
                "placas": list(result.get("placas", []))
            }
        except Exception as e:
            logger.error(f"Hubo problemas actualizando saldo de usuario {user_id}: {e}")
            return None

    def list_users(self) -> list:
        # Se listan todos los usuarios para frontend
        try:
            docs = list(self.users.find({}).sort("created_at", -1))
            out = []
            for doc in docs:
                placas = doc.get("placas", [])
                if not isinstance(placas, list):
                    placas = []
                out.append({
                    "_id": str(doc.get("_id")),
                    "nombre": doc.get("nombre", doc.get("name", "Sin nombre")),
                    "rfid": doc.get("rfid", doc.get("card_id", "")),
                    "saldo": float(doc.get("saldo", doc.get("balance", 0)) or 0),
                    "activo": bool(doc.get("activo", doc.get("active", True))),
                    "placas": placas
                })
            return out
        except Exception as e:
            logger.error(f"Hubo problemas listando usuarios: {e}")
            return []

    def set_user_active(self, user_id: str, active: bool) -> Dict[str, Any]:
        # Se activa o desactiva un usuario
        try:
            result = self.users.find_one_and_update(
                {"_id": ObjectId(user_id)},
                {"$set": {"active": bool(active), "activo": bool(active)}},
                return_document=ReturnDocument.AFTER
            )
            if not result:
                return None
            return {
                "_id": str(result.get("_id")),
                "nombre": result.get("nombre", result.get("name", "Sin nombre")),
                "rfid": result.get("rfid", result.get("card_id", "")),
                "saldo": float(result.get("saldo", result.get("balance", 0)) or 0),
                "activo": bool(result.get("activo", result.get("active", True))),
                "placas": list(result.get("placas", []))
            }
        except Exception as e:
            logger.error(f"Hubo problemas cambiando estado de usuario {user_id}: {e}")
            return None

    def update_user_profile(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        # Se actualiza el perfil de usuario (nombre, RFID, saldo, estado)
        try:
            target_id = ObjectId(user_id)
        except (InvalidId, TypeError):
            logger.error(f"ID de usuario inválido para actualización: {user_id}")
            return None

        try:
            patch = {}

            if "nombre" in updates or "name" in updates:
                nombre = str(updates.get("nombre", updates.get("name", ""))).strip()
                if nombre:
                    patch["nombre"] = nombre
                    patch["name"] = nombre

            if "rfid" in updates or "card_id" in updates:
                rfid = str(updates.get("rfid", updates.get("card_id", ""))).strip().upper()
                if rfid:
                    duplicate = self.users.find_one({"rfid": rfid, "_id": {"$ne": target_id}})
                    if duplicate is not None:
                        logger.warning(f"RFID duplicado en actualización: {rfid}")
                        return {"error": "RFID ya está en uso"}
                    patch["rfid"] = rfid
                    patch["card_id"] = rfid

            if "saldo" in updates or "balance" in updates:
                saldo = max(0.0, float(updates.get("saldo", updates.get("balance", 0)) or 0))
                patch["saldo"] = saldo
                patch["balance"] = saldo

            if "activo" in updates or "active" in updates:
                activo = bool(updates.get("activo", updates.get("active", True)))
                patch["activo"] = activo
                patch["active"] = activo

            if "placas" in updates:
                placas = updates.get("placas", [])
                if isinstance(placas, list):
                    patch["placas"] = [str(placa).strip().upper() for placa in placas if str(placa).strip()]
                logger.info(f"🚗 PLACAS UPDATE - Input: {placas} → Normalized: {patch.get('placas')}")

            if not patch:
                logger.warning(f"⚠️ UPDATE PROFILE - Patch vacío para {user_id}, updates recibidas: {updates}")
                return None

            logger.info(f"📝 PATCH FINAL - user_id: {user_id}, patch keys: {list(patch.keys())}, placas en patch: {patch.get('placas')}")
            result = self.users.find_one_and_update(
                {"_id": target_id},
                {"$set": patch},
                return_document=ReturnDocument.AFTER
            )
            if not result:
                return None
            return {
                "_id": str(result.get("_id")),
                "nombre": result.get("nombre", result.get("name", "Sin nombre")),
                "rfid": result.get("rfid", result.get("card_id", "")),
                "saldo": float(result.get("saldo", result.get("balance", 0)) or 0),
                "activo": bool(result.get("activo", result.get("active", True))),
                "placas": list(result.get("placas", []))
            }
        except Exception as e:
            logger.error(f"Hubo problemas actualizando perfil de usuario {user_id}: {e}")
            return None

    def delete_user(self, user_id: str) -> bool:
        # Se elimina un usuario
        try:
            result = self.users.delete_one({"_id": ObjectId(user_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Hubo problemas eliminando usuario {user_id}: {e}")
            return False

    def delete_all_users(self) -> int:
        # Se eliminan todos los usuarios
        try:
            result = self.users.delete_many({})
            return int(result.deleted_count)
        except Exception as e:
            logger.error(f"Hubo problemas eliminando todos los usuarios: {e}")
            return 0
    
    def update_space_status(self, space_id: int, status: str) -> bool:
        # Se actualiza el estado de un espacio en el parqueo
        try:
            self.spaces.update_one(
                {"space_id": space_id},
                {
                    "$set": {
                        "status": status,
                        "last_updated": datetime.utcnow().isoformat()
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Hubo problemas al actualizar un espacio del parqueo {space_id}: {e}")
            return False
    
    def log_suspicious_activity(self, rfid: str, details: Dict[str, Any]) -> bool:
        # Se registra una actividad sospechosa
        try:
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "rfid": rfid,
                "type": "suspicious_activity",
                "details": details
            }
            self.logs.insert_one(log_entry)
            return True
        except Exception as e:
            logger.error(f"Hubo problemas al registrar la actividad sospechosa: {e}")
            return False

    def get_dashboard_statistics(self, hours: int = 12) -> Dict[str, Any]:
        # Se construyen métricas para dashboard de estadísticas y reportes
        try:
            now = datetime.utcnow()
            start = now - timedelta(hours=hours - 1)

            # Usar agrupación por hora, día o semana según el rango
            if hours <= 48:
                grouping = "hour"
                interval = timedelta(hours=1)
            elif hours <= 720:  # 30 días
                grouping = "day"
                interval = timedelta(days=1)
            else:
                grouping = "week"
                interval = timedelta(days=7)

            hourly_labels = []
            hourly_map = {}
            
            if grouping == "hour":
                for i in range(hours):
                    bucket = start + timedelta(hours=i)
                    label = bucket.strftime("%H:00")
                    hourly_labels.append(label)
                    if label not in hourly_map:
                        hourly_map[label] = {
                            "hora": label,
                            "ingresos": 0,
                            "salidas": 0,
                            "gas": 0
                        }
            elif grouping == "day":
                current = start.replace(hour=0, minute=0, second=0, microsecond=0)
                while current <= now:
                    label = current.strftime("%d/%m")
                    hourly_labels.append(label)
                    hourly_map[label] = {
                        "hora": label,
                        "ingresos": 0,
                        "salidas": 0,
                        "gas": 0
                    }
                    current += timedelta(days=1)
            else:  # week
                current = start.replace(hour=0, minute=0, second=0, microsecond=0)
                while current <= now:
                    end_week = current + timedelta(days=6)
                    label = f"{current.strftime('%d/%m')} - {end_week.strftime('%d/%m')}"
                    hourly_labels.append(label)
                    hourly_map[label] = {
                        "hora": label,
                        "ingresos": 0,
                        "salidas": 0,
                        "gas": 0
                    }
                    current += timedelta(days=7)

            events = list(self.events.find({}).sort("timestamp", -1).limit(10000))
            usos_por_espacio = {}
            emergencias = 0
            ventilador_on = 0
            suspicious_count = 0
            recent_alerts = []

            for event in events:
                ts_raw = event.get("timestamp")
                if not ts_raw:
                    continue

                try:
                    ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")).replace(tzinfo=None)
                except Exception:
                    continue

                if ts < start or ts > now + timedelta(minutes=5):
                    continue

                event_type = event.get("type")
                
                # Determinar la etiqueta hora según el tipo de agrupación
                if grouping == "hour":
                    hour_label = ts.strftime("%H:00")
                elif grouping == "day":
                    hour_label = ts.strftime("%d/%m")
                else:  # week
                    week_start = ts - timedelta(days=ts.weekday())
                    week_end = week_start + timedelta(days=6)
                    hour_label = f"{week_start.strftime('%d/%m')} - {week_end.strftime('%d/%m')}"
                
                in_window = hour_label in hourly_map and ts >= start

                if event_type == "access" and bool(event.get("granted", False)):
                    if in_window:
                        hourly_map[hour_label]["ingresos"] += 1

                elif event_type == "exit":
                    if in_window:
                        hourly_map[hour_label]["salidas"] += 1

                elif event_type == "occupancy" and event.get("status") == "occupied":
                    space_id = event.get("space_id")
                    if space_id is not None:
                        usos_por_espacio[space_id] = usos_por_espacio.get(space_id, 0) + 1

                elif event_type == "emergency" and bool(event.get("triggered", False)):
                    emergencias += 1
                    if in_window:
                        hourly_map[hour_label]["gas"] += 1

                elif event_type == "fan" and str(event.get("status", "")).lower() == "on":
                    ventilador_on += 1

                elif event_type == "suspicious":
                    suspicious_count += 1
                    if len(recent_alerts) < 10:
                        recent_alerts.append({
                            "timestamp": event.get("timestamp"),
                            "rfid": event.get("rfid", ""),
                            "attempts": int(event.get("attempts", 0) or 0),
                            "message": f"Actividad sospechosa RFID {event.get('rfid', '')}"
                        })

            ingresos = [hourly_map[label] for label in hourly_labels]
            espacios = [
                {"espacio": f"E{space_id}", "usos": usos}
                for space_id, usos in sorted(usos_por_espacio.items(), key=lambda x: str(x[0]))
            ]

            if not espacios:
                espacios = [{"espacio": f"E{i}", "usos": 0} for i in range(1, 6)]

            resumen = {
                "ingresos": sum(item["ingresos"] for item in ingresos),
                "salidas": sum(item["salidas"] for item in ingresos),
                "emergencias": emergencias,
                "ventilador": ventilador_on,
                "sospechosas": suspicious_count
            }

            return {
                "ok": True,
                "ingresos": ingresos,
                "espacios": espacios,
                "gas": [{"hora": item["hora"], "activaciones": item["gas"]} for item in ingresos],
                "resumen": resumen,
                "alertas": recent_alerts
            }
        except Exception as e:
            logger.error(f"Hubo problemas generando estadísticas del dashboard: {e}")
            return {
                "ok": False,
                "ingresos": [],
                "espacios": [],
                "gas": [],
                "resumen": {
                    "ingresos": 0,
                    "salidas": 0,
                    "emergencias": 0,
                    "ventilador": 0,
                    "sospechosas": 0
                },
                "alertas": []
            }
    
    def close(self):
        # Se cierra la conexión
        if self.client:
            self.client.close()
            logger.info("Conexión a MongoDB cerrada con éxito")