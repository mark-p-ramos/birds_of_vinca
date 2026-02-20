import subprocess

import cv2
from moviepy import VideoFileClip, concatenate_videoclips


async def curate_videos(urls: list[str]) -> list[str]:
    return []


def _normalize_to_constant_frame_rate(input_path, output_path, fps=30):
    # Convert a video to constant frame rate (CFR) using ffmpeg.
    # if os.path.exists(output_path):
    #     return output_path

    cmd = [
        "ffmpeg",
        "-y",  # overwrite output
        "-i",
        input_path,
        "-vf",
        f"fps={fps}",
        "-vsync",
        "cfr",
        "-movflags",
        "+faststart",
        output_path,
    ]

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return output_path


def curate_video():
    # ---------------- CONFIG ----------------
    VIDEO_PATH = "house-finch.mp4"
    VIDEO_CFR_PATH = "house-finch-cfr.mp4"
    OUTPUT_PATH = "output.mp4"

    FRAME_SKIP = 1
    MERGE_GAP_SECONDS = 1.5
    MIN_MOTION_AREA = 8000
    NO_MOTION_FRAMES_REQUIRED = 5  # 3–10 is typical

    # ----------------------------------------

    _normalize_to_constant_frame_rate(VIDEO_PATH, VIDEO_CFR_PATH)

    cap = cv2.VideoCapture(VIDEO_CFR_PATH)
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
    video = VideoFileClip(VIDEO_CFR_PATH)
    clips = [video.subclipped(s, e) for s, e in merged]

    if clips:
        final = concatenate_videoclips(clips, method="compose")
        final.write_videofile(OUTPUT_PATH, fps=video.fps, codec="libx264", audio_codec="aac")
    else:
        print("No significant motion detected. Output video not created.")
