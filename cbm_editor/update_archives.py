import hashlib
import os
import stat
import tarfile
import zipfile
from pathlib import Path


MAX_UPDATE_FILE_SIZE = 4 * 1024 * 1024 * 1024


def _copy_and_hash(source, destination, expected_size, cancelled=None):
    digest = hashlib.sha256()
    received = 0
    try:
        with Path(destination).open("xb") as output:
            while True:
                if cancelled is not None and cancelled():
                    raise InterruptedError()
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > expected_size:
                    raise RuntimeError("The extracted update is larger than declared by its archive.")
                output.write(chunk)
                digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        Path(destination).unlink(missing_ok=True)
        raise
    if received != expected_size:
        Path(destination).unlink(missing_ok=True)
        raise RuntimeError("The extracted update is incomplete.")
    return received, digest.hexdigest()


def extract_windows_executable_archive(archive_path, destination, expected_name, cancelled=None):
    archive_path = Path(archive_path)
    destination = Path(destination)
    expected_name = str(expected_name)
    if Path(expected_name).name != expected_name or not expected_name.casefold().endswith(".exe"):
        raise RuntimeError("The expected Windows executable filename is invalid.")

    with zipfile.ZipFile(archive_path, mode="r") as archive:
        members = [member for member in archive.infolist() if member.filename == expected_name]
        if len(members) != 1:
            raise RuntimeError(f"The Windows update archive must contain exactly one {expected_name} file.")
        member = members[0]
        unix_mode = (member.external_attr >> 16) & 0xFFFF
        if (
            member.filename != expected_name
            or member.is_dir()
            or member.flag_bits & 0x1
            or (unix_mode & 0o170000) not in (0, stat.S_IFREG)
        ):
            raise RuntimeError("The Windows update archive contains an invalid entry.")
        if member.file_size <= 0 or member.file_size > MAX_UPDATE_FILE_SIZE:
            raise RuntimeError("The archived Windows executable has an invalid size.")
        with archive.open(member, mode="r") as source:
            return _copy_and_hash(source, destination, member.file_size, cancelled)


def extract_linux_appimage_archive(archive_path, destination, expected_name, cancelled=None):
    archive_path = Path(archive_path)
    destination = Path(destination)
    expected_name = str(expected_name)
    if Path(expected_name).name != expected_name or not expected_name.endswith(".AppImage"):
        raise RuntimeError("The expected AppImage filename is invalid.")
    with tarfile.open(archive_path, mode="r:gz") as archive:
        members = [member for member in archive.getmembers() if member.name == expected_name]
        if len(members) != 1:
            raise RuntimeError(f"The Linux update archive must contain exactly one {expected_name} file.")
        member = members[0]
        if member.name != expected_name or not member.isfile() or member.issym() or member.islnk():
            raise RuntimeError("The Linux update archive contains an invalid entry.")
        if member.size <= 0 or member.size > MAX_UPDATE_FILE_SIZE:
            raise RuntimeError("The archived AppImage has an invalid size.")
        source = archive.extractfile(member)
        if source is None:
            raise RuntimeError("The archived AppImage could not be opened.")
        try:
            return _copy_and_hash(source, destination, member.size, cancelled)
        finally:
            source.close()
