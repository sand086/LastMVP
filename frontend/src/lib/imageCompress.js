/**
 * Browser-side image compression using Canvas API.
 * Shrinks large photos before upload to reduce bandwidth and backend storage.
 *
 * Strategy:
 *   - Images under MIN_BYTES (1 MB) are returned as-is.
 *   - Larger images are resized to MAX_DIMENSION (1920px) longest side and
 *     re-encoded to JPEG at QUALITY (0.85). PNGs with transparency preserved.
 *   - If compression fails for any reason, the original file is returned.
 */

const MIN_BYTES = 1 * 1024 * 1024;     // 1 MB threshold
const MAX_DIMENSION = 1920;             // px (longest side)
const QUALITY = 0.85;                   // JPEG quality

const loadImage = (file) => new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = (e) => { URL.revokeObjectURL(url); reject(e); };
    img.src = url;
});

const canvasToBlob = (canvas, type, quality) => new Promise((resolve) => {
    canvas.toBlob((b) => resolve(b), type, quality);
});

/**
 * Compress a single image. Always returns a File (possibly the original).
 * @param {File} file
 * @returns {Promise<File>}
 */
export const compressImage = async (file) => {
    try {
        if (!file || !file.type?.startsWith('image/')) return file;
        if (file.size <= MIN_BYTES) return file;

        const img = await loadImage(file);
        let { width, height } = img;
        const longest = Math.max(width, height);
        if (longest > MAX_DIMENSION) {
            const scale = MAX_DIMENSION / longest;
            width = Math.round(width * scale);
            height = Math.round(height * scale);
        }

        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        // Fill white background for JPEG (prevents black bars on transparent PNGs)
        const isPng = file.type === 'image/png';
        if (!isPng) {
            ctx.fillStyle = '#FFFFFF';
            ctx.fillRect(0, 0, width, height);
        }
        ctx.drawImage(img, 0, 0, width, height);

        const outType = isPng ? 'image/png' : 'image/jpeg';
        const blob = await canvasToBlob(canvas, outType, QUALITY);
        if (!blob || blob.size >= file.size) return file; // no gain → keep original

        const outName = isPng ? file.name : file.name.replace(/\.(png|webp|heic|heif)$/i, '.jpg');
        return new File([blob], outName, { type: outType, lastModified: Date.now() });
    } catch (err) {
        console.warn('[imageCompress] fallback to original:', err?.message || err);
        return file;
    }
};

/**
 * Compress multiple files in parallel. Returns both the output files and
 * per-file savings info for UI feedback.
 */
export const compressImages = async (files) => {
    const tasks = Array.from(files || []).map(async (f) => {
        const out = await compressImage(f);
        return {
            original: f,
            compressed: out,
            originalSize: f.size,
            finalSize: out.size,
            saved: f.size - out.size,
            compressed_applied: out !== f,
        };
    });
    return Promise.all(tasks);
};
