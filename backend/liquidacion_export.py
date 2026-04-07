"""
Liquidacion Export — Generates the "Liquidación del Servicio por Proveedor" Excel
in the Belgos/SOP format for operational review and provider reconciliation.
"""
from datetime import datetime, timezone
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
from openpyxl.utils import get_column_letter

DEFAULT_SLA_PACKAGES = 40

# ── Styles ──
_DARK_FILL = PatternFill(start_color="2E3B4E", end_color="2E3B4E", fill_type="solid")
_MED_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
_FORMULA_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
_ALT_FILL = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
_WHITE_FILL = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
_WHITE_FONT = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
_NORMAL_FONT = Font(name="Calibri", size=10)
_BOLD_FONT = Font(name="Calibri", size=10, bold=True)
_THIN = Border(
    left=Side(style="thin", color="D9D9D9"),
    right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),
    bottom=Side(style="thin", color="D9D9D9"),
)
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)


def _auto_width(ws, min_width=12):
    for col_cells in ws.columns:
        max_len = min_width
        col_letter = None
        for cell in col_cells:
            if hasattr(cell, 'column_letter'):
                col_letter = cell.column_letter
            try:
                if cell.value and hasattr(cell, 'column_letter'):
                    max_len = max(max_len, min(len(str(cell.value)), 30))
            except Exception:
                pass
        if col_letter:
            ws.column_dimensions[col_letter].width = max_len + 2


def _write_header_cell(ws, row, col, value, fill=None, font=None):
    cell = ws.cell(row=row, column=col, value=value)
    cell.fill = fill or _MED_FILL
    cell.font = font or _WHITE_FONT
    cell.alignment = _CENTER
    cell.border = _THIN
    return cell


def _write_data_cell(ws, row, col, value, is_formula=False, is_alt=False, fmt=None):
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = _NORMAL_FONT
    cell.alignment = _CENTER
    cell.border = _THIN
    if is_formula:
        cell.fill = _FORMULA_FILL
    elif is_alt:
        cell.fill = _ALT_FILL
    else:
        cell.fill = _WHITE_FILL
    if fmt:
        cell.number_format = fmt
    return cell


# ═══════════════════════════════════════════════════
# Sheet 1: Formato (template)
# ═══════════════════════════════════════════════════
def _build_formato_sheet(wb):
    ws = wb.create_sheet("Formato")
    headers = [
        "Fecha", "Nombre del Operador", "Sitio de Carga", "Tipo de Servicio",
        "Placas", "Ruta Cubbo", "Paquetes a ruta", "Entregas",
        "Entregas Fallidas", "Devuelto s/ Visita-Intento", "Entregado Final",
        "Tipo de unidad", "Importe", "% Efectividad",
    ]
    for c, h in enumerate(headers, 1):
        _write_header_cell(ws, 1, c, h)

    # Example row with formulas
    example = [
        "2026-05-16", "Juanito P", "CDMX", "Carga", "xxxxxxxx", "N/a",
        40, 35, 4, 1, None, "Sedan", 1300, None,
    ]
    for c, v in enumerate(example, 1):
        _write_data_cell(ws, 2, c, v)
    # Formulas
    ws.cell(row=2, column=11, value="=H2+I2").fill = _FORMULA_FILL
    ws.cell(row=2, column=11).border = _THIN
    ws.cell(row=2, column=14, value="=K2/G2").fill = _FORMULA_FILL
    ws.cell(row=2, column=14).border = _THIN
    ws.cell(row=2, column=14).number_format = "0%"
    _auto_width(ws)


# ═══════════════════════════════════════════════════
# Sheet 2: Provider sheet (main)
# ═══════════════════════════════════════════════════
def _build_provider_sheet(wb, provider_name, rows_data, sla_packages=40):
    ws = wb.create_sheet(provider_name[:31])  # Excel sheet name limit

    # ── Row 1: Group headers ──
    # Provider name (A-M)
    cell = ws.merge_cells("A1:M1")
    _write_header_cell(ws, 1, 1, provider_name, _DARK_FILL)
    # Detalle Paq M&E (N-S)
    ws.merge_cells("N1:S1")
    _write_header_cell(ws, 1, 14, "Detalle Paq M&E", _DARK_FILL)
    # Diferencias (T-V)
    ws.merge_cells("T1:V1")
    _write_header_cell(ws, 1, 20, "Diferencias Paquetes M&E", _DARK_FILL)
    # Montos (W-AB)
    ws.merge_cells("W1:AB1")
    _write_header_cell(ws, 1, 23, "Montos por Facturar", _DARK_FILL)

    # ── Row 2: Column headers ──
    col_headers = [
        "Fecha", "Nombre del Operador", "Sitio de Carga", "Tipo de Servicio",
        "Placas", "Ruta Cubbo", "Paquetes a ruta", "Entregas",
        "Entregas Fallidas", "Devuelto s/ Visita-Intento", "Recolectado",
        "Tipo de unidad", "Importe",
        # M&E columns
        "Paquetes Cargados", "Completados", "Cancelados", "Pendientes",
        "Completados c/ Evidencia", "Completados s/ Evidencia",
        # Differences
        "Dif. Carga", "Dif. Entrega", "Pend./Cancel.",
        # Montos
        "Procedentes a Cobro", "Costo x Pq", "Incidencias", "Total",
        "% Efectividad", f"% Efect. SLA {sla_packages}",
    ]
    for c, h in enumerate(col_headers, 1):
        fill = _FORMULA_FILL if c >= 20 else _MED_FILL
        font = _BOLD_FONT if c >= 20 else _WHITE_FONT
        _write_header_cell(ws, 2, c, h, fill, font)

    # ── Data rows grouped by driver ──
    # Sort by driver, then date
    sorted_rows = sorted(rows_data, key=lambda r: (r.get("driver", ""), r.get("fecha", "")))

    current_driver = None
    data_row = 3
    for row in sorted_rows:
        # Insert separator between drivers
        if current_driver is not None and row.get("driver") != current_driver:
            data_row += 1  # empty row
        current_driver = row.get("driver", "")

        r = data_row
        is_alt = (r % 2 == 0)
        delivered = row.get("completados", 0) or 0
        total_pkgs = row.get("total_paquetes", 0) or 0
        cancelled = row.get("cancelados", 0) or 0
        failed = max(0, total_pkgs - delivered - cancelled)

        # A-M: Provider data columns
        fecha_str = str(row.get("fecha", ""))[:10]  # Truncate to YYYY-MM-DD
        _write_data_cell(ws, r, 1, fecha_str, is_alt=is_alt)
        _write_data_cell(ws, r, 2, row.get("driver", ""), is_alt=is_alt)
        _write_data_cell(ws, r, 3, row.get("estado", ""), is_alt=is_alt)
        _write_data_cell(ws, r, 4, row.get("tipo_servicio", ""), is_alt=is_alt)
        _write_data_cell(ws, r, 5, row.get("placas", ""), is_alt=is_alt)
        _write_data_cell(ws, r, 6, row.get("order_id", ""), is_alt=is_alt)
        _write_data_cell(ws, r, 7, total_pkgs, is_alt=is_alt)
        _write_data_cell(ws, r, 8, delivered, is_alt=is_alt)
        _write_data_cell(ws, r, 9, failed, is_alt=is_alt)
        _write_data_cell(ws, r, 10, cancelled, is_alt=is_alt)
        _write_data_cell(ws, r, 11, f"=G{r}", is_formula=True)  # Recolectado = Paquetes a ruta
        _write_data_cell(ws, r, 12, row.get("tipo_unidad", ""), is_alt=is_alt)
        _write_data_cell(ws, r, 13, row.get("costo", 0) or 0, is_alt=is_alt, fmt='$#,##0.00')

        # N-S: M&E data
        _write_data_cell(ws, r, 14, total_pkgs, is_alt=is_alt)
        _write_data_cell(ws, r, 15, delivered, is_alt=is_alt)
        _write_data_cell(ws, r, 16, cancelled, is_alt=is_alt)
        _write_data_cell(ws, r, 17, row.get("pendientes", 0) or 0, is_alt=is_alt)
        _write_data_cell(ws, r, 18, row.get("con_evidencia", 0) or 0, is_alt=is_alt)
        _write_data_cell(ws, r, 19, row.get("sin_evidencia", 0) or 0, is_alt=is_alt)

        # T-V: Differences (formulas)
        _write_data_cell(ws, r, 20, f"=G{r}-N{r}", is_formula=True)
        _write_data_cell(ws, r, 21, f"=(H{r}+I{r})-O{r}", is_formula=True)
        _write_data_cell(ws, r, 22, f"=P{r}+Q{r}", is_formula=True)

        # W-AB: Montos (formulas)
        _write_data_cell(ws, r, 23, f"=V{r}", is_formula=True)  # Procedentes a Cobro
        _write_data_cell(ws, r, 24, f"=IFERROR(M{r}/{sla_packages},0)", is_formula=True, fmt='$#,##0.00')
        _write_data_cell(ws, r, 25, "", is_formula=True, fmt='$#,##0.00')  # Incidencias (manual)
        _write_data_cell(ws, r, 26, f"=M{r}-Y{r}", is_formula=True, fmt='$#,##0.00')
        _write_data_cell(ws, r, 27, f"=IFERROR(O{r}/N{r},0)", is_formula=True, fmt='0%')
        _write_data_cell(ws, r, 28, f"=IFERROR(O{r}/{sla_packages},0)", is_formula=True, fmt='0%')

        data_row += 1

    # ── Side table: pivot by driver (col AD+) ──
    _write_header_cell(ws, 2, 30, "Team")
    _write_header_cell(ws, 2, 31, "Driver")
    _write_header_cell(ws, 2, 32, "Fecha")
    _write_header_cell(ws, 2, 33, "Total Paquetes")
    _write_header_cell(ws, 2, 34, "Completados")
    _write_header_cell(ws, 2, 35, "Cancelados")
    _write_header_cell(ws, 2, 36, "Pendientes")
    _write_header_cell(ws, 2, 37, "Con Evidencia")
    _write_header_cell(ws, 2, 38, "Sin Evidencia")

    pivot_row = 3
    for row in sorted_rows:
        _write_data_cell(ws, pivot_row, 30, row.get("team", ""))
        _write_data_cell(ws, pivot_row, 31, row.get("driver", ""))
        _write_data_cell(ws, pivot_row, 32, str(row.get("fecha", ""))[:10])
        _write_data_cell(ws, pivot_row, 33, row.get("total_paquetes", 0))
        _write_data_cell(ws, pivot_row, 34, row.get("completados", 0))
        _write_data_cell(ws, pivot_row, 35, row.get("cancelados", 0))
        _write_data_cell(ws, pivot_row, 36, row.get("pendientes", 0))
        _write_data_cell(ws, pivot_row, 37, row.get("con_evidencia", 0))
        _write_data_cell(ws, pivot_row, 38, row.get("sin_evidencia", 0))
        pivot_row += 1

    # Freeze panes
    ws.freeze_panes = "B3"
    _auto_width(ws)


# ═══════════════════════════════════════════════════
# Sheet 3: Incidencias a cobro
# ═══════════════════════════════════════════════════
def _build_incidencias_sheet(wb, incidents_data, comments_data):
    ws = wb.create_sheet("Incidencias a cobro")
    headers = ["#", "RUTA", "Operador", "Guías", "MONTO"]
    for c, h in enumerate(headers, 1):
        _write_header_cell(ws, 1, c, h)

    row_idx = 2
    # From incidents collection
    for inc in incidents_data:
        _write_data_cell(ws, row_idx, 1, row_idx - 1)
        _write_data_cell(ws, row_idx, 2, inc.get("route_id", ""))
        _write_data_cell(ws, row_idx, 3, inc.get("driver", ""))
        _write_data_cell(ws, row_idx, 4, inc.get("guide", ""))
        _write_data_cell(ws, row_idx, 5, inc.get("amount", ""), fmt='$#,##0.00')
        row_idx += 1

    # From AI comments — parse guides with evidence issues
    for cd in comments_data:
        comments = cd.get("comentarios", "")
        if not comments or comments == "Sin incidencias":
            continue
        lines = [l.strip() for l in comments.split("\n") if l.strip()]
        for line in lines:
            # Lines that look like tracking numbers (not descriptions)
            if len(line) < 30 and not line.startswith("No se") and not line.startswith("Sin"):
                _write_data_cell(ws, row_idx, 1, row_idx - 1)
                _write_data_cell(ws, row_idx, 2, cd.get("order_id", ""))
                _write_data_cell(ws, row_idx, 3, cd.get("driver", ""))
                _write_data_cell(ws, row_idx, 4, line)
                _write_data_cell(ws, row_idx, 5, "", fmt='$#,##0.00')
                row_idx += 1

    if row_idx == 2:
        _write_data_cell(ws, 2, 1, "")
        _write_data_cell(ws, 2, 2, "Sin incidencias en el período")

    _auto_width(ws)


# ═══════════════════════════════════════════════════
# Sheet 4: Catalogo_Drivers
# ═══════════════════════════════════════════════════
def _build_catalogo_sheet(wb, all_rows):
    ws = wb.create_sheet("Catalogo_Drivers")
    headers = ["Data M&E", "Proveedor", "Data Proveedor"]
    for c, h in enumerate(headers, 1):
        _write_header_cell(ws, 1, c, h)

    seen = set()
    row_idx = 2
    for r in sorted(all_rows, key=lambda x: (x.get("proveedor", ""), x.get("driver", ""))):
        key = (r.get("driver", ""), r.get("proveedor", ""))
        if key in seen:
            continue
        seen.add(key)
        _write_data_cell(ws, row_idx, 1, r.get("driver", ""))
        _write_data_cell(ws, row_idx, 2, r.get("proveedor", ""))
        _write_data_cell(ws, row_idx, 3, r.get("driver", ""))  # Same initially
        row_idx += 1

    _auto_width(ws)


# ═══════════════════════════════════════════════════
# Sheet 5: route_summary (raw data)
# ═══════════════════════════════════════════════════
def _build_route_summary_sheet(wb, all_rows):
    ws = wb.create_sheet("route_summary")

    all_cols = [
        ("order_id", "ORDER ID"), ("fecha", "Fecha"), ("driver", "Driver"), ("team", "Team"),
        ("tipo_unidad", "Tipo de unidad"), ("estado", "Estado"), ("tipo_servicio", "Tipo de servicio"),
        ("proveedor", "Proveedor"), ("costo", "Costo"), ("pv", "PV"),
        ("horario_asistencia", "Horario de asistencia"), ("hora_entrada", "Hora de entrada"),
        ("hora_salida", "Hora de salida"), ("tolerancia", "Tolerancia"),
        ("asistencia_en_tiempo", "Asistencia en tiempo"),
        ("horas_laboradas", "Horas laboradas"), ("distancia_km", "Distancia (KM)"),
        ("km_excedente", "KM excedente"), ("tipo_tarifa", "Tipo de tarifa"),
        ("costo_km_adicional", "Costo por KM adicional"), ("backup_activado", "Backup?"),
        ("hora_inicio_backup", "Hora inicio backup"), ("horas_laboradas_backup", "Hrs backup"),
        ("total_paquetes", "Total de paquetes"), ("completados", "Completados"),
        ("cancelados", "Cancelados"), ("pendientes", "Pendientes"),
        ("con_evidencia", "Completados con evidencia"), ("sin_evidencia", "Completados sin evidencia"),
        ("score_ia", "Score IA"), ("comentarios", "Comentarios"), ("driver_courier", "Driver Courier"),
    ]

    # Row 1-2: Totals summary
    total_rutas = len(all_rows)
    total_dias = len(set(r.get("fecha", "") for r in all_rows))
    total_pkgs = sum(r.get("total_paquetes", 0) or 0 for r in all_rows)
    total_completados = sum(r.get("completados", 0) or 0 for r in all_rows)
    total_con_ev = sum(r.get("con_evidencia", 0) or 0 for r in all_rows)
    total_costo = sum(r.get("costo", 0) or 0 for r in all_rows)

    summary_labels = ["Total rutas", "Días operados", "Total paquetes", "Completados", "Con evidencia", "Costo total"]
    summary_values = [total_rutas, total_dias, total_pkgs, total_completados, total_con_ev, total_costo]
    for c, label in enumerate(summary_labels, 1):
        cell = ws.cell(row=1, column=c, value=label)
        cell.font = _BOLD_FONT
        cell.fill = _DARK_FILL
        cell.font = _WHITE_FONT
        cell.border = _THIN
    for c, val in enumerate(summary_values, 1):
        cell = ws.cell(row=2, column=c, value=val)
        cell.font = _BOLD_FONT
        cell.border = _THIN
        if c == 6:
            cell.number_format = '$#,##0.00'

    # Row 3: empty separator
    # Row 4: Headers
    for c, (key, label) in enumerate(all_cols, 1):
        _write_header_cell(ws, 4, c, label, _MED_FILL)

    # Row 5+: Data
    for row_idx, row in enumerate(all_rows, 5):
        for c, (key, _) in enumerate(all_cols, 1):
            if key == "driver_courier":
                # XLOOKUP formula
                val = f"=IFERROR(XLOOKUP(C{row_idx},Catalogo_Drivers!A:A,Catalogo_Drivers!C:C),\"\")"
                _write_data_cell(ws, row_idx, c, val, is_formula=True)
            else:
                val = row.get(key)
                if val is None:
                    val = ""
                elif isinstance(val, bool):
                    val = "Si" if val else "No"
                is_alt = (row_idx % 2 == 0)
                fmt = None
                if key in ("costo", "pv", "costo_km_adicional"):
                    fmt = '$#,##0.00'
                _write_data_cell(ws, row_idx, c, val, is_alt=is_alt, fmt=fmt)

    ws.freeze_panes = "A5"
    _auto_width(ws)


# ═══════════════════════════════════════════════════
# Main generator
# ═══════════════════════════════════════════════════
async def generate_liquidacion_excel(db, all_rows, date_from, date_to, sla_config=None):
    """Generate the full Liquidación Excel workbook."""

    if sla_config is None:
        sla_config = {"default_sla": DEFAULT_SLA_PACKAGES, "by_provider": {}}

    default_sla = sla_config.get("default_sla", DEFAULT_SLA_PACKAGES)
    by_provider_sla = sla_config.get("by_provider", {})

    # Fetch incidents for the period
    journey_ids = [r.get("journey_id") for r in all_rows if r.get("journey_id")]
    incidents_raw = []
    if journey_ids:
        incidents_raw = await db.incidents.find(
            {"journey_id": {"$in": journey_ids}},
            {"_id": 0}
        ).to_list(5000)

    incidents_data = []
    for inc in incidents_raw:
        # Find the matching row
        matching_row = next((r for r in all_rows if r.get("journey_id") == inc.get("journey_id")), {})
        incidents_data.append({
            "route_id": matching_row.get("order_id", ""),
            "driver": matching_row.get("driver", ""),
            "guide": inc.get("tracking_number", inc.get("description", "")),
            "amount": inc.get("amount", inc.get("cost", "")),
        })

    # Build AI comments for incidencias parsing
    comments_data = [r for r in all_rows if r.get("comentarios") and r.get("comentarios") != "Sin incidencias"]

    # Group by provider
    by_provider = {}
    for row in all_rows:
        prov = row.get("proveedor", "Sin proveedor")
        by_provider.setdefault(prov, []).append(row)

    # Build workbook
    wb = Workbook()
    wb.remove(wb.active)  # Remove default sheet

    _build_formato_sheet(wb)

    for prov_name in sorted(by_provider.keys()):
        # Resolve SLA: check by provider name first, then by provider ID, fallback to default
        prov_sla = default_sla
        if prov_name in by_provider_sla:
            prov_sla = by_provider_sla[prov_name]
        else:
            # Check if any row has a provider_id that matches a key in by_provider_sla
            sample_row = by_provider[prov_name][0] if by_provider[prov_name] else {}
            prov_id = sample_row.get("provider_id", "")
            if prov_id and prov_id in by_provider_sla:
                prov_sla = by_provider_sla[prov_id]
        _build_provider_sheet(wb, prov_name, by_provider[prov_name], sla_packages=prov_sla)

    _build_incidencias_sheet(wb, incidents_data, comments_data)
    _build_catalogo_sheet(wb, all_rows)
    _build_route_summary_sheet(wb, all_rows)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
