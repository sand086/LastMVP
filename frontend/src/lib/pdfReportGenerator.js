/**
 * PDF Report Generator — Multi-page, legible, complete LastMile OS report.
 *
 * Uses jsPDF + jspdf-autotable for native PDF tables.
 * Donut/pie charts are rendered natively (no html2canvas) to avoid cut-off text.
 *
 * Revisión 2026-04-24 — 13 correcciones solicitadas por usuario:
 *   1. Cards pag.1 no se cortan (altura + font + splitTextToSize)
 *   2. "Tasa de entrega" compara vs target (no vs periodo anterior sin contexto)
 *   3. Stats "Total/Entregados/Fallidos/Rutas/Pendientes" en tarjetas visibles
 *   4. Rutas usa total_journeys (antes total_routes → siempre 0)
 *   5. Mostrar "Pendientes/No intentados" = total - entregados - fallidos
 *   6. Donut chart nativo pag.1 con Entregados/Fallidos/Pendientes
 *   7. Donut de incidencias nativo (sin captura html2canvas)
 *   8–9. Eliminada columna "Dias op." de Proveedores y Drivers (reporte diario)
 *   10. "Analisis IA" renombrado a "Herramientas tecnologicas"
 *   11. Cards IA removidas del cover — solo aparecen en pag. Herramientas
 *   12. Paginado del texto IA corregido
 *   13. Limpieza de caracteres no-ASCII (emojis/iconos) en cards y narrativa
 */

/* ─── Color palette ─── */
const C = {
    dark: [26, 25, 22],
    sec: [107, 105, 96],
    ter: [156, 154, 146],
    green: [22, 163, 74],
    amber: [239, 159, 39],
    coral: [226, 75, 74],
    teal: [29, 158, 117],
    blue: [37, 99, 235],
    purple: [60, 52, 137],
    white: [255, 255, 255],
    headerBg: [240, 239, 236],
    surface2: [240, 239, 236],
    borderLight: [226, 224, 219],
};

const MARGIN = { left: 14, right: 14, top: 14, bottom: 14 };
const PAGE_NUM_Y_OFFSET = 8;

/* ─── Helpers ─── */
const healthColor = (val) => (val >= 90 ? C.green : val >= 70 ? C.amber : C.coral);

// jsPDF default font cannot render arbitrary Unicode (emoji, arrows, etc.).
// Keep only printable Latin-1/Latin-Ext characters + basic punctuation.
const cleanText = (s) => (s || '').toString()
    .replace(/[^\x20-\x7E\u00A0-\u024F\n\r\t]/g, '')
    .replace(/\u00A0/g, ' ')
    .trim();

const pct = (num, den, dec = 1) => den > 0 ? (num / den * 100) : 0;

function addPageFooter(pdf, pageNum, totalPages) {
    const w = pdf.internal.pageSize.getWidth();
    const h = pdf.internal.pageSize.getHeight();
    pdf.setFontSize(8);
    pdf.setTextColor(...C.ter);
    pdf.text(`Pagina ${pageNum} de ${totalPages}`, w / 2, h - PAGE_NUM_Y_OFFSET, { align: 'center' });
    pdf.text('LastMile OS - Reporte generado automaticamente', MARGIN.left, h - PAGE_NUM_Y_OFFSET);
}

function addSectionTitle(pdf, title, y) {
    pdf.setFontSize(16);
    pdf.setTextColor(...C.dark);
    pdf.setFont(undefined, 'bold');
    pdf.text(cleanText(title), MARGIN.left, y);
    pdf.setFont(undefined, 'normal');
    const w = pdf.internal.pageSize.getWidth();
    pdf.setDrawColor(...C.borderLight);
    pdf.setLineWidth(0.3);
    pdf.line(MARGIN.left, y + 2, w - MARGIN.right, y + 2);
    return y + 10;
}

/* ─── KPI card (larger, with wrapping label) ─── */
function drawKpiBlock(pdf, x, y, w, h, label, value, delta, deltaLabel) {
    pdf.setFillColor(255, 255, 255);
    pdf.roundedRect(x, y, w, h, 2, 2, 'F');
    pdf.setDrawColor(...C.borderLight);
    pdf.roundedRect(x, y, w, h, 2, 2, 'S');

    // Label (top, wrapped)
    pdf.setFontSize(9);
    pdf.setTextColor(...C.sec);
    pdf.setFont(undefined, 'normal');
    const labelLines = pdf.splitTextToSize(cleanText(label), w - 6);
    pdf.text(labelLines, x + w / 2, y + 7, { align: 'center' });

    // Value (middle, large)
    const numeric = parseFloat(String(value).replace('%', '')) || 0;
    pdf.setFontSize(22);
    pdf.setTextColor(...healthColor(numeric));
    pdf.setFont(undefined, 'bold');
    pdf.text(String(value), x + w / 2, y + h / 2 + 4, { align: 'center' });

    // Delta (bottom, with its own label)
    if (delta != null && !isNaN(delta)) {
        const dColor = delta >= 0 ? C.green : C.coral;
        const sign = delta >= 0 ? '+' : '';
        pdf.setFontSize(7.5);
        pdf.setTextColor(...dColor);
        pdf.setFont(undefined, 'bold');
        pdf.text(`${sign}${delta.toFixed(1)}pp ${deltaLabel || ''}`.trim(), x + w / 2, y + h - 4, { align: 'center' });
        pdf.setFont(undefined, 'normal');
    }
}

/* ─── Stat box (Total/Entregados/Fallidos/Pendientes/Rutas) ─── */
function drawStatBox(pdf, x, y, w, h, label, value, color) {
    pdf.setFillColor(255, 255, 255);
    pdf.roundedRect(x, y, w, h, 2, 2, 'F');
    pdf.setDrawColor(...C.borderLight);
    pdf.roundedRect(x, y, w, h, 2, 2, 'S');

    // Top strip (colored)
    pdf.setFillColor(...color);
    pdf.roundedRect(x, y, w, 2, 2, 2, 'F');

    pdf.setFontSize(8);
    pdf.setTextColor(...C.sec);
    pdf.setFont(undefined, 'normal');
    pdf.text(cleanText(label), x + w / 2, y + 7, { align: 'center' });

    pdf.setFontSize(15);
    pdf.setTextColor(...C.dark);
    pdf.setFont(undefined, 'bold');
    pdf.text(String(value ?? 0), x + w / 2, y + h - 4, { align: 'center' });
    pdf.setFont(undefined, 'normal');
}

function drawProgressBar(pdf, x, y, w, h, percentage, color) {
    pdf.setFillColor(...C.surface2);
    pdf.roundedRect(x, y, w, h, h / 2, h / 2, 'F');
    const fillW = Math.min(percentage / 100, 1) * w;
    if (fillW > 0) {
        pdf.setFillColor(...color);
        pdf.roundedRect(x, y, fillW, h, h / 2, h / 2, 'F');
    }
}

/* ─── Native donut/pie chart (no html2canvas) ─── */
function drawDonut(pdf, cx, cy, rOuter, rInner, segments) {
    const total = segments.reduce((s, x) => s + (x.value || 0), 0);
    if (total <= 0) return;
    let angle = -Math.PI / 2; // start top
    segments.forEach(seg => {
        const sweep = (seg.value / total) * 2 * Math.PI;
        if (sweep <= 0) return;
        const steps = Math.max(12, Math.ceil((sweep / (Math.PI * 2)) * 96));
        pdf.setFillColor(...seg.color);
        for (let i = 0; i < steps; i++) {
            const a1 = angle + (sweep * i / steps);
            const a2 = angle + (sweep * (i + 1) / steps);
            const x1 = cx + Math.cos(a1) * rOuter;
            const y1 = cy + Math.sin(a1) * rOuter;
            const x2 = cx + Math.cos(a2) * rOuter;
            const y2 = cy + Math.sin(a2) * rOuter;
            pdf.triangle(cx, cy, x1, y1, x2, y2, 'F');
        }
        angle += sweep;
    });
    // Inner white hole → donut effect
    if (rInner > 0) {
        pdf.setFillColor(255, 255, 255);
        pdf.circle(cx, cy, rInner, 'F');
    }
}

function drawDonutLegend(pdf, x, y, segments, total) {
    pdf.setFontSize(8);
    let ly = y;
    segments.forEach(seg => {
        if (seg.value == null) return;
        // color swatch
        pdf.setFillColor(...seg.color);
        pdf.roundedRect(x, ly - 2.5, 3, 3, 0.5, 0.5, 'F');
        pdf.setTextColor(...C.dark);
        pdf.setFont(undefined, 'bold');
        const percentage = total > 0 ? (seg.value / total * 100).toFixed(1) : '0.0';
        pdf.text(cleanText(seg.label), x + 5, ly);
        pdf.setFont(undefined, 'normal');
        pdf.setTextColor(...C.sec);
        pdf.text(`${seg.value}  (${percentage}%)`, x + 5, ly + 4);
        ly += 10;
    });
    return ly;
}

/* ═══════════════════════════════════════════════════════════════════
 * COVER PAGE
 * ═══════════════════════════════════════════════════════════════════ */
function buildCoverPage(pdf, meta, reportData, slaData, qualityData) {
    const w = pdf.internal.pageSize.getWidth();

    // Header bar
    pdf.setFillColor(...C.dark);
    pdf.rect(0, 0, w, 36, 'F');
    pdf.setFontSize(18);
    pdf.setTextColor(...C.white);
    pdf.setFont(undefined, 'bold');
    pdf.text('LastMile OS - Reporte Operativo', MARGIN.left, 16);
    pdf.setFontSize(10);
    pdf.setFont(undefined, 'normal');
    pdf.text(`Periodo: ${meta.dateFrom} a ${meta.dateTo}`, MARGIN.left, 24);
    const filterText = meta.filters?.length ? `Filtros: ${meta.filters.join(', ')}` : 'Sin filtros aplicados';
    pdf.text(cleanText(filterText), MARGIN.left, 30);
    pdf.text(`Generado: ${new Date().toLocaleString('es-MX')} por ${cleanText(meta.userName || '')}`, w - MARGIN.right, 24, { align: 'right' });

    let y = 44;

    // ── KPI CARDS (4 taller cards) ──
    const delivery = reportData?.delivery_rate || 0;
    const totalPkg = reportData?.total_packages || 0;
    const totalDelivered = reportData?.total_delivered || 0;
    const totalFailed = reportData?.total_failed || 0;
    const visitRate = totalPkg > 0 ? Math.round((totalDelivered + totalFailed) / totalPkg * 1000) / 10 : 0;
    const qualityAvg = qualityData?.summary?.avg_score || 0;
    const sla = slaData?.consolidated?.actual || delivery;
    const slaTarget = slaData?.consolidated?.target || 90;

    // Fix #2: "Tasa de entrega" compara vs target (no vs periodo anterior)
    const deliveryVsTarget = delivery - slaTarget;

    const kpiW = (w - MARGIN.left - MARGIN.right - 9) / 4;
    const kpiH = 46; // taller to avoid label cut-off
    drawKpiBlock(pdf, MARGIN.left, y, kpiW, kpiH, 'Tasa de entrega', `${delivery}%`, deliveryVsTarget, `vs target ${slaTarget}%`);
    drawKpiBlock(pdf, MARGIN.left + kpiW + 3, y, kpiW, kpiH, 'Tasa de visita', `${visitRate}%`, null);
    drawKpiBlock(pdf, MARGIN.left + (kpiW + 3) * 2, y, kpiW, kpiH, 'Calidad evidencias', `${qualityAvg}%`, null);
    drawKpiBlock(pdf, MARGIN.left + (kpiW + 3) * 3, y, kpiW, kpiH, 'SLA vs Target', `${sla}%`, sla - slaTarget, `vs ${slaTarget}%`);
    y += kpiH + 8;

    // ── STAT BOXES (Total/Entregados/Fallidos/Pendientes/Rutas) ──
    // Fix #3: boxes visibles
    // Fix #4: total_routes → total_journeys
    // Fix #5: Pendientes = total - entregados - fallidos
    const totalRoutes = reportData?.total_journeys || reportData?.total_routes || 0;
    const pending = Math.max(0, totalPkg - totalDelivered - totalFailed);

    const statW = (w - MARGIN.left - MARGIN.right - 12) / 5;
    const statH = 22;
    drawStatBox(pdf, MARGIN.left + 0 * (statW + 3), y, statW, statH, 'Total paquetes', totalPkg, C.blue);
    drawStatBox(pdf, MARGIN.left + 1 * (statW + 3), y, statW, statH, 'Entregados', totalDelivered, C.green);
    drawStatBox(pdf, MARGIN.left + 2 * (statW + 3), y, statW, statH, 'Fallidos', totalFailed, C.coral);
    drawStatBox(pdf, MARGIN.left + 3 * (statW + 3), y, statW, statH, 'Pendientes', pending, C.amber);
    drawStatBox(pdf, MARGIN.left + 4 * (statW + 3), y, statW, statH, 'Rutas', totalRoutes, C.purple);
    y += statH + 4;

    // Legend explaining "Pendientes"
    pdf.setFontSize(7.5);
    pdf.setTextColor(...C.ter);
    pdf.text('Pendientes = paquetes cargados sin intento exitoso ni fallo registrado (en curso / no intentados / devolucion a bodega).', MARGIN.left, y + 2);
    y += 8;

    // ── DONUT: Distribución de paquetes ──
    // Fix #6: donut nativo con 3 universos
    y = addSectionTitle(pdf, 'Distribucion de paquetes', y + 2);
    const cx = MARGIN.left + 30;
    const cy = y + 32;
    const segmentsPkg = [
        { value: totalDelivered, color: C.green, label: 'Entregados' },
        { value: totalFailed, color: C.coral, label: 'Fallidos' },
        { value: pending, color: C.amber, label: 'Pendientes' },
    ];
    drawDonut(pdf, cx, cy, 22, 12, segmentsPkg);

    // Center total
    pdf.setFontSize(13);
    pdf.setTextColor(...C.dark);
    pdf.setFont(undefined, 'bold');
    pdf.text(String(totalPkg), cx, cy - 1, { align: 'center' });
    pdf.setFont(undefined, 'normal');
    pdf.setFontSize(7);
    pdf.setTextColor(...C.sec);
    pdf.text('paquetes', cx, cy + 4, { align: 'center' });

    // Legend to the right
    drawDonutLegend(pdf, cx + 30, cy - 10, segmentsPkg, totalPkg);

    return y + 60;
}

/* ═══════════════════════════════════════════════════════════════════
 * PROVIDERS PAGE (Fix #8: sin "Dias op.")
 * ═══════════════════════════════════════════════════════════════════ */
function buildProvidersPage(pdf, reportData, slaData) {
    const provMetrics = reportData?.provider_metrics;
    pdf.addPage();
    let y = addSectionTitle(pdf, 'Proveedores', 20);

    if (!provMetrics || Object.keys(provMetrics).length === 0) {
        pdf.setFontSize(12);
        pdf.setTextColor(...C.sec);
        pdf.text('Sin datos de proveedores para este periodo.', MARGIN.left, y + 10);
        return;
    }

    const slaMap = {};
    if (slaData?.by_provider) {
        for (const p of slaData.by_provider) slaMap[p.provider_name] = p;
    }

    const headers = ['Proveedor', 'Rutas', 'Paquetes', 'Entregados', 'Entrega%', 'Visita%', 'Km', 'SLA'];
    const rows = Object.entries(provMetrics).map(([name, m]) => {
        const visitR = m.packages_loaded > 0 ? Math.round((m.delivered + m.failed) / m.packages_loaded * 1000) / 10 : 0;
        const slaActual = slaMap[name]?.sla_actual || m.delivery_rate || 0;
        return [
            cleanText(name),
            m.routes,
            m.packages_loaded,
            m.delivered,
            `${m.delivery_rate}%`,
            `${visitR}%`,
            (m.km_total || 0).toLocaleString(),
            `${slaActual}%`,
        ];
    });

    pdf.autoTable({
        startY: y,
        head: [headers],
        body: rows,
        margin: { left: MARGIN.left, right: MARGIN.right },
        styles: { fontSize: 9, cellPadding: 3, textColor: C.dark, lineColor: C.borderLight, lineWidth: 0.2 },
        headStyles: { fillColor: C.headerBg, textColor: C.dark, fontStyle: 'bold', fontSize: 9 },
        alternateRowStyles: { fillColor: [250, 249, 247] },
    });
}

/* ═══════════════════════════════════════════════════════════════════
 * DRIVERS PAGE (Fix #9: sin "Dias op.")
 * ═══════════════════════════════════════════════════════════════════ */
function buildDriversPage(pdf, reportData) {
    const driverMetrics = reportData?.driver_metrics;
    pdf.addPage();
    let y = addSectionTitle(pdf, 'Drivers', 20);

    if (!driverMetrics || Object.keys(driverMetrics).length === 0) {
        pdf.setFontSize(12);
        pdf.setTextColor(...C.sec);
        pdf.text('Sin datos de drivers para este periodo.', MARGIN.left, y + 10);
        return;
    }

    const headers = ['Driver', 'Rutas', 'Paquetes', 'Entregados', 'SLA individual', 'Km'];
    const rows = Object.entries(driverMetrics)
        .map(([name, m]) => [
            cleanText(name),
            m.routes,
            m.packages_loaded,
            m.delivered,
            `${m.delivery_rate}%`,
            (m.km_total || 0).toLocaleString(),
        ])
        .sort((a, b) => parseFloat(b[4]) - parseFloat(a[4]));

    pdf.autoTable({
        startY: y,
        head: [headers],
        body: rows,
        margin: { left: MARGIN.left, right: MARGIN.right },
        styles: { fontSize: 9, cellPadding: 3, textColor: C.dark, lineColor: C.borderLight, lineWidth: 0.2 },
        headStyles: { fillColor: C.headerBg, textColor: C.dark, fontStyle: 'bold', fontSize: 9 },
        alternateRowStyles: { fillColor: [250, 249, 247] },
    });

    const lastY = pdf.lastAutoTable?.finalY || 100;
    pdf.setFontSize(8);
    pdf.setTextColor(...C.ter);
    pdf.text('Politica de strikes: 1er aviso - 2do descanso operativo - 3ro baja. Filas con SLA <60% requieren atencion.', MARGIN.left, lastY + 8);
}

/* ═══════════════════════════════════════════════════════════════════
 * INCIDENTS PAGE (Fix #7: donut nativo, sin cut-off)
 * ═══════════════════════════════════════════════════════════════════ */
function buildIncidentsPage(pdf, reportData) {
    const incidents = reportData?.incidents_by_type || {};
    pdf.addPage();
    let y = addSectionTitle(pdf, 'Incidencias', 20);

    if (Object.keys(incidents).length === 0) {
        pdf.setFontSize(12);
        pdf.setTextColor(...C.sec);
        pdf.text('Sin incidencias registradas para este periodo.', MARGIN.left, y + 10);
        return;
    }

    // Palette for donut segments
    const palette = [C.coral, C.amber, C.blue, C.teal, C.purple, C.green, [220, 38, 127], [100, 116, 139]];
    const entries = Object.entries(incidents)
        .sort(([, a], [, b]) => b - a);
    const segments = entries.map(([label, value], i) => ({
        label, value, color: palette[i % palette.length],
    }));
    const total = segments.reduce((s, x) => s + x.value, 0);

    // Donut (left)
    const cx = MARGIN.left + 30;
    const cy = y + 32;
    drawDonut(pdf, cx, cy, 22, 12, segments);
    pdf.setFontSize(13);
    pdf.setTextColor(...C.dark);
    pdf.setFont(undefined, 'bold');
    pdf.text(String(total), cx, cy - 1, { align: 'center' });
    pdf.setFont(undefined, 'normal');
    pdf.setFontSize(7);
    pdf.setTextColor(...C.sec);
    pdf.text('incidencias', cx, cy + 4, { align: 'center' });

    // Legend (right) — cleanText on labels avoids cut-off of unicode
    drawDonutLegend(pdf, cx + 30, cy - 10, segments, total);

    // Table below
    y = cy + 36;
    const rows = entries.map(([type, count]) => [
        cleanText(type),
        count,
        total > 0 ? `${(count / total * 100).toFixed(1)}%` : '0%',
    ]);
    pdf.autoTable({
        startY: y,
        head: [['Tipo de incidencia', 'Total', '% del total']],
        body: rows,
        margin: { left: MARGIN.left, right: MARGIN.right },
        styles: { fontSize: 9, cellPadding: 3, textColor: C.dark, lineColor: C.borderLight, lineWidth: 0.2 },
        headStyles: { fillColor: C.headerBg, textColor: C.dark, fontStyle: 'bold', fontSize: 9 },
    });

    const lastY = pdf.lastAutoTable?.finalY || 100;
    pdf.setFontSize(8);
    pdf.setTextColor(...C.ter);
    pdf.text('Incidencias de zona (accesibilidad) NO penalizan el SLA del driver.', MARGIN.left, lastY + 8);
}

/* ═══════════════════════════════════════════════════════════════════
 * ATTEMPTS PAGE
 * ═══════════════════════════════════════════════════════════════════ */
function buildAttemptsPage(pdf, attemptsData) {
    pdf.addPage();
    let y = addSectionTitle(pdf, 'Intentos de entrega', 20);

    if (!attemptsData) {
        pdf.setFontSize(12);
        pdf.setTextColor(...C.sec);
        pdf.text('Sin datos de intentos para este periodo.', MARGIN.left, y + 10);
        return;
    }

    const w = pdf.internal.pageSize.getWidth();
    const contentW = w - MARGIN.left - MARGIN.right;

    pdf.setFontSize(12);
    pdf.setTextColor(...C.dark);
    pdf.setFont(undefined, 'bold');
    pdf.text('Distribucion de intentos', MARGIN.left, y);
    pdf.setFont(undefined, 'normal');
    y += 6;

    const bars = [
        { label: '1er intento', ...attemptsData.first_attempt, color: C.green },
        { label: '2do intento', ...attemptsData.second_attempt, color: C.amber },
        { label: '3er+ intento', ...attemptsData.third_attempt, color: C.coral },
    ];
    bars.forEach(b => {
        pdf.setFontSize(10);
        pdf.setTextColor(...C.sec);
        pdf.text(b.label, MARGIN.left, y + 4);
        pdf.setTextColor(...C.dark);
        pdf.setFont(undefined, 'bold');
        pdf.text(`${b.count || 0} (${b.pct || 0}%)`, MARGIN.left + 80, y + 4);
        pdf.setFont(undefined, 'normal');
        drawProgressBar(pdf, MARGIN.left + 120, y, contentW - 130, 5, b.pct || 0, b.color);
        y += 10;
    });

    y += 6;

    pdf.setFontSize(12);
    pdf.setTextColor(...C.dark);
    pdf.setFont(undefined, 'bold');
    pdf.text('Causa de reintento (2do+)', MARGIN.left, y);
    pdf.setFont(undefined, 'normal');
    y += 6;

    const causes = [
        { label: 'Gestion del driver', key: 'driver_management', color: C.coral },
        { label: 'Cliente ausente', key: 'client_absent', color: C.amber },
        { label: 'Direccion erronea', key: 'wrong_address', color: C.blue },
        { label: 'Zona sin acceso', key: 'zone_no_access', color: C.teal },
    ];
    causes.forEach(c => {
        const d = attemptsData.retry_causes?.[c.key] || { count: 0, pct: 0 };
        pdf.setFontSize(10);
        pdf.setTextColor(...C.sec);
        pdf.text(c.label, MARGIN.left, y + 4);
        pdf.setTextColor(...C.dark);
        pdf.setFont(undefined, 'bold');
        pdf.text(`${d.count} (${d.pct}%)`, MARGIN.left + 100, y + 4);
        pdf.setFont(undefined, 'normal');
        drawProgressBar(pdf, MARGIN.left + 140, y, contentW - 150, 5, d.pct, c.color);
        y += 10;
    });

    pdf.setFontSize(8);
    pdf.setTextColor(...C.ter);
    pdf.text(`Total de paquetes en periodo: ${attemptsData.total_packages || 0}. Reintentos impactan directamente el costo operativo.`, MARGIN.left, y + 6);
}

/* ═══════════════════════════════════════════════════════════════════
 * QUALITY PAGE
 * ═══════════════════════════════════════════════════════════════════ */
function buildQualityPage(pdf, qualityData) {
    pdf.addPage();
    let y = addSectionTitle(pdf, 'Evidencias - Calidad', 20);

    const summary = qualityData?.summary || {};
    const avg = summary.avg_score || 0;
    const total = summary.total_evaluated || 0;
    const complete = summary.complete || 0;
    const incomplete = summary.incomplete || 0;
    const byProvider = qualityData?.by_provider || [];
    const byType = qualityData?.by_type || [];

    if (!total && !byProvider.length) {
        pdf.setFontSize(12);
        pdf.setTextColor(...C.sec);
        pdf.text('Sin evidencias registradas para este periodo.', MARGIN.left, y + 10);
        return;
    }

    pdf.setFontSize(36);
    pdf.setTextColor(...healthColor(avg));
    pdf.setFont(undefined, 'bold');
    pdf.text(`${avg.toFixed(1)}`, MARGIN.left + 30, y + 10);
    pdf.setFontSize(10);
    pdf.setTextColor(...C.ter);
    pdf.setFont(undefined, 'normal');
    pdf.text('Score global', MARGIN.left + 30, y + 16);

    pdf.setFontSize(10);
    pdf.setTextColor(...C.sec);
    pdf.text(`Completas: ${complete}`, MARGIN.left + 80, y + 6);
    pdf.text(`Incompletas: ${incomplete}`, MARGIN.left + 80, y + 12);
    pdf.text(`Total evaluadas: ${total}`, MARGIN.left + 80, y + 18);
    drawProgressBar(pdf, MARGIN.left + 80, y + 22, 80, 4, Math.min(avg / 90 * 100, 100), avg >= 90 ? C.green : C.amber);
    pdf.setFontSize(8);
    pdf.setTextColor(...C.ter);
    pdf.text('Target: 90%', MARGIN.left + 80, y + 30);

    y += 38;

    if (byType.length > 0) {
        pdf.setFontSize(11);
        pdf.setTextColor(...C.dark);
        pdf.setFont(undefined, 'bold');
        pdf.text('Por tipo de evidencia', MARGIN.left, y);
        pdf.setFont(undefined, 'normal');
        y += 6;
        byType.forEach(t => {
            pdf.setFontSize(9);
            pdf.setTextColor(...C.sec);
            pdf.text(`${cleanText(t.type || t._id)}: ${t.count} (${t.avg_score ? t.avg_score.toFixed(0) : 0}%)`, MARGIN.left + 4, y);
            y += 5;
        });
        y += 4;
    }

    if (byProvider.length > 0) {
        pdf.setFontSize(11);
        pdf.setTextColor(...C.dark);
        pdf.setFont(undefined, 'bold');
        pdf.text('Por proveedor', MARGIN.left, y);
        pdf.setFont(undefined, 'normal');
        y += 6;
        byProvider.forEach(p => {
            const score = p.avg_score || 0;
            pdf.setFontSize(9);
            pdf.setTextColor(...C.sec);
            pdf.text(cleanText(p.provider || p._id || '?'), MARGIN.left + 4, y + 3);
            drawProgressBar(pdf, MARGIN.left + 80, y, 100, 5, score, score >= 85 ? C.green : score >= 70 ? C.amber : C.coral);
            pdf.setTextColor(...C.dark);
            pdf.setFont(undefined, 'bold');
            pdf.text(`${score.toFixed(0)}%`, MARGIN.left + 186, y + 3);
            pdf.setFont(undefined, 'normal');
            y += 8;
        });
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * SLA PAGE
 * ═══════════════════════════════════════════════════════════════════ */
function buildSLAPage(pdf, slaData) {
    pdf.addPage();
    let y = addSectionTitle(pdf, 'SLA', 20);

    if (!slaData) {
        pdf.setFontSize(12);
        pdf.setTextColor(...C.sec);
        pdf.text('Sin datos SLA para este periodo.', MARGIN.left, y + 10);
        return;
    }

    const { consolidated, by_provider, by_driver, brackets } = slaData;

    pdf.setFontSize(12);
    pdf.setTextColor(...C.dark);
    pdf.setFont(undefined, 'bold');
    pdf.text('SLA Consolidado ME - Cubbo', MARGIN.left, y);
    pdf.setFont(undefined, 'normal');
    y += 6;

    const slaColor = consolidated.actual >= consolidated.target ? C.green : C.coral;
    pdf.setFontSize(36);
    pdf.setTextColor(...slaColor);
    pdf.setFont(undefined, 'bold');
    pdf.text(`${consolidated.actual}%`, MARGIN.left + 30, y + 10);
    pdf.setFont(undefined, 'normal');
    pdf.setFontSize(10);
    pdf.setTextColor(...C.ter);
    pdf.text(`Target actual: ${consolidated.target}%`, MARGIN.left + 30, y + 16);
    drawProgressBar(pdf, MARGIN.left + 30, y + 20, 100, 5, Math.min(consolidated.actual / consolidated.target * 100, 100), slaColor);
    y += 30;

    if (brackets?.length > 0) {
        pdf.setFontSize(11);
        pdf.setTextColor(...C.dark);
        pdf.setFont(undefined, 'bold');
        pdf.text('Brackets de escalamiento', MARGIN.left, y);
        pdf.setFont(undefined, 'normal');
        y += 6;

        const statusLabels = { exceeded: 'Superado', active: 'En curso', pending: 'Pendiente' };
        const statusColors = { exceeded: C.green, active: C.amber, pending: C.ter };
        brackets.forEach(b => {
            pdf.setFontSize(9);
            pdf.setTextColor(...C.dark);
            pdf.text(cleanText(b.label), MARGIN.left + 4, y + 3);
            pdf.setFont(undefined, 'bold');
            pdf.text(`${b.target}%`, MARGIN.left + 60, y + 3);
            pdf.setFont(undefined, 'normal');
            drawProgressBar(pdf, MARGIN.left + 85, y, 80, 4, Math.min(consolidated.actual / b.target * 100, 100), statusColors[b.status] || C.ter);
            pdf.setTextColor(...(statusColors[b.status] || C.ter));
            pdf.text(statusLabels[b.status] || b.status, MARGIN.left + 170, y + 3);
            y += 8;
        });
        y += 6;
    }

    if (by_provider?.length > 0) {
        pdf.setFontSize(11);
        pdf.setTextColor(...C.dark);
        pdf.setFont(undefined, 'bold');
        pdf.text('Por proveedor', MARGIN.left, y);
        pdf.setFont(undefined, 'normal');
        y += 2;

        pdf.autoTable({
            startY: y,
            head: [['Proveedor', 'SLA actual', 'Target', 'Brecha', 'Estado']],
            body: by_provider.map(p => [
                cleanText(p.provider_name),
                `${p.sla_actual}%`,
                `${p.target}%`,
                `${p.gap_pp >= 0 ? '+' : ''}${p.gap_pp}pp`,
                p.status === 'above' ? 'OK' : 'Bajo',
            ]),
            margin: { left: MARGIN.left, right: MARGIN.right },
            styles: { fontSize: 9, cellPadding: 3, textColor: C.dark, lineColor: C.borderLight, lineWidth: 0.2 },
            headStyles: { fillColor: C.headerBg, textColor: C.dark, fontStyle: 'bold', fontSize: 9 },
        });
        y = pdf.lastAutoTable?.finalY + 8 || y + 30;
    }

    if (by_driver?.length > 0) {
        const pageH = pdf.internal.pageSize.getHeight();
        if (y + 40 > pageH - 20) { pdf.addPage(); y = 20; }

        pdf.setFontSize(11);
        pdf.setTextColor(...C.dark);
        pdf.setFont(undefined, 'bold');
        pdf.text('Top drivers', MARGIN.left, y);
        pdf.setFont(undefined, 'normal');
        y += 2;

        pdf.autoTable({
            startY: y,
            head: [['Driver', 'SLA', 'vs Target', 'Estado']],
            body: by_driver.slice(0, 10).map(d => [
                cleanText(d.driver_name),
                `${d.sla_actual}%`,
                `${d.gap_pp >= 0 ? '+' : ''}${d.gap_pp}pp`,
                d.status === 'above' ? 'OK' : 'Bajo',
            ]),
            margin: { left: MARGIN.left, right: MARGIN.right },
            styles: { fontSize: 9, cellPadding: 3, textColor: C.dark, lineColor: C.borderLight, lineWidth: 0.2 },
            headStyles: { fillColor: C.headerBg, textColor: C.dark, fontStyle: 'bold', fontSize: 9 },
        });
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * "HERRAMIENTAS TECNOLOGICAS" PAGE (Fix #10 + #11 + #12 + #13)
 * ═══════════════════════════════════════════════════════════════════ */
function buildAIPage(pdf, aiNarrative, aiCards) {
    if (!aiNarrative && !aiCards?.length) return;

    pdf.addPage();
    // Fix #10: renombrado
    let y = addSectionTitle(pdf, 'Herramientas tecnologicas', 20);
    const w = pdf.internal.pageSize.getWidth();
    const contentW = w - MARGIN.left - MARGIN.right;
    const pageH = pdf.internal.pageSize.getHeight();

    pdf.setFontSize(8);
    pdf.setTextColor(...C.ter);
    pdf.text('Analisis generado automaticamente por IA. Debe validarse operativamente.', MARGIN.left, y);
    y += 6;

    // Fix #11: Cards IA solo aparecen aqui (no en cover)
    if (aiCards?.length > 0) {
        // Taller cards with wrapped text to prevent cut-off
        const cardW = (contentW - (aiCards.length - 1) * 4) / aiCards.length;
        const cardH = 32;
        aiCards.forEach((card, i) => {
            const cx = MARGIN.left + i * (cardW + 4);
            const colors = {
                alerta: { bg: [254, 242, 242], border: C.coral },
                tendencia: { bg: [239, 246, 255], border: C.blue },
                logro: { bg: [240, 253, 244], border: C.green },
            };
            const cc = colors[card.tipo] || colors.tendencia;
            pdf.setFillColor(...cc.bg);
            pdf.roundedRect(cx, y, cardW, cardH, 2, 2, 'F');
            pdf.setDrawColor(...cc.border);
            pdf.setLineWidth(0.4);
            pdf.roundedRect(cx, y, cardW, cardH, 2, 2, 'S');

            // Title (Fix #13: cleanText removes unicode icons)
            pdf.setFontSize(9);
            pdf.setTextColor(...cc.border);
            pdf.setFont(undefined, 'bold');
            const titleLines = pdf.splitTextToSize(cleanText(card.titulo || ''), cardW - 6);
            pdf.text(titleLines.slice(0, 2), cx + 3, y + 6);

            // Body
            pdf.setFont(undefined, 'normal');
            pdf.setFontSize(7.5);
            pdf.setTextColor(...C.sec);
            const bodyLines = pdf.splitTextToSize(cleanText(card.cuerpo || ''), cardW - 6);
            const titleOffset = Math.min(titleLines.length, 2) * 4;
            pdf.text(bodyLines.slice(0, 4), cx + 3, y + 6 + titleOffset + 3);
        });
        y += cardH + 6;
    }

    // Fix #12 + #13: Narrative with correct pagination and unicode stripping
    if (aiNarrative) {
        const cleaned = cleanText(
            aiNarrative
                .replace(/#{1,6}\s*/g, '')
                .replace(/\*\*(.+?)\*\*/g, '$1')
                .replace(/\*(.+?)\*/g, '$1')
                .replace(/`(.+?)`/g, '$1')
                .replace(/\r\n/g, '\n')
        );

        pdf.setFontSize(10);
        pdf.setTextColor(...C.dark);
        pdf.setFont(undefined, 'normal');
        const lineH = 5;
        const lines = pdf.splitTextToSize(cleaned, contentW);

        let cursorY = y;
        const bottomLimit = pageH - 18; // leave room for footer
        for (const line of lines) {
            if (cursorY + lineH > bottomLimit) {
                pdf.addPage();
                cursorY = 20;
            }
            pdf.text(line, MARGIN.left, cursorY);
            cursorY += lineH;
        }
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * MAIN EXPORT
 * ═══════════════════════════════════════════════════════════════════ */
export async function generateMultiPagePDF({
    reportData, prevReportData, qualityData, attemptsData, slaData,
    aiNarrative, aiCards, meta,
}) {
    const { default: jsPDF } = await import('jspdf');
    const { applyPlugin } = await import('jspdf-autotable');
    applyPlugin(jsPDF);

    const pdf = new jsPDF('p', 'mm', 'a4');

    // Cover (KPI cards + stat boxes + packages donut — no captured charts, no AI cards)
    buildCoverPage(pdf, meta, reportData, slaData, qualityData);

    // Providers (sin Dias op.)
    buildProvidersPage(pdf, reportData, slaData);

    // Drivers (sin Dias op.)
    buildDriversPage(pdf, reportData);

    // Incidents (donut nativo + tabla con %)
    buildIncidentsPage(pdf, reportData);

    // Attempts
    buildAttemptsPage(pdf, attemptsData);

    // Quality
    buildQualityPage(pdf, qualityData);

    // SLA
    buildSLAPage(pdf, slaData);

    // Herramientas tecnologicas (antes "Analisis IA")
    buildAIPage(pdf, aiNarrative, aiCards);

    // Page numbers
    const totalPages = pdf.internal.getNumberOfPages();
    for (let i = 1; i <= totalPages; i++) {
        pdf.setPage(i);
        addPageFooter(pdf, i, totalPages);
    }

    pdf.save(`reporte_operativo_${meta.dateFrom}_${meta.dateTo}.pdf`);
}
