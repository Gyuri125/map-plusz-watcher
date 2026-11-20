"""Multipart/form-data kódolás fájlfeltöltéshez (Discord, Telegram)."""

from __future__ import annotations

import uuid


def encode_multipart(
    fields: dict[str, str],
    files: list[tuple[str, str, str, bytes]],
) -> tuple[bytes, str]:
    """Összeállít egy multipart body-t és a hozzá tartozó Content-Type-ot.

    A ``files`` elemei: (mezőnév, fájlnév, MIME-típus, tartalom).
    """
    boundary = "----MapPlusz" + uuid.uuid4().hex
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("ascii"))
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii")
        )
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    for field_name, filename, content_type, data in files:
        chunks.append(f"--{boundary}\r\n".encode("ascii"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{filename}"\r\n'
            ).encode("ascii")
        )
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode("ascii"))
        chunks.append(data)
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    body = b"".join(chunks)
    return body, f"multipart/form-data; boundary={boundary}"
