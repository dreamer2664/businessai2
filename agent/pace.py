"""The pace clock (milestone 13): "I need it in 10 minutes" → a visible timer and reminders, never a stop.
"I'm away 5 hours, take it slow" → a time budget: the task may use it, and whatever is left goes to self-study.
"Take at least 3 hours" → a floor: the first pass is delivered, then the agent keeps deepening (more reading angles,
project steps) until the floor — never idle filler; "at most 20 minutes" → a ceiling (the deadline timer).

One Pace object lives on the Agent. The live screen shows it, /status prints it, and long loops call `tick()` to get
a reminder string ("⏰ owner wanted this in 10 min — 2 min left") at most once every REMIND_EVERY seconds.
"""
import time

REMIND_EVERY = 120


class Pace:
    def __init__(self, log=None):
        self.log = log or (lambda kind, **f: None)
        self.clear()

    def clear(self):
        self.forced_hurry = False
        self.stopped = False
        self.mode = "normal"          # quick | normal | slow
        self.goal = ""
        self.started = 0.0
        self.deadline = None          # epoch seconds when the owner wants it
        self.deadline_min = None      # what the owner asked for ("in 10 minutes")
        self.budget_until = None      # epoch seconds until which the owner is away (slow mode)
        self.floor_until = None       # epoch seconds before which the job must not end ("at least 3 hours")
        self.floor_min = None
        self.last_remind = 0.0
        self.late_told = False
        self.done_at = None

    def set(self, brief_pace, goal=""):
        """From Brief.parse_pace(): {"pace", "deadline_min", "budget_min", "why"}."""
        self.clear()
        self.mode = brief_pace.get("pace", "normal")
        self.goal = goal[:80]
        self.started = time.time()
        if brief_pace.get("deadline_min"):
            self.deadline_min = int(brief_pace["deadline_min"])
            self.deadline = self.started + 60 * brief_pace["deadline_min"]
        if brief_pace.get("budget_min"):
            self.budget_until = self.started + 60 * brief_pace["budget_min"]
        if brief_pace.get("floor_min"):
            self.floor_min = int(brief_pace["floor_min"])
            self.floor_until = self.started + 60 * self.floor_min
        self.log("pace_set", mode=self.mode, deadline_min=brief_pace.get("deadline_min"), budget_min=brief_pace.get("budget_min"), floor_min=brief_pace.get("floor_min"))

    def finish(self):
        self.done_at = time.time()

    # ---- what the clock says ------------------------------------------------------
    def over_budget(self):
        """Quiet-time budget used up (owner may be back) → long loops wrap up, no new background work."""
        return self.budget_until is not None and time.time() > self.budget_until

    def remaining(self):
        if not self.deadline:
            return None
        return int(self.deadline - time.time())

    def budget_left(self):
        if not self.budget_until:
            return None
        return int(self.budget_until - time.time())

    def active(self):
        return bool(self.started) and self.done_at is None

    def floor_left(self):
        """Seconds still owed to the floor ("at least N"), 0 when none/none left."""
        if not self.floor_until or self.stopped:
            return 0
        return max(0, int(self.floor_until - time.time()))

    def under_floor(self):
        return self.floor_left() > 0

    def floor_done(self):
        """The floor was honoured (or the owner said 'enough') → the job may end."""
        self.floor_until = None

    def text(self):
        """One line for /status and the live screen."""
        if not self.started:
            return "pace: normal"
        el = int(time.time() - self.started)
        bits = [f"pace: {self.mode}"]
        if self.goal:
            bits.append(f"“{self.goal}”")
        bits.append(f"elapsed {el // 60} min")
        r = self.remaining()
        if r is not None:
            bits.append(f"⏰ owner wants it in {self.deadline_min} min — " + (f"{r // 60} min left" if r >= 0 else f"{-r // 60} min LATE"))
        b = self.budget_left()
        if b is not None:
            bits.append(f"🐢 owner away — {b // 3600} h {b % 3600 // 60} min of quiet time left" if b > 0 else "owner may be back — wrap up")
        if self.floor_min:
            f = self.floor_left()
            bits.append(f"⏬ at least {self.floor_min // 60} h {self.floor_min % 60} min asked — {f // 3600} h {f % 3600 // 60} min still to use" if f > 0 else f"⏬ the {self.floor_min} min floor is honoured")
        if self.done_at:
            bits.append("done")
        return " · ".join(bits)

    def tick(self):
        """Call from long loops. Returns a reminder string when one is due, else ''."""
        if not self.active():
            return ""
        now = time.time()
        r = self.remaining()
        if r is not None:
            if r < 0 and not self.late_told:
                self.late_told = True
                self.last_remind = now
                self.log("pace_late", late_s=-r)
                return f"⏰ I'm past the {self.deadline_min} minutes you wanted — finishing as fast as I can (no corners cut on the checks)."
            if now - self.last_remind >= REMIND_EVERY and 0 <= r <= 3 * 60:
                self.last_remind = now
                return f"⏰ {max(1, r // 60)} min left of the {self.deadline_min} you gave me — wrapping up."
        return ""

    def hurry(self):
        """True when the deadline is close/past: tools should take the short path (fewer pages, shorter reads)."""
        r = self.remaining()
        return self.mode == "quick" or (r is not None and r < 5 * 60) or getattr(self, "forced_hurry", False)

    def hurry_now(self):
        """The owner said 'hurry up' mid-job: from now on every tool takes the short path."""
        self.forced_hurry = True
        self.mode = "quick"

    def slow_now(self, floor_min=None, budget_min=None):
        """The owner said 'slow down' / 'take 5-6 hours' mid-job: quick is off, the floor/budget count from the job's start."""
        self.forced_hurry = False
        self.mode = "slow"
        self.deadline = None
        self.deadline_min = None
        base = self.started or time.time()
        if floor_min:
            self.floor_min = int(floor_min)
            self.floor_until = base + 60 * self.floor_min
        if budget_min:
            self.budget_until = base + 60 * int(budget_min)
        self.log("pace_slowed", floor_min=self.floor_min, budget_min=budget_min)

    def stop_now(self):
        """The owner said 'stop': long loops end at their next check and hand over what they have."""
        self.stopped = True

    def should_stop(self):
        return getattr(self, "stopped", False)

    def pages_budget(self, normal=3):
        """How many pages a research step may read, by pace."""
        if self.hurry():
            return max(1, normal - 1)
        if self.mode == "slow" or self.under_floor():
            return normal + 2
        return normal

    def has_quiet_time(self, minutes=20):
        """Slow mode: is there still enough owner-away time to start another study session?"""
        b = self.budget_left()
        return b is not None and b > minutes * 60
