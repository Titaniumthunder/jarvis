# training_stats.py
# Reports how much training data the interaction logger has accumulated.
#
# Run with:  ./jarvis --stats
#
# Per-action counts matter more than the headline total: the distribution is
# lopsided by nature (lots of answer_question, few watch_printer), and a LoRA
# trained on a dataset with empty actions will simply never predict them.

import collections
import json

from tools import interaction_logger as il

# Turns to accumulate before the first LoRA run is worth attempting.
# 300 is enough to shake out the pipeline; 500 is where the adapter starts
# being genuinely useful across 24 actions, so that's what we aim at.
TARGET_TURNS = 500


def _read_jsonl(directory) -> list[dict]:
    records = []
    if not directory.exists():
        return records
    for path in sorted(directory.glob("*.jsonl")):
        try:
            with path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue  # skip a torn line, keep the rest
        except Exception:
            continue
    return records


def collect() -> dict:
    """Gather stats from disk. Flushes pending writes first so counts are exact."""
    il.flush()

    turns = _read_jsonl(il.TURNS_DIR)
    feedback = _read_jsonl(il.FEEDBACK_DIR)

    labels: dict[str, str] = {}
    for f in feedback:
        tid, label = f.get("turn_id"), f.get("label")
        if not tid or not label:
            continue
        # Negative wins over positive if a turn somehow got both.
        if labels.get(tid) == "negative":
            continue
        labels[tid] = label

    actions = collections.Counter(t.get("brain", {}).get("action", "?") for t in turns)
    sources = collections.Counter(t.get("source", "?") for t in turns)
    days = sorted({t.get("ts", "")[:10] for t in turns if t.get("ts")})

    positive = sum(1 for t in turns if labels.get(t.get("turn_id")) == "positive")
    negative = sum(1 for t in turns if labels.get(t.get("turn_id")) == "negative")

    return {
        "total": len(turns),
        "positive": positive,
        "negative": negative,
        "neutral": len(turns) - positive - negative,
        "actions": actions,
        "sources": sources,
        "days": days,
        "feedback_events": len(feedback),
    }


def render(s: dict) -> str:
    if s["total"] == 0:
        return (
            "\nJarvis training data\n"
            "────────────────────\n"
            "No interactions logged yet.\n\n"
            "The logger records automatically as you use Jarvis "
            "(./jarvis-web or ./jarvis).\n"
        )

    span = f"{s['days'][0]} → {s['days'][-1]}" if s["days"] else "unknown"
    lines = [
        "",
        "Jarvis training data",
        "────────────────────",
        f"Total turns      {s['total']}",
        f"Date range       {span}  ({len(s['days'])} active days)",
        f"Sources          " + ", ".join(f"{k}={v}" for k, v in s["sources"].most_common()),
        "",
        f"Labelled         {s['positive']} positive · {s['negative']} negative "
        f"· {s['neutral']} neutral",
        f"Feedback events  {s['feedback_events']}",
        "",
        "Per-action coverage",
    ]

    width = max((len(a) for a in s["actions"]), default=10)
    for action, count in s["actions"].most_common():
        bar = "█" * min(count, 30)
        lines.append(f"  {action:<{width}}  {count:>4}  {bar}")

    pct = min(100, int(100 * s["total"] / TARGET_TURNS))
    filled = int(28 * pct / 100)
    lines += [
        "",
        f"Readiness for first LoRA run ({TARGET_TURNS} turns)",
        f"  [{'█' * filled}{'░' * (28 - filled)}] {pct}%  ({s['total']}/{TARGET_TURNS})",
    ]
    if s["total"] < TARGET_TURNS:
        lines.append(f"  {TARGET_TURNS - s['total']} more turns to go. Keep using Jarvis normally.")
    else:
        lines.append("  Enough data to attempt Phase 4. Check per-action coverage above first.")
    lines.append("")
    return "\n".join(lines)


def main():
    print(render(collect()))


if __name__ == "__main__":
    main()
