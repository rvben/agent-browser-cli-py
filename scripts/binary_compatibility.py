"""Read executable headers without running a foreign-platform binary."""

import struct


def elf_requirements(data: bytes) -> tuple[int, list[tuple[int, ...]]]:
    """Read the machine and glibc requirements from an ELF64 version-need table."""
    if data[:6] != b"\x7fELF\x02\x01":
        raise RuntimeError("Expected a little-endian ELF64 executable")
    machine = struct.unpack_from("<H", data, 18)[0]
    offset = struct.unpack_from("<Q", data, 40)[0]
    entry_size, count = struct.unpack_from("<HH", data, 58)
    if entry_size < 64 or not count:
        raise RuntimeError("ELF section headers are required to verify compatibility")
    sections = [
        struct.unpack_from("<IIQQQQIIQQ", data, offset + i * entry_size)
        for i in range(count)
    ]
    versions = []
    for section in sections:
        if section[1] != 0x6FFFFFFE:  # SHT_GNU_verneed
            continue
        strings_section = sections[section[6]]
        strings = data[strings_section[4] : strings_section[4] + strings_section[5]]
        cursor, end = section[4], section[4] + section[5]
        while cursor < end:
            _, auxiliary_count, _, auxiliary_offset, next_offset = struct.unpack_from(
                "<HHIII", data, cursor
            )
            auxiliary = cursor + auxiliary_offset
            for _ in range(auxiliary_count):
                _, _, _, name_offset, next_auxiliary = struct.unpack_from(
                    "<IHHII", data, auxiliary
                )
                name = strings[name_offset : strings.index(b"\0", name_offset)].decode(
                    "ascii"
                )
                if name.startswith("GLIBC_") and name[6:7].isdigit():
                    versions.append(tuple(int(part) for part in name[6:].split(".")))
                elif name.startswith("GLIBC_"):
                    raise RuntimeError(f"Unrecognized glibc ABI requirement: {name}")
                auxiliary += next_auxiliary
            if not next_offset:
                break
            cursor += next_offset
    return machine, versions


def check_binary(data: bytes, system: str, machine: str) -> None:
    if system.startswith("linux"):
        architecture, versions = elf_requirements(data)
        if architecture != {"x86_64": 62, "arm64": 183}[machine]:
            raise RuntimeError("ELF architecture does not match its wheel")
        if system == "linux" and (not versions or max(versions) > (2, 28)):
            raise RuntimeError(
                f"ELF glibc requirements {versions} exceed the manylinux_2_28 tag"
            )
        if system == "linux-musl" and versions:
            raise RuntimeError("A musllinux wheel must not require glibc")
    elif system == "darwin":
        if data[:4] != b"\xcf\xfa\xed\xfe":
            raise RuntimeError("Expected a Mach-O 64-bit executable")
        architecture = struct.unpack_from("<I", data, 4)[0]
        if architecture != {"x86_64": 0x01000007, "arm64": 0x0100000C}[machine]:
            raise RuntimeError("Mach-O architecture does not match its wheel")
        commands = struct.unpack_from("<I", data, 16)[0]
        cursor = 32
        minimum = None
        for _ in range(commands):
            command, size = struct.unpack_from("<II", data, cursor)
            if size < 8:
                raise RuntimeError("Invalid Mach-O load command")
            if command in (0x24, 0x32):
                encoded = struct.unpack_from(
                    "<I", data, cursor + (8 if command == 0x24 else 12)
                )[0]
                minimum = (encoded >> 16, (encoded >> 8) & 255, encoded & 255)
            cursor += size
        advertised = (11, 0, 0) if machine == "arm64" else (10, 12, 0)
        if minimum is None or minimum > advertised:
            raise RuntimeError(
                f"Mach-O minimum {minimum} exceeds advertised macOS {advertised}"
            )
    elif system == "windows":
        if data[:2] != b"MZ":
            raise RuntimeError("Expected a Windows PE executable")
        pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
        if (
            data[pe_offset : pe_offset + 4] != b"PE\0\0"
            or struct.unpack_from("<H", data, pe_offset + 4)[0] != 0x8664
        ):
            raise RuntimeError("Expected a Windows x64 PE executable")
