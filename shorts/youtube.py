from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any


def credentials_present() -> bool:
    return bool(
        os.getenv("YOUTUBE_CLIENT_ID")
        and os.getenv("YOUTUBE_CLIENT_SECRET")
        and os.getenv("YOUTUBE_REFRESH_TOKEN")
    )


def upload_short(video_path: str | Path, title: str, description: str, tags: list[str] | None = None) -> dict[str, Any]:
    if not credentials_present():
        logging.warning("YouTube credentials missing; publication skipped")
        return {"status": "skipped", "reason": "credentials_missing"}

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    credentials = Credentials(
        token=os.getenv("YOUTUBE_ACCESS_TOKEN"),
        refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("YOUTUBE_CLIENT_ID"),
        client_secret=os.getenv("YOUTUBE_CLIENT_SECRET"),
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    if credentials.expired or not credentials.valid:
        credentials.refresh(Request())

    youtube = build("youtube", "v3", credentials=credentials)
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags or [],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/*", resumable=True)
    response = (
        youtube.videos()
        .insert(part="snippet,status", body=body, media_body=media)
        .execute()
    )
    video_id = response["id"]
    return {
        "status": "uploaded",
        "video_id": video_id,
        "video_url": f"https://youtube.com/shorts/{video_id}",
    }
