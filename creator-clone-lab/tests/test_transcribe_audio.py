from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import transcribe_audio


class TranscribeProviderOrderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.media = Path("sample.mp4")

    @patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=True)
    @patch.object(transcribe_audio, "transcribe_local")
    @patch.object(transcribe_audio, "has_local_whisper", return_value=True)
    @patch.object(transcribe_audio, "transcribe_groq", return_value="groq transcript")
    def test_auto_prefers_groq(self, groq, _has_local, local) -> None:
        transcript, provider = transcribe_audio.transcribe_auto(self.media, "zh", "groq-model", "small")
        self.assertEqual((transcript, provider), ("groq transcript", "groq"))
        groq.assert_called_once()
        local.assert_not_called()

    @patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=True)
    @patch.object(transcribe_audio, "transcribe_local", return_value="local transcript")
    @patch.object(transcribe_audio, "has_local_whisper", return_value=True)
    @patch.object(transcribe_audio, "transcribe_groq", side_effect=RuntimeError("network unavailable"))
    def test_auto_falls_back_locally_when_groq_fails(self, _groq, _has_local, local) -> None:
        transcript, provider = transcribe_audio.transcribe_auto(self.media, "zh", "groq-model", "small")
        self.assertEqual((transcript, provider), ("local transcript", "local-fallback"))
        local.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    @patch.object(transcribe_audio, "transcribe_local", return_value="local transcript")
    @patch.object(transcribe_audio, "has_local_whisper", return_value=True)
    @patch.object(transcribe_audio, "transcribe_groq")
    def test_auto_uses_local_when_groq_is_not_configured(self, groq, _has_local, local) -> None:
        transcript, provider = transcribe_audio.transcribe_auto(self.media, "zh", "groq-model", "small")
        self.assertEqual((transcript, provider), ("local transcript", "local"))
        groq.assert_not_called()
        local.assert_called_once()


if __name__ == "__main__":
    unittest.main()
