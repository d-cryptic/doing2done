"""Enumerate + export Apple Notes via JXA (osascript). Mac-only.

Text notes: body HTML is returned inline. Handwriting/diagrams are NOT in the
body — Phase 1.1 will render those notes to PDF/PNG for the OCR step. For now we
surface note metadata + any text body so the pipeline is exercisable end-to-end.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

_JXA = r"""
function run() {
  const Notes = Application('Notes');
  const out = [];
  const notes = Notes.notes();
  for (let i = 0; i < notes.length; i++) {
    const n = notes[i];
    try {
      out.push({
        id: n.id(),
        name: n.name(),
        modified: n.modificationDate().toISOString(),
        body: n.body(),                      // HTML; empty-ish for pure drawings
        folder: n.container().name(),
      });
    } catch (e) { /* skip locked/unavailable */ }
  }
  return JSON.stringify(out);
}
"""


@dataclass(frozen=True)
class RawNote:
    id: str
    name: str
    modified: str
    body_html: str
    folder: str


def list_notes() -> list[RawNote]:
    """Return all Apple Notes with metadata + HTML body (requires Automation perm)."""
    proc = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", _JXA],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout or "[]")
    return [
        RawNote(
            id=n["id"],
            name=n.get("name", "Untitled"),
            modified=n.get("modified", ""),
            body_html=n.get("body", ""),
            folder=n.get("folder", ""),
        )
        for n in data
    ]

# TODO(phase-1.1): render notes containing PKDrawing to PDF/PNG in exports_dir
# (print-to-PDF via Notes UI automation) so ocr.recognize() can read handwriting.
