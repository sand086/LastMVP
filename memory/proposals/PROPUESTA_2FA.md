# Propuesta: Autenticación de 2 Factores (2FA / A2F)

**Fecha**: 22/04/2026
**Autor**: Equipo LastMile OS
**Scope**: Hardening de autenticación para LastMile OS (producción)
**Decisión esperada**: Aprobar opción A, B o C + timeline

---

## 1. Contexto

El sistema de autenticación actual de LastMile OS incluye:

- ✅ JWT en cookies `httpOnly` + `Secure` + `SameSite=lax` (production-grade)
- ✅ Password hashing con `bcrypt` (cost 12)
- ✅ Rate limiting en login (`slowapi`: 10 req/min por IP)
- ✅ Auditoría de `login_success` / `login_failed` en `audit_logs`
- ✅ Role-based access control (developer, coordinator, agent, proveedor, executive)
- ✅ Brute force protection (lockout después de N intentos)
- ❌ **Sin segundo factor** — una credencial comprometida = acceso total

**Riesgo actual**: Un coordinador con acceso a `Liquidación`, `Admin IA` y `API tokens` puede ser objetivo de phishing. Una credencial filtrada basta para exfiltrar data de clientes, manipular evaluaciones o generar refresh tokens de 90 días.

## 2. Opciones comparadas

| Criterio                    | A) TOTP (Authenticator) | B) Email OTP            | C) SMS OTP (Twilio)     | D) WebAuthn/Passkeys    |
|-----------------------------|--------------------------|-------------------------|--------------------------|--------------------------|
| Seguridad                   | ⭐⭐⭐⭐                    | ⭐⭐⭐                     | ⭐⭐ (SIM-swap risk)      | ⭐⭐⭐⭐⭐                    |
| UX                          | Buena (app móvil)        | Muy buena               | Buena                    | Excelente (biometría)    |
| Costo operacional           | **$0**                   | **~$0** (Resend free)   | ~$10-30 USD/mes          | $0                       |
| Tiempo implementación       | 3-4 días                 | 2 días                  | 3 días                   | 5-7 días                 |
| Funciona offline            | ✅                       | ❌                       | ❌                        | ✅                       |
| Requiere dispositivo extra  | Sí (smartphone)          | No                      | Sí (smartphone)          | Depende del autenticador |
| Backup codes                | Sí                       | Sí                      | Sí                       | Sí                       |
| Compatible Yael/Jair/Ops    | ✅                       | ✅                       | ✅                        | Requiere Mac/iOS reciente|

## 3. Recomendación: **Opción A (TOTP) + Email OTP como fallback**

**Por qué**:
- Costo cero, infraestructura cero.
- Estándar industria (RFC 6238); funciona con Google Authenticator, Authy, 1Password, iOS Keychain, Bitwarden.
- Offline-capable — el driver / coord no depende de tener señal.
- Email OTP solo como **fallback para recuperación** (si pierde el autenticador).

## 4. Arquitectura propuesta

### Modelo de datos (nuevos campos en `users`)
```
{
    ...
    "totp_enabled": bool,              # default false
    "totp_secret": str | None,         # base32, cifrado con AES-GCM (PII_ENCRYPTION_KEY)
    "totp_backup_codes": [             # 10 códigos one-time, bcrypt-hasheados
        {"hash": "...", "used": false, "used_at": null}
    ],
    "totp_enrolled_at": iso_string | None,
    "mfa_required_from": iso_string,   # enforcement date configurable por rol
}
```

### Endpoints nuevos
- `POST /api/auth/2fa/setup` → genera `totp_secret` + QR code + 10 backup codes (solo mostrados 1 vez).
- `POST /api/auth/2fa/verify-setup` → valida 1er código TOTP para confirmar enrollment.
- `POST /api/auth/2fa/challenge` → después del password OK, recibe código TOTP/backup antes de emitir cookie.
- `POST /api/auth/2fa/disable` → desactiva 2FA (requiere password + código vigente).
- `POST /api/auth/2fa/regenerate-backup-codes` → emite 10 nuevos códigos.

### Flujo de login
```
1. POST /auth/login con email + password
   ↓
2. Si totp_enabled=false → cookie JWT (como hoy)
   Si totp_enabled=true  → 200 {"mfa_required": true, "mfa_token": <short-lived 5min JWT>}
   ↓
3. POST /auth/2fa/challenge con mfa_token + código 6 dígitos
   ↓
4. Si OK → cookie JWT final + invalidar mfa_token
```

### Políticas de enforcement
- **Obligatorio** para roles `developer`, `coordinator`, `executive` (fecha flag `mfa_required_from`).
- **Opcional** para `agent`, `proveedor` (banner persistente "Activa 2FA — Ajustes → Seguridad").
- **Grace period**: 7 días desde notificación para auto-enrollment antes de bloqueo.

## 5. Libraries (sin costo)

| Propósito         | Librería Python         | Tamaño | Notas                         |
|-------------------|-------------------------|--------|-------------------------------|
| TOTP RFC 6238     | `pyotp` (2.9.0)         | 15 KB  | Stateless, zero deps          |
| QR code           | `qrcode[pil]` (7.4.2)   | 80 KB  | Genera PNG base64 para UI     |
| AES-GCM secrets   | `cryptography` (42.0)   | ya en stack | Cifrar totp_secret en DB      |
| Resend (fallback) | `resend`                | 15 KB  | Ya disponible en Emergent     |

**Frontend**: `qrcode.react` (12 KB) para renderizar QR en pantalla de setup.

## 6. Plan de implementación (timeline)

### Sprint 1 — Backend (2.5 días)
- Modelo de datos + migración idempotente.
- Endpoints `/auth/2fa/setup`, `/auth/2fa/verify-setup`, `/auth/2fa/challenge`, `/auth/2fa/disable`.
- Modificar `/auth/login` para retornar `mfa_required` si aplica.
- Cifrado `totp_secret` con `PII_ENCRYPTION_KEY` (env var nueva).
- Tests unitarios en `/app/backend/tests/test_2fa.py`.

### Sprint 2 — Frontend (2 días)
- Página `Settings → Seguridad` con flujo de setup (QR + validación + backup codes).
- Pantalla `LoginChallenge.jsx` que aparece cuando `mfa_required=true`.
- Input de 6 dígitos con auto-submit y paste-friendly.
- Página de backup codes descargable como PDF.
- Banner "Activa 2FA" para roles no-enforced.

### Sprint 3 — Rollout + Ops (1.5 días)
- Comunicado interno con instrucciones + screenshots.
- Script admin de emergencia: `GET /api/admin/users/{id}/disable-2fa` (auditable) para recovery si alguien pierde totp_secret Y backup codes.
- Grace period (7 días) + enforcement automático vía middleware.
- Monitoreo: métricas en `/api/admin/2fa-stats` (% usuarios enrolados, intentos fallidos).

### Total: **6 días laborales** (1.5 semanas)

## 7. Presupuesto

| Concepto                                      | Esfuerzo  | Costo interno |
|-----------------------------------------------|-----------|----------------|
| Backend: endpoints + tests + cifrado          | 2.5 días  | —              |
| Frontend: setup screen + login challenge      | 2.0 días  | —              |
| Integración + rollout + comunicado            | 1.5 días  | —              |
| QA / revisión de seguridad                    | 0.5 días  | —              |
| **TOTAL esfuerzo**                            | **6.5 días** |              |
| **Costos externos (licencias, SaaS)**         |           | **$0 USD**     |
| **Costos infra recurrentes**                  |           | **$0 USD/mes** |

**Email OTP fallback**: ~$0 (Resend free tier cubre 3K emails/mes).

## 8. Checklist de cumplimiento y seguridad

- ✅ Secretos TOTP cifrados at-rest (AES-GCM con PII_ENCRYPTION_KEY en env)
- ✅ Backup codes almacenados como bcrypt hashes, nunca en claro
- ✅ MFA token de transición con TTL de 5 min (mitigación replay)
- ✅ Rate limiting específico en endpoints 2FA: 5 intentos / 5 min
- ✅ Auditoría completa: enrollment, disable, challenge success/fail en `audit_logs`
- ✅ ISO 27001 A.9.4.2 (Secure log-on procedures) cumplido
- ✅ SOC 2 CC6.1 (Logical access controls) cumplido

## 9. Riesgos y mitigaciones

| Riesgo                                 | Mitigación                                                       |
|----------------------------------------|------------------------------------------------------------------|
| Usuario pierde autenticador y backup   | Admin endpoint auditable + protocolo interno de verificación     |
| Adopción baja en agentes               | Grace period + banner + enforcement por fase                     |
| Integración Power BI (refresh token)   | Refresh tokens exentos de 2FA (son credenciales de servicio)     |
| Reloj del cliente desalineado          | `pyotp.verify(code, valid_window=1)` (±30s tolerancia)           |

## 10. Métricas de éxito (30 días post-rollout)

- ✅ ≥ 95 % de `coordinator` / `developer` / `executive` enrolados
- ✅ 0 incidentes de credential stuffing que escalen a breach
- ✅ < 3 % tickets de soporte por recuperación 2FA
- ✅ Banner de enrolamiento visible para roles no-enforced

## 11. Recomendación final

**✅ Aprobar opción A (TOTP) con ejecución inmediata en 6.5 días laborales**.

ROI en seguridad:
- **Costo incremental**: $0 USD.
- **Valor**: bloquea el 99 % de ataques por credencial comprometida (phishing + credential stuffing + dumps).
- **Time to value**: 1.5 semanas.

---

*Para aprobar, responder: "OK 2FA A — ejecutar"*
