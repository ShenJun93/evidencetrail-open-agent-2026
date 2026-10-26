"""Fail-closed local narrator/validator for a genuine 180-second Edge demo.

No network calls, user secrets, cloud models, ffmpeg downloads or arbitrary
outside paths. A named session is required to prevent mixing the wrong movie.
Output: Git-ignored voiced REVIEW, not an owner-approved submission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SESSIONS = ROOT / "acceptance" / "logs" / "prize-video-local"
SILENT = "EvidenceTrail_Counterfactual_DEMO_SILENT_REVIEW.mp4"
NARRATED = "EvidenceTrail_Counterfactual_DEMO_NARRATED_REVIEW.mp4"
PCM = "voiceover-180s-mixed.wav"
VOICE_DIR = "voiceover-180s"
STARTS = (0, 13, 40, 59, 91, 126, 152, 169)
SECONDS = 180
SAMPLE_RATE = 22050
NAME_PATTERN = re.compile(r"\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d-\d{3}Z-record\Z")


class LocalMediaError(ValueError):
    pass


def session_path(name: str) -> Path:
    if not NAME_PATTERN.fullmatch(name):
        raise LocalMediaError("INVALID_LOCAL_RECORDING_SESSION")
    path = SESSIONS / name
    if not path.is_dir() or path.is_symlink():
        raise LocalMediaError("LOCAL_RECORDING_SESSION_NOT_FOUND")
    if path.resolve().parent != SESSIONS.resolve():
        raise LocalMediaError("SESSION_ESCAPES_APPROVED_LOCAL_DIRECTORY")
    return path


def run(args: list[str], limit: int) -> str:
    try:
        p = subprocess.run(args, cwd=ROOT, capture_output=True,
                           encoding="utf-8", errors="replace",
                           timeout=limit, check=False)
    except (OSError, subprocess.SubprocessError):
        raise LocalMediaError("LOCAL_FFMPEG_OR_FFPROBE_UNAVAILABLE") from None
    if p.returncode != 0:
        raise LocalMediaError("LOCAL_MEDIA_COMMAND_FAILED")
    return p.stdout


def probe(path: Path) -> dict:
    try:
        info = json.loads(run([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,width,height",
            "-of", "json", str(path)], 20))
    except (TypeError, KeyError, ValueError):
        raise LocalMediaError("LOCAL_FFPROBE_FORMAT_INVALID") from None
    return info


def check_video(path: Path, require_audio: bool) -> dict:
    if not path.is_file() or path.stat().st_size < 100_000:
        raise LocalMediaError("LOCAL_VIDEO_MISSING_OR_TOO_SMALL")
    meta = probe(path)
    try:
        duration = float(meta["format"]["duration"])
        streams = {s["codec_type"]: s for s in meta["streams"]}
        expected = {"video", "audio"} if require_audio else {"video"}
        if set(streams) != expected:
            raise LocalMediaError("UNEXPECTED_VIDEO_STREAMS")
        if streams["video"]["codec_name"] != "h264":
            raise LocalMediaError("VIDEO_NOT_H264")
        if require_audio and streams["audio"]["codec_name"] != "aac":
            raise LocalMediaError("AUDIO_NOT_AAC")
        if abs(duration - SECONDS) > 0.5:
            raise LocalMediaError("VIDEO_DURATION_OUTSIDE_180_SECONDS")
        if streams["video"].get("width") != 1440 or streams["video"].get("height") != 900:
            raise LocalMediaError("VIDEO_DIMENSIONS_DIFFER_FROM_CAPTURE")
    except (TypeError, KeyError, ValueError):
        raise LocalMediaError("LOCAL_VIDEO_PROBE_FIELDS_INVALID") from None
    return {"duration": duration, "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def build_pcm(dir_path: Path) -> dict:
    voicedir = dir_path / VOICE_DIR
    if not voicedir.is_dir() or voicedir.is_symlink():
        raise LocalMediaError("VOICE_DIRECTORY_MISSING")
    voice_paths = [voicedir / f"voice-{i:02d}.wav" for i in range(8)]
    chunks = []
    timings = []
    for i, wav in enumerate(voice_paths):
        if not wav.is_file() or wav.is_symlink():
            raise LocalMediaError("VOICE_WAV_MISSING")
        try:
            with wave.open(str(wav), "rb") as f:
                if (f.getnchannels(), f.getsampwidth(), f.getframerate(),
                    f.getcomptype()) != (1, 2, SAMPLE_RATE, "NONE"):
                    raise LocalMediaError("VOICE_PCM_FORMAT_UNSUPPORTED")
                n = f.getnframes()
                chunk = f.readframes(n)
        except (OSError, EOFError, wave.Error):
            raise LocalMediaError("VOICE_WAV_CORRUPT") from None
        next_start = STARTS[i + 1] if i + 1 < len(STARTS) else SECONDS
        gap = next_start - STARTS[i]
        if not chunk or len(chunk) != n * 2 or n > gap * SAMPLE_RATE:
            raise LocalMediaError("VOICE_EXCEEDS_ITS_SCENE_WINDOW")
        chunks.append(chunk)
        timings.append(round(n / SAMPLE_RATE, 2))
    # Validate ALL eight parts and lengths before writing a mixed file.
    pcm_file = dir_path / PCM
    if pcm_file.exists() or pcm_file.is_symlink():
        raise LocalMediaError("MIXED_WAV_ALREADY_EXISTS")
    mixed = bytearray(SECONDS * SAMPLE_RATE * 2)
    for sec, data in zip(STARTS, chunks):
        start = sec * SAMPLE_RATE * 2
        mixed[start:start + len(data)] = data
    with wave.open(str(pcm_file), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(mixed)
    return {"voice_seconds_by_scene": timings, "mixed_wav": PCM}


def run_mix(session: str, do_mix: bool) -> dict:
    local = session_path(session)
    src = local / SILENT
    video = check_video(src, require_audio=False)
    if not do_mix:
        return {"status": "SILENT_INPUT_FFPROBE_PASS",
                "session": session, "duration": video["duration"],
                "silent_sha256": video["sha256"], "no_external_calls": True}
    dst = local / NARRATED
    evidence = local / "voiced-review-status.json"
    if dst.exists() or dst.is_symlink() or evidence.exists() or evidence.is_symlink():
        raise LocalMediaError("VOICE_REVIEW_OUTPUT_ALREADY_EXISTS")
    pcm = build_pcm(local)
    run(["ffmpeg", "-n", "-hide_banner", "-loglevel", "error",
         "-i", str(src), "-i", str(local / PCM),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-af", "afade=t=out:st=178:d=2",
         "-t", str(SECONDS), "-movflags", "+faststart", str(dst)], 100)
    result = check_video(dst, require_audio=True)
    run(["ffmpeg", "-v", "error", "-i", str(dst),
         "-f", "null", "NUL"], 100)
    audit = {
        "kind": "EVIDENCETRAIL_COUNTERFACTUAL_VOICED_REVIEW_V1",
        "status": "OFFLINE_MUX_AND_FULL_DECODE_PASS",
        "session": session,
        "duration_seconds": result["duration"],
        "input_video_sha256": video["sha256"],
        "narrated_sha256": result["sha256"],
        "narrated_bytes": result["bytes"],
        "voice_seconds_by_scene": pcm["voice_seconds_by_scene"],
        "voiceover": "LOCAL_WINDOWS_SYSTEM_SPEECH",
        "source_footage": "LOCALHOST_ISOLATED_EDGE_SAMPLE_ONLY",
        "human_visual_review_complete": False,
        "nvidia_model_inference_verified": False,
        "sponsor_eligibility_verified": False,
        "video_submitted": False
    }
    evidence.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return {"status": audit["status"], "video": str(dst),
            "duration": result["duration"], "bytes": result["bytes"],
            "sha256": result["sha256"], "submission_ready": False}


def main() -> int:
    p = argparse.ArgumentParser(description="Offline 180-second research-video narration")
    action = p.add_mutually_exclusive_group(required=True)
    action.add_argument("--verify-input", action="store_true")
    action.add_argument("--mix", action="store_true")
    p.add_argument("--session", required=True)
    args = p.parse_args()
    try:
        result = run_mix(args.session, do_mix=args.mix)
    except (LocalMediaError, OSError) as e:
        print(json.dumps({"status": "BLOCKED",
                          "code": str(e) if isinstance(e, LocalMediaError)
                          else "LOCAL_FILE_IO_FAILED"}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
