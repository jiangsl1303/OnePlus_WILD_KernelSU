# OnePlus KernelSU-Next 一键构建（AK3 刷机包）

> ✅ **已实测跑通**：2026-10-10，`device=ACE3v` 一次产出 **4 个 AK3 包**（A15/A16 × 6.1.75/6.1.118/6.1.141），
> 4 个 build job 全部 `success`，总耗时 24m21s。完整证据见 [`VERIFICATION.md`](./VERIFICATION.md)。

参考 [WildKernels/OnePlus_KernelSU_SUSFS](https://github.com/WildKernels/OnePlus_KernelSU_SUSFS) 的构建体系，
做了一套**可以精确选择任意一款一加设备（或全部设备）**、一键产出 **KernelSU-Next 版 GKI 内核 AnyKernel3 刷机包**的工具。

核心思路：把 WildKernels 那套「一次只能按 Android 大版本批量构建」的流程，改成「按型号精确构建」，
并且**每次运行都从上游拉取最新的设备配置与内核源码清单**，所以永远构建的是最新内核。

---

## 目录内容

```
oneplus-ksun-builder/
├── .github/workflows/build-oneplus-ksun.yml   ← 放进你 fork 的仓库里，负责云端编译
├── opbuild.py                                 ← 本地一键触发 / 查状态 / 下载（可选，但强烈推荐）
├── SUSFS-LKM.md                               ← SUSFS 方案分析：为什么用 LKM、源码补丁为什么走不通（含实测数据）
├── VERIFICATION.md                            ← 实测跑通报告（含 SHA-256、日志证据、复现参数）
└── README.md                                  ← 本文档
```

---

## SUSFS 有四种方案，先选一种

| `susfs_mode` | 内核 | SUSFS | 说明 |
|---|---|---|---|
| `patched` | 钉定 KSUN **33239** | 钉定 **v2.2.0** | 传统源码补丁路线，已验证可用，但版本必须成对钉死 |
| **`lkm`（默认，推荐）** | 最新 KernelSU-Next（`dev`，当前 KSUVER 33337） | **v2.3.0**（可加载模块） | 内核侧**一行 SUSFS 补丁都不打**；SUSFS 由额外产出的模块 zip 提供，开机由 `ksud` 加载 |
| `source` | pershoot/KernelSU-Next **`dev-susfs`** | **v2.3.0**（源码） | WildKernels GKI 仓库同款方案：KSUN 侧集成已内置在 fork 里，SUSFS 直接编进内核。**免刷 LKM、免重启两次** |
| `none` | 最新 KernelSU-Next | 无 | 只带 KernelSU-Next |

**为什么默认用 `lkm`**：`source` 模式虽然方案优雅，但依赖 pershoot 的 `dev-susfs` 分支
（非官方 KernelSU-Next），且只在本仓库的 OnePlus 内核上做过干跑验证（补丁零 `.rej`），
尚未跑完整 CI 编译；求稳就选默认的 `lkm`。

**`source` 模式是什么**（2026-10-12 从 WildKernels/GKI_KernelSU_SUSFS 学到并迁移）：

- KSUN 侧：用 `pershoot/KernelSU-Next` 的 `dev-susfs` 分支 —— 该 fork 已内置 SUSFS v2.3.0 的
  KSUN 侧集成（`kernel/feature/selinux_hide.c` 定义全局 `fake_state`，8 个源文件带
  `CONFIG_KSU_SUSFS` 钩子）。**不再需要** `10_enable_susfs_for_ksu.patch`，也不需要上游
  `kernel_patches` 的 `next/susfs_fix_patches`（只提供到 v2.2.0）。
- SUSFS 侧：取 `pershoot/susfs4ksu` 的 `gki-<版本>-dev` 分支（= simonpunk 分支头 + 2 条
  "no features core / Toolkit 共存"提交，实测仍为 `v2.3.0`）。
- 内核侧：只做 SUSFS 自带的 `fs/` + `include/linux/` 覆盖，再打
  `50_add_susfs_in_gki-android14-6.1.patch`。已在真实 ACE3V 内核树（6.1.141）上干跑：
  **退出码 0、零 `.rej`**。

**为什么以前不走 source**：自制「官方 KSUN + v2.3.0 集成补丁」在 KSUN dev 上有 7+ 个
`.rej`，且 `kernel_patches` 没有对应的 v2.3.0 fix 补丁；pershoot fork 方案把集成
交给 SUSFS 维护线同步更新，从根上消掉了补丁维护问题。
完整实测数据与原理见 **[SUSFS-LKM.md](./SUSFS-LKM.md)**。

---

## 快速开始

### 第 1 步：Fork 上游仓库

打开 <https://github.com/WildKernels/OnePlus_KernelSU_SUSFS>，点右上角 **Fork**。

> 必须 fork，不能只新建一个空仓库 —— 编译用的 `build-kernel` action 就在这个仓库里。

### 第 2 步：放入 workflow 文件

把本目录下的 `build-oneplus-ksun.yml` 上传到你的 fork 仓库的 `.github/workflows/` 目录。

网页操作：进入你的 fork → **Add file → Upload files** → 拖入文件 →
路径填 `.github/workflows/build-oneplus-ksun.yml` → Commit。

放好后，仓库的 **Actions** 页面左侧会出现 **Build OnePlus Kernel (KernelSU-Next + SUSFS)**。

### 第 2.5 步：必须的前置条件 ⚠️

跳过这几步，构建一定会在中途硬失败。**必须都做完再触发构建。**

**① 先生成工具链缓存（否则报 Toolchain NOT FOUND）**

上游 `build-kernel` action 不会自动下载编译工具链，它只从你自己 fork 的
`toolchain-cache` Release 里取。新 fork 没有这个 Release，构建会在 "Setup toolchain"
阶段直接致命退出：

```
##[error][FATAL ERROR] Toolchain clang-xxxx.tar.gz NOT FOUND in GitHub Release cache!
##[error][FATAL ERROR] Please Run Mirror Toolchain Workflow or select sync toolchain during build!!!
```

做法：进入 fork → **Actions** → 左侧选 **🛠️ ToolChains Generator** → **Run workflow**。
它会下载约 5.4 GB 工具链并以 Release 形式存到你的仓库（**只需做一次**，之后长期有效）。

**② 给 `build-kernel` action 打一个下载补丁（否则 SUSFS 拉取 403）**

gitlab.com 的 WAF 会用「User-Agent 声明 vs TLS 指纹是否一致」来判定机器人。
上游 action 用 `aria2c` 并**伪造 Chrome UA**，两者都命中，于是对 SUSFS 归档 URL 直接 403：

```
-> [HttpSkipResponseCommand.cc:239] errorCode=22 The response status is not successful. status=403
curl: (22) The requested URL returned error: 403
##[error]All attempts failed for https://gitlab.com/simonpunk/susfs4ksu.git
```

实测结论（在 GitHub runner 上，同一个 URL）：

| 请求方式 | 结果 |
|----------|------|
| `curl`（默认 UA） | **200** ✅ |
| `curl -A curl/8.9.1` | 200 ✅ |
| `curl -A "Mozilla/5.0 ... Chrome/120"` | **403** ❌ |
| `curl -A ""` | 200 ✅ |
| `aria2c`（伪造 Chrome UA + 16 并发 Range） | **403** ❌ |
| `wget`（默认 UA） | 200 ✅ |
| GitLab `api/v4/.../archive.tar.gz`（两种 UA 都） | 200 ✅ |

所以修法：**不要覆盖 User-Agent**，改成 curl 优先（默认 UA）、api/v4 归档为第二路径、
aria2c 兜底。在 fork 仓库编辑 `.github/actions/build-kernel/action.yml`，
找到函数 `retry_fetch_archive()` 里的下载循环，把这一段：

```yaml
          while [ $attempt -le $max_attempts ]; do
              echo " Attempt $attempt/$max_attempts: High-speed fetch for $repo_name ($branch)"

              if aria2c -x16 -s16 -j16 -k1M --retry-wait=2 --max-tries=5 -d "/dev/shm" -o "$archive_name" --allow-overwrite=true "${aria2_headers[@]}" $aria_log_flags "$download_url"; then
                  mkdir -p "$repo_name"
                  if tar -I "pigz -p $nproc -b 256" -x --record-size=1M -f "$shm_path" -C "$repo_name" --strip-components=1 --no-same-owner; then
                      echo "✅ Success: $repo_name synced"
                      rm -f "$shm_path"
                      return 0
                  fi
              fi
```

替换为：

```yaml
          # 备用下载路径：GitLab API 归档端点（两种 UA 都放行）
          local api_url=""
          if [[ "$url" == *"gitlab.com"* ]]; then
              local proj
              proj=$(printf '%s' "$url" | sed -E 's#^https?://gitlab\.com/##; s#\.git$##' | sed 's#/#%2F#g')
              api_url="https://gitlab.com/api/v4/projects/${proj}/repository/archive.tar.gz?sha=${branch}"
          fi

          while [ $attempt -le $max_attempts ]; do
              echo " Attempt $attempt/$max_attempts: Fetch for $repo_name ($branch)"

              # 关键：不要覆盖 User-Agent，否则 Cloudflare 判机器人 403
              local fetched=0
              if curl -fsSL --retry 3 --retry-delay 2 --max-time 300 -o "$shm_path" "$download_url"; then
                  fetched=1
                  echo "   ↳ curl ok ($(stat -c%s "$shm_path" 2>/dev/null || echo '?') bytes)"
              elif [ -n "$api_url" ] && curl -fsSL --retry 3 --retry-delay 2 --max-time 300 -o "$shm_path" "$api_url"; then
                  fetched=1
                  echo "   ↳ curl(api/v4) ok"
              elif aria2c -x16 -s16 -j16 -k1M --retry-wait=2 --max-tries=5 -d "/dev/shm" -o "$archive_name" --allow-overwrite=true $aria_log_flags "$download_url"; then
                  fetched=1
                  echo "   ↳ aria2c ok"
              fi

              if [ "$fetched" = "1" ]; then
                  mkdir -p "$repo_name"
                  if tar -I "pigz -p $nproc -b 256" -x --record-size=1M -f "$shm_path" -C "$repo_name" --strip-components=1 --no-same-owner; then
                      echo "✅ Success: $repo_name synced"
                      rm -f "$shm_path"
                      return 0
                  fi
              fi
```

> 注意：改了 action 之后，如果以后同步上游更新，这个补丁会被覆盖，需要重新打。
> 上游若哪天自己修了（去掉伪造 UA / 换掉 aria2c），就可以不再打。
> 另外 `retry_clone()` 里给 `kernel_patches` 用的 clone 不受影响（走 git 协议，正常）。

**③ 预先创建 `ccache-cache` tag + Release（否则构建成功但缓存保存失败）**

上游 `cache/save` action 的逻辑是：如果 tag 不存在，就用 `GITHUB_TOKEN` 新建并推送它。
但 `GITHUB_TOKEN` 是 GitHub App token，**没有 `workflows` 权限**，只要待推送的提交树里含
`.github/workflows/` 文件就会被拒：

```
! [remote rejected] ccache-cache -> ccache-cache
  (refusing to allow a GitHub App to create or update workflow
   `.github/workflows/...` without `workflows` permission)
```

它虽然对 push 失败做了 `|| echo "Push failed..."` 容错继续执行，但 **Release 从未被创建**，
于是紧接着的上传全部失败：

```
##[error]Failed to upload cache-...tzst after multiple attempts.
```

修法：**事先把 tag 和 Release 建好**，runner 里 `git rev-parse ccache-cache` 直接命中，
整段推送逻辑被跳过。用你的 GitHub Token 执行一次即可：

```bash
curl -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/<你的用户名>/<你的fork>/releases \
  -d '{"tag_name":"ccache-cache","target_commitish":"main",
       "name":"General Cache","body":"Automated storage for build assets",
       "draft":false,"prerelease":false}'
```

返回 `HTTP 201` 即成功。也可以直接在网页上：**Releases → Draft a new release**，
Tag 填 `ccache-cache`，Target 选 `main`，标题随意，点 **Publish release**。

> 只需要做一次。之后每次构建都会把 ccache 缓存（每个设备约 540 MB）追加到这个 Release 里，
> 下次同设备构建命中缓存后编译会明显变快。

**④ 关于 `CCACHE_LOGFILE`（本 workflow 已内置，无需操作）**

`action.yml` 的 `📊 ccache Post-Build Statistics` 步骤里有一行
`cp "${{ env.CCACHE_LOGFILE }}" "$CCACHE_DIR"`。这个变量**必须由调用方 workflow 提供**
（上游 `build-kernel-release.yml` 里设的，本 workflow 也已设），否则会展开成空串并报：

```
Perform ccache eviction!
cp: cannot stat '': No such file or directory
##[error]Process completed with exit code 1.
```

本仓库提供的 `build-oneplus-ksun.yml` 已在 `Configure ccache` 步骤里写好了
`CCACHE_LOG="${GITHUB_WORKSPACE}/ccache.log"` 与 `CCACHE_LOGFILE=${CCACHE_LOG}`，**不用你改**。

### 第 3 步：触发构建

#### 方式 A：GitHub 网页操作

1. 进入 fork 仓库 → **Actions**
2. 左侧选 **Build OnePlus Kernel (KernelSU-Next + SUSFS)**
3. 右侧 **Run workflow** 下拉，填参数：

   | 参数 | 说明 |
   |------|------|
   | **device** | `all` = 全部设备；或填型号关键字，如 `OP13`、`OP13,OP12`、`13`、`ace5`、`pad3` |
   | **android_version** | `auto` 不限；或限定 `A14` / `A15` / `A16` |
   | **susfs_mode** | `lkm`（默认）= 最新内核 + SUSFS v2.3.0 可加载模块；`source` = pershoot dev-susfs + SUSFS v2.3.0 源码（WildKernels 同款）；`patched` = 源码补丁（钉定 KSUN 33239 + SUSFS v2.2.0）；`none` = 不带 SUSFS |
   | **ksu_ref** | KernelSU-Next 分支或 commit。`auto`（默认）按 `susfs_mode` 自动选：`lkm`/`none` → 官方 `dev`（最新）；`source` → pershoot 的 `dev-susfs`；`patched` → `234f6e04`（KSUN 33239） |
   | **susfs_ref** | 默认 `auto`：`patched` 模式钉到 v2.2.0 末次提交；`source` 模式取 pershoot/susfs4ksu 的 `gki-<版本>-dev` 分支头（实测 v2.3.0）。也可显式填 commit |
   | **optimize_level** | 编译优化，默认 `O2` |
   | **clean_build** | 勾选则不用 ccache 缓存（更慢） |
   | **make_release** | 勾选则构建完自动创建 Release（AK3 包 + LKM 模块一起发） |
   | **list_only** | 勾选则只列出匹配到的设备，不构建（**用来查型号关键字**） |
   | **debug** | 输出详细日志 |

4. 点 **Run workflow**，等 20～40 分钟
5. 构建完成后，在本次 run 页面底部 **Artifacts** 区域下载

   - `AK3_<型号>_<OS>_<内核>_KSUN_<KSUVER>.zip` —— 内核刷机包
   - `SUSFS-LKM-v2.3.0-r18-arm64-multi-kmi.zip` —— SUSFS 模块（仅 `susfs_mode=lkm` 时产出）

#### 方式 B：本地脚本（推荐，更省事）

```bash
# 一次性配置
export GITHUB_TOKEN=ghp_xxxxxxxx                      # GitHub Token，需 repo + workflow 权限
export OP_REPO=你的用户名/OnePlus_KernelSU_SUSFS        # 你的 fork

# 查设备
python opbuild.py list                    # 列出全部 158 个配置
python opbuild.py list --filter 13        # 只看一加 13 系列

# 触发构建
python opbuild.py build --device OP13               # 只构建一加 13
python opbuild.py build --device OP13 --android A15 # 限定 Android 15 的配置
python opbuild.py build --device OP13,OP12          # 多个设备
python opbuild.py build --device all --android A16  # 全部 A16 设备
python opbuild.py build --device OP13 --release     # 顺便建 Release

# 看进度 / 下载
python opbuild.py status
python opbuild.py download --out D:\ak3
```

Windows 下设置环境变量用 `set GITHUB_TOKEN=...`（cmd）或 `$env:GITHUB_TOKEN="..."`（PowerShell）。

---

## LKM 模式怎么用（默认模式）

`susfs_mode=lkm` 时一次运行会产出**两类产物**，刷入要分两步：

```
① 刷 AK3 内核包         AK3_<型号>_<OS>_<内核>_KSUN_<KSUVER>.zip
   （TWRP 或 KernelSU 管理器的「安装 → 修补/刷入」）
② 重启
③ 安装 SUSFS 模块       SUSFS-LKM-v2.3.0-r18-arm64-multi-kmi.zip
   （KernelSU 管理器的「模块 → 从本地安装」）
④ 重启
⑤ 验证
   cat /data/adb/modules/susfs_lkm_loader/load.log
   ls /proc/susfs_path /proc/susfs_kstat /proc/susfs_open_redirect
```

**顺序不能反**：SUSFS 模块要靠内核里已内置的 KernelSU 符号才能加载。

**这个模块是什么**：SUSFS v2.3.0 编译成的可加载内核模块（`.ko`），
内置 8 个 KMI 的二进制（`android12-5.10` … `android17-6.18`），
开机时按 `/proc/sys/kernel/osrelease` 的真实值自动选对应的那份加载。
它**不管理规则** —— 隐藏规则交给 FolkSU 之类的工具通过 `/proc/susfs_*` 节点写。

**它会自己保护自己**：加载前先用探测器确认当前没有 SUSFS 在跑，
如果检测到已存在就**原样不动地退出**，绝不叠加（叠加会崩内核）。

**如果加载失败**：看 `load.log`。常见原因是厂商内核的 ABI 与 GKI 基线不同，
符号解析不到。这时把 `susfs_mode` 改回 `patched` 走已验证的源码补丁路线。

原理、实测数据与风险详见 **[SUSFS-LKM.md](./SUSFS-LKM.md)**。

---

## source 模式怎么用（SUSFS 编进内核）

`susfs_mode=source` 时 SUSFS 直接编进内核，产物只有 AK3 一个 zip，刷一步：

```
① 刷 AK3 内核包         AK3_<型号>_<OS>_<内核>_KSUN_<KSUVER>.zip
② 重启
③ 验证
   cat /proc/version                      # 含 KSUVER
   ls /proc/susfs_path /proc/susfs_kstat /proc/susfs_open_redirect
```

**它和 lkm 的本质区别**：lkm 是「最新官方内核 + 外挂模块」；source 是
「pershoot 定制 fork + SUSFS 源码内置」。两者都能用，source 少一次重启、
少一个模块，但用的是非官方 KSUN 分支。

**用法**（网页触发时）：

| 参数 | 填法 |
|------|------|
| `device` | `ACE3v`（或你的型号） |
| `susfs_mode` | `source` |
| `ksu_ref` | `auto`（自动解析 pershoot `dev-susfs` 分支头） |
| `susfs_ref` | `auto`（自动取 pershoot/susfs4ksu `gki-android14-6.1-dev` 分支头） |

本地脚本：

```bash
python opbuild.py build --device ACE3v --susfs-mode source
```

**验证状态**：补丁侧已在真实 ACE3V 内核树（`android_kernel_common_oneplus_sm7675`
@ 6.1.141）干跑通过（`patch -p1 --forward` 退出码 0、零 `.rej`），
**完整编译链接尚未在 CI 跑过** —— 第一次构建请盯住
"Apply SUSFS Patches" 与编译阶段日志，有问题把日志发来。

---

## 设备选择怎么填

`device` 输入框支持四级模糊匹配，越精确越优先：

| 你填的 | 匹配结果 | 说明 |
|--------|----------|------|
| `all` | 全部 158 个配置 | 全部设备 × 全部 Android 版本 |
| `OP13` | 6 个 | 一加 13 全部变体，**不会**误匹配 13T / 13S / 13r |
| `OP13T` | 4 个 | 只匹配一加 13T |
| `13` | 16 个 | 13 / 13T / 13S / 13r 全系列 |
| `oneplus_13` | 6 个 | 用 manifest 文件名匹配，等价于 `OP13` |
| `ace5pro` | 4 个 | 归一化匹配 → `OP-ACE-5-PRO*` |
| `pad3` | 8 个 | 归一化匹配 → `OP-PAD-3-*` |
| `OP13,OP12` | 10 个 | 逗号分隔可多选 |

匹配优先级：**型号边界前缀 → manifest 边界前缀 → 归一化前缀 → 归一化包含**。

> 拿不准填什么，就先把 `list_only` 勾上跑一次，或在本地 `python opbuild.py list --filter 关键字`，
> 输出会精确告诉你匹配到了哪些设备。

### 关于 android_version

同一个设备往往有多个 Android 版本的配置，例如一加 13：

- `OP13-6.6.30` → A15（Android 15 系统）
- `OP13` / `OP13-6.6.89` → A16（Android 16 系统）

**选哪个取决于你手机当前运行的 Android 版本**，不要盲目选最新。
不确定就先选 `auto`，构建矩阵的 Job Summary 会列出全部匹配项，你看清楚再决定。

---

## 产物说明

构建产物的命名规则：

```
# 内核刷机包（AnyKernel3）
AK3_<型号>_<OS版本>_<内核版本>_KSUN_<KernelSU-Next版本>[_SuSFS_<SUSFS版本>].zip

# SUSFS 模块（仅 susfs_mode=lkm 时产出）
SUSFS-LKM-<SUSFS版本>-arm64-multi-kmi.zip
```

例如：

```
AK3_OP13_A16_6.6.89_KSUN_33337.zip                        ← lkm 模式（不带源码补丁，无 SuSFS 后缀）
AK3_OP13_A16_6.6.89_KSUN_33239_SuSFS_v2.2.0.zip           ← patched 模式
SUSFS-LKM-v2.3.0-r18-arm64-multi-kmi.zip                  ← lkm 模式附带的 SUSFS 模块
```

**AK3 包**刷入方式：

- **KernelSU Manager / WildKSU Manager** → 安装 → 选择该 zip
- 或 **TWRP / OrangeFox** → 安装 → 选择该 zip

**SUSFS LKM 模块**刷入方式：KernelSU 管理器 → 模块 → 从本地安装 → 选择该 zip → 重启。
（顺序：先刷 AK3 内核包并重启，再装模块并重启。）

> 前提：设备已解锁 Bootloader。刷机前务必备份数据。

---

## 常用机型速查

| 设备 | 建议关键字 | 内核 |
|------|-----------|------|
| 一加 15 / 15T / 15R | `OP15` | android16-6.12 |
| 一加 13 / 13T / 13S / 13R | `OP13` | android15-6.6 |
| 一加 12 / 12R | `OP12` | android14-6.1 |
| 一加 11 / 11R | `OP11` | android13-5.15 |
| 一加 10 Pro / 10T / 10R | `OP10` | android12-5.10 |
| 一加 Ace 5 / 5 Pro / 5 Race / 5 Ultra | `ace5` | android14-6.1 / 15-6.6 |
| 一加 Ace 3 / 3 Pro / 3V | `ace3` | android13-5.15 / 14-6.1 |
| 一加 Ace 2 / 2 Pro / 2V | `ace2` | android12-5.10 / 13-5.15 |
| 一加 Nord 4 / 5 / CE 系列 | `nord` | 视型号而定 |
| 一加 Pad 2 / 3 / Pro | `pad` | 视型号而定 |

---

## 完整设备清单

以下是上游当前全部 158 个可构建配置（会自动跟随上游更新）。

<details>
<summary><b>点开查看完整清单</b></summary>

### Android 16（A16）

| 型号 | 内核 |
|------|------|
| `OP-ACE-2-PRO` | android13-5.15 |
| `OP-ACE-2` | android12-5.10 |
| `OP-ACE-2V` | android12-5.10 |
| `OP-ACE-3-5.15.167` | android13-5.15 |
| `OP-ACE-3-PRO-6.1.118` | android14-6.1 |
| `OP-ACE-3-PRO` | android14-6.1 |
| `OP-ACE-3` | android13-5.15 |
| `OP-ACE-3V-6.1.118` | android14-6.1 |
| `OP-ACE-3V` | android14-6.1 |
| `OP-ACE-5-6.1.118` | android14-6.1 |
| `OP-ACE-5-PRO-6.6.89` | android15-6.6 |
| `OP-ACE-5-PRO` | android15-6.6 |
| `OP-ACE-5-RACE-6.1.134` | android14-6.1 |
| `OP-ACE-5-RACE` | android14-6.1 |
| `OP-ACE-5-ULTRA-6.6.89` | android15-6.6 |
| `OP-ACE-5-ULTRA` | android15-6.6 |
| `OP-ACE-5` | android14-6.1 |
| `OP-ACE-6-6.6.89` | android15-6.6 |
| `OP-ACE-6-ULTRA` | android16-6.12 |
| `OP-ACE-6` | android15-6.6 |
| `OP-ACE-6T` | android16-6.12 |
| `OP-N6` | android13-5.15 |
| `OP-NORD-3` | android12-5.10 |
| `OP-NORD-4-6.1.118` | android14-6.1 |
| `OP-NORD-4-CE` | android13-5.15 |
| `OP-NORD-4` | android14-6.1 |
| `OP-NORD-5-6.1.118` | android14-6.1 |
| `OP-NORD-5` | android14-6.1 |
| `OP-NORD-6` | android15-6.6 |
| `OP-NORD-CE-5-6.1.134` | android14-6.1 |
| `OP-NORD-CE-5` | android14-6.1 |
| `OP-NORD-CE4-LITE` | android14-6.1 |
| `OP-NORD-CE6-LITE` | android14-6.1 |
| `OP-OPEN-5.15.167` | android13-5.15 |
| `OP-OPEN` | android13-5.15 |
| `OP-PAD-2-MT6991` | android15-6.6 |
| `OP-PAD-2-PRO-6.6.89` | android15-6.6 |
| `OP-PAD-2-PRO` | android15-6.6 |
| `OP-PAD-2-SM8650` | android14-6.1 |
| `OP-PAD-3-MT6897` | android14-6.1 |
| `OP-PAD-3-PRO` | android16-6.12 |
| `OP-PAD-3-SM8750-6.6.89` | android15-6.6 |
| `OP-PAD-3-SM8750` | android15-6.6 |
| `OP-PAD-4` | android16-6.12 |
| `OP-PAD-GO-2` | android14-6.1 |
| `OP-PAD-LITE` | android16-6.12 |
| `OP-PAD-MT6983` | android12-5.10 |
| `OP-PAD-PRO` | android14-6.1 |
| `OP-TURBO-6` | android15-6.6 |
| `OP-TURBO-6V-6.1.118` | android14-6.1 |
| `OP-TURBO-6V` | android14-6.1 |
| `OP-TURBO-6X` | android14-6.1 |
| `OP10pro` | android12-5.10 |
| `OP11-5.15.167` | android13-5.15 |
| `OP11` | android13-5.15 |
| `OP11r` | android12-5.10 |
| `OP12-6.1.118` | android14-6.1 |
| `OP12` | android14-6.1 |
| `OP12r-5.15.167` | android13-5.15 |
| `OP12r` | android13-5.15 |
| `OP13-6.6.89` | android15-6.6 |
| `OP13` | android15-6.6 |
| `OP13S` | android15-6.6 |
| `OP13T-6.6.89` | android15-6.6 |
| `OP13T` | android15-6.6 |
| `OP13r-6.1.118` | android14-6.1 |
| `OP13r` | android14-6.1 |
| `OP15` | android16-6.12 |
| `OP15T` | android16-6.12 |
| `OP15r` | android16-6.12 |

### Android 15（A15）

| 型号 | 内核 |
|------|------|
| `OP-ACE-2-5.10.209` | android12-5.10 |
| `OP-ACE-2-PRO-5.15.149` | android13-5.15 |
| `OP-ACE-2-PRO` | android13-5.15 |
| `OP-ACE-2` | android12-5.10 |
| `OP-ACE-2V-5.10.209` | android12-5.10 |
| `OP-ACE-2V` | android12-5.10 |
| `OP-ACE-3-5.15.149` | android13-5.15 |
| `OP-ACE-3-PRO-6.1.75` | android14-6.1 |
| `OP-ACE-3-PRO` | android14-6.1 |
| `OP-ACE-3` | android13-5.15 |
| `OP-ACE-3V-6.1.75` | android14-6.1 |
| `OP-ACE-3V` | android14-6.1 |
| `OP-ACE-5-6.1.75` | android14-6.1 |
| `OP-ACE-5-PRO-6.6.30` | android15-6.6 |
| `OP-ACE-5-PRO` | android15-6.6 |
| `OP-ACE-5-RACE` | android14-6.1 |
| `OP-ACE-5-ULTRA-6.6.50` | android15-6.6 |
| `OP-ACE-5-ULTRA` | android15-6.6 |
| `OP-ACE-5.10.209` | android12-5.10 |
| `OP-ACE-5.10.226` | android12-5.10 |
| `OP-ACE-5` | android14-6.1 |
| `OP-ACE-RACE-5.10.209` | android12-5.10 |
| `OP-ACE-RACE-5.10.226` | android12-5.10 |
| `OP-ACE-RACE` | android12-5.10 |
| `OP-ACE` | android12-5.10 |
| `OP-NORD-3-5.10.209` | android12-5.10 |
| `OP-NORD-3` | android12-5.10 |
| `OP-NORD-4-6.1.75` | android14-6.1 |
| `OP-NORD-4-CE-5.15.149` | android13-5.15 |
| `OP-NORD-4-CE-5.15.167` | android13-5.15 |
| `OP-NORD-4-CE` | android13-5.15 |
| `OP-NORD-4` | android14-6.1 |
| `OP-NORD-5` | android14-6.1 |
| `OP-NORD-CE-5` | android14-6.1 |
| `OP-NORD-CE4-LITE` | android14-6.1 |
| `OP-NORD-N30-SE` | android15-6.6 |
| `OP-OPEN-5.15.149` | android13-5.15 |
| `OP-OPEN` | android13-5.15 |
| `OP-PAD-2-PRO-6.6.30` | android15-6.6 |
| `OP-PAD-2-PRO` | android15-6.6 |
| `OP-PAD-2-SM8650-6.1.75` | android14-6.1 |
| `OP-PAD-2-SM8650` | android14-6.1 |
| `OP-PAD-3-MT6897-6.1.75` | android14-6.1 |
| `OP-PAD-3-MT6897` | android14-6.1 |
| `OP-PAD-3-SM8750-6.6.30` | android15-6.6 |
| `OP-PAD-3-SM8750` | android15-6.6 |
| `OP-PAD-LITE` | android12-5.10 |
| `OP-PAD-MT6983-5.10.209` | android12-5.10 |
| `OP-PAD-MT6983` | android12-5.10 |
| `OP-PAD-PRO-6.1.75` | android14-6.1 |
| `OP-PAD-PRO` | android14-6.1 |
| `OP10pro-5.10.209` | android12-5.10 |
| `OP10pro` | android12-5.10 |
| `OP10r` | android12-5.10 |
| `OP10t-5.10.209` | android12-5.10 |
| `OP10t-5.10.226` | android12-5.10 |
| `OP10t` | android12-5.10 |
| `OP11-5.15.149` | android13-5.15 |
| `OP11` | android13-5.15 |
| `OP11r-5.10.209` | android12-5.10 |
| `OP11r` | android12-5.10 |
| `OP12-6.1.75` | android14-6.1 |
| `OP12` | android14-6.1 |
| `OP12r-5.15.149` | android13-5.15 |
| `OP12r` | android13-5.15 |
| `OP13-6.6.30` | android15-6.6 |
| `OP13-CPH-6.6.56` | android15-6.6 |
| `OP13-CPH` | android15-6.6 |
| `OP13-PJZ` | android15-6.6 |
| `OP13S` | android15-6.6 |
| `OP13T-6.6.56` | android15-6.6 |
| `OP13T` | android15-6.6 |
| `OP13r-6.1.75` | android14-6.1 |
| `OP13r` | android14-6.1 |

### Android 14（A14）

| 型号 | 内核 |
|------|------|
| `OP-ACE-2V` | android12-5.10 |
| `OP-ACE-3-PRO` | android14-6.1 |
| `OP-ACE-RACE` | android12-5.10 |
| `OP-ACE` | android12-5.10 |
| `OP-NORD-3` | android12-5.10 |
| `OP-PAD-GO` | android12-5.10 |
| `OP-PAD-MT6983` | android12-5.10 |
| `OP-PAD-PRO` | android14-6.1 |
| `OP10pro` | android12-5.10 |
| `OP10r` | android12-5.10 |
| `OP11` | android13-5.15 |
| `OP11r` | android12-5.10 |
| `OP12` | android14-6.1 |

</details>

---

## 常见问题

**Q：构建要多久？**
首次约 30～50 分钟（要下载完整工具链）；之后因为有 ccache 缓存，同机型重复构建约 15～25 分钟。

**Q：`all` 一次全构建现实吗？**
158 个配置、并发 10，整体会跑很久（数小时），也大量消耗 Actions 额度。
建议配合 `android_version` 缩小范围，例如 `device=all` + `android_version=A16`。

**Q：产物在哪？**
本次 run 页面底部的 **Artifacts** 区域。勾选 `make_release` 的话会额外生成 Release。

**Q：报错 `No config files found`？**
`device` 关键字没匹配到设备。先把 `list_only` 勾上跑一次看匹配结果，或用 `opbuild.py list`。

**Q：报错 404 / 找不到 workflow？**
检查 `build-oneplus-ksun.yml` 是否放在 `.github/workflows/` 目录下，以及 fork 仓库是否启用了 Actions。

**Q：`susfs_ref` 是干什么的？为什么默认要钉住旧版本？**

SUSFS 和 KernelSU-Next 必须**成对**，否则补丁打不上。三个约束：

1. 上游 `WildKernels/kernel_patches` 的 `next/susfs_fix_patches/` 只提供到 **v2.2.0**；
2. SUSFS 上游 `simonpunk/susfs4ksu` 的各 `gki-*` 分支已于 **2026-08-30 升到 v2.3.0**，
   action 的 `case "$susfs_version"` 是硬编码白名单，遇到 v2.3.0 直接致命退出：
   ```
   SusFS Version: v2.3.0
   ##[error]Unsupported SUSFS version: v2.3.0
   ```
3. 那个 v2.2.0 目录里的修复补丁是按 **KSUN 33239** 生成的
   （提交信息 `Update KSUN 33239 SusFS 2.2.0 + KSU_Toolkit`，2026-08-11）。
   SUSFS 或 KSU 任何一边更新，`10_enable_susfs_for_ksu.patch` 都会在**更多文件**上产生
   `.rej`，而对应 `fix_<文件>.patch` 不存在，于是报：
   ```
   Patching file: app_profile.h with fix_app_profile.h.patch
   .../susfs_fix_patches/v2.2.0/fix_app_profile.h.patch: No such file or directory
   ##[error]Process completed with exit code 1.
   ```

所以 workflow 把两边一起钉到 **2026-08-11** 那一组：

| 内核分支 | SUSFS 钉定提交 | 该日期的 SUSFS 版本 |
|----------|----------------|---------------------|
| `gki-android12-5.10` | `3c14ad549f82` | v2.2.0 |
| `gki-android13-5.10` | `f81aaf10e956` | v2.2.0 |
| `gki-android13-5.15` | `ccb1918684b2` | v2.2.0 |
| `gki-android14-5.15` | `0463ac089308` | v2.2.0 |
| `gki-android14-6.1`  | `e287d5906638` | v2.2.0 |
| `gki-android15-6.6`  | `be7b7ef49a1e` | v2.2.0 |
| `gki-android16-6.12` | `f37930f374ef` | v2.2.0 |

KernelSU-Next 则钉到 `234f6e040fcbca18b16d2398e1aa225712ec99ad`（该日期的 `dev` HEAD）。

> 这组配对是**实测验证过**的：对 7 个分支各跑一次
> `patch -p1 --forward < 10_enable_susfs_for_ksu.patch`，产生的 `.rej` 恰好是
> `{Kbuild, init.c, kernel_umount.c, setuid_hook.c, sucompat.c, supercall.c}`，
> 与 `v2.2.0/` 下的 6 个 `fix_*.patch` 一一对应。

`susfs_ref` 可填：

| 值 | 行为 |
|----|------|
| `auto`（默认）/ 留空 | 用上表钉定值，并联网校验该提交确实报告 v2.2.0 |
| `latest` | 跟随分支头；若分支头版本不被 action 支持，自动回退到钉定值并打 warning |
| 任意 commit / 分支名 | 原样传给构建器（高级用法） |

> 上游补齐 v2.3.0 的修复补丁后，把 `susfs_ref` 改成 `latest`、`ksu_ref` 改回 `dev` 即可。
>
> 另外：钉定值故意用 **12 位短 SHA** —— gitlab.com 的 WAF 对 URL 路径里完整的
> 40 位十六进制串会直接返回 403，短 SHA 不受影响，且 GitLab 的 `/-/archive/` 与
> `/-/raw/` 都能正常解析短 SHA。

**Q：怎么保持"最新"？**
workflow 每次运行都会从上游 `WildKernels/OnePlus_KernelSU_SUSFS` 拉取最新的
`configs/`（设备与内核版本清单）和 `manifests/`（内核源码仓库 revision）。
所以只要上游更新了内核源码，你直接跑就是最新的。
（注意：`ksu_ref` / `susfs_ref` 默认是**钉定**的，见下条 —— 这是为了让 SUSFS 补丁能打上。）

**Q：`ksu_ref` 为什么默认不是 `dev`？**

因为 KernelSU-Next 和 SUSFS 的修复补丁必须版本配对。上游 `kernel_patches` 的
`next/susfs_fix_patches/v2.2.0/` 是按 **KSUN 33239** 生成的，从它的提交历史就能看出来：

```
2026-08-11  Update KSUN 33239 SusFS 2.2.0 + KSU_Toolkit   ← 最新一版
2026-07-20  Update KSUN 33219 SusFS 2.2.0 + KSU_Toolkit
2026-06-30  Update KSUN 33207 SusFS 2.2.0 + KSU_Toolkit
2026-06-21  Update KSUN 33201 SusFS 2.2.0 + KSU_Toolkit
```

而 `dev` 分支一直在前进（当前 KSUN 33337）。KernelSU-Next 一变，
`10_enable_susfs_for_ksu.patch` 就会在**新的文件**上产生 `.rej`，而对应的
`fix_<文件>.patch` 并不存在，于是构建报：

```
Patching file: allowlist.c with fix_allowlist.c.patch
.../susfs_fix_patches/v2.2.0/fix_allowlist.c.patch: No such file or directory
##[error]Process completed with exit code 1.
```

所以 `ksu_ref` 默认钉到 **`234f6e040fcbca18b16d2398e1aa225712ec99ad`**，
它就是 2026-08-11 时的 `dev` HEAD，对应 KSUN 33239。

> KernelSU-Next 的版本号算法：`版本 = dev 分支提交数 + 30000`。
> 例如 `dev` 当前 3337 个提交 → 33337；目标 33239 → 33239-30000 = 3239 个提交。
>
> 想换版本：先算出目标提交数，再用 GitHub API 取第 N 个提交
> （`/repos/KernelSU-Next/KernelSU-Next/commits?sha=dev&per_page=1&page=3239+1`）。
>
> 等上游 `kernel_patches` 补出 v2.3.0 的修复补丁后，就可以把 `susfs_ref` 改成 `latest`
> 并把 `ksu_ref` 改回 `dev`。

**Q：为什么我的设备不在清单里？**
上游尚未收录该机型。可以到上游仓库提 issue 请求适配，或选一款内核版本（`androidXX-YY.ZZ.AAA`）
最接近的设备尝试 —— 但 `XX-YY.ZZ` 必须完全一致。

**Q：KernelSU-Next 都更新到 3333x 了，还不能连上 SUSFS v2.3.0 吗？**

**不是 KernelSU-Next 太旧，而是 SUSFS 那侧的补丁集没跟上。** 需要两个上游动作同时发生：

1. `WildKernels/kernel_patches` 要发布 `next/susfs_fix_patches/v2.3.0/`（含 7 个新 fix 补丁）。
   现状：只到 `v2.2.0`，仓库最后推送 `2026-09-14`，最后一次 SUSFS 相关提交是
   `2026-08-11 Update KSUN 33239 SusFS 2.2.0 + KSU_Toolkit`。
2. `build-kernel` action 的 `case "$susfs_version"` 要加 `"v2.3.0")` 分支。
   现状：**2026-10-11 推送的最新版 action.yml 仍然只到 `v2.2.0`**，
   全文**没有任何 LKM 相关内容**，遇到 v2.3.0 依然报 `Unsupported SUSFS version`。

还有一个反直觉的实测结论：**内核越新，SUSFS v2.3.0 反而越贴**。
把 SUSFS v2.3.0 的主补丁往不同版本的 KernelSU-Next 上打，产生的 `.rej` 数是：

| KernelSU-Next | `.rej` 数 |
|---|---|
| 最新 `dev`（33337） | **7** |
| 33303（`1905f41e`） | 10 |
| 33304（`e4bf775a`） | 10 |

原因是 `simonpunk/susfs4ksu` 的 `-dev` 分支一直在追上游改动。所以"升到某个版本就能打上"
这个思路不成立 —— 必须有人写 fix 补丁。

> **所以本项目默认走 LKM 路线**：内核用最新 KernelSU-Next（一行 SUSFS 补丁都不打），
> SUSFS v2.3.0 作为 `.ko` 模块加载。这样**绕开上面两个前置条件**，
> 直接拿到「最新内核 + 新 SUSFS」。
>
> 完整实测数据见 **[SUSFS-LKM.md](./SUSFS-LKM.md)**。

**Q：LKM 模式加载失败怎么办？**

先看日志：`cat /data/adb/modules/susfs_lkm_loader/load.log`。

| 现象 | 原因 | 处理 |
|---|---|---|
| `Refusing unsupported kernel: 6.1.xxx-android14-...` | `osrelease` 里没有 `-android14-` 这样的 KMI 标记 | 少见；确认内核版本串格式 |
| `probe=12` / `无法确认 SUSFS 不存在` | 探测器判定当前环境不安全 | 先卸载其它 SUSFS 实现再试 |
| `susfs_insmod 退出码=非0` + `ksud insmod 退出码=非0` | 厂商内核 ABI 与 GKI 基线差异导致符号解析失败 | 改 `susfs_mode=patched` 走源码补丁路线 |
| `检测到已有 SUSFS，保持原样不动` | 内核里已经内置了 SUSFS | 正常行为，不需要这个模块 |

---

## 免责声明

刷内核有变砖风险。请务必先备份数据、确认机型与内核版本完全对应。
本工具只是对上游构建流程的编排封装，内核本身的稳定性与安全性由上游项目决定。
