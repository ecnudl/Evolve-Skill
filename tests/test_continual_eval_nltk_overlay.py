import hashlib
import io
import json
import os
import stat
import subprocess
import zipfile
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import nltk_overlay as overlay
from skillopt.continual_eval.core import read_json


def archive(entries=None, *, symlink=False):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as target:
        for name, value in entries or [("punkt/PY3/english.pickle", b"not unpickled")]:
            info = zipfile.ZipInfo(name)
            if symlink:
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            target.writestr(info, value)
    payload = data.getvalue()
    spec = {"name": "punkt", "subdir": "tokenizers", "bytes": len(payload), "expanded_max": 1024,
            "sha256": hashlib.sha256(payload).hexdigest(), "required_member": "punkt/PY3/english.pickle"}
    return payload, spec


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    payload, spec = archive()
    monkeypatch.setattr(overlay, "PACKAGES", (spec,))
    calls = []
    monkeypatch.setattr(overlay, "_fetch", lambda item: calls.append(item) or payload)
    root = tmp_path / "overlay"
    result = overlay.prepare(root)
    return root, result, calls


def test_prepare_is_data_only_and_exact_replay(prepared):
    root, result, calls = prepared
    manifest = overlay.check(root)
    assert result["status"] == "prepared_not_built" and len(calls) == 1
    assert manifest["model_calls"] == 0 and manifest["host_deserialization"] is False
    assert manifest["version"] == "bcb-nltk-data-overlay-v2" and manifest["builder"] == overlay.BUILDER
    assert (root / "context/nltk_data/tokenizers/punkt/PY3/english.pickle").read_bytes() == b"not unpickled"
    assert all(p.stat().st_mode & 0o777 == 0o755 for p in (root / "context/nltk_data").rglob("*") if p.is_dir())
    commands = [line for line in (root / "context/Dockerfile").read_text().splitlines() if not line.startswith("#")]
    assert commands == [f"FROM {overlay.BASE_IMAGE}", "COPY nltk_data/ /usr/share/nltk_data/"]
    with pytest.raises(ValueError, match="new private"):
        overlay.prepare(root)


@pytest.mark.parametrize("name", ["../english.pickle", "/punkt/english.pickle", "punkt/../english.pickle",
                                 "punkt\\english.pickle", "punkt//english.pickle", "punkt/./english.pickle",
                                 "other/english.pickle", "punkt/C:english.pickle"])
def test_archive_rejects_unsafe_paths(name):
    payload, spec = archive([(name, b"x")])
    with pytest.raises(ValueError, match="Unsafe archive path"):
        overlay._members(payload, spec)


def test_archive_rejects_symlink_duplicate_and_expansion():
    payload, spec = archive(symlink=True)
    with pytest.raises(ValueError, match="Link/special"):
        overlay._members(payload, spec)
    with pytest.warns(UserWarning):
        payload, spec = archive([("punkt/PY3/english.pickle", b"x"), ("punkt/PY3/english.pickle", b"y")])
    with pytest.raises(ValueError, match="Unsafe archive path"):
        overlay._members(payload, spec)
    payload, spec = archive()
    with pytest.raises(ValueError, match="expansion"):
        overlay._members(payload, {**spec, "expanded_max": 1})
    with pytest.raises(ValueError, match="size/SHA256"):
        overlay._members(payload + b"x", spec)
    with pytest.raises(ValueError, match="size/SHA256"):
        overlay._members(payload, {**spec, "sha256": "0" * 64})


@pytest.mark.parametrize("target", ["context/Dockerfile", "context/nltk_data/tokenizers/punkt/PY3/english.pickle", "archives/punkt.zip"])
def test_changed_context_or_archive_is_rejected(prepared, target):
    root, _, _ = prepared
    (root / target).write_bytes(b"changed")
    with pytest.raises(ValueError):
        overlay.check(root)


def test_extra_context_and_symlink_are_rejected(prepared):
    root, _, _ = prepared
    (root / "context/extra").symlink_to(root / "manifest.json")
    with pytest.raises(ValueError, match="Symlink"):
        overlay.check(root)


@pytest.mark.parametrize("extra", [False, True])
def test_resealed_context_still_must_match_official_archive(prepared, extra):
    root, _, _ = prepared
    path = root / "context/nltk_data/tokenizers/punkt/PY3/english.pickle"
    if extra:
        path = path.with_name("other.pickle")
    path.write_bytes(b"not official archive bytes")
    path.chmod(0o644)
    manifest = read_json(root / "manifest.json", sealed=True)
    manifest.pop("record_hash")
    manifest["context_files"] = overlay._files(root / "context")
    (root / "manifest.json").write_text(json.dumps(seal(manifest)))
    with pytest.raises(ValueError, match="official archive contents"):
        overlay.check(root)


def test_failed_download_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(overlay, "_fetch", lambda _: b"wrong")
    root = tmp_path / "failed"
    with pytest.raises(ValueError):
        overlay.prepare(root)
    failure = read_json(root / "prepare-failure.json", sealed=True)
    assert failure["status"] == "failed" and failure["model_calls"] == 0
    assert not (root / "manifest.json").exists()


def images(monkeypatch, *, wrong_layers=False, wrong_config=False):
    base = {"Id": overlay.BASE_IMAGE, "RootFS": {"Layers": ["sha256:old"]}, "Config": {"Env": ["A=1"]}}
    image_id = "sha256:" + "c" * 64
    built = deepcopy(base)
    built.update(Id=image_id)
    built["RootFS"]["Layers"] += ["sha256:new"]
    if wrong_layers:
        built["RootFS"]["Layers"][0] = "sha256:other"
    if wrong_config:
        built["Config"]["Env"] = ["A=2"]
    monkeypatch.setattr(overlay, "_image", lambda key: base if key == overlay.BASE_IMAGE else built)
    return image_id


def test_build_has_no_tag_pull_network_or_execution(prepared, monkeypatch):
    root, _, _ = prepared
    image_id = images(monkeypatch)
    calls = []

    def command(args, **kwargs):
        calls.append((args, kwargs))
        (root / "image.id").write_text(image_id)

    monkeypatch.setattr(overlay.subprocess, "run", command)
    monkeypatch.setenv("DOCKER_BUILDKIT", "1")
    result = overlay.build(root)
    assert result["status"] == "built_not_qualified" and result["qualification_performed"] is False
    assert result["image_id"] == image_id and result["model_calls"] == 0
    assert calls[0][0] == ["docker", "build", "--pull=false", "--network=none", "--iidfile",
                           str(root / "image.id"), str(root / "context")]
    assert calls[0][1]["timeout"] == 600
    assert calls[0][1]["env"]["DOCKER_BUILDKIT"] == "0"
    assert os.environ["DOCKER_BUILDKIT"] == "1"  # No global/shell/daemon change.
    assert result["builder"] == read_json(root / "build-intent.json", sealed=True)["builder"] == overlay.BUILDER
    with pytest.raises(ValueError, match="already attempted"):
        overlay.build(root)


@pytest.mark.parametrize("change", ["version", "builder"])
def test_old_protocol_or_changed_builder_is_not_reused(prepared, change):
    root, _, _ = prepared
    value = read_json(root / "manifest.json", sealed=True)
    value.pop("record_hash")
    value[change] = "bcb-nltk-data-overlay-v1" if change == "version" else {"engine": "buildkit"}
    (root / "manifest.json").write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError, match="Overlay identity changed"):
        overlay.check(root)


@pytest.mark.parametrize("wrong_layers,wrong_config", [(True, False), (False, True)])
def test_build_cannot_change_runtime_or_base(prepared, monkeypatch, wrong_layers, wrong_config):
    root, _, _ = prepared
    image_id = images(monkeypatch, wrong_layers=wrong_layers, wrong_config=wrong_config)
    monkeypatch.setattr(overlay.subprocess, "run", lambda *args, **kwargs: (root / "image.id").write_text(image_id))
    result = overlay.build(root)
    assert result["status"] == "build_failed_or_unverified" and "image_id" not in result
    assert read_json(root / "build-receipt.json", sealed=True) == result


def test_build_failure_preserved_not_retried(prepared, monkeypatch):
    root, _, _ = prepared
    images(monkeypatch)

    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("docker", 600)

    monkeypatch.setattr(overlay.subprocess, "run", fail)
    result = overlay.build(root)
    assert result["status"] == "build_failed_or_unverified" and result["error_type"] == "TimeoutExpired"
    with pytest.raises(ValueError, match="already attempted"):
        overlay.build(root)


def test_cli_check_reports_no_new_execution(prepared, capsys):
    root, _, _ = prepared
    overlay.main(["check", "--output", str(root)])
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "validated_not_built" and value["model_calls"] == 0
