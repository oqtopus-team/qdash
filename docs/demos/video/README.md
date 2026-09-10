# QDash demo video (Remotion)

A 30 second product demo of QDash rendered with [Remotion](https://www.remotion.dev/).

## Usage

```bash
cd docs/demos/video
bun install

bun run dev      # Remotion Studio: preview and tweak
bun run render   # writes out/qdash-demo.mp4 (1920x1080, 30 fps, 30 s, H.264 + AAC)
bun run still    # writes out/poster.png (frame 60)
```

## Structure

| Path                              | Purpose                                              |
| --------------------------------- | ---------------------------------------------------- |
| `src/QDashDemo.tsx`               | Scene timeline, feature copy, BGM (edit text here)   |
| `src/scenes/Intro.tsx`            | Logo + title reveal                                  |
| `src/scenes/FeatureScene.tsx`     | Caption card + browser-framed screenshot             |
| `src/scenes/Outro.tsx`            | Links and credits                                    |
| `src/components/BrowserFrame.tsx` | Browser chrome with a slow Ken Burns zoom            |
| `public/screens/*.png`            | UI screenshots (3840x1612, viewport 1920x806 at 2x)  |
| `public/oqtopus-symbol.png`       | Logo (copy of `docs/public/images/oqtopus-symbol.png`) |
| `public/bgm.m4a`                  | Background music                                     |
| `scripts/make_bgm.py`             | Generator for `bgm.m4a` (numpy + scipy)              |

## Screenshots

Captured from a production instance with the browser window at 1920x1080.
Numeric values on the dashboard heatmap, the CDF axes, and the analysis y-axis were blurred
in the browser before capture, and operator names were replaced with
`operator`, so the images contain no design parameters or personal names.
The execution screenshot is cropped (`crop=3440:1444:400:168`) so the task
detail panel stays visible inside the frame.

To refresh: sign in, resize the window to 1920x1080, capture each page listed
in `src/QDashDemo.tsx`, and keep the 3840:1612 aspect ratio (or adjust it in
`BrowserFrame.tsx`).

## BGM

`public/bgm.m4a` is an original 108 BPM track synthesized by
`scripts/make_bgm.py`, so there are no licensing constraints. Regenerate with:

```bash
uv run --with numpy --with scipy python3 scripts/make_bgm.py public/bgm.wav
ffmpeg -y -i public/bgm.wav -c:a aac -b:a 192k public/bgm.m4a
```

To use a licensed track instead, drop it into `public/` and change the
`<Audio>` source in `src/QDashDemo.tsx`. Fades are baked into the file
(0.5 s in, 3.5 s out), so a replacement should include its own.
