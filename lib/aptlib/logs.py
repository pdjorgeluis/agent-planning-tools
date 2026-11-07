"""Rolling metadata-only logs, rotated at 50 entries into a monthly archive."""

import os
import re
import sys
from datetime import datetime, timezone

ROTATE_AT = 50
REQUEST_CHARS = 100
_ENTRY_RE = re.compile(r"^## \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC \u2014 ", re.M)


def one_line(text, limit):
    """Collapse whitespace so request text cannot forge a log entry."""
    return " ".join((text or "").split())[:limit]


def _header(tool):
    return (f"# {tool.capitalize()} reviews \u2014 rolling log\n\n"
            "One entry per call. Entries hold metadata only (never the full "
            "request, never file contents, never keys). At 50 entries the log "
            f"rolls into `{tool}-reviews-archive-YYYY-MM.md`.\n\n---\n\n")


def rotate(log_path, tool):
    if not os.path.exists(log_path):
        return
    with open(log_path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    starts = [m.start() for m in _ENTRY_RE.finditer(text)]
    if len(starts) < ROTATE_AT:
        return
    entries = text[starts[0]:]
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    archive = os.path.join(os.path.dirname(log_path),
                           f"{tool}-reviews-archive-{month}.md")
    if os.path.exists(archive):
        with open(archive, "a", encoding="utf-8") as f:
            f.write("\n" + entries)
    else:
        with open(archive, "w", encoding="utf-8") as f:
            f.write(f"# {tool.capitalize()} reviews \u2014 archive {month}\n\n"
                    + entries)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(text[:starts[0]])


def append(log_dir, tool, title, fields):
    """Append one entry. Never raises: a log problem must not fail a review."""
    try:
        os.makedirs(log_dir, mode=0o700, exist_ok=True)
        path = os.path.join(log_dir, f"{tool}-reviews.md")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        body = "".join(f"**{k}:** {one_line(str(v), 300)}\n"
                       for k, v in fields.items())
        entry = f"## {now} UTC \u2014 {one_line(title, 80)}\n\n{body}\n---\n"
        try:
            rotate(path, tool)
        except OSError as exc:
            print(f"[{tool}] warning: log rotation failed: {exc}", file=sys.stderr)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(_header(tool))
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError as exc:
        print(f"[{tool}] warning: cannot write log: {exc}", file=sys.stderr)
