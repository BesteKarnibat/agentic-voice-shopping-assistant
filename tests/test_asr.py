import numpy as np

from asr import StreamingASR, make_asr_node
from asr.transcriber import Segment, TranscriptionResult


class Fake:
    def __init__(self, text="recommend a cleaner under fifteen dollars"):
        self.text = text
        self.calls = []

    def transcribe(self, audio):
        self.calls.append(audio)
        seg = Segment(0.0, 1.5, self.text)
        return TranscriptionResult(self.text, [seg] if self.text else [], "en", 0.99, 1.5, 0.1)


def test_node_sets_transcript_and_segments():
    out = make_asr_node(Fake())({"audio_path": "x.wav"})
    assert out["transcript"].startswith("recommend")
    assert out["asr_segments"][0]["start"] == 0.0
    assert out["step_log"][0]["node"] == "asr"


def test_node_empty_speech_and_missing_input():
    assert "errors" in make_asr_node(Fake(""))({"audio_path": "x.wav"})
    assert "errors" in make_asr_node(Fake())({})
    assert "errors" not in make_asr_node(Fake())({"transcript": "hi"})


def test_streaming_endpointing():
    f = Fake()
    s = StreamingASR(f, silence_s=0.5)

    def chunk(amp):  # 0.1 s of audio
        return np.full(1600, int(amp * 32767), dtype=np.int16).tobytes()

    assert s.feed(chunk(0.0)) is None  # leading silence ignored
    for _ in range(5):
        assert s.feed(chunk(0.3)) is None
    res = None
    for _ in range(5):
        res = s.feed(chunk(0.0)) or res
    assert res and res.text and len(f.calls) == 1
