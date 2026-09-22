"""Validate, build and safely publish a tested version. No credentials are printed.

`check` is local and read-only. `prepare` reads remote release state. `build`
writes dist/. `publish` is restricted to a successful same-repository main push
Tests workflow and only creates missing tags, releases or assets.
"""
from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
SHA = re.compile(r"[a-f0-9]{40}")


def run(*args: str, cwd: Path = ROOT, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, **kwargs)


def metadata(root: Path) -> str:
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError("Release version must use stable MAJOR.MINOR.PATCH syntax")
    source = ast.parse((root / "src/jev_skill_router/__init__.py").read_text(encoding="utf-8"))
    values = [ast.literal_eval(node.value) for node in source.body
              if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)]
    if values != [version]:
        raise ValueError("Package and pyproject versions do not match")
    for name in ("CHANGELOG.md", "CHANGELOG.ko.md"):
        headings = re.findall(r"^## ([0-9]+\.[0-9]+\.[0-9]+)(?:\s|$)", (root / name).read_text(encoding="utf-8"), re.M)
        if not headings or headings[0] != version:
            raise ValueError(f"Newest release in {name} does not match {version}")
    for suffix in ("md", "ko.md"):
        path = root / f"docs/updates/v{version}.{suffix}"
        first = path.read_text(encoding="utf-8").splitlines()[0]
        if not first.startswith("# ") or not re.search(rf"(?<![\d.]){re.escape(version)}(?![\d.])", first):
            raise ValueError(f"Release notes heading does not match version: {path.name}")
    return version


def trusted_event(expected_sha: str, environ=None) -> str:
    env = os.environ if environ is None else environ
    if not SHA.fullmatch(expected_sha):
        raise ValueError("Expected a full tested commit SHA")
    if env.get("GITHUB_EVENT_NAME") != "workflow_run":
        raise ValueError("Publishing requires a trusted Tests workflow_run event")
    event = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    workflow = event.get("workflow_run", {})
    repo = env.get("GITHUB_REPOSITORY", "")
    if (repo != "himomohi/jev-skill-router"
            or workflow.get("name") != "Tests"
            or workflow.get("event") != "push"
            or workflow.get("conclusion") != "success"
            or workflow.get("head_branch") != "main"
            or (workflow.get("head_repository") or {}).get("full_name") != repo
            or workflow.get("head_sha") != expected_sha):
        raise ValueError("Release requires successful Tests for this repository's main push and exact SHA")
    return repo


def check_checkout(root: Path, sha: str) -> None:
    if not SHA.fullmatch(sha) or run("git", "rev-parse", "HEAD", cwd=root).stdout.decode().strip() != sha:
        raise ValueError("Checkout differs from tested commit")
    run("git", "diff", "--exit-code", "HEAD", "--", cwd=root)


class GitHub:
    def __init__(self, repository: str):
        self.repository = repository

    def api(self, path: str, payload: dict | None = None):
        args = ["gh", "api", f"repos/{self.repository}/{path}"]
        options = {}
        if payload is not None:
            args += ["--method", "POST", "--input", "-"]
            options["input"] = json.dumps(payload).encode()
        try:
            return json.loads(run(*args, **options).stdout)
        except subprocess.CalledProcessError as exc:
            # Authentication/network/server errors must never be treated as absence.
            if payload is None and b"(HTTP 404)" in (exc.stderr or b""):
                return None
            raise

    def tag_sha(self, tag: str) -> str | None:
        ref = self.api(f"git/ref/tags/{tag}")
        if ref is None:
            return None
        obj = ref["object"]
        for _ in range(5):
            if obj["type"] == "commit" and SHA.fullmatch(obj["sha"]):
                return obj["sha"]
            if obj["type"] != "tag" or not SHA.fullmatch(obj["sha"]):
                break
            annotation = self.api(f"git/tags/{obj['sha']}")
            if annotation is None:
                break
            obj = annotation["object"]
        raise ValueError("Existing version tag does not resolve to a commit")

    def release(self, tag: str):
        # The tag endpoint returns published releases only. Drafts must be
        # discovered through the authenticated list and refreshed by numeric ID.
        published = self.api(f"releases/tags/{tag}")
        if published is not None:
            return published
        matches = []
        for page in range(1, 11):
            entries = self.api(f"releases?per_page=100&page={page}")
            if not isinstance(entries, list):
                raise ValueError("Could not inspect draft releases")
            matches.extend(item for item in entries if isinstance(item, dict) and item.get('tag_name') == tag)
            if len(entries) < 100:
                break
        else:
            raise ValueError("Release listing exceeds the supported discovery bound")
        if len(matches) > 1:
            raise ValueError("Multiple releases use this tag; manual review required")
        if not matches:
            return None
        identifier = matches[0].get('id')
        if type(identifier) is not int or identifier <= 0:
            raise ValueError("Invalid draft release identifier")
        release = self.api(f"releases/{identifier}")
        if not isinstance(release, dict) or release.get('tag_name') != tag:
            raise ValueError("Draft release changed during inspection")
        return release

    def create_tag(self, tag: str, sha: str) -> None:
        self.api("git/refs", {"ref": f"refs/tags/{tag}", "sha": sha})

    def release_command(self, *args: str):
        return run("gh", "release", *args, "--repo", self.repository)

    def asset_bytes(self, asset: dict) -> bytes:
        identifier = asset.get("id")
        if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0:
            raise ValueError("Invalid remote release asset identifier")
        return run("gh", "api", f"repos/{self.repository}/releases/assets/{identifier}",
                   "--header", "Accept: application/octet-stream").stdout


def eligible(github: GitHub, tag: str, sha: str, root: Path = ROOT) -> bool:
    existing = github.tag_sha(tag)
    if existing is None or existing == sha:
        return True
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", existing, sha], cwd=root,
                              capture_output=True)
    if ancestor.returncode == 0:
        print(f"{tag} is already associated with an earlier commit; no release for this unchanged version.")
        return False
    raise ValueError("Existing version tag points to an unrelated commit; refusing to modify it")


def normalize_zip(path: Path, epoch: int) -> None:
    output = io.BytesIO()
    stamp = time.gmtime(max(epoch, 315532800))[:6]  # ZIP cannot represent dates before 1980.
    with zipfile.ZipFile(path) as original, zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as result:
        for item in sorted(original.infolist(), key=lambda x: x.filename):
            info = zipfile.ZipInfo(item.filename, stamp)
            info.create_system = 3
            info.external_attr = item.external_attr
            info.compress_type = zipfile.ZIP_DEFLATED
            result.writestr(info, original.read(item), compresslevel=9)
    path.write_bytes(output.getvalue())


def normalize_sdist(path: Path, epoch: int) -> None:
    output = io.BytesIO()
    with tarfile.open(path, "r:gz") as original, gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=epoch) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as result:
            for member in sorted(original.getmembers(), key=lambda x: x.name):
                data = original.extractfile(member) if member.isfile() else None
                member.uid = member.gid = 0
                member.uname = member.gname = ""
                member.mtime = epoch
                member.pax_headers = {}
                result.addfile(member, data)
    path.write_bytes(output.getvalue())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def asset_names(version: str) -> set[str]:
    return {f"jev_skill_router-{version}-py3-none-any.whl", f"jev_skill_router-{version}.tar.gz",
            f"jev-skill-router-{version}-source.zip"}


def build(root: Path, output: Path, version: str, sha: str) -> None:
    check_checkout(root, sha)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Release output directory must be empty; no existing files were changed")
    epoch = int(run("git", "show", "-s", "--format=%ct", sha, cwd=root).stdout)
    env = dict(os.environ, SOURCE_DATE_EPOCH=str(epoch), PYTHONHASHSEED="0")
    run(sys.executable, "-m", "build", "--no-isolation", "--outdir", str(output), cwd=root, env=env)
    source = output / f"jev-skill-router-{version}-source.zip"
    run("git", "archive", "--format=zip", f"--prefix=jev-skill-router-{version}/",
        "--output", str(source), sha, cwd=root)
    if {path.name for path in output.iterdir()} != asset_names(version):
        raise ValueError("Unexpected package names or extra files in release output")
    for path in output.iterdir():
        if path.name.endswith(".tar.gz"):
            normalize_sdist(path, epoch)
        else:
            normalize_zip(path, epoch)
    sums = "".join(f"{digest(path)}  {path.name}\n" for path in sorted(output.iterdir()))
    (output / "SHA256SUMS").write_text(sums, encoding="utf-8", newline="\n")
    print(f"Built {version}: wheel, sdist, source ZIP and SHA256SUMS")


def local_assets(output: Path, version: str) -> dict[str, Path]:
    expected = asset_names(version)
    files = {path.name: path for path in output.iterdir() if path.is_file() and not path.is_symlink()}
    if set(files) != expected | {"SHA256SUMS"}:
        raise ValueError("Missing or unexpected release assets")
    lines = files["SHA256SUMS"].read_text(encoding="utf-8").splitlines()
    valid = {f"{digest(files[name])}  {name}" for name in expected}
    if len(lines) != len(expected) or set(lines) != valid:
        raise ValueError("Release checksums do not match local packages")
    return files


def missing_assets(github: GitHub, release: dict, assets: dict[str, Path]) -> list[str]:
    existing = release.get("assets", [])
    names = [item.get("name") for item in existing]
    if len(set(names)) != len(names) or any(name not in assets for name in names):
        raise ValueError("Release contains duplicate or unexpected assets; nothing was overwritten")
    # Verify every existing file before adding anything to a partial release.
    for item in existing:
        content = github.asset_bytes(item)
        if hashlib.sha256(content).hexdigest() != digest(assets[item["name"]]):
            raise ValueError(f"Existing release asset differs: {item['name']}; refusing to overwrite")
    return sorted(set(assets) - set(names))


def publish(github: GitHub, root: Path, output: Path, version: str, sha: str) -> None:
    assets = local_assets(output, version)
    tag = f"v{version}"
    existing = github.tag_sha(tag)
    if existing not in (None, sha):
        raise ValueError("Version tag changed; refusing to move or overwrite it")
    release = github.release(tag)
    if release is not None:
        # A release with a missing remote tag is inconsistent. Do not repair it
        # by silently creating a tag at the new tested commit.
        if existing is None:
            raise ValueError("Existing release has no version tag; manual review required")
        missing = missing_assets(github, release, assets)
    else:
        missing = sorted(assets)
    if existing is None:
        github.create_tag(tag, sha)
    if github.tag_sha(tag) != sha:
        raise ValueError("Version tag does not match the tested commit")
    if release is None:
        github.release_command("create", tag, "--verify-tag", "--draft", "--title", f"Jev Skill Router {version}",
                               "--notes-file", str(root / f"docs/updates/{tag}.md"))
    for name in missing:
        github.release_command("upload", tag, str(assets[name]))  # Deliberately no --clobber.
    complete = github.release(tag)
    if complete is None or missing_assets(github, complete, assets):
        raise ValueError("Release assets are incomplete; draft retained for retry")
    if github.tag_sha(tag) != sha:
        raise ValueError("Version tag changed before publication")
    if complete.get("draft"):
        github.release_command("edit", tag, "--draft=false", "--latest")
    print(f"Verified release: https://github.com/{github.repository}/releases/tag/{tag}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "prepare", "build", "publish"))
    parser.add_argument("--sha", help="Full SHA of the successful Tests workflow")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args(argv)
    version = metadata(ROOT)
    if args.command == "check":
        print(f"Release metadata is consistent: {version}")
        return 0
    if args.sha is None:
        parser.error("--sha is required")
    check_checkout(ROOT, args.sha)
    if args.command == "build":
        build(ROOT, args.output.resolve(), version, args.sha)
        return 0
    github = GitHub(trusted_event(args.sha))
    if args.command == "prepare":
        needed = eligible(github, f"v{version}", args.sha)
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write(f"publish_needed={str(needed).lower()}\nversion={version}\n")
    else:
        publish(github, ROOT, args.output.resolve(), version, args.sha)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        # subprocess errors can contain authentication output. Report the stage,
        # never captured stderr/stdout or environment values.
        message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(f"Release stopped: {message}", file=sys.stderr)
        raise SystemExit(1)
