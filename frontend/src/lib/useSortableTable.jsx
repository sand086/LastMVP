import { useState, useMemo, useCallback } from 'react';
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react';

/**
 * Hook for sortable table columns.
 * Usage:
 *   const { sortedData, SortHeader, sortKey, sortDir } = useSortableTable(data);
 *   <SortHeader field="name">Nombre</SortHeader>
 */
export function useSortableTable(data, defaultKey = null, defaultDir = 'asc') {
    const [sortKey, setSortKey] = useState(defaultKey);
    const [sortDir, setSortDir] = useState(defaultDir);

    const handleSort = useCallback((key) => {
        if (sortKey === key) {
            setSortDir(d => d === 'asc' ? 'desc' : 'asc');
        } else {
            setSortKey(key);
            setSortDir('asc');
        }
    }, [sortKey]);

    const sortedData = useMemo(() => {
        if (!sortKey || !data) return data;
        return [...data].sort((a, b) => {
            let va = a[sortKey];
            let vb = b[sortKey];
            // Handle null/undefined
            if (va == null) va = '';
            if (vb == null) vb = '';
            // Numeric comparison
            if (typeof va === 'number' && typeof vb === 'number') {
                return sortDir === 'asc' ? va - vb : vb - va;
            }
            // String comparison
            const sa = String(va).toLowerCase();
            const sb = String(vb).toLowerCase();
            if (sa < sb) return sortDir === 'asc' ? -1 : 1;
            if (sa > sb) return sortDir === 'asc' ? 1 : -1;
            return 0;
        });
    }, [data, sortKey, sortDir]);

    const SortHeader = useCallback(({ field, children, className = '' }) => {
        const isActive = sortKey === field;
        return (
            <th
                className={`cursor-pointer select-none hover:bg-slate-100 transition-colors ${className}`}
                onClick={() => handleSort(field)}
                data-testid={`sort-header-${field}`}
            >
                <span className="inline-flex items-center gap-1">
                    {children}
                    {isActive ? (
                        sortDir === 'asc' ? <ChevronUp className="w-3 h-3 text-blue-600" /> : <ChevronDown className="w-3 h-3 text-blue-600" />
                    ) : (
                        <ChevronsUpDown className="w-3 h-3 text-slate-300" />
                    )}
                </span>
            </th>
        );
    }, [sortKey, sortDir, handleSort]);

    return { sortedData, SortHeader, sortKey, sortDir };
}
