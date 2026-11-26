from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from .collector import collect
from .curator import curate
from .education import EDUCATION_TOPICS
from .script import education_script, news_script
from .storage import Storage
from .video import assemble_video, render_slides, synthesize
from .youtube import credentials_present, upload_short


def run(config: dict, slot: str) -> dict:
    storage = Storage()
    try:
        items = collect(config["news"]["sources"])
        candidates = curate(
            items,
            config["news"]["keywords"],
            int(config["news"]["window_hours"]),
            storage.seen_identity,
            storage.seen_item,
        )

        if candidates:
            item = candidates[0]
            kind = "news"
            identity = item.identity
            script = news_script(item)
            source = f"Fonte primaria: {item.source} - {item.url}"
            title = item.title[:100]
        else:
            kind = "education"
            topic_index = datetime.now(timezone.utc).toordinal() % len(EDUCATION_TOPICS)
            topic, citation = EDUCATION_TOPICS[topic_index]
            script = education_script(topic)
            identity = f"education:{topic_index}:{datetime.now(timezone.utc).date().isoformat()}"
            source = f"Fonte: {citation}"
            title = topic[:100]

        output_dir = Path("output") / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        slides = render_slides(script, source, output_dir)
        audio_path = output_dir / "narration.mp3"
        tts_created = synthesize(script, audio_path)
        video_path = output_dir / "short.mp4"
        video_created = assemble_video(
            slides,
            audio_path if tts_created else None,
            video_path,
            int(config["video"]["duration_seconds"]),
        )
        result = {
            "kind": kind,
            "identity": identity,
            "script": script,
            "source": source,
            "title": title,
            "output_dir": str(output_dir),
            "tts_created": tts_created,
            "video_created": video_created,
            "status": "review_ready",
        }

        auto_publish = os.getenv("YOUTUBE_AUTO_PUBLISH", "").strip().casefold() == "true"
        if not auto_publish:
            if kind == "news" and video_created:
                storage.mark_seen(
                    identity,
                    candidates[0].title,
                    candidates[0].url,
                    candidates[0].source,
                    candidates[0].published_at.isoformat(),
                )
            storage.record_publication(slot, kind, identity, "review_pending")
            return result

        upload_count = storage.daily_upload_count()
        daily_cost = storage.daily_quota_cost()
        upload_cost = int(config["publish"]["youtube_quota_upload_cost"])
        if upload_count >= int(config["publish"]["max_daily_uploads"]):
            storage.record_publication(slot, kind, identity, "skipped_daily_upload_limit")
            result["status"] = "skipped_daily_upload_limit"
            return result
        if daily_cost + upload_cost > 10000:
            storage.record_publication(slot, kind, identity, "skipped_daily_quota")
            result["status"] = "skipped_daily_quota"
            return result

        if not credentials_present():
            logging.warning("YouTube credentials missing; review package retained")
            storage.record_publication(slot, kind, identity, "skipped_missing_credentials")
            result["status"] = "skipped_missing_credentials"
            return result

        video_path = output_dir / "short.mp4"
        if not video_path.exists():
            storage.record_publication(slot, kind, identity, "skipped_no_video")
            result["status"] = "skipped_no_video"
            return result

        upload = upload_short(
            video_path,
            title,
            f"{script}\n\n{source}",
            ["reforma tributaria", "educacao financeira", "YouTube Shorts"],
        )
        status = upload["status"]
        storage.record_publication(
            slot,
            kind,
            identity,
            status,
            upload.get("video_id"),
            upload.get("video_url"),
            config["publish"]["youtube_quota_upload_cost"] if status == "uploaded" else 0,
        )
        if kind == "news" and status == "uploaded":
            storage.mark_seen(
                identity,
                candidates[0].title,
                candidates[0].url,
                candidates[0].source,
                candidates[0].published_at.isoformat(),
            )
        result.update(upload)
        return result
    finally:
        storage.close()
