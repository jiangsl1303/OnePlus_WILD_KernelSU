#!/usr/bin/env python3
"""按「能不能干净打上」挑 SUSFS 提交（解决 OnePlus 树 sublevel 落后 GKI 的老毛病）。

背景：simonpunk/susfs4ksu 的 `gki-android*-*` 分支是跟着 **最新 GKI sublevel** rebase 的
（例：6.12 分支 2026-10-18 被 rebase 到 6.12.92），而一加/厂商树常年落后
（例：OnePlus 6.12.38）。直接拿分支 tip 的内核补丁去 `patch` 会成片 `.rej`
（实测 `fs/proc/task_mmu.c` 8 个 hunk 挂 3 个）。

做法：从新到旧遍历候选提交，对每个候选下载该提交的归档，用 `patch --dry-run --forward`
在内核树上试打 `50_add_susfs_in_<branch>.patch`，**第一个零 reject 的就是赢家**。
不改动树（--dry-run 只读），选中的归档目录留给调用方替换 `$SUSFS_FOLDER`。

用法（供 action 调用）：
  python3 susfs_pick_commit.py --branch gki-android16-6.12 --tree /path/to/common \
      --dest /path/to/susfs4ksu --max-tries 8 --json-out /tmp/pick.json

输出（stdout 末行）：PICKED <sha> <dir> <version>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = "simonpunk%2Fsusfs4ksu"
ARCHIVE = "https://gitlab.com/api/v4/projects/{proj}/repository/archive.tar.gz?sha={sha}"
COMMITS = (
    "https://gitlab.com/api/v4/projects/{proj}/repository/commits"
    "?ref_name={branch}&path=kernel_patches&per_page=100&page={page}"
)


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch_json(url: str, retries: int = 3) -> list:
    last = ""
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last = str(exc)
            if attempt < retries:
                continue
    raise RuntimeError(f"fetch failed {url}: {last}")


def download_archive(sha: str, out_dir: Path, retries: int = 3) -> Path | None:
    url = ARCHIVE.format(proj=PROJECT, sha=sha)
    tarball = out_dir / f"{sha}.tar.gz"
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=180) as resp, open(tarball, "wb") as fh:
                shutil.copyfileobj(resp, fh)
            extract_dir = out_dir / sha
            with tarfile.open(tarball, "r:gz") as tar:
                members = tar.getmembers()
                if not members:
                    raise RuntimeError("empty archive")
                root = members[0].name.split("/")[0]
                for member in members:
                    parts = member.name.split("/", 1)
                    if len(parts) == 1:
                        continue
                    member.name = parts[1]
                    tar.extract(member, extract_dir, filter="data")
            tarball.unlink(missing_ok=True)
            return extract_dir
        except Exception as exc:  # noqa: BLE001 - 网络/解包都可能失败
            log(f"    [warn] archive {sha[:9]} attempt {attempt}/{retries}: {exc}")
            tarball.unlink(missing_ok=True)
    return None


def parse_ver(text: str) -> tuple[int, ...]:
    m = re.search(r"v?(\d+(?:\.\d+)*)", text or "")
    if not m:
        return (0,)
    return tuple(int(x) for x in m.group(1).split("."))


def read_version(extract_dir: Path) -> str:
    hdr = extract_dir / "kernel_patches" / "include" / "linux" / "susfs.h"
    if not hdr.exists():
        return ""
    m = re.search(r'#define\s+SUSFS_VERSION\s+"([^"]+)"', hdr.read_text(errors="replace"))
    return m.group(1) if m else ""


def patch_file_for(extract_dir: Path, branch: str) -> Path | None:
    exact = extract_dir / "kernel_patches" / f"50_add_susfs_in_{branch}.patch"
    if exact.exists():
        return exact
    # 老提交可能用别名分支名
    cands = sorted((extract_dir / "kernel_patches").glob("50_add_susfs_in_*.patch"))
    return cands[0] if len(cands) == 1 else None


def try_patch(tree: Path, patch: Path) -> bool:
    proc = subprocess.run(
        ["patch", "-p1", "--forward", "--dry-run", "-i", str(patch)],
        cwd=tree,
        capture_output=True,
        text=True,
    )
    rejects = re.findall(r"(\S+)\.rej", proc.stdout + proc.stderr)
    if proc.returncode == 0 and not rejects:
        return True
    if rejects:
        log(f"    [x] {len(set(rejects))} reject(s): {', '.join(sorted(set(rejects))[:4])}")
    return False


def build_ladder(commits: list[dict], max_tries: int) -> list[dict]:
    """拼候选顺序：tip → rebase/offset 类「时代边界」提交 → 剩余名额按全区间等距取样。

    顺序即优先级：越靠前越新，越可能带上最新修复；一旦某个候选零 reject 就停。
    """
    picked: list[dict] = []
    seen: set[str] = set()

    def add(c: dict) -> None:
        if c["id"] not in seen:
            seen.add(c["id"])
            picked.append(c)

    if commits:
        add(commits[0])

    marker = re.compile(r"rebase|offset|older gki|patch offset|bump version", re.I)
    for c in commits:
        if len(picked) >= max_tries - 4:
            break
        if marker.search(c["title"]):
            add(c)

    # 等距补齐：把整段历史摊开，避免只在最近几个月里打转
    remaining = max_tries - len(picked)
    if remaining > 0 and len(commits) > 2:
        step = max(1, len(commits) // remaining)
        for i in range(len(commits) - 1, 0, -step):
            if len(picked) >= max_tries:
                break
            add(commits[i])

    return picked[:max_tries]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", required=True, help="如 gki-android16-6.12")
    ap.add_argument("--tree", required=True, help="内核树目录（common/）")
    ap.add_argument("--dest", required=True, help="选中的归档要放到哪（= $SUSFS_FOLDER）")
    ap.add_argument("--max-tries", type=int, default=8)
    ap.add_argument("--json-out", default="")
    ap.add_argument("--list-only", action="store_true", help="只打印候选阶梯，不下载")
    ap.add_argument("--min-version", default="v2.2.0",
                    help="SUSFS 版本下限；低于它的老提交会启用 NEED_HOOKS 等另一套代码路径，必须排除")
    args = ap.parse_args()

    tree = Path(args.tree)
    dest = Path(args.dest)
    if not tree.is_dir():
        raise SystemExit(f"[!] 内核树不存在: {tree}")

    commits: list[dict] = []
    for page in (1, 2, 3):
        batch = fetch_json(COMMITS.format(proj=PROJECT, branch=args.branch, page=page))
        if not batch:
            break
        commits += batch
        if len(batch) < 100:
            break
    log(f"[*] {args.branch} 候选提交 {len(commits)} 个"
        f"（{commits[-1]['committed_date'][:10]} → {commits[0]['committed_date'][:10]}）"
        if commits else f"[!] {args.branch} 没有候选提交")

    ladder = build_ladder(commits, args.max_tries)
    if args.list_only:
        for i, c in enumerate(ladder, 1):
            print(f"{i:2} {c['id']} {c['committed_date'][:10]} {c['title'][:70]}")
        return 0

    work = Path(tempfile.mkdtemp(prefix="susfs-pick-"))
    try:
        for idx, cand in enumerate(ladder, 1):
            sha = cand["id"]
            log(f"[{idx}] {sha[:9]} {cand['committed_date'][:10]} {cand['title'][:60]}")
            extract = download_archive(sha, work)
            if not extract:
                continue
            ver = read_version(extract)
            if parse_ver(ver) < parse_ver(args.min_version):
                log(f"    [x] 版本 {ver or '?'} < 下限 {args.min_version}（老版本会走 NEED_HOOKS 另一套路径），跳过")
                shutil.rmtree(extract, ignore_errors=True)
                continue
            pf = patch_file_for(extract, args.branch)
            if not pf:
                log("    [x] 该提交里没有匹配的内核补丁")
                shutil.rmtree(extract, ignore_errors=True)
                continue
            if try_patch(tree, pf):
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True)
                shutil.move(str(extract), str(dest))
                log(f"[+] 选中 {sha} （SUSFS {ver or '?'}）—— 零 reject")
                if args.json_out:
                    Path(args.json_out).write_text(
                        json.dumps({"sha": sha, "version": ver, "dir": str(dest),
                                    "date": cand["committed_date"], "title": cand["title"]},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"PICKED {sha} {dest} {ver}")
                return 0
            shutil.rmtree(extract, ignore_errors=True)
        log("[!] 所有候选都打不上——请人工确认（可能要改 patch 而不是换提交）")
        return 2
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
