#!/usr/bin/env python3
"""
upload_pending.py — Download generated reels from GitHub Actions artifacts and upload to Instagram.

Usage:
    python upload_pending.py

Run this locally whenever you want to push pending reels to Instagram.
"""
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

_DIR = Path(__file__).parent.resolve()

# Load .env
_env = _DIR / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from uploader import upload_reel


def _gh(*args) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return r.stdout.strip()


def main():
    print("Fetching recent workflow runs...")
    runs_json = _gh("run", "list", "--workflow=pipeline.yml",
                    "--status=success", "--limit=10", "--json",
                    "databaseId,displayTitle,createdAt,headBranch")
    runs = json.loads(runs_json)

    if not runs:
        print("No successful runs found.")
        return

    uploaded = 0
    for run in runs:
        run_id = run["databaseId"]
        created = run["createdAt"]

        # Check if this run has a reel artifact
        try:
            artifacts_json = _gh("api", f"repos/:owner/:repo/actions/runs/{run_id}/artifacts")
            artifacts = json.loads(artifacts_json).get("artifacts", [])
        except subprocess.CalledProcessError:
            continue

        reel_artifacts = [a for a in artifacts if a["name"].startswith("reel-")]
        if not reel_artifacts:
            continue

        for artifact in reel_artifacts:
            artifact_id = artifact["id"]
            artifact_name = artifact["name"]

            print(f"\nRun {run_id} ({created}) — artifact: {artifact_name}")

            with tempfile.TemporaryDirectory() as tmp:
                zip_path = Path(tmp) / "reel.zip"

                # Download artifact
                print("  Downloading...")
                subprocess.run(
                    ["gh", "api", f"repos/:owner/:repo/actions/artifacts/{artifact_id}/zip",
                     "--output", str(zip_path)],
                    check=True, capture_output=True
                )

                # Extract
                extract_dir = Path(tmp) / "extracted"
                extract_dir.mkdir()
                with zipfile.ZipFile(zip_path) as z:
                    z.extractall(extract_dir)

                mp4_files = list(extract_dir.glob("*.mp4"))
                if not mp4_files:
                    print("  No MP4 found in artifact — skipping.")
                    continue

                mp4 = mp4_files[0]
                jpg = mp4.with_suffix(".jpg")

                # Build caption from filename (slug → philosopher name)
                slug = mp4.stem.rsplit("-", 1)[0]  # remove timestamp
                philosopher = slug.replace("-", " ").title()
                caption = (
                    f'"{philosopher}"\n\n'
                    f"#philosophy #quotes #wisdom #deepthoughts #philosophyquotes "
                    f"#mindset #existentialism #stoicism #motivation"
                )

                print(f"  Uploading {mp4.name}...")
                try:
                    upload_reel(str(mp4), caption, str(jpg) if jpg.exists() else None)
                    print(f"  ✓ Uploaded!")
                    uploaded += 1

                    # Delete artifact so we don't re-upload it
                    subprocess.run(
                        ["gh", "api", "--method=DELETE",
                         f"repos/:owner/:repo/actions/artifacts/{artifact_id}"],
                        check=True, capture_output=True
                    )
                    print(f"  Artifact deleted.")
                except Exception as e:
                    print(f"  ✗ Upload failed: {e}")

    print(f"\nDone. {uploaded} reel(s) uploaded.")


if __name__ == "__main__":
    main()
