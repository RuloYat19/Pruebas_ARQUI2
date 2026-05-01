from datetime import datetime, timedelta
import os
from typing import Any

import bcrypt
import jwt
from bson import ObjectId
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo import ReturnDocument

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "parkguard_db")
JWT_SECRET = os.getenv("JWT_SECRET", "parkguard-dev-secret")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").strip().lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")
AUTH_COOKIE_NAME = "pg_access_token"

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

users_col = db["users"]
auth_users_col = db["auth_users"]
events_col = db["events"]
logs_col = db["logs"]

app = FastAPI(title="ParkGuard Backend API", version="1.0.0")
security = HTTPBearer(auto_error=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    nombre: str
    rfid: str
    saldo: float = 0
    activo: bool = True


class UserUpdate(BaseModel):
    nombre: str | None = None
    rfid: str | None = None
    saldo: float | None = None
    activo: bool | None = None


def _hash_password(plain_password: str) -> str:
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def _verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except Exception:
        return False


def _serialize_auth_user(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": str(doc.get("username", "")),
        "role": str(doc.get("role", "user")),
    }


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=JWT_EXPIRE_MINUTES * 60,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
    )


def _ensure_admin_user() -> None:
    auth_users_col.create_index("username", unique=True)
    admin_username = ADMIN_USERNAME.strip()
    admin_password = ADMIN_PASSWORD
    if not admin_username or not admin_password:
        raise RuntimeError("ADMIN_USERNAME y ADMIN_PASSWORD son obligatorios")

    admin_doc = auth_users_col.find_one({"username": admin_username})
    if admin_doc is None:
        auth_users_col.insert_one(
            {
                "username": admin_username,
                "password_hash": _hash_password(admin_password),
                "role": "admin",
                "active": True,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
        )


def _serialize_user(doc: dict[str, Any]) -> dict[str, Any]:
    placas = doc.get("placas", [])
    if not isinstance(placas, list):
        placas = []
    return {
        "_id": str(doc.get("_id")),
        "nombre": doc.get("nombre", doc.get("name", "Sin nombre")),
        "rfid": str(doc.get("rfid", doc.get("card_id", ""))),
        "saldo": float(doc.get("saldo", doc.get("balance", 0)) or 0),
        "activo": bool(doc.get("activo", doc.get("active", True))),
        "placas": placas,
    }


def _create_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        ) from exc

    username = str(payload.get("sub", ""))
    role = str(payload.get("role", "user"))
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )
    return {"username": username, "role": role}


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any]:
    bearer_token: str | None = None
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)

    if credentials is not None and credentials.scheme.lower() == "bearer":
        bearer_token = credentials.credentials

    token = bearer_token or cookie_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token requerido",
        )

    return _decode_token(token)


def _get_time_labels(hours: int) -> list[datetime]:
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=hours - 1)
    return [start + timedelta(hours=index) for index in range(hours)]


def _build_stats(hours: int) -> dict[str, Any]:
    labels = _get_time_labels(hours)
    label_keys = [bucket.strftime("%H:00") for bucket in labels]

    ingresos_map = {
        key: {"hora": key, "ingresos": 0, "salidas": 0, "gas": 0}
        for key in label_keys
    }

    start_iso = labels[0].isoformat()
    events = list(events_col.find({"timestamp": {"$gte": start_iso}}))

    emergencias = 0
    ventilador = 0

    for event in events:
        timestamp = str(event.get("timestamp", ""))
        key = timestamp[11:16] + ":00" if len(timestamp) >= 16 else None

        event_type = str(event.get("type", "")).lower()
        if event_type == "access" and bool(event.get("granted", False)):
            if key in ingresos_map:
                ingresos_map[key]["ingresos"] += 1
        elif event_type == "exit":
            if key in ingresos_map:
                ingresos_map[key]["salidas"] += 1
        elif event_type == "emergency" and bool(event.get("triggered", False)):
            emergencias += 1
            if key in ingresos_map:
                ingresos_map[key]["gas"] += 1
        elif event_type == "fan" and str(event.get("status", "")).lower() == "on":
            ventilador += 1

    space_usage: dict[str, int] = {}
    occupancy_events = events_col.find({
        "type": "occupancy",
        "timestamp": {"$gte": start_iso},
        "status": "occupied",
    })
    for event in occupancy_events:
        space_id = str(event.get("space_id", "N/A"))
        key = f"E{space_id}" if space_id.isdigit() else space_id
        space_usage[key] = space_usage.get(key, 0) + 1

    espacios = [
        {"espacio": key, "usos": value}
        for key, value in sorted(space_usage.items(), key=lambda item: item[0])
    ]

    suspicious_alerts = list(
        logs_col.find({
            "type": "suspicious_activity",
            "timestamp": {"$gte": start_iso},
        }).sort("timestamp", -1).limit(50)
    )
    alertas = [
        {
            "timestamp": row.get("timestamp"),
            "rfid": row.get("rfid"),
            "attempts": row.get("details", {}).get("attempts", 0),
            "message": row.get("details", {}).get("message", "Actividad sospechosa"),
        }
        for row in suspicious_alerts
    ]

    ingresos = list(ingresos_map.values())
    gas = [{"hora": row["hora"], "activaciones": row["gas"]} for row in ingresos]

    return {
        "ingresos": ingresos,
        "espacios": espacios,
        "gas": gas,
        "resumen": {
            "ingresos": sum(item["ingresos"] for item in ingresos),
            "salidas": sum(item["salidas"] for item in ingresos),
            "emergencias": emergencias,
            "ventilador": ventilador,
            "sospechosas": len(alertas),
        },
        "alertas": alertas,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("startup")
def on_startup() -> None:
    _ensure_admin_user()


@app.post("/auth/login")
def login(payload: LoginRequest, response: Response) -> dict[str, Any]:
    username = payload.username.strip()
    password = payload.password

    user_doc = auth_users_col.find_one({"username": username, "active": True})
    if user_doc is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )

    password_hash = str(user_doc.get("password_hash", ""))
    if not _verify_password(password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )

    role = str(user_doc.get("role", "user"))
    token = _create_token(username=username, role=role)
    _set_auth_cookie(response, token)
    return {
        "user": _serialize_auth_user(user_doc),
        "expires_in": JWT_EXPIRE_MINUTES * 60,
    }


@app.post("/auth/logout")
def logout(response: Response) -> dict[str, str]:
    _clear_auth_cookie(response)
    return {"message": "Sesión cerrada"}


@app.get("/auth/me")
def auth_me(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user_doc = auth_users_col.find_one(
        {
            "username": current_user["username"],
            "active": True,
        }
    )
    if user_doc is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no autorizado",
        )
    return {"user": _serialize_auth_user(user_doc)}


@app.get("/users")
def list_users(_: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    docs = list(users_col.find({}).sort("created_at", -1))
    return [_serialize_user(doc) for doc in docs]


@app.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    _: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    rfid = payload.rfid.strip().upper()
    if not rfid:
        raise HTTPException(status_code=400, detail="RFID requerido")

    existing = users_col.find_one({"rfid": rfid})
    if existing is not None:
        raise HTTPException(status_code=409, detail="RFID ya está en uso")

    nombre = payload.nombre.strip()
    doc = {
        "name": nombre,
        "nombre": nombre,
        "rfid": rfid,
        "card_id": rfid,
        "balance": max(0.0, float(payload.saldo)),
        "saldo": max(0.0, float(payload.saldo)),
        "active": bool(payload.activo),
        "activo": bool(payload.activo),
        "created_at": datetime.utcnow().isoformat(),
    }
    result = users_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize_user(doc)


@app.put("/users/{user_id}")
def update_user(
    user_id: str,
    payload: UserUpdate,
    _: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        target_id = ObjectId(user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="ID inválido") from exc

    patch: dict[str, Any] = {}
    if payload.nombre is not None:
        nombre = payload.nombre.strip()
        patch["nombre"] = nombre
        patch["name"] = nombre

    if payload.rfid is not None:
        rfid = payload.rfid.strip().upper()
        duplicate = users_col.find_one({"rfid": rfid, "_id": {"$ne": target_id}})
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="RFID ya está en uso")
        patch["rfid"] = rfid
        patch["card_id"] = rfid

    if payload.saldo is not None:
        safe_balance = max(0.0, float(payload.saldo))
        patch["saldo"] = safe_balance
        patch["balance"] = safe_balance

    if payload.activo is not None:
        patch["activo"] = bool(payload.activo)
        patch["active"] = bool(payload.activo)

    if not patch:
        raise HTTPException(status_code=400, detail="No hay cambios para aplicar")

    result = users_col.find_one_and_update(
        {"_id": target_id},
        {"$set": patch},
        return_document=ReturnDocument.AFTER,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return _serialize_user(result)


@app.patch("/users/{user_id}/active")
def toggle_user_active(
    user_id: str,
    payload: UserUpdate,
    _: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if payload.activo is None:
        raise HTTPException(status_code=400, detail="Campo activo requerido")

    try:
        target_id = ObjectId(user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="ID inválido") from exc

    result = users_col.find_one_and_update(
        {"_id": target_id},
        {"$set": {"activo": bool(payload.activo), "active": bool(payload.activo)}},
        return_document=ReturnDocument.AFTER,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return _serialize_user(result)


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    _: dict[str, Any] = Depends(get_current_user),
) -> None:
    try:
        target_id = ObjectId(user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="ID inválido") from exc

    result = users_col.delete_one({"_id": target_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")


@app.get("/stats")
def get_stats(
    hours: int = Query(default=12, ge=1, le=2880),
    _: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return _build_stats(hours=hours)