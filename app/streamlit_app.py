"""Split-screen voice UI.  Run: uv run streamlit run app/streamlit_app.py

Left half: the voice chat (speak, upload or type; transcript and answer as chat bubbles; spoken reply).
Right half: everything the chat doesn't show for the latest answer: agent steps, comparison table,
citations, private document IDs, live-source links, timestamps and the critic's verdict.
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

# `streamlit run` puts app/ on sys.path, not the repo root; add it so asr/tts/app import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from app import view  # noqa: E402
from app.pipeline import run_turn  # noqa: E402
from config.paths import AUDIO_DIR  # noqa: E402

st.set_page_config(page_title="Voice Shopping Assistant", page_icon="🛒", layout="wide")

# Fill the browser window: both panes grow with the viewport height and scroll internally, leaving room
# under the chat for the upload expander and the chat box. The details panel uses the sidebar's colour
# (Streamlit's built-in sidebar background: #21201D dark, #F8F8F7 light).
_PANEL_BG = "#F8F8F7" if st.context.theme.type == "light" else "#21201D"
st.markdown(f"""
<style>
.block-container {{padding-top: 2.5rem; padding-bottom: 0.5rem; max-width: 100%;}}
[data-testid="stChatInput"] textarea {{max-height: 80px !important; min-height: 0 !important;}}
.st-key-chatbox, .st-key-detailpanel, .st-key-detailbox,
[data-testid="stLayoutWrapper"]:has(> .st-key-chatbox),
[data-testid="stLayoutWrapper"]:has(> .st-key-detailbox) {{flex: 0 0 auto !important;}}
[data-testid="stLayoutWrapper"]:has(> .st-key-chatbox),
[data-testid="stLayoutWrapper"]:has(> .st-key-detailbox) {{height: auto !important;}}
.st-key-chatbox {{height: calc(100vh - 340px) !important; min-height: 250px;}}
/* Microphone: show only Streamlit's record button, as a large round blue button (darker and pulsing while recording). */
.st-key-micwrap {{align-items: center; gap: 0.25rem;}}
.st-key-micwrap [data-testid="stAudioInput"] > div {{background: transparent !important; border: none !important;
    justify-content: center; min-height: 0; padding: 0;}}
.st-key-micwrap [data-testid="stAudioInput"] > div > div:has([data-testid="stAudioInputWaveSurfer"]),
.st-key-micwrap [data-testid="stAudioInputWaveformTimeCode"],
.st-key-micwrap [data-testid="stElementToolbar"] {{display: none !important;}}
.st-key-micwrap div:has(> [data-testid="stAudioInputActionButton"]) {{width: auto !important; height: auto !important;
    flex: 0 0 auto !important;}}
.st-key-micwrap [data-testid="stAudioInputActionButton"] {{width: 64px; min-width: 64px; height: 64px; flex: 0 0 64px;
    border-radius: 50%;
    background-color: #1E88E5; color: white !important; display: flex; align-items: center; justify-content: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.35); transition: transform 0.1s;}}
.st-key-micwrap [data-testid="stAudioInputActionButton"]:hover {{transform: scale(1.06);}}
.st-key-micwrap [data-testid="stAudioInputActionButton"] svg {{width: 30px; height: 30px; color: white; fill: currentColor;}}
.st-key-micwrap [data-testid="stAudioInputActionButton"][aria-label="Stop recording"] {{background-color: #0D47A1;
    animation: micpulse 1.2s infinite;}}
@keyframes micpulse {{0% {{box-shadow: 0 0 0 0 rgba(30,136,229,0.6);}} 100% {{box-shadow: 0 0 0 16px rgba(30,136,229,0);}}}}
.st-key-micwrap [data-testid="stCaptionContainer"] {{text-align: center;}}
/* New chat button: blue instead of the theme's red primary colour. */
.st-key-new_chat button {{background-color: #1E88E5 !important; border-color: #1E88E5 !important; color: white !important;}}
.st-key-new_chat button:hover {{background-color: #1565C0 !important; border-color: #1565C0 !important;}}
.st-key-type_toggle button {{font-size: 0.8rem; padding: 0; min-height: 0; opacity: 0.75;}}
.st-key-type_toggle p {{font-size: 0.8rem;}}
.st-key-detailpanel {{background-color: {_PANEL_BG}; border-radius: 0.75rem; padding: 1rem 1.25rem;
    height: calc(100vh - 90px); min-height: 350px;}}
.st-key-detailbox {{height: calc(100vh - 200px) !important; min-height: 250px; border: none !important;}}
</style>
""", unsafe_allow_html=True)

GREETING = "Hi! Tap the microphone below and tell me what you're shopping for."


def new_chat() -> None:
    st.session_state["messages"] = []
    st.session_state["chat_id"] = uuid.uuid4().hex[:8]


def save_audio(data: bytes, suffix: str = ".wav") -> str:
    folder = AUDIO_DIR / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex[:8]}-{int(time.time())}{suffix}"
    path.write_bytes(data)
    return str(path)


def handle_input(text: str | None = None, audio_bytes: bytes | None = None, suffix: str = ".wav") -> None:
    """Run one turn and append the user's and the assistant's chat messages."""
    text = (text or "").strip() or None
    audio_path = save_audio(audio_bytes, suffix) if audio_bytes and not text else None
    with st.spinner("Listening and thinking..."):
        state, mode = run_turn(audio_path=audio_path, text=text,
                               session_id=st.session_state["chat_id"])
    heard = state.get("transcript") or ""
    msgs = st.session_state["messages"]
    msgs.append({"role": "user", "content": heard or "🎙️ (nothing recognised)",
                 "audio": audio_path, "segments": state.get("asr_segments") or []})
    msgs.append({"role": "assistant", "state": state, "mode": mode,
                 "autoplay": bool(state.get("tts_audio_path"))})


def render_user(m: dict) -> None:
    st.markdown(m["content"])
    if m.get("audio"):
        st.audio(m["audio"])


def render_details(user_msg: dict | None, state: dict) -> None:
    """Right panel: everything the chat bubbles don't show."""
    if user_msg and user_msg.get("segments"):
        st.markdown("#### Transcript timestamps")
        st.dataframe([{"start": x["start"], "end": x["end"], "text": x["text"]} for x in user_msg["segments"]],
                     hide_index=True, width="stretch")

    route = view.route_summary(state)
    if route:
        st.markdown("#### Routing and safety")
        st.markdown(route)

    st.markdown("#### Agent steps")
    steps = view.step_rows(state)
    if steps:
        for s_ in steps:
            with st.expander(f"{s_['time']}  {s_['node']}: {s_['summary']}"):
                if s_["details"]:
                    st.json(s_["details"])
                else:
                    st.caption("No details")
    else:
        st.caption("No steps recorded.")

    st.markdown("#### Product comparison (top 3)")
    rows = view.comparison_rows(state)
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.caption("No products to compare.")

    private, web = view.split_citations(state)
    st.markdown("#### Citations")
    if private or web:
        for c in private + web:
            ref = f"`{c['doc_id']}`" if c.get("doc_id") else c.get("url", "")
            st.markdown(f"{c['marker']} {c.get('title', '')} ({c['source_type']}) {ref}")
    else:
        st.caption("No citations.")

    st.markdown("#### Private document IDs")
    ids = view.private_doc_ids(state)
    if ids:
        st.markdown(" ".join(f"`{i}`" for i in ids))
    else:
        st.caption("No catalog documents used.")

    st.markdown("#### Live-source links")
    links = view.live_links(state)
    if links:
        for l in links:
            st.markdown(f"- [{l['title']}]({l['url']})")
    else:
        st.caption("No live sources used.")

    if state.get("critic"):
        st.markdown("#### Critic verdict")
        st.write("Approved" if state["critic"].get("approved") else "Rejected")
        st.json(state["critic"], expanded=False)

    render_evaluation()


def render_evaluation() -> None:
    """Placeholder for ProofAgent evaluation evidence (required by the brief)."""
    # TODO(Alekhya, with Beste): show ProofAgent evaluation evidence here once Beste's harness output
    #  format is settled (docs_assignment/deliverables.md section 1.5): e.g. load the results file
    #  (path to be added to config/paths.py), then show overall scores per scenario, pass/fail counts,
    #  and the failure analysis by stage (ASR -> Router -> Planner -> RAG/MCP -> Answerer -> TTS).
    st.markdown("#### Evaluation (ProofAgent)")
    st.caption("Placeholder: ProofAgent evaluation results will appear here once the harness is connected.")


def render_assistant(m: dict) -> None:
    state = m["state"]
    for err in state.get("errors") or []:
        st.error(err)
    safety = state.get("safety") or {}
    if safety and safety.get("is_safe") is False:
        st.warning(f"🛡️ Safety check: {safety.get('reason') or safety.get('category') or 'request declined'}")
    reply = view.reply_text(state)
    if reply:
        st.markdown(reply)
        audio = state.get("tts_audio_path")
        if audio:
            st.audio(audio, autoplay=m.pop("autoplay", False))  # autoplay once, not on reruns
    elif m.get("mode") == "asr_only":
        st.info("The agent workflow isn't connected yet (check that `agent.run_agent` imports), so I could only "
                "transcribe what you said.")
    elif not state.get("errors"):
        st.markdown("I couldn't produce an answer for that.")


# ---------------- Page ----------------
if "messages" not in st.session_state:
    new_chat()
st.session_state.setdefault("upload_key", 0)
st.session_state.setdefault("mic_key", 0)
st.session_state.setdefault("typing", False)  # text box is a hidden backup; speaking is the default


def toggle_typing() -> None:
    st.session_state["typing"] = not st.session_state["typing"]

with st.sidebar:
    st.title("🛒 Voice Shopping Assistant")
    if st.button("➕ New chat", type="primary", width="stretch", key="new_chat"):
        new_chat()
        st.rerun()
    st.caption("Ask for a product by voice. Answers are spoken aloud and backed by evidence shown on the right.")

st.session_state.setdefault("show_details", True)  # details side panel is visible by default


def toggle_details() -> None:
    st.session_state["show_details"] = not st.session_state["show_details"]


if st.session_state["show_details"]:
    chat_col, detail_col = st.columns(2, gap="large")
else:
    chat_col, detail_col = st.container(), None

with chat_col:
    title_col, toggle_col = st.columns([5, 2], vertical_alignment="center")
    title_col.subheader("💬 Chat")
    toggle_col.button("Hide details ▶" if st.session_state["show_details"] else "◀ Show details",
                      on_click=toggle_details, width="stretch",
                      help="Show or hide the evidence and agent details panel")
    box = st.container(height=300, key="chatbox")
    with box:
        with st.chat_message("assistant"):
            st.markdown(GREETING)
        for m in st.session_state["messages"]:
            with st.chat_message(m["role"]):
                if m["role"] == "user":
                    render_user(m)
                else:
                    render_assistant(m)

    # Speaking is the default input. A new key after each turn clears the recorder for the next request.
    with st.container(key="micwrap"):
        rec = st.audio_input("Tap the microphone and speak your request", label_visibility="collapsed",
                             key=f"mic_{st.session_state['mic_key']}")
        st.caption("Tap the microphone to speak; tap again to send")
    if rec is not None:
        handle_input(audio_bytes=rec.getvalue())
        st.session_state["mic_key"] += 1
        st.rerun()

    # Typing is a small backup option, hidden until asked for.
    st.button("Prefer to speak? Hide the text box" if st.session_state["typing"]
              else "Can't speak now? Type your request instead",
              type="tertiary", key="type_toggle", on_click=toggle_typing)
    if st.session_state["typing"]:
        typed = st.chat_input("Type your request...")
        if typed:
            handle_input(text=typed)
            st.rerun()

    with st.expander("Upload an audio file instead"):
        up = st.file_uploader("WAV, MP3 or M4A", type=["wav", "mp3", "m4a"],
                              key=f"upload_{st.session_state['upload_key']}")
        if up is not None and st.button("Send file"):
            handle_input(audio_bytes=up.getvalue(), suffix="." + up.name.rsplit(".", 1)[-1])
            st.session_state["upload_key"] += 1
            st.rerun()

if detail_col is not None:
    with detail_col, st.container(key="detailpanel"):
        st.subheader("Evidence and agent details")
        msgs = st.session_state["messages"]
        with st.container(height=300, border=False, key="detailbox"):
            if len(msgs) >= 2:
                render_details(msgs[-2], msgs[-1]["state"])
            else:
                st.info("Steps, product comparison, citations, document IDs and live links for the latest "
                        "answer will appear here.")
                render_evaluation()
