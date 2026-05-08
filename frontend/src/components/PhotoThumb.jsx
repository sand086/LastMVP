import React, { useState } from 'react';
import { ImageOff } from 'lucide-react';

/**
 * Robust thumbnail with retry + CSS-only fallback.
 *
 * Replaces the previous pattern `onError={e => e.target.src=''}` which caused
 * the browser's "broken image" icon (because src='' triggers a re-fetch with
 * empty URL → triggers onError again → broken-image placeholder).
 *
 * Behavior:
 *   - On first load failure, retry once with a cache-busting query param
 *     (covers transient timeouts / proxy hiccups).
 *   - On second failure, swap to a CSS-only placeholder showing an icon
 *     (no <img src=''> ever, no broken icon).
 *   - Click still triggers `onClick` so the carousel can attempt the full
 *     image fetch independently.
 */
const PhotoThumb = ({ src, alt, className = 'w-16 h-16', onClick, testId }) => {
    const [stage, setStage] = useState('initial');  // initial | retry | failed

    if (stage === 'failed') {
        return (
            <button
                type="button"
                className={`${className} rounded border border-slate-300 bg-slate-100 flex flex-col items-center justify-center text-slate-400 hover:border-amber-400 transition-colors`}
                onClick={onClick}
                title="No se pudo cargar — click para reintentar"
                data-testid={testId ? `${testId}-failed` : undefined}
            >
                <ImageOff className="w-5 h-5" />
                <span className="text-[9px] font-medium mt-0.5">No carga</span>
            </button>
        );
    }

    const finalSrc = stage === 'retry' ? `${src}${src.includes('?') ? '&' : '?'}_t=${Date.now()}` : src;

    return (
        <button
            type="button"
            className={`${className} rounded border border-slate-200 overflow-hidden hover:border-blue-400 transition-colors`}
            onClick={onClick}
            data-testid={testId}
        >
            <img
                src={finalSrc}
                alt={alt}
                className="w-full h-full object-cover"
                loading="lazy"
                onError={() => {
                    if (stage === 'initial') setStage('retry');
                    else setStage('failed');
                }}
            />
        </button>
    );
};

export default PhotoThumb;
