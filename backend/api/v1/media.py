"""Media file serving — stored WAV/MP4 outputs.

resolve_path performs strict file-id validation (UUID-hex + whitelisted
extension) so this endpoint cannot be used for path traversal.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.services.storage.local import get_storage

router = APIRouter()

_CONTENT_TYPES = {
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".png": "image/png",
    ".jpg": "image/jpeg",
}


@router.get("/media/{file_id}")
async def get_media(file_id: str) -> FileResponse:
    path = get_storage().resolve_path(file_id)
    if path is None:
        raise HTTPException(status_code=404, detail="File not found")
    ext = "." + file_id.rsplit(".", 1)[-1]
    return FileResponse(path, media_type=_CONTENT_TYPES.get(ext, "application/octet-stream"))
