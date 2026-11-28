"""CLI: python -m asr path/to/audio.wav [--model small] [--words] [--lang auto]"""
import argparse
import json

from .transcriber import WhisperTranscriber

p = argparse.ArgumentParser()
p.add_argument("audio")
p.add_argument("--model", default="small")
p.add_argument("--lang", default="en", help="use 'auto' to detect the language")
p.add_argument("--words", action="store_true", help="word-level timestamps")
a = p.parse_args()
r = WhisperTranscriber(a.model, language=None if a.lang == "auto" else a.lang,
                       word_timestamps=a.words).transcribe(a.audio)
print(json.dumps({"text": r.text, "language": r.language, "duration": r.duration,
                  "latency_s": round(r.latency_s, 2), "segments": r.segment_dicts}, indent=2))
