"""Apple Calendar sync — put timed todos on your actual calendar (macOS, JXA).

No Google OAuth: Calendar.app is scriptable locally. Timed todos become 30-min
events; date-only todos become all-day events. Idempotent via a task->event map.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess

from .config import Settings
from .state import State
from .todo import TodoService

_JXA_UPSERT = r"""
function run(argv) {
  const [calName, title, startISO, endISO, allDay, existingUid] = argv;
  const Cal = Application('Calendar');
  let cal;
  try { cal = Cal.calendars.byName(calName); cal.name(); }
  catch (e) { cal = Cal.Calendar({name: calName}); Cal.calendars.push(cal); }

  // update in place if we already made this event
  if (existingUid) {
    const found = cal.events.whose({uid: existingUid})();
    if (found.length) {
      const ev = found[0];
      ev.summary = title;
      ev.startDate = new Date(startISO);
      ev.endDate = new Date(endISO);
      return JSON.stringify({uid: ev.uid(), action: 'updated'});
    }
  }
  const ev = Cal.Event({
    summary: title,
    startDate: new Date(startISO),
    endDate: new Date(endISO),
    alldayEvent: allDay === 'true',
  });
  cal.events.push(ev);
  return JSON.stringify({uid: ev.uid(), action: 'created'});
}
"""


def _parse(due: str | None) -> tuple[dt.datetime, bool] | None:
    if not due:
        return None
    try:
        d = dt.datetime.fromisoformat(due.replace("Z", "+00:00"))
    except ValueError:
        return None
    all_day = d.hour == 0 and d.minute == 0
    return d, all_day


def sync(settings: Settings, state: State, svc: TodoService, apply: bool = False) -> dict:
    """Mirror due-dated open todos onto the Apple Calendar. Returns a small report."""
    created = updated = skipped = 0
    for task, _project in svc.open_with_project():
        parsed = _parse(task.due_date)
        if not parsed:
            continue
        start, all_day = parsed
        end = start + dt.timedelta(days=1 if all_day else 0, minutes=0 if all_day else 30)
        sig = hashlib.sha1(f"{task.title}|{start.isoformat()}|{all_day}".encode()).hexdigest()
        prev = state.get_cal_event(task.id)
        if prev and prev[1] == sig:
            skipped += 1
            continue  # unchanged
        if not apply:
            created += 1
            continue
        proc = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", _JXA_UPSERT,
             settings.calendar_name, task.title,
             start.isoformat(), end.isoformat(), "true" if all_day else "false",
             prev[0] if prev else ""],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            continue
        try:
            res = json.loads(proc.stdout.strip())
        except json.JSONDecodeError:
            continue
        state.set_cal_event(task.id, res["uid"], sig)
        if res["action"] == "created":
            created += 1
        else:
            updated += 1
    return {"created": created, "updated": updated, "unchanged": skipped}
