#!/usr/bin/env python3
#
# Misc utilties for working with RPi config.txt files
#
# Copyright (c) 2018 sakaki <sakaki@deciban.com>
# License: GPL v3+
# NO WARRANTY

import re, os, subprocess, shutil
from tempfile import mktemp
from pathlib import Path

def app_name():
    return("pyconfig_gen")

def setup_tmpfile_copy(path):
    if not Path(path).is_file():
        os.mknod(path) # touch
    f = mktemp()
    shutil.copyfile(path, f)
    return f

def make_real_user_owned(path):
    # revert given path to real owner, so
    # we can create e.g. config files in the
    # user's directory
    uid = os.getenv("SUDO_UID") or 0
    gid = os.getenv("SUDO_GID") or 0
    os.chown(path, int(uid), int(gid))

def set_config_var(key, value, path, check_first = True, int_cast = True):
    made_change = False
    tmp_path = path + ".bak"
    req = "?" if "=" in key else ""
    assign = "" if "=" in key else "="
    # avoid unnecessary writes to filesystemkey, value, path, check_first, int_cast)
    if check_first and get_config_var(key, path, int_cast = int_cast) == value:
        return
    find_key=re.compile(f"#?\s*{key}[=,]{req}.*$")
    find_uncommented_key=re.compile(f"\s*{key}[=,]{req}.*$")
    def_line = f"{key}{assign}{value}\n"
    try:
        with open(path, "r") as in_file:
            with open(tmp_path, "w+") as out_file:
                for line in in_file:
                    if find_key.match(line):
                        if not made_change:
                            line = def_line
                            made_change = True
                        elif find_uncommented_key.match(line):
                            # subsequent uncommented definition of key
                            # comment this out
                            line = f"#{line}"
                    print(line, end="", file=out_file)
                if not made_change:
                    # got to end without finding key, so set it now
                    print(def_line, end="", file=out_file)
        # commit changes atomically
        shutil.move(tmp_path, path)
    finally:
        # ensure bak copy of file isn't left around
        if  Path(tmp_path).is_file():
            os.remove(tmp_path)

def get_config_var(key, path, default = None, int_cast = True):
    # default is returned if key not defined or cast fails
    req = "?" if "=" in key else ""
    find_uncommented_key=re.compile(f"\s*{key}[=,]{req}([^\n]*)$")
    with open(path, "r") as in_file:
        for line in in_file:
            m  = find_uncommented_key.match(line)
            if m:
                v = m.group(1)
                if int_cast:
                    try:
                        v = int(v)
                    except (TypeError, ValueError):
                        v = default
                return(v)
    return(default)

def comment_config_var(key, path, check_first = True):
    tmp_path = path + ".bak"
    req = "?" if "=" in key else ""
    find_uncommented_key=re.compile(f"\s*{key}[=,]{req}.*$")
    # avoid unnecessary writes to filesystem
    if check_first and not config_var_defined(key, path):
        return
    try:
        with open(path, "r") as in_file:
            with open(tmp_path, "w+") as out_file:
                for line in in_file:
                    if find_uncommented_key.match(line):
                        line = f"#{line}"
                    print(line, end="", file=out_file)
        # commit changes atomically
        shutil.move(tmp_path, path)
    finally:
        # ensure bak copy of file isn't left around
        if Path(tmp_path).is_file():
            os.remove(tmp_path)

def config_var_defined(key, path):
    # return False if key absent or commented out (all instances) in config
    req = "?" if "=" in key else ""
    find_uncommented_key=re.compile(f"\s*{key}={req}.*$")
    with open(path, "r") as in_file:
        for line in in_file:
            if find_uncommented_key.match(line):
                return(True)
    return(False)


def set_or_comment_config_var(key, value, default, path, check_first = True):
    # comment given key if value is default, otherwise set it
    if value is None or value == default:
        comment_config_var(key, path, check_first)
    else:
        set_config_var(key, value, path, check_first)

def config_files_differ_materially(path1, path2, print_debug = False):
    # return True iff sorted, space-stripped non-commment lines differ
    find_uncommented_key=re.compile("([^#])\s*([^=,]+[=,][^\n]*)\s*$")
    active_lines1 = []
    active_lines2 = []
    with open(path1, "r") as in_file1:
        for line in in_file1:
           m = find_uncommented_key.match(line)
           if m:
               active_lines1 += [m.group(1).lstrip() + m.group(2)]
    with open(path2, "r") as in_file2:
        for line in in_file2:
           m = find_uncommented_key.match(line)
           if m:
               active_lines2 += [m.group(1).lstrip() + m.group(2)]
    active_lines1.sort()
    active_lines2.sort()
    if print_debug:
        print(active_lines1)
        print(active_lines2)
    return(active_lines1 != active_lines2)

CEA_FALLBACK_MODES = [
    ( 1,  640,  480, 60,  4,  3, False, False),
    ( 2,  720,  480, 60,  4,  3, False, False),
    ( 3,  720,  480, 60, 16,  9, False, False),
    ( 4, 1280,  720, 60, 16,  9, False, False),
    ( 5, 1920, 1080, 60, 16,  9, False, False),
    (16, 1920, 1080, 60, 16,  9, False, False),
]

CEA_FALLBACK_MODES_TXT = [
    f"{t[0]}: {t[1]}x{t[2]} {t[3]}Hz {t[4]}:{t[5]}" for t in CEA_FALLBACK_MODES
]

DMT_FALLBACK_MODES = [
    ( 4,  640,  480, 60,  4,  3, False, False),
    ( 9,  800,  600, 60,  4,  3, False, False),
    (16, 1024,  768, 60,  4,  3, False, False),
    (28, 1280,  800, 60, 16, 10, False, False),
    (32, 1280,  960, 60,  4,  3, False, False),
    (35, 1280, 1024, 60,  5,  4, False, False),
    (47, 1440,  900, 60, 16, 10, False, False),
    (51, 1600, 1200, 60,  4,  3, False, False),
    (58, 1680, 1050, 60, 16, 10, False, False),
    (82, 1920, 1080, 60, 16,  9, False, False),
    (85, 1280,  720, 60, 16,  9, False, False),
]

DMT_FALLBACK_MODES_TXT = [
    f"{t[0]}: {t[1]}x{t[2]} {t[3]}Hz {t[4]}:{t[5]}" for t in DMT_FALLBACK_MODES
]

def do_reboot():
    subprocess.run(['/sbin/reboot'])

def get_valid_modes(target, base_mode_txt, use_fake_data = False):
    find_modelines=re.compile("mode\s+(\d+):\s+(\d+)x(\d+)\s+@\s+(\d+)Hz\s+(\d+):(\d+),.*progressive")
    find_preferred=re.compile("prefer")
    find_native=re.compile("native")
    if use_fake_data and Path(f"/usr/share/{app_name()}/tvservice_output").is_dir():
        output= subprocess.run(["cat", f"/usr/share/{app_name()}/tvservice_output/{target.lower()}1.txt"],
                               stdout=subprocess.PIPE).stdout.decode('utf-8').splitlines()
    else:
        output= subprocess.run(["tvservice", "-m", target],
                               stdout=subprocess.PIPE).stdout.decode('utf-8').splitlines()
    valid_modes = []
    valid_modes_txt = []
    modes_found = 0
    for line in output:
        m = find_modelines.search(line)
        if m:
            is_preferred = find_preferred.search(line) is not None
            is_native = find_native.search(line) is not None
            valid_modes += [tuple([int(m.group(i)) for i in range(1,7)]) +
                            (is_preferred, is_native)]
            tags=""
            if is_preferred:
                tags += " (prefer)"
            if is_native:
                tags += " (native)"
            valid_modes_txt += [f"{m.group(1)}: {m.group(2)}x{m.group(3)} {m.group(4)}Hz {m.group(5)}:{m.group(6)}{tags}"]
            modes_found += 1
    return([(0, 0, 0, 0, 0, 0, False, False)] + valid_modes,
               [base_mode_txt] + valid_modes_txt)

def get_fallback_modes(target, base_mode_txt, use_fake_data = False):
    # generate a fallback list from the group, used when no
    # EDID preferences as to mode are available
    if target == "CEA":
        fallback_modes = CEA_FALLBACK_MODES
        fallback_modes_txt = CEA_FALLBACK_MODES_TXT
    else: # assume DMT
        fallback_modes = DMT_FALLBACK_MODES
        fallback_modes_txt = DMT_FALLBACK_MODES_TXT
    return([(0, 0, 0, 0, 0, 0, False, False)] + fallback_modes,
           [base_mode_txt] + fallback_modes_txt)
