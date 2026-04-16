/**
 * PDF Report Generator — Multi-page, legible, complete LastMile OS report.
 *
 * Uses jsPDF + jspdf-autotable for native PDF tables (no html2canvas screenshots).
 * Charts are rendered via html2canvas on individual elements only.
 */

/* ─── Color palette (matches Reports.jsx tokens) ─── */
const C = {
    dark: [26, 25, 22],       // #1A1916
    sec: [107, 105, 96],      // #6B6960
    ter: [156, 154, 146],     // #9C9A92
    green: [22, 163, 74],     // #16A34A
    amber: [239, 159, 39],    // #EF9F27
    coral: [226, 75, 74],     // #E24B4A
    teal: [29, 158, 117],     // #1D9E75
    blue: [37, 99, 235],      // #2563EB
    purple: [60, 52, 137],    // #3C3489
    white: [255, 255, 255],
    headerBg: [240, 239, 236], // #F0EFEC
    surface2: [240, 239, 236],
    borderLight: [226, 224, 219],
};

const MARGIN = { left: 14, right: 14, top: 14, bottom: 14 };
const PAGE_NUM_Y_OFFSET = 8;

/* ─── Helpers ─── */
function healthColor(val) {
    if (val >= 90) return C.green;
    if (val >= 70) return C.amber;
    return C.coral;
}

function formatDate(d) {
    if (!d) return '';
    return new Date(d).toLocaleDateString('es-MX', { day: 'numeric', month: 'short', year: 'numeric' });
}

function addPageFooter(pdf, pageNum, totalPages) {
    const w = pdf.internal.pageSize.getWidth();
    const h = pdf.internal.pageSize.getHeight();
    pdf.setFontSize(8);
    pdf.setTextColor(...C.ter);
    pdf.text(`Pagina ${pageNum} de ${totalPages}`, w / 2, h - PAGE_NUM_Y_OFFSET, { align: 'center' });
    pdf.text('LastMile OS — Reporte generado automaticamente', MARGIN.left, h - PAGE_NUM_Y_OFFSET);
}

function addSectionTitle(pdf, title, y) {
    pdf.setFontSize(16);
    pdf.setTextColor(...C.dark);
    pdf.setFont(undefined, 'bold');
    pdf.text(title, MARGIN.left, y);
    pdf.setFont(undefined, 'normal');
    // Underline
    const w = pdf.internal.pageSize.getWidth();
    pdf.setDrawColor(...C.borderLight);
    pdf.setLineWidth(0.3);
    pdf.line(MARGIN.left, y + 2, w - MARGIN.right, y + 2);
    return y + 10;
}

function drawKpiBlock(pdf, x, y, w, h, label, value, delta, healthVal) {
    // Background
    pdf.setFillColor(255, 255, 255);
    pdf.roundedRect(x, y, w, h, 2, 2, 'F');
    pdf.setDrawColor(...C.borderLight);
    pdf.roundedRect(x, y, w, h, 2, 2, 'S');

    // Value
    const color = healthColor(parseFloat(value) || 0);
    pdf.setFontSize(24);
    pdf.setTextColor(...color);
    pdf.setFont(undefined, 'bold');
    pdf.text(String(value), x + w / 2, y + h / 2 - 2, { align: 'center' });

    // Label
    pdf.setFontSize(9);
    pdf.setTextColor(...C.sec);
    pdf.setFont(undefined, 'normal');
    pdf.text(label, x + w / 2, y + 10, { align: 'center' });

    // Delta
    if (delta != null) {
        const dColor = delta >= 0 ? C.green : C.coral;
        const sign = delta >= 0 ? '+' : '';
        pdf.setFontSize(8);
        pdf.setTextColor(...dColor);
        pdf.text(`${sign}${delta.toFixed(1)}pp`, x + w / 2, y + h - 6, { align: 'center' });
    }
}

function drawProgressBar(pdf, x, y, w, h, pct, color) {
    pdf.setFillColor(...C.surface2);
    pdf.roundedRect(x, y, w, h, h / 2, h / 2, 'F');
    const fillW = Math.min(pct / 100, 1) * w;
    if (fillW > 0) {
        pdf.setFillColor(...color);
        pdf.roundedRect(x, y, fillW, h, h / 2, h / 2, 'F');
    }
}

/* ─── Chart capture helper ─── */
async function captureChart(selector) {
    try {
        const el = document.querySelector(selector);
        if (!el) return null;
        const { default: html2canvas } = await import('html2canvas');
        const canvas = await html2canvas(el, { scale: 2, useCORS: true, logging: false, backgroundColor: '#FFFFFF' });
        return canvas.toDataURL('image/png');
    } catch (err) { console.error("PDF generation error:", err);
        return null;
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * PAGE BUILDERS
 * ═══════════════════════════════════════════════════════════════════ */

function buildCoverPage(pdf, meta, reportData, slaData, qualityData, prevData, aiCards) {
    const w = pdf.internal.pageSize.getWidth();

    // Header bar
    pdf.setFillColor(...C.dark);
    pdf.rect(0, 0, w, 36, 'F');
    pdf.setFontSize(18);
    pdf.setTextColor(...C.white);
    pdf.setFont(undefined, 'bold');
    pdf.text('LastMile OS — Reporte Operativo', MARGIN.left, 16);
    pdf.setFontSize(10);
    pdf.setFont(undefined, 'normal');
    pdf.text(`Periodo: ${meta.dateFrom} a ${meta.dateTo}`, MARGIN.left, 24);
    const filterText = meta.filters?.length ? `Filtros: ${meta.filters.join(', ')}` : 'Sin filtros aplicados';
    pdf.text(filterText, MARGIN.left, 30);
    pdf.text(`Generado: ${new Date().toLocaleString('es-MX')} por ${meta.userName}`, w - MARGIN.right, 24, { align: 'right' });

    let y = 44;

    // AI Cards (alert/trend/achievement banners)
    if (aiCards?.length > 0) {
        const cardW = (w - MARGIN.left - MARGIN.right - (aiCards.length - 1) * 4) / aiCards.length;
        aiCards.forEach((card, i) => {
            const cx = MARGIN.left + i * (cardW + 4);
            const colors = {
                alerta: { bg: [254, 242, 242], border: C.coral, text: C.coral },
                tendencia: { bg: [239, 246, 255], border: C.blue, text: C.blue },
                logro: { bg: [240, 253, 244], border: C.green, text: C.green },
            };
            const cc = colors[card.tipo] || colors.tendencia;
            pdf.setFillColor(...cc.bg);
            pdf.roundedRect(cx, y, cardW, 22, 2, 2, 'F');
            pdf.setDrawColor(...cc.border);
            pdf.setLineWidth(0.5);
            pdf.roundedRect(cx, y, cardW, 22, 2, 2, 'S');

            pdf.setFontSize(8);
            pdf.setTextColor(...cc.text);
            pdf.setFont(undefined, 'bold');
            const titleText = card.titulo || '';
            pdf.text(titleText.substring(0, 40), cx + 4, y + 7);
            pdf.setFont(undefined, 'normal');
            pdf.setFontSize(7);
            pdf.setTextColor(...C.sec);
            const bodyLines = pdf.splitTextToSize(card.cuerpo || '', cardW - 8);
            pdf.text(bodyLines.slice(0, 2), cx + 4, y + 13);
        });
        y += 28;
    }

    // KPI cards
    const delivery = reportData?.delivery_rate || 0;
    const totalPkg = reportData?.total_packages || 1;
    const totalDelivered = reportData?.total_delivered || 0;
    const totalFailed = reportData?.total_failed || 0;
    const visitRate = totalPkg > 0 ? Math.round((totalDelivered + totalFailed) / totalPkg * 1000) / 10 : 0;
    const qualityAvg = qualityData?.summary?.avg_score || 0;
    const sla = slaData?.consolidated?.actual || delivery;
    const slaTarget = slaData?.consolidated?.target || 75;
    const prevDelivery = prevData?.delivery_rate || null;
    const deliveryDelta = prevDelivery != null ? delivery - prevDelivery : null;

    const kpiW = (w - MARGIN.left - MARGIN.right - 12) / 4;
    const kpiH = 40;
    drawKpiBlock(pdf, MARGIN.left, y, kpiW, kpiH, 'Tasa de entrega', `${delivery}%`, deliveryDelta, delivery);
    drawKpiBlock(pdf, MARGIN.left + kpiW + 4, y, kpiW, kpiH, 'Tasa de visita', `${visitRate}%`, null, visitRate);
    drawKpiBlock(pdf, MARGIN.left + (kpiW + 4) * 2, y, kpiW, kpiH, 'Calidad evidencias', `${qualityAvg}%`, null, qualityAvg);
    drawKpiBlock(pdf, MARGIN.left + (kpiW + 4) * 3, y, kpiW, kpiH, 'SLA vs Target', `${sla}%`, sla - slaTarget, sla);
    y += kpiH + 6;

    // Summary stats
    pdf.setFontSize(9);
    pdf.setTextColor(...C.sec);
    const stats = [
        `Total paquetes: ${reportData?.total_packages || 0}`,
        `Entregados: ${reportData?.total_delivered || 0}`,
        `Fallidos: ${reportData?.total_failed || 0}`,
        `Rutas: ${reportData?.total_routes || 0}`,
    ];
    pdf.text(stats.join('   |   '), MARGIN.left, y + 4);
    y += 10;

    return y;
}

async function addChartsToPage(pdf, y) {
    const w = pdf.internal.pageSize.getWidth();
    const contentW = w - MARGIN.left - MARGIN.right;

    // Capture combo chart
    const comboImg = await captureChart('[data-testid="charts-section"] > div:first-child');
    if (comboImg) {
        const imgH = 60;
        pdf.addImage(comboImg, 'PNG', MARGIN.left, y, contentW * 0.58, imgH);
        // Donut chart
        const donutImg = await captureChart('[data-testid="charts-section"] > div:last-child');
        if (donutImg) {
            pdf.addImage(donutImg, 'PNG', MARGIN.left + contentW * 0.6, y, contentW * 0.4, imgH);
        }
        y += imgH + 6;
    }
    return y;
}

function buildTablePage(pdf, title, headers, rows, columnWidths) {
    pdf.addPage();
    let y = addSectionTitle(pdf, title, 20);

    if (!rows || rows.length === 0) {
        pdf.setFontSize(12);
        pdf.setTextColor(...C.sec);
        pdf.text('Sin datos disponibles para este periodo.', MARGIN.left, y + 10);
        return;
    }

    pdf.autoTable({
        startY: y,
        head: [headers],
        body: rows,
        margin: { left: MARGIN.left, right: MARGIN.right },
        styles: {
            fontSize: 9,
            cellPadding: 3,
            textColor: C.dark,
            lineColor: C.borderLight,
            lineWidth: 0.2,
        },
        headStyles: {
            fillColor: C.headerBg,
            textColor: C.dark,
            fontStyle: 'bold',
            fontSize: 9,
        },
        alternateRowStyles: {
            fillColor: [250, 249, 247],
        },
        columnStyles: columnWidths || {},
        didDrawPage: () => {},
    });
}

function buildProvidersPage(pdf, reportData, slaData) {
    const provMetrics = reportData?.provider_metrics;
    if (!provMetrics) {
        buildTablePage(pdf, 'Proveedores', [], []);
        return;
    }
    const slaMap = {};
    if (slaData?.by_provider) {
        for (const p of slaData.by_provider) slaMap[p.provider_name] = p;
    }

    const headers = ['Proveedor', 'Dias op.', 'Rutas', 'Paquetes', 'Entregados', 'Entrega%', 'Visita%', 'Km', 'SLA'];
    const rows = Object.entries(provMetrics).map(([name, m]) => {
        const visitR = m.packages_loaded > 0 ? Math.round((m.delivered + m.failed) / m.packages_loaded * 1000) / 10 : 0;
        const slaActual = slaMap[name]?.sla_actual || m.delivery_rate || 0;
        return [name, m.days_operated, m.routes, m.packages_loaded, m.delivered, `${m.delivery_rate}%`, `${visitR}%`, (m.km_total || 0).toLocaleString(), `${slaActual}%`];
    });

    buildTablePage(pdf, 'Proveedores', headers, rows);
}

function buildDriversPage(pdf, reportData) {
    const driverMetrics = reportData?.driver_metrics;
    if (!driverMetrics) {
        buildTablePage(pdf, 'Drivers', [], []);
        return;
    }
    const headers = ['Driver', 'Dias op.', 'Rutas', 'Paquetes', 'Entregados', 'SLA individual', 'Km'];
    const rows = Object.entries(driverMetrics)
        .map(([name, m]) => [name, m.days_operated, m.routes, m.packages_loaded, m.delivered, `${m.delivery_rate}%`, (m.km_total || 0).toLocaleString()])
        .sort((a, b) => parseFloat(b[5]) - parseFloat(a[5]));
    buildTablePage(pdf, 'Drivers', headers, rows);

    // Footer note
    const lastY = pdf.lastAutoTable?.finalY || 100;
    pdf.setFontSize(8);
    pdf.setTextColor(...C.ter);
    pdf.text('Politica de strikes: 1er aviso — 2do descanso operativo — 3ro baja. Filas con SLA <60% requieren atencion.', MARGIN.left, lastY + 8);
}

function buildIncidentsPage(pdf, reportData) {
    const incidents = reportData?.incidents_by_type;
    if (!incidents || Object.keys(incidents).length === 0) {
        buildTablePage(pdf, 'Incidencias', [], []);
        return;
    }
    const headers = ['Tipo de incidencia', 'Total'];
    const rows = Object.entries(incidents)
        .map(([type, count]) => [type, count])
        .sort((a, b) => b[1] - a[1]);
    buildTablePage(pdf, 'Incidencias', headers, rows);

    const lastY = pdf.lastAutoTable?.finalY || 100;
    pdf.setFontSize(8);
    pdf.setTextColor(...C.ter);
    pdf.text('Incidencias de zona (accesibilidad) NO penalizan el SLA del driver.', MARGIN.left, lastY + 8);
}

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

    // Attempt bars
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
        pdf.text(`${b.count} (${b.pct}%)`, MARGIN.left + 80, y + 4);
        pdf.setFont(undefined, 'normal');
        drawProgressBar(pdf, MARGIN.left + 120, y, contentW - 130, 5, b.pct, b.color);
        y += 10;
    });

    y += 6;

    // Retry causes
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

function buildQualityPage(pdf, qualityData) {
    pdf.addPage();
    let y = addSectionTitle(pdf, 'Evidencias — Calidad', 20);

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

    const w = pdf.internal.pageSize.getWidth();

    // Score global
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

    // By type
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
            pdf.text(`${t.type || t._id}: ${t.count} (${t.avg_score ? t.avg_score.toFixed(0) : 0}%)`, MARGIN.left + 4, y);
            y += 5;
        });
        y += 4;
    }

    // By provider
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
            pdf.text(p.provider || p._id || '?', MARGIN.left + 4, y + 3);
            drawProgressBar(pdf, MARGIN.left + 80, y, 100, 5, score, score >= 85 ? C.green : score >= 70 ? C.amber : C.coral);
            pdf.setTextColor(...C.dark);
            pdf.setFont(undefined, 'bold');
            pdf.text(`${score.toFixed(0)}%`, MARGIN.left + 186, y + 3);
            pdf.setFont(undefined, 'normal');
            y += 8;
        });
    }
}

function buildSLAPage(pdf, slaData) {
    pdf.addPage();
    let y = addSectionTitle(pdf, 'SLA', 20);

    if (!slaData) {
        pdf.setFontSize(12);
        pdf.setTextColor(...C.sec);
        pdf.text('Sin datos SLA para este periodo.', MARGIN.left, y + 10);
        return;
    }

    const w = pdf.internal.pageSize.getWidth();
    const { consolidated, by_provider, by_driver, brackets } = slaData;

    // Consolidated SLA
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

    // Brackets
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
            pdf.text(b.label, MARGIN.left + 4, y + 3);
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

    // By provider table
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
                p.provider_name,
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

    // Top drivers table
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
                d.driver_name,
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

function buildAIPage(pdf, aiNarrative, aiCards) {
    if (!aiNarrative && !aiCards?.length) return;

    pdf.addPage();
    let y = addSectionTitle(pdf, 'Analisis IA', 20);
    const w = pdf.internal.pageSize.getWidth();
    const contentW = w - MARGIN.left - MARGIN.right;
    const pageH = pdf.internal.pageSize.getHeight();

    pdf.setFontSize(8);
    pdf.setTextColor(...C.ter);
    pdf.text('Este analisis fue generado automaticamente por IA y debe validarse operativamente.', MARGIN.left, y);
    y += 6;

    // Cards
    if (aiCards?.length > 0) {
        const cardW = (contentW - (aiCards.length - 1) * 4) / aiCards.length;
        aiCards.forEach((card, i) => {
            const cx = MARGIN.left + i * (cardW + 4);
            const colors = {
                alerta: { bg: [254, 242, 242], border: C.coral },
                tendencia: { bg: [239, 246, 255], border: C.blue },
                logro: { bg: [240, 253, 244], border: C.green },
            };
            const cc = colors[card.tipo] || colors.tendencia;
            pdf.setFillColor(...cc.bg);
            pdf.roundedRect(cx, y, cardW, 20, 2, 2, 'F');
            pdf.setDrawColor(...cc.border);
            pdf.setLineWidth(0.4);
            pdf.roundedRect(cx, y, cardW, 20, 2, 2, 'S');

            pdf.setFontSize(8);
            pdf.setTextColor(...cc.border);
            pdf.setFont(undefined, 'bold');
            pdf.text((card.titulo || '').substring(0, 35), cx + 3, y + 6);
            pdf.setFont(undefined, 'normal');
            pdf.setFontSize(7);
            pdf.setTextColor(...C.sec);
            const bodyLines = pdf.splitTextToSize(card.cuerpo || '', cardW - 6);
            pdf.text(bodyLines.slice(0, 2), cx + 3, y + 12);
        });
        y += 26;
    }

    // Narrative
    if (aiNarrative) {
        const cleanText = aiNarrative
            .replace(/#{1,6}\s*/g, '')
            .replace(/\*\*(.+?)\*\*/g, '$1')
            .replace(/\*(.+?)\*/g, '$1')
            .replace(/[^\S\n]+/g, ' ')
            .trim();

        pdf.setFontSize(10);
        pdf.setTextColor(...C.dark);
        const lines = pdf.splitTextToSize(cleanText, contentW);

        // Paginate
        const lineH = 4.5;
        const maxLinesPerPage = Math.floor((pageH - y - 20) / lineH);
        let lineIdx = 0;
        while (lineIdx < lines.length) {
            if (lineIdx > 0) { pdf.addPage(); y = 20; }
            const endIdx = lineIdx + (lineIdx === 0 ? maxLinesPerPage : Math.floor((pageH - 30) / lineH));
            const pageLines = lines.slice(lineIdx, endIdx);
            pdf.text(pageLines, MARGIN.left, y);
            lineIdx = endIdx;
        }
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * MAIN EXPORT FUNCTION
 * ═══════════════════════════════════════════════════════════════════ */

export async function generateMultiPagePDF({
    reportData, prevReportData, qualityData, attemptsData, slaData,
    aiNarrative, aiCards, meta,
}) {
    const { default: jsPDF } = await import('jspdf');
    const { applyPlugin } = await import('jspdf-autotable');
    
    // Apply the autoTable plugin to jsPDF
    applyPlugin(jsPDF);

    const pdf = new jsPDF('p', 'mm', 'a4');

    // Page 1: Cover + KPIs + Charts
    let y = buildCoverPage(pdf, meta, reportData, slaData, qualityData, prevReportData, aiCards);
    y = await addChartsToPage(pdf, y);

    // Page 2: Providers
    buildProvidersPage(pdf, reportData, slaData);

    // Page 3: Drivers
    buildDriversPage(pdf, reportData);

    // Page 4: Incidents
    buildIncidentsPage(pdf, reportData);

    // Page 5: Attempts
    buildAttemptsPage(pdf, attemptsData);

    // Page 6: Quality/Evidence
    buildQualityPage(pdf, qualityData);

    // Page 7: SLA
    buildSLAPage(pdf, slaData);

    // Page 8: AI Analysis
    buildAIPage(pdf, aiNarrative, aiCards);

    // Add page numbers
    const totalPages = pdf.internal.getNumberOfPages();
    for (let i = 1; i <= totalPages; i++) {
        pdf.setPage(i);
        addPageFooter(pdf, i, totalPages);
    }

    pdf.save(`reporte_operativo_${meta.dateFrom}_${meta.dateTo}.pdf`);
}
