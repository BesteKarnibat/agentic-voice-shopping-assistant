from tts import build_spoken_summary, make_tts_node


class FakeBackend:
    extension = "mp3"

    def __init__(self, fail=False):
        self.fail, self.texts = fail, []

    def stream(self, text):
        if self.fail:
            raise RuntimeError("boom")
        self.texts.append(text)
        yield b"abc"
        yield b"def"


def test_summary_strips_markers_and_limits_words():
    s = build_spoken_summary("Try Catan Junior [1], only $19 **today**. " + "More words. " * 40)
    assert "[1]" not in s and "*" not in s
    assert len(s.split()) <= 40 and s.endswith(".")


def test_summary_falls_back_to_final_answer_and_hard_trims():
    assert build_spoken_summary("", "Top pick is Seventh Generation [2].") == "Top pick is Seventh Generation."
    long = build_spoken_summary("word " * 100)
    assert len(long.split()) == 40


def test_node_writes_audio(tmp_path):
    b = FakeBackend()
    out = make_tts_node(b, str(tmp_path))({"session_id": "s1", "spoken_summary": "Hello [1]."})
    assert open(out["tts_audio_path"], "rb").read() == b"abcdef"
    assert b.texts == ["Hello."] and out["step_log"][0]["node"] == "tts"


def test_node_failure_and_empty(tmp_path):
    out = make_tts_node(FakeBackend(fail=True), str(tmp_path))({"spoken_summary": "Hi."})
    assert out["tts_audio_path"] is None and out["errors"]
    assert make_tts_node(FakeBackend(), str(tmp_path))({})["errors"]


def test_lead_in_silence_prepended_to_pcm(tmp_path):
    import wave

    from tts.synthesizer import synthesize_to_file

    class Pcm:
        extension, pcm_rate = "wav", 24000

        def stream(self, text):
            yield b"\x01\x00" * 100

    p = synthesize_to_file("hi", str(tmp_path), "x", Pcm(), lead_in_ms=500)
    with wave.open(p) as w:
        assert w.getframerate() == 24000 and w.getnframes() == 12000 + 100
        assert w.readframes(1) == b"\x00\x00"
