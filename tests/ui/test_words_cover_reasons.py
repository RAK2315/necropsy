"""UI task 48: every engine rejection reason has plain words. Built by Claude Code, not Kiro.

The format-coverage spec added two reasons (sample_above_maxval, decoder_malformed). Until a mapping exists the
screen shows the raw engine term, so this test reads the engine's own REASONS set and requires a case for each
in both reasonText and reasonExplain in public/js/words.js. internal_error and input_too_short are not reported by
reasonExplain's callers in a way that needs a sentence, but they are still required in reasonText.
"""
import re
from pathlib import Path

from necropsy.engine.types import REASONS

WORDS = (Path(__file__).resolve().parents[2] / "public" / "js" / "words.js").read_text(encoding="utf-8")


def _cases(function_name: str) -> set:
    start = WORDS.index(f"export function {function_name}(")
    end = WORDS.index("\n}\n", start)
    return set(re.findall(r"case '([a-z_]+)'", WORDS[start:end]))


def test_reason_text_names_every_engine_reason():
    missing = set(REASONS) - _cases("reasonText")
    assert not missing, missing


def test_reason_explain_names_every_decoder_and_maxval_reason():
    needed = {r for r in REASONS if r.startswith("decoder_")} | {"sample_above_maxval"}
    missing = needed - _cases("reasonExplain")
    assert not missing, missing


def test_decoder_words_do_not_assume_run_length():
    # These reasons now come from LZW, Deflate, LZMA, PackBits and PNM text decoders too (decoders.STATUS_REASONS).
    for fn in ("reasonText", "reasonExplain"):
        start = WORDS.index(f"export function {fn}(")
        body = WORDS[start:WORDS.index("\n}\n", start)]
        for reason in ("decoder_overrun", "decoder_underrun", "decoder_unconsumed"):
            line = body[body.index(f"case '{reason}'"):]
            line = line[:line.index("\n    case ") if "\n    case " in line else len(line)]
            assert "run-length" not in line and "a run " not in line, (fn, reason, line)
