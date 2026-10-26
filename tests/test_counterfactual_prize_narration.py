"""Fixture-only timing and trust-boundary checks for 180s prize narration."""
from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import mix_counterfactual_prize_narration as m


class PrizeNarrationOfflineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.session = "2026-10-23T20-14-02-315Z-record"
        self.folder = self.root / self.session
        self.voices = self.folder / m.VOICE_DIR
        self.voices.mkdir(parents=True)
        for i in range(8):
            with wave.open(str(self.voices / f"voice-{i:02d}.wav"), "wb") as f:
                f.setnchannels(1); f.setsampwidth(2); f.setframerate(m.SAMPLE_RATE)
                f.writeframes(b"\x00\x00" * (m.SAMPLE_RATE // 10))

    def test_scene_schedule_covers_180_seconds(self):
        self.assertEqual(m.SECONDS, 180)
        self.assertEqual(m.STARTS, (0, 13, 40, 59, 91, 126, 152, 169))
        self.assertEqual(len(m.STARTS), 8)
        self.assertTrue(all(a < b for a, b in zip(m.STARTS, (*m.STARTS[1:], m.SECONDS))))

    def test_session_paths_reject_traversal_and_sibling(self):
        with patch.object(m, "SESSIONS", self.root):
            for bad in ("../elsewhere", "abc", "2026-10-23T20-14-02-315Z-shots"):
                with self.subTest(value=bad), self.assertRaises(m.LocalMediaError):
                    m.session_path(bad)
            self.assertEqual(m.session_path(self.session), self.folder)

    def test_bounded_eight_voice_chunks_create_exact_180sec_wav(self):
        receipt = m.build_pcm(self.folder)
        self.assertEqual(len(receipt["voice_seconds_by_scene"]), 8)
        with wave.open(str(self.folder / m.PCM), "rb") as f:
            self.assertEqual(f.getnframes(), m.SECONDS * m.SAMPLE_RATE)
            self.assertEqual(f.getnchannels(), 1)

    def test_refuse_missing_scene_or_existing_review_wav(self):
        m.build_pcm(self.folder)
        with self.assertRaisesRegex(m.LocalMediaError, "ALREADY_EXISTS"):
            m.build_pcm(self.folder)
        (self.folder / m.PCM).unlink()
        (self.voices / "voice-05.wav").unlink()
        with self.assertRaisesRegex(m.LocalMediaError, "VOICE_WAV_MISSING"):
            m.build_pcm(self.folder)

    def test_voice_longer_than_scene_is_refused_without_output(self):
        with wave.open(str(self.voices / "voice-07.wav"), "wb") as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(m.SAMPLE_RATE)
            f.writeframes(b"\x00\x00" * ((m.SECONDS - m.STARTS[-1] + 1) * m.SAMPLE_RATE))
        with self.assertRaisesRegex(m.LocalMediaError, "EXCEEDS"):
            m.build_pcm(self.folder)
        self.assertFalse((self.folder / m.PCM).exists())


if __name__ == "__main__":
    unittest.main()
