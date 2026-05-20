"""Generador de README markdown por suscripción (PROMPT 39 V3 P2 backlog).

Devuelve un texto self-contained con:
  - Endpoint, eventos suscritos, schema_version
  - Headers que enviamos
  - Ejemplos de verificación HMAC en Node, Python, PHP, cURL
  - Sample payload del primer evento de la suscripción
"""
from __future__ import annotations

NODE_EXAMPLE = """\
// Node 18+
import crypto from "crypto";

function verify(secret, body, signatureHeader) {
  const expected = "sha256=" + crypto
    .createHmac("sha256", secret)
    .update(body, "utf8")
    .digest("hex");
  return crypto.timingSafeEqual(
    Buffer.from(expected), Buffer.from(signatureHeader)
  );
}

// Express
app.post("/webhooks/mye", express.raw({type: "application/json"}), (req, res) => {
  const sig = req.header("X-MyE-Signature");
  if (!verify(process.env.MYE_WEBHOOK_SECRET, req.body, sig)) {
    return res.status(401).send("invalid signature");
  }
  const event = JSON.parse(req.body);
  // process event…
  return res.status(200).send("ok");
});
"""

PYTHON_EXAMPLE = """\
# Python 3.10+
import hmac, hashlib

def verify(secret: str, body: bytes, signature_header: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)

# FastAPI
from fastapi import FastAPI, Request, HTTPException
app = FastAPI()

@app.post("/webhooks/mye")
async def receive(request: Request):
    body = await request.body()
    sig = request.headers.get("x-mye-signature", "")
    if not verify(MYE_WEBHOOK_SECRET, body, sig):
        raise HTTPException(401, "invalid signature")
    event = await request.json()
    # process event…
    return {"ok": True}
"""

PHP_EXAMPLE = """\
<?php
// PHP 8.0+
function mye_verify(string $secret, string $body, string $signatureHeader): bool {
    $expected = 'sha256=' . hash_hmac('sha256', $body, $secret);
    return hash_equals($expected, $signatureHeader);
}

$body = file_get_contents('php://input');
$sig  = $_SERVER['HTTP_X_MYE_SIGNATURE'] ?? '';
if (!mye_verify(getenv('MYE_WEBHOOK_SECRET'), $body, $sig)) {
    http_response_code(401);
    exit('invalid signature');
}
$event = json_decode($body, true);
// process event…
http_response_code(200);
echo 'ok';
"""

CURL_EXAMPLE = """\
# Verificación local con cURL + openssl (para debug)
echo -n '<body>' | openssl dgst -sha256 -hmac '<secret>' -hex
# Compara contra el header X-MyE-Signature recibido
"""


def generate_readme(*, subscription: dict, event_codes: list[str],
                     samples_by_code: dict | None = None,
                     base_docs_url: str = "https://docs.myexcellence.io") -> str:
    """Construye el README markdown completo."""
    sub_id = subscription.get("id", "—")
    url = subscription.get("endpoint_url", "—")
    pii = "**SÍ — con consentimiento firmado**" if subscription.get("include_pii") else "no (enmascarado)"
    samples_by_code = samples_by_code or {}

    lines: list[str] = []
    lines.append(f"# Webhook MyExcellence · {sub_id[:8]}")
    lines.append("")
    lines.append("> Webhook saliente desde MyExcellence hacia tu endpoint. "
                 "Verificación HMAC SHA-256 obligatoria. Reintentos exponenciales "
                 "ante 5xx/timeout, deduplicación por `event_id`.")
    lines.append("")
    lines.append("## Datos de tu suscripción")
    lines.append("")
    lines.append(f"- **Endpoint**: `{url}`")
    lines.append(f"- **Eventos suscritos**: {', '.join('`' + c + '`' for c in event_codes) or 'ninguno'}")
    lines.append(f"- **Incluye PII**: {pii}")
    lines.append(f"- **Subscription ID**: `{sub_id}`")
    lines.append("")
    lines.append("## Headers que enviamos")
    lines.append("")
    lines.append("| Header | Descripción |")
    lines.append("|---|---|")
    lines.append("| `X-MyE-Signature` | `sha256=<hex>` HMAC del body con tu secreto |")
    lines.append("| `X-MyE-Signature-V2` | (opcional) firma con secreto rotado, válida 7 días |")
    lines.append("| `X-MyE-Event` | Código del evento (ej. `ticket.created`) |")
    lines.append("| `X-MyE-Event-Id` | UUID único — usa para deduplicar |")
    lines.append("| `X-MyE-Schema-Version` | Versión del payload (ej. `v1`) |")
    lines.append("| `X-MyE-Timestamp` | Unix epoch del envío |")
    lines.append("| `X-MyE-Subscription-Id` | UUID de tu suscripción |")
    lines.append("")
    lines.append("## Política de reintentos")
    lines.append("")
    lines.append(("Tu endpoint debe responder **2xx en menos de 30 segundos**. "
                  "Si responde 5xx, 429, o timeout:"))
    lines.append("")
    lines.append("```text")
    lines.append("intento 2 → +1m")
    lines.append("intento 3 → +5m")
    lines.append("intento 4 → +30m")
    lines.append("intento 5 → +2h")
    lines.append("intento 6 → +12h")
    lines.append("intento 7 → +24h")
    lines.append("Tras 7 fallas → DLQ (replay manual desde el panel)")
    lines.append("```")
    lines.append("")
    lines.append("Si tu endpoint mantiene >30% errores en 1h, abrimos el circuito "
                 "automáticamente (cooldown 5min) y notificamos al admin.")
    lines.append("")
    lines.append("## Ejemplos de verificación")
    lines.append("")
    lines.append("### Node.js (Express)")
    lines.append("```js")
    lines.append(NODE_EXAMPLE.rstrip())
    lines.append("```")
    lines.append("")
    lines.append("### Python (FastAPI)")
    lines.append("```python")
    lines.append(PYTHON_EXAMPLE.rstrip())
    lines.append("```")
    lines.append("")
    lines.append("### PHP")
    lines.append("```php")
    lines.append(PHP_EXAMPLE.rstrip())
    lines.append("```")
    lines.append("")
    lines.append("### cURL (debug)")
    lines.append("```bash")
    lines.append(CURL_EXAMPLE.rstrip())
    lines.append("```")
    lines.append("")

    if samples_by_code:
        lines.append("## Payloads de ejemplo")
        lines.append("")
        for code, sample in samples_by_code.items():
            lines.append(f"### {code}")
            lines.append("")
            lines.append("```json")
            import json
            lines.append(json.dumps(sample, indent=2, ensure_ascii=False))
            lines.append("```")
            lines.append("")
    lines.append("## Soporte")
    lines.append("")
    lines.append(f"- Documentación: {base_docs_url}/webhooks")
    lines.append("- Reintentos manuales y DLQ: panel `/admin/webhooks`")
    lines.append("- Para rotar el secreto: `POST /api/admin/webhooks/subscriptions/{id}/rotate-secret`")
    lines.append("")
    lines.append("---")
    lines.append("Generado por MyExcellence · " + sub_id)
    return "\n".join(lines)
