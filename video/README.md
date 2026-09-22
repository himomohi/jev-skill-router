# Remotion overview / Remotion 소개 영상

Editable React/Remotion source: 30 seconds, 1280×720, 24 fps, English and Korean compositions. The comparison scene reads `docs/benchmark.json`; it does not hardcode a different marketing number. Motion is frame-driven, with no CSS animation or wall-clock timers. No external music, photos or font binaries are bundled.

## What was actually rendered?

The supplied `docs/media/preview.en.mp4` and `preview.ko.mp4` were rendered by **Pillow + FFmpeg**, using the same five-scene storyboard and benchmark. Their persistent footer identifies them as local preview-renderer output. They are conceptual animations, not live Jev or host recordings.

The **Remotion project rendered successfully** in [GitHub Actions run 35685682423](https://github.com/himomohi/jev-skill-router/actions/runs/35685682423) using the committed lockfile, dependency-backed TypeScript checking, and Noto Sans CJK. Download `overview.en.mp4` and `overview.ko.mp4` from [v0.1.0](https://github.com/himomohi/jev-skill-router/releases/tag/v0.1.0). Each video contains 720 frames at 1280×720 and 24 fps (30 seconds of video; container duration approximately 30.06 seconds). Both languages’ five scenes were visually inspected. These are conceptual animations, not live Jev or host recordings.

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

The GitHub Actions **Render Remotion videos (manual)** workflow installs, typechecks, renders both compositions and uploads workflow artifacts. It is not scheduled or automatically run on every push. The successful run is linked above; its `remotion-overviews` artifact contains both MP4s.

## Reproduce the separate local previews

The preview renderer is a different program, not a fake Remotion runtime:

```bash
python -m pip install Pillow
python scripts/render_preview.py --lang en
python scripts/render_preview.py --lang ko --font /path/to/a/Korean-capable-font.ttf
```

Run from the repository root. FFmpeg must be on PATH. Common installed fonts are detected; no font is downloaded or redistributed. The two renderers share content and data, not pixel-identical rendering guarantees.

## 한국어 안내

영어·한국어 30초 Remotion 영상과 편집 가능한 소스를 제공합니다. GitHub Actions에서 의존성 설치, TypeScript 검사, 두 언어 렌더링을 완료하고 각 5개 장면을 확인했습니다. [v0.1.0](https://github.com/himomohi/jev-skill-router/releases/tag/v0.1.0)의 `overview.en.mp4`, `overview.ko.mp4`가 실제 Remotion 출력입니다. 저장소의 `preview.*.mp4`는 별도 Pillow·FFmpeg 미리보기입니다. 두 영상 모두 설계 설명용이며 실제 Jev 사용 녹화가 아닙니다.

`npm ci → npm run typecheck → npm run render`로 실제 Remotion 출력을 만들 수 있습니다. GitHub에는 수동 실행형 영상 워크플로를 제공합니다. 수치는 `docs/benchmark.json`을 읽으며, 바이트 감소를 토큰·비용·속도 개선으로 바꾸어 표시하지 않습니다.
