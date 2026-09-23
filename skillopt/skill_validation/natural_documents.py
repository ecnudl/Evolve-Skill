"""Fetch allowlisted documentation on Linux; preserve the existing safety checks.

Local Clash fake-IP DNS is deliberately NOT exempted from public-address checks.
Only trusted host code runs over SSH, never model-supplied scripts. The remote
proxy is activated in this shell only. Raw snapshots are copied and hash checked.
"""
import base64
import hashlib
import json
import shlex
import subprocess

from skillopt.validator_pilot import research as legacy
from skillopt.validator_pilot.api import digest, write_immutable_json

from .models import require
from .natural_policy import approved, fetch_sources
from .panel import checked_path


REMOTE_SCRIPT = r'''
import base64, hashlib, json, sys, tempfile
from pathlib import Path
import httpx
from skillopt.validator_pilot import research as legacy
from skillopt.skill_validation.natural_policy import approved
urls = json.loads(sys.stdin.read(10000))
assert type(urls) is list and len(urls) <= 3 and len(set(urls)) == len(urls)
for url in urls:
    approved(url)
class Restricted:
    def __init__(self, client): self.client = client
    def stream(self, method, url):
        assert method == "GET"
        return self.client.stream(method, approved(url))
with tempfile.TemporaryDirectory(prefix="skillval-documents-") as directory:
    root = Path(directory)
    with httpx.Client(trust_env=True, follow_redirects=False, timeout=httpx.Timeout(20, connect=10)) as client:
        records = [legacy._fetch_one(url, root, Restricted(client)) for url in urls]
    snapshots = []
    for record in records:
        item = {"record": record}
        if record["ok"]:
            raw = (root / "documents" / record["snapshot_id"] / "source.html").read_bytes()
            item["html_base64"] = base64.b64encode(raw).decode()
        snapshots.append(item)
    print(json.dumps({"snapshots": snapshots,
        "fetch_module_sha256": hashlib.sha256(Path(legacy.__file__).read_bytes()).hexdigest()}))
'''


class SSHDocumentFetcher:
    def __init__(self, remote_repo):
        require(type(remote_repo) is str and remote_repo.startswith("/"), "Absolute remote repository required")
        self.remote_repo = remote_repo
        self.identity = {"version": "ssh-official-documents-v1", "host": "PJ-CL4MIND-DULIN",
                         "remote_repo": remote_repo, "proxy_on": True, "public_dns_check": True,
                         "script_hash": hashlib.sha256(REMOTE_SCRIPT.encode()).hexdigest()}

    def __call__(self, urls, root):
        require(type(urls) is list and len(urls) <= 3 and len(set(urls)) == len(urls), "Bounded unique URLs required")
        for url in urls:
            approved(url)
        root = checked_path(root)
        protocol = {"transport": self.identity, "urls": urls}
        write_immutable_json(root / "transport.json", protocol)
        receipt = root / "remote_snapshots.json"
        if receipt.exists():
            result = json.loads(receipt.read_text())
        else:
            shell = "proxy_on >/dev/null && cd " + shlex.quote(self.remote_repo)
            shell += " && /root/miniconda3/envs/skill_validation/bin/python -c " + shlex.quote(REMOTE_SCRIPT)
            try:
                process = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                    self.identity["host"], "bash -ic " + shlex.quote(shell)], input=json.dumps(urls),
                    text=True, capture_output=True, timeout=200, check=False)
                require(process.returncode == 0 and len(process.stdout) <= 10000000,
                        "Remote document transport failed or exceeded output limit")
                result = json.loads(process.stdout)
            except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
                raise ValueError("Remote document transport unavailable") from None
        require(type(result) is dict and type(result.get("snapshots")) is list
                and len(result["snapshots"]) == len(urls), "Incomplete remote document response")
        # Validate every record before persisting any snapshot or trusting it as research evidence.
        validated = []
        for item, url in zip(result["snapshots"], urls):
            record = item["record"]
            identifier = digest({"url": url, "protocol": "bounded-research-v1"})
            require(record["requested_url"] == url and record["snapshot_id"] == identifier, "Document identity mismatch")
            for attempt in record.get("attempts", []):
                approved(attempt["url"])
            raw = None
            if record["ok"]:
                approved(record["final_url"])
                raw = base64.b64decode(item["html_base64"], validate=True)
                require(len(raw) <= legacy.MAX_HTML_BYTES
                        and hashlib.sha256(raw).hexdigest() == record["raw_html_sha256"]
                        and hashlib.sha256(record["text"].encode()).hexdigest() == record["text_sha256"],
                        "Remote document hash mismatch")
            validated.append((identifier, record, raw))
        write_immutable_json(receipt, result)
        for identifier, record, raw in validated:
            directory = root / "documents" / identifier
            if raw is not None:
                legacy._write_bytes(directory / "source.html", raw)
                legacy._write_bytes(directory / "excerpt.txt", record["text"].encode())
            write_immutable_json(directory / "source.json", record)
        # Existing parser rechecks request/redirect allowlists and the imported immutable hashes.
        return fetch_sources(urls, root)
