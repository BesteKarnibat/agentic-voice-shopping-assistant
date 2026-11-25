from app import view
from app.pipeline import run_turn
from tts import make_tts_node


class FakeTTS:
    extension = "mp3"

    def __init__(self):
        self.spoken = []

    def stream(self, text):
        self.spoken.append(text)
        yield b"x"


def _row(rank, title, src="catalog"):
    return {"rank": rank, "title": title, "brand": None, "price": 9.5, "price_source": src, "rating": 4.5,
            "ingredients": None, "doc_id": f"d{rank}", "live_url": None, "citation_markers": [f"[{rank}]"]}


def test_comparison_table_is_top3_in_agreed_columns():
    s = {"comparison_table": [_row(4, "D"), _row(2, "B", "web"), _row(1, "A"), _row(3, "C")]}
    rows = view.comparison_rows(s)
    assert [r["Product"] for r in rows] == ["A", "B", "C"]
    assert list(rows[0]) == ["Product", "Price", "Rating", "Ingredients", "Source", "Citation"]
    assert rows[0]["Price"] == "$9.50" and rows[0]["Ingredients"] == "unknown"
    assert rows[1]["Source"] == "Live web" and rows[0]["Citation"] == "[1]"


def test_citation_helpers():
    s = {
        "comparison_table": [_row(1, "A")],
        "citations": [
            {"marker": "[1]", "source_type": "private", "doc_id": "d1", "url": None, "title": "A"},
            {"marker": "[2]", "source_type": "web", "doc_id": None, "url": "https://x.test/a", "title": "A live"}],
        "step_log": [{"timestamp": "2026-01-01T10:20:30+00:00", "node": "router", "summary": "s", "details": {}}],
    }
    private, web = view.split_citations(s)
    assert len(private) == 1 and len(web) == 1
    assert view.private_doc_ids(s) == ["d1"]
    assert view.live_links(s) == [{"url": "https://x.test/a", "title": "A live"}]
    assert view.step_rows(s)[0]["time"] == "10:20:30"


def test_reply_and_route_for_clarification_and_refusal():
    clar = {"intent": "unclear", "clarification_question": "What surface is it for?"}
    assert view.reply_text(clar) == "What surface is it for?"
    assert "Asked to clarify" in view.route_summary(clar)
    unsafe = {"intent": "unsafe", "final_answer": "I can't help mix cleaners.",
              "safety": {"is_safe": False, "category": "chemical_mixing", "reason": None}}
    assert view.reply_text(unsafe).startswith("I can't")
    assert "chemical_mixing" in view.route_summary(unsafe)
    assert view.comparison_rows({}) == [] and view.reply_text({}) == ""


def test_without_agent_only_asr_runs(monkeypatch):
    import app.pipeline as p

    monkeypatch.setattr(p, "load_agent", lambda: None)
    state, mode = run_turn(text="hello")
    assert mode == "asr_only" and state["transcript"] == "hello"
    assert "final_answer" not in state and "tts_audio_path" not in state


def test_run_agent_called_with_transcript_then_tts(tmp_path):
    seen = []

    def run_agent(transcript):
        seen.append(transcript)
        return {"transcript": "overwritten?", "final_answer": "Pick A [1].", "spoken_summary": "Pick A.",
                "step_log": [{"timestamp": "", "node": "router", "summary": "ok", "details": {}}]}

    tts = FakeTTS()
    state, mode = run_turn(text="cleaner under $15", agent=run_agent,
                           tts_node=make_tts_node(tts, str(tmp_path)))
    assert mode == "agent" and seen == ["cleaner under $15"]
    assert state["transcript"] == "cleaner under $15"  # ASR transcript kept
    assert [e["node"] for e in state["step_log"]] == ["asr", "router", "tts"]
    assert tts.spoken == ["Pick A."] and state["tts_audio_path"].endswith(".mp3")


def test_clarification_is_spoken(tmp_path):
    tts = FakeTTS()
    state, _ = run_turn(text="I need a cleaner", agent=lambda t: {"clarification_question": "For which surface?"},
                        tts_node=make_tts_node(tts, str(tmp_path)))
    assert tts.spoken == ["For which surface?"] and state["tts_audio_path"]


def test_agent_exception_is_reported():
    def boom(t):
        raise RuntimeError("graph down")

    state, mode = run_turn(text="hi", agent=boom)
    assert mode == "agent" and any("graph down" in e for e in state["errors"])
