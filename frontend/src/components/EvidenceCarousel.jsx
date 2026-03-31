import React, { useState, useEffect, useCallback } from 'react';
import { Dialog, DialogContent, DialogTitle } from '../components/ui/dialog';
import { Button } from '../components/ui/button';
import { ChevronLeft, ChevronRight, X, ZoomIn, ZoomOut } from 'lucide-react';

const EvidenceCarousel = ({ open, onClose, images, initialIndex = 0, packageInfo }) => {
    const [currentIndex, setCurrentIndex] = useState(initialIndex);
    const [zoom, setZoom] = useState(1);

    useEffect(() => {
        setCurrentIndex(initialIndex);
        setZoom(1);
    }, [initialIndex, open]);

    const goNext = useCallback(() => {
        if (currentIndex < images.length - 1) {
            setCurrentIndex(i => i + 1);
            setZoom(1);
        }
    }, [currentIndex, images.length]);

    const goPrev = useCallback(() => {
        if (currentIndex > 0) {
            setCurrentIndex(i => i - 1);
            setZoom(1);
        }
    }, [currentIndex]);

    // Keyboard navigation
    useEffect(() => {
        if (!open) return;
        const handler = (e) => {
            if (e.key === 'ArrowRight') goNext();
            else if (e.key === 'ArrowLeft') goPrev();
            else if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, [open, goNext, goPrev, onClose]);

    // Touch swipe support
    const [touchStart, setTouchStart] = useState(null);
    const handleTouchStart = (e) => setTouchStart(e.touches[0].clientX);
    const handleTouchEnd = (e) => {
        if (touchStart === null) return;
        const diff = touchStart - e.changedTouches[0].clientX;
        if (diff > 50) goNext();
        else if (diff < -50) goPrev();
        setTouchStart(null);
    };

    if (!images || images.length === 0) return null;

    const currentImage = images[currentIndex];
    const photoAnalysis = currentImage?.analysis;

    return (
        <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
            <DialogContent className="max-w-[95vw] max-h-[95vh] p-0 bg-slate-950 border-slate-800 overflow-hidden" data-testid="evidence-carousel-modal">
                <DialogTitle className="sr-only">Evidencia fotográfica</DialogTitle>
                {/* Top bar */}
                <div className="flex items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-800">
                    <div className="flex items-center gap-3">
                        <span className="text-sm font-mono text-slate-400" data-testid="carousel-position">
                            Foto {currentIndex + 1} de {images.length}
                        </span>
                        {packageInfo && (
                            <span className="text-xs text-slate-500">
                                | Guía: <span className="font-mono text-slate-300">{packageInfo.guide}</span>
                                {packageInfo.deliveryType && (
                                    <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${
                                        packageInfo.deliveryType === 'exitosa' ? 'bg-emerald-900/50 text-emerald-400' :
                                        packageInfo.deliveryType === 'terceros' ? 'bg-blue-900/50 text-blue-400' :
                                        'bg-red-900/50 text-red-400'
                                    }`}>
                                        {packageInfo.deliveryType === 'exitosa' ? 'Exitosa' :
                                         packageInfo.deliveryType === 'terceros' ? 'Terceros' : 'Fallida'}
                                    </span>
                                )}
                                {packageInfo.score !== undefined && (
                                    <span className={`ml-2 font-mono ${
                                        packageInfo.score === 100 ? 'text-emerald-400' :
                                        packageInfo.score >= 60 ? 'text-amber-400' : 'text-red-400'
                                    }`}>
                                        Score: {packageInfo.score}
                                    </span>
                                )}
                            </span>
                        )}
                    </div>
                    <div className="flex items-center gap-2">
                        <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white h-8 w-8 p-0"
                            onClick={() => setZoom(z => Math.min(3, z + 0.5))} data-testid="carousel-zoom-in">
                            <ZoomIn className="w-4 h-4" />
                        </Button>
                        <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white h-8 w-8 p-0"
                            onClick={() => setZoom(z => Math.max(0.5, z - 0.5))} data-testid="carousel-zoom-out">
                            <ZoomOut className="w-4 h-4" />
                        </Button>
                        <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white h-8 w-8 p-0"
                            onClick={onClose} data-testid="carousel-close">
                            <X className="w-4 h-4" />
                        </Button>
                    </div>
                </div>

                {/* Main image area */}
                <div
                    className="relative flex items-center justify-center"
                    style={{ height: 'calc(95vh - 140px)' }}
                    onTouchStart={handleTouchStart}
                    onTouchEnd={handleTouchEnd}
                >
                    {/* Left arrow */}
                    {currentIndex > 0 && (
                        <button
                            className="absolute left-2 z-10 w-10 h-10 rounded-full bg-black/60 text-white flex items-center justify-center hover:bg-black/80 transition"
                            onClick={goPrev}
                            data-testid="carousel-prev"
                        >
                            <ChevronLeft className="w-6 h-6" />
                        </button>
                    )}

                    {/* Image */}
                    <div className="overflow-auto w-full h-full flex items-center justify-center">
                        <img
                            src={currentImage?.url}
                            alt={`Evidencia ${currentIndex + 1}`}
                            className="max-h-full object-contain transition-transform duration-200"
                            style={{ transform: `scale(${zoom})` }}
                            data-testid="carousel-image"
                        />
                    </div>

                    {/* Right arrow */}
                    {currentIndex < images.length - 1 && (
                        <button
                            className="absolute right-2 z-10 w-10 h-10 rounded-full bg-black/60 text-white flex items-center justify-center hover:bg-black/80 transition"
                            onClick={goNext}
                            data-testid="carousel-next"
                        >
                            <ChevronRight className="w-6 h-6" />
                        </button>
                    )}
                </div>

                {/* Bottom: metadata + thumbnails */}
                <div className="bg-slate-900 border-t border-slate-800 px-4 py-2">
                    {/* AI analysis metadata */}
                    {photoAnalysis && (
                        <div className="text-xs text-slate-400 mb-2 flex flex-wrap gap-3">
                            {photoAnalysis.photo_type && (
                                <span>Tipo: <span className="text-slate-200 capitalize">{photoAnalysis.photo_type.replace('_', ' ')}</span></span>
                            )}
                            {photoAnalysis.quality && (
                                <span>Calidad: <span className={`${
                                    photoAnalysis.quality === 'buena' ? 'text-emerald-400' :
                                    photoAnalysis.quality === 'aceptable' ? 'text-amber-400' : 'text-red-400'
                                }`}>{photoAnalysis.quality}</span></span>
                            )}
                            {photoAnalysis.guide_number_visible && photoAnalysis.guide_number_text && (
                                <span>Guía OCR: <span className="text-slate-200 font-mono">{photoAnalysis.guide_number_text}</span></span>
                            )}
                            {photoAnalysis.description && (
                                <span className="text-slate-500 italic">{photoAnalysis.description}</span>
                            )}
                        </div>
                    )}
                    {/* Thumbnail strip */}
                    <div className="flex gap-1.5 overflow-x-auto pb-1" data-testid="carousel-thumbnails">
                        {images.map((img, idx) => (
                            <button
                                key={`thumb-${img.url}`}
                                onClick={() => { setCurrentIndex(idx); setZoom(1); }}
                                className={`shrink-0 w-12 h-12 rounded overflow-hidden border-2 transition ${
                                    idx === currentIndex ? 'border-blue-500 opacity-100' : 'border-transparent opacity-50 hover:opacity-80'
                                }`}
                                data-testid={`carousel-thumb-${idx}`}
                            >
                                <img src={img.url} alt={`Thumb ${idx + 1}`} className="w-full h-full object-cover" />
                            </button>
                        ))}
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
};

export default EvidenceCarousel;
