"""Probe expressions: tokenizer, recursive-descent parser and evaluator.

Grammar (conventional precedence, ^ is right-associative):

    expr   := term (('+' | '-') term)*
    term   := unary (('*' | '/') unary)*
    unary  := '-' unary | power
    power  := atom ('^' unary)?
    atom   := NUMBER | NAME | '(' expr ')'

NAME is either a system probe (``sys.<name>``) or a custom probe (a bare
identifier). No ``eval`` is ever used.
"""

from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

IDENT_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
SYS_PREFIX = "sys."

_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<num>(?:\d+\.?\d*|\.\d+))
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]*)?)
  | (?P<op>[-+*/^()])
""", re.VERBOSE)


class ExprError(Exception):
    def __init__(self, message: str, pos: int = 0, length: int = 1, suggestion: str | None = None):
        super().__init__(message)
        self.message = message
        self.pos = pos
        self.length = max(1, length)
        self.suggestion = suggestion


class EvalError(Exception):
    """Raised when an expression can't be evaluated right now (missing sensor, division by zero)."""


@dataclass(frozen=True)
class Token:
    kind: str   # 'num' | 'name' | 'op' | 'end'
    text: str
    pos: int


def is_valid_custom_name(name: str) -> bool:
    return bool(IDENT_RE.match(name))


def tokenize(src: str) -> list[Token]:
    out: list[Token] = []
    i = 0
    while i < len(src):
        m = _TOKEN_RE.match(src, i)
        if not m:
            raise ExprError(f"Unexpected character “{src[i]}”.", i)
        kind = m.lastgroup
        text = m.group()
        if kind == "name":
            if "." in text:
                prefix, _, rest = text.partition(".")
                if prefix != "sys":
                    raise ExprError(f"Unknown prefix “{prefix}.”; system probes start with “sys.”.", i, len(prefix) + 1)
                if not rest:
                    raise ExprError("Expected a sensor name after “sys.”.", i, len(text))
            elif not IDENT_RE.match(text):
                raise ExprError(f"“{text}” is not a valid name.", i, len(text))
        if kind != "ws":
            out.append(Token(kind, text, i))
        i = m.end()
    out.append(Token("end", "", len(src)))
    return out


# AST nodes are tuples: ('num', value) | ('ref', name, pos) | ('neg', node) | (op, left, right)

class _Parser:
    def __init__(self, tokens: list[Token]):
        self.t = tokens
        self.i = 0

    def peek(self) -> Token:
        return self.t[self.i]

    def take(self) -> Token:
        tok = self.t[self.i]
        self.i += 1
        return tok

    def parse(self):
        if self.peek().kind == "end":
            raise ExprError("Enter an expression.", 0)
        node = self.expr()
        tok = self.peek()
        if tok.kind != "end":
            raise ExprError(f"Unexpected “{tok.text}”.", tok.pos, len(tok.text))
        return node

    def expr(self):
        node = self.term()
        while self.peek().text in ("+", "-") and self.peek().kind == "op":
            op = self.take().text
            node = (op, node, self.term())
        return node

    def term(self):
        node = self.unary()
        while self.peek().text in ("*", "/") and self.peek().kind == "op":
            op = self.take().text
            node = (op, node, self.unary())
        return node

    def unary(self):
        if self.peek().kind == "op" and self.peek().text == "-":
            self.take()
            return ("neg", self.unary())
        return self.power()

    def power(self):
        base = self.atom()
        if self.peek().kind == "op" and self.peek().text == "^":
            self.take()
            return ("^", base, self.unary())
        return base

    def atom(self):
        tok = self.take()
        if tok.kind == "num":
            return ("num", float(tok.text))
        if tok.kind == "name":
            return ("ref", tok.text, tok.pos)
        if tok.kind == "op" and tok.text == "(":
            node = self.expr()
            close = self.take()
            if not (close.kind == "op" and close.text == ")"):
                raise ExprError("Missing “)”.", close.pos, max(1, len(close.text)))
            return node
        if tok.kind == "end":
            raise ExprError("The expression ends too early.", tok.pos)
        raise ExprError(f"Unexpected “{tok.text}”.", tok.pos, len(tok.text))


def parse(src: str):
    return _Parser(tokenize(src)).parse()


def refs(node) -> list[tuple[str, int]]:
    """Probe names referenced by an AST, with their positions, in order."""
    kind = node[0]
    if kind == "ref":
        return [(node[1], node[2])]
    if kind == "num":
        return []
    if kind == "neg":
        return refs(node[1])
    return refs(node[1]) + refs(node[2])


def evaluate(node, lookup: Callable[[str], float]) -> float:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "ref":
        return lookup(node[1])
    if kind == "neg":
        return -evaluate(node[1], lookup)
    a = evaluate(node[1], lookup)
    b = evaluate(node[2], lookup)
    try:
        if kind == "+":
            v = a + b
        elif kind == "-":
            v = a - b
        elif kind == "*":
            v = a * b
        elif kind == "/":
            if b == 0:
                raise EvalError("Division by zero.")
            v = a / b
        else:
            v = a ** b
    except (OverflowError, ZeroDivisionError) as e:
        raise EvalError(str(e)) from None
    if isinstance(v, complex) or math.isnan(v) or math.isinf(v):
        raise EvalError("The result is not a real number.")
    return v


def check(src: str, known: Iterable[str]) -> tuple[object, list[str]]:
    """Parse and check every name is known. Returns (ast, referenced names).

    Raises ExprError with a "did you mean" suggestion for unknown names.
    """
    ast = parse(src)
    known = set(known)
    names = []
    for name, pos in refs(ast):
        if name not in known:
            close = difflib.get_close_matches(name, sorted(known), n=1, cutoff=0.6)
            raise ExprError(f"Unknown probe “{name}”.", pos, len(name), close[0] if close else None)
        names.append(name)
    return ast, names


def find_cycle(graph: Mapping[str, Iterable[str]]) -> list[str] | None:
    """A reference cycle among custom probes, as a list of names, or None."""
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    stack: list[str] = []

    def visit(n: str) -> list[str] | None:
        color[n] = GREY
        stack.append(n)
        for m in graph.get(n, ()):
            if m not in color:
                continue
            if color[m] == GREY:
                return stack[stack.index(m):] + [m]
            if color[m] == WHITE:
                found = visit(m)
                if found:
                    return found
        stack.pop()
        color[n] = BLACK
        return None

    for n in graph:
        if color[n] == WHITE:
            found = visit(n)
            if found:
                return found
    return None


class ProbeSet:
    """Evaluates custom probes on top of system sensor readings, memoised per tick."""

    def __init__(self, system: Mapping[str, float | None], custom: Mapping[str, str]):
        self.system = system
        self.custom = dict(custom)
        self._asts: dict[str, object] = {}
        self._errors: dict[str, str] = {}
        known = set(system) | set(custom)
        for name, src in self.custom.items():
            try:
                self._asts[name], _ = check(src, known)
            except ExprError as e:
                self._errors[name] = e.message
        self._cache: dict[str, float] = {}
        self._active: set[str] = set()

    def value(self, name: str) -> float:
        if name in self.system:
            v = self.system[name]
            if v is None:
                raise EvalError(f"{name} can’t be read.")
            return v
        if name in self._cache:
            return self._cache[name]
        if name in self._errors:
            raise EvalError(self._errors[name])
        if name not in self._asts:
            raise EvalError(f"Unknown probe “{name}”.")
        if name in self._active:
            raise EvalError("Circular reference.")
        self._active.add(name)
        try:
            v = evaluate(self._asts[name], self.value)
        finally:
            self._active.discard(name)
        self._cache[name] = v
        return v

    def try_value(self, name: str) -> tuple[float | None, str | None]:
        try:
            return self.value(name), None
        except EvalError as e:
            return None, str(e)
