"""Download the Qwen publisher mirror, pinning and verifying each file revision.

The file URL format follows ModelScope's official get_file_download_url implementation.
No remote Python code is executed. The snapshot ID is a manifest hash, not a HF commit.
"""

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from decisionbench.artifacts import file_hash, write_json


def download(out):
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "download-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        url = "https://modelscope.cn/api/v1/models/Qwen/Qwen3-0.6B/repo/files?Revision=master&Recursive=true"
        with urllib.request.urlopen(url, timeout=30) as response:
            listing = json.load(response)
        files = [
            {key: f[key] for key in ("Path", "Revision", "Sha256", "Size")}
            for f in listing["Data"]["Files"]
            if f["Type"] == "blob"
        ]
        for entry in files:
            if Path(entry["Path"]).name != entry["Path"] or entry["Path"].endswith(".py"):
                raise ValueError("unexpected model repository file")
        snapshot = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        manifest = {
            "publisher": "Qwen",
            "model": "Qwen3-0.6B",
            "source": url,
            "snapshot_id": "modelscope-manifest-sha256:" + snapshot,
            "files": files,
            "verified": False,
        }
        write_json(manifest_path, manifest)

    def fetch(entry):
        path = out / entry["Path"]
        if path.is_file() and file_hash(path) == entry["Sha256"]:
            return
        params = urllib.parse.urlencode({"Revision": entry["Revision"], "FilePath": entry["Path"]})
        url = "https://modelscope.cn/api/v1/models/Qwen/Qwen3-0.6B/repo?" + params
        temporary = path.with_name(path.name + ".partial")
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
        if temporary.stat().st_size != entry["Size"] or file_hash(temporary) != entry["Sha256"]:
            raise ValueError(f"publisher hash or size mismatch: {entry['Path']}")
        temporary.replace(path)
        print(f"Verified {entry['Path']}: {entry['Size']} bytes", flush=True)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(fetch, manifest["files"]))
    manifest["verified"] = True
    write_json(manifest_path, manifest)
    print(manifest["snapshot_id"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    download(args.out.resolve())


if __name__ == "__main__":
    main()
