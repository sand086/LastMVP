// ============================================================================
// 01_DRY_RUN_DIAGNOSTICO.js  — REVERSO iter79 (Escenario 1)
// ============================================================================
//
// LECTURA EXCLUSIVA. No modifica nada.
// Objetivo: contar y mostrar lo que el script de apply haría.
//
// USO:
//   mongosh "$MONGO_URL/$DB_NAME" --quiet --file 01_DRY_RUN_DIAGNOSTICO.js
//
// O bien (interactivo):
//   mongosh "$MONGO_URL/$DB_NAME"
//   load("01_DRY_RUN_DIAGNOSTICO.js")
// ============================================================================

(function () {
    print("");
    print("╔══════════════════════════════════════════════════════════════════╗");
    print("║  DRY-RUN: Reverso iter79 (modelo 1-plan-1-journey)              ║");
    print("║  Lectura exclusiva. NO modifica datos.                           ║");
    print("╚══════════════════════════════════════════════════════════════════╝");
    print("");

    // ─── Snapshot total ────────────────────────────────────────────────────
    const totalJourneys  = db.journeys.countDocuments({});
    const totalPackages  = db.packages.countDocuments({});
    const totalIncidents = db.incidents.countDocuments({});
    print("📊 Estado actual:");
    print(`   journeys  total: ${totalJourneys}`);
    print(`   packages  total: ${totalPackages}`);
    print(`   incidents total: ${totalIncidents}`);
    print("");

    // ─── 1. Journeys legacy (a desmarcar) ─────────────────────────────────
    const legacyQuery = { migrated_to_journeys: { $exists: true, $ne: [] } };
    const legacyCount = db.journeys.countDocuments(legacyQuery);
    print(`🟡 Journeys LEGACY (con migrated_to_journeys[] set): ${legacyCount}`);
    print(`    → A LIMPIAR: removeremos migrated_to_journeys[], migrated_at,`);
    print(`      _legacy_plan_journey, leftover_packages_count.`);

    if (legacyCount > 0) {
        print("    Sample (5):");
        db.journeys.find(legacyQuery,
            { _id: 0, id: 1, client_id: 1, date: 1, driver_name: 1, packages_total: 1, migrated_to_journeys: 1 }
        ).limit(5).forEach(j => {
            const newCount = (j.migrated_to_journeys || []).length;
            print(`      legacy=${(j.id||"").slice(0,8)} date=${j.date} driver=${(j.driver_name||"").slice(0,20)} pkgs_total=${j.packages_total} → split en ${newCount} nuevas`);
        });
    }
    print("");

    // ─── 2. Journeys nuevas (a borrar) ────────────────────────────────────
    const newQuery = { migrated_from: { $exists: true, $ne: null } };
    const newCount = db.journeys.countDocuments(newQuery);
    print(`🔴 Journeys NUEVAS (creadas por iter79, con migrated_from): ${newCount}`);
    print(`    → A BORRAR: estas se eliminan completamente.`);

    if (newCount > 0) {
        print("    Sample (5):");
        db.journeys.find(newQuery,
            { _id: 0, id: 1, migrated_from: 1, driver_name: 1, packages_total: 1, routal_route_id: 1 }
        ).limit(5).forEach(j => {
            print(`      new=${(j.id||"").slice(0,8)} ← from legacy=${(j.migrated_from||"").slice(0,8)} driver=${(j.driver_name||"").slice(0,20)} pkgs=${j.packages_total} route=${(j.routal_route_id||"").slice(0,8)}`);
        });
    }
    print("");

    // ─── 3. Packages a regresar al legacy ─────────────────────────────────
    const newJourneyIds = db.journeys.distinct("id", newQuery);
    const packagesOnNew = db.packages.countDocuments({ journey_id: { $in: newJourneyIds } });
    print(`📦 Packages a REASIGNAR (de journey nueva → legacy): ${packagesOnNew}`);
    print(`    → A MOVER: package.journey_id = newJourney.migrated_from`);

    if (packagesOnNew > 0) {
        // Distribución por nueva journey
        print("    Distribución por nueva journey (top 5):");
        db.packages.aggregate([
            { $match: { journey_id: { $in: newJourneyIds } } },
            { $group: { _id: "$journey_id", count: { $sum: 1 } } },
            { $sort: { count: -1 } },
            { $limit: 5 },
        ]).forEach(r => {
            const j = db.journeys.findOne({ id: r._id }, { _id: 0, driver_name: 1, migrated_from: 1 });
            print(`      new=${r._id.slice(0,8)} (${(j && j.driver_name || "?").slice(0,20)}) → legacy=${(j && j.migrated_from || "?").slice(0,8)} pkgs=${r.count}`);
        });
    }
    print("");

    // ─── 4. Incidents (verificar que ya están en legacy) ──────────────────
    const legacyIds = db.journeys.distinct("id", legacyQuery);
    const incidentsOnLegacy = db.incidents.countDocuments({ journey_id: { $in: legacyIds } });
    const incidentsOnNew = db.incidents.countDocuments({ journey_id: { $in: newJourneyIds } });
    print(`📋 Incidents:`);
    print(`   en LEGACY (correcto, no se mueven): ${incidentsOnLegacy}`);
    print(`   en NUEVAS (a mover de vuelta a legacy): ${incidentsOnNew}`);
    print("");

    // ─── 5. Verificar coherencia para el reverso ──────────────────────────
    print("🔍 Verificación de coherencia:");
    let anyMismatch = false;
    db.journeys.find(legacyQuery, { _id: 0, id: 1, migrated_to_journeys: 1 })
        .limit(10)  // sólo muestreo, para no eternizar el dry-run
        .forEach(legacy => {
            const expectedNewIds = legacy.migrated_to_journeys || [];
            const actualNewIds = db.journeys.distinct("id", { migrated_from: legacy.id });
            const missing = expectedNewIds.filter(x => !actualNewIds.includes(x));
            const extra   = actualNewIds.filter(x => !expectedNewIds.includes(x));
            if (missing.length || extra.length) {
                anyMismatch = true;
                print(`   ⚠ legacy=${legacy.id.slice(0,8)} declara ${expectedNewIds.length} hijas pero existen ${actualNewIds.length} con migrated_from a esa legacy`);
                if (missing.length) print(`      faltan: ${missing.map(x => x.slice(0,8)).join(", ")}`);
                if (extra.length)   print(`      sobran: ${extra.map(x => x.slice(0,8)).join(", ")}`);
            }
        });
    if (!anyMismatch) print("   ✓ Sin mismatch en muestra de 10 legacy. Mapping consistente.");
    print("");

    // ─── 6. Plan summary ──────────────────────────────────────────────────
    print("╔══════════════════════════════════════════════════════════════════╗");
    print("║  PLAN DE APPLY (cuando ejecutes 02_APPLY_REVERSE.js)            ║");
    print("╠══════════════════════════════════════════════════════════════════╣");
    print(`║  1. Mover ${String(packagesOnNew).padEnd(6)} packages: journey_id new → legacy           ║`);
    print(`║  2. Mover ${String(incidentsOnNew).padEnd(6)} incidents: journey_id new → legacy        ║`);
    print(`║  3. Borrar ${String(newCount).padEnd(6)} journeys nuevas                                ║`);
    print(`║  4. Limpiar ${String(legacyCount).padEnd(5)} journeys legacy (unset campos de migración) ║`);
    print(`║  5. Recalcular packages_total en cada legacy                     ║`);
    print("╚══════════════════════════════════════════════════════════════════╝");
    print("");

    if (newCount === 0 && legacyCount === 0) {
        print("✅ NADA QUE REVERSAR. La DB no tiene rastros de iter79.");
    } else {
        print("📝 Si los números arriba se ven correctos, ejecuta:");
        print('   mongosh "$MONGO_URL/$DB_NAME" --file 02_APPLY_REVERSE.js');
    }
    print("");
})();
