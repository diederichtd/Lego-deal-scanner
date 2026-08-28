"""Push the built site somewhere it gets a public URL.

Modes (config: site.deploy.mode):
  none    - do nothing (default)
  folder  - copy files into another local folder (e.g. a synced Dropbox / iCloud dir)
  rsync   - rsync -az --delete to user@host:/path/
  netlify - npx netlify deploy --prod --dir <outdir>
  git     - commit the outdir on its own branch and push (GitHub Pages etc.)
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def deploy(outdir: Path, site_cfg: dict) -> Optional[str]:
    d = site_cfg.get("deploy") or {}
    mode = (d.get("mode") or "none").lower()
    public = site_cfg.get("public_url") or ""
    if mode == "none":
        return None
    try:
        if mode == "folder":
            dest = Path(d["dest"]).expanduser()
            dest.mkdir(parents=True, exist_ok=True)
            for f in outdir.iterdir():
                if f.is_file():
                    shutil.copy2(f, dest / f.name)
            return public or str(dest)

        if mode == "rsync":
            subprocess.run(
                ["rsync", "-az", "--delete", f"{outdir}/", d["target"]],
                check=True, capture_output=True, text=True,
            )
            return public or d.get("target")

        if mode == "netlify":
            cmd = ["npx", "--yes", "netlify", "deploy", "--prod", "--dir", str(outdir)]
            if d.get("site_id"):
                cmd += ["--site", d["site_id"]]
            out = subprocess.run(cmd, check=True, capture_output=True, text=True)
            for line in out.stdout.splitlines():
                if "Website URL" in line or line.strip().startswith("https://"):
                    return line.split()[-1]
            return public or None

        if mode == "git":
            return _git_publish(outdir, d, public)
    except (subprocess.CalledProcessError, KeyError, OSError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        log.error("deploy (%s) failed: %s", mode, detail)
        return None

    log.warning("unknown deploy mode: %s", mode)
    return None


def _git(outdir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(outdir), *args],
        check=True, capture_output=True, text=True,
    )


def _git_publish(outdir: Path, d: dict, public: str) -> Optional[str]:
    branch = d.get("branch", "gh-pages")
    remote_url = d.get("remote_url")
    if not (outdir / ".git").exists():
        if not remote_url:
            log.error("git deploy: set site.deploy.remote_url on first run")
            return None
        _git(outdir, "init", "-q")
        _git(outdir, "checkout", "-q", "-B", branch)
        _git(outdir, "remote", "add", "origin", remote_url)
    _git(outdir, "add", "-A")
    # commit may be a no-op if nothing changed; tolerate that
    res = subprocess.run(
        ["git", "-C", str(outdir), "commit", "-q", "-m", "update deals"],
        capture_output=True, text=True,
    )
    if res.returncode != 0 and "nothing to commit" not in (res.stdout + res.stderr):
        log.error("git commit failed: %s", res.stderr or res.stdout)
        return None
    _git(outdir, "push", "-q", "-f", "origin", branch)
    return public or None
