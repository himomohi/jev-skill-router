# Publishing a tested version

The `Release` workflow publishes a GitHub release after the **Tests** workflow
passes for a push to `main` in `himomohi/jev-skill-router`. It checks out the exact
passed commit. Pull requests, forks, failed tests and manual Tests runs cannot
publish. Only the release job has `contents: write`; no personal access token is
required. This publishes GitHub assets, not a package to PyPI.

## Prepare a version

Update these together in a reviewed commit:

- `pyproject.toml` and `src/jev_skill_router/__init__.py`.
- The newest release heading in `CHANGELOG.md` and `CHANGELOG.ko.md`.
- `docs/updates/vVERSION.md` and `docs/updates/vVERSION.ko.md`, with that version
  in their first heading. Include upgrade steps and known limitations.

Use a stable `MAJOR.MINOR.PATCH` version. Run:

```bash
python scripts/build_release.py check
python -m pytest -q
```

Push the reviewed commit to `main` using the normal authorized publishing
process. Watch **Tests**, then **Release**, in GitHub Actions. An unchanged
version already tagged at an ancestor commit is skipped, so a later documentation
or test correction does not silently repackage the same version.

## Release assets and integrity

Each release contains a Python wheel, source distribution, complete tracked
source ZIP, and `SHA256SUMS`. The source ZIP includes the guided installers,
examples and documentation. The wheel is suitable for installation into an
existing Python environment. Assets come from the tested commit, with pinned
packaging tools and normalized archive timestamps to support reproducible
retries. Checksums detect changed download bytes; they are not digital signatures.

For an independently downloaded asset, compare its SHA-256 with the entry in
`SHA256SUMS`. On Linux, place all four assets together and run
`sha256sum --check SHA256SUMS`; on macOS, use `shasum -a 256 -c SHA256SUMS`.
In PowerShell, use `Get-FileHash -Algorithm SHA256 <downloaded-file>` and compare
the returned hash with its entry.

To exercise packaging locally, use a clean, committed checkout and an empty
output directory. This does not publish:

```bash
python -m pip install 'build==1.2.2.post1' 'setuptools==80.9.0' 'wheel==0.45.1'
python scripts/build_release.py build --sha "$(git rev-parse HEAD)" --output dist
```

## Recover an interrupted run

Rerun the failed **Release** job for the original tested commit. A created tag is
never moved. The script verifies every existing asset against the freshly built
package, uploads only missing files, checks the complete result, then publishes
the draft. A rerun of an already complete matching release makes no changes.

If a tag points at a different commit or an existing asset has different bytes,
publication stops. Inspect the failed run and existing release. Correct a source
or packaging change under a **new version**; do not overwrite the old asset or
force-move a published tag. Existing tags on unrelated history also require
manual review. This project does not automatically enable GitHub repository-wide
immutable-release settings; its own publisher is create-only for tags and assets.

## Security rationale and references

GitHub warns that `workflow_run` can have write access even when the upstream
workflow did not. The job guard and publisher both require a successful Tests
push from this repository's `main`; checkout uses `head_sha`, not the current
branch head. It does not download or execute upstream PR artifacts, and checkout
does not persist credentials. Publishing explicitly creates a tag at the tested
commit and uses `gh release create --verify-tag` with a draft. Asset upload never
uses `--clobber`.

- [GitHub workflow_run event and security warning](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
- [GitHub CLI release creation and --verify-tag](https://cli.github.com/manual/gh_release_create)
- [GitHub CLI asset upload and --clobber behavior](https://cli.github.com/manual/gh_release_upload)
- [Git reference creation API](https://docs.github.com/en/rest/git/refs#create-a-reference)

This pipeline validates packaging and release provenance. It does not establish
live Jev accuracy, billed cost savings or real host task success.
