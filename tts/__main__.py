"""CLI: python -m tts "text to speak" [out_dir]"""
import sys

from config.paths import AUDIO_DIR
from .summary import build_spoken_summary
from .synthesizer import synthesize_to_file

text = build_spoken_summary(sys.argv[1])
print(synthesize_to_file(text, sys.argv[2] if len(sys.argv) > 2 else str(AUDIO_DIR / "tts"), "cli"))
