#!/usr/bin/env python3
#
# Simple configuration settings app for the RPi
#
# Copyright (c) 2018-19 sakaki <sakaki@deciban.com>
# License: GPL v3+
# NO WARRANTY

import sys, os, re, shutil, time, subprocess, pwd
from PyQt5 import QtCore
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QDialog, QWidget, QPushButton
from PyQt5.QtWidgets import QMessageBox, QDialogButtonBox, QButtonGroup
from PyQt5.QtGui import QIcon
from pyconfig_gen.pyconfig_gen_dialog import Ui_MainDialog
from pyconfig_gen.config_utils import *

CONFIG_PATHNAME = "/boot/config.txt"
CONFIG_LNG_PATHNAME = "/boot/config.txt.lng"
CONFIG_TBC_PATHNAME = "/boot/config.txt.tbc"
CONFIG_REJ_PATHNAME = "/boot/config.txt.rej"
CONFIG_OLD_PATHNAME = "/boot/config.txt.old"
WIFI_REGDOM_PATHNAME = "/etc/conf.d/rpi3-wifi-regdom"
WIFI_MODPROBE_PATHNAME = "/etc/modprobe.d/rpi3-wifi-regdom.conf"

HDMI_BASE_MODE_TXT = "Auto-detect from EDID"
BREAK_REBOOT_NOTIFIED = "break_reboot_notified"
BASE_TITLE = "RPi Configuration"
SAVE_NEEDED = " (Unsaved Changes)"
CMAS = [256, 192, 128, 96, 64, 0]
GPUS = [256, 192, 128, 96, 64, 32, 16, 0]


class TimeoutMessageBox(QMessageBox):
    def __init__(self, timeout_secs = 3, parent = None,
                 which_display_button = QMessageBox.Yes,
                 display_button_suffix = "f\" in {self.time_to_wait}s\""):
        super(TimeoutMessageBox, self).__init__(parent)
        self.time_to_wait = timeout_secs
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1000) # 1s
        self.timer.timeout.connect(self.on_tick)
        self.which_display_button = which_display_button
        self.display_button_text = None
        self.display_button = None
        self.display_button_suffix = display_button_suffix

    def on_tick(self):
        if self.display_button is None:
            self.display_button = self.button(self.which_display_button)
            self.display_button_base_text = self.display_button.text()
        if not self.timer.isActive():
            self.timer.start()
        self.display_button.setText(
            self.display_button_base_text + eval( self.display_button_suffix ) )
        if self.time_to_wait <= 0:
            self.close()
        else:
            self.time_to_wait -= 1

    def closeEvent(self, event):
        self.timer.stop()
        event.accept()


class MainDialog(QDialog):

    allow_reboot = False
    use_fake_data = False
    is_autostart = False

    tmp_pathname = None
    hdmi_safe = None
    hdmi_group = None
    dtoverlay_vc4 = None
    hdmi_force_hotplug = None
    hdmi_ignore_edid = None
    config_hdmi_boost = None
    disable_overscan = None
    cma_vc4 = None
    gpu_vc4 = None
    overscan_left = None
    overscan_right = None
    overscan_top = None
    overscan_bottom = None
    hdmi_force_edid_audio = None
    hdmi_drive = None
    dtparam_spi = None
    dtparam_i2c = None
    dtparam_i2s = None
    dtparam_audio = None
    dtoverlay_disable_bt = None
    dtparam_camera = None

    valid_cea_modes = []
    valid_cea_modes_txt = []
    valid_dmt_modes = []
    valid_dmt_modes_txt = []
    valid_modes = None
    valid_modes_txt = None
    in_update = False
    dirty = False
    reset_b = None
    cancel_b = None
    ok_b = None
    using_fallback_hdmi_data = None
    save_lng = True
    first_run = False

    hdmi_safe1 = None
    hdmi_group1 = None
    hdmi_force_hotplug1 = None
    hdmi_ignore_edid1 = None
    config_hdmi_boost1 = None
    disable_overscan1 = None
    overscan_left1 = None
    overscan_right1 = None
    overscan_top1 = None
    overscan_bottom1 = None
    hdmi_force_edid_audio1 = None
    hdmi_drive1 = None

    valid_cea_modes1 = []
    valid_cea_modes_txt1 = []
    valid_dmt_modes1 = []
    valid_dmt_modes_txt1 = []
    valid_modes1 = None
    valid_modes_txt1 = None
    using_fallback_hdmi_data1 = None
    original_uid = None
    original_gid = None
    original_home = None
    original_path = None
    original_display = None

    country_list = None
    tmp_regdom_pathname = None
    wifi_regdom = None

    overclock_bg = None
    overclock_level = None


    # utilities -----------------------------------------------------

    def make_tmp_copy_of_config(self):
        self.tmp_pathname=setup_tmpfile_copy(CONFIG_PATHNAME)
        self.tmp_regdom_pathname=setup_tmpfile_copy(WIFI_REGDOM_PATHNAME)

    def cleanup_tmp_copy_of_config(self):
        if self.tmp_pathname:
            if os.path.exists(self.tmp_pathname):
                os.remove(self.tmp_pathname)
            bak_pathname = f"{self.tmp_pathname}.bak"
            if os.path.exists(bak_pathname):
                os.remove(bak_pathname)
        if self.tmp_regdom_pathname:
            if os.path.exists(self.tmp_regdom_pathname):
                os.remove(self.tmp_regdom_pathname)

    def sys_exit(self, retval = 0):
        self.cleanup_tmp_copy_of_config()
        sys.exit(retval)

    # state management ----------------------------------------------

    def populate_state_from_config(self, is_initial = False):
        find_vc4_and_cma=re.compile("([^,\s]+)\s*,?\s*(cma-(\d+))?")
        v = get_config_var("hdmi_safe", self.tmp_pathname, 0)
        self.hdmi_safe = (v == 1)
        v = get_config_var("hdmi_safe:1@pi4", self.tmp_pathname, 0)
        self.hdmi_safe1 = (v == 1)
        v = get_config_var("hdmi_group", self.tmp_pathname, 0)
        # assume default if undefined
        self.hdmi_group = v if 0 <= v <= 2 else 0
        v = get_config_var("hdmi_group:1@pi4", self.tmp_pathname, 0)
        # assume default if undefined
        self.hdmi_group1 = v if 0 <= v <= 2 else 0
        v = get_config_var("hdmi_mode", self.tmp_pathname, 0)
        # assume default if undefined
        self.hdmi_mode = v if (self.hdmi_group == 1 and 0 <= v <= 59) or \
            (self.hdmi_group == 2 and 0 <= v <= 86) else 0
        v = get_config_var("hdmi_mode:1@pi4", self.tmp_pathname, 0)
        # assume default if undefined
        self.hdmi_mode1 = v if (self.hdmi_group1 == 1 and 0 <= v <= 59) or \
            (self.hdmi_group1 == 2 and 0 <= v <= 86) else 0
        v = get_config_var("dtoverlay=vc4-", self.tmp_pathname,
                           "", False)
        m = find_vc4_and_cma.match(v)
        if m:
            if m.group(1) == "fkms-v3d":
                self.dtoverlay_vc4 = 0
            elif m.group(1) == "kms-v3d":
                self.dtoverlay_vc4 = 1
            else:
                self.dtoverlay_vc4 = 2
            try:
                self.cma_vc4 = CMAS.index(int(m.group(3)))
            except (ValueError, TypeError):
                self.cma_vc4 = CMAS.index(0)
        else:
            self.dtoverlay_vc4 = 2
            self.cma_vc4 = CMAS.index(0)
        v = get_config_var("gpu_mem", self.tmp_pathname, 9999)
        try:
            self.gpu_vc4 = GPUS.index(v)
        except (ValueError, TypeError):
            self.gpu_vc4 = GPUS.index(0)
        v = get_config_var("hdmi_force_hotplug", self.tmp_pathname, 0)
        self.hdmi_force_hotplug = v == 1
        v = get_config_var("hdmi_force_hotplug:1@pi4", self.tmp_pathname, 0)
        self.hdmi_force_hotplug1 = v == 1
        v = get_config_var("hdmi_ignore_edid", self.tmp_pathname,
                           None, False)
        self.hdmi_ignore_edid = v is not None and v.lower() == "0xa5000080"
        v = get_config_var("hdmi_ignore_edid:1@pi4", self.tmp_pathname,
                           None, False)
        self.hdmi_ignore_edid1 = v is not None and v.lower() == "0xa5000080"
        v = get_config_var("config_hdmi_boost", self.tmp_pathname, 5)
        self.config_hdmi_boost = v
        v = get_config_var("config_hdmi_boost:1@pi4", self.tmp_pathname, 5)
        self.config_hdmi_boost1 = v
        v = get_config_var("disable_overscan", self.tmp_pathname, 0)
        self.disable_overscan = v == 1
        v = get_config_var("disable_overscan:1@pi4", self.tmp_pathname, 0)
        self.disable_overscan1 = v == 1
        v = get_config_var("overscan_left", self.tmp_pathname, 0)
        self.overscan_left = v
        v = get_config_var("overscan_right", self.tmp_pathname, 0)
        self.overscan_right = v
        v = get_config_var("overscan_top", self.tmp_pathname, 0)
        self.overscan_top = v
        v = get_config_var("overscan_bottom", self.tmp_pathname, 0)
        self.overscan_bottom = v
        v = get_config_var("overscan_left:1@pi4", self.tmp_pathname, 0)
        self.overscan_left1 = v
        v = get_config_var("overscan_right:1@pi4", self.tmp_pathname, 0)
        self.overscan_right1 = v
        v = get_config_var("overscan_top:1@pi4", self.tmp_pathname, 0)
        self.overscan_top1 = v
        v = get_config_var("overscan_bottom:1@pi4", self.tmp_pathname, 0)
        self.overscan_bottom1 = v
        v = get_config_var("hdmi_force_edid_audio", self.tmp_pathname, 0)
        self.hdmi_force_edid_audio = v == 1
        v = get_config_var("hdmi_force_edid_audio:1@pi4", self.tmp_pathname, 0)
        self.hdmi_force_edid_audio1 = v == 1
        v = get_config_var("hdmi_drive", self.tmp_pathname, 1)
        self.hdmi_drive = v
        v = get_config_var("hdmi_drive:1@pi4", self.tmp_pathname, 1)
        self.hdmi_drive1 = v
        v = get_config_var("dtparam=spi=", self.tmp_pathname,
                           None, False)
        self.dtparam_spi = True if v and "on" in v else False
        v = get_config_var("dtparam=i2c_arm=", self.tmp_pathname,
                           None, False)
        self.dtparam_i2c = True if v and "on" in v else False
        v = get_config_var("dtparam=i2s=", self.tmp_pathname,
                           None, False)
        self.dtparam_i2s = True if v and "on" in v else False
        v = get_config_var("dtparam=audio=", self.tmp_pathname,
                           None, False)
        self.dtparam_audio = True if v and "on" in v else False
        v = get_config_var("dtoverlay=pi3-disable-bt", self.tmp_pathname,
                           None, False)
        self.dtoverlay_disable_bt = v is not None
        v = get_config_var("start_x", self.tmp_pathname, 0)
        self.dtparam_camera = v == 1

        force_turbo = max(get_config_var("force_turbo", self.tmp_pathname, 0),
                          get_config_var("force_turbo@pi4", self.tmp_pathname, 0))
        arm_freq = get_config_var("arm_freq@pi4", self.tmp_pathname, 1500)
        gpu_freq = get_config_var("gpu_freq@pi4", self.tmp_pathname, 500)
        over_voltage = get_config_var("over_voltage@pi4", self.tmp_pathname, 0)
        # infer the overclock level
        self.overclock_level = 4
        if force_turbo == 0:
            if arm_freq == 1500 and gpu_freq == 500 and over_voltage == 0:
                self.overclock_level = 0
            elif arm_freq == 1750 and gpu_freq == 500 and over_voltage == 2:
                self.overclock_level = 1
            elif arm_freq == 1750 and gpu_freq == 600 and over_voltage == 4:
                self.overclock_level = 2
            elif arm_freq == 2000 and gpu_freq == 600 and over_voltage == 6:
                self.overclock_level = 3
        
        # WiFi status
        v = get_config_var("WIFI_REGDOM", self.tmp_regdom_pathname,
                           None, False)
        v = v.replace('"', '')
        v = v.replace("'", "")
        self.wifi_regdom = v
        
    def dirty_check(self):
        if config_files_differ_materially(self.tmp_pathname, CONFIG_PATHNAME,
                                          print_debug = self.use_fake_data) or \
           config_files_differ_materially(self.tmp_regdom_pathname, WIFI_REGDOM_PATHNAME,
                                       print_debug = self.use_fake_data):
            self.setWindowTitle(BASE_TITLE + SAVE_NEEDED)
            self.dirty = True
        else:
            self.setWindowTitle(BASE_TITLE)
            self.dirty = False
        if self.dirty:
            self.reset_b.setEnabled(True)
            self.ok_b.setEnabled(True)
        else:
            self.reset_b.setEnabled(False)
            self.ok_b.setEnabled(False)

    def populate_gui_from_state(self, is_initial = False):
        self.ui.graphics_driver_cb.setCurrentIndex(self.dtoverlay_vc4)
        self.ui.cma_cb.setCurrentIndex(self.cma_vc4)
        self.ui.gpu_cb.setCurrentIndex(self.gpu_vc4)
        self.ui.cma_cb.setEnabled(0 <= self.dtoverlay_vc4 <= 1)
        self.ui.safe_mode_rb.setChecked(self.hdmi_safe)
        self.ui.safe_mode1_rb.setChecked(self.hdmi_safe1)
        self.ui.normal_mode_rb.setChecked(not self.hdmi_safe)
        self.ui.normal_mode_gb.setEnabled(not self.hdmi_safe)
        self.ui.normal_mode1_rb.setChecked(not self.hdmi_safe1)
        self.ui.normal_mode1_gb.setEnabled(not self.hdmi_safe1)
        self.ui.hdmi_group_cb.setCurrentIndex(self.hdmi_group)
        self.ui.hdmi_group1_cb.setCurrentIndex(self.hdmi_group1)
        self.ui.hdmi_mode_cb.setEnabled(self.hdmi_group > 0)
        self.ui.hdmi_mode1_cb.setEnabled(self.hdmi_group1 > 0)
        self.ui.hdmi_group_cb.setCurrentIndex(self.hdmi_group)
        self.ui.hdmi_group1_cb.setCurrentIndex(self.hdmi_group1)
        self.ui.overscan_gb.setChecked(not self.disable_overscan)
        self.ui.overscan1_gb.setChecked(not self.disable_overscan1)
        # ensure dialog populated
        if is_initial:
            self.hdmi_group_changed(self.hdmi_group)
            self.hdmi_group1_changed(self.hdmi_group1)
        ix = [i for i, j in enumerate(self.valid_modes) if j[0] == self.hdmi_mode]
        if ix:
            self.ui.hdmi_mode_cb.setCurrentIndex(ix[0])
        else:
            self.ui.hdmi_mode_cb.setCurrentIndex(0)
        ix1 = [i for i, j in enumerate(self.valid_modes1) if j[0] == self.hdmi_mode1]
        if ix1:
            self.ui.hdmi_mode1_cb.setCurrentIndex(ix1[0])
        else:
            self.ui.hdmi_mode1_cb.setCurrentIndex(0)
        self.ui.hdmi_force_hotplug_cb.setChecked(self.hdmi_force_hotplug)
        self.ui.hdmi_force_hotplug1_cb.setChecked(self.hdmi_force_hotplug1)
        self.ui.hdmi_ignore_edid_cb.setChecked(self.hdmi_ignore_edid)
        self.ui.hdmi_ignore_edid1_cb.setChecked(self.hdmi_ignore_edid1)
        self.ui.config_hdmi_boost_sb.setValue(self.config_hdmi_boost)
        if self.config_hdmi_boost == 5:
            self.ui.config_hdmi_boost_status_lb.setText("(default)")
        elif self.config_hdmi_boost==11:
            self.ui.config_hdmi_boost_status_lb.setText("(max)")
        elif self.config_hdmi_boost==0:
            self.ui.config_hdmi_boost_status_lb.setText("(min)")
        else:
            self.ui.config_hdmi_boost_status_lb.clear()
        self.ui.config_hdmi_boost1_sb.setValue(self.config_hdmi_boost1)
        if self.config_hdmi_boost1 == 5:
            self.ui.config_hdmi_boost_status1_lb.setText("(default)")
        elif self.config_hdmi_boost1==11:
            self.ui.config_hdmi_boost_status1_lb.setText("(max)")
        elif self.config_hdmi_boost1==0:
            self.ui.config_hdmi_boost_status1_lb.setText("(min)")
        else:
            self.ui.config_hdmi_boost_status1_lb.clear()
        self.ui.overscan_gb.setChecked(not self.disable_overscan)
        self.ui.overscan_left_sb.setValue(self.overscan_left)
        self.ui.overscan_right_sb.setValue(self.overscan_right)
        self.ui.overscan_top_sb.setValue(self.overscan_top)
        self.ui.overscan_bottom_sb.setValue(self.overscan_bottom)
        self.ui.overscan_left1_sb.setValue(self.overscan_left1)
        self.ui.overscan_right1_sb.setValue(self.overscan_right1)
        self.ui.overscan_top1_sb.setValue(self.overscan_top1)
        self.ui.overscan_bottom1_sb.setValue(self.overscan_bottom1)
        self.ui.hdmi_force_edid_audio_cb.setChecked(self.hdmi_force_edid_audio)
        self.ui.hdmi_force_edid_audio1_cb.setChecked(self.hdmi_force_edid_audio1)
        self.ui.hdmi_drive_cb.setChecked(self.hdmi_drive == 2)
        self.ui.hdmi_drive1_cb.setChecked(self.hdmi_drive1 == 2)
        self.ui.spi_cb.setChecked(self.dtparam_spi)
        self.ui.i2c_cb.setChecked(self.dtparam_i2c)
        self.ui.i2s_cb.setChecked(self.dtparam_i2s)
        self.ui.audio_cb.setChecked(self.dtparam_audio)
        self.ui.camera_cb.setChecked(self.dtparam_camera)
        self.ui.bluetooth_cb.setChecked(not self.dtoverlay_disable_bt)
        ix = [i for i, j in enumerate(self.country_list) if j[0:2] == self.wifi_regdom]
        if ix:
            self.ui.wifi_country_code_cb.setCurrentIndex(ix[0])
        else:
            self.ui.wifi_country_code_cb.setCurrentIndex(0)
        self.overclock_bg.button(self.overclock_level).setChecked(True)
        
        self.dirty_check()

    def populate_state_from_gui(self, is_initial = False):
        self.dtoverlay_vc4 = self.ui.graphics_driver_cb.currentIndex()
        self.cma_vc4 = self.ui.cma_cb.currentIndex()
        self.gpu_vc4 = self.ui.gpu_cb.currentIndex()
        self.hdmi_safe = self.ui.safe_mode_rb.isChecked()
        self.hdmi_safe1 = self.ui.safe_mode1_rb.isChecked()
        self.hdmi_group = self.ui.hdmi_group_cb.currentIndex()
        self.hdmi_group1 = self.ui.hdmi_group1_cb.currentIndex()
        try:
            self.hdmi_mode = self.valid_modes[self.ui.hdmi_mode_cb.currentIndex()][0]
        except IndexError:
            self.hdmi_mode = 0
        try:
            self.hdmi_mode1 = self.valid_modes1[self.ui.hdmi_mode1_cb.currentIndex()][0]
        except IndexError:
            self.hdmi_mode1 = 0
        self.hdmi_force_hotplug = self.ui.hdmi_force_hotplug_cb.isChecked()
        self.hdmi_force_hotplug1 = self.ui.hdmi_force_hotplug1_cb.isChecked()
        self.hdmi_ignore_edid = self.ui.hdmi_ignore_edid_cb.isChecked()
        self.hdmi_ignore_edid1 = self.ui.hdmi_ignore_edid1_cb.isChecked()
        self.config_hdmi_boost = self.ui.config_hdmi_boost_sb.value()
        self.config_hdmi_boost1 = self.ui.config_hdmi_boost1_sb.value()
        self.disable_overscan = not self.ui.overscan_gb.isChecked()
        self.disable_overscan1 = not self.ui.overscan1_gb.isChecked()
        self.overscan_left = self.ui.overscan_left_sb.value()
        self.overscan_right = self.ui.overscan_right_sb.value()
        self.overscan_top = self.ui.overscan_top_sb.value()
        self.overscan_bottom = self.ui.overscan_bottom_sb.value()
        self.hdmi_force_edid_audio = self.ui.hdmi_force_edid_audio_cb.isChecked()
        self.hdmi_force_edid_audio1 = self.ui.hdmi_force_edid_audio1_cb.isChecked()
        self.hdmi_drive = 2 if self.ui.hdmi_drive_cb.isChecked() else 0
        self.hdmi_drive1 = 2 if self.ui.hdmi_drive1_cb.isChecked() else 0
        self.dtparam_spi = self.ui.spi_cb.isChecked()
        self.dtparam_i2c = self.ui.i2c_cb.isChecked()
        self.dtparam_i2s = self.ui.i2s_cb.isChecked()
        self.dtparam_audio = self.ui.audio_cb.isChecked()
        self.dtparam_camera = self.ui.camera_cb.isChecked()
        self.dtoverlay_disable_bt = not self.ui.bluetooth_cb.isChecked()
        self.wifi_regdom = self.country_list[self.ui.wifi_country_code_cb.currentIndex()][0:2]
        self.overclock_level = self.overclock_bg.checkedId()

    def populate_config_from_state(self, is_initial = False):
        if self.dtoverlay_vc4 == 2:
            comment_config_var("dtoverlay=vc4-", self.tmp_pathname)
        else:
            v = ""
            if self.dtoverlay_vc4 == 0:
                v += "f"
            v += "kms-v3d"
            if self.cma_vc4 < 5:
                v += f",cma-{CMAS[self.cma_vc4]}"
            set_config_var("dtoverlay=vc4-", v, self.tmp_pathname, True, False)
        set_or_comment_config_var("gpu_mem", GPUS[self.gpu_vc4], 0, self.tmp_pathname)
        if self.hdmi_safe:
            set_config_var("hdmi_safe", "1", self.tmp_pathname)
            # comment out anything else related
            comment_config_var("hdmi_force_hotplug", self.tmp_pathname)
            comment_config_var("hdmi_ignore_edid", self.tmp_pathname)

            comment_config_var("config_hdmi_boost", self.tmp_pathname)
            comment_config_var("hdmi_group", self.tmp_pathname)
            comment_config_var("hdmi_mode", self.tmp_pathname)
            comment_config_var("disable_overscan", self.tmp_pathname)
            for d in ["left", "right", "top", "bottom"]:
                comment_config_var(f"overscan_{d}", self.tmp_pathname)
        else:
            comment_config_var("hdmi_safe", self.tmp_pathname)
            # set other hdmi-related vars, respecting defaults
            set_or_comment_config_var("hdmi_group", self.hdmi_group,
                                      0, self.tmp_pathname)
            set_or_comment_config_var("hdmi_mode", self.hdmi_mode,
                                      0, self.tmp_pathname)
            set_or_comment_config_var("hdmi_force_hotplug",
                                      1 if self.hdmi_force_hotplug else 0,
                                      0, self.tmp_pathname)
            set_or_comment_config_var("hdmi_ignore_edid",
                                      "0xa5000080" if self.hdmi_ignore_edid else None,
                                      None, self.tmp_pathname)
            set_or_comment_config_var("config_hdmi_boost", self.config_hdmi_boost,
                                      5, self.tmp_pathname)
            set_or_comment_config_var("disable_overscan",
                                      1 if self.disable_overscan else 0,
                                      0, self.tmp_pathname)
            if self.disable_overscan:
                for d in ["left", "right", "top", "bottom"]:
                    comment_config_var(f"overscan_{d}", self.tmp_pathname)
            else:
                set_or_comment_config_var("overscan_left", self.overscan_left,
                                          0, self.tmp_pathname)
                set_or_comment_config_var("overscan_right", self.overscan_right,
                                          0, self.tmp_pathname)
                set_or_comment_config_var("overscan_top", self.overscan_top,
                                          0, self.tmp_pathname)
                set_or_comment_config_var("overscan_bottom", self.overscan_bottom,
                                          0, self.tmp_pathname)
            set_or_comment_config_var("hdmi_force_edid_audio",
                                      1 if self.hdmi_force_edid_audio else 0,
                                      0, self.tmp_pathname)
            set_or_comment_config_var("hdmi_drive", self.hdmi_drive,
                                      0, self.tmp_pathname)
        if self.hdmi_safe1:
            set_config_var("hdmi_safe:1@pi4", "1", self.tmp_pathname)
            # comment out anything else related
            comment_config_var("hdmi_force_hotplug:1@pi4", self.tmp_pathname)
            comment_config_var("hdmi_ignore_edid:1@pi4", self.tmp_pathname)

            comment_config_var("config_hdmi_boost:1@pi4", self.tmp_pathname)
            comment_config_var("hdmi_group:1@pi4", self.tmp_pathname)
            comment_config_var("hdmi_mode:1@pi4", self.tmp_pathname)
            comment_config_var("disable_overscan:1@pi4", self.tmp_pathname)
            for d in ["left", "right", "top", "bottom"]:
                comment_config_var(f"overscan_{d}:1@pi4", self.tmp_pathname)
        else:
            comment_config_var("hdmi_safe:1@pi4", self.tmp_pathname)
            # set other hdmi-related vars, respecting defaults
            set_or_comment_config_var("hdmi_group:1@pi4", self.hdmi_group1,
                                      0, self.tmp_pathname)
            set_or_comment_config_var("hdmi_mode:1@pi4", self.hdmi_mode1,
                                      0, self.tmp_pathname)
            set_or_comment_config_var("hdmi_force_hotplug:1@pi4",
                                      1 if self.hdmi_force_hotplug1 else 0,
                                      0, self.tmp_pathname)
            set_or_comment_config_var("hdmi_ignore_edid:1@pi4",
                                      "0xa5000080" if self.hdmi_ignore_edid1 else None,
                                      None, self.tmp_pathname)
            set_or_comment_config_var("config_hdmi_boost:1@pi4", self.config_hdmi_boost1,
                                      5, self.tmp_pathname)
            set_or_comment_config_var("disable_overscan:1@pi4",
                                      1 if self.disable_overscan1 else 0,
                                      0, self.tmp_pathname)
            if self.disable_overscan1:
                for d in ["left", "right", "top", "bottom"]:
                    comment_config_var(f"overscan_{d}:1@pi4", self.tmp_pathname)
            else:
                set_or_comment_config_var("overscan_left:1@pi4", self.overscan_left1,
                                          0, self.tmp_pathname)
                set_or_comment_config_var("overscan_right:1@pi4", self.overscan_right1,
                                          0, self.tmp_pathname)
                set_or_comment_config_var("overscan_top:1@pi4", self.overscan_top1,
                                          0, self.tmp_pathname)
                set_or_comment_config_var("overscan_bottom:1@pi4", self.overscan_bottom1,
                                          0, self.tmp_pathname)
            set_or_comment_config_var("hdmi_force_edid_audio:1@pi4",
                                      1 if self.hdmi_force_edid_audio1 else 0,
                                      0, self.tmp_pathname)
            set_or_comment_config_var("hdmi_drive:1@pi4", self.hdmi_drive1,
                                      0, self.tmp_pathname)

        if self.dtparam_spi:
            set_config_var("dtparam=spi=", "on", self.tmp_pathname, "off", False)
        else:
            comment_config_var("dtparam=spi=", self.tmp_pathname)
        if self.dtparam_i2c:
            set_config_var("dtparam=i2c_arm=", "on", self.tmp_pathname, "off", False)
        else:
            comment_config_var("dtparam=i2c_arm=", self.tmp_pathname)
        if self.dtparam_i2s:
            set_config_var("dtparam=i2s=", "on", self.tmp_pathname, "off", False)
        else:
            comment_config_var("dtparam=i2s=", self.tmp_pathname)
        if self.dtparam_audio:
            set_config_var("dtparam=audio=", "on", self.tmp_pathname, "off", False)
        else:
            comment_config_var("dtparam=audio=", self.tmp_pathname)
        if self.dtoverlay_disable_bt:
            set_config_var("dtoverlay=pi3-disable-bt", "", self.tmp_pathname, "off", False)
        else:
            comment_config_var("dtoverlay=pi3-disable-bt", self.tmp_pathname)
        set_or_comment_config_var("start_x",
                                  1 if self.dtparam_camera else 0,
                                  0, self.tmp_pathname)
        if self.overclock_level < 4:
            if self.overclock_level == 0:
                (arm_freq, gpu_freq, over_voltage) = (1500, 500, 0)
            elif self.overclock_level == 1:
                (arm_freq, gpu_freq, over_voltage) = (1750, 500, 2)
            elif self.overclock_level == 2:
                (arm_freq, gpu_freq, over_voltage) = (1750, 600, 4)
            elif self.overclock_level == 3:
                (arm_freq, gpu_freq, over_voltage) = (2000, 600, 6)
            set_or_comment_config_var("force_turbo", 0, 0, self.tmp_pathname)
            set_or_comment_config_var("force_turbo@pi4", 0, 0, self.tmp_pathname)
            set_or_comment_config_var("arm_freq@pi4", arm_freq, 1500, self.tmp_pathname)
            set_or_comment_config_var("gpu_freq@pi4", gpu_freq, 500, self.tmp_pathname)
            set_or_comment_config_var("over_voltage@pi4", over_voltage, 0, self.tmp_pathname)
        
        set_config_var("WIFI_REGDOM", '"' + self.wifi_regdom + '"',
                       self.tmp_regdom_pathname, True, False)


    def update_everything(self):
        if not self.in_update:
            self.in_update = True
            try:
                self.populate_state_from_gui()
                self.populate_config_from_state()
                self.populate_gui_from_state()
            finally:
                self.in_update = False

    def initial_update(self):
        if not self.in_update:
            self.in_update = True
            try:
                self.populate_state_from_config(True)
                # set sensible defaults for overscan
                if self.hdmi_safe:
                    self.disable_overscan = False
                if not config_var_defined("overscan_left", self.tmp_pathname):
                    self.overscan_left = 24
                if not config_var_defined("overscan_right", self.tmp_pathname):
                    self.overscan_right = 24
                if not config_var_defined("overscan_top", self.tmp_pathname):
                    self.overscan_top = 24
                if not config_var_defined("overscan_bottom", self.tmp_pathname):
                    self.overscan_bottom = 24
                if self.hdmi_safe1:
                    self.disable_overscan1 = False
                if not config_var_defined("overscan_left:1@pi4", self.tmp_pathname):
                    self.overscan_left1 = 24
                if not config_var_defined("overscan_right:1@pi4", self.tmp_pathname):
                    self.overscan_right1 = 24
                if not config_var_defined("overscan_top:1@pi4", self.tmp_pathname):
                    self.overscan_top1 = 24
                if not config_var_defined("overscan_bottom:1@pi4", self.tmp_pathname):
                    self.overscan_bottom1 = 24
                self.populate_gui_from_state(True)
            finally:
                self.in_update=False

    def do_revert(self):
        self.cleanup_tmp_copy_of_config()
        self.make_tmp_copy_of_config()
        self.initial_update()

    def do_save_state(self):
        cdm = config_files_differ_materially(self.tmp_pathname,
                                             CONFIG_PATHNAME,
                                             self.use_fake_data)
        if cdm:
            if self.save_lng:
                shutil.copyfile(CONFIG_PATHNAME, CONFIG_LNG_PATHNAME)
            shutil.copyfile(self.tmp_pathname, CONFIG_PATHNAME)
        os.remove(self.tmp_pathname)
        shutil.copyfile(self.tmp_regdom_pathname, WIFI_REGDOM_PATHNAME)
        # reflect in module settings too
        subprocess.run(f"[[ -s \"{WIFI_REGDOM_PATHNAME}\" ]] && " +
                       f"sed -i 's#ieee80211_regdom=.*$#" +
                       f"ieee80211_regdom=\"{self.wifi_regdom}\"#g' " +
                       f"\"{WIFI_MODPROBE_PATHNAME}\"",
                       shell=True)
        os.remove(self.tmp_regdom_pathname)

        if self.save_lng:
            if cdm:
                # make sure /boot/config.txt.lng has the newer mtime
                time.sleep(0.1)
                os.utime(CONFIG_LNG_PATHNAME, None) # touch, essentially
            return(True)
        else:
            # check if, as a result of multiple edits without reboot,
            # we're back where we started, and if so, remove the lng variant
            if config_files_differ_materially(CONFIG_LNG_PATHNAME,
                                                  CONFIG_PATHNAME, self.use_fake_data):
                return(True)
            else:
                os.remove(CONFIG_LNG_PATHNAME)
                return(False) # signal no reboot needed

    # slots ---------------------------------------------------------

    def gui_changed(self):
        # generic handler
        self.update_everything()

    def gui_value_changed(self, v):
        # generic handler
        self.gui_changed()

    def camera_cb_value_changed(self, v):
        if self.ui.camera_cb.isChecked() and GPUS[self.gpu_vc4] < 128:
            if not self.in_update:
                QMessageBox.warning(self, self.windowTitle(),
"""

<p><strong>Warning:</strong> your current GPU memory allocation is too low to use the camera.</p>

<p>Force-setting 128 MiB GPU memory allocation instead.</p>

""")
                self.ui.gpu_cb.setCurrentIndex(GPUS.index(128))
        self.gui_changed()

    def gui_bool_changed(self, b):
        # generic handler
        self.gui_changed()

    def accept(self):
        self.update_everything()
        # prompt for reboot, unless do_save_state returns False,
        # indicating we're back where we started (multiple saves
        # leading back to the currently-booted-under config)
        do_reboot_txt = """

<p>Your configuration has been saved, and will take effect from next boot.</p>

<p>Would you like to reboot now?<p>

"""
        info_txt = """

<p>Your changes will take effect when you next restart your RPi.</p>

"""
        info2_txt = """

<p>No restart is necessary, as your configuration is now unchanged
again from that which this session was booted under.</p>

"""
        if self.dirty:
            reboot_needed = self.do_save_state()
            if reboot_needed:
                if QMessageBox.question(self, self.windowTitle(), do_reboot_txt,
                                        QMessageBox.Yes | QMessageBox.No,
                                        QMessageBox.Yes) == QMessageBox.Yes:
                    self.reboot_now()
                else:
                    QMessageBox.information(self, self.windowTitle(), info_txt)
            else:
                QMessageBox.information(self, self.windowTitle(),info2_txt)
                    
        super(MainDialog, self).accept()

    def reject(self):
        super(MainDialog, self).reject()

    def hdmi_group_changed(self, index):
        self.ui.hdmi_mode_cb.clear()
        if index == 1:
            self.valid_modes = self.valid_cea_modes
            self.valid_modes_txt = self.valid_cea_modes_txt
        else:
            self.valid_modes = self.valid_dmt_modes
            self.valid_modes_txt = self.valid_dmt_modes_txt
        self.ui.hdmi_mode_cb.addItems(self.valid_modes_txt)
        self.update_everything()

    def hdmi_group1_changed(self, index):
        self.ui.hdmi_mode1_cb.clear()
        if index == 1:
            self.valid_modes1 = self.valid_cea_modes1
            self.valid_modes_txt1 = self.valid_cea_modes_txt1
        else:
            self.valid_modes1 = self.valid_dmt_modes1
            self.valid_modes_txt1 = self.valid_dmt_modes_txt1
        self.ui.hdmi_mode1_cb.addItems(self.valid_modes_txt1)
        self.update_everything()

    def sync_fallback_lists(self):
        # force dropdowns to update with new list
        old_hdmi_mode = self.hdmi_mode
        self.hdmi_group_changed(self.hdmi_group)
        # may be we can still use old mode, if it exists in new mode list
        self.hdmi_mode = old_hdmi_mode
        self.populate_gui_from_state()
        self.update_everything()

    def sync_fallback_lists1(self):
        # force dropdowns to update with new list
        old_hdmi_mode1 = self.hdmi_mode1
        self.hdmi_group1_changed(self.hdmi_group1)
        # may be we can still use old mode, if it exists in new mode list
        self.hdmi_mode1 = old_hdmi_mode1
        self.populate_gui_from_state()
        self.update_everything()

    def hdmi_ignore_edid_changed(self, b):
        # repopulate the HDMI mode lists with sane defaults,
        # if ignoring EDID...
        self.update_everything()
        self.get_system_data(fallback = self.ui.hdmi_ignore_edid_cb.isChecked())
        self.sync_fallback_lists()

    def hdmi_ignore_edid1_changed(self, b):
        # repopulate the HDMI mode lists with sane defaults,
        # if ignoring EDID...
        self.update_everything()
        self.get_system_data1(fallback = self.ui.hdmi_ignore_edid1_cb.isChecked())
        self.sync_fallback_lists1()

    def button_bar_button_clicked(self, button):
        if(button.text() == "Revert"):
            self.do_revert()

    def layout_editor_button_clicked(self, b):
        existing_pid = pid_of_process("arandr")
        if existing_pid != 0:
            bring_window_to_front(existing_pid)
        else:
            run_command_as(['/usr/bin/python-exec2c', 'arandr'], self.original_uid,
                           self.original_gid, env={"PATH": self.original_home,
                                                   "PATH": self.original_path,
                                                   "DISPLAY": self.original_display,
                                                   "XAUTHORITY": os.getenv("XAUTHORITY") or ""})

    # initialization ------------------------------------------------

    def show_fallback_popup(self):
        QMessageBox.warning(self, self.windowTitle(),
"""

<p><strong>Warning:</strong> no data about supported CEA or DMT modes
could be detected. Perhaps you have no display connected?</p>

<p>Assuming a default list of 60Hz HDMI modes instead.</p>

""")
                            
    def show_first_run_popup(self):
        QMessageBox.information(self, self.windowTitle(),
"""

<p><strong>Welcome!</strong> You can use this application to modify a
number of important settings on your RPi. It has been auto-started on
this first login, in case you would like to (e.g.) increase the
graphics resolution of your display (via HDMI group/mode), prevent
'clipping' at the display edges (via overscan), change the graphics
driver, etc.<./p> Remember that you'll need to reboot before any
changes made here take effect.</p>

<p>This app may also be found under the <kbd>Applications</kbd>
&rarr; <kbd>Settings</kbd> menu (named <kbd>RPi Config
Tool</kbd> there).</p>

<p>If you <em>do</em> make changes with this app and reboot, you'll be
prompted (when the system comes back up) whether to keep or reject the
changes you made. The default choice here, which is auto-selected
after a timeout, is to <strong>reject</strong> them and restart back
to the last-known-good configuration again.</p>

<p>This means you don't need to worry about making configuration
changes that turn out to be incompatible with your system (wrong
display settings, for example).</p>

""")

    def show_break_reboot_detected_popup(self):
        QMessageBox.warning(self, self.windowTitle(),
"""

<p>As you did not explicitly accept them, your most
recent config changes have been discarded,
and your last-known-good config is again in force.</p>
<p>The rejected config may be reviewed at

""" f"<em>{CONFIG_REJ_PATHNAME}</em>, until the next reboot.</p>")

    def get_system_data(self, fallback = False):
        fn = get_fallback_modes if fallback else get_valid_modes
        self.using_fallback_hdmi_data = fallback
        while True:
            (self.valid_cea_modes, self.valid_cea_modes_txt) = \
                fn("CEA", HDMI_BASE_MODE_TXT, self.use_fake_data, 0)
            (self.valid_dmt_modes, self.valid_dmt_modes_txt) = \
                fn("DMT", HDMI_BASE_MODE_TXT, self.use_fake_data, 0)
            if len(self.valid_cea_modes) > 1 or len(self.valid_dmt_modes) > 1:
                break
            fn = get_fallback_modes
            self.using_fallback_hdmi_data = True

    def get_system_data1(self, fallback = False):
        fn = get_fallback_modes if fallback else get_valid_modes
        self.using_fallback_hdmi_data1 = fallback
        while True:
            (self.valid_cea_modes1, self.valid_cea_modes_txt1) = \
                fn("CEA", HDMI_BASE_MODE_TXT, self.use_fake_data, 1)
            (self.valid_dmt_modes1, self.valid_dmt_modes_txt1) = \
                fn("DMT", HDMI_BASE_MODE_TXT, self.use_fake_data, 1)
            if len(self.valid_cea_modes1) > 1 or len(self.valid_dmt_modes1) > 1:
                break
            fn = get_fallback_modes
            self.using_fallback_hdmi_data1 = True
        

    def setup_buttons(self):
        self.reset_b = self.ui.main_bb.button(QDialogButtonBox.Reset)
        self.cancel_b = self.ui.main_bb.button(QDialogButtonBox.Cancel)
        self.cancel_b.setToolTip("Exit without saving changes")
        self.ok_b = self.ui.main_bb.button(QDialogButtonBox.Ok)
        self.ok_b.setText("Save and Exit")
        self.ok_b.setToolTip("Save your changes and exit; you'll be prompted to reboot if necessary")
        self.reset_b.setIcon(QIcon())
        self.reset_b.setText("Revert")
        self.reset_b.setToolTip("Revert all edits since you opened the application")

    def setup_tooltips(self):
        # avoid having to duplicate text in the .ui file
        self.ui.normal_mode1_rb.setToolTip(self.ui.normal_mode_rb.toolTip())
        self.ui.safe_mode1_rb.setToolTip(self.ui.safe_mode_rb.toolTip())
        self.ui.hdmi_group_cb.setToolTip(self.ui.hdmi_group_lb.toolTip())
        self.ui.hdmi_group1_lb.setToolTip(self.ui.hdmi_group_lb.toolTip())
        self.ui.hdmi_group1_cb.setToolTip(self.ui.hdmi_group_lb.toolTip())
        self.ui.hdmi_mode_cb.setToolTip(self.ui.hdmi_mode_lb.toolTip())
        self.ui.hdmi_mode1_lb.setToolTip(self.ui.hdmi_mode_lb.toolTip())
        self.ui.hdmi_mode1_cb.setToolTip(self.ui.hdmi_mode_lb.toolTip())
        self.ui.graphics_driver_cb.setToolTip(self.ui.graphics_driver_lb.toolTip())
        self.ui.cma_cb.setToolTip(self.ui.cma_lb.toolTip())
        self.ui.gpu_cb.setToolTip(self.ui.gpu_lb.toolTip())
        self.ui.config_hdmi_boost_sb.setToolTip(self.ui.config_hdmi_boost_lb.toolTip())
        self.ui.config_hdmi_boost1_lb.setToolTip(self.ui.config_hdmi_boost_lb.toolTip())
        self.ui.config_hdmi_boost1_sb.setToolTip(self.ui.config_hdmi_boost_lb.toolTip())
        self.ui.overscan1_gb.setToolTip(self.ui.overscan_gb.toolTip())
        self.ui.overscan_left_sb.setToolTip(self.ui.overscan_left_lb.toolTip())
        self.ui.overscan_left1_lb.setToolTip(self.ui.overscan_left_lb.toolTip())
        self.ui.overscan_left1_sb.setToolTip(self.ui.overscan_left_lb.toolTip())
        self.ui.overscan_right_sb.setToolTip(self.ui.overscan_right_lb.toolTip())
        self.ui.overscan_right1_lb.setToolTip(self.ui.overscan_right_lb.toolTip())
        self.ui.overscan_right1_sb.setToolTip(self.ui.overscan_right_lb.toolTip())
        self.ui.overscan_top_sb.setToolTip(self.ui.overscan_top_lb.toolTip())
        self.ui.overscan_top1_lb.setToolTip(self.ui.overscan_top_lb.toolTip())
        self.ui.overscan_top1_sb.setToolTip(self.ui.overscan_top_lb.toolTip())
        self.ui.overscan_bottom_sb.setToolTip(self.ui.overscan_bottom_lb.toolTip())
        self.ui.overscan_bottom1_lb.setToolTip(self.ui.overscan_bottom_lb.toolTip())
        self.ui.overscan_bottom1_sb.setToolTip(self.ui.overscan_bottom_lb.toolTip())
        self.ui.hdmi_force_hotplug1_cb.setToolTip(self.ui.hdmi_force_hotplug_cb.toolTip())
        self.ui.hdmi_ignore_edid1_cb.setToolTip(self.ui.hdmi_ignore_edid_cb.toolTip())
        self.ui.config_hdmi_boost1_lb.setToolTip(self.ui.config_hdmi_boost_lb.toolTip())
        self.ui.hdmi_drive1_cb.setToolTip(self.ui.hdmi_drive_cb.toolTip())
        self.ui.hdmi_force_edid_audio1_cb.setToolTip(self.ui.hdmi_force_edid_audio_cb.toolTip())
        self.ui.wifi_country_code_cb.setToolTip(self.ui.wifi_country_code_lb.toolTip())
        
    def reboot_now(self):
        if self.allow_reboot:
            do_reboot()
        else:
            print("*** WOULD REBOOT ***")
        self.sys_exit(0)

    def has_pending_config_changes(self):
        return(Path(CONFIG_TBC_PATHNAME).is_file())

    def break_reboot_lng_restore_just_happened(self):
        return(Path(CONFIG_REJ_PATHNAME).is_file() and
               not Path(self.handled_already_sentinel()).is_file())

    def handle_pending_config_changes(self):
        # background: on save, old config.txt -> config.txt.lng, new
        # to config.txt; on reboot, the rpi3-config-mv service renames
        # config.txt -> config.txt.tbc, config.txt.lng -> config.txt
        # so when this fn is called, on app startup, and if
        # config.txt.tbc exists:
        #  if user rejects changes, config.txt.tbc -> config.txt.rej, and reboot
        #  if user accepts changes, config.txt -> config.text.old, config.text.tbc -> config.txt

        if self.has_pending_config_changes():
            TIMEOUT_SECS = 60
            m = TimeoutMessageBox(parent = self, timeout_secs = TIMEOUT_SECS,
                                  which_display_button = QMessageBox.No)
            m.setText(
"""

<p><strong>Important!</strong> You have just rebooted under a modified
RPi system configuration file (which has been temporarily moved to
<em>/boot/config.txt.tbc</em> post-reboot, pending your
confirmation).</p>

<p>Would you like to keep using your (modified) version?</p>

<p><strong>NB:</strong> if you don't answer

""" f"within {TIMEOUT_SECS}s, "

"""then your <em>prior</em> version of this file (which was
temporarily moved after the latest restart to
<em>/boot/config.txt</em>) will <em>automatically</em> be retained,
and your system will reboot to start using it again.</p>

<p>This is a safeguard, to ensure you don't get stuck
without (e.g.) a visible display.</p>

""")
            m.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            m.button(QMessageBox.No).setText("No, Reboot to Prior Version")
            m.button(QMessageBox.Yes).setText("Yes, Keep Using Modified Version")
            m.setWindowTitle("Booted under Modified Configuration")
            m.setDefaultButton(QMessageBox.No)
            m.setIcon(QMessageBox.Warning)
            m.on_tick()
            ret = m.exec()
            if ret == QMessageBox.No or ret == QMessageBox.NoButton:
                # reject the last-boot config
                # note that since the rpi3-config-mv service has already renamed
                # config.txt -> config.txt.tbc, even if the user doesn't
                # autologin, they'll still have the lng driver active
                # if they (hard or soft) reboot
                shutil.move(CONFIG_TBC_PATHNAME, CONFIG_REJ_PATHNAME)
                self.reboot_now()
            else:
                # backup booted-with version, promote the pending version
                shutil.copyfile(CONFIG_PATHNAME, CONFIG_OLD_PATHNAME)
                shutil.move(CONFIG_TBC_PATHNAME, CONFIG_PATHNAME)
                self.do_revert()

    def check_running_as_root(self):
        if not os.geteuid() == 0:
            QMessageBox.critical(self, self.windowTitle(),
                                "You need to be root to run this program. Quitting.")
            self.sys_exit(1)

    def local_home_dir(self):
        # look through sudo
        user = os.getenv("SUDO_USER") or "root"
        homedir = "/root" if user == "root" else f"/home/{user}"
        return(homedir)

    def local_config_root_dir(self):
        return(f"{self.local_home_dir()}/.config")

    def local_config_dir(self):
        return(f"{self.local_config_root_dir()}/{app_name()}")
      
    def is_first_run(self):
        return(not Path(self.local_config_dir()).is_dir())

    def make_local_config_dir(self):
        if self.first_run:
            rd = self.local_config_root_dir()
            if not Path(rd).is_dir():
                os.mkdir(rd)
                make_real_user_owned(rd)
            lcd = self.local_config_dir()
            if not Path(lcd).is_dir():
                os.mkdir(lcd)
                make_real_user_owned(lcd)
                
    def handled_already_sentinel(self):
        return(f"/tmp/.{app_name()}_BREAK_REBOOT_NOTIFIED")

    def handle_break_reboot_lng_restore(self):
        # deal with a rej config being present: this indicates that
        # the rpi3-config-mv service has picked up a tbc file,
        # which likely indicates a break reboot caused by a timeout
        if self.break_reboot_lng_restore_just_happened():
            os.mknod(self.handled_already_sentinel()) # touch
            make_real_user_owned(self.handled_already_sentinel())
            self.show_break_reboot_detected_popup()
            
    def resolve_prior_edit_without_reboot(self):
        # if an lng config is present, the user has modified config.txt via this
        # app, but not rebooted yet
        # in this case, mark that we don't want to save as last-known-good
        # on a "save and exit" this time
        if Path(CONFIG_LNG_PATHNAME).is_file() and Path(CONFIG_PATHNAME).is_file():
            self.save_lng = False

    def setup_wifi_country_codes(self):
        self.country_list = get_wifi_country_list()
        self.ui.wifi_country_code_cb.clear()
        self.ui.wifi_country_code_cb.addItems(self.country_list)

    def setup_overclock_button_group(self):
        self.overclock_bg = QButtonGroup()
        self.overclock_bg.addButton(self.ui.overclock0_rb, 0)
        self.overclock_bg.addButton(self.ui.overclock1_rb, 1)
        self.overclock_bg.addButton(self.ui.overclock2_rb, 2)
        self.overclock_bg.addButton(self.ui.overclock3_rb, 3)
        self.overclock_bg.addButton(self.ui.overclock4_rb, 4)
        self.overclock_bg.buttonClicked['int'].connect(self.gui_value_changed)
    
    def __init__(self, allow_reboot = False, use_fake_data = False,
                 is_autostart = False):
        self.in_update = True
        self.allow_reboot = allow_reboot
        self.use_fake_data = use_fake_data
        self.is_autostart = is_autostart
        self.resolve_prior_edit_without_reboot()
        self.make_tmp_copy_of_config()
        super(MainDialog, self).__init__()
        self.ui = Ui_MainDialog()
        self.ui.setupUi(self)
        self.setup_buttons()
        self.setup_tooltips()
        self.setup_wifi_country_codes()
        self.get_system_data()
        self.get_system_data1()
        self.setup_overclock_button_group()
        self.in_update = False
        self.initial_update()
        self.resize(0, 0) # shrink to minimum size given fonts etc.
        self.check_running_as_root()
        # save off the pre-sudo UID and GID
        (self.original_uid, self.original_gid) = (int(os.environ["SUDO_UID"]),
                                                  int(os.environ["SUDO_GID"]))
        self.original_home = pwd.getpwuid(self.original_uid).pw_dir
        self.original_path = os.environ["PATH"]
        self.original_display = os.environ["DISPLAY"]
        self.first_run = self.is_first_run()
        if self.is_autostart and not self.has_pending_config_changes() and \
           not self.break_reboot_lng_restore_just_happened() and \
           not self.first_run:
            # nothing to do
            self.sys_exit(0)
        self.make_local_config_dir()
        self.show()
        if self.first_run:
            self.show_first_run_popup()
        self.handle_pending_config_changes()
        self.handle_break_reboot_lng_restore()

# module level ------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    parser = QtCore.QCommandLineParser()
    a_opt = QtCore.QCommandLineOption("a", "autostart run")
    r_opt = QtCore.QCommandLineOption("R", "prevent reboot")
    d_opt = QtCore.QCommandLineOption("d", "use fake data for testing")
    parser.addOption(r_opt)
    parser.addOption(d_opt)
    parser.addOption(a_opt)
    parser.process(app)
    dialog = MainDialog(allow_reboot = not parser.isSet(r_opt),
                        use_fake_data = parser.isSet(d_opt),
                        is_autostart = parser.isSet(a_opt))
    try:
        app.exec_()
    finally:
        dialog.cleanup_tmp_copy_of_config()

if __name__ == "__main__":
    main()
