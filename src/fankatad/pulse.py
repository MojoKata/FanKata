"""Speed pulse: ramp one fan between full and low speed so the user can spot it,
and check which speed sensor follows (requirements 5.5, 8.7)."""

from __future__ import annotations

from dataclasses import dataclass, field

LENGTH = 8.0         # seconds of pattern
PHASE = 1.0          # seconds per high/low phase
MAX_RUNTIME = 15.0   # hard cap, whatever happens
ABORT_TEMP = 85.0    # °C on a linked probe
FAN_LOW = 30.0       # % for fans; pumps use their current speed


@dataclass
class Pulse:
    fan: str
    own_tach: str | None
    low: float
    started: float
    samples: list = field(default_factory=list)    # (t, duty, {tach: rpm})
    stop_reason: str | None = None

    @classmethod
    def create(cls, fan: str, own_tach: str | None, fan_type: str, current_duty: float | None, now: float) -> "Pulse":
        low = FAN_LOW
        if fan_type == "pump":
            low = current_duty if current_duty is not None else 60.0
        return cls(fan, own_tach, low, now)

    def duty_at(self, t: float) -> float:
        return 100.0 if int(t // PHASE) % 2 == 0 else self.low

    def elapsed(self, now: float) -> float:
        return now - self.started

    def finished(self, now: float) -> bool:
        t = self.elapsed(now)
        return self.stop_reason is not None or t >= LENGTH or t >= MAX_RUNTIME

    def record(self, now: float, duty: float, rpms: dict) -> None:
        self.samples.append((round(self.elapsed(now), 3), duty, dict(rpms)))

    def snapshot(self, now: float) -> dict:
        own = self.own_tach
        return {
            "fan": self.fan,
            "elapsed": round(min(self.elapsed(now), LENGTH), 2),
            "length": LENGTH,
            "low": self.low,
            "duty": self.duty_at(self.elapsed(now)),
            "samples": [[t, d, r.get(own) if own else None] for t, d, r in self.samples],
        }

    def analyze(self) -> dict:
        """Which tach sensors followed the pattern."""
        per_tach: dict[str, dict[str, list[float]]] = {}
        for t, duty, rpms in self.samples:
            within = t % PHASE
            if within < PHASE / 2:      # skip the spin-up/down half of each phase
                continue
            side = "high" if duty >= 99.5 else "low"
            for tach, rpm in rpms.items():
                if rpm is not None:
                    per_tach.setdefault(tach, {"high": [], "low": []})[side].append(rpm)
        deltas = {}
        for tach, d in per_tach.items():
            if d["high"] and d["low"]:
                hi = sum(d["high"]) / len(d["high"])
                lo = sum(d["low"]) / len(d["low"])
                if hi - lo > max(80.0, 0.12 * hi):
                    deltas[tach] = hi - lo
        followers = sorted(deltas, key=deltas.get, reverse=True)
        chip = self.fan.split(":")[0]

        def short(tid: str) -> str:
            c, _, n = tid.partition(":")
            return n if c == chip else f"{c} {n}"

        if self.own_tach and self.own_tach in followers:
            kind, sensor = "self", self.own_tach
            msg = f"{short(sensor)} is following the pulse. This control drives this fan."
        elif followers:
            kind, sensor = "other", followers[0]
            msg = f"{short(sensor)} followed the pulse. This control drives {short(sensor)}’s sensor."
        else:
            kind, sensor = "none", None
            msg = ("No speed change detected. The header may be empty, the fan may have no speed sensor, "
                   "or it may be DC-driven while set to PWM mode.")
        if self.stop_reason and self.stop_reason != "done":
            msg = f"{self.stop_reason} {msg}"
        return {"fan": self.fan, "kind": kind, "sensor": sensor, "followers": followers, "message": msg,
                "stopped": self.stop_reason}
