/**
 * PDF export for single journey (JourneyDetail page).
 * Uses jsPDF + autoTable (already installed for Reports PDF).
 *
 * Sections:
 *   - Cover: route_id, date, driver, provider, client, status
 *   - KPIs: packages total/delivered/failed/pending/delivery-rate
 *   - Start data: km, fuel, vehicle, driver pre-shift
 *   - Packages table (tracking, destinatario, status, attempts, ia score)
 *   - Incidents list
 *   - Close data
 */

const BRAND = { teal: [13, 148, 136], slate: [30, 41, 59], slateLt: [148, 163, 184], red: [220, 38, 38], green: [5, 150, 105], amber: [217, 119, 6] };

const loadPdfDeps = async () => {
    const { default: jsPDF } = await import('jspdf');
    const { applyPlugin } = await import('jspdf-autotable');
    applyPlugin(jsPDF);
    return jsPDF;
};

const fmtDate = (iso) => {
    if (!iso) return '—';
    try {
        const d = new Date(iso);
        if (isNaN(d.getTime())) return iso;
        return d.toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch { return iso; }
};

const fmtDateTime = (iso) => {
    if (!iso) return '—';
    try {
        const d = new Date(iso);
        if (isNaN(d.getTime())) return iso;
        return d.toLocaleString('es-MX', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch { return iso; }
};

const statusLabel = (s) => {
    const m = { pending: 'Pendiente', started: 'Iniciado', closed: 'Finalizado', cancelled: 'Cancelado',
        delivered: 'Entregado', failed: 'Fallido', picked: 'Recolectado', en_route: 'En ruta' };
    return m[s] || s || '—';
};

const addHeader = (pdf, journey) => {
    const pageW = pdf.internal.pageSize.getWidth();
    pdf.setFillColor(...BRAND.slate);
    pdf.rect(0, 0, pageW, 22, 'F');
    pdf.setTextColor(255, 255, 255);
    pdf.setFontSize(11);
    pdf.setFont('helvetica', 'bold');
    pdf.text('LastMile OS · Detalle de Ruta', 14, 9);
    pdf.setFontSize(8);
    pdf.setFont('helvetica', 'normal');
    pdf.text(`Generado: ${new Date().toLocaleString('es-MX')}`, pageW - 14, 9, { align: 'right' });

    pdf.setFontSize(13);
    pdf.setFont('helvetica', 'bold');
    pdf.text(`Ruta ${fmtDate(journey.date)} · ${journey.driver_name || 'Sin driver'}`, 14, 18);
    pdf.setTextColor(...BRAND.slate);
};

const addFooter = (pdf, pageNum, totalPages) => {
    const pageW = pdf.internal.pageSize.getWidth();
    const pageH = pdf.internal.pageSize.getHeight();
    pdf.setFontSize(8);
    pdf.setTextColor(...BRAND.slateLt);
    pdf.text(`Página ${pageNum} de ${totalPages}`, pageW / 2, pageH - 8, { align: 'center' });
};

const addSummaryBlock = (pdf, journey, startY) => {
    const metaRows = [
        ['Order ID', journey.order_id || journey.cosmo_route_id || '—'],
        ['Fecha', fmtDate(journey.date)],
        ['Estado', statusLabel(journey.status)],
        ['Driver', journey.driver_name || '—'],
        ['Proveedor', journey.provider_name || '—'],
        ['Cliente', journey.client_name || '—'],
        ['Tipo de ruta', journey.route_type ? `${journey.route_type}${journey.city ? ` — ${journey.city}` : ''}` : 'CDMX / Zona Metro'],
    ];
    pdf.autoTable({
        startY,
        head: [['Datos de la ruta', '']],
        body: metaRows,
        theme: 'plain',
        headStyles: { fillColor: [243, 244, 246], textColor: BRAND.slate, fontStyle: 'bold' },
        columnStyles: { 0: { fontStyle: 'bold', cellWidth: 45, textColor: BRAND.slateLt }, 1: { textColor: BRAND.slate } },
        styles: { fontSize: 9, cellPadding: 2.5 },
        margin: { left: 14, right: 14 },
    });
    return pdf.lastAutoTable.finalY + 4;
};

const addKpisBlock = (pdf, journey, startY) => {
    const total = journey.packages_total ?? (journey.packages?.length || 0);
    const delivered = journey.packages_delivered ?? 0;
    const failed = journey.packages_failed ?? 0;
    const pending = Math.max(0, total - delivered - failed);
    const rate = total > 0 ? ((delivered / total) * 100).toFixed(1) : '0.0';
    const rows = [[`${total}`, `${delivered}`, `${failed}`, `${pending}`, `${rate}%`]];
    pdf.autoTable({
        startY,
        head: [['Paquetes totales', 'Entregados', 'Fallidos', 'Pendientes', 'Delivery rate']],
        body: rows,
        theme: 'grid',
        headStyles: { fillColor: BRAND.teal, textColor: [255, 255, 255], fontStyle: 'bold', halign: 'center' },
        bodyStyles: { halign: 'center', fontSize: 11, fontStyle: 'bold', textColor: BRAND.slate },
        styles: { cellPadding: 4 },
        margin: { left: 14, right: 14 },
    });
    return pdf.lastAutoTable.finalY + 4;
};

const addStartBlock = (pdf, journey, startY) => {
    const s = journey.start_data || {};
    if (!journey.started_at && !s.km_initial && !s.fuel_level) return startY;
    const rows = [
        ['Iniciado', fmtDateTime(journey.started_at)],
        ['KM inicial', s.km_initial ?? '—'],
        ['Combustible', s.fuel_level || '—'],
        ['Condición del vehículo', s.vehicle_condition || '—'],
    ];
    pdf.autoTable({
        startY,
        head: [['Inicio de ruta', '']],
        body: rows,
        theme: 'plain',
        headStyles: { fillColor: [243, 244, 246], textColor: BRAND.slate, fontStyle: 'bold' },
        styles: { fontSize: 9, cellPadding: 2.5 },
        columnStyles: { 0: { fontStyle: 'bold', cellWidth: 50, textColor: BRAND.slateLt } },
        margin: { left: 14, right: 14 },
    });
    return pdf.lastAutoTable.finalY + 4;
};

const addPackagesTable = (pdf, journey, startY) => {
    const pkgs = journey.packages || [];
    if (!pkgs.length) return startY;
    const rows = pkgs.slice(0, 400).map(p => [
        (p.tracking_number || p.tracking_id || '—').toString().slice(0, 24),
        (p.recipient_name || p.destinatario || '—').toString().slice(0, 28),
        statusLabel(p.status || p.order_status),
        String(p.attempts ?? p.delivery_attempts ?? 0),
        p.evidence_score != null ? String(p.evidence_score) : (p.ai_score != null ? String(p.ai_score) : '—'),
    ]);
    pdf.autoTable({
        startY,
        head: [['Tracking', 'Destinatario', 'Estado', 'Intentos', 'IA Score']],
        body: rows,
        theme: 'striped',
        headStyles: { fillColor: BRAND.slate, textColor: [255, 255, 255], fontStyle: 'bold', fontSize: 9 },
        bodyStyles: { fontSize: 8, textColor: BRAND.slate },
        alternateRowStyles: { fillColor: [248, 250, 252] },
        columnStyles: {
            0: { cellWidth: 40, font: 'courier' },
            3: { halign: 'center', cellWidth: 18 },
            4: { halign: 'center', cellWidth: 20 },
        },
        margin: { left: 14, right: 14 },
        didDrawPage: (data) => {
            // keep header on every page (autotable handles this when using the same call)
        },
    });
    if (pkgs.length > 400) {
        const y = pdf.lastAutoTable.finalY + 4;
        pdf.setFontSize(8);
        pdf.setTextColor(...BRAND.slateLt);
        pdf.text(`Se muestran los primeros 400 de ${pkgs.length} paquetes. Usa el export Excel para ver todos.`, 14, y);
        return y + 6;
    }
    return pdf.lastAutoTable.finalY + 4;
};

const addIncidentsBlock = (pdf, journey, startY) => {
    const incs = journey.incidents || [];
    if (!incs.length) return startY;
    const rows = incs.map(i => [
        fmtDateTime(i.created_at || i.timestamp),
        (i.type || i.incident_type || '—').toString().slice(0, 22),
        (i.severity || '—'),
        (i.description || i.comment || '—').toString().slice(0, 80),
        i.resolved ? 'Resuelto' : 'Abierto',
    ]);
    pdf.autoTable({
        startY,
        head: [['Fecha', 'Tipo', 'Severidad', 'Descripción', 'Estado']],
        body: rows,
        theme: 'grid',
        headStyles: { fillColor: BRAND.amber, textColor: [255, 255, 255], fontStyle: 'bold', fontSize: 9 },
        bodyStyles: { fontSize: 8, textColor: BRAND.slate },
        margin: { left: 14, right: 14 },
    });
    return pdf.lastAutoTable.finalY + 4;
};

const addCloseBlock = (pdf, journey, startY) => {
    const c = journey.close_data || {};
    if (!journey.closed_at && !c.km_final && !c.km_traveled) return startY;
    const rows = [
        ['Finalizado', fmtDateTime(journey.closed_at)],
        ['KM final', c.km_final ?? '—'],
        ['KM recorridos', c.km_traveled ?? '—'],
        ['Combustible final', c.fuel_level_final || '—'],
        ['Notas', (c.notes || c.observations || '—').toString().slice(0, 240)],
    ];
    pdf.autoTable({
        startY,
        head: [['Cierre de ruta', '']],
        body: rows,
        theme: 'plain',
        headStyles: { fillColor: [243, 244, 246], textColor: BRAND.slate, fontStyle: 'bold' },
        styles: { fontSize: 9, cellPadding: 2.5 },
        columnStyles: { 0: { fontStyle: 'bold', cellWidth: 50, textColor: BRAND.slateLt } },
        margin: { left: 14, right: 14 },
    });
    return pdf.lastAutoTable.finalY + 4;
};

export const exportJourneyPdf = async (journey) => {
    if (!journey) throw new Error('journey is required');
    const jsPDF = await loadPdfDeps();
    const pdf = new jsPDF('p', 'mm', 'a4');
    const pageH = pdf.internal.pageSize.getHeight();

    const ensureRoom = (cursorY, needed = 40) => {
        if (cursorY + needed > pageH - 15) {
            pdf.addPage();
            addHeader(pdf, journey);
            return 28;
        }
        return cursorY;
    };

    addHeader(pdf, journey);
    let y = 28;
    y = addSummaryBlock(pdf, journey, y);
    y = ensureRoom(y, 20);
    y = addKpisBlock(pdf, journey, y);
    y = ensureRoom(y, 40);
    y = addStartBlock(pdf, journey, y);
    y = ensureRoom(y, 40);
    y = addPackagesTable(pdf, journey, y);
    y = ensureRoom(y, 40);
    y = addIncidentsBlock(pdf, journey, y);
    y = ensureRoom(y, 40);
    y = addCloseBlock(pdf, journey, y);

    // Footer with page numbers
    const total = pdf.internal.getNumberOfPages();
    for (let i = 1; i <= total; i++) {
        pdf.setPage(i);
        addFooter(pdf, i, total);
    }

    const safeDate = (journey.date || 'ruta').toString().slice(0, 10);
    const safeDriver = (journey.driver_name || 'driver').replace(/[^a-z0-9_-]+/gi, '_').slice(0, 24);
    pdf.save(`ruta_${safeDate}_${safeDriver}.pdf`);
};
