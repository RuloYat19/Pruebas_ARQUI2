from datetime import datetime
from typing import Optional, Dict, Any

class EventSchema:
    """Estructura estándar para los eventos que suceden en el proyecto"""
    
    @staticmethod
    def access_event(
        user_id: str,
        rfid: str,
        granted: bool,
        reason: str = "",
        plate: str = "",
        vehicle_type: str = "",
        tariff: float = 0.0,
    ) -> Dict[str, Any]:
        return {
            "type": "access",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "rfid": rfid,
            "granted": granted,
            "reason": reason,
            "plate": plate,
            "vehicle_type": vehicle_type,
            "tariff": tariff,
            "details": {}
        }
    
    @staticmethod
    def occupancy_event(space_id: int, status: str, previous_status: Optional[str] = None) -> Dict[str, Any]:
        return {
            "type": "occupancy",
            "timestamp": datetime.utcnow().isoformat(),
            "space_id": space_id,
            "status": status,  # "occupied" o "free"
            "previous_status": previous_status,
            "details": {}
        }
    
    @staticmethod
    def emergency_event(triggered: bool, gas_level: Optional[float] = None) -> Dict[str, Any]:
        return {
            "type": "emergency",
            "timestamp": datetime.utcnow().isoformat(),
            "triggered": triggered,
            "gas_level": gas_level,
            "details": {}
        }
    
    @staticmethod
    def fan_event(status: str, source: str = "auto") -> Dict[str, Any]:
        return {
            "type": "fan",
            "timestamp": datetime.utcnow().isoformat(),
            "status": status,  # "on" o "off"
            "source": source,  # "auto" o "manual"
            "details": {}
        }
    
    @staticmethod
    def suspicious_activity_event(rfid: str, attempts: int, time_window: int) -> Dict[str, Any]:
        return {
            "type": "suspicious",
            "timestamp": datetime.utcnow().isoformat(),
            "rfid": rfid,
            "attempts": attempts,
            "time_window_seconds": time_window,
            "details": {}
        }
    
    @staticmethod
    def space_status_update(space_id: int, enabled: bool) -> Dict[str, Any]:
        return {
            "type": "space_maintenance",
            "timestamp": datetime.utcnow().isoformat(),
            "space_id": space_id,
            "enabled": enabled,
            "details": {}
        }