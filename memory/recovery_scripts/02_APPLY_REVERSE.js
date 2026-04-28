// ============================================================================
// 02_APPLY_REVERSE.js  — REVERSO iter79 (Escenario 1)
// ============================================================================
//
// ⚠️ ESCRITURAS REALES. CORRER SOLO DESPUÉS DEL BACKUP Y DEL DRY-RUN.
//
// Acciones:
//   1. Mover packages: journey_id new → legacy (campo migrated_from)
//   2. Mover incidents: journey_id new → legacy
//   3. Borrar journeys creadas por iter79
//   4. Limpiar campos de migración en journeys legacy (vuelven a estado pre-iter79)
//   5. Recalcular packages_total/_delivered/_failed en legacy
//
// Idempotente: si ya se corrió, los pasos 1-3 quedan en 0.
//
// USO:
//   mongosh "$MONGO_URL/$DB_NAME" --file 02_APPLY_REVERSE.js
// ============================================================================

(function () {
    const startTs = new Date();
    print("");
    print("╔══════════════════════════════════════════════════════════════════╗");
    print("║  APPLY: Reverso iter79 — escrituras reales                       ║");
    print("╚══════════════════════════════════════════════════════════════════╝");
    print("");

    // ─── Pre-flight ────────────────────────────────────────────────────────
    const newJourneys = db.journeys.find(
        { migrated_from: { $exists: true, $ne: null } },
        { _id: 0, id: 1, migrated_from: 1 }
    ).toArray();

    const legacyJourneys = db.journeys.find(
        { migrated_to_journeys: { $exists: true, $ne: [] } },
        { _id: 0, id: 1 }
    ).toArray();

    if (newJourneys.length === 0 && legacyJourneys.length === 0) {
        print("✅ Nada que reversar. Sale.");
        return;
    }

    print(`Encontradas ${newJourneys.length} journeys nuevas y ${legacyJourneys.length} legacy.`);
    print("");

    // Mapa { newJourneyId → legacyJourneyId }
    const newToLegacy = {};
    newJourneys.forEach(nj => { newToLegacy[nj.id] = nj.migrated_from; });

    // ─── 1. Mover packages ────────────────────────────────────────────────
    print("→ Paso 1/5: moviendo packages new → legacy ...");
    let pkgMoved = 0;
    let pkgErr = 0;
    const newJourneyIds = Object.keys(newToLegacy);
    const pkgBulk = newJourneyIds.map(newId => ({
        updateMany: {
            filter: { journey_id: newId },
            update: {
                $set: {
                    journey_id: newToLegacy[newId],
                    _reversed_from: newId,
                    _reversed_at: new Date().toISOString(),
                },
                $unset: { routal_route_id: "" },
            },
        },
    }));
    if (pkgBulk.length > 0) {
        // bulkWrite en chunks de 500 para no explotar
        const chunks = [];
        for (let i = 0; i < pkgBulk.length; i += 500) chunks.push(pkgBulk.slice(i, i + 500));
        chunks.forEach((chunk, ci) => {
            try {
                const r = db.packages.bulkWrite(chunk, { ordered: false });
                pkgMoved += r.modifiedCount || 0;
            } catch (e) {
                pkgErr++;
                print(`   ⚠ chunk ${ci}: ${e.message}`);
            }
        });
    }
    print(`   ✓ Packages movidos: ${pkgMoved} (errores: ${pkgErr})`);
    print("");

    // ─── 2. Mover incidents (por si hubo creación post-migración) ──────────
    print("→ Paso 2/5: moviendo incidents new → legacy ...");
    let incMoved = 0;
    const incBulk = newJourneyIds.map(newId => ({
        updateMany: {
            filter: { journey_id: newId },
            update: {
                $set: {
                    journey_id: newToLegacy[newId],
                    _reversed_from: newId,
                    _reversed_at: new Date().toISOString(),
                },
            },
        },
    }));
    if (incBulk.length > 0) {
        const chunks = [];
        for (let i = 0; i < incBulk.length; i += 500) chunks.push(incBulk.slice(i, i + 500));
        chunks.forEach(chunk => {
            try {
                const r = db.incidents.bulkWrite(chunk, { ordered: false });
                incMoved += r.modifiedCount || 0;
            } catch (e) {
                print(`   ⚠ ${e.message}`);
            }
        });
    }
    print(`   ✓ Incidents movidos: ${incMoved}`);
    print("");

    // ─── 3. Borrar journeys nuevas ────────────────────────────────────────
    print("→ Paso 3/5: eliminando journeys nuevas (creadas por iter79) ...");
    const delResult = db.journeys.deleteMany({
        id: { $in: newJourneyIds },
        migrated_from: { $exists: true },
    });
    print(`   ✓ Journeys nuevas borradas: ${delResult.deletedCount}`);
    print("");

    // ─── 4. Limpiar campos de migración en legacy ─────────────────────────
    print("→ Paso 4/5: limpiando campos migrated_to_journeys/migrated_at en legacy ...");
    const cleanResult = db.journeys.updateMany(
        { migrated_to_journeys: { $exists: true } },
        {
            $unset: {
                migrated_to_journeys: "",
                migrated_at: "",
                _legacy_plan_journey: "",
                leftover_packages_count: "",
            },
            $set: { _reverse_iter79_at: new Date().toISOString() },
        }
    );
    print(`   ✓ Legacy limpias: ${cleanResult.modifiedCount}`);
    print("");

    // ─── 5. Recalcular packages_total en legacy ───────────────────────────
    print("→ Paso 5/5: recalculando packages_total/delivered/failed en legacy ...");
    let recalcOk = 0;
    legacyJourneys.forEach(lj => {
        const aggArr = db.packages.aggregate([
            { $match: { journey_id: lj.id } },
            {
                $group: {
                    _id: null,
                    total:     { $sum: 1 },
                    delivered: { $sum: { $cond: [{ $eq: ["$status", "delivered"] }, 1, 0] } },
                    failed:    { $sum: { $cond: [{ $eq: ["$status", "failed"]    }, 1, 0] } },
                },
            },
        ]).toArray();
        const stats = aggArr[0] || { total: 0, delivered: 0, failed: 0 };
        db.journeys.updateOne(
            { id: lj.id },
            {
                $set: {
                    packages_total:     stats.total,
                    packages_delivered: stats.delivered,
                    packages_failed:    stats.failed,
                    updated_at: new Date().toISOString(),
                },
            }
        );
        recalcOk++;
    });
    print(`   ✓ Legacy recalculadas: ${recalcOk}`);
    print("");

    // ─── 6. Validación post ───────────────────────────────────────────────
    print("🔍 Validación post-reverso:");
    const remainingNew = db.journeys.countDocuments({ migrated_from: { $exists: true } });
    const remainingMarked = db.journeys.countDocuments({ migrated_to_journeys: { $exists: true } });
    const orphanPkgs = db.packages.countDocuments({ routal_route_id: { $exists: true } });
    print(`   journeys nuevas restantes (debe ser 0): ${remainingNew}`);
    print(`   journeys con migrated_to_journeys (debe ser 0): ${remainingMarked}`);
    print(`   packages con routal_route_id residual (debe ser 0): ${orphanPkgs}`);
    print("");

    // ─── Summary ──────────────────────────────────────────────────────────
    const elapsed = Math.round((new Date() - startTs) / 1000);
    print("╔══════════════════════════════════════════════════════════════════╗");
    print("║  REVERSO COMPLETADO                                              ║");
    print("╠══════════════════════════════════════════════════════════════════╣");
    print(`║  Packages movidos: ${String(pkgMoved).padEnd(46)}║`);
    print(`║  Incidents movidos: ${String(incMoved).padEnd(45)}║`);
    print(`║  Journeys nuevas borradas: ${String(delResult.deletedCount).padEnd(38)}║`);
    print(`║  Legacy desmarcadas: ${String(cleanResult.modifiedCount).padEnd(44)}║`);
    print(`║  Legacy recalculadas: ${String(recalcOk).padEnd(43)}║`);
    print(`║  Tiempo total: ${String(elapsed + "s").padEnd(50)}║`);
    print("╚══════════════════════════════════════════════════════════════════╝");
    print("");
    print("📌 Próximos pasos:");
    print("   1. Verificar en /rutas que las rutas regresan al modelo 1-plan-1-journey");
    print("   2. Verificar que las incidencias muestran sobre rutas con paquetes");
    print("   3. Si todo OK, eliminar el campo `_reverse_iter79_at` y `_reversed_from`");
    print("      en journeys, packages e incidents (limpieza opcional)");
    print("");
})();
