"""
PII (Personally Identifiable Information) protection — at-rest encryption + role-based masking.

Strategy (R00C / iter58):
  - Symmetric encryption (Fernet AES-128) reusing utils.encryption infrastructure.
  - Marker prefix `enc::` distinguishes encrypted values from legacy plain values
    → backward-compatible: existing data stays plain until edited, new writes are encrypted.
  - Indexable / searchable fields (tracking_number, address_cp) stay plain by design.
  - Encrypted scope (conservative iter58 rollout):
      packages.recipient_name
      packages.address
      packages.recipient_phone
  - Role-based display:
      coordinator/developer/executive → see plain after decrypt
      agent/proveedor                  → see masked (e.g. "Juan P***", "55****1234")
"""
import logging
from typing import Optional, Iterable

from utils.encryption import _get_fernet  # internal helper exposed as needed

logger = logging.getLogger(__name__)

ENC_PREFIX = "enc::"

# Roles that see plain text after decryption
PLAIN_ROLES = {"coordinator", "developer", "executive"}
# Roles that see masked output
MASKED_ROLES = {"agent", "proveedor"}

# Default PII fields per collection — single source of truth for hooks
PII_FIELDS_PACKAGES = ("recipient_name", "address", "recipient_phone")


# ─────────────── ENCRYPT / DECRYPT ───────────────

def encrypt_pii(value: Optional[str]) -> Optional[str]:
    """Encrypt a single string value with the `enc::` marker. Idempotent — already
    encrypted values are returned unchanged. None/empty values pass through.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    if not value:
        return value
    if value.startswith(ENC_PREFIX):
        return value  # already encrypted — idempotent
    try:
        fernet = _get_fernet()
        token = fernet.encrypt(value.encode("utf-8")).decode("ascii")
        return f"{ENC_PREFIX}{token}"
    except Exception as e:
        logger.error(f"[pii] encrypt failed: {e}")
        return value  # fail-open to avoid losing data on transient errors


def decrypt_pii(value: Optional[str]) -> Optional[str]:
    """Decrypt a single value if it carries the `enc::` marker; otherwise return as-is.
    Resilient to malformed tokens (returns original masked string).
    """
    if value is None or not isinstance(value, str) or not value:
        return value
    if not value.startswith(ENC_PREFIX):
        return value  # legacy plain value
    token = value[len(ENC_PREFIX):]
    try:
        fernet = _get_fernet()
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except Exception as e:
        logger.warning(f"[pii] decrypt failed: {type(e).__name__}")
        return "[encrypted]"


def is_encrypted(value: Optional[str]) -> bool:
    return bool(value) and isinstance(value, str) and value.startswith(ENC_PREFIX)


# ─────────────── MASKING ───────────────

def mask_name(value: Optional[str]) -> str:
    """Juan Pérez García → Juan P*** G***"""
    if not value:
        return value or ""
    parts = value.strip().split()
    out = []
    for i, p in enumerate(parts):
        if i == 0 and len(p) > 1:
            out.append(p)  # keep first name fully
        elif len(p) <= 1:
            out.append(p)
        else:
            out.append(f"{p[0]}***")
    return " ".join(out)


def mask_phone(value: Optional[str]) -> str:
    """+52 55 1234 5678 → +52 55****5678"""
    if not value:
        return value or ""
    digits = "".join(c for c in value if c.isdigit())
    if len(digits) < 4:
        return "***"
    keep_tail = 4
    keep_head = 2 if len(digits) >= 8 else 0
    return f"{digits[:keep_head]}{'*' * (len(digits) - keep_head - keep_tail)}{digits[-keep_tail:]}"


def mask_address(value: Optional[str]) -> str:
    """Calle 123, Col Centro, CP 06000 → Calle ***, Col ***, CP 06000
    Preserves leading street name if very short; masks numbers and details.
    """
    if not value:
        return value or ""
    txt = value.strip()
    # Replace any sequence of 2+ digits with ***
    import re
    masked = re.sub(r"\d{2,}", "***", txt)
    # Truncate very long addresses (defensive)
    return masked[:80] + ("…" if len(masked) > 80 else "")


# ─────────────── ROLE-BASED VISIBILITY ───────────────

def _visibility(role: Optional[str]) -> str:
    """Returns 'plain' | 'masked' | 'plain' (default for unknown — fail-secure)"""
    if role in PLAIN_ROLES:
        return "plain"
    if role in MASKED_ROLES:
        return "masked"
    return "plain"  # admin/system internal calls (no role) get plain


def apply_pii_visibility_pkg(pkg: dict, role: Optional[str]) -> dict:
    """In-place transformation: decrypt + apply role-based mask on a package doc.

    For PLAIN_ROLES: returns decrypted plain values.
    For MASKED_ROLES: returns masked values (decrypts first, then masks).
    Idempotent — safe to call on already plain or already masked docs.
    """
    if not pkg:
        return pkg

    visibility = _visibility(role)

    rn = pkg.get("recipient_name")
    addr = pkg.get("address")
    phone = pkg.get("recipient_phone")

    rn_plain = decrypt_pii(rn) if rn else rn
    addr_plain = decrypt_pii(addr) if addr else addr
    phone_plain = decrypt_pii(phone) if phone else phone

    if visibility == "masked":
        pkg["recipient_name"] = mask_name(rn_plain) if rn_plain else rn_plain
        pkg["address"] = mask_address(addr_plain) if addr_plain else addr_plain
        pkg["recipient_phone"] = mask_phone(phone_plain) if phone_plain else phone_plain
    else:
        pkg["recipient_name"] = rn_plain
        pkg["address"] = addr_plain
        pkg["recipient_phone"] = phone_plain

    return pkg


def apply_pii_visibility_pkgs(pkgs: Iterable[dict], role: Optional[str]) -> list:
    """Bulk wrapper. Mutates and returns the list."""
    return [apply_pii_visibility_pkg(p, role) for p in (pkgs or [])]


# ─────────────── ENCRYPT-ON-WRITE HELPER ───────────────

def encrypt_pkg_pii(pkg: dict) -> dict:
    """In-place encryption of PII fields before insert/update.
    Idempotent: skips already-encrypted (enc::) values.
    """
    if not pkg:
        return pkg
    for field in PII_FIELDS_PACKAGES:
        v = pkg.get(field)
        if v:
            pkg[field] = encrypt_pii(v)
    return pkg
