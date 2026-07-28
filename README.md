# Foveated Path Tracing on Desktop Displays

> Gaze-contingent foveated rendering in a real-time path tracer, built on the
> [AMD Capsaicin](https://github.com/GPUOpen-LibrariesAndSDKs/Capsaicin) framework
> (Direct3D 12 / DXR).


<img width="2000" height="546" alt="sponza_group2" src="https://github.com/user-attachments/assets/b6e5ee6f-08d1-4b51-96d5-6d8f2915d809" />


*Peripheral region of Sponza. Left to right: full-quality reference, nearest-anchor
reconstruction, and 3×3 Gaussian reconstruction. Only one pixel in sixteen is traced
in this region.*

---

## What this is

Path tracing is expensive, and its cost scales directly with the number of rays you
trace. Human vision, on the other hand, only resolves fine detail in a small region
around wherever the eye is pointed — everything else is rendered at a level of detail
the viewer cannot actually see.

This project exploits that. Rays are traced at full density only around the gaze
point; further out, most pixels are skipped entirely and reconstructed afterwards
from their neighbours. Because a skipped pixel costs *nothing* in a path tracer — no
BVH traversal, no shading, no bounces — the saving is direct.

**Result:** 1.4–1.7× faster frame times at 1920×1080, depending on the scene.

| Gaussian | Nearest |
|----------|---------|
|<img width="544" height="306" alt="FlyingGaussianGif" src="https://github.com/user-attachments/assets/29a8da88-f78b-40cb-9e1b-bc9c8216a87d" /> | <img width="544" height="306" alt="FlyingNearestGif" src="https://github.com/user-attachments/assets/47eff5c1-2ad4-4934-8e86-0d6b8c790996" />|
|<img width="544" height="306" alt="SponzaGaussianGif" src="https://github.com/user-attachments/assets/37453457-f88a-4720-b812-879d2a3f012b" /> |<img width="544" height="306" alt="SponzaNearestGif" src="https://github.com/user-attachments/assets/27c53ce7-1755-4f7d-95f7-004ecd01e157" /> |






*The foveal region follows the gaze point in real time. Here it is driven by the
mouse; the same input path is designed to be swapped for a Tobii Eye Tracker 5.*

---

## 🎥 Demo Video

Click the image below to watch the demo.

[![Demo Video](https://img.youtube.com/vi/nQRQgYVg8VM/mqdefault.jpg)](https://www.youtube.com/watch?v=nQRQgYVg8VM)

## Paper

The full write-up, including the method, measurements and discussion, is available
here:

📄 very soon

---

## How it works

### Three regions, three sampling rates

The screen is divided into three regions by distance from the gaze point. The stride
determines how densely rays are cast:

| Region | Stride | Pixels traced | Screen area |
|--------|--------|---------------|-------------|
| Fovea | 1 | every pixel | 2.55% |
| Intermediate | 2 | 1 in 4 | 8.50% |
| Periphery | 4 | 1 in 16 | 88.96% |

Weighted by area, this comes out to roughly **10% of the rays** of a non-foveated
render.

### Two passes

Skipping rays leaves holes, and those holes have to be filled. This happens in a
**separate compute pass**, not inline — GPU threads run in parallel, so a pixel
trying to read its neighbour during the first pass might read a value that has not
been computed yet. Splitting the work into two dispatches makes that race impossible.

```
Pass 1   trace rays at anchor pixels only
   ↓     (GPU barrier)
Pass 2   fill the skipped pixels from neighbouring anchors
```


### Two reconstruction methods

Both are selectable at runtime from the GUI:

**Nearest anchor** — copy the value of the anchor at the origin of the block. Cheap,
sharp, but visibly blocky.

**Gaussian 3×3** — take a distance-weighted average of the nine surrounding anchors.
Smoother, and only about 2% more expensive.

<!-- ══════════════════════════════════════════════════════════════════
     KARSILASTIRMA GORSELLERI
     ══════════════════════════════════════════════════════════════ -->
| Reference | Nearest anchor | Gaussian 3×3 |
|:---:|:---:|:---:|
| <img width="187" height="167" alt="FlyingWorld_Disabled_crop" src="https://github.com/user-attachments/assets/06d974f5-3479-41d5-a5b5-95cc0e9833ab" />|<img width="206" height="187" alt="FlyingWorld_Nearest_crop" src="https://github.com/user-attachments/assets/1d712ea8-c07d-4533-8a03-588e4ac6ca0e" /> | <img width="207" height="181" alt="FlyingWorld_Gaussian_crop" src="https://github.com/user-attachments/assets/93db3b68-7eef-413e-bf88-5932b9e61cb4" /> |

*Peripheral crop from the scene Flying World. The blocking in the middle image is what nearest-anchor
reconstruction produces at stride 4.*

---

## Results

<img width="672" height="669" alt="sponza_group1" src="https://github.com/user-attachments/assets/df81d6a0-9bdc-4e68-b5ae-a63a503d0eea" />


### Performance

| Scene | Reference | Nearest | Gaussian | Speedup |
|-------|-----------|---------|----------|---------|
| Sponza | 6.93 ms | 4.18 ms | 4.27 ms | **1.66×** |
| Flying World | 7.05 ms | 4.95 ms | 5.04 ms | **1.42×** |

Per-pass breakdown for Sponza, from Capsaicin's own profiler:

| Pass | Reference | Nearest | Gaussian |
|------|-----------|---------|----------|
| Path tracing | 6.346 ms | 4.226 ms | 4.235 ms |
| Reconstruction | — | 0.088 ms | 0.161 ms |
| Other passes | 0.574 ms | 0.555 ms | 0.554 ms |

Note that the reconstruction pass costs almost nothing — under 2% of a frame either
way — so the choice between the two methods can be made purely on image quality.

### Image quality

Measured against a non-foveated reference at 2000 accumulated frames.

| Scene | Method | PSNR (dB) | SSIM |
|-------|--------|-----------|------|
| Sponza | Nearest | 33.46 | 0.8694 |
| Sponza | Gaussian | **34.27** | **0.9049** |
| Flying World | Nearest | **25.38** | 0.8616 |
| Flying World | Gaussian | 25.27 | **0.8787** |

Broken down by eccentricity band:

<img width="1050" height="675" alt="psnr_by_eccentricity" src="https://github.com/user-attachments/assets/241e9b6d-3922-4978-a9c6-15c806c4302f" />


The foveal bars are identical, and that is the point: no pixels are skipped there, so
the reconstruction pass never touches them. Both methods *have* to score the same,
which is a useful check that the measurement setup is behaving.

---

## Building

**Requirements**
- Windows 10 (2004 or newer)
- Visual Studio 2022 or newer
- CMake 3.30+
- A GPU supporting DirectX Raytracing 1.1
  *(developed on an AMD Radeon RX 9070 XT — the framework is GPU-agnostic, so
  NVIDIA cards work too)*

```bash
git clone --recurse-submodules https://github.com/BoraYalcinn/foveated-path-tracing.git
cd foveated-path-tracing
cmake CMakeLists.txt -B ./build
cmake --build ./build --config Release
./build/bin/Release/scene_viewer.exe
```

Then pick **Reference Path Tracer** from the renderer dropdown — the foveation
controls appear underneath it.

---

## Controls

| Setting | What it does |
|---------|--------------|
| **Foveated Rendering** | Toggles the whole system on and off |
| **Reconstruction** | Nearest anchor or Gaussian 3×3 |
| **Fovea / Mid Radius** | Size of each region, in normalised screen units |
| **Fovea / Mid / Periphery SPP** | Samples per pixel in each region |
| **Gaze Follows Mouse** | Gaze tracks the cursor; turn off to freeze it for measurements |

Camera: hold left mouse button to look around, WASD to move. The gaze point only
follows the cursor while the button is *not* held, so looking around does not drag
the fovea with it.

---

## Reproducing the measurements

Everything in the results above can be regenerated. Capsaicin's benchmark mode
renders a fixed number of frames and dumps both an EXR and a per-pass timing CSV:

```bash
# Reference (foveation off)
./build/bin/Release/scene_viewer.exe --benchmark-mode --benchmark-frames 2000 \
  --benchmark-capture-frames 1 --start-scene-index 4 --start-renderer-index 1 \
  --dump-folder ./results --render-options reference_pt_foveated_enabled=false \
  --benchmark-suffix "_REF"

# Nearest anchor
./build/bin/Release/scene_viewer.exe --benchmark-mode --benchmark-frames 2000 \
  --benchmark-capture-frames 1 --start-scene-index 4 --start-renderer-index 1 \
  --dump-folder ./results --render-options reference_pt_foveated_enabled=true \
  reference_pt_reconstruction_mode=0 reference_pt_gaze_follow_mouse=false \
  reference_pt_gaze_x=0.5 reference_pt_gaze_y=0.5 --benchmark-suffix "_NEAREST"

# Gaussian (same, with reconstruction_mode=1)
```

Then run the analysis script, which computes PSNR and SSIM, splits the error by
eccentricity band, and writes out the comparison crops and difference maps:

```bash
python -m pip install opencv-python scikit-image numpy matplotlib imageio
python tools/compare_reconstruction.py ./results
```

---

## What's in this repository

```
src/core/src/render_techniques/reference_path_tracer/
  reference_path_tracer.comp    # foveation + reconstruction (HLSL)
  reference_path_tracer.cpp     # uniforms, kernel dispatch, GUI
  reference_path_tracer.h       # render options
tools/
  compare_reconstruction.py     # PSNR / SSIM / eccentricity analysis
results/                        # measurement output
docs/images/                    # figures used in this README
paper/                          # the write-up
```

The foveation work lives almost entirely in those three files. Everything else is
Capsaicin.

---

## Known limitations

Being upfront about what this does not do:

- **No temporal reprojection.** Accumulated samples are not reprojected when the
  camera moves, so there is ghosting under motion. This is the standard fix in the
  literature and the most obvious thing to add next.
- **Thread-level skipping, not warp-level.** Skipped pixels return early, but they
  sit on a regular grid, so most warps still contain at least one anchor and stay
  scheduled. Tracing ~90% fewer rays only reduced the path tracing pass by 33%.
  Packing surviving anchors into fewer, fully occupied warps should recover much
  more of that.
- **Aggressive peripheral sampling.** At 1 sample per pixel the periphery shows
  visible artefacts in darker regions, where a single ray often reaches no light
  source at all.
- **Eye tracker not yet integrated.** Gaze is driven by the mouse. The Tobii Eye
  Tracker 5 plugs into the same code path.
- **Two scenes, one GPU.** Enough to show that the answer is scene-dependent, not
  enough to generalise.

---

## Prior work

Before this, I built a foveated rendering prototype in Unity URP, trying post-process
blur, Variable Rate Shading, and a two-camera setup. None of them produced a
measurable frame time reduction, and understanding *why* is what pushed this project
toward a path tracer instead.

🔗 [Unity prototype repository](https://github.com/BoraYalcinn/FoveatedRendering-EyeTracking)

---

## Acknowledgements

Built on [AMD Capsaicin](https://github.com/GPUOpen-LibrariesAndSDKs/Capsaicin),
released under the MIT License. The foveation and reconstruction passes are my
addition; everything else — the path tracer, the acceleration structures, the
sampling infrastructure — is AMD's.

Developed as an undergraduate summer research project.

---

## License

MIT, matching Capsaicin's own license. See [LICENSE](LICENSE).
