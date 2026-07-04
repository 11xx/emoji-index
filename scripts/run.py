#!/usr/bin/env python3
import json
import urllib.request
import urllib.error
from pathlib import Path

INPUT_PATH  = Path("emoji-base.txt")
OUTPUT_PATH = Path("emoji-rich.out")
MODEL_NAME  = "qwen3.5:9b"
OLLAMA_URL  = "http://localhost:11434/api/generate"

PROMPT_TEMPLATE = """\
You are building a fuzzy search index for a terminal emoji picker.
Users type partial words into fzf/tofi and the full line is searched.

Emoji: {emoji}
Name: {name}
Group: {group}
Subgroup: {subgroup}

Write exactly two lines. Nothing else — no labels, no numbering, no markdown.

Line 1: A natural 6–12 word phrase describing the social or emotional function of this emoji
in real conversations. Must differ meaningfully from the name above.

Line 2: Target about 20 unique comma-separated lowercase keywords, longer only when useful for search matching.

Rules for Line 2:
- Every keyword must appear EXACTLY ONCE. No duplicates, no near-duplicates.
- Use SINGLE words wherever possible. Multi-word phrases only for established slang
  (e.g. "good vibes", "lmao", "passive aggressive", "rolling on floor"). 
- When a concept has modifiers, list the root word ONCE, then the modifiers separately.
  WRONG: fun vibes, happy vibes, warm vibes
  RIGHT: vibes, fun, happy, warm
- Cover all 8 categories with at least one term each:
  VISUAL · EMOTION · SYNONYMS · USAGE · TONE · INTERNET · CONCEPTS · ACTIONS
- Stop at exactly 20. Do not continue after the 20th keyword.\
"""


def load_processed(path: Path) -> set[str]:
    seen = set()
    if not path.exists():
        return seen
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            tok = line.strip().split(" | ", 1)
            if tok and tok[0]:
                seen.add(tok[0])
    return seen


def query_model(prompt: str) -> str:
    payload = json.dumps({
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 220,      # 20 keywords avg ~8 tokens each = ~160; label ~30; headroom
            "num_ctx": 1024,
            "repeat_penalty": 1.4,   # strongly discourages token repetition loops
            "repeat_last_n": 128,    # look back this many tokens when applying the penalty
        },
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data.get("response", "").strip()


def dedup_keywords(raw: str) -> str:
    """Deduplicate comma-separated keywords, preserving first-occurrence order."""
    seen: set[str] = set()
    result: list[str] = []
    for kw in raw.split(","):
        kw = kw.strip().lower()
        if kw and kw not in seen:
            seen.add(kw)
            result.append(kw)
    return ", ".join(result)


def parse_response(response: str) -> tuple[str, str]:
    lines = [l.strip() for l in response.splitlines() if l.strip()]
    label    = lines[0] if len(lines) > 0 else ""
    keywords = dedup_keywords(lines[1]) if len(lines) > 1 else ""
    return label, keywords


def main():
    seen = load_processed(OUTPUT_PATH)
    print(f"Resuming. Detected {len(seen)} existing records.")

    if not INPUT_PATH.exists():
        print(f"Error: {INPUT_PATH} not found. Run extract.awk first.")
        return

    total = sum(1 for l in INPUT_PATH.open("r", encoding="utf-8") if l.strip())
    processed = len(seen)

    with OUTPUT_PATH.open("a", encoding="utf-8") as out:
        with INPUT_PATH.open("r", encoding="utf-8") as infile:
            for raw in infile:
                raw = raw.strip()
                if not raw:
                    continue

                try:
                    emoji, group, subgroup, name = [p.strip() for p in raw.split(" | ")]
                except ValueError:
                    print(f"Skipping malformed: {raw!r}")
                    continue

                if emoji in seen:
                    continue

                prompt = PROMPT_TEMPLATE.format(
                    emoji=emoji, group=group, subgroup=subgroup, name=name
                )

                try:
                    response = query_model(prompt)
                except KeyboardInterrupt:
                    print("\nInterrupted. Progress saved.")
                    break
                except Exception as e:
                    print(f"Error on {emoji} ({name}): {e}")
                    continue

                label, keywords = parse_response(response)

                if not label or not keywords:
                    print(f"Rejected incomplete output for {emoji}: {response!r}")
                    continue

                line = f"{emoji} | {group} | {subgroup} | {name} | {label} | {keywords}"
                out.write(line + "\n")
                out.flush()
                seen.add(emoji)
                processed += 1
                print(f"[{processed}/{total}] {line}")


if __name__ == "__main__":
    main()
