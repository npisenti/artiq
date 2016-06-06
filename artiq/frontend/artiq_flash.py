#!/usr/bin/env python3.5
# Copyright (C) 2015 Robert Jordens <jordens@gmail.com>

import argparse
import os
import subprocess
import tempfile
import site

from artiq import __artiq_dir__ as artiq_dir
from artiq.frontend.bit2bin import bit2bin


def get_argparser():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="ARTIQ flashing/deployment tool",
        epilog="""\
Valid actions:

    * proxy: load the flash proxy gateware bitstream
    * gateware: write gateware bitstream to flash
    * bios: write bios to flash
    * runtime: write runtime to flash
    * storage: write storage image to flash
    * load: load gateware bitstream into device (volatile but fast)
    * start: trigger the target to (re)load its gateware bitstream from flash

Prerequisites:

    * Connect the board through its/a JTAG adapter.
    * Have OpenOCD installed and in your $PATH.
    * Have access to the JTAG adapter's devices. Udev rules from OpenOCD:
      'sudo cp openocd/contrib/99-openocd.rules /etc/udev/rules.d'
      and replug the device. Ensure you are member of the
      plugdev group: 'sudo adduser $USER plugdev' and re-login.
""")
    parser.add_argument("-t", "--target", default="kc705",
                        help="target board, default: %(default)s")
    parser.add_argument("-m", "--adapter", default="clock",
                        help="target adapter, default: %(default)s")
    parser.add_argument("-f", "--storage", help="write file to storage area")
    parser.add_argument("-d", "--dir", help="look for files in this directory")
    parser.add_argument("ACTION", nargs="*",
                        default="proxy gateware bios runtime start".split(),
                        help="actions to perform, default: %(default)s")
    return parser


def main():
    parser = get_argparser()
    opts = parser.parse_args()

    config = {
        "kc705": {
            "chip": "xc7k325t",
            "start": "xc7_program xc7.tap",
            "gateware": 0x000000,
            "bios": 0xaf0000,
            "runtime": 0xb00000,
            "storage": 0xb80000,
        },
        "pipistrello": {
            "chip": "xc6slx45",
            "start": "xc6s_program xc6s.tap",
            "gateware": 0x000000,
            "bios": 0x170000,
            "runtime": 0x180000,
            "storage": 0x200000,
        },
    }[opts.target]

    if opts.dir is None:
        opts.dir = os.path.join(artiq_dir, "binaries",
                                "{}-{}".format(opts.target, opts.adapter))
    if not os.path.exists(opts.dir):
        raise SystemExit("Binaries directory '{}' does not exist"
                         .format(opts.dir))

    conda_prefix_path = site.getsitepackages()[0]
    if os.name == "nt":
        scripts_path = os.path.join(conda_prefix_path, "Library", "share", "openocd", "scripts")
    else:
        scripts_path = os.path.join(conda_prefix_path, "share", "openocd", "scripts")

    conv = False

    prog = []
    prog.append("init")
    for action in opts.ACTION:
        if action == "proxy":
            proxy_base = "bscan_spi_{}.bit".format(config["chip"])
            proxy = None
            for p in [opts.dir, os.path.expanduser("~/.migen"),
                      "/usr/local/share/migen", "/usr/share/migen"]:
                proxy_ = os.path.join(p, proxy_base)
                if os.access(proxy_, os.R_OK):
                    proxy = "jtagspi_init 0 {{{}}}".format(proxy_)
                    break
            if not proxy:
                raise SystemExit(
                    "proxy gateware bitstream {} not found".format(proxy_base))
            prog.append(proxy)
        elif action == "gateware":
            bin = os.path.join(opts.dir, "top.bin")
            if not os.access(bin, os.R_OK):
                bin_handle, bin = tempfile.mkstemp()
                bit = os.path.join(opts.dir, "top.bit")
                conv = True
            prog.append("jtagspi_program {{{}}} 0x{:x}".format(
                bin, config["gateware"]))
        elif action == "bios":
            prog.append("jtagspi_program {{{}}} 0x{:x}".format(
                os.path.join(opts.dir, "bios.bin"), config["bios"]))
        elif action == "runtime":
            prog.append("jtagspi_program {{{}}} 0x{:x}".format(
                os.path.join(opts.dir, "runtime.fbi"), config["runtime"]))
        elif action == "storage":
            prog.append("jtagspi_program {{{}}} 0x{:x}".format(
                opts.storage, config["storage"]))
        elif action == "load":
            prog.append("pld load 0 {{{}}}".format(
                os.path.join(opts.dir, "top.bit")))
        elif action == "start":
            prog.append(config["start"])
        else:
            raise ValueError("invalid action", action)
    prog.append("exit")
    try:
        if conv:
            bit2bin(bit, bin_handle)
        subprocess.check_call([
            "openocd",
            "-s", scripts_path,
            "-f", os.path.join("board", opts.target + ".cfg"),
            "-c", "; ".join(prog),
        ])
    finally:
        if conv:
            os.unlink(bin)


if __name__ == "__main__":
    main()
