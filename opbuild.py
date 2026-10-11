#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OnePlus KernelSU-Next 内核一键构建助手
=======================================

配合仓库里的 .github/workflows/build-oneplus-ksun.yml 使用，提供四件事：

    list      列出上游所有可构建的一加设备（含建议的关键字）
    build     一键触发云端构建（单个设备 / 多个 / 全部）
    status    查看最近的构建状态
    download  把构建好的 AnyKernel3 刷机包下载到本地

仅依赖 Python 标准库，Windows / macOS / Linux 通用。

------------------------------------------------------------
准备（只需做一次）
------------------------------------------------------------
1. Fork https://github.com/WildKernels/OnePlus_KernelSU_SUSFS
2. 把 build-oneplus-ksun.yml 放到 fork 仓库的 .github/workflows/ 目录
3. 生成一个 GitHub Token（Settings → Developer settings → Personal access
   tokens → Tokens (classic)），勾选 repo 和 workflow 权限
4. 设置环境变量：

   Windows (cmd)      set GITHUB_TOKEN=ghp_xxxxxxxx
                      set OP_REPO=你的用户名/OnePlus_KernelSU_SUSFS
   Windows (PowerShell)
                      $env:GITHUB_TOKEN="ghp_xxxxxxxx"
                      $env:OP_REPO="你的用户名/OnePlus_KernelSU_SUSFS"
   macOS / Linux      export GITHUB_TOKEN=ghp_xxxxxxxx
                      export OP_REPO=你的用户名/OnePlus_KernelSU_SUSFS

------------------------------------------------------------
用法示例
------------------------------------------------------------
    python opbuild.py list
    python opbuild.py list --filter 13
    python opbuild.py build --device OP13
    python opbuild.py build --device OP13 --android A15
    python opbuild.py build --device OP13,OP12 --release
    python opbuild.py build --device all --android A16
    python opbuild.py status
    python opbuild.py download
    python opbuild.py download --run-id 12345678 --out D:\\ak3
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------
UPSTREAM = "WildKernels/OnePlus_KernelSU_SUSFS"
UPSTREAM_TARBALL = (
    f"https://codeload.github.com/{UPSTREAM}/tar.gz/refs/heads/main"
)
WORKFLOW_FILE = "build-oneplus-ksun.yml"
API = "https://api.github.com"

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def die(msg: str, code: int = 1):
    print(f"[错误] {msg}", file=sys.stderr)
    sys.exit(code)


def request(url: str, token: str = "", method: str = "GET", body=None,
            raw: bool = False, retries: int = 3):
    """发一个 GitHub API 请求，返回解析后的 JSON 或原始 bytes。"""
    data = None
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "opbuild/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers,
                                         method=method)
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = resp.read()
                return payload if raw else json.loads(payload or b"{}")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            last_err = f"HTTP {e.code} {e.reason}  {detail}"
            if e.code in (401, 403, 404):
                break
            time.sleep(2 * attempt)
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            time.sleep(2 * attempt)
    raise RuntimeError(last_err or "未知网络错误")


def fetch_upstream_configs() -> list[dict]:
    """下载上游 tarball 并解析出全部设备配置。"""
    print(f"正在从上游 {UPSTREAM} 拉取最新设备配置 ...")
    req = urllib.request.Request(
        UPSTREAM_TARBALL, headers={"User-Agent": "opbuild/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        blob = resp.read()

    pat = re.compile(r"^[^/]+/configs/[^/]+/[^/]+\.json$")
    configs: list[dict] = []
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for member in tf.getmembers():
            if not pat.match(member.name):
                continue
            fh = tf.extractfile(member)
            if fh is None:
                continue
            try:
                cfg = json.loads(fh.read().decode("utf-8"))
                cfg["_file"] = member.name.split("/")[-1]
                configs.append(cfg)
            except Exception:
                continue
    print(f"共获取 {len(configs)} 条设备配置。\n")
    return configs


def match_configs(configs: list[dict], keyword: str) -> list[dict]:
    """与 workflow 内保持一致的四级匹配，方便本地预览。"""
    kw = keyword.strip().lower()
    if kw in ("", "all", "*"):
        return configs

    def norm(s: str) -> str:
        return re.sub(r"[._-]", "", s.lower())

    out: list[dict] = []
    for token in [t.strip() for t in kw.split(",") if t.strip()]:
        n = norm(token)
        # 1) 型号边界前缀
        hit = [c for c in configs
               if c["model"].lower() == token
               or c["model"].lower().startswith(token + "-")
               or c["model"].lower().startswith(token + "_")
               or c["model"].lower().startswith(token + ".")]
        # 2) manifest 边界前缀
        if not hit:
            hit = [c for c in configs
                   if c["manifest"].lower() == token
                   or c["manifest"].lower().startswith(token + "_")
                   or c["manifest"].lower().startswith(token + "-")]
        # 3) 归一化前缀
        if not hit:
            hit = [c for c in configs
                   if norm(c["model"]).startswith(n)
                   or norm(c["model"]).startswith("op" + n)]
        # 4) 归一化包含
        if not hit:
            hit = [c for c in configs
                   if n in norm(c["model"]) or n in norm(c["manifest"])]
        out.extend(hit)

    seen, uniq = set(), []
    for c in out:
        key = (c["model"], c["os_version"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    return uniq


# --------------------------------------------------------------------------
# 子命令
# --------------------------------------------------------------------------
def cmd_list(args):
    configs = fetch_upstream_configs()

    if args.filter:
        configs = match_configs(configs, args.filter)
        if not configs:
            die(f"关键字 '{args.filter}' 没有匹配到任何设备。")

    groups: dict[str, list[dict]] = {}
    for c in configs:
        groups.setdefault(c["os_version"], []).append(c)

    print(f"{'型号 (model)':<26}{'OS':<6}{'内核':<20}{'SoC':<18}{'分支'}")
    print("-" * 100)
    for os_ver in sorted(groups, reverse=True):
        for c in sorted(groups[os_ver], key=lambda x: x["model"]):
            print(f"{c['model']:<26}{c['os_version']:<6}"
                  f"{c['android_version'] + '-' + c['kernel_version']:<20}"
                  f"{str(c.get('soc', '')):<18}{c.get('branch', '')}")
    print("-" * 100)
    print(f"合计 {len(configs)} 条配置。")
    print("\n把这些 '型号' 直接填进 workflow 的 device 输入框即可。")
    print("也可以填系列关键字，例如：OP13 / 13 / ace5 / pad3 / all")


def _need_repo_token(args) -> tuple[str, str]:
    repo = (args.repo or env("OP_REPO")).strip()
    token = (args.token or env("GITHUB_TOKEN")).strip()
    if not repo:
        die("未指定仓库。请设置环境变量 OP_REPO，或加 --repo 你的用户名/仓库名")
    if "/" not in repo:
        die(f"仓库格式应为 owner/repo，当前为 '{repo}'")
    if not token:
        die("未提供 GitHub Token。请设置环境变量 GITHUB_TOKEN，或加 --token")
    return repo, token


def cmd_build(args):
    repo, token = _need_repo_token(args)

    # 触发前先本地预览将要构建哪些设备，避免误操作
    if not args.yes:
        try:
            configs = fetch_upstream_configs()
            if args.android != "auto":
                configs = [c for c in configs if c["os_version"] == args.android]
            matched = match_configs(configs, args.device)
            if not matched:
                die(f"关键字 '{args.device}' 没有匹配到任何设备，已取消。")
            print(f"即将构建 {len(matched)} 个配置：")
            for c in matched[:40]:
                print(f"  - {c['model']:<26}[{c['os_version']}] "
                      f"{c['android_version']}-{c['kernel_version']}")
            if len(matched) > 40:
                print(f"  ... 其余 {len(matched) - 40} 个略")
            print()
            if len(matched) > 12 and not args.release:
                print("提示：设备较多，构建耗时较长且会消耗 Actions 额度。")
                print("      可用 --android A15/A16 缩小范围，或 --list-only 先预览。\n")
            answer = input("确认触发云端构建？(y/N) ").strip().lower()
            if answer not in ("y", "yes"):
                print("已取消。")
                return
        except KeyboardInterrupt:
            print("\n已取消。")
            return
        except Exception as e:  # noqa: BLE001
            print(f"[警告] 预览失败（{e}），继续直接触发。")

    inputs = {
        "device": args.device,
        "android_version": args.android,
        "susfs_mode": args.susfs_mode,
        "fetch_manager": "true" if args.fetch_manager else "false",
        "ksu_ref": args.ksu_ref,
        "susfs_ref": args.susfs_ref,
        "optimize_level": args.optimize,
        "clean_build": "true" if args.clean else "false",
        "make_release": "true" if args.release else "false",
        "list_only": "true" if args.list_only else "false",
        "debug": "true" if args.debug else "false",
    }

    url = f"{API}/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    print(f"正在触发 {repo} 的 {WORKFLOW_FILE} ...")
    try:
        request(url, token, method="POST",
                body={"ref": args.ref_branch, "inputs": inputs})
    except RuntimeError as e:
        msg = str(e)
        if "404" in msg:
            die("触发失败（404）。请检查：\n"
                "  1) 仓库名是否正确\n"
                "  2) fork 仓库里是否存在 "
                f".github/workflows/{WORKFLOW_FILE}\n"
                "  3) Token 是否有 workflow 权限")
        die(f"触发失败：{msg}")

    print("[成功] 构建已触发！")
    print(f"查看进度：https://github.com/{repo}/actions")
    print(f"或用：python {os.path.basename(sys.argv[0])} status")
    print(f"完成后下载：python {os.path.basename(sys.argv[0])} download")


def cmd_status(args):
    repo, token = _need_repo_token(args)
    url = (f"{API}/repos/{repo}/actions/runs"
           f"?per_page={args.limit}&event=workflow_dispatch")
    runs = request(url, token).get("workflow_runs", [])
    if not runs:
        print("没有找到手动触发的构建记录。")
        return

    print(f"{'Run ID':<14}{'状态':<16}{'结论':<14}{'开始时间':<22}{'标题'}")
    print("-" * 110)
    for r in runs:
        print(f"{r['id']:<14}{r['status']:<16}"
              f"{str(r.get('conclusion') or '-'):<14}"
              f"{r.get('created_at', ''):<22}{r.get('display_title', '')}")
    print("-" * 110)
    print("下载最新一次构建产物：python "
          f"{os.path.basename(sys.argv[0])} download")


def cmd_download(args):
    repo, token = _need_repo_token(args)
    out_dir = args.out or os.path.join(os.getcwd(), "ak3")
    os.makedirs(out_dir, exist_ok=True)

    run_id = args.run_id
    if not run_id:
        runs = request(
            f"{API}/repos/{repo}/actions/runs"
            f"?per_page=10&event=workflow_dispatch", token).get("workflow_runs", [])
        done = [r for r in runs if r.get("conclusion") == "success"]
        if not done:
            die("没有成功的构建记录。可先运行 status 查看。")
        run_id = done[0]["id"]
        print(f"使用最近一次成功构建：Run {run_id}")

    arts = request(
        f"{API}/repos/{repo}/actions/runs/{run_id}/artifacts", token)
    items = arts.get("artifacts", [])
    if not items:
        die(f"Run {run_id} 没有可下载的产物。")

    print(f"找到 {len(items)} 个产物，开始下载到 {out_dir}\n")
    saved = 0
    for a in items:
        name = a["name"]
        url = a["archive_download_url"]
        print(f"  ↓ {name}")
        try:
            blob = request(url, token, raw=True)
        except RuntimeError as e:
            print(f"    [失败] {e}")
            continue

        target = os.path.join(out_dir, name)
        if not target.lower().endswith(".zip"):
            target += ".zip"

        try:
            # artifact 下载接口返回的是 zip 包，里面装着真正的 AK3 zip
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                inner = [n for n in zf.namelist() if n.lower().endswith(".zip")]
                if inner:
                    for n in inner:
                        dest = os.path.join(out_dir, os.path.basename(n))
                        with open(dest, "wb") as f:
                            f.write(zf.read(n))
                        size = os.path.getsize(dest) / 1024 / 1024
                        print(f"    [完成] {os.path.basename(dest)}  ({size:.1f} MB)")
                        saved += 1
                else:
                    with open(target, "wb") as f:
                        f.write(blob)
                    print(f"    [完成] {os.path.basename(target)}")
                    saved += 1
        except zipfile.BadZipFile:
            with open(target, "wb") as f:
                f.write(blob)
            print(f"    [完成] {os.path.basename(target)}")
            saved += 1

    print(f"\n共保存 {saved} 个文件到：{out_dir}")
    if saved:
        print("刷机方式：KernelSU Manager 里直接选择该 zip 安装，或用 TWRP 刷入。")


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        prog="opbuild",
        description="OnePlus KernelSU-Next 内核一键构建助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="列出上游所有可构建设备")
    p_list.add_argument("--filter", "-f", default="",
                        help="只看匹配该关键字的设备，如 13 / ace5 / pad3")
    p_list.set_defaults(func=cmd_list)

    p_build = sub.add_parser("build", help="触发云端构建")
    p_build.add_argument("--device", "-d", required=True,
                         help="设备关键字：all / OP13 / OP13,OP12 / 13 / ace5")
    p_build.add_argument("--android", "-a", default="auto",
                         choices=["auto", "A14", "A15", "A16"],
                         help="Android 大版本过滤，默认 auto")
    p_build.add_argument("--susfs-mode", default="lkm",
                         choices=["source", "lkm", "patched", "none"],
                         help="SUSFS 方案：lkm(默认)=最新内核 + SUSFS v2.3.0 可加载模块；"
                              "source=pershoot dev-susfs + SUSFS v2.3.0 源码内置（WildKernels 同款，"
                              "auto 时自动取 pershoot fork 分支头，无需显式指定配对）；"
                              "patched=钉定 KSUN 33239 + SUSFS v2.2.0；"
                              "none=不带 SUSFS")
    p_build.add_argument("--ksu-ref", default="auto",
                         help="KernelSU-Next 分支或 commit。auto(默认)=按 susfs_mode 自动："
                              "lkm/none → dev（最新）；source → pershoot 的 dev-susfs；"
                              "patched → 234f6e04（KSUN 33239）")
    p_build.add_argument("--susfs-ref", default="auto",
                         help="SUSFS 源码引用：source 模式 auto=pershoot/susfs4ksu 的 "
                              "gki-<版本>-dev 分支头（实测 v2.3.0）；"
                              "patched 模式 auto=钉到 v2.2.0 末次提交；latest=跟随分支头；"
                              "也可填 commit/分支名")
    p_build.add_argument("--fetch-manager", action="store_true", default=True,
                         help="顺带抓取版本号最接近的官方 KernelSU-Next 管理器 APK（普通版+spoof 版），默认开")
    p_build.add_argument("--no-manager", dest="fetch_manager", action="store_false",
                         help="不抓取管理器 APK")
    p_build.add_argument("--optimize", default="O2", choices=["O2", "O3"])
    p_build.add_argument("--clean", action="store_true",
                         help="禁用 ccache 缓存")
    p_build.add_argument("--release", action="store_true",
                         help="构建成功后创建 Release")
    p_build.add_argument("--list-only", action="store_true",
                         help="只列出匹配设备，不构建")
    p_build.add_argument("--debug", action="store_true")
    p_build.add_argument("--ref-branch", default="main",
                         help="workflow 所在分支，默认 main")
    p_build.add_argument("--repo", default="", help="你的 fork：owner/repo")
    p_build.add_argument("--token", default="", help="GitHub Token")
    p_build.add_argument("--yes", "-y", action="store_true",
                         help="跳过确认直接触发")
    p_build.set_defaults(func=cmd_build)

    p_status = sub.add_parser("status", help="查看最近的构建状态")
    p_status.add_argument("--limit", type=int, default=5)
    p_status.add_argument("--repo", default="")
    p_status.add_argument("--token", default="")
    p_status.set_defaults(func=cmd_status)

    p_dl = sub.add_parser("download", help="下载 AK3 刷机包")
    p_dl.add_argument("--run-id", type=int, default=0,
                      help="指定 Run ID，默认取最近一次成功构建")
    p_dl.add_argument("--out", default="", help="保存目录，默认 ./ak3")
    p_dl.add_argument("--repo", default="")
    p_dl.add_argument("--token", default="")
    p_dl.set_defaults(func=cmd_download)

    args = parser.parse_args()
    if not getattr(args, "cmd", None):
        parser.print_help()
        return
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n已中断。")
    except RuntimeError as e:
        die(str(e))


if __name__ == "__main__":
    main()
