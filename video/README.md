# Remotion overview / Remotion 소개 영상

Editable React/Remotion source: 30 seconds, 1280×720, 24 fps, English and Korean compositions. The comparison scene reads `docs/benchmark.json`; it does not hardcode a different marketing number. Motion is frame-driven, with no CSS animation or wall-clock timers. No external music, photos or font binaries are bundled.

## What was actually rendered?

The supplied `docs/media/preview.en.mp4` and `preview.ko.mp4` were rendered by **Pillow + FFmpeg**, using the same five-scene storyboard and benchmark. Their persistent footer identifies them as local preview-renderer output. They are conceptual animations, not live Jev or host recordings.

The **Remotion project has not yet been rendered**. In the Work continuation, npm ciation succeeded, a transitive dependency lockfile was generated, and `npm run typecheck` passed. Rendering stopped while downloading Chrome Headless Shell because the network proxy tunnel timed out. Actual Remotion layout/rendering remains unverified. Do not describe the preview files as successful Remotion renders.

## Render with Remotion

With Node.js 20+ and network access:

```bash
cd video
npm ci
npm run typecheck
npm run render
```

This produces `docs/media/overview.en.mp4` and `overview.ko.mp4`, keeping previews separate. Direct Remotion packages use 4.0.506; React uses 19.0.0. The committed `package-lock.json` pins transitive dependencies; `npm ci` installs that exact dependency tree.

The documented CLI supports `--browser-executable=/absolute/path/to/chromium`. Otherwise a browser download may be needed. Install a Korean-capable system font, such as Noto Sans CJK, and inspect line wrapping on your platform. Fonts are not bundled.

```bash
npm run studio
npx remotion render src/index.tsx OverviewKO out/overview.ko.mp4 --concurrency=2
```

The GitHub Actions **Render Remotion videos (manual)** workflow installs, typechecks, renders both compositions and uploads workflow artifacts. It is not scheduled or automatically run on every push. No successful GitHub run is claimed in this bundle.

## Reproduce the separate local previews

The preview renderer is a different program, not a fake Remotion runtime:

```bash
python -m pip install Pillow
python scripts/render_preview.py --lang en
python scripts/render_preview.py --lang ko --font /path/to/a/Korean-capable-font.ttf
```

Run from the repository root. FFmpeg must be on PATH. Common installed fonts are detected; no font is downloaded or redistributed. The two renderers share content and data, not pixel-identical rendering guarantees.

## 한국어 안내

영어·한국어 30초 영상의 Remotion 소스를 포함합니다. 실제 제공한 MP4는 Pillow와 FFmpeg로 제작한 **별도 미리보기**이며, 화면 아래에도 이를 표시합니다. Work에서 의존성 설치와 TypeScript 검사는 통과했습니다. 렌더링은 Chrome Headless Shell 다운로드 중 네트워크 시간 초과로 중단되어, Remotion 렌더링 성공이나 실제 Jev 사용 녹화를 주장하지 않습니다.

`npm ci → npm run typecheck → npm run render`로 실제 Remotion 출력을 만들 수 있습니다. GitHub에는 수동 실행형 영상 워크플로를 제공합니다. 수치는 `docs/benchmark.json`을 읽으며, 바이트 감소를 토큰·비용·속도 개선으로 바꾸어 표시하지 않습니다.
