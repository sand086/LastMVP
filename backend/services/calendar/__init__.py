"""MxCalendarService — Bundle D · Parte 2 (Mayo 2026).

Servicio de calendario mexicano con festivos nacionales + opcionales.

Colección `mx_holidays`:
    {
      id: uuid,
      tenant_id: uuid | None,   # None = nacional, aplica a todos
      date: "YYYY-MM-DD",
      name: str,
      is_optional: bool,
      category: "nacional" | "optativo" | "tenant_specific",
      created_at: ISO,
    }

Seed determinista de festivos 2026-2030 con cálculo de fechas móviles
(primer lunes de feb / tercer lunes de mar/nov / Pascua para Jueves/Viernes
Santo).
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from core.db import get_db
from core.uuid import new_id

_INDEX_CREATED = False
_SEEDED = False


async def _ensure_index() -> None:
    global _INDEX_CREATED
    if _INDEX_CREATED:
        return
    db = get_db()
    await db.mx_holidays.create_index(
        [("tenant_id", 1), ("date", 1)], unique=True,
    )
    await db.mx_holidays.create_index([("date", 1)])
    _INDEX_CREATED = True


# ─── Fechas móviles ──────────────────────────────────────────────────────
def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """Devuelve la fecha del n-ésimo `weekday` (0=Lun..6=Dom) del `month`/`year`."""
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return date(year, month, 1 + offset + (n - 1) * 7)


def _easter_sunday(year: int) -> date:
    """Algoritmo de Gauss/Meeus/Jones/Butcher para Pascua occidental."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    month = (h + L - 7 * m + 114) // 31
    day = ((h + L - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def festivos_mx_para_anio(year: int) -> list[dict]:
    """Devuelve lista de festivos para `year` con su categoría."""
    easter = _easter_sunday(year)
    jueves_santo = easter - timedelta(days=3)
    viernes_santo = easter - timedelta(days=2)
    items = [
        (date(year, 1, 1),                       "Año Nuevo",                      "nacional"),
        (_nth_weekday_of_month(year, 2, 0, 1),   "Día de la Constitución",         "nacional"),
        (_nth_weekday_of_month(year, 3, 0, 3),   "Natalicio de Benito Juárez",     "nacional"),
        (jueves_santo,                            "Jueves Santo",                   "optativo"),
        (viernes_santo,                           "Viernes Santo",                  "optativo"),
        (date(year, 5, 1),                        "Día del Trabajo",                "nacional"),
        (date(year, 9, 16),                       "Día de la Independencia",        "nacional"),
        (date(year, 11, 2),                       "Día de Muertos",                 "optativo"),
        (_nth_weekday_of_month(year, 11, 0, 3),   "Día de la Revolución",           "nacional"),
        (date(year, 12, 12),                      "Día de la Virgen de Guadalupe",  "optativo"),
        (date(year, 12, 25),                      "Navidad",                        "nacional"),
    ]
    return [
        {"date": d.isoformat(), "name": name, "category": cat,
         "is_optional": cat == "optativo"}
        for d, name, cat in items
    ]


async def seed_holidays_if_empty() -> int:
    """Inserta festivos 2026-2030 si la colección está vacía.
    Idempotente — el índice unique impide duplicados; igual hacemos un check
    para evitar inserts innecesarios."""
    global _SEEDED
    if _SEEDED:
        return 0
    await _ensure_index()
    db = get_db()
    count = await db.mx_holidays.count_documents({"tenant_id": None}, limit=1)
    if count > 0:
        _SEEDED = True
        return 0

    docs = []
    for year in range(2026, 2031):
        for h in festivos_mx_para_anio(year):
            docs.append({
                "id": new_id(),
                "tenant_id": None,
                "date": h["date"],
                "name": h["name"],
                "is_optional": h["is_optional"],
                "category": h["category"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
    try:
        await db.mx_holidays.insert_many(docs, ordered=False)
    except Exception:  # noqa: BLE001
        # ignore duplicados — el seed es idempotente
        pass
    _SEEDED = True
    return len(docs)


class MxCalendarService:
    """API de calendario mexicano."""

    async def is_holiday(self, dt: date, tenant_id: Optional[str] = None,
                         respect_optional: bool = False) -> bool:
        await _ensure_index()
        db = get_db()
        date_str = dt.isoformat() if isinstance(dt, date) else str(dt)[:10]
        query = {"date": date_str,
                 "$or": [{"tenant_id": None}, {"tenant_id": tenant_id}]}
        if not respect_optional:
            query["is_optional"] = False
        return await db.mx_holidays.find_one(query, {"_id": 0, "id": 1}) is not None

    async def is_business_day(self, dt: date, tenant_id: Optional[str] = None,
                              respect_optional: bool = False) -> bool:
        # Excluir sáb/dom + festivos
        if dt.weekday() >= 5:
            return False
        return not await self.is_holiday(dt, tenant_id, respect_optional)

    async def add_business_days(self, dt: date, days: int,
                                tenant_id: Optional[str] = None,
                                respect_optional: bool = False) -> date:
        current = dt
        remaining = int(days)
        # Avanzar día por día — alcanza para días pequeños (SLA típico < 14d).
        step = 1 if remaining >= 0 else -1
        while remaining != 0:
            current = current + timedelta(days=step)
            if await self.is_business_day(current, tenant_id, respect_optional):
                remaining -= step
        return current

    async def next_business_day(self, dt: date,
                                tenant_id: Optional[str] = None,
                                respect_optional: bool = False) -> date:
        return await self.add_business_days(dt, 1, tenant_id, respect_optional)


# Singleton
mx_calendar = MxCalendarService()
