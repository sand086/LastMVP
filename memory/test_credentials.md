# Test Credentials

## User Accounts
| Role | Email | Password |
|------|-------|----------|
| Developer | dev@me.mx | LastMile2026 |
| Coordinator | yael@me.mx | LastMile2026 |
| Agent | agente@me.mx | LastMile2026 |
| Proveedor | proveedor@me.mx | LastMile2026 |

## Auth Notes
- JWT stored in httpOnly cookie `lm_access_token` (Path=/api, Secure, SameSite=lax)
- Bearer header still works for API consumers (backward compat)
- Refresh tokens (90 days) available for Power BI integration
