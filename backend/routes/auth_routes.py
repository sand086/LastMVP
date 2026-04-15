"""
Authentication routes: login, logout, password reset.
"""
import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from datetime import datetime, timezone, timedelta
from starlette.requests import Request as StarletteRequest

from dependencies import (
    db, limiter, security, get_current_user, require_role,
    hash_password, verify_password, verify_password_async, create_token, create_refresh_token,
    JWT_SECRET, JWT_ALGORITHM,
)
from models import (
    UserLogin, TokenResponse, PasswordResetRequestCreate, PasswordChangeByAdmin,
)
from middleware import log_audit_event

router = APIRouter(tags=["Auth"])


@router.post("/auth/login", response_model=TokenResponse)
@limiter.limit("20/minute")
async def login(data: UserLogin, request: StarletteRequest):
    now = datetime.now(timezone.utc)
    client_ip = request.headers.get(
        "x-forwarded-for", request.client.host if request.client else "unknown"
    ).split(",")[0].strip()

    lock_record = await db.login_attempts.find_one(
        {"email": data.email, "ip": client_ip}, {"_id": 0}
    )
    if lock_record and lock_record.get("blocked_until"):
        blocked_until = datetime.fromisoformat(lock_record["blocked_until"])
        if blocked_until > now:
            raise HTTPException(
                status_code=429,
                detail="Cuenta bloqueada temporalmente. Intenta en 15 minutos.",
            )

    user = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not user or not await verify_password_async(data.password, user["password"]):
        ten_min_ago = (now - timedelta(minutes=10)).isoformat()
        if lock_record:
            last_attempt = lock_record.get("last_attempt", "")
            attempts = lock_record.get("attempts", 0)
            if last_attempt < ten_min_ago:
                attempts = 1
            else:
                attempts += 1
            update_fields = {"attempts": attempts, "last_attempt": now.isoformat()}
            if attempts >= 5:
                update_fields["blocked_until"] = (now + timedelta(minutes=15)).isoformat()
            await db.login_attempts.update_one(
                {"email": data.email, "ip": client_ip}, {"$set": update_fields}
            )
        else:
            await db.login_attempts.insert_one({
                "email": data.email,
                "ip": client_ip,
                "attempts": 1,
                "last_attempt": now.isoformat(),
                "blocked_until": None,
            })
        await log_audit_event(
            db, data.email, "", "login_failed", "user", "",
            details=f"Failed login for {data.email}", status="error",
        )
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    await db.login_attempts.delete_many({"email": data.email, "ip": client_ip})
    token = create_token(user["id"], user["email"], user["role"])
    user_response = {k: v for k, v in user.items() if k != "password"}
    await log_audit_event(db, user["id"], user["role"], "login_success", "user", user["id"])
    return TokenResponse(access_token=token, user=user_response)


@router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return user


@router.post("/auth/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = pyjwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        jti = payload.get("jti")
        if jti:
            await db.revoked_tokens.insert_one({
                "jti": jti,
                "revoked_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": datetime.fromtimestamp(payload["exp"], tz=timezone.utc).isoformat(),
            })
    except Exception:
        pass
    return {"message": "Sesión cerrada correctamente."}


# ==================== PASSWORD RESET ====================

@router.post("/auth/request-password-reset")
async def request_password_reset(data: PasswordResetRequestCreate):
    import uuid
    user = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not user:
        return {"message": "Si el email existe, se notificará al administrador"}
    request_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "user_email": user["email"],
        "user_name": user["name"],
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }
    await db.password_reset_requests.insert_one(request_doc)
    return {"message": "Solicitud enviada. El administrador procesará tu solicitud."}


@router.get("/password-reset-requests")
async def get_password_reset_requests(
    admin: dict = Depends(require_role(["coordinator", "developer"]))
):
    requests = await db.password_reset_requests.find({}, {"_id": 0}).sort("requested_at", -1).to_list(100)
    return requests


@router.delete("/password-reset-requests/{request_id}")
async def dismiss_password_reset_request(
    request_id: str,
    admin: dict = Depends(require_role(["coordinator", "developer"])),
):
    result = await db.password_reset_requests.delete_one({"id": request_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return {"message": "Solicitud eliminada"}


@router.post("/users/change-password")
async def change_password_by_admin(
    data: PasswordChangeByAdmin,
    admin: dict = Depends(require_role(["coordinator", "developer"])),
):
    result = await db.users.update_one(
        {"id": data.user_id},
        {"$set": {"password": hash_password(data.new_password)}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await db.password_reset_requests.update_many(
        {"user_id": data.user_id, "status": "pending"},
        {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"message": "Contraseña actualizada exitosamente"}



# ==================== REFRESH TOKEN ====================

@router.post("/auth/refresh-token")
async def generate_refresh_token(
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """Generate a long-lived refresh token (90 days) for API/Power BI integrations.
    Only coordinators and developers can generate refresh tokens."""
    result = create_refresh_token(user["id"], user["email"], user["role"])

    # Store token metadata for revocation support
    await db.refresh_tokens.insert_one({
        "jti": result["jti"],
        "user_id": user["id"],
        "user_email": user["email"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": result["expires_at"],
        "revoked": False,
    })

    return {
        "refresh_token": result["token"],
        "expires_at": result["expires_at"],
        "message": "Token generado. Valido por 90 dias. Guardar en lugar seguro.",
    }


@router.post("/auth/exchange-token")
async def exchange_refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Exchange a refresh token for a short-lived access token."""
    try:
        payload = pyjwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=400, detail="No es un refresh token")

        jti = payload.get("jti")
        if jti:
            stored = await db.refresh_tokens.find_one({"jti": jti}, {"_id": 0})
            if not stored or stored.get("revoked"):
                raise HTTPException(status_code=401, detail="Refresh token revocado")

        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password": 0})
        if not user:
            raise HTTPException(status_code=401, detail="Usuario no encontrado")

        access_token = create_token(user["id"], user["email"], user["role"])
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {"id": user["id"], "email": user["email"], "role": user["role"], "name": user.get("name")},
        }
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expirado")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Refresh token invalido")


@router.delete("/auth/refresh-token/{jti}")
async def revoke_refresh_token(
    jti: str,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """Revoke a specific refresh token."""
    result = await db.refresh_tokens.update_one(
        {"jti": jti, "user_id": user["id"]},
        {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Token no encontrado")
    return {"message": "Refresh token revocado exitosamente"}


@router.get("/auth/refresh-tokens")
async def list_refresh_tokens(
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """List all active refresh tokens for the current user."""
    tokens = await db.refresh_tokens.find(
        {"user_id": user["id"], "revoked": False},
        {"_id": 0, "jti": 1, "created_at": 1, "expires_at": 1},
    ).sort("created_at", -1).to_list(50)
    return tokens
