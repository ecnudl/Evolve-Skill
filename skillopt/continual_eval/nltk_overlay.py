"""Build a reviewed data-only NLTK layer; never execute/unpickle downloaded data."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
import subprocess
import time
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from skillopt.coevolution_v5.core import seal

from .core import output_lock, read_json, require, safe_path, write_json

VERSION = "bcb-nltk-data-overlay-v2"
BUILDER = {"engine": "legacy", "child_environment": {"DOCKER_BUILDKIT": "0"}}
BASE_IMAGE = "sha256:b13b0bb97861eb3a2f3f9ead1e8718d1410882613f84e088bb31338c343149fa"
REVISION = "550b6625bcef1f2abff2ff770a5a0d272c9c6b2a"
PACKAGES = (
    {"name": "punkt", "subdir": "tokenizers", "bytes": 13905355, "expanded_max": 37245719,
     "sha256": "51c3078994aeaf650bfc8e028be4fb42b4a0d177d41c012b6a983979653660ec",
     "required_member": "punkt/PY3/english.pickle"},
    {"name": "stopwords", "subdir": "corpora", "bytes": 37733, "expanded_max": 89446,
     "sha256": "48c0e52d8b52546e827f53761fb30300c0ab94f70660d28bd65ba0a86270946b",
     "required_member": "stopwords/english"},
)
DOCKERFILE = Path(__file__).parent / "runtime" / "Dockerfile.nltk-data"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _identity():
    return {"module_sha256": _sha(Path(__file__).read_bytes()), "dockerfile_sha256": _sha(DOCKERFILE.read_bytes())}


def _url(spec):
    return f"https://raw.githubusercontent.com/nltk/nltk_data/{REVISION}/packages/{spec['subdir']}/{spec['name']}.zip"


def _fetch(spec):
    # proxy_on must be active in this same Linux shell; never print proxy values.
    with httpx.Client(timeout=60, trust_env=True, follow_redirects=False) as client:
        with client.stream("GET", _url(spec)) as response:
            require(response.status_code == 200 and str(response.url) == _url(spec), "Unexpected resource response")
            chunks, length = [], 0
            for chunk in response.iter_bytes():
                length += len(chunk)
                require(length <= spec["bytes"], "Resource exceeds pinned size")
                chunks.append(chunk)
    return b"".join(chunks)


def _members(payload, spec):
    require(len(payload) == spec["bytes"] and _sha(payload) == spec["sha256"], "Resource size/SHA256 mismatch")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
        require(0 < len(infos) <= 1024, "Archive member count exceeds limit")
        seen, total, files = set(), 0, {}
        for item in infos:
            name = item.filename
            path = PurePosixPath(name)
            require(name not in seen and "\\" not in name and ":" not in name and "\x00" not in name
                    and not path.is_absolute() and ".." not in path.parts
                    and name.rstrip("/") == str(path) and path.parts[0] == spec["name"], "Unsafe archive path")
            seen.add(name)
            mode = stat.S_IFMT(item.external_attr >> 16)
            require(mode in (0, stat.S_IFREG, stat.S_IFDIR) and not item.flag_bits & 1, "Link/special/encrypted archive member")
            require((mode != stat.S_IFDIR or item.is_dir()) and (mode != stat.S_IFREG or not item.is_dir()),
                    "Archive type/path disagreement")
            total += item.file_size
            require(total <= spec["expanded_max"], "Archive expansion exceeds pinned bound")
            if not item.is_dir():
                value = archive.read(item)  # ZIP decompression/CRC only, never deserialize pickle.
                require(len(value) == item.file_size, "Archive member size mismatch")
                files[name] = value
        require(spec["required_member"] in files, "Required native resource missing")
        return files


def _files(directory):
    directory = safe_path(directory)
    result = {}
    for path in directory.rglob("*"):
        require(not path.is_symlink(), "Symlink in private build context")
        require(path.is_file() or path.is_dir(), "Special file in private build context")
        require(path.stat().st_mode & 0o777 == (0o644 if path.is_file() else 0o755),
                "Build context data permissions changed")
        if path.is_file():
            result[str(path.relative_to(directory))] = _sha(path.read_bytes())
    return result


def prepare(output):
    root = safe_path(output)
    require(not root.exists(), "Use a new private overlay directory")
    root.mkdir(parents=True, mode=0o700)
    context = root / "context"
    context.mkdir(mode=0o700)
    (root / "archives").mkdir(mode=0o700)
    try:
        packages = []
        for spec in PACKAGES:
            payload = _fetch(spec)
            files = _members(payload, spec)
            (root / "archives" / (spec["name"] + ".zip")).write_bytes(payload)
            for name, value in files.items():
                target = context / "nltk_data" / spec["subdir"] / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                target.write_bytes(value)
                target.chmod(0o644)
            packages.append({**spec, "url": _url(spec), "members": len(files), "expanded_bytes": sum(map(len, files.values()))})
        (context / "Dockerfile").write_bytes(DOCKERFILE.read_bytes())
        (context / "Dockerfile").chmod(0o644)
        for directory in (context / "nltk_data", *(context / "nltk_data").rglob("*")):
            if directory.is_dir():
                directory.chmod(0o755)  # Docker runtime UID65534 must read data even under host umask077.
        value = seal({"version": VERSION, "base_image": BASE_IMAGE, "revision": REVISION,
                      "source": _identity(), "builder": BUILDER, "packages": packages, "context_files": _files(context),
                      "model_calls": 0, "host_deserialization": False, "packages_upgraded": False,
                      "baseline_scores_replaced": False, "image_built": False})
        write_json(root / "manifest.json", value)
        return {"status": "prepared_not_built", "manifest_hash": value["record_hash"], "model_calls": 0}
    except Exception as exc:
        write_json(root / "prepare-failure.json", seal({"version": VERSION, "status": "failed",
                   "error_type": type(exc).__name__, "model_calls": 0, "source": _identity()}))
        raise


def check(output):
    root = safe_path(output)
    value = read_json(root / "manifest.json", sealed=True)
    require(value["version"] == VERSION and value["base_image"] == BASE_IMAGE and value["revision"] == REVISION
            and value["source"] == _identity() and value["builder"] == BUILDER, "Overlay identity changed")
    require(value["context_files"] == _files(root / "context") and
            (root / "context/Dockerfile").read_bytes() == DOCKERFILE.read_bytes(), "Build context changed")
    packages = []
    expected = {"Dockerfile": _sha(DOCKERFILE.read_bytes())}
    for spec in PACKAGES:
        files = _members(safe_path(root / "archives" / (spec["name"] + ".zip")).read_bytes(), spec)
        packages.append({**spec, "url": _url(spec), "members": len(files), "expanded_bytes": sum(map(len, files.values()))})
        expected.update({f"nltk_data/{spec['subdir']}/{name}": _sha(payload) for name, payload in files.items()})
    require(value["packages"] == packages, "Resource manifest changed")
    require(value["context_files"] == expected, "Context differs from verified official archive contents")
    return value


def _image(image_id):
    return json.loads(subprocess.check_output(["docker", "image", "inspect", image_id], stderr=subprocess.DEVNULL))[0]


def build(output):
    root = safe_path(output)
    with output_lock(root):
        manifest = check(root)
        require(not (root / "build-intent.json").exists(), "Build already attempted; preserve it, do not retry silently")
        base = _image(BASE_IMAGE)
        require(base["Id"] == BASE_IMAGE, "Original local base image unavailable")
        write_json(root / "build-intent.json", seal({"manifest_hash": manifest["record_hash"],
                   "base_image": BASE_IMAGE, "base_layers": base["RootFS"]["Layers"], "builder": BUILDER, "model_calls": 0}))
        started = time.monotonic()
        try:
            with (root / "build.log").open("xb") as log:
                subprocess.run(["docker", "build", "--pull=false", "--network=none", "--iidfile",
                                str(root / "image.id"), str(root / "context")], stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=600, env={**os.environ, **BUILDER["child_environment"]})
            image_id = (root / "image.id").read_text().strip()
            require(image_id.startswith("sha256:") and len(image_id) == 71 and image_id != BASE_IMAGE,
                    "New immutable image identity required")
            built = _image(image_id)
            layers = base["RootFS"]["Layers"]
            require(built["Id"] == image_id and built["RootFS"]["Layers"][:-1] == layers,
                    "Built image is not exactly one layer on the frozen base")
            keys = ("Env", "Entrypoint", "Cmd", "User", "WorkingDir", "Shell", "Healthcheck")
            require(all(built["Config"].get(k) == base["Config"].get(k) for k in keys), "Base execution configuration changed")
            require(check(root) == manifest, "Build inputs changed during build")
            result = {"status": "built_not_qualified", "image_id": image_id,
                      "layers": built["RootFS"]["Layers"], "base_configuration_preserved": True}
        except Exception as exc:
            result = {"status": "build_failed_or_unverified", "error_type": type(exc).__name__}
        result = seal({"version": VERSION, "manifest_hash": manifest["record_hash"], "base_image": BASE_IMAGE,
                       "builder": BUILDER, "base_created": base.get("Created"),
                       "model_calls": 0, "wall_seconds": round(time.monotonic() - started, 6),
                       "qualification_performed": False, "baseline_scores_replaced": False, **result})
        write_json(root / "build-receipt.json", result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "check", "build"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    value = globals()[args.command](args.output)
    if args.command == "check":
        value = {"status": "validated_not_built", "manifest_hash": value["record_hash"], "model_calls": 0}
    print(json.dumps({k: value[k] for k in ("status", "manifest_hash", "image_id", "model_calls", "error_type") if k in value}))


if __name__ == "__main__":
    main()
