"""CurrencyService — Bundle D · Parte 2 (Mayo 2026).

Servicio centralizado de conversión / formato de divisas. **Sin Banxico real**
por decisión Bundle D iter31: depende del usuario configurar `BANXICO_TOKEN`
para habilitar el fetch real. Por defecto: manual override + valor seedeado.

Cache: colección Mongo `currency_rates_history` con índice TTL (12h).
Esquema:
    {
      id: uuid, from_curr: "USD", to_curr: "MXN", rate: 17.5,
      source: "manual" | "manual_override" | "banxico" | "fallback",
      fetched_at: ISO, expires_at: ISO (TTL Mongo)
    }

Tabla `currency_rates_manual` (opcional) permite a superadmin/root_dev
hardcodear tipo de cambio. Una entrada activa por (from, to).
"""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.db import get_db
from core.uuid import new_id

logger = logging.getLogger("currency")

CACHE_TTL_SECONDS = 12 * 3600  # 12 horas

# Valores seed muy conservadores (Mayo 2026). Solo aplican si NO hay manual
# override ni cache. Actualizables por superadmin vía endpoint admin.
SEED_RATES = {
    ("USD", "MXN"): 17.50,
    ("MXN", "USD"): 1.0 / 17.50,
    ("EUR", "MXN"): 19.30,
    ("MXN", "MXN"): 1.0,
    ("USD", "USD"): 1.0,
    ("EUR", "EUR"): 1.0,
}

_INDEX_CREATED = False


async def _ensure_index() -> None:
    global _INDEX_CREATED
    if _INDEX_CREATED:
        return
    db = get_db()
    await db.currency_rates_history.create_index(
        "expires_at", expireAfterSeconds=0,
    )
    await db.currency_rates_history.create_index(
        [("from_curr", 1), ("to_curr", 1), ("fetched_at", -1)],
    )
    await db.currency_rates_manual.create_index(
        [("from_curr", 1), ("to_curr", 1)], unique=True,
    )
    _INDEX_CREATED = True


@dataclass
class RateInfo:
    from_curr: str
    to_curr: str
    rate: float
    source: str
    fetched_at: str

    def as_dict(self) -> dict:
        return {
            "from": self.from_curr, "to": self.to_curr, "rate": self.rate,
            "source": self.source, "fetched_at": self.fetched_at,
        }


class CurrencyService:
    """Singleton service. Sin estado mutable."""

    async def get_rate(self, from_curr: str, to_curr: str) -> RateInfo:
        from_curr, to_curr = from_curr.upper(), to_curr.upper()
        # Mismo currency → 1.0 sin cache.
        if from_curr == to_curr:
            return RateInfo(from_curr, to_curr, 1.0, "identity",
                            datetime.now(timezone.utc).isoformat())
        await _ensure_index()
        db = get_db()

        # 1) Manual override del superadmin (siempre gana)
        manual = await db.currency_rates_manual.find_one(
            {"from_curr": from_curr, "to_curr": to_curr}, {"_id": 0},
        )
        if manual and manual.get("rate"):
            info = RateInfo(from_curr, to_curr, float(manual["rate"]),
                            "manual_override",
                            manual.get("updated_at", datetime.now(timezone.utc).isoformat()))
            await self._persist(info)
            return info

        # 2) Cache (12h)
        cached = await db.currency_rates_history.find_one(
            {"from_curr": from_curr, "to_curr": to_curr},
            {"_id": 0}, sort=[("fetched_at", -1)],
        )
        if cached and cached.get("expires_at"):
            try:
                exp = datetime.fromisoformat(cached["expires_at"])
                if exp > datetime.now(timezone.utc):
                    return RateInfo(from_curr, to_curr, float(cached["rate"]),
                                    cached.get("source", "cache"),
                                    cached["fetched_at"])
            except Exception:  # noqa: BLE001
                pass

        # 3) Banxico (deshabilitado por defecto — habilitar con BANXICO_TOKEN)
        token = os.environ["BANXICO_TOKEN"]
        if token and from_curr == "USD" and to_curr == "MXN":
            try:
                # Implementación real diferida — usar requests/httpx aquí.
                # Por iter31 dejamos placeholder con warning.
                logger.warning("BANXICO_TOKEN set but real fetch not implemented yet "
                               "(Bundle D iter31). Using seed.")
            except Exception as e:  # noqa: BLE001
                logger.error("banxico fetch failed: %s", e)

        # 4) Seed
        rate = SEED_RATES.get((from_curr, to_curr))
        if rate is None:
            # Compute via USD inversa si aplica
            via_usd_a = SEED_RATES.get((from_curr, "USD"))
            via_usd_b = SEED_RATES.get(("USD", to_curr))
            if via_usd_a and via_usd_b:
                rate = via_usd_a * via_usd_b
            else:
                # Último recurso: 1.0 — caller debe lidiar
                logger.error("no rate available for %s->%s", from_curr, to_curr)
                rate = 1.0

        info = RateInfo(from_curr, to_curr, float(rate), "seed",
                        datetime.now(timezone.utc).isoformat())
        await self._persist(info)
        return info

    async def convert(self, amount: float, from_curr: str, to_curr: str) -> dict:
        info = await self.get_rate(from_curr, to_curr)
        return {
            "amount": round(amount * info.rate, 4),
            "rate": info.rate,
            "fetched_at": info.fetched_at,
            "source": info.source,
        }

    @staticmethod
    def format(amount: Optional[float], currency: str = "MXN") -> str:
        """Formato MX. Importable sin instanciar (helper estático)."""
        if amount is None:
            return "—"
        try:
            num = float(amount)
        except (TypeError, ValueError):
            return "—"
        # Locale-aware separators: coma para miles, punto para decimal (es-MX).
        formatted = f"{num:,.2f}"
        if currency == "MXN":
            return f"${formatted} MXN"
        if currency == "USD":
            return f"USD ${formatted}"
        return f"{currency} {formatted}"

    async def _persist(self, info: RateInfo) -> None:
        """Persistir histórico para auditoría + cache TTL."""
        now = datetime.now(timezone.utc)
        doc = {
            "id": new_id(),
            "from_curr": info.from_curr,
            "to_curr": info.to_curr,
            "rate": info.rate,
            "source": info.source,
            "fetched_at": info.fetched_at,
            "expires_at": (now + timedelta(seconds=CACHE_TTL_SECONDS)).isoformat(),
        }
        try:
            await get_db().currency_rates_history.insert_one(doc)
        except Exception as e:  # noqa: BLE001
            logger.error("currency persist failed: %s", e)


# Singleton — barato, sin estado mutable.
currency_service = CurrencyService()
