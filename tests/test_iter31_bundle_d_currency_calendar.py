"""Iter31 — Bundle D · Currency + Calendar services."""
from __future__ import annotations
from datetime import date, datetime, timezone, timedelta

import pytest

from services.currency import CurrencyService, currency_service, SEED_RATES
from services.calendar import (
    MxCalendarService, mx_calendar, festivos_mx_para_anio,
    seed_holidays_if_empty, _easter_sunday,
)


# ─── CurrencyService ─────────────────────────────────────────────────────
def test_currency_format_mxn():
    assert CurrencyService.format(1234.5, "MXN") == "$1,234.50 MXN"


def test_currency_format_usd():
    assert CurrencyService.format(87.30, "USD") == "USD $87.30"


def test_currency_format_other():
    assert CurrencyService.format(100, "EUR") == "EUR 100.00"


def test_currency_format_null():
    assert CurrencyService.format(None) == "—"


@pytest.mark.asyncio
async def test_currency_get_rate_identity(db):
    info = await currency_service.get_rate("USD", "USD")
    assert info.rate == 1.0
    assert info.source == "identity"


@pytest.mark.asyncio
async def test_currency_get_rate_uses_seed_by_default(db):
    # Sin manual override → seed
    await db.currency_rates_manual.delete_many({})
    await db.currency_rates_history.delete_many({})
    info = await currency_service.get_rate("USD", "MXN")
    assert info.rate == SEED_RATES[("USD", "MXN")]
    # Debe persistir en historial
    last = await db.currency_rates_history.find_one(
        {"from_curr": "USD", "to_curr": "MXN"}, {"_id": 0},
        sort=[("fetched_at", -1)],
    )
    assert last is not None
    assert last["source"] == "seed"


@pytest.mark.asyncio
async def test_currency_manual_override_wins(db):
    await db.currency_rates_manual.delete_many({})
    await db.currency_rates_history.delete_many({})
    await db.currency_rates_manual.insert_one({
        "id": "test-manual", "from_curr": "USD", "to_curr": "MXN",
        "rate": 99.99, "updated_at": "2026-01-01T00:00:00+00:00",
    })
    info = await currency_service.get_rate("USD", "MXN")
    assert info.rate == 99.99
    assert info.source == "manual_override"


@pytest.mark.asyncio
async def test_currency_convert(db):
    await db.currency_rates_manual.delete_many({})
    await db.currency_rates_history.delete_many({})
    result = await currency_service.convert(10, "USD", "MXN")
    assert result["amount"] == round(10 * SEED_RATES[("USD", "MXN")], 4)


# ─── MxCalendarService ───────────────────────────────────────────────────
def test_easter_2026():
    assert _easter_sunday(2026) == date(2026, 4, 5)


def test_easter_2027():
    # Pascua 2027 conocida: 28-mar
    assert _easter_sunday(2027) == date(2027, 3, 28)


def test_festivos_anio_2026_contains_main():
    items = festivos_mx_para_anio(2026)
    dates = {h["date"] for h in items}
    assert "2026-01-01" in dates  # Año Nuevo
    assert "2026-09-16" in dates  # Independencia
    assert "2026-05-01" in dates  # Trabajo
    assert "2026-12-25" in dates  # Navidad


@pytest.mark.asyncio
async def test_calendar_seed_holidays(db):
    # Limpiar y sembrar
    await db.mx_holidays.delete_many({"tenant_id": None})
    from services.calendar import _SEEDED  # noqa: F401
    import services.calendar as cal_mod
    cal_mod._SEEDED = False
    inserted = await seed_holidays_if_empty()
    assert inserted > 0
    count = await db.mx_holidays.count_documents({"tenant_id": None})
    # 5 años × 11 festivos = 55
    assert count == 55


@pytest.mark.asyncio
async def test_calendar_is_holiday_independencia(db):
    import services.calendar as cal_mod
    cal_mod._SEEDED = False
    await seed_holidays_if_empty()
    # 16-sep-2026
    assert await mx_calendar.is_holiday(date(2026, 9, 16)) is True


@pytest.mark.asyncio
async def test_calendar_is_business_day_sabado(db):
    # Sábado siempre False
    assert await mx_calendar.is_business_day(date(2026, 5, 16)) is False


@pytest.mark.asyncio
async def test_calendar_is_business_day_regular_monday(db):
    # 11-mayo-2026 lunes regular (no feriado)
    assert await mx_calendar.is_business_day(date(2026, 5, 11)) is True


@pytest.mark.asyncio
async def test_calendar_add_business_days_skips_holiday(db):
    import services.calendar as cal_mod
    cal_mod._SEEDED = False
    await seed_holidays_if_empty()
    # Sumar 3 días hábiles desde lunes 14-sep-2026:
    #   +1 → mar 15-sep
    #   +1 → jue 17-sep (salta mié 16-sep — Día de la Independencia)
    #   +1 → vie 18-sep
    result = await mx_calendar.add_business_days(date(2026, 9, 14), 3)
    assert result == date(2026, 9, 18)


@pytest.mark.asyncio
async def test_calendar_add_business_days_skips_weekend(db):
    # Viernes +1 día hábil → lunes
    result = await mx_calendar.add_business_days(date(2026, 5, 15), 1)
    assert result == date(2026, 5, 18)


@pytest.mark.asyncio
async def test_calendar_add_business_days_zero(db):
    # 0 días = mismo día
    result = await mx_calendar.add_business_days(date(2026, 5, 11), 0)
    assert result == date(2026, 5, 11)
