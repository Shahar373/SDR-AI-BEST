#!/usr/bin/env python3
"""
Sanitize radio-derived text before it enters the agent context.

Strips: ANSI/control sequences, prompt-injection patterns, markdown code
fences, null bytes. Length-caps at 64 KB.

Usage:
  echo "raw text" | python3 sanitize_rf_text.py
  python3 sanitize_rf_text.py --text "raw decoded string"
  python3 sanitize_rf_text.py --file /path/to/decoded_output.txt

Importable form (used by decoder scripts):
  from sanitize_rf_text import sanitize
  clean, warnings = sanitize("raw text")
"""
import argparse
import json
import re
import sys
from pathlib import Path

_INJECTION_PATTERNS = [
    # OpenAI / Anthropic chat delimiters
    r"---INST---",
    r"\[INST\]",
    r"\[/INST\]",
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"<\|endoftext\|>",
    r"<\|fim_prefix\|>",
    r"<\|fim_suffix\|>",
    r"<\|fim_middle\|>",
    r"\[SYSTEM\]",
    # Llama-2 / Mistral / Phi role markers
    r"<<SYS>>",
    r"<</SYS>>",
    r"<SYS>",
    r"</SYS>",
    r"<s>",
    r"</s>",
    r"<\|system\|>",
    r"<\|user\|>",
    r"<\|assistant\|>",
    # Common markdown/text role markers (anchored at line start to reduce false positives)
    r"(?m)^\s*###\s*System",
    r"(?m)^\s*###\s*Human",
    r"(?m)^\s*###\s*Assistant",
    r"(?m)^\s*Human\s*:",
    r"(?m)^\s*Assistant\s*:",
    r"(?m)^\s*System\s*:",
    # Imperative override phrases (case-insensitive)
    r"(?i)ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions?",
    r"(?i)disregard\s+(?:all\s+)?(?:previous|prior)\s+instructions?",
    r"(?i)forget\s+(?:all\s+)?(?:previous|prior)\s+instructions?",
    r"(?i)new\s+instructions?:\s",
    r"(?i)override\s+(?:system\s+)?prompt",
]

_ANSI_ESC = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b[()][AB012]|\x1b.")
_CONTROL  = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MD_FENCE = re.compile(r"^```[^\n]*$", re.MULTILINE)
_MAX_LEN  = 65_536


def sanitize(text: str) -> tuple[str, list[str]]:
    """
    Clean untrusted RF-derived text for safe inclusion in agent context.

    Returns (sanitized_text, warnings_list).
    """
    warnings: list[str] = []
    original_len = len(text)

    # Null bytes
    if "\x00" in text:
        text = text.replace("\x00", "")
        warnings.append("removed: null bytes")

    # ANSI escape sequences
    cleaned = _ANSI_ESC.sub("", text)
    if cleaned != text:
        warnings.append("removed: ANSI escape sequences")
    text = cleaned

    # Control characters (keep \t \n \r)
    cleaned = _CONTROL.sub("", text)
    if cleaned != text:
        warnings.append("removed: control characters")
    text = cleaned

    # Markdown code fences
    cleaned = _MD_FENCE.sub("[CODE BLOCK REMOVED]", text)
    if cleaned != text:
        warnings.append("removed: markdown code fences")
    text = cleaned

    # Prompt-injection patterns
    for pat in _INJECTION_PATTERNS:
        cleaned = re.sub(pat, "[INJECTION REMOVED]", text)
        if cleaned != text:
            warnings.append(f"removed: injection pattern ({pat[:30]})")
        text = cleaned

    # Length cap
    if len(text) > _MAX_LEN:
        text = text[:_MAX_LEN] + "…[TRUNCATED]"
        warnings.append(f"truncated: {original_len} → {_MAX_LEN} chars")

    return text.strip(), warnings


def sanitize_value(v) -> str | None:
    """Sanitize a single string field from RF data. Returns tagged string or None."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    clean, _ = sanitize(s)
    return f"[UNTRUSTED RF DATA] {clean}"


def main():
    ap = argparse.ArgumentParser(description="Sanitize RF-derived text")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--text", help="Raw text string to sanitize")
    src.add_argument("--file", help="Path to file containing raw text")
    args = ap.parse_args()

    if args.text:
        raw = args.text
    elif args.file:
        raw = Path(args.file).read_text(errors="replace")
    else:
        raw = sys.stdin.read()

    sanitized, warnings = sanitize(raw)
    print(json.dumps({
        "sanitized": sanitized,
        "warnings": warnings,
        "label": "[UNTRUSTED RF DATA]",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
