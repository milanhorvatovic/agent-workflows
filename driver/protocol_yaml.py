"""A YAML subset for the protocol's own documents, stdlib-only.

The driver reads and writes exactly two YAML shapes — `workflow-state.yaml`
(protocol/spec.md §10) and the `metadata.workflow` blocks in stage and
workflow files (§9) — and both stay inside a deliberately small subset:
block mappings and sequences by indentation, plain and double-quoted
scalars, integers, booleans, null, empty flow collections (`[]`, `{}`), and
comments. Anchors, aliases, tags, multi-line scalars, and non-empty flow
collections are outside the subset and are rejected, never misread: the
run-state format is protocol-owned with one writer, and the authored blocks
are validated against the schemas in CI, so anything outside the subset is
a defect to surface rather than input to accommodate.

`dumps` emits the canonical form `loads` accepts, and round-trips: strings
that could be misread as another scalar type — or that carry characters
plain YAML cannot — are double-quoted, everything else stays plain. YAML
1.2 core semantics throughout: `true`/`false`/`null` only, no octal
surprises, no `yes`/`on` booleans — the driver must read `on:` as the
string key spec §9.1 declares, which is the known YAML 1.1 failure.
"""

from __future__ import annotations

import re

INDENT = 2

# YAML 1.2 core scalars the subset resolves; everything else plain is a string.
NULLS = frozenset({"null", "~", ""})
BOOLEANS = {"true": True, "false": False}
INTEGER = re.compile(r"^-?(0|[1-9][0-9]*)$")

# A plain scalar the emitter may leave unquoted: no YAML indicator where it
# could change meaning — a leading `{`, `[`, or `(` opens flow syntax, so a
# `{run}/…` path is always quoted, which is also how the shipped fixtures
# write it — no leading/trailing space, no characters the reader would
# misparse. Conservative on purpose: quoting more than YAML strictly requires
# is canonical here, misreading is the only failure that matters.
PLAIN_SAFE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9 _./:{}()\[\]-]*$")

ESCAPES = {
    "\\": "\\",
    '"': '"',
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\x00",
}


class ProtocolYamlError(ValueError):
    """The text is outside the subset, or not YAML at all."""

    def __init__(self, line_number: int, message: str) -> None:
        super().__init__(f"line {line_number}: {message}")
        self.line_number = line_number


class _Line:
    __slots__ = ("number", "indent", "content")

    def __init__(self, number: int, indent: int, content: str) -> None:
        self.number = number
        self.indent = indent
        self.content = content


def loads(text: str) -> object:
    """Parse one document of the subset; raise ProtocolYamlError outside it."""
    lines = _content_lines(text)
    if not lines:
        return None
    value, index = _parse_block(lines, 0, lines[0].indent)
    if index != len(lines):
        raise ProtocolYamlError(lines[index].number, "content after the document")
    return value


def dumps(data: object) -> str:
    """Emit the canonical form of `data`; `loads` round-trips it."""
    if isinstance(data, (dict, list)) and data:
        return "\n".join(_emit_block(data, 0)) + "\n"
    # A bare scalar or empty collection is a one-line document.
    return _emit_scalar(data) + "\n"


def _content_lines(text: str) -> list[_Line]:
    lines: list[_Line] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ProtocolYamlError(number, "tab in indentation")
        stripped = _strip_comment(raw, number)
        if not stripped.strip():
            continue
        lines.append(_Line(number, len(stripped) - len(stripped.lstrip()), stripped.strip()))
    return lines


def _strip_comment(raw: str, number: int) -> str:
    """Drop a trailing comment — a `#` outside quotes, at start or after a
    space, per YAML. Tracking the quote state is what keeps a `#` inside a
    quoted scalar as content.

    Only the double quote opens a scalar here. A single quote is a character
    like any other at this stage — `don't` is a plain scalar YAML reads as
    the word it is — and the one form that is outside the subset, a scalar
    that *begins* with a quote, is refused where scalars are resolved rather
    than wherever an apostrophe appears.
    """
    in_quotes = False
    index = 0
    while index < len(raw):
        character = raw[index]
        if in_quotes:
            if character == "\\":
                index += 1
            elif character == '"':
                in_quotes = False
        elif character == '"':
            in_quotes = True
        elif character == "#" and (index == 0 or raw[index - 1] in " \t"):
            return raw[:index]
        index += 1
    if in_quotes:
        raise ProtocolYamlError(number, "unterminated double-quoted scalar")
    return raw


def _parse_block(lines: list[_Line], start: int, indent: int) -> tuple[object, int]:
    line = lines[start]
    if line.indent != indent:
        raise ProtocolYamlError(line.number, f"expected indent {indent}, got {line.indent}")
    if line.content.startswith("- ") or line.content == "-":
        return _parse_sequence(lines, start, indent)
    return _parse_mapping(lines, start, indent)


def _parse_mapping(lines: list[_Line], start: int, indent: int) -> tuple[dict, int]:
    mapping: dict[str, object] = {}
    index = start
    while index < len(lines) and lines[index].indent == indent:
        line = lines[index]
        if line.content.startswith("- ") or line.content == "-":
            raise ProtocolYamlError(line.number, "sequence entry inside a mapping")
        key, rest = _split_key(line)
        if key in mapping:
            raise ProtocolYamlError(line.number, f"duplicate key {key!r}")
        if rest:
            mapping[key] = _parse_scalar(rest, line.number)
            index += 1
        elif index + 1 < len(lines) and lines[index + 1].indent > indent:
            mapping[key], index = _parse_block(lines, index + 1, lines[index + 1].indent)
        else:
            mapping[key] = None
            index += 1
        if index < len(lines) and lines[index].indent > indent:
            raise ProtocolYamlError(lines[index].number, "unexpected deeper indentation")
    return mapping, index


def _parse_sequence(lines: list[_Line], start: int, indent: int) -> tuple[list, int]:
    sequence: list[object] = []
    index = start
    while index < len(lines) and lines[index].indent == indent:
        line = lines[index]
        if not (line.content.startswith("- ") or line.content == "-"):
            raise ProtocolYamlError(line.number, "mapping entry inside a sequence")
        rest = line.content[2:].strip() if line.content != "-" else ""
        if not rest:
            # `-` alone: the item is the deeper-indented block that follows.
            if index + 1 < len(lines) and lines[index + 1].indent > indent:
                item, index = _parse_block(lines, index + 1, lines[index + 1].indent)
                sequence.append(item)
            else:
                sequence.append(None)
                index += 1
            continue
        if _is_mapping_start(rest):
            # `- key: value`: the dash line opens a mapping whose further keys
            # are indented past the dash, aligned with the inline key.
            item_indent = indent + 2
            virtual = _Line(line.number, item_indent, rest)
            tail = lines[index + 1 :]
            consumed_from_tail = 0
            for candidate in tail:
                if candidate.indent >= item_indent:
                    consumed_from_tail += 1
                else:
                    break
            block = [virtual] + tail[:consumed_from_tail]
            item, used = _parse_mapping(block, 0, item_indent)
            if used != len(block):
                raise ProtocolYamlError(block[used].number, "unexpected indentation in sequence item")
            sequence.append(item)
            index += 1 + consumed_from_tail
        else:
            sequence.append(_parse_scalar(rest, line.number))
            index += 1
    return sequence, index


def _split_key(line: _Line) -> tuple[str, str]:
    content = line.content
    if content.startswith('"'):
        raise ProtocolYamlError(line.number, "quoted keys are outside the subset")
    head, separator, rest = content.partition(":")
    if not separator or (rest and not rest.startswith(" ")):
        raise ProtocolYamlError(line.number, "expected `key:` or `key: value`")
    key = head.strip()
    if not key or any(c in key for c in "{}[],&*#?|>%@`\"'"):
        raise ProtocolYamlError(line.number, f"not a plain key: {head!r}")
    return key, rest.strip()


def _is_mapping_start(rest: str) -> bool:
    """Does a dash line's remainder open a mapping (`- key: value`)? A quoted
    scalar never does, and a plain scalar with `: ` in it is a key."""
    if rest.startswith('"'):
        return False
    head, separator, tail = rest.partition(":")
    return bool(separator) and (not tail or tail.startswith(" ")) and bool(head.strip())


def _parse_scalar(token: str, number: int) -> object:
    if token == "[]":
        return []
    if token == "{}":
        return {}
    if token.startswith('"'):
        return _unquote(token, number)
    if token.startswith(("'", "&", "*", "!", "|", ">", "[", "{")):
        raise ProtocolYamlError(number, f"scalar outside the subset: {token!r}")
    if token in NULLS:
        return None
    if token in BOOLEANS:
        return BOOLEANS[token]
    if INTEGER.match(token):
        return int(token)
    return token


def _unquote(token: str, number: int) -> str:
    if len(token) < 2 or not token.endswith('"'):
        raise ProtocolYamlError(number, "unterminated double-quoted scalar")
    body = token[1:-1]
    out: list[str] = []
    index = 0
    while index < len(body):
        character = body[index]
        if character != "\\":
            if character == '"':
                raise ProtocolYamlError(number, "content after a quoted scalar")
            out.append(character)
            index += 1
            continue
        index += 1
        if index >= len(body):
            raise ProtocolYamlError(number, "dangling escape")
        escape = body[index]
        if escape in ESCAPES:
            out.append(ESCAPES[escape])
            index += 1
            continue
        width = {"x": 2, "u": 4}.get(escape)
        if width is None:
            raise ProtocolYamlError(number, f"escape outside the subset: \\{escape}")
        digits = body[index + 1 : index + 1 + width]
        if len(digits) != width or any(d not in "0123456789abcdefABCDEF" for d in digits):
            raise ProtocolYamlError(number, f"malformed \\{escape} escape")
        codepoint = int(digits, 16)
        # A lone surrogate is not a character UTF-8 can carry, and this
        # module's documents are read and written as UTF-8: accepted here,
        # it would load, pass validation, and then break the next save with
        # an encoding error — a state file the driver could no longer
        # persist. The subset ends where the encoding does.
        if 0xD800 <= codepoint <= 0xDFFF:
            raise ProtocolYamlError(
                number, f"\\{escape}{digits} is a surrogate, which UTF-8 cannot carry"
            )
        out.append(chr(codepoint))
        index += 1 + width
    return "".join(out)


def _emit_block(data: object, indent: int) -> list[str]:
    pad = " " * indent
    lines: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            _check_key(key)
            if isinstance(value, (dict, list)) and value:
                lines.append(f"{pad}{key}:")
                lines += _emit_block(value, indent + INDENT)
            else:
                lines.append(f"{pad}{key}: {_emit_scalar(value)}")
        return lines
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item:
                first, *others = _emit_block(item, indent + INDENT)
                lines.append(f"{pad}- {first.strip()}")
                lines += others
            elif isinstance(item, list) and item:
                lines.append(f"{pad}-")
                lines += _emit_block(item, indent + INDENT)
            else:
                lines.append(f"{pad}- {_emit_scalar(item)}")
        return lines
    raise TypeError(f"not a collection: {type(data).__name__}")


def _check_key(key: object) -> None:
    if not isinstance(key, str) or not key or any(c in key for c in ":{}[],&*#?|>%@`\"' \t"):
        raise ValueError(f"not a plain key: {key!r}")


def _emit_scalar(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        if value:
            raise ValueError("non-empty list is not a scalar")
        return "[]"
    if isinstance(value, dict):
        if value:
            raise ValueError("non-empty mapping is not a scalar")
        return "{}"
    if not isinstance(value, str):
        raise TypeError(f"not a subset value: {type(value).__name__}")
    if (
        PLAIN_SAFE.match(value)
        and value not in NULLS
        and value not in BOOLEANS
        and not INTEGER.match(value)
        and not value.endswith(" ")
        and ": " not in value
        # A trailing colon opens a mapping wherever a value may start one:
        # `- note:` is a sequence of one mapping to the reader, not the
        # string it was given, so a manifest path or a stall flag ending in
        # `:` would come back as a different document than it went in as.
        and not value.endswith(":")
        and " #" not in value
    ):
        return value
    return _quote(value)


def _quote(value: str) -> str:
    out = ['"']
    for character in value:
        if character == "\\":
            out.append("\\\\")
        elif character == '"':
            out.append('\\"')
        elif character == "\n":
            out.append("\\n")
        elif character == "\t":
            out.append("\\t")
        elif character == "\r":
            out.append("\\r")
        elif (
            ord(character) < 0x20
            or 0x7F <= ord(character) <= 0x9F
            or character in "\u2028\u2029"
        ):
            # Every character `str.splitlines` breaks on has to leave here as
            # an escape, or the emitter writes a document the reader sees as
            # two lines: C0 and C1 cover its \v, \f, \x1c-\x1e and NEL, and
            # U+2028/U+2029 are the two it splits on beyond them.
            out.append(f"\\u{ord(character):04x}")
        else:
            out.append(character)
    out.append('"')
    return "".join(out)
