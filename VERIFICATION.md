# 构建验证报告 — OnePlus ACE 3V (KernelSU-Next + SUSFS)

**结论：完整链路跑通，产出 4 个可直接刷入的 AnyKernel3 包。**

| 项目 | 值 |
|---|---|
| 仓库 | `jiangsl1303/OnePlus_WILD_KernelSU` |
| Workflow | `.github/workflows/build-oneplus-ksun.yml` |
| Run ID | `38090743432` |
| 触发时间 | 2026-10-10T22:15:34Z |
| 完成时间 | 2026-10-10T22:39:55Z |
| 总耗时 | **24 分 21 秒** |
| 最终状态 | **completed / success** |
| 设备关键字 | `ACE3v` |

---

## 1. Job 级结果

| Job | 结论 | 起 | 止 |
|---|---|---|---|
| Resolve devices | success | 22:15:37Z | 22:15:43Z |
| build (OP-ACE-3V-6.1.118 / A16 / KSUN) | **success** | 22:15:45Z | 22:39:53Z |
| build (OP-ACE-3V / A16 / KSUN) | **success** | 22:15:45Z | 22:34:20Z |
| build (OP-ACE-3V / A15 / KSUN) | **success** | 22:15:45Z | 22:39:54Z |
| build (OP-ACE-3V-6.1.75 / A15 / KSUN) | **success** | 22:15:45Z | 22:38:00Z |
| Create release | skipped（`make_release=false`） | — | — |

---

## 2. 产物清单（4 个 AK3 包）

| 文件名 | 大小 | SHA-256 |
|---|---|---|
| `AK3_OP-ACE-3V_A16_android14-6.1.141_KSUN_33239_SuSFS_v2.2.0.zip` | 18,731,430 B | `dad0c4872b6aadf679598941dd970b91b1f1086582226b453a811cb265b1b7f1` |
| `AK3_OP-ACE-3V_A15_android14-6.1.118_KSUN_33239_SuSFS_v2.2.0.zip` | 18,712,556 B | `9ea87cf80a5009004876076818af94c25e039126d4c31b385fe770241a2c9422` |
| `AK3_OP-ACE-3V_A16_android14-6.1.118_KSUN_33239_SuSFS_v2.2.0.zip` | 18,691,609 B | `b963668ecfc4067eec953296db473ec8555f6e9e991f9d5da4d467e99c5d9141` |
| `AK3_OP-ACE-3V_A15_android14-6.1.75_KSUN_33239_SuSFS_v2.2.0.zip` | 18,503,902 B | `ad0e335b72fa4940afc7ba27a9ce3786e3d8020ce45f4b2cd56760f95428bd93` |

下载地址：
```
https://github.com/jiangsl1303/OnePlus_WILD_KernelSU/actions/runs/38090743432
```

---

## 3. 包结构校验（4/4 通过）

每个 zip 均为 21 个条目，`testzip()` 全部返回 OK：

| 检查项 | 结果 |
|---|---|
| `anykernel.sh` | OK |
| `Image`（未压缩内核镜像，约 37.5–38.3 MB） | OK |
| `META-INF/com/google/android/update-binary` | OK |
| `META-INF/com/google/android/updater-script` | OK |
| `tools/magiskboot` | OK |
| `tools/ak3-core.sh` | OK |
| `banner` | OK |
| `OP-ACE-3V_A16.txt` / `OP-ACE-3V_A15.txt`（设备清单） | OK |

`anykernel.sh` 关键配置：
```
kernel.string=Wild Kernels by TheWildJames aka Morgan Weedman
do.devicecheck=0
block=boot
```

---

## 4. 内核内容校验（在 `Image` 二进制中实测）

| 包 | 设备清单 | Linux 版本串 | SUSFS | KernelSU |
|---|---|---|---|---|
| A16 / 6.1.141 | `android14-6.1.141 \| A16 \| KSUN \| 33239 \| v2.2.0` | `6.1.141-android14-OP-WILD` | YES | YES |
| A15 / 6.1.118 | `android14-6.1.118 \| A15 \| KSUN \| 33239 \| v2.2.0` | `6.1.118-android14-OP-WILD` | YES | YES |
| A16 / 6.1.118 | `android14-6.1.118 \| A16 \| KSUN \| 33239 \| v2.2.0` | `6.1.118-android14-OP-WILD` | YES | YES |
| A15 / 6.1.75 | `android14-6.1.75 \| A15 \| KSUN \| 33239 \| v2.2.0` | `6.1.75-android14-OP-WILD` | YES | YES |

字符串证据（取自 `Image` 的 `.rodata`）：
- `CONFIG_KSU_SUSFS_SUS_MOUNT` + `v2.2.0` → SUSFS 已编入
- `KernelSU: hook_manager: escape to root for init executing ksud: %d` → KernelSU 已编入
- `susfs: enable logging to kernel` / `susfs:[%u][%d][%s] ...` → SUSFS 运行期日志钩子就位
- `Linux version 6.1.xxx-android14-OP-WILD (OnePlus@ubuntu-build)` → 内核版本正确

> 注：KSU 版本号 `33239` 以整数常量形式存在于内核，不是字符串，因此二进制里搜不到该字符串；它由构建日志 `KSUVER: 33239` 与设备清单文件确认。

---

## 5. 构建日志关键证据

```
KSUVER: 33239
SusFS Version: v2.2.0
KERNEL_FULL_VER: android14-6.1.141
```

**补丁链按预期工作**（SUSFS 的 `.rej` 恰好 6 个，与 6 个 fix 补丁一一对应）：
```
1 out of 2 hunks FAILED -- saving rejects to file kernel/Kbuild.rej
6 out of 8 hunks FAILED -- saving rejects to file kernel/core/init.c.rej
1 out of 1 hunk  FAILED -- saving rejects to file kernel/feature/kernel_umount.c.rej
2 out of 5 hunks FAILED -- saving rejects to file kernel/feature/sucompat.c.rej
1 out of 2 hunks FAILED -- saving rejects to file kernel/hook/setuid_hook.c.rej
1 out of 1 hunk  FAILED -- saving rejects to file kernel/supercall/supercall.c.rej

Patching file: setuid_hook.c  with fix_setuid_hook.c.patch
Patching file: sucompat.c     with fix_sucompat.c.patch
Patching file: kernel_umount.c with fix_kernel_umount.c.patch
Patching file: supercall.c    with fix_supercall.c.patch
Patching file: init.c         with fix_init.c.patch
Patching file: Kbuild         with fix_Kbuild.patch
Patching Hook Mode!
Patching KSU_TOOLKIT Support for SusFS kernel!
```

**ccache 收尾正常**（此前失败的 `cp: cannot stat ''` 已消失）：
```
📊 ccache Post-Build Statistics
Cacheable calls:   3246 / 4872 (66.63%)
ccache Hit Rate: 5.0%
Archive created: cache-KSUN-v3-OP-ACE-3V-A16-android14-6.1.141-ed55f2a1.tzst (549767570 bytes)
```

**产物上传成功**：
```
Artifact AK3_OP-ACE-3V_A16_android14-6.1.141_KSUN_33239_SuSFS_v2.2.0.zip has been successfully uploaded!
Final size is 18731430 bytes. Artifact ID is 11683194788
```

**ccache 缓存已落盘**（Release `ccache-cache`，4 个资产 ≈ 2.18 GB）：
| 资产 | 大小 |
|---|---|
| `cache-KSUN-v3-OP-ACE-3V-A16-android14-6.1.141-ed55f2a1.tzst` | 549,767,570 B |
| `cache-KSUN-v3-OP-ACE-3V-6.1.118-A16-android14-6.1.118-cc77dd91.tzst` | 547,688,588 B |
| `cache-KSUN-v3-OP-ACE-3V-A15-android14-6.1.118-ed55f2a1.tzst` | 545,058,034 B |
| `cache-KSUN-v3-OP-ACE-3V-6.1.75-A15-android14-6.1.75-7b13d290.tzst` | 538,096,327 B |

缓存命中后，后续同设备构建会显著加速。

---

## 6. 本次修复的三个根因

| # | 现象 | 根因 | 修复 |
|---|---|---|---|
| 1 | `Unsupported SUSFS version: v2.3.0` | 上游 `kernel_patches/next/susfs_fix_patches` 只到 `v2.2.0`；susfs4ksu `gki-*` 分支 2026-08-30 升到 v2.3.0 | SUSFS 钉到 2026-08-11 的提交（与 KSUN 33239 严格配对） |
| 2 | GitLab archive 下载 403（`aria2c` 失败、`curl` 成功同一 URL） | 伪造 Chrome UA 与 TLS 指纹不匹配，被 Cloudflare WAF 拦截 | `retry_fetch_archive()` 改为 **curl 默认 UA 优先 → `api/v4` 归档备用 → `aria2c` 兜底** |
| 3 | `ccache Post-Build Statistics` 报 `cp: cannot stat ''` | `CCACHE_LOGFILE` 由**调用方 workflow** 提供，本 workflow 漏设，`action.yml` 中 `cp "${{ env.CCACHE_LOGFILE }}"` 展开为空 | 在 `Configure ccache` 步骤补 `CCACHE_LOG` / `CCACHE_LOGFILE` |
| 4 | `Failed to upload cache-...tzst` | `cache/save` 在 tag 不存在时用 GITHUB_TOKEN（GitHub App token，无 `workflows` 权限）推新 tag → 被拒 → 落入 `else` 分支但 release 从未创建 | 预先创建 `ccache-cache` tag + Release，使 runner 内 `git rev-parse` 直接命中、跳过推送 |

---

## 7. 版本配对（可复现基线）

| 组件 | 引用 | 值 |
|---|---|---|
| KernelSU-Next | `234f6e040fcbca18b16d2398e1aa225712ec99ad` | KSUN **33239** |
| SUSFS（android14-6.1） | `e287d5906638` | **v2.2.0** |
| SUSFS（android15-6.6） | `be7b7ef49a1e` | v2.2.0 |
| SUSFS（android16-6.12） | `f37930f374ef` | v2.2.0 |
| SUSFS（android13-5.15） | `ccb1918684b2` | v2.2.0 |
| SUSFS（android14-5.15） | `0463ac089308` | v2.2.0 |
| SUSFS（android13-5.10） | `f81aaf10e956` | v2.2.0 |
| SUSFS（android12-5.10） | `3c14ad549f82` | v2.2.0 |

---

## 8. 复现方式

在 GitHub 网页上：**Actions → Build OnePlus Kernel (KernelSU-Next + SUSFS) → Run workflow**

| 输入 | 值 |
|---|---|
| `device` | `ACE3v` |
| `android_version` | `auto` |
| `ksu_ref` | `234f6e040fcbca18b16d2398e1aa225712ec99ad` |
| `susfs_ref` | `auto` |
| `optimize_level` | `O2` |
| `clean_build` | `false` |
| `make_release` | `false`（想长期保存/分享则改 `true`） |
| `list_only` | `false` |
| `debug` | `false` |

命令行等价（需 GitHub Token）：
```bash
python opbuild.py --device ACE3v --android-version auto \
  --ksu-ref 234f6e040fcbca18b16d2398e1aa225712ec99ad \
  --susfs-ref auto --optimize-level O2
```

---

## 9. 刷入说明

1. 确认手机内核版本与包名中的 `android14-6.1.xxx` **完全一致**（设置 → 关于手机 → 内核版本）。
2. 已解锁 Bootloader，并已安装 KernelSU Manager。
3. 用 KernelSU Manager 的「安装」→ 选择「未安装 / 修补 boot 镜像」→ 选用本 zip；或在 TWRP 中直接刷入 zip。
4. 首次刷入后重启，在 KernelSU Manager 里应显示已安装版本 **33239**。

> 本包 `do.devicecheck=0`，不做机型强校验；刷错版本的内核可能导致无法开机，请务必核对 `android14-6.1.xxx`。

---

# 附：source 模式验证（SUSFS v2.3.0 源码直编，2026-10-12）

**结论：source 模式完整链路跑通，4 个 AK3 包全部产出，SUSFS v2.3.0 确认编进内核。**

| 项目 | 值 |
|---|---|
| Run ID | `38166593478` |
| 触发/完成时间 | 2026-10-11T19:06:14Z → 19:20:52Z（约 15 分钟） |
| 最终状态 | **completed / success** |
| 参数 | `device=ACE3v` / `susfs_mode=source` / `ksu_ref=auto` / `susfs_ref=auto` |
| KSUN 解析值 | `dev-susfs` → `188cf08dae644d6ede3806c258b7af11d36dca93`（`pershoot/KernelSU-Next`） |
| SUSFS 解析值 | `fb0f1f7dd768`（`gitlab.com/pershoot/susfs4ksu` 的 `gki-android14-6.1-dev` 分支头） |
| KSUN 版本号 | **33348**（pershoot fork rev-list 计数，与官方 33239 不同属预期） |

## A. 关键日志实证（4 个 build job：114550344589 / 114550344652 / 114550344658 / 114550344686，逐一下载日志核对）

4/4 job 运行时均输出：
- `SusFS Version: v2.3.0`
- `ksu_resolved_hash=188cf08dae644d6ede3806c258b7af11d36dca93`、`susfs_resolved_hash=fb0f1f7dd768`
- `KSUN 侧集成由 pershoot dev-susfs 内置提供：跳过 10_enable_susfs_for_ksu.patch / next/susfs_fix_patches`
- `50_add_susfs_in_gki-android14-6.1.patch` 全部 hunk succeeded（含 offset/fuzz），各 job 日志 `saving rejects` 计数均 **0**
- `CONFIG_KSU_SUSFS=y` 及 11 个 `CONFIG_KSU_SUSFS_*` defconfig 项写入

## B. 产物清单（4 个 AK3 包，均 KSUN_33348 + SuSFS_v2.3.0）

| 文件名 | 大小 | SHA-256 |
|---|---|---|
| `AK3_OP-ACE-3V_A15_android14-6.1.118_KSUN_33348_SuSFS_v2.3.0.zip` | 18,732,646 B | `6d06b3e77c49781f511a61035fde65bf477360ebdcb3cf86b80901021dfe814c` |
| `AK3_OP-ACE-3V_A16_android14-6.1.118_KSUN_33348_SuSFS_v2.3.0.zip` | 18,712,381 B | `6b2c36bdf726e264b2531333a0f17163928144931da12bb496bcef278ea26e6c` |
| `AK3_OP-ACE-3V_A16_android14-6.1.141_KSUN_33348_SuSFS_v2.3.0.zip` | 18,751,519 B | `105971ac88172f47e1e8858ae34430006617e2ce611a7fd404f63b438f5d0d7f` |
| `AK3_OP-ACE-3V_A15_android14-6.1.75_KSUN_33348_SuSFS_v2.3.0.zip` | 18,522,149 B | `2b64b1cdda1d5cb465c166f58bdaeed9bffa1b808020a8c9452d19c8ffd34750` |

下载地址：https://github.com/jiangsl1303/OnePlus_WILD_KernelSU/actions/runs/38166593478

## C. 内核镜像实证（6.1.118 / A15 包）

解开 zip 中的 `Image`（38,283,776 B，ARM64 magic `4d5a40fa`），直接命中字符串：
`susfs`、`SuSFS`、`sus_path`、`try_umount`、`spoof_uname`、`ksu_selinux_hide`
——SUSFS v2.3.0 特性开关与 pershoot KSUN 侧 `selinux_hide` 集成均在二进制中，即确证编入内核而非外壳标注。

## D. 刷入说明（source 模式）

与第 9 节相同，注意：① 核对内核 `android14-6.1.xxx` 与包名一致；② 已验证 KSUN 版本显示 **33348**；③ source 模式 SUSFS 已在内核内，**无需再刷 LKM 模块**。
