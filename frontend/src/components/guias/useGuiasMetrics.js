/**
 * Custom hook: deriva metricas y listas filtradas para GuiasTab.
 * Todo es memoizado sobre `packages + reviewOverrides + segment`.
 */
import { useMemo } from 'react';

export function useGuiasMetrics(packages, reviewOverrides, segment) {
    const mergedPackages = useMemo(() => {
        return (packages || []).map((p) => {
            const override = reviewOverrides[p.id];
            return override ? { ...p, ...override } : p;
        });
    }, [packages, reviewOverrides]);

    const kpis = useMemo(() => {
        const total = mergedPackages.length;
        const withScore = mergedPackages.filter((p) => p.ai_score != null);
        const avgScore =
            withScore.length > 0
                ? Math.round(withScore.reduce((s, p) => s + p.ai_score, 0) / withScore.length)
                : 0;
        const complete = withScore.filter((p) => p.ai_score === 100).length;
        const aiEvaluated = withScore.length;
        const manualReviewed = mergedPackages.filter(
            (p) => p.manually_reviewed || p.manual_review?.decision,
        ).length;
        const discrepancies = mergedPackages.filter((p) => p.discrepancy?.detected).length;
        const withConfidence = mergedPackages.filter((p) => p.confidence?.score != null);
        const avgConfidence =
            withConfidence.length > 0
                ? Math.round(
                      withConfidence.reduce((s, p) => s + p.confidence.score, 0) / withConfidence.length,
                  )
                : null;
        return {
            avgScore,
            complete,
            totalScored: withScore.length,
            aiEvaluated,
            manualReviewed,
            totalPkgs: total,
            discrepancies,
            avgConfidence,
        };
    }, [mergedPackages]);

    const aiErrorSummary = useMemo(() => {
        const errorMap = {};
        mergedPackages.forEach((p) =>
            (p.ai_errors || []).forEach((e) => {
                errorMap[e] = (errorMap[e] || 0) + 1;
            }),
        );
        return Object.entries(errorMap).sort((a, b) => b[1] - a[1]);
    }, [mergedPackages]);

    const segmentCounts = useMemo(
        () => ({
            all: mergedPackages.length,
            alert: mergedPackages.filter((p) => (p.ai_errors || []).length > 0).length,
            discrepancy: mergedPackages.filter((p) => p.discrepancy?.detected).length,
            no_evidence: mergedPackages.filter(
                (p) => (p.photos_count || 0) === 0 && !(p.kosmo_proof_urls?.length),
            ).length,
            pending_review: mergedPackages.filter(
                (p) => !p.manually_reviewed && !p.rejection_reason && !p.manual_review?.decision,
            ).length,
        }),
        [mergedPackages],
    );

    const filteredPackages = useMemo(() => {
        let list = [...mergedPackages];
        if (segment === 'alert') list = list.filter((p) => (p.ai_errors || []).length > 0);
        if (segment === 'discrepancy') list = list.filter((p) => p.discrepancy?.detected);
        if (segment === 'no_evidence')
            list = list.filter(
                (p) => (p.photos_count || 0) === 0 && !(p.kosmo_proof_urls?.length),
            );
        if (segment === 'pending_review')
            list = list.filter(
                (p) => !p.manually_reviewed && !p.rejection_reason && !p.manual_review?.decision,
            );
        list.sort((a, b) => {
            const aDisc = a.discrepancy?.detected ? 1 : 0;
            const bDisc = b.discrepancy?.detected ? 1 : 0;
            if (bDisc !== aDisc) return bDisc - aDisc;
            const aErr = (a.ai_errors || []).length;
            const bErr = (b.ai_errors || []).length;
            if (bErr !== aErr) return bErr - aErr;
            return (a.order_reference_id || a.tracking_number || '').localeCompare(
                b.order_reference_id || b.tracking_number || '',
            );
        });
        return list;
    }, [mergedPackages, segment]);

    return { mergedPackages, kpis, aiErrorSummary, segmentCounts, filteredPackages };
}
