import asyncio
import os
import shutil
import subprocess
import tempfile
from typing import Optional
from urllib.parse import unquote, urlparse

import cv2
import httpx
from moviepy import VideoFileClip, concatenate_videoclips

from curator.storage import GCS, unique_blob_name


async def curate_videos(urls: list[str]) -> list[str]:
    # fairly certain there is only ever one video even though it comes in a list
    url = urls[0]

    file_path, file_name, content_type = await download_video_to_tempdir(url)
    curated_path = _curate_video(file_path)
    if curated_path is None:
        return []

    blob_name = unique_blob_name("videos", file_name)
    await _upload_video(curated_path, blob_name, content_type)
    return blob_name


def _normalize_to_constant_frame_rate(input_path: str, fps: int = 30) -> None:
    """Convert a video to constant frame rate (CFR) in-place using ffmpeg."""
    fd, temp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)

    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vf",
            f"fps={fps}",
            "-vsync",
            "cfr",
            "-movflags",
            "+faststart",
            temp_path,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.replace(temp_path, input_path)
    except Exception:
        os.unlink(temp_path)
        raise


def _curate_video(file_path: str) -> str | None:
    # ---------------- CONFIG ----------------
    FRAME_SKIP = 1
    MERGE_GAP_SECONDS = 1.5
    MIN_MOTION_AREA = 8000
    NO_MOTION_FRAMES_REQUIRED = 5  # 3–10 is typical
    # ----------------------------------------

    _normalize_to_constant_frame_rate(file_path)

    cap = cv2.VideoCapture(file_path)
    fps = cap.get(cv2.CAP_PROP_FPS)

    bg_subtractor = cv2.createBackgroundSubtractorMOG2(
        history=500, varThreshold=50, detectShadows=True
    )

    segments = []
    current_start = None
    frame_idx = 0
    motion_frames = 0
    no_motion_frames = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % FRAME_SKIP == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)

            fg_mask = bg_subtractor.apply(blur)

            # Clean up noise
            fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)[1]
            fg_mask = cv2.dilate(fg_mask, None, iterations=2)

            contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            motion_detected = any(cv2.contourArea(cnt) >= MIN_MOTION_AREA for cnt in contours)

            time_sec = frame_idx / fps

            if motion_detected:
                motion_frames += 1
                no_motion_frames = 0

                if current_start is None:
                    current_start = time_sec

            else:
                no_motion_frames += 1
                motion_frames = 0

                if current_start is not None and no_motion_frames >= NO_MOTION_FRAMES_REQUIRED:
                    end_time = time_sec - (NO_MOTION_FRAMES_REQUIRED / fps)
                    segments.append((current_start, end_time))
                    current_start = None

        frame_idx += 1

    cap.release()

    if current_start is not None:
        segments.append((current_start, frame_idx / fps))

    # --------- MERGE CLOSE SEGMENTS ----------
    merged = []
    for start, end in segments:
        if not merged:
            merged.append([start, end])
        else:
            prev_start, prev_end = merged[-1]
            if start - prev_end <= MERGE_GAP_SECONDS:
                merged[-1][1] = end
            else:
                merged.append([start, end])

    # --------- CALCULATE OUTPUT DURATION ----------
    output_duration_seconds = sum(end - start for start, end in merged)
    print(f"Output duration: {output_duration_seconds:.2f} seconds")

    # --------- CUT VIDEO ---------------------
    video = VideoFileClip(file_path)
    clips = [video.subclipped(s, e) for s, e in merged]

    if clips:
        final = concatenate_videoclips(clips, method="compose")
        fd, output_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        final.write_videofile(output_path, fps=video.fps, codec="libx264", audio_codec="aac")
        return output_path

    print("No significant motion detected. Output video not created.")
    return None


async def _upload_video(
    file_path: str,
    blob_name: str,
    content_type: str,
) -> None:
    bucket = GCS.bucket
    blob = bucket.blob(blob_name)
    await asyncio.to_thread(blob.upload_from_filename, file_path, content_type=content_type)


async def download_video_to_tempdir(
    url: str,
    timeout: float = 30.0,
    max_size_mb: Optional[int] = 500,
) -> tuple[str, str, str]:
    """
    Downloads a video file from a URL to the system temp directory.

    Args:
        url: Video URL
        timeout: Request timeout in seconds
        max_size_mb: Optional max allowed file size (MB)

    Returns:
        (local file path, file name, content type)
    """

    parsed = urlparse(url)
    filename = unquote(parsed.path.split("/")[-1])
    if not filename:
        raise ValueError("Could not determine filename from URL")

    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, filename)
    content_type = ""

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")
            content_length = response.headers.get("Content-Length")
            if content_length and max_size_mb:
                size_mb = int(content_length) / (1024 * 1024)
                if size_mb > max_size_mb:
                    raise ValueError(f"Video too large ({size_mb:.2f} MB > {max_size_mb} MB)")

            with open(file_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)

    return (file_path, filename, content_type)


def _copy_to_temp(input_path: str) -> str:
    """Copy a file to the temp directory with a unique name. Return the new path."""
    _, ext = os.path.splitext(input_path)
    fd, temp_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    shutil.copy2(input_path, temp_path)
    return temp_path


async def main() -> None:
    # -- test upload video --
    # path = "/tmp/tmpxplzmony.mp4"
    # await _upload_video(path, "videos/test.mp4", "video/mp4")
    # print("upload complete")

    # -- test curate video --
    # input_path = "../../tests/videos/chickadee.mp4"
    # temp_path = _copy_to_temp(input_path)
    # curated_path = _curate_video(temp_path)
    # if curated_path is not None:
    #     print(curated_path)
    pass


if __name__ == "__main__":
    asyncio.run(main())
