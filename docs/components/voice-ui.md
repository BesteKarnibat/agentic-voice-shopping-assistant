# Voice and UI

**Owner:** Alekhya · **Branch:** `feature/ui` · **Status:** draft (ASR, TTS and Streamlit UI built; waiting on `run_agent` and ProofAgent output)
**Code:** [`asr/`](../../asr/) (speech to text), [`tts/`](../../tts/) (text to speech), tests in [`tests/`](../../tests/). Streamlit app: [`app/`](../../app/).

## 1. Overview

```mermaid
flowchart LR
    mic[Recording WAV/MP3 or mic stream] --> asr[asr_node<br/>Whisper]
    asr -->|transcript| graph["run_agent(transcript)<br/>LangGraph: Router → Planner → Retriever → Answerer/Critic"]
    graph -->|spoken_summary, final_answer, clarification_question| tts[tts_node<br/>OpenAI TTS]
    tts -->|tts_audio_path| spk[Speaker]
    graph -->|answer, table, citations, step_log| ui[Screen]
```

The UI runs the voice steps around the agreed entry point `run_agent(transcript) → state`
([task-planning.md](../../docs_assignment/task-planning.md), handoff 5): ASR first, then `run_agent`, then TTS.
Both voice steps follow the node rules of `AgentState` ([contracts/state.py](../../contracts/state.py)): partial
updates and one `step_log` entry each. If either fails, it adds a message to `errors` and the turn continues,
so the on-screen answer still works.

## 2. ASR (Whisper)

Code: [`asr/transcriber.py`](../../asr/transcriber.py), [`asr/node.py`](../../asr/node.py), [`asr/streaming.py`](../../asr/streaming.py).

| Aspect | Choice |
|--------|--------|
| Model | [faster-whisper](https://github.com/SYSTRAN/faster-whisper), local. Default `small` on CPU (`int8`); `ASR_MODEL`, `ASR_DEVICE`, `ASR_COMPUTE` override. For a GPU set `ASR_DEVICE=cuda` and `ASR_COMPUTE=float16`; if the CUDA libraries are missing (e.g. `cublas64_12.dll not found`) it logs a warning and falls back to CPU. |
| Input | A WAV/MP3 file path (decoded by PyAV, no system ffmpeg), or a 16 kHz float32 array. |
| Streaming | `StreamingASR.feed(pcm16_bytes)` takes live 16 kHz int16 chunks and returns a result after ~1 s of silence or 30 s of speech. |
| Timestamps | Segment `start`/`end` always. Word-level times with `word_timestamps=True`. |
| Accents / noise | Voice-activity filter drops silence and noise. Temperature fallback `[0, 0.2, 0.4]` retries hard audio. A shopping-vocabulary prompt ([prompts/asr_initial_prompt.md](../../prompts/asr_initial_prompt.md)) helps with prices and brand names. `language="en"` by default; `None` auto-detects. |
| Failure handling | Missing file or error → empty `transcript` and an `errors` entry. No speech → same. Typed text with no audio skips ASR. |

State mapping: `audio_path` → `transcript` and `asr_segments` (`[{"start", "end", "text", ...}]`).

## 3. TTS

Code: [`tts/summary.py`](../../tts/summary.py), [`tts/synthesizer.py`](../../tts/synthesizer.py), [`tts/node.py`](../../tts/node.py).

- **Spoken summary rule:** use the Answerer's `spoken_summary`, else the start of `final_answer` (this covers
  refusals), else the Router's `clarification_question`.
  Remove `[n]` markers, URLs and markdown, then keep whole sentences up to 40 words (about 15 s). The
  voice says the same thing as the screen, minus citations.
- **Engine:** OpenAI TTS (`gpt-4o-mini-tts`, voice `alloy`) when `OPENAI_API_KEY` is set. Audio streams
  to disk as it is generated. Otherwise an offline fallback (`pyttsx3`) is used. Model and voice:
  `TTS_MODEL`, `TTS_VOICE`. Voice style: [prompts/tts_instructions.md](../../prompts/tts_instructions.md).
- **Lead-in pause:** the file starts with 500 ms of silence (`TTS_LEAD_IN_MS`) because players often
  clip the first word. OpenAI audio is requested as raw PCM and wrapped as WAV so silence can be added.
- **Output:** `data/audio/tts/<session_id>-<timestamp>.wav` (`TTS_OUT_DIR` overrides). Audio is gitignored.

State mapping: `spoken_summary` / `final_answer` / `clarification_question` → `tts_audio_path`.

## 4. UI

Code: [`app/streamlit_app.py`](../../app/streamlit_app.py) (page), [`app/view.py`](../../app/view.py) (state to display data),
[`app/pipeline.py`](../../app/pipeline.py) (runs a turn).

The screen is split in half. **Left:** the voice chat. **Right:** everything the chat does not show, for the latest answer.

| Where | UI element | `AgentState` field |
|-------|------------|--------------------|
| Left | Microphone recorder (default input); small "Can't speak now? Type your request instead" link opens a text box; upload expander (WAV/MP3/M4A) | `audio_path`, `transcript` |
| Left | Your message bubble (speech transcript) | `transcript` |
| Left | Assistant bubble: answer with `[n]` markers, refusal, or clarifying question; safety warning if blocked | `final_answer`, `clarification_question`, `safety` |
| Left | Spoken reply player (autoplays once; links are never spoken) | `tts_audio_path`, `spoken_summary` |
| Right | Transcript timestamps | `asr_segments` |
| Right | Routing and safety (intent, safety check, clarification) | `intent`, `safety`, `clarification_question` |
| Right | Agent steps (expandable, with details) | `step_log` |
| Right | Product comparison, top 3: Product, Price, Rating, Age range, Warnings, Source, Citation | `comparison_table` |
| Right | Citations | `citations` |
| Right | Private document IDs | `citations` (private), `comparison_table.doc_id` |
| Right | Live-source links | `citations` (web), `comparison_table.live_url`, `web_results` |
| Right | Critic verdict | `critic` |
| Right | Evaluation (ProofAgent): **placeholder**, see the TODO in `render_evaluation()` | Planned: Beste's results file |

The sidebar's **New chat** button clears the conversation and the right panel.

**Agent connection:** `app/pipeline.py` calls `agent.run_agent(transcript, session_id=..., asr_segments=...)` ([agent/run.py](../../agent/run.py)), which runs the real graph against the real RAG index and MCP server. `AGENT_ENTRY` (default `agent:run_agent`) can point at another entry point. If the returned state has no `tts_audio_path`, the UI runs TTS itself. The UI passes `on_step`, so each agent step appears live while the answer is being built. `run_agent` never raises and always returns a `final_answer` (a fallback apology on failure, with the cause in `errors`). If the import fails, only speech recognition runs and the UI says so. No sample data is shown.

## 5. Usage

```bash
# Transcribe a file (first run downloads the model)
uv run python -m asr sample.wav --model small --words

# Speak a sentence
uv run python -m tts "I'd go with Catan Junior at about twenty dollars, for ages six and up."

# Launch the UI
uv run streamlit run app/streamlit_app.py

# Tests (no model or API key needed)
uv run pytest tests
```

Dependencies are in `pyproject.toml` (`uv sync`): `streamlit`, `faster-whisper`, `av>=14,<17` (`av` 19 breaks
faster-whisper 1.2.1, so it is pinned), `openai`, `pyttsx3`, and `pytest` as a dev dependency.

## 6. Decisions, limitations, and known issues

- **faster-whisper over the OpenAI Whisper API:** runs offline, no per-call cost, no audio leaves the
  machine. Cost: model download and slower CPU inference.
- **OpenAI TTS over ElevenLabs/Polly/Coqui:** one API key already needed for the LLM, natural voice,
  streaming. Offline fallback works without a key.
- **Streaming is energy-based:** silence detection uses a loudness threshold, so it may need tuning in
  a noisy room. Each utterance is transcribed once at the end, not word by word.
- **Measured so far:** one 7.4 s recording transcribed on CPU with `small` in 5.2 s. Word error rate not measured.
- **Not measured yet:** word error rate and OpenAI TTS latency. The offline voice has been run for real; OpenAI TTS
  has not (no API key during development).
- **No conversation memory:** each turn calls `run_agent` with only the latest transcript.
- **Lead-in length** (500 ms) is a guess; raise `TTS_LEAD_IN_MS` if the first word is still clipped.
