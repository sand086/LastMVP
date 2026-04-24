import React, { useState, useRef } from 'react';
import { Button } from './ui/button';
import { 
    Camera, 
    X, 
    Loader2, 
    Image as ImageIcon,
    Maximize2,
    Trash2
} from 'lucide-react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from './ui/dialog';
import { compressImages } from '../lib/imageCompress';
import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export const ImageUploader = ({ 
    images = [], 
    onUpload, 
    onDelete, 
    uploading = false,
    disabled = false,
    maxFiles = 5,
    label = "Agregar imágenes"
}) => {
    const fileInputRef = useRef(null);
    const [previewImage, setPreviewImage] = useState(null);
    const [compressing, setCompressing] = useState(false);

    const handleFileSelect = async (e) => {
        const files = Array.from(e.target.files || []);
        if (files.length === 0) return;

        // Filter valid image files
        const validFiles = files.filter(file => {
            const ext = file.name.toLowerCase();
            return ext.endsWith('.jpg') || ext.endsWith('.jpeg') || ext.endsWith('.png');
        });

        if (validFiles.length === 0) {
            if (fileInputRef.current) fileInputRef.current.value = '';
            return;
        }

        // Auto-compress (only large images are actually resized/recoded)
        setCompressing(true);
        let outFiles = validFiles;
        try {
            const results = await compressImages(validFiles);
            outFiles = results.map(r => r.compressed);
            const savedBytes = results.reduce((s, r) => s + Math.max(0, r.saved), 0);
            const compressedCount = results.filter(r => r.compressed_applied).length;
            if (compressedCount > 0 && savedBytes > 0) {
                const savedMb = (savedBytes / (1024 * 1024)).toFixed(1);
                toast.success(`${compressedCount} imagen(es) optimizada(s) · ${savedMb} MB ahorrados`, { duration: 2500 });
            }
        } catch (err) {
            console.warn('Compression failed, uploading originals:', err);
        } finally {
            setCompressing(false);
        }

        if (onUpload) onUpload(outFiles);

        // Reset input
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    const getImageUrl = (image) => {
        if (image.path) {
            return `${API_URL}${image.path}`;
        }
        return image.url || '';
    };

    return (
        <div className="space-y-3">
            {/* Upload button */}
            {!disabled && images.length < maxFiles && (
                <div>
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept=".jpg,.jpeg,.png"
                        multiple
                        onChange={handleFileSelect}
                        className="hidden"
                        data-testid="image-file-input"
                    />
                    <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploading || compressing}
                        data-testid="upload-image-btn"
                    >
                        {(uploading || compressing) ? (
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                            <Camera className="w-4 h-4 mr-2" />
                        )}
                        {compressing ? 'Optimizando...' : label}
                    </Button>
                    <p className="text-xs text-slate-500 mt-1">
                        JPG, JPEG, PNG • Optimización automática sobre 1MB
                    </p>
                </div>
            )}

            {/* Image thumbnails */}
            {images.length > 0 && (
                <div className="flex flex-wrap gap-2">
                    {images.map((image) => (
                        <div 
                            key={image.id || image.filename}
                            className="relative group"
                        >
                            <div 
                                className="w-20 h-20 rounded-sm overflow-hidden border border-slate-200 cursor-pointer hover:border-slate-400 transition-colors"
                                onClick={() => setPreviewImage(image)}
                            >
                                <img
                                    src={getImageUrl(image)}
                                    alt={image.original_name || 'Imagen'}
                                    className="w-full h-full object-cover"
                                    onError={(e) => {
                                        e.target.onerror = null;
                                        e.target.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%23999" stroke-width="1"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>';
                                    }}
                                />
                            </div>
                            {/* Hover actions */}
                            <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity rounded-sm flex items-center justify-center gap-1">
                                <button
                                    type="button"
                                    className="p-1 bg-white rounded-sm hover:bg-slate-100"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setPreviewImage(image);
                                    }}
                                    title="Ver imagen"
                                >
                                    <Maximize2 className="w-3 h-3 text-slate-700" />
                                </button>
                                {!disabled && onDelete && (
                                    <button
                                        type="button"
                                        className="p-1 bg-white rounded-sm hover:bg-red-50"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            onDelete(image.id);
                                        }}
                                        title="Eliminar imagen"
                                    >
                                        <Trash2 className="w-3 h-3 text-red-600" />
                                    </button>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Empty state */}
            {images.length === 0 && disabled && (
                <div className="flex items-center gap-2 text-slate-400 text-sm">
                    <ImageIcon className="w-4 h-4" />
                    <span>Sin imágenes</span>
                </div>
            )}

            {/* Image preview modal */}
            <Dialog open={!!previewImage} onOpenChange={() => setPreviewImage(null)}>
                <DialogContent className="max-w-3xl">
                    <DialogHeader>
                        <DialogTitle className="font-heading">
                            {previewImage?.original_name || 'Imagen'}
                        </DialogTitle>
                    </DialogHeader>
                    {previewImage && (
                        <div className="flex justify-center">
                            <img
                                src={getImageUrl(previewImage)}
                                alt={previewImage.original_name || 'Imagen'}
                                className="max-h-[70vh] object-contain rounded-sm"
                            />
                        </div>
                    )}
                </DialogContent>
            </Dialog>
        </div>
    );
};

export default ImageUploader;
