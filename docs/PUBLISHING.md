# Publishing and releases

The public repository is [himomohi/jev-skill-router](https://github.com/himomohi/jev-skill-router). [v0.1.0](https://github.com/himomohi/jev-skill-router/releases/tag/v0.1.0) provides the source ZIP and English/Korean Remotion MP4s. Updates are committed directly to `main`.

Version 0.4.1 materials: [English update guide](updates/v0.4.1.md), [한국어 업데이트 안내](updates/v0.4.1.ko.md), [English changelog](../CHANGELOG.md), [한국어 변경 이력](../CHANGELOG.ko.md).

Updates to this existing repository use the [tested-version release workflow](RELEASING.md). After a successful Tests run for a main push, it publishes matching wheel, sdist, source ZIP and checksums at the exact tested SHA. PyPI publication is not configured. The initial-repository helper below is a separate manual workflow; it does not update this repository or provide that CI gate.

To publish a separate new repository, the included create-only helper uses your own authorized GitHub CLI. It needs Git, `gh`, a successful `gh auth login`, network access, and your configured Git `user.name`/`user.email`.

Review the source, documentation and media, then from the extracted root:

```bash
python scripts/publish_github.py --public --release
```

It reads the authenticated login, targets `<login>/jev-skill-router`, creates a local main branch if needed, scans and stages allowlisted source/docs/media, commits, creates the **new** remote, and pushes. `--release` creates the tag for the current `pyproject.toml` version at the pushed commit, uses its versioned notes, and attaches historical preview MP4s from `docs/media`. It does not rebuild current media or create the tested package assets described above. Omit `--release` to only publish the repository. `--private` is available instead of `--public`; `--name OTHER_NAME` chooses another new name.

An existing repository, existing remote, unexpected tracked file, recognizable secret or symlink stops the helper. It does not force-push, rewrite existing history, impersonate a Git author or use another connector's credentials. A failure may leave a local commit or a newly created remote; inspect the state rather than deleting/retrying blindly. Once a repo exists, subsequent updates should use the normal Git workflow, not the create-only helper.

The included `.github/workflows/test.yml` runs a small Python matrix on relevant changes. The Remotion workflow is **manual only**, not scheduled or automatically run on every push. The [Python matrix](https://github.com/himomohi/jev-skill-router/actions/runs/35685705223) and [Remotion render](https://github.com/himomohi/jev-skill-router/actions/runs/35685682423) both completed successfully.

The source includes separate preview MP4s. Release assets named `overview.en.mp4` and `overview.ko.mp4` are actual Remotion outputs. For future renders, follow [video/README.md](../video/README.md), inspect both languages, and upload the outputs to the appropriate release.
