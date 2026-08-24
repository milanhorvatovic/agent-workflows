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

# YAML 1.2 core resolution: what any conforming reader applies to a plain
# scalar, and therefore what decides whether a value this module writes comes
# back as the type it was given. The subset resolves three of core's kinds —
# null, boolean, decimal integer — in every spelling core gives them, since a
# document the driver did not write may use any of them. `on`, `yes`, and `On`
# are deliberately absent: they are booleans in YAML 1.1 and strings in 1.2,
# and `on:` is the key §9.1 declares.
CORE_NULL = re.compile(r"^(?:null|Null|NULL|~|)$")
CORE_BOOL = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
CORE_INT = re.compile(r"^[-+]?[0-9]+$")
# Core resolves these too, to types the subset does not carry. They are
# refused on read rather than returned as text, and quoted on write rather
# than emitted as a lookalike another reader would resolve away — which is
# what `protocol: 0.2` was: a string on the way out, a float on the way back,
# and a document the schema rejects for a type the driver never intended.
CORE_UNSUPPORTED = re.compile(
    r"^(?:[-+]?0[xX][0-9a-fA-F]+"  # hexadecimal integer
    r"|[-+]?0[oO][0-7]+"  # octal integer
    r"|[-+]?(?:\.[0-9]+|[0-9]+\.[0-9]*)(?:[eE][-+]?[0-9]+)?"  # float with a fraction
    r"|[-+]?[0-9]+[eE][-+]?[0-9]+"  # float with an exponent
    r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"  # infinity, not-a-number
)
# Not a core kind, and quoted on write all the same: readers in this
# ecosystem resolve a plain timestamp to a date or a datetime — the
# conformance suite's does — while §10 declares `at` a string. The
# asymmetry is deliberate. On write the module must leave nothing a reader
# can retype, which is why every shipped fixture quotes its timestamps; on
# read it resolves as 1.2 core does, since a producer writing a plain
# timestamp under that schema meant the string core gives back.
TIMESTAMP = re.compile(
    r"^(?:[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[Tt]|[ \t]+)[0-9]{1,2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9]{1,2}(?::[0-9]{2})?))?)$"
)

# A plain scalar the emitter may leave unquoted: no YAML indicator where it
# could change meaning — a leading `{`, `[`, or `(` opens flow syntax, so a
# `{run}/…` path is always quoted, which is also how the shipped fixtures
# write it — no leading/trailing space, no characters the reader would
# misparse. Conservative on purpose: quoting more than YAML strictly requires
# is canonical here, misreading is the only failure that matters.
PLAIN_SAFE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9 _./:{}()\[\]-]*$")

# The characters YAML forbids at the start of a plain scalar: quoting and
# anchors, tags and aliases, block scalars, flow punctuation, a comment, a
# directive, and the two reserved indicators. A token beginning with one of
# these is not a scalar in any context, so reading it as text would accept a
# document no conforming reader accepts — and the emitter would then rewrite
# it as a quoted string, laundering the malformation into valid YAML.
INDICATORS = "'\"&*!|>[]{},#%@`"

# The characters a document may not carry raw: C0 apart from tab, newline,
# and carriage return, DEL and C1 — NEL among them — and the two Unicode
# line separators. Quoted, each has an escape; raw, each is either invalid
# YAML or a line break the reader would consume silently.
RAW_FORBIDDEN = re.compile("[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f-\\x9f\\u2028\\u2029]")

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
    """Emit the canonical form of `data`; `loads` round-trips it.

    A document is a non-empty mapping or sequence, which is what both shapes
    this module exists for are — run state and a `metadata.workflow` block.
    A bare scalar was emitted here once and `loads` never read one back: the
    reader parses a document as a mapping or a sequence and nothing else, so
    what `dumps` wrote could not be reloaded, breaking the round trip this
    line promises. Refusing is the half that keeps the promise true, since
    widening the reader would admit a document the protocol never has.
    """
    if not isinstance(data, (dict, list)) or not data:
        raise ValueError(f"not a document: {data!r}")
    return "\n".join(_emit_block(data, 0)) + "\n"


def _content_lines(text: str) -> list[_Line]:
    # Raw control characters are not YAML content, and this module cannot
    # read them harmlessly: NUL and its neighbours would survive into a
    # value and be written back, while NEL and U+2028/U+2029 are consumed as
    # line breaks by the split below — a document that silently loses its
    # shape rather than one that is refused. Tab, newline, and carriage
    # return are the three YAML does allow, and the emitter escapes every
    # character named here, so nothing the driver writes lands on this.
    found = RAW_FORBIDDEN.search(text)
    if found is not None:
        raise ProtocolYamlError(
            text.count("\n", 0, found.start()) + 1,
            f"raw control character in the document: {found.group()!r}",
        )
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
    # A key is resolved like any other plain scalar, and a key's type decides
    # the mapping's shape rather than one value inside it: `true:` is a
    # boolean key to a conforming reader and a string key here, and `1:` and
    # `01:` are one integer key there and two distinct string keys here — a
    # document that reads as two different mappings depending on who opens
    # it. Quoting is how YAML says "the string", and quoted keys are outside
    # this subset, so the only reading left is to refuse.
    if _resolves_as_non_string(key):
        raise ProtocolYamlError(
            line.number, f"key would resolve as a non-string: {key!r}"
        )
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
    if token[0] in INDICATORS:
        raise ProtocolYamlError(number, f"scalar outside the subset: {token!r}")
    # `-`, `?`, and `:` open a plain scalar only when what follows is not a
    # space: `-7` is a number and `- item` is a sequence entry written where
    # a value belongs. Read as text, the second is a document this module
    # accepts and every conforming reader refuses.
    if token[0] in "-?:" and (len(token) == 1 or token[1] in " \t"):
        raise ProtocolYamlError(number, f"scalar outside the subset: {token!r}")
    # A plain scalar carrying a mapping indicator is not a plain scalar:
    # `a: value: other` is a nested mapping written on one line, which YAML
    # refuses, and `a: value:` is the same shape with an empty value. Read
    # as text they are exactly the misreading this module exists to avoid —
    # and the emitter quotes both forms, so nothing it writes lands here.
    if ": " in token or token.endswith(":"):
        raise ProtocolYamlError(
            number, f"plain scalar carries a mapping indicator: {token!r}"
        )
    if CORE_NULL.match(token):
        return None
    if CORE_BOOL.match(token):
        return token.lower() == "true"
    if CORE_INT.match(token):
        return int(token)
    if CORE_UNSUPPORTED.match(token):
        raise ProtocolYamlError(number, f"scalar type outside the subset: {token!r}")
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
    # The emitting half of the rule the reader applies: this subset has no
    # quoted keys, so a key another reader would resolve away is one this
    # module cannot write at all rather than one it writes carefully.
    if _resolves_as_non_string(key):
        raise ValueError(f"key would resolve as a non-string: {key!r}")


def _resolves_as_non_string(value: str) -> bool:
    """Whether a conforming reader would resolve this text as something
    other than the string it is. Such a value has to be quoted, or the
    document says one thing to this module and another to everyone else."""
    return bool(
        CORE_NULL.match(value)
        or CORE_BOOL.match(value)
        or CORE_INT.match(value)
        or CORE_UNSUPPORTED.match(value)
        or TIMESTAMP.match(value)
    )


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
        and not _resolves_as_non_string(value)
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
