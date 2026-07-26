#!/usr/bin/env python3
"""
Foveated Path Tracing - Reconstruction Method Comparison
=========================================================
Compares REF / NEAREST / GAUSSIAN EXR renders:
  - Global PSNR / SSIM
  - Per-eccentricity-band error analysis (fovea / mid / periphery)
  - Difference maps and side-by-side crops

SETUP:
    python -m pip install opencv-python scikit-image numpy matplotlib imageio

USAGE:
    python compare_reconstruction.py ./results
"""

import os
os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"   # must be set before importing cv2

import sys
import glob
import numpy as np
import cv2
import matplotlib.pyplot as plt
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

# ─────────────────────────────────────────────────────────
# CONFIG — must match the values used during rendering
# ─────────────────────────────────────────────────────────
GAZE_X       = 0.5     # reference_pt_gaze_x
GAZE_Y       = 0.5     # reference_pt_gaze_y
FOVEA_RADIUS = 0.12    # reference_pt_fovea_radius
MID_RADIUS   = 0.25    # reference_pt_mid_radius


# ─────────────────────────────────────────────────────────
# EXR loading — tries several backends
# ─────────────────────────────────────────────────────────
def load_exr(path):
    """Load an EXR file as float32 RGB, trying multiple backends."""

    # Backend 1: OpenCV
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH | cv2.IMREAD_ANYCOLOR)
    if img is not None:
        if img.ndim == 3 and img.shape[2] >= 3:
            img = img[:, :, :3][:, :, ::-1]      # drop alpha, BGR -> RGB
        return np.ascontiguousarray(img.astype(np.float32))

    # Backend 2: imageio (v3 API)
    try:
        import imageio.v3 as iio
        arr = iio.imread(path)
        arr = np.asarray(arr, dtype=np.float32)
        if arr.ndim == 3 and arr.shape[2] >= 3:
            arr = arr[:, :, :3]
        return np.ascontiguousarray(arr)
    except Exception:
        pass

    # Backend 3: imageio + freeimage plugin (downloads binary on first use)
    try:
        import imageio
        try:
            imageio.plugins.freeimage.download()
        except Exception:
            pass
        arr = imageio.imread(path, format="EXR-FI")
        arr = np.asarray(arr, dtype=np.float32)
        if arr.ndim == 3 and arr.shape[2] >= 3:
            arr = arr[:, :, :3]
        return np.ascontiguousarray(arr)
    except Exception:
        pass

    raise RuntimeError(
        f"Could not read EXR: {path}\n"
        "Install an EXR-capable backend:\n"
        "    python -m pip install imageio\n"
        "    python -m pip install --upgrade opencv-python\n"
        "Or re-run the benchmark with --save-as-jpeg and use the JPEG loader."
    )


def load_image(path):
    """Load EXR or LDR image as float32 RGB in [0,1] for LDR, linear for EXR."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".exr":
        return load_exr(path), True          # (image, is_hdr)
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Could not read image: {path}")
    return img[:, :, ::-1].astype(np.float32) / 255.0, False


def tonemap(img, is_hdr):
    """HDR -> LDR (Reinhard + gamma). LDR images pass through."""
    if not is_hdr:
        return np.clip(img, 0, 1)
    img = np.clip(img, 0, None)
    mapped = img / (1.0 + img)
    return np.clip(mapped ** (1.0 / 2.2), 0, 1)


def eccentricity_mask(shape, gaze, r_inner, r_outer, aspect):
    """Mask of pixels whose gaze distance falls in [r_inner, r_outer)."""
    h, w = shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    u = (xs + 0.5) / w
    v = (ys + 0.5) / h
    du = (u - gaze[0]) * aspect      # aspect correction (same as in the shader)
    dv = v - gaze[1]
    dist = np.sqrt(du * du + dv * dv)
    return (dist >= r_inner) & (dist < r_outer)


def masked_psnr(ref, test, mask):
    """PSNR computed over masked pixels only."""
    if mask.sum() == 0:
        return float('nan')
    diff = (ref - test)[mask]
    mse = np.mean(diff ** 2)
    if mse <= 1e-12:
        return float('inf')
    return 10.0 * np.log10(1.0 / mse)


def find_file(folder, tag):
    """
    Locate a render by its benchmark suffix.
    NOTE: glob is case-insensitive on Windows, so a bare '_REF' would also match
    '_ReferencePathTracer'. We therefore require the double-underscore form that
    --benchmark-suffix produces (e.g. '__REF_') and verify case explicitly.
    """
    candidates = []
    for ext in ("exr", "jpeg", "jpg", "png"):
        candidates += glob.glob(os.path.join(folder, f"*__{tag}_*.{ext}"))

    # Enforce case-sensitive match on the tag (Windows glob ignores case)
    exact = [p for p in candidates if f"__{tag}_" in os.path.basename(p)]
    if exact:
        return sorted(exact)[0]
    if candidates:
        return sorted(candidates)[0]

    raise FileNotFoundError(
        f"No render found for tag '{tag}' in {folder}\n"
        f"Expected a filename containing '__{tag}_'.\n"
        f"Files present: {[os.path.basename(p) for p in glob.glob(os.path.join(folder, '*'))]}"
    )


def frame_time_from_name(path):
    """Extract the trailing frame-time value encoded in the filename."""
    base = os.path.splitext(os.path.basename(path))[0]
    try:
        return float(base.split("_")[-1])
    except ValueError:
        return None


def main(folder):
    print("=" * 62)
    print("  FOVEATED RECONSTRUCTION COMPARISON")
    print("=" * 62)

    ref_path   = find_file(folder, "REF")
    near_path  = find_file(folder, "NEAREST")
    gauss_path = find_file(folder, "GAUSSIAN")

    print(f"\nReference : {os.path.basename(ref_path)}")
    print(f"Nearest   : {os.path.basename(near_path)}")
    print(f"Gaussian  : {os.path.basename(gauss_path)}")

    ref_raw,   is_hdr = load_image(ref_path)
    near_raw,  _      = load_image(near_path)
    gauss_raw, _      = load_image(gauss_path)

    if not (ref_raw.shape == near_raw.shape == gauss_raw.shape):
        raise RuntimeError("Image dimensions differ! All renders must use the same resolution.")

    ref   = tonemap(ref_raw,   is_hdr)
    near  = tonemap(near_raw,  is_hdr)
    gauss = tonemap(gauss_raw, is_hdr)

    h, w = ref.shape[:2]
    aspect = w / h
    gaze = (GAZE_X, GAZE_Y)
    print(f"\nResolution : {w} x {h}   (aspect {aspect:.3f})")
    print(f"Gaze point : ({GAZE_X}, {GAZE_Y})")
    print(f"Radii      : fovea {FOVEA_RADIUS}, mid {MID_RADIUS}")

    # ── Performance (parsed from filenames) ──
    print("\n" + "-" * 62)
    print("  PERFORMANCE (frame time from filename)")
    print("-" * 62)
    t_ref   = frame_time_from_name(ref_path)
    t_near  = frame_time_from_name(near_path)
    t_gauss = frame_time_from_name(gauss_path)
    if t_ref and t_near and t_gauss:
        print(f"  Reference : {t_ref*1000:7.3f} ms")
        print(f"  Nearest   : {t_near*1000:7.3f} ms   ({t_ref/t_near:.3f}x speedup)")
        print(f"  Gaussian  : {t_gauss*1000:7.3f} ms   ({t_ref/t_gauss:.3f}x speedup)")
        print(f"  Gaussian is {(t_gauss/t_near - 1)*100:.2f}% slower than Nearest")

    # ── Global metrics ──
    print("\n" + "-" * 62)
    print("  GLOBAL METRICS (full frame)")
    print("-" * 62)
    for name, img in (("Nearest ", near), ("Gaussian", gauss)):
        psnr = peak_signal_noise_ratio(ref, img, data_range=1.0)
        ssim = structural_similarity(ref, img, channel_axis=2, data_range=1.0)
        print(f"  {name}: PSNR {psnr:6.2f} dB   SSIM {ssim:.4f}")

    # ── Eccentricity bands ──
    print("\n" + "-" * 62)
    print("  ECCENTRICITY BANDS (the key analysis)")
    print("-" * 62)
    bands = [
        ("Fovea     (stride 1)", 0.0,          FOVEA_RADIUS),
        ("Mid       (stride 2)", FOVEA_RADIUS, MID_RADIUS),
        ("Periphery (stride 4)", MID_RADIUS,   10.0),
    ]
    print(f"  {'Band':<22} {'Area %':>7} {'Nearest':>9} {'Gaussian':>9} {'Delta':>8}")
    print("  " + "-" * 58)

    band_results = []
    for label, r0, r1 in bands:
        mask = eccentricity_mask(ref.shape, gaze, r0, r1, aspect)
        mask3 = np.repeat(mask[:, :, None], 3, axis=2)
        area = 100.0 * mask.sum() / mask.size
        p_near  = masked_psnr(ref, near,  mask3)
        p_gauss = masked_psnr(ref, gauss, mask3)
        delta = p_gauss - p_near
        print(f"  {label:<22} {area:6.2f}% {p_near:8.2f}  {p_gauss:8.2f}  {delta:+7.2f}")
        band_results.append((label, area, p_near, p_gauss))

    print("\n  (PSNR in dB, higher = closer to reference)")
    print("  (Positive delta means Gaussian is better)")
    print("  (Fovea band should be near-identical: no pixels are skipped there)")

    # ── Plot ──
    labels  = [b[0].split()[0] for b in band_results]
    n_vals  = [b[2] for b in band_results]
    g_vals  = [b[3] for b in band_results]
    finite  = [v for v in n_vals + g_vals if np.isfinite(v)]
    cap     = (max(finite) * 1.15) if finite else 1.0
    n_plot  = [v if np.isfinite(v) else cap for v in n_vals]
    g_plot  = [v if np.isfinite(v) else cap for v in g_vals]

    x = np.arange(len(labels))
    plt.figure(figsize=(7, 4.5))
    plt.bar(x - 0.18, n_plot, 0.36, label="Nearest Anchor")
    plt.bar(x + 0.18, g_plot, 0.36, label="Gaussian 3x3")
    plt.xticks(x, labels)
    plt.ylabel("PSNR (dB)")
    plt.title("Reconstruction quality by eccentricity band")
    plt.legend()
    plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    out_plot = os.path.join(folder, "psnr_by_eccentricity.png")
    plt.savefig(out_plot, dpi=150)
    print(f"\n  Plot saved: {out_plot}")

    # ── Difference maps ──
    amp = 5.0
    for name, img in (("nearest", near), ("gaussian", gauss)):
        diff = np.clip(np.abs(ref - img) * amp, 0, 1)
        out = os.path.join(folder, f"diff_{name}.png")
        cv2.imwrite(out, (diff[:, :, ::-1] * 255).astype(np.uint8))
        print(f"  Difference map ({amp}x amplified): {out}")

    # ── Side-by-side crops ──
    cs = min(h, w) // 5
    cx, cy = int(GAZE_X * w), int(GAZE_Y * h)
    crops = {
        "fovea":     (cx - cs // 2, cy - cs // 2),
        "periphery": (max(0, cx - int(0.35 * w)), max(0, cy - int(0.30 * h))),
    }
    for cname, (x0, y0) in crops.items():
        x0 = max(0, min(x0, w - cs)); y0 = max(0, min(y0, h - cs))
        strip = np.hstack([
            ref[y0:y0+cs, x0:x0+cs],
            near[y0:y0+cs, x0:x0+cs],
            gauss[y0:y0+cs, x0:x0+cs],
        ])
        out = os.path.join(folder, f"crop_{cname}_REF_NEAREST_GAUSSIAN.png")
        cv2.imwrite(out, (strip[:, :, ::-1] * 255).astype(np.uint8))
        print(f"  Crop ({cname}, left-to-right REF|NEAREST|GAUSSIAN): {out}")

    print("\n" + "=" * 62)
    print("  Analysis complete.")
    print("=" * 62)


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "./results"
    main(folder)
