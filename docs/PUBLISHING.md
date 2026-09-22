# Create the GitHub repository and attach videos

This build produced a local source bundle; the connected GitHub integration did not expose repository creation or release-asset upload. **There is no claimed remote repository or successful remote push in the validation record.**

The included helper performs the missing external step using your own local, authorized GitHub CLI. It needs Git, `gh`, a successful `gh auth login`, network access, and your configured Git `user.name`/`user.email`.

Review the source, documentation and media, then from the extracted root:

```bash
python scripts/publish_github.py --public --release
```

It reads the authenticated login, targets `<login>/jev-skill-router`, creates a local main branch if needed, scans and stages allowlisted source/docs/media, commits, creates the **new** remote, and pushes. `--release` creates `v0.1.0` and attaches MP4s from `docs/media`. Omit `--release` to only publish the repository. `--private` is available instead of `--public`; `--name OTHER_NAME` chooses another new name.

An existing repository, existing remote, unexpected tracked file, recognizable secret or symlink stops the helper. It does not force-push, rewrite existing history, impersonate a Git author or use another connector's credentials. A failure may leave a local commit or a newly created remote; inspect the state rather than deleting/retrying blindly. Once a repo exists, subsequent updates should use the normal Git workflow, not the create-only helper.

The included `.github/workflows/test.yml` runs a small Python matrix on relevant changes. The Remotion workflow is **manual only**, not scheduled or automatically run on every push. No Actions execution has been observed until the files actually exist in a GitHub repository.

The source includes preview MP4s, not a claimed Remotion render. To replace/augment release media with actual Remotion outputs, follow [video/README.md](../video/README.md), inspect the rendered files, and upload them using your existing release workflow.
