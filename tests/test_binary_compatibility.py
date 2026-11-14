"""Catch upstream ABI/architecture changes before publishing a misleading wheel."""

import runpy
import struct
from pathlib import Path

import pytest

CHECK = runpy.run_path(
    str(Path(__file__).resolve().parent.parent / "scripts/binary_compatibility.py")
)["check_binary"]


def elf(machine=62, versions=()):
    strings = b"\0"
    offsets = []
    for version in versions:
        offsets.append(len(strings))
        strings += version.encode() + b"\0"
    version_table = struct.pack("<HHIII", 1, len(versions), 0, 16, 0)
    for index, offset in enumerate(offsets):
        version_table += struct.pack(
            "<IHHII", 0, 0, 0, offset, 16 if index < len(offsets) - 1 else 0
        )
    binary = bytearray(256)
    binary[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<H", binary, 18, machine)
    struct.pack_into("<Q", binary, 40, 64)
    struct.pack_into("<HH", binary, 58, 64, 3)
    struct.pack_into(
        "<IIQQQQIIQQ", binary, 128, 0, 3, 0, 0, 256, len(strings), 0, 0, 1, 0
    )
    struct.pack_into(
        "<IIQQQQIIQQ",
        binary,
        192,
        0,
        0x6FFFFFFE,
        0,
        0,
        256 + len(strings),
        len(version_table),
        1,
        0,
        1,
        0,
    )
    return bytes(binary) + strings + version_table


@pytest.mark.parametrize(
    "versions,passes",
    [
        (("GLIBC_2.2.5", "GLIBC_2.28"), True),
        (("GLIBC_2.29",), False),
        (("GLIBC_2.34", "GLIBC_2.17"), False),
        ((), False),
    ],
)
def test_manylinux_floor(versions, passes):
    data = elf(versions=versions)
    if passes:
        CHECK(data, "linux", "x86_64")
    else:
        with pytest.raises(RuntimeError, match="glibc requirements"):
            CHECK(data, "linux", "x86_64")


def test_musl_must_not_depend_on_glibc():
    CHECK(elf(machine=183), "linux-musl", "arm64")
    with pytest.raises(RuntimeError, match="must not require glibc"):
        CHECK(elf(versions=("GLIBC_2.17",)), "linux-musl", "x86_64")
    with pytest.raises(RuntimeError, match="architecture"):
        CHECK(elf(machine=183), "linux-musl", "x86_64")


@pytest.mark.parametrize(
    "command,architecture,minimum,machine,passes",
    [
        (0x24, 0x01000007, (10, 12), "x86_64", True),
        (0x24, 0x01000007, (10, 13), "x86_64", False),
        (0x32, 0x0100000C, (11, 0), "arm64", True),
        (0x32, 0x0100000C, (12, 0), "arm64", False),
    ],
)
def test_macos_minimum(command, architecture, minimum, machine, passes):
    data = bytearray(56)
    struct.pack_into("<IIIIIIII", data, 0, 0xFEEDFACF, architecture, 0, 2, 1, 24, 0, 0)
    struct.pack_into("<II", data, 32, command, 24)
    struct.pack_into(
        "<I", data, 40 if command == 0x24 else 44, minimum[0] << 16 | minimum[1] << 8
    )
    if passes:
        CHECK(data, "darwin", machine)
    else:
        with pytest.raises(RuntimeError, match="minimum"):
            CHECK(data, "darwin", machine)


def test_windows_architecture():
    data = bytearray(128)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 64)
    data[64:68] = b"PE\0\0"
    struct.pack_into("<H", data, 68, 0x8664)
    CHECK(data, "windows", "x86_64")
    struct.pack_into("<H", data, 68, 0xAA64)
    with pytest.raises(RuntimeError, match="Windows x64"):
        CHECK(data, "windows", "x86_64")


def test_nonversioned_glibc_abi_cannot_silently_pass_floor_check():
    with pytest.raises(RuntimeError, match="ABI requirement"):
        CHECK(elf(versions=("GLIBC_2.28", "GLIBC_ABI_DT_RELR")), "linux", "x86_64")
