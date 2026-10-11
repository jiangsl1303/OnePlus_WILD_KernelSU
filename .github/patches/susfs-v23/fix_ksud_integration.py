#!/usr/bin/env python3
"""
Fix ksud_integration.c for SUSFS v2.3.0 on KernelSU-Next (source mode).
- Add missing includes.
- Wrap old 2-arg ksu_handle_execveat_ksud into a 5-arg version (sucompat.c needs it).
- Inject ksu_stop_ksud_execve_hook & ksud_execve_key (original file
  hook/syscall_event_bridge.c was removed from Kbuild by SUSFS main patch).
"""
import sys

p = "kernel/runtime/ksud_integration.c"
with open(p, encoding="utf-8") as f:
    s = f.read()

# 1) includes
if 'hook/syscall_event_bridge.h' not in s:
    s = s.replace(
        '#include "feature/selinux_hide.h"\n',
        '#include "feature/selinux_hide.h"\n'
        '#include "hook/syscall_event_bridge.h"\n'
        '#include <linux/jump_label.h>\n',
        1,
    )

# 2) 5-arg wrapper for sucompat.c
OLD_DEF = 'void ksu_handle_execveat_ksud(const char *path, struct user_arg_ptr *argv)\n{'
if OLD_DEF in s:
    s = s.replace(
        OLD_DEF,
        'static void ksu_handle_execveat_ksud_path(const char *path, struct user_arg_ptr *argv)\n{',
        1,
    )
    wrapper = """
/* 5-arg wrapper: sucompat.c calls with 5 args */
int ksu_handle_execveat_ksud(int *fd, struct filename **filename_ptr,
                             struct user_arg_ptr *argv,
                             struct user_arg_ptr *envp, int *flags)
{
    (void)fd;
    (void)envp;
    (void)flags;
    if (!filename_ptr || !*filename_ptr || argv == NULL)
        return 0;
    ksu_handle_execveat_ksud_path((*filename_ptr)->name, argv);
    return 0;
}
"""
    s = s + wrapper

# 3) stop hook & key (original in hook/syscall_event_bridge.c, removed from Kbuild)
if 'ksu_stop_ksud_execve_hook' not in s:
    s = s + """
/* ksu_stop_ksud_execve_hook & ksud_execve_key (orig in hook/syscall_event_bridge.c) */
DEFINE_STATIC_KEY_TRUE(ksud_execve_key);

void ksu_stop_ksud_execve_hook(void)
{
    static_branch_disable(&ksud_execve_key);
}
"""

with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(s)
print("ksud_integration.c patched")
