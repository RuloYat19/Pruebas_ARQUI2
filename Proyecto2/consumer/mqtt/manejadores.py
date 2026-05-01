import json
from datetime import datetime, timedelta
from typing import Dict, Any
from utils.logger import setup_logger
from modelos.esquemas import EventSchema
from baseDeDatos.mongodb import MongoDBClient

logger = setup_logger(__name__)

CAR_TARIFF = 5.0
MOTORCYCLE_TARIFF = 2.5

# Cache simple para detección de alguna actividad sospechosa que suceda
attempt_cache = {}
suspicious_cooldown = {}

class MQTTMessageHandler:
    def __init__(self, db_client: MongoDBClient):
        self.db = db_client
        self.pending_registration = None
    
    def handle_access_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Se procesa la solicitud de acceso RFID
        rfid = payload.get("rfid", "")
        space_available = payload.get("space_available", False)
        
        logger.info(f"La solicitud acceso RFID es: {rfid}")
        
        # Se busca el usuario en la base de datos de Mongo
        user = self.db.get_user_by_rfid_any(rfid)

        denied_reason = ""
        granted = False

        if user is None:
            denied_reason = "Usuario no encontrado"
        elif not bool(user.get("active", user.get("activo", False))):
            denied_reason = "Usuario inactivo"
        elif not space_available:
            denied_reason = "Parqueo sin espacios disponibles"
        else:
            current_balance = float(user.get("saldo", user.get("balance", 0)) or 0)
            if current_balance <= 0:
                denied_reason = "Saldo insuficiente"
            else:
                granted = True

        suspicious_alert = None

        if granted:
            current_balance = float(user.get("saldo", user.get("balance", 0)) or 0)
            new_balance = max(0.0, current_balance - 1.0)
            updated_user = self.db.update_user_balance(str(user.get("_id")), new_balance)

            # El acceso es permitido y no hubo problemas con ello
            response = {
                "granted": True,
                "user_id": str(user.get("_id")),
                "user_name": user.get("nombre", user.get("name", "")),
                "message": "Acceso permitido",
                "balance_remaining": float((updated_user or {}).get("saldo", new_balance))
            }
            
            # Se registra el evento
            event = EventSchema.access_event(
                user_id=str(user.get("_id")),
                rfid=rfid,
                granted=True
            )
            self.db.insert_event(event)

            # Reinicia intentos al tener un acceso válido
            attempt_cache.pop(rfid, None)
            
        else:
            # El acceso es denegado
            response = {
                "granted": False,
                "message": f"Acceso denegado: {denied_reason}",
                "deny_code": "NO_BALANCE" if denied_reason == "Saldo insuficiente" else "GENERIC_DENY"
            }

            suspicious_alert = self._check_suspicious_activity(rfid)
            if suspicious_alert is not None:
                response["alert"] = suspicious_alert

            # Se registra el evento
            event = EventSchema.access_event(
                user_id=str(user.get("_id")) if user else "unknown",
                rfid=rfid,
                granted=False,
                reason=denied_reason
            )
            self.db.insert_event(event)
        
        return response

    def handle_viv_vehicle_detected(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Se procesa la detección vehicular desde VIV usando la placa reconocida
        plate = str(payload.get("placa", payload.get("plate_text", "")) or "").strip().upper()
        vehicle_type = str(payload.get("tipo", payload.get("vehicle_type", "")) or "").strip().lower()
        confidence = float(payload.get("confidence", payload.get("confianza", 0)) or 0)

        if vehicle_type in {"carro", "car", "sedan", "auto"}:
            vehicle_type = "car"
        elif vehicle_type in {"moto", "motorcycle", "motorbike", "bike"}:
            vehicle_type = "motorcycle"

        if not plate or plate == "NO DETECTADA":
            response = {
                "granted": False,
                "message": "Placa no detectada",
                "deny_code": "PLATE_NOT_DETECTED"
            }
            self.db.insert_event(EventSchema.access_event(
                user_id="unknown",
                rfid="",
                granted=False,
                reason="Placa no detectada",
                plate=plate,
                vehicle_type=vehicle_type,
                tariff=0.0,
            ))
            return response

        user = self.db.get_user_by_plate(plate)
        if user is None:
            response = {
                "granted": False,
                "message": "Placa no registrada",
                "deny_code": "PLATE_NOT_FOUND",
                "plate": plate,
                "vehicle_type": vehicle_type,
            }
            self.db.insert_event(EventSchema.access_event(
                user_id="unknown",
                rfid="",
                granted=False,
                reason="Placa no registrada",
                plate=plate,
                vehicle_type=vehicle_type,
                tariff=0.0,
            ))
            return response

        if not bool(user.get("active", user.get("activo", False))):
            response = {
                "granted": False,
                "message": "Usuario inactivo",
                "deny_code": "USER_INACTIVE",
                "plate": plate,
                "vehicle_type": vehicle_type,
            }
            self.db.insert_event(EventSchema.access_event(
                user_id=str(user.get("_id")),
                rfid=str(user.get("rfid", user.get("card_id", ""))),
                granted=False,
                reason="Usuario inactivo",
                plate=plate,
                vehicle_type=vehicle_type,
                tariff=0.0,
            ))
            return response

        tariff = CAR_TARIFF if vehicle_type == "car" else MOTORCYCLE_TARIFF
        current_balance = float(user.get("saldo", user.get("balance", 0)) or 0)

        if current_balance < tariff:
            response = {
                "granted": False,
                "message": "Saldo insuficiente",
                "deny_code": "NO_BALANCE",
                "plate": plate,
                "vehicle_type": vehicle_type,
                "tariff": tariff,
            }
            self.db.insert_event(EventSchema.access_event(
                user_id=str(user.get("_id")),
                rfid=str(user.get("rfid", user.get("card_id", ""))),
                granted=False,
                reason="Saldo insuficiente",
                plate=plate,
                vehicle_type=vehicle_type,
                tariff=tariff,
            ))
            return response

        new_balance = max(0.0, current_balance - tariff)
        updated_user = self.db.update_user_balance(str(user.get("_id")), new_balance)

        response = {
            "granted": True,
            "user_id": str(user.get("_id")),
            "user_name": user.get("nombre", user.get("name", "")),
            "message": f"Acceso permitido - Cobrado {tariff:.2f}",
            "plate": plate,
            "vehicle_type": vehicle_type,
            "tariff": tariff,
            "balance_remaining": float((updated_user or {}).get("saldo", new_balance))
        }

        event = EventSchema.access_event(
            user_id=str(user.get("_id")),
            rfid=str(user.get("rfid", user.get("card_id", ""))),
            granted=True,
            plate=plate,
            vehicle_type=vehicle_type,
            tariff=tariff,
        )
        self.db.insert_event(event)
        return response
    
    def handle_occupancy_change(self, payload: Dict[str, Any]) -> None:
        # Se procesa el cambio de ocupación en los espacios del parqueo
        space_id = payload.get("space_id")
        status = payload.get("status")  # "occupied" o "free"
        
        logger.info(f"🅿️ Espacio {space_id}: {status}")
        
        # Se actualiza la base de datos
        self.db.update_space_status(space_id, status)
        
        # Se registra el evento
        event = EventSchema.occupancy_event(
            space_id=space_id,
            status=status,
            previous_status=payload.get("previous_status")
        )
        self.db.insert_event(event)
    
    def handle_emergency_trigger(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Se procesa la activación de emergencia
        triggered = payload.get("triggered", False)
        gas_level = payload.get("gas_level", 0)
        
        logger.warning(f"SE DETECTÓ LA EMERGENCIA, POR FAVOR SALGA DE AHÍ PERO PARA AYER: {triggered} - El nivel del gas es de: {gas_level}")
        
        # Se registra el evento
        event = EventSchema.emergency_event(
            triggered=triggered,
            gas_level=gas_level
        )
        self.db.insert_event(event)
        
        # Se publica el comando de vuelta al hardware
        return {
            "command": "emergency",
            "action": "activate" if triggered else "deactivate",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def handle_exit_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Se procesa la solicitud de salida
        space_id = payload.get("space_id")
        
        logger.info(f"Se ha solicitado la salida del espacio {space_id}")
        
        # Se libera el espacio en la base de datos
        self.db.update_space_status(space_id, "free")
        
        # Se registrar el evento de salida
        event = {
            "type": "exit",
            "timestamp": datetime.utcnow().isoformat(),
            "space_id": space_id,
            "details": payload
        }
        self.db.insert_event(event)
        
        return {
            "command": "exit_gate",
            "action": "open",
            "space_id": space_id
        }
    
    def handle_fan_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Se procesa el comando del ventilador para el frontend
        action = payload.get("action")  # Si está apagado o encendido
        source = payload.get("source", "manual")
        
        logger.info(f"Ventilador: {action} (desde {source})")
        
        # Se registra el evento
        event = EventSchema.fan_event(status=action, source=source)
        self.db.insert_event(event)
        
        return {
            "command": "fan",
            "action": action,
            "source": source
        }
    
    def handle_space_management(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Se habilitan o deshabilitan los espacios desde frontend
        space_id = payload.get("space_id")
        enabled = payload.get("enabled", True)
        
        logger.info(f"🔧 Espacio {space_id}: {'habilitado' if enabled else 'deshabilitado'}")
        
        # Se registra el evento
        event = EventSchema.space_status_update(space_id, enabled)
        self.db.insert_event(event)
        
        return {
            "command": "space_management",
            "space_id": space_id,
            "enabled": enabled,
            "timestamp": datetime.utcnow().isoformat()
        }

    def handle_registration_start(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Se inicia el modo lector para registrar un usuario por RFID
        if self.pending_registration is not None:
            return {
                "ok": False,
                "state": "busy",
                "message": "Ya hay un registro en curso, espere a que finalice"
            }

        name = (payload.get("name") or payload.get("nombre") or "").strip()
        balance = float(payload.get("balance", payload.get("saldo", 0)) or 0)
        active = bool(payload.get("active", payload.get("activo", True)))
        placas = payload.get("placas", [])
        if not isinstance(placas, list):
            placas = []
        placas = [str(placa).strip().upper() for placa in placas if str(placa).strip()]

        if not name:
            return {
                "ok": False,
                "state": "error",
                "message": "Debe escribir el nombre antes de iniciar el lector"
            }

        self.pending_registration = {
            "name": name,
            "balance": balance,
            "active": active,
            "placas": placas,
            "started_at": datetime.utcnow().isoformat()
        }

        return {
            "ok": True,
            "state": "waiting_card",
            "message": "Acerque tarjeta para registrar"
        }

    def handle_registration_card_scanned(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Se procesa la tarjeta leída por la Raspberry para registro de usuario
        if self.pending_registration is None:
            return {
                "ok": False,
                "state": "error",
                "message": "No hay un registro en curso"
            }

        rfid = (payload.get("rfid") or "").strip().upper()
        if not rfid:
            return {
                "ok": False,
                "state": "error",
                "message": "No se reconocio la tarjeta, intente de nuevo"
            }

        existing = self.db.get_user_by_rfid_any(rfid)
        if existing is not None:
            self.pending_registration = None
            return {
                "ok": False,
                "state": "duplicate",
                "message": "Esta tarjeta ya fue registrada"
            }

        new_user = self.db.create_user(
            name=self.pending_registration["name"],
            rfid=rfid,
            balance=self.pending_registration["balance"],
            active=self.pending_registration["active"],
            placas=self.pending_registration.get("placas", [])
        )

        if new_user is None:
            self.pending_registration = None
            return {
                "ok": False,
                "state": "error",
                "message": "No se pudo registrar el usuario, intente de nuevo"
            }

        self.db.insert_event({
            "type": "user_registration",
            "timestamp": datetime.utcnow().isoformat(),
            "rfid": rfid,
            "user_name": new_user.get("name"),
            "details": {"source": "rfid_reader"}
        })

        self.pending_registration = None
        return {
            "ok": True,
            "state": "registered",
            "message": "Tarjeta registrada correctamente",
            "user": {
                "_id": new_user.get("_id"),
                "nombre": new_user.get("nombre"),
                "rfid": new_user.get("rfid"),
                "saldo": new_user.get("saldo", 0),
                "activo": new_user.get("activo", True),
                "placas": new_user.get("placas", [])
            }
        }

    def handle_users_list_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Retorna la lista de usuarios para el frontend
        users = self.db.list_users()
        return {
            "ok": True,
            "users": users
        }

    def handle_user_toggle_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Activa/desactiva usuario por ID
        user_id = str(payload.get("user_id", "")).strip()
        active = bool(payload.get("active", True))

        if not user_id:
            return {"ok": False, "message": "Falta user_id"}

        updated = self.db.set_user_active(user_id, active)
        if not updated:
            return {"ok": False, "message": "No se pudo actualizar el usuario"}

        self.db.insert_event({
            "type": "user_toggle",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "active": active,
            "details": {"source": "frontend"}
        })

        return {
            "ok": True,
            "user": updated
        }

    def handle_user_delete_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Elimina usuario por ID
        user_id = str(payload.get("user_id", "")).strip()
        if not user_id:
            return {"ok": False, "message": "Falta user_id"}

        deleted = self.db.delete_user(user_id)
        if not deleted:
            return {"ok": False, "message": "No se pudo eliminar el usuario"}

        self.db.insert_event({
            "type": "user_delete",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "details": {"source": "frontend"}
        })

        return {
            "ok": True,
            "user_id": user_id
        }

    def handle_user_update_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Actualiza datos de la tarjeta/usuario desde frontend
        user_id = str(payload.get("user_id", "")).strip()
        if not user_id:
            return {"ok": False, "message": "Falta user_id"}

        updates = {
            "nombre": payload.get("nombre"),
            "rfid": payload.get("rfid"),
            "saldo": payload.get("saldo"),
            "activo": payload.get("activo"),
            "placas": payload.get("placas", [])
        }
        
        placas_recibidas = updates.get('placas', [])
        logger.info(f"📋 UPDATE REQUEST INICIADO")
        logger.info(f"  → user_id: {user_id}")
        logger.info(f"  → placas recibidas: {placas_recibidas}")
        logger.info(f"  → tipo de placas: {type(placas_recibidas)}")

        updated = self.db.update_user_profile(user_id, updates)
        if not updated:
            logger.error(f"❌ UPDATE FAILED - No se pudo actualizar el usuario {user_id}")
            return {"ok": False, "message": "No se pudo actualizar el usuario"}

        if isinstance(updated, dict) and updated.get("error"):
            logger.error(f"❌ UPDATE ERROR - {updated.get('error')}")
            return {"ok": False, "message": updated.get("error")}
        
        placas_guardadas = updated.get("placas", [])
        logger.info(f"✅ UPDATE EXITOSO - placas guardadas: {placas_guardadas}")

        self.db.insert_event({
            "type": "user_update",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "details": {
                "source": "frontend",
                "fields": {
                    "nombre": updated.get("nombre"),
                    "rfid": updated.get("rfid"),
                    "saldo": updated.get("saldo"),
                    "activo": updated.get("activo")
                }
            }
        })

        return {
            "ok": True,
            "user": updated
        }

    def handle_stats_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Entrega métricas para dashboard y reportes
        hours = int(payload.get("hours", 12) or 12)
        if hours < 1:
            hours = 12
        if hours > 2880:  # Máximo 120 días
            hours = 2880
        return self.db.get_dashboard_statistics(hours=hours)
    
    def _check_suspicious_activity(self, rfid: str) -> Dict[str, Any]:
        # Se detectan los múltiples intentos fallidos en corto tiempo
        global attempt_cache, suspicious_cooldown
        
        now = datetime.utcnow()
        
        if rfid not in attempt_cache:
            attempt_cache[rfid] = []
        
        # Se limpian los intentos antiguos (> 60 segundos)
        attempt_cache[rfid] = [
            t for t in attempt_cache[rfid] 
            if (now - t).total_seconds() < 60
        ]
        
        # Se agrega el intento actual
        attempt_cache[rfid].append(now)
        
        # Si hay al menos 3 intentos fallidos en 60 segundos, se considera sospechoso
        if len(attempt_cache[rfid]) >= 3:
            last_alert_at = suspicious_cooldown.get(rfid)
            if last_alert_at and (now - last_alert_at).total_seconds() < 60:
                return None

            logger.warning(f"Actividad sospechosa detectada para RFID: {rfid}")
            suspicious_cooldown[rfid] = now
            
            # Se registra en la base de datos
            self.db.log_suspicious_activity(
                rfid=rfid,
                details={
                    "attempts": len(attempt_cache[rfid]),
                    "time_window": 60,
                    "first_attempt": attempt_cache[rfid][0].isoformat(),
                    "last_attempt": now.isoformat()
                }
            )
            
            # Se crea el evento
            event = EventSchema.suspicious_activity_event(
                rfid=rfid,
                attempts=len(attempt_cache[rfid]),
                time_window=60
            )
            self.db.insert_event(event)

            return {
                "type": "suspicious",
                "rfid": rfid,
                "attempts": len(attempt_cache[rfid]),
                "time_window_seconds": 60,
                "timestamp": now.isoformat(),
                "message": f"Actividad sospechosa detectada para tarjeta {rfid}"
            }

        return None