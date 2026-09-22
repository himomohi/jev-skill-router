"""Regression checks for publication guards and interrupted-release recovery."""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_release", ROOT / "scripts/build_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
COMMIT = "a" * 40


def test_repository_release_metadata_agrees():
    release.metadata(ROOT)


@pytest.fixture
def metadata_tree(tmp_path):
    (tmp_path / "src/jev_skill_router").mkdir(parents=True)
    (tmp_path / "docs/updates").mkdir(parents=True)
    files = {"pyproject.toml": '[project]\nversion="1.2.3"\n',
             "src/jev_skill_router/__init__.py": '__version__="1.2.3"\n',
             "CHANGELOG.md": "# Changelog\n\n## 1.2.3 — today\n",
             "CHANGELOG.ko.md": "# 변경 내역\n\n## 1.2.3 — today\n",
             "docs/updates/v1.2.3.md": "# Jev Skill Router 1.2.3\n\nNotes.\n",
             "docs/updates/v1.2.3.ko.md": "# Jev Skill Router 1.2.3\n\n업데이트.\n"}
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("file", ["src/jev_skill_router/__init__.py", "CHANGELOG.md", "CHANGELOG.ko.md",
                                  "docs/updates/v1.2.3.md", "docs/updates/v1.2.3.ko.md"])
def test_version_drift_blocks_release(metadata_tree, file):
    path = metadata_tree / file
    path.write_text(path.read_text(encoding="utf-8").replace("1.2.3", "1.2.2"), encoding="utf-8")
    with pytest.raises(ValueError):
        release.metadata(metadata_tree)


def event_environment(tmp_path, **changes):
    workflow = dict(name="Tests", event="push", conclusion="success", head_branch="main", head_sha=COMMIT,
                    head_repository={"full_name": "himomohi/jev-skill-router"})
    workflow.update(changes)
    path = tmp_path / "event.json"
    path.write_text(json.dumps({"workflow_run": workflow}), encoding="utf-8")
    return dict(GITHUB_EVENT_NAME="workflow_run", GITHUB_EVENT_PATH=str(path),
                GITHUB_REPOSITORY="himomohi/jev-skill-router")


@pytest.mark.parametrize("changes", [{"event": "pull_request"}, {"event": "workflow_dispatch"},
                                     {"conclusion": "failure"}, {"head_branch": "feature"},
                                     {"head_repository": {"full_name": "attacker/fork"}},
                                     {"head_repository": None}, {"head_sha": "b" * 40}, {"name": "Other"}])
def test_non_main_or_untrusted_workflow_cannot_publish(tmp_path, changes):
    with pytest.raises(ValueError):
        release.trusted_event(COMMIT, event_environment(tmp_path, **changes))


def test_trusted_workflow_and_exact_sha_required(tmp_path):
    environment = event_environment(tmp_path)
    assert release.trusted_event(COMMIT, environment) == "himomohi/jev-skill-router"
    environment["GITHUB_EVENT_NAME"] = "push"
    with pytest.raises(ValueError, match="workflow_run"):
        release.trusted_event(COMMIT, environment)


def packages(tmp_path):
    output = tmp_path / "dist"
    output.mkdir()
    for name in release.asset_names("1.2.3"):
        (output / name).write_bytes(f"package {name}".encode())
    (output / "SHA256SUMS").write_text("".join(f"{release.digest(path)}  {path.name}\n"
                                               for path in sorted(output.iterdir())), encoding="utf-8")
    return output


class FakeGitHub:
    repository = "himomohi/jev-skill-router"

    def __init__(self, tag=None, draft=None):
        self.tag = tag
        self.current = None if draft is None else {"draft": draft, "assets": []}
        self.contents = {}
        self.writes = []

    def tag_sha(self, tag):
        return self.tag

    def release(self, tag):
        return self.current

    def create_tag(self, tag, sha):
        assert self.tag is None
        self.writes.append(("tag", tag, sha))
        self.tag = sha

    def asset_bytes(self, item):
        return self.contents[item["name"]]

    def release_command(self, command, *args):
        self.writes.append((command, *args))
        assert "--clobber" not in args
        if command == "create":
            assert self.current is None and "--verify-tag" in args and "--draft" in args
            self.current = {"draft": True, "assets": []}
        elif command == "upload":
            path = Path(args[1])
            assert path.name not in self.contents
            self.contents[path.name] = path.read_bytes()
            self.current["assets"].append({"name": path.name, "id": len(self.contents)})
        elif command == "edit":
            assert len(self.contents) == 4
            self.current["draft"] = False
        else:
            pytest.fail(f"Unexpected release mutation: {command}")


def test_new_release_is_complete_before_publication_and_rerun_does_not_write(tmp_path):
    github = FakeGitHub()
    output = packages(tmp_path)
    release.publish(github, tmp_path, output, "1.2.3", COMMIT)
    assert github.writes[0] == ("tag", "v1.2.3", COMMIT)
    assert github.writes[-1][0] == "edit" and not github.current["draft"]
    first_writes = list(github.writes)
    release.publish(github, tmp_path, output, "1.2.3", COMMIT)
    assert github.writes == first_writes


def test_interrupted_draft_only_uploads_missing_assets(tmp_path):
    output = packages(tmp_path)
    github = FakeGitHub(COMMIT, draft=True)
    name = sorted(release.asset_names("1.2.3"))[0]
    github.contents[name] = (output / name).read_bytes()
    github.current["assets"].append({"name": name, "id": 1})
    release.publish(github, tmp_path, output, "1.2.3", COMMIT)
    assert [entry[0] for entry in github.writes] == ["upload", "upload", "upload", "edit"]


def test_mismatched_existing_asset_fails_before_any_mutation(tmp_path):
    output = packages(tmp_path)
    github = FakeGitHub(COMMIT, draft=True)
    name = sorted(release.asset_names("1.2.3"))[0]
    github.contents[name] = b"different published package"
    github.current["assets"].append({"name": name, "id": 1})
    with pytest.raises(ValueError, match="refusing to overwrite"):
        release.publish(github, tmp_path, output, "1.2.3", COMMIT)
    assert not github.writes


def test_existing_version_tag_never_moved(tmp_path):
    github = FakeGitHub("b" * 40)
    with pytest.raises(ValueError, match="refusing to move"):
        release.publish(github, tmp_path, packages(tmp_path), "1.2.3", COMMIT)
    assert not github.writes


def test_damaged_local_asset_is_not_published(tmp_path):
    output = packages(tmp_path)
    (output / sorted(release.asset_names("1.2.3"))[0]).write_bytes(b"changed after build")
    github = FakeGitHub()
    with pytest.raises(ValueError, match="checksums"):
        release.publish(github, tmp_path, output, "1.2.3", COMMIT)
    assert not github.writes


def test_release_with_missing_tag_requires_review(tmp_path):
    github = FakeGitHub(None, draft=True)
    with pytest.raises(ValueError, match="no version tag"):
        release.publish(github, tmp_path, packages(tmp_path), "1.2.3", COMMIT)
    assert not github.writes


def test_same_version_on_descendant_commit_skips_release(monkeypatch):
    github = FakeGitHub("b" * 40)
    monkeypatch.setattr(release.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0))
    assert not release.eligible(github, "v1.2.3", COMMIT)
    assert not github.writes


@pytest.mark.parametrize("error", [b"gh: unavailable (HTTP 503)", b"gh: Bad credentials (HTTP 401)", b"network failure"])
def test_api_errors_never_misidentified_as_missing_tag(monkeypatch, error):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args, stderr=error)
    monkeypatch.setattr(release, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        release.GitHub("himomohi/jev-skill-router").tag_sha("v1.2.3")


def test_packaging_timestamps_do_not_break_asset_retry_checksums(tmp_path):
    zips, tars = [], []
    for index in (1, 2):
        zpath = tmp_path / f"{index}.whl"
        with zipfile.ZipFile(zpath, "w") as archive:
            info = zipfile.ZipInfo("module.py", (2020 + index, 1, 1, 0, 0, 0))
            archive.writestr(info, b"print('same content')\n")
        release.normalize_zip(zpath, 1700000000)
        zips.append(zpath.read_bytes())
        tpath = tmp_path / f"{index}.tar.gz"
        with tarfile.open(tpath, "w:gz") as archive:
            info = tarfile.TarInfo("module.py")
            info.mtime = index
            info.uid = info.gid = index
            info.uname = f"builder{index}"
            info.size = 4
            archive.addfile(info, io.BytesIO(b"same"))
        release.normalize_sdist(tpath, 1700000000)
        tars.append(tpath.read_bytes())
    assert zips[0] == zips[1] and tars[0] == tars[1]
    with zipfile.ZipFile(io.BytesIO(zips[0])) as archive:
        assert archive.read("module.py") == b"print('same content')\n"
    with tarfile.open(fileobj=io.BytesIO(tars[0]), mode="r:gz") as archive:
        assert archive.extractfile("module.py").read() == b"same"
