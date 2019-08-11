#!/usr/bin/env python3
#
# Misc utilties for working with RPi config.txt files
#
# Copyright (c) 2018-19 sakaki <sakaki@deciban.com>
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

def parse_key(fullkey, prevfilt = "all"):
    # only switch filter for all, none or pi.*
    find_keysplit=re.compile(f"([^@]+)@([^@]+)")
    m = find_keysplit.match(fullkey)
    if m:
        return (m.group(1), m.group(2))
    else:
        return (fullkey, "all")

def set_config_var(qualified_key, value, path, check_first = True, int_cast = True):
    # you can qualify a key filter thus: "foo@pi4"; "foo" implies "foo@all"
    made_change = False
    (key, filt) = parse_key(qualified_key)
    current_filt = "all"
    tmp_path = path + ".bak"
    req = "?" if "=" in key else ""
    assign = "" if "=" in key else "="
    # avoid unnecessary writes to filesystemkey, value, path, check_first, int_cast)
    if check_first and get_config_var(qualified_key, path, int_cast = int_cast) == value:
        return
    find_key=re.compile(f"^#?\s*{key}[=,]{req}.*$")
    find_uncommented_key=re.compile(f"^\s*{key}[=,]{req}.*$")
    find_filter=re.compile(f"^\s*\[([^[]+)\]")
    def_line = f"{key}{assign}{value}\n"
    try:
        # record last line where the target filter is in scope
        # lines are indexed from 1
        lno = 0
        lng_lno = None
        with open(path, "r") as in_file:
            for line in in_file:
                lno += 1
                m = find_filter.match(line)
                if m:
                    f = m.group(1)
                    if f == "all" or f == "none" or f.find("pi") == 0:
                        if current_filt != f and current_filt == filt:
                            # no longer in the goal filter, so the
                            # previous line is the last in block
                            lng_lno = lno - 1
                        current_filt = f
        # deal with last line being a filter change, to the
        # one we want
        if current_filt == filt:
            lng_lno = lno
        # now run through and actually do the edit
        current_filt = "all"
        # now we look for the target tag; but if we haven't found
        # it by the time we get to line lng_lno, we insert it
        # immediately
        with open(path, "r") as in_file:
            with open(tmp_path, "w+") as out_file:
                lno = 0
                for line in in_file:
                    lno += 1
                    m = find_filter.match(line)
                    if m:
                        f = m.group(1)
                        if f == "all" or f == "none" or f.find("pi") == 0:
                            current_filt = f
                    elif current_filt != "none" and current_filt == filt and find_key.match(line):
                        if not made_change:
                            line = def_line
                            made_change = True
                        elif find_uncommented_key.match(line):
                            # subsequent uncommented definition of key
                            # comment this out
                            line = f"#{line}"
                    print(line, end="", file=out_file)
                    if not made_change and lno == lng_lno:
                        # at the end of the last block
                        # featuring this filter, so add now
                        print(def_line, end="", file=out_file)
                        made_change = True

                if not made_change:
                    # got to EOF without finding key, so set it now
                    if current_filt != filt :
                        # got to activate the group before adding anything
                        print(f"[{filt}]", file=out_file)
                    print(def_line, end="", file=out_file)

        # commit changes atomically
        shutil.move(tmp_path, path)
    finally:
        # ensure bak copy of file isn't left around
        if  Path(tmp_path).is_file():
            os.remove(tmp_path)

def get_config_var(qualified_key, path, default = None, int_cast = True):
    # default is returned if key not defined or cast fails
    (key, filt) = parse_key(qualified_key)
    current_filt = "all"
    req = "?" if "=" in key else ""
    find_uncommented_key=re.compile(f"^\s*{key}[=,]{req}([^\n]*)$")
    find_filter=re.compile(f"^\s*\[([^[]+)\]")
    in_subgroup = False
    with open(path, "r") as in_file:
        for line in in_file:
            m = find_filter.match(line)
            if m:
                f = m.group(1)
                if f == "all" or f == "none" or f.find("pi") == 0:
                    current_filt = f
                    continue
            if current_filt == "none":
                continue
            if current_filt == filt:
                # in the correct section, look for a key match
                m = find_uncommented_key.match(line)
                if m:
                    v = m.group(1)
                    if int_cast:
                        try:
                            v = int(v)
                        except (TypeError, ValueError):
                            v = default
                    return(v)
    return(default)

def comment_config_var(qualified_key, path, check_first = True):
    (key, filt) = parse_key(qualified_key)
    current_filt = "all"
    tmp_path = path + ".bak"
    req = "?" if "=" in key else ""
    find_uncommented_key=re.compile(f"^\s*{key}[=,]{req}.*$")
    find_filter=re.compile(f"^\s*\[([^[]+)\]")
    # avoid unnecessary writes to filesystem
    if check_first and not config_var_defined(qualified_key, path):
        return
    try:
        with open(path, "r") as in_file:
            with open(tmp_path, "w+") as out_file:
                for line in in_file:
                    m = find_filter.match(line)
                    if m:
                        f = m.group(1)
                        if f == "all" or f == "none" or f.find("pi") == 0:
                            current_filt = f
                    elif current_filt == filt and find_uncommented_key.match(line):
                            line = f"#{line}"
                    print(line, end="", file=out_file)
        # commit changes atomically
        shutil.move(tmp_path, path)
    finally:
        # ensure bak copy of file isn't left around
        if Path(tmp_path).is_file():
            os.remove(tmp_path)

def config_var_defined(qualified_key, path):
    (key, filt) = parse_key(qualified_key)
    current_filt = "all"
    # return False if key absent or commented out (all instances) in config
    req = "?" if "=" in key else ""
    find_uncommented_key=re.compile(f"^\s*{key}={req}.*$")
    find_filter=re.compile(f"^\s*\[([^[]+)\]")
    in_subgroup = False
    with open(path, "r") as in_file:
        for line in in_file:
            m = find_filter.match(line)
            if m:
                f = m.group(1)
                if f == "all" or f == "none" or f.find("pi") == 0:
                    current_filt = f
            elif current_filt != "none" and current_filt == filt:
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
    find_uncommented_key=re.compile("^\s*([^#=,]+)([=,][^\n]*)\s*$")
    find_filter=re.compile(f"^\s*\[([^[]+)\]")
    current_filt="all"
    in_subgroup = False
    active_lines1 = []
    active_lines2 = []
    with open(path1, "r") as in_file1:
        for line in in_file1:
            m = find_filter.match(line)
            if m:
                f = m.group(1)
                if f == "all" or f == "none" or f.find("pi") == 0:
                    current_filt = f
                    continue
            if current_filt == "none":
                continue
            m = find_uncommented_key.match(line)
            if m:
                active_lines1 += [m.group(1).lstrip() + "@" + current_filt + m.group(2)]
    current_filt = "all"
    with open(path2, "r") as in_file2:
        for line in in_file2:
            m = find_filter.match(line)
            if m:
                f = m.group(1)
                if f == "all" or f == "none" or f.find("pi") == 0:
                    current_filt = f
                    continue
            if current_filt == "none":
                continue
            m = find_uncommented_key.match(line)
            if m:
                active_lines2 += [m.group(1).lstrip() + "@" + current_filt + m.group(2)]
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
    (14,  848,  480, 60, 16,  9, False, False),
    (16, 1024,  768, 60,  4,  3, False, False),
    (23, 1280,  768, 60, 15,  9, False, False),
    (28, 1280,  800, 60, 16, 10, False, False),
    (32, 1280,  960, 60,  4,  3, False, False),
    (35, 1280, 1024, 60,  5,  4, False, False),
    (39, 1360,  768, 60, 16,  9, False, False),
    (42, 1400, 1050, 60,  4,  3, False, False),
    (47, 1440,  900, 60, 16, 10, False, False),
    (51, 1600, 1200, 60,  4,  3, False, False),
    (58, 1680, 1050, 60, 16, 10, False, False),
    (62, 1792, 1344, 60,  4,  3, False, False),
    (65, 1856, 1392, 60,  4,  3, False, False),
    (69, 1920, 1200, 60, 16, 10, False, False),
    (73, 1920, 1440, 60,  4,  3, False, False),
    (77, 2560, 1600, 60, 16, 10, False, False),
    (81, 1366,  768, 60, 16,  9, False, False),
    (82, 1920, 1080, 60, 16,  9, False, False),
    (85, 1280,  720, 60, 16,  9, False, False),
]

DMT_FALLBACK_MODES_TXT = [
    f"{t[0]}: {t[1]}x{t[2]} {t[3]}Hz {t[4]}:{t[5]}" for t in DMT_FALLBACK_MODES
]

def do_reboot():
    subprocess.run(['/sbin/reboot'])

def get_valid_modes(target, base_mode_txt, use_fake_data = False, hdmi_index = 0):
    find_modelines=re.compile("mode\s+(\d+):\s+(\d+)x(\d+)\s+@\s+(\d+)Hz\s+(\d+):(\d+),.*progressive")
    find_preferred=re.compile("prefer")
    find_native=re.compile("native")
    find_display=re.compile(f"Display Number (\d+), type HDMI {hdmi_index}")
    
    # we begin by finding the HDMI display number corresponding to the given index
    if use_fake_data and Path(f"/usr/share/{app_name()}/tvservice_output").is_dir():
        output= subprocess.run(["cat", f"/usr/share/{app_name()}/tvservice_output/list.txt"],
                               stdout=subprocess.PIPE).stdout.decode('utf-8')
    else:
        output= subprocess.run(["tvservice", "-l"],
                               stdout=subprocess.PIPE).stdout.decode('utf-8')
    m = find_display.search(output)
    if m:
        device_id = int(m.group(1))
    else:
        device_id = 999
    if use_fake_data and Path(f"/usr/share/{app_name()}/tvservice_output").is_dir():
        output= subprocess.run(["cat", f"/usr/share/{app_name()}/tvservice_output/{target.lower()}{hdmi_index}.txt"],
                               stdout=subprocess.PIPE).stdout.decode('utf-8').splitlines()
    else:
        output= subprocess.run(["tvservice", "-v", str(device_id), "-m", target],
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

def get_fallback_modes(target, base_mode_txt, use_fake_data = False, hdmi_index = 0):
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

def get_wifi_country_list():
    country_list=["00: World (Not Recommended)"]
    find_listing=re.compile(f"^([A-Z][A-Z])\s+(.*)$")
    with open("/usr/share/zoneinfo/iso3166.tab", "r") as in_file1:
        for line in in_file1:
            m = find_listing.match(line)
            if m:
                country_list += [m.group(1) + ": " + m.group(2)]
    return country_list

def pid_of_process(pname):
    ret = subprocess.run(["pgrep", "-x", pname],
                               stdout=subprocess.PIPE)
    if ret.returncode == 1:
        return 0
    else:
        return(int(ret.stdout.decode('utf-8').splitlines()[0]))

def run_command_as(cmd, uid, gid, other_groups=[], env=None):
    def demote_user():
        os.setgid(gid)
        os.setgroups(other_groups)
        os.setuid(uid)
    if env is None:
        p = subprocess.Popen(cmd, preexec_fn=demote_user, shell=False)
    else:
        p = subprocess.Popen(cmd, preexec_fn=demote_user, shell=False, env=env)

def bring_window_to_front(pid):
    subprocess.run("wmctrl -ia $(wmctrl -lp | awk -vpid=" + str(pid) + \
                   " '$3==pid {print $1; exit}')",
                   shell=True)
