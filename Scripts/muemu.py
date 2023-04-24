#
#  Script for running QEMU with the appropriate options for the given SKU/ARCH.
#
#  Copyright (c) Microsoft Corporation
#  SPDX-License-Identifier: BSD-2-Clause-Patent
#

from typing import List
import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

parser = argparse.ArgumentParser()

# HINT: Run with '--help all' to get complete help.
parser.add_argument("-u", "--update", action="store_true",
                    help="Updates the firmware binaries.")
parser.add_argument("--firmwaredir", default="./fw",
                    help="Directory to download and use firmware binaries.")
parser.add_argument("-a", "--arch", default="x64",
                    choices=["x64", "arm64"], help="The guest architecture for the VM.")
parser.add_argument("-d", "--disk",
                    help="Path to the disk file.")
parser.add_argument("-c", "--cores", default=2, type=int,
                    help="Path to the disk file.")
parser.add_argument("-m", "--memory", default="4096",
                    help="The memory size to use in Mb.")
parser.add_argument("--vnc",
                    help="Provides the VNC port to use. E.g. ':1' for localhost:5901")
parser.add_argument("--accel", default="tcg",
                    choices=["tcg", "kvm", "whpx"], help="Acceleration back-end to use in QEMU.")
parser.add_argument("--version", default="1.1.4",
                    help="The Project MU firmware version to use.")
parser.add_argument("--qemudir", default="",
                    help="Path to a custom QEMU install directory.")
parser.add_argument("--gdbport", type=int,
                    help="Enabled the GDB server on the specified port.")
parser.add_argument("--debugfw", action="store_true",
                    help="Enables update to use the DEBUG firmware binaries.")
parser.add_argument("--verbose", action="store_true",
                    help="Enabled verbose script prints.")

args = parser.parse_args()


def main():
    # Run special operations if requested.
    if args.update:
        update_firmware()
        return

    # Build the platform specific arguments.
    qemu_args = []
    if args.arch == "x64":
        build_args_x64(qemu_args)
    elif args.arch == "arm64":
        build_args_arm64(qemu_args)
    else:
        raise ValueError(f"Invalid architecture '{args.arch}'!")

    # General device config
    qemu_args += ["-name", f"MU-{args.arch}"]
    qemu_args += ["-m", f"{args.memory}"]
    qemu_args += ["-smp", f"{args.cores}"]

    # SMBIOS
    qemu_args += ["-smbios", "type=0,vendor=Palindrome,uefi=on"]
    qemu_args += ["-smbios",
                  "type=1,manufacturer=Palindrome,product=MuQemu,serial=42-42-42-42"]

    # Storage
    if args.disk != None:
        qemu_args += ["-hda", f"{args.disk}"]

    # User input devices
    qemu_args += ["-device", "qemu-xhci,id=usb"]
    qemu_args += ["-device", "usb-mouse,id=input0,bus=usb.0,port=1"]
    qemu_args += ["-device", "usb-kbd,id=input1,bus=usb.0,port=2"]

    # Network
    qemu_args += ["-nic", "model=e1000"]

    # Display
    if args.vnc != None:
        qemu_args += ["-display", f"vnc={args.vnc}"]

    # Debug & Serial ports
    if args.gdbport != None:
        qemu_args += ["-gdb", f"tcp::{args.gdbport}"]

    # Launch QEMU
    run_qemu(qemu_args)


def build_args_x64(qemu_args: List[str]):
    qemu_args += [f"{args.qemudir}qemu-system-x86_64"]
    qemu_args += ["-machine", "q35,smm=on"]
    qemu_args += ["-cpu", "qemu64,+rdrand,umip,+smep"]
    qemu_args += ["-global", "ICH9-LPC.disable_s3=1"]
    qemu_args += ["-debugcon", "file:uefi-x64.log"]
    qemu_args += ["-global", "isa-debugcon.iobase=0x402"]
    qemu_args += ["-vga", "cirrus"]

    # Flash storage
    code_fd = f"{args.firmwaredir}/x64/QemuQ35/VisualStudio-x64/QEMUQ35_CODE.fd"
    data_fd = f"{args.firmwaredir}/x64/QemuQ35/VisualStudio-x64/QEMUQ35_VARS.fd"
    qemu_args += ["-global", "driver=cfi.pflash01,property=secure,value=on"]
    qemu_args += ["-drive",
                  f"if=pflash,format=raw,unit=0,file={code_fd},readonly=on"]
    qemu_args += ["-drive", f"if=pflash,format=raw,unit=1,file={data_fd}"]


def build_args_arm64(qemu_args: List[str]):
    qemu_args += [f"{args.qemudir}qemu-system-aarch64"]
    qemu_args += ["-machine", "sbsa-ref"]
    qemu_args += ["-cpu", "max"]
    qemu_args += ["-serial", "file:uefi-arm64.log"]

    # Flash storage
    sec_fd = f"{args.firmwaredir}/aarch64/QemuSbsa/GCC-AARCH64/SECURE_FLASH0.fd"
    efi_fd = f"{args.firmwaredir}/aarch64/QemuSbsa/GCC-AARCH64/QEMU_EFI.fd"
    qemu_args += ["-global", "driver=cfi.pflash01,property=secure,value=on"]
    qemu_args += ["-drive", f"if=pflash,format=raw,unit=0,file={sec_fd}"]
    qemu_args += ["-drive",
                  f"if=pflash,format=raw,unit=1,file={efi_fd},readonly=on"]


def run_qemu(qemu_args: List[str]):
    if args.verbose:
        print(qemu_args)
    try:
        subprocess.run(qemu_args, shell=True)
    except Exception as e:
        raise e


def update_firmware():
    #
    # Updates the firmware to the following configuration.
    #     <root>/<arch>/<platform>/<build_toolchain>/<files>
    #
    print("Updating firmware...")

    build_type = "DEBUG" if args.debugfw else "RELEASE"
    fw_info_list = [["QemuQ35", "x64"],
                    ["QemuSbsa", "aarch64"]]

    for fw_info in fw_info_list:
        url = f"https://github.com/microsoft/mu_tiano_platforms/releases/download/v{args.version}/Mu.{fw_info[0]}.FW.{build_type}-{args.version}.zip"
        zip_path = f"{fw_info[0]}.zip"

        print(f"Downloading {fw_info[0]}")
        urllib.request.urlretrieve(url, zip_path)
        print(f"Unzipping {fw_info[0]}")
        unzip_path = f"{args.firmwaredir}/{fw_info[1]}/{fw_info[0]}/"
        shutil.rmtree(unzip_path, ignore_errors=True)
        with zipfile.ZipFile(zip_path, "r") as zip:
            zip.extractall(unzip_path)
        os.remove(zip_path)


try:
    main()
except KeyboardInterrupt as e:
    sys.stdout.write("\n")
    pass
