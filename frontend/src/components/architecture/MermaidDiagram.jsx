import React, { useEffect, useRef } from 'react';
import mermaid from 'mermaid';

mermaid.initialize({
    startOnLoad: false,
    theme: 'base',
    themeVariables: {
        primaryColor: '#F0EFEC',
        primaryTextColor: '#1A1916',
        primaryBorderColor: '#C8C6BF',
        lineColor: '#6B6960',
        secondaryColor: '#EFF6FF',
        tertiaryColor: '#F5F3FF',
        fontFamily: 'DM Sans, sans-serif',
    },
    flowchart: { htmlLabels: true, curve: 'basis' },
    securityLevel: 'loose',
});

let idCounter = 0;

/** Renders a Mermaid diagram string inline. */
export const MermaidDiagram = ({ chart, testId }) => {
    const ref = useRef(null);
    const [svg, setSvg] = React.useState(null);
    const [error, setError] = React.useState(null);

    useEffect(() => {
        if (!chart) return;
        let cancelled = false;
        const renderId = `mermaid-${++idCounter}`;
        mermaid
            .render(renderId, chart)
            .then(({ svg: rendered }) => {
                if (!cancelled) {
                    setSvg(rendered);
                    setError(null);
                }
            })
            .catch((e) => {
                if (!cancelled) {
                    setError(e.message || 'Error rendering diagram');
                }
            });
        return () => {
            cancelled = true;
        };
    }, [chart]);

    if (error) {
        return (
            <div className="p-4 bg-red-50 border border-red-200 rounded text-sm text-red-700" data-testid={testId ? `${testId}-error` : undefined}>
                Error renderizando diagrama: {error}
            </div>
        );
    }
    if (!svg) {
        return (
            <div className="p-4 text-slate-400 text-sm" data-testid={testId ? `${testId}-loading` : undefined}>
                Renderizando diagrama…
            </div>
        );
    }
    return (
        <div
            ref={ref}
            className="mermaid-wrapper overflow-x-auto"
            data-testid={testId}
            dangerouslySetInnerHTML={{ __html: svg }}
        />
    );
};

export default MermaidDiagram;
