"""Mux pre-recorded, offline Windows TTS segments to a fixed 96-second MP4.

All inputs/outputs live in an ignored local acceptance/logs directory.
No accounts, browser profile, network, API keys, third-party services or
synthetic sponsor claims. Voice WAVs were made with Windows System.Speech.
"""
from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "acceptance" / "logs" / "judge-video-20261023"
VOICES = OUT / "voiceover-draft"
SILENT = OUT / "EvidenceTrail_Track02_Actual_Demo_DRAFT_v3_2026-10-23.mp4"
PCM_FILE = OUT / "offline_voiceover_96_seconds.wav"
NARRATED = OUT / "EvidenceTrail_Track02_Actual_Demo_NARRATED_DRAFT_v4_2026-10-23.mp4"
STARTS = [0, 9, 21, 33, 45, 59, 71, 83]
SECONDS = 96
SAMPLE_RATE = 22050


def run(args: list[str], timeout: int) -> str:
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                       timeout=timeout, check=False)
    if p.returncode:
        raise RuntimeError(f"PROCESS_FAILED_{args[0]}_{p.returncode}: {p.stderr[-900:]}")
    return p.stdout


def build_pcm() -> None:
    total = SAMPLE_RATE * SECONDS
    pcm = bytearray(total * 2)
    for i, sec in enumerate(STARTS):
        path = VOICES / f"voice-{i:02d}.wav"
        with wave.open(str(path), "rb") as f:
            channels, sw, rate = f.getnchannels(), f.getsampwidth(), f.getframerate()
            if (channels, sw, rate) != (1, 2, SAMPLE_RATE):
                raise ValueError(f"UNEXPECTED_PCM_FORMAT_{i}: {(channels, sw, rate)}")
            chunk = f.readframes(f.getnframes())
        max_samples = ((STARTS[i+1] if i+1 < len(STARTS) else SECONDS) - sec) * SAMPLE_RATE
        if len(chunk) > max_samples * 2:
            raise ValueError(f"VOICE_SEGMENT_EXCEEDS_SCENE_{i}")
        byte_offset = sec * SAMPLE_RATE * 2
        pcm[byte_offset:byte_offset+len(chunk)] = chunk
        print(f"SEGMENT_{i}_START={sec}_ACTUAL_DURATION={len(chunk)/2/SAMPLE_RATE:.3f}s")
    with wave.open(str(PCM_FILE), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(pcm)


def main() -> None:
    if not SILENT.exists():
        raise FileNotFoundError("VERIFIED_SILENT_V3_INPUT_MISSING")
    build_pcm()
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(SILENT), "-i", str(PCM_FILE),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-af", "afade=t=out:st=94:d=2",
         "-t", str(SECONDS), "-movflags", "+faststart", str(NARRATED)], 50)
    meta = json.loads(run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,size:stream=codec_type,codec_name,width,height",
         "-of", "json", str(NARRATED)], 20))
    streams = {s["codec_type"]: s for s in meta["streams"]}
    duration = float(meta["format"]["duration"])
    if set(streams) != {"video", "audio"}:
        raise RuntimeError("MISSING_NARRATED_AUDIO_OR_VIDEO_TRACK")
    if streams["video"]["codec_name"] != "h264" or streams["audio"]["codec_name"] != "aac":
        raise RuntimeError("UNEXPECTED_VIDEO_AUDIO_CODECS")
    if abs(duration - SECONDS) > 0.1:
        raise RuntimeError(f"VIDEO_DURATION_MISMATCH_{duration}")
    # Decode the entire result, not just its container header.
    run(["ffmpeg", "-v", "error", "-i", str(NARRATED), "-f", "null", "NUL"], 35)
    print(f"VOICED_DRAFT_VERIFIED duration={duration:.3f}s size={meta['format']['size']}")
    print(f"VIDEO={NARRATED}")
    print("AUDIO_AND_VIDEO_DECODING_PASS; no vendor or network calls")


if __name__ == "__main__":
    main()
