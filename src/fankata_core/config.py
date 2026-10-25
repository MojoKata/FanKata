"""The Fankata configuration: Curves, custom Probes and Fan settings.

Stored as TOML at /etc/fankata/config.toml, owned by the service. Reading uses
tomllib (Python 3.11+) or the vendored tomli; writing uses the small emitter
below, which covers exactly the value types this schema uses.
"""

from __future__ import annotations

import copy
import os
import tempfile
from dataclasses import dataclass, field

try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from . import curve as curvemod
from . import expr as exprmod

SCHEMA_VERSION = 1
FAN_TYPES = ("case", "aio", "pump", "generic")
from .paths import CONFIG_PATH as DEFAULT_PATH  # noqa: E402


@dataclass
class CurveDef:
    name: str
    points: list[list[float]]
    allow_zero: bool = False


@dataclass
class ProbeDef:
    name: str
    expr: str


@dataclass
class FanSettings:
    name: str | None = None
    type: str | None = None          # user override of the detected type
    curve: str | None = None
    probe: str | None = None
    rpm_sensor: str | None = None    # e.g. "fan3"; defaults to the channel's own

    def is_empty(self) -> bool:
        return not any((self.name, self.type, self.curve, self.probe, self.rpm_sensor))


@dataclass
class Config:
    curves: list[CurveDef] = field(default_factory=list)
    probes: list[ProbeDef] = field(default_factory=list)
    fans: dict[str, FanSettings] = field(default_factory=dict)

    def curve(self, name: str) -> CurveDef | None:
        return next((c for c in self.curves if c.name == name), None)

    def probe(self, name: str) -> ProbeDef | None:
        return next((p for p in self.probes if p.name == name), None)

    def fan(self, fan_id: str) -> FanSettings:
        return self.fans.get(fan_id) or FanSettings()

    def copy(self) -> "Config":
        return copy.deepcopy(self)

    # --- dict form (used on the wire and in TOML) ---------------------------------
    def to_dict(self) -> dict:
        fans = {}
        for fid, s in sorted(self.fans.items()):
            d = {k: v for k, v in vars(s).items() if v not in (None, "")}
            if d:
                fans[fid] = d
        return {
            "version": SCHEMA_VERSION,
            "curves": [{"name": c.name, "allow_zero": c.allow_zero,
                        "points": [[_num(x), _num(y)] for x, y in c.points]} for c in self.curves],
            "probes": [{"name": p.name, "expr": p.expr} for p in self.probes],
            "fans": fans,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        if not isinstance(d, dict):
            raise ValueError("configuration must be a table")
        curves = []
        for c in d.get("curves", []):
            pts = [[float(p[0]), float(p[1])] for p in c.get("points", [])]
            curves.append(CurveDef(str(c["name"]), pts, bool(c.get("allow_zero", False))))
        probes = [ProbeDef(str(p["name"]), str(p["expr"])) for p in d.get("probes", [])]
        fans = {}
        for fid, s in (d.get("fans") or {}).items():
            fans[str(fid)] = FanSettings(**{k: (str(v) if v is not None else None)
                                            for k, v in s.items() if k in FanSettings.__dataclass_fields__})
        return cls(curves, probes, fans)


def _num(v: float):
    return int(v) if float(v).is_integer() else float(v)


# --- TOML ------------------------------------------------------------------------

def _toml_str(s: str) -> str:
    out = ['"']
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _toml_val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return _toml_str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_val(x) for x in v) + "]"
    raise TypeError(f"can't write {type(v).__name__} to TOML")


def _toml_key(k: str) -> str:
    return k if k.replace("_", "").replace("-", "").isalnum() and k.isascii() else _toml_str(k)


def dumps(cfg: Config) -> str:
    d = cfg.to_dict()
    lines = ["# Fankata configuration. Managed by fankatad; edit with the Fankata app.",
             f"version = {d['version']}", ""]
    for c in d["curves"]:
        lines += ["[[curves]]", f"name = {_toml_str(c['name'])}",
                  f"allow_zero = {_toml_val(c['allow_zero'])}", f"points = {_toml_val(c['points'])}", ""]
    for p in d["probes"]:
        lines += ["[[probes]]", f"name = {_toml_str(p['name'])}", f"expr = {_toml_str(p['expr'])}", ""]
    for fid, s in d["fans"].items():
        lines.append(f"[fans.{_toml_key(fid)}]")
        lines += [f"{k} = {_toml_val(v)}" for k, v in s.items()]
        lines.append("")
    return "\n".join(lines)


def loads(text: str) -> Config:
    return Config.from_dict(tomllib.loads(text))


def load(path: str) -> Config:
    with open(path, "rb") as f:
        return Config.from_dict(tomllib.load(f))


def save(cfg: Config, path: str) -> None:
    """Atomic write: temp file in the same directory, fsync, rename."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".toml", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(dumps(cfg))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --- validation ------------------------------------------------------------------

def validate(cfg: Config, system_probes: set[str] | frozenset[str], strict: bool = True) -> list[str]:
    """All rule violations. With strict=False, references to system probes that
    are missing right now are tolerated (the sensor may come back)."""
    errs: list[str] = []
    seen = set()
    for c in cfg.curves:
        if not c.name.strip():
            errs.append("Curve names can’t be empty.")
        if c.name in seen:
            errs.append(f"Curve name “{c.name}” is used twice.")
        seen.add(c.name)
        for _, msg in curvemod.point_errors(c.points, c.allow_zero):
            errs.append(f"{c.name}: {msg}")

    custom = {}
    for p in cfg.probes:
        if not exprmod.is_valid_custom_name(p.name):
            errs.append(f"“{p.name}” is not a valid probe name: start with a letter, then letters, digits and _ only.")
        if p.name in custom:
            errs.append(f"Probe name “{p.name}” is used twice.")
        custom[p.name] = p.expr

    known = set(custom) | set(system_probes)
    graph: dict[str, list[str]] = {}
    for name, src in custom.items():
        try:
            ast = exprmod.parse(src)
        except exprmod.ExprError as e:
            errs.append(f"Probe {name}: {e.message}")
            continue
        names = [n for n, _ in exprmod.refs(ast)]
        for n in names:
            if n.startswith(exprmod.SYS_PREFIX):
                if strict and n not in system_probes:
                    errs.append(f"Probe {name}: unknown probe “{n}”.")
            elif n not in custom:
                errs.append(f"Probe {name}: unknown probe “{n}”.")
        graph[name] = [n for n in names if n in custom]
    cycle = exprmod.find_cycle(graph)
    if cycle:
        errs.append("Probes can’t reference themselves: " + " → ".join(cycle) + ".")

    curve_names = {c.name for c in cfg.curves}
    for fid, s in cfg.fans.items():
        if s.type and s.type not in FAN_TYPES:
            errs.append(f"Fan {fid}: unknown type “{s.type}”.")
        if s.curve and s.curve not in curve_names:
            errs.append(f"Fan {fid}: unknown curve “{s.curve}”.")
        if s.probe and s.probe not in known and (strict or not s.probe.startswith(exprmod.SYS_PREFIX)):
            errs.append(f"Fan {fid}: unknown probe “{s.probe}”.")
    return errs


def users_of_curve(cfg: Config, name: str) -> list[str]:
    return [fid for fid, s in cfg.fans.items() if s.curve == name]


def users_of_probe(cfg: Config, name: str) -> list[str]:
    out = [f"fan {fid}" for fid, s in cfg.fans.items() if s.probe == name]
    for p in cfg.probes:
        if p.name == name:
            continue
        try:
            if any(n == name for n, _ in exprmod.refs(exprmod.parse(p.expr))):
                out.append(f"probe {p.name}")
        except exprmod.ExprError:
            pass
    return out


def default_config() -> Config:
    return Config(curves=[
        CurveDef("Quiet", [[20, 20], [40, 25], [55, 35], [70, 60], [85, 100]]),
        CurveDef("Balanced", [[20, 25], [40, 30], [60, 45], [75, 75], [85, 100]]),
        CurveDef("Performance", [[20, 40], [45, 55], [60, 75], [75, 100]]),
        CurveDef("Pump steady", [[20, 60], [40, 70], [60, 85], [70, 100]]),
        CurveDef("Full blast", [[0, 100], [100, 100]]),
    ])
