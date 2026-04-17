import React, { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getManualBySlug } from '../lib/api';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import {
    ArrowLeft, BookOpen, CheckCircle2, AlertTriangle, Lightbulb, Info, Printer, Loader2,
} from 'lucide-react';

// ── Block Renderers ────────────────────────────────────────────
const CalloutBlock = ({ text }) => (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex gap-3" data-testid="block-callout">
        <Info className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
        <p className="text-sm text-blue-800 leading-relaxed">{text}</p>
    </div>
);

const SectionBlock = ({ title, items, id }) => (
    <div id={id} className="scroll-mt-20" data-testid={`block-section-${id}`}>
        <h2 className="text-base font-semibold text-slate-900 mb-2 flex items-center gap-2">
            <span className="w-1 h-5 bg-slate-800 rounded-full" />
            {title}
        </h2>
        {items && items.length > 0 && (
            <ul className="space-y-1.5 ml-5">
                {items.map((item, i) => (
                    <li key={`${id}-item-${i}`} className="text-sm text-slate-600 flex items-start gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-slate-400 mt-2 flex-shrink-0" />
                        <span>{item}</span>
                    </li>
                ))}
            </ul>
        )}
    </div>
);

const ChecklistBlock = ({ items }) => (
    <div className="space-y-1.5" data-testid="block-checklist">
        {(items || []).map((item, i) => (
            <div key={`checklist-${i}`} className="flex items-center gap-2 text-sm text-slate-700">
                <CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                <span>{item}</span>
            </div>
        ))}
    </div>
);

const TableBlock = ({ headers, rows }) => (
    <div className="overflow-x-auto rounded-lg border border-slate-200" data-testid="block-table">
        <table className="w-full text-sm">
            <thead>
                <tr className="bg-slate-50">
                    {(headers || []).map((h, i) => (
                        <th key={`th-${i}`} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-600 uppercase tracking-wider border-b">{h}</th>
                    ))}
                </tr>
            </thead>
            <tbody>
                {(rows || []).map((row, ri) => (
                    <tr key={`row-${ri}`} className="border-b last:border-0 hover:bg-slate-50/50">
                        {row.map((cell, ci) => (
                            <td key={`cell-${ri}-${ci}`} className="px-4 py-2.5 text-slate-700">{cell}</td>
                        ))}
                    </tr>
                ))}
            </tbody>
        </table>
    </div>
);

const TipBlock = ({ text }) => (
    <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 flex gap-3" data-testid="block-tip">
        <Lightbulb className="w-5 h-5 text-emerald-500 flex-shrink-0 mt-0.5" />
        <p className="text-sm text-emerald-800 leading-relaxed">{text}</p>
    </div>
);

const WarningBlock = ({ text }) => (
    <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex gap-3" data-testid="block-warning">
        <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
        <p className="text-sm text-amber-800 leading-relaxed">{text}</p>
    </div>
);

const ImageBlock = ({ url, caption }) => (
    <figure className="space-y-2" data-testid="block-image">
        <img src={url} alt={caption || ''} className="rounded-lg border border-slate-200 max-w-full" loading="lazy" />
        {caption && <figcaption className="text-xs text-slate-500 text-center">{caption}</figcaption>}
    </figure>
);

const BLOCK_RENDERERS = {
    callout: CalloutBlock,
    section: SectionBlock,
    checklist: ChecklistBlock,
    table: TableBlock,
    tip: TipBlock,
    warning: WarningBlock,
    image: ImageBlock,
};

// ── Main Component ─────────────────────────────────────────────
const ManualViewer = () => {
    const { slug } = useParams();
    const [manual, setManual] = useState(null);
    const [loading, setLoading] = useState(true);
    const [activeSection, setActiveSection] = useState('');
    const observerRef = useRef(null);

    useEffect(() => {
        const fetchManual = async () => {
            try {
                const res = await getManualBySlug(slug);
                setManual(res.data);
            } catch (err) {
                console.error('Failed to load manual:', err);
            } finally {
                setLoading(false);
            }
        };
        fetchManual();
    }, [slug]);

    // IntersectionObserver for active section tracking
    useEffect(() => {
        if (!manual?.content) return;
        const sections = manual.content.filter(b => b.type === 'section');
        if (sections.length === 0) return;

        observerRef.current = new IntersectionObserver(
            (entries) => {
                for (const entry of entries) {
                    if (entry.isIntersecting) {
                        setActiveSection(entry.target.id);
                    }
                }
            },
            { rootMargin: '-80px 0px -60% 0px', threshold: 0.1 }
        );

        const timer = setTimeout(() => {
            sections.forEach((s, i) => {
                const el = document.getElementById(`section-${i}`);
                if (el) observerRef.current.observe(el);
            });
        }, 300);

        return () => {
            clearTimeout(timer);
            if (observerRef.current) observerRef.current.disconnect();
        };
    }, [manual]);

    if (loading) {
        return <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-slate-400" /></div>;
    }

    if (!manual) {
        return (
            <div className="text-center py-16">
                <BookOpen className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                <p className="text-slate-500 mb-4">Manual no encontrado</p>
                <Link to="/manuales"><Button variant="outline"><ArrowLeft className="w-4 h-4 mr-2" />Volver al indice</Button></Link>
            </div>
        );
    }

    const sections = (manual.content || []).filter(b => b.type === 'section').map((s, i) => ({
        id: `section-${i}`,
        title: s.title,
    }));

    let sectionIdx = 0;

    return (
        <div className="flex gap-8" data-testid="manual-viewer">
            {/* Main content */}
            <div className="flex-1 min-w-0 space-y-5 max-w-4xl">
                {/* Breadcrumb */}
                <Link to="/manuales" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors" data-testid="manual-back">
                    <ArrowLeft className="w-4 h-4" /> Volver al indice
                </Link>

                {/* Header */}
                <div>
                    <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">{manual.title}</h1>
                    {manual.subtitle && <p className="text-slate-500 mt-1">{manual.subtitle}</p>}
                    <div className="flex flex-wrap gap-1.5 mt-3">
                        {(manual.tags || []).map(tag => (
                            <span key={tag} className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-500">{tag}</span>
                        ))}
                    </div>
                </div>

                {/* Blocks */}
                <div className="space-y-5">
                    {(manual.content || []).map((block, i) => {
                        const Renderer = BLOCK_RENDERERS[block.type];
                        if (!Renderer) return null;

                        const props = { ...block };
                        if (block.type === 'section') {
                            props.id = `section-${sectionIdx}`;
                            sectionIdx++;
                        }
                        return <Renderer key={`block-${block.type}-${i}`} {...props} />;
                    })}
                </div>

                {/* Print button */}
                <div className="pt-4 border-t border-slate-200">
                    <Button variant="outline" size="sm" onClick={() => window.print()} data-testid="manual-print-btn">
                        <Printer className="w-4 h-4 mr-2" />Imprimir / PDF
                    </Button>
                </div>
            </div>

            {/* Sidebar TOC (desktop) */}
            {sections.length > 0 && (
                <aside className="hidden lg:block w-56 flex-shrink-0">
                    <div className="sticky top-24 space-y-1">
                        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Contenido</p>
                        {sections.map(s => (
                            <a
                                key={s.id}
                                href={`#${s.id}`}
                                className={`block text-sm py-1 px-2 rounded transition-colors ${
                                    activeSection === s.id
                                        ? 'text-blue-700 bg-blue-50 font-medium'
                                        : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'
                                }`}
                                data-testid={`toc-${s.id}`}
                            >
                                {s.title}
                            </a>
                        ))}
                    </div>
                </aside>
            )}
        </div>
    );
};

export default ManualViewer;
