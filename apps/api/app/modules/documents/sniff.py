"""Upload type checks (pure): extension allow-list + magic-byte sniffing (spec §5.5).

The declared ``Content-Type`` is never trusted: the stored type is what the bytes say, and it must agree with
the file extension. Anything else is rejected.
"""

from dataclasses import dataclass

# extension → canonical media type
ALLOWED_EXTENSIONS: dict[str, str] = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "heic": "image/heic",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
}
_ZIP_TYPES = {ALLOWED_EXTENSIONS["docx"], ALLOWED_EXTENSIONS["xlsx"]}
_HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"}


class UnsupportedFileError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FileType:
    extension: str
    media_type: str


def extension_of(filename: str) -> str:
    _, dot, ext = filename.rpartition(".")
    return ext.lower() if dot else ""


def type_for_filename(filename: str) -> FileType:
    ext = extension_of(filename)
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise UnsupportedFileError(f"File type .{ext or '?'} is not allowed (allowed: {allowed})")
    return FileType(ext, ALLOWED_EXTENSIONS[ext])


def sniff(head: bytes) -> str | None:  # noqa: PLR0911 - one return per signature reads best
    """Media type from the first bytes, or ``None`` if unrecognised."""
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] in _HEIC_BRANDS:
        return "image/heic"
    if head.startswith(b"PK\x03\x04"):
        return "application/zip"
    if head and b"\x00" not in head:
        try:
            head.decode("utf-8")
        except UnicodeDecodeError:
            # A multi-byte character may be cut at the boundary; retry without the last 3 bytes.
            try:
                head[:-3].decode("utf-8")
            except UnicodeDecodeError:
                return None
        return "text/plain"
    return None


def verify(filename: str, head: bytes) -> str:
    """The media type to store, or raise if the content does not match the extension."""
    expected = type_for_filename(filename).media_type
    actual = sniff(head)
    matches = (
        actual == expected
        or (actual == "application/zip" and expected in _ZIP_TYPES)
        or (actual == "text/plain" and expected == "text/csv")
    )
    if not matches:
        raise UnsupportedFileError(
            f"File content ({actual or 'unknown'}) does not match its extension (.{extension_of(filename)})"
        )
    return expected
