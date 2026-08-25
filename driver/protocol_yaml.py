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

# Far above what the protocol's documents nest and far below where the
# interpreter's own stack gives out.
MAX_DEPTH = 64

# What YAML separates with, and the whole of it: `str.strip()` would take
# every Unicode space with it, and a non-breaking or ideographic space is
# content — trimmed silently, a value comes back shorter than it was
# written, which is the quiet reshaping this module refuses everywhere
# else.
WHITESPACE = " \t"

# YAML 1.2 core resolution: what any conforming reader applies to a plain
# scalar, and therefore what decides whether a value this module writes comes
# back as the type it was given. The subset resolves three of core's kinds —
# null, boolean, decimal integer — in every spelling core gives them, since a
# document the driver did not write may use any of them. `on`, `yes`, and `On`
# are deliberately absent: they are booleans in YAML 1.1 and strings in 1.2,
# and `on:` is the key §9.1 declares.
CORE_NULL = re.compile(r"^(?:null|Null|NULL|~|)$")
CORE_BOOL = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
CORE_INT = re.compile(r"^[-+]?(?:0|[1-9][0-9]*)$")
# Core resolves these too, to types the subset does not carry. They are
# refused on read rather than returned as text, and quoted on write rather
# than emitted as a lookalike another reader would resolve away — which is
# what `protocol: 0.2` was: a string on the way out, a float on the way back,
# and a document the schema rejects for a type the driver never intended.
CORE_UNSUPPORTED = re.compile(
    r"^(?:[-+]?0[xX][0-9a-fA-F]+"  # hexadecimal integer
    r"|[-+]?0[oO][0-7]+"  # octal integer
    # A decimal with a leading zero is the one form readers disagree about:
    # `010` is ten to a 1.2 reader and eight to a 1.1 one, `0777` is 777 or
    # 511, and `08` is a number to the first and a string to the second.
    # Resolving it either way picks a side, so the subset does not carry it
    # — the same treatment its octal and hexadecimal neighbours get.
    r"|[-+]?0[0-9]+"
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
# could change meaning — a leading `{` or `[` opens a flow collection, so a
# `{run}/…` path is always quoted, which is also how the shipped fixtures
# write it — no leading/trailing space, no characters the reader would
# misparse. The first character is held to a letter, a digit, or `_`, which
# is narrower than YAML asks: a leading `(` is an ordinary character to any
# reader, and quoting it costs nothing this module needs back. Conservative
# on purpose: quoting more than YAML strictly requires is canonical here,
# misreading is the only failure that matters.
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


# Every break the split below treats as one. A document written with
# carriage returns is read line by line like any other, so a diagnostic
# that counted `\n` alone reported every defect in it against line 1 —
# the line-numbered error this module promises, no better than none.
LINE_BREAK = re.compile(r"\r\n|\r|\n")


def _line_number(text: str, offset: int) -> int:
    return len(LINE_BREAK.findall(text[:offset])) + 1


def _content_lines(text: str) -> list[_Line]:
    # Raw control characters are not YAML content, and this module cannot
    # read them harmlessly: NUL and its neighbours would survive into a
    # value and be written back, while NEL and U+2028/U+2029 are consumed as
    # line breaks by the split below — a document that silently loses its
    # shape rather than one that is refused. Tab, newline, and carriage
    # return are the three YAML does allow, and the emitter escapes every
    # character named here, so nothing the driver writes lands on this.
    # A stream may open with U+FEFF, which marks its encoding rather than
    # its content: every conforming reader drops it, and one that keeps it
    # reads `\ufeffrun` where the document says `run` — a state file
    # another tool wrote, resumed against keys nothing recognizes. Only the
    # stream's own: one anywhere else is content.
    if text.startswith("\ufeff"):
        text = text[1:]
    found = RAW_FORBIDDEN.search(text)
    if found is not None:
        raise ProtocolYamlError(
            _line_number(text, found.start()),
            f"raw control character in the document: {found.group()!r}",
        )
    lines: list[_Line] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip(" \t"))]:
            raise ProtocolYamlError(number, "tab in indentation")
        stripped = _strip_comment(raw, number)
        if not stripped.strip(WHITESPACE):
            continue
        lines.append(
            _Line(
                number,
                len(stripped) - len(stripped.lstrip(WHITESPACE)),
                stripped.strip(WHITESPACE),
            )
        )
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
    index = _scalar_start(raw)
    if index < len(raw) and raw[index] == '"':
        # A quoted scalar: everything to its closing quote is content, `#`
        # included, and a comment can only begin after it.
        index += 1
        while index < len(raw):
            if raw[index] == "\\":
                index += 2
                continue
            if raw[index] == '"':
                break
            index += 1
        else:
            raise ProtocolYamlError(number, "unterminated double-quoted scalar")
        if index >= len(raw):
            raise ProtocolYamlError(number, "unterminated double-quoted scalar")
        index += 1
    while index < len(raw):
        if raw[index] == "#" and (index == 0 or raw[index - 1] in " \t"):
            return raw[:index]
        index += 1
    return raw


def _scalar_start(raw: str) -> int:
    """Where this line's scalar begins — past the indentation, a sequence
    dash, and a `key: ` if the line carries one.

    Quotes delimit a scalar only when the scalar itself starts quoted;
    anywhere else they are ordinary characters, so `note: 5" # inches` is
    the plain scalar `5"` with a comment after it rather than the start of
    a quoted scalar that never closes. Knowing where a scalar may begin is
    what tells the two apart.
    """
    index = len(raw) - len(raw.lstrip(WHITESPACE))
    if raw[index : index + 2] == "- ":
        index += 2
        index += len(raw[index:]) - len(raw[index:].lstrip(WHITESPACE))
    rest = raw[index:]
    if rest.startswith(('"', "#")):
        return index
    marker = min(
        (found for found in (rest.find(": "), rest.find(":\t")) if found != -1),
        default=-1,
    )
    if marker != -1:
        index += marker + 2
        return index + len(raw[index:]) - len(raw[index:].lstrip(WHITESPACE))
    if rest.rstrip(WHITESPACE).endswith(":"):
        # `key:` alone — the value is the block that follows, and this line
        # carries no scalar for a quote to open.
        return len(raw)
    return index


def _parse_block(
    lines: list[_Line], start: int, indent: int, depth: int = 0
) -> tuple[object, int]:
    # Nesting is recursion here, and Python's stack is not a subset rule: a
    # document nested past it raised `RecursionError` out of the parser and
    # past every handler that turns malformed input into a reported defect.
    # The limit is explicit and far above anything the protocol's documents
    # reach — run state nests four deep, a declaration five — so the depth
    # that trips it is a document no reader should be asked to carry.
    if depth > MAX_DEPTH:
        raise ProtocolYamlError(lines[start].number, f"nested past {MAX_DEPTH} levels")
    line = lines[start]
    if line.indent != indent:
        raise ProtocolYamlError(line.number, f"expected indent {indent}, got {line.indent}")
    if line.content.startswith("- ") or line.content == "-":
        return _parse_sequence(lines, start, indent, depth)
    return _parse_mapping(lines, start, indent, depth)


def _parse_mapping(
    lines: list[_Line], start: int, indent: int, depth: int = 0
) -> tuple[dict, int]:
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
            mapping[key], index = _parse_block(
                lines, index + 1, lines[index + 1].indent, depth + 1
            )
        else:
            mapping[key] = None
            index += 1
        if index < len(lines) and lines[index].indent > indent:
            raise ProtocolYamlError(lines[index].number, "unexpected deeper indentation")
    return mapping, index


def _parse_sequence(
    lines: list[_Line], start: int, indent: int, depth: int = 0
) -> tuple[list, int]:
    sequence: list[object] = []
    index = start
    while index < len(lines) and lines[index].indent == indent:
        line = lines[index]
        if not (line.content.startswith("- ") or line.content == "-"):
            raise ProtocolYamlError(line.number, "mapping entry inside a sequence")
        rest = line.content[2:].strip(WHITESPACE) if line.content != "-" else ""
        if not rest:
            # `-` alone: the item is the deeper-indented block that follows.
            if index + 1 < len(lines) and lines[index + 1].indent > indent:
                item, index = _parse_block(
                    lines, index + 1, lines[index + 1].indent, depth + 1
                )
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
            item, used = _parse_mapping(block, 0, item_indent, depth + 1)
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
    # YAML separates a key from its value with a space or a tab, so a
    # document written with the second is legal and this module must not
    # call it malformed — the same pair the scalar check treats as a
    # mapping indicator.
    if not separator or (rest and rest[0] not in " \t"):
        raise ProtocolYamlError(line.number, "expected `key:` or `key: value`")
    key = head.strip(WHITESPACE)
    # The tab is here and not in the emitter's list alone deliberately: this
    # subset has no quoted-key form, so a key the emitter cannot write is
    # one the reader must not accept — otherwise a document loads and the
    # next save refuses it, which is the round trip broken from the inside.
    # A space is different and stays readable: the emitter writes it.
    if not key or not _is_plain_key(key):
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
    return key, rest.strip(WHITESPACE)


def _is_mapping_start(rest: str) -> bool:
    """Does a dash line's remainder open a mapping (`- key: value`)? A quoted
    scalar never does, and a plain scalar with `: ` in it is a key."""
    if rest.startswith('"'):
        return False
    head, separator, tail = rest.partition(":")
    # Either separator YAML gives, as everywhere else a key is recognized:
    # read without the tab, `- key:\tvalue` falls through to the scalar
    # resolver and is refused as a mapping indicator, which is a document
    # the subset admits reported as one it does not.
    return bool(separator) and (not tail or tail[0] in WHITESPACE) and bool(
        head.strip(WHITESPACE)
    )


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
    if ": " in token or ":\t" in token or token.endswith(":"):
        raise ProtocolYamlError(
            number, f"plain scalar carries a mapping indicator: {token!r}"
        )
    if CORE_NULL.match(token):
        return None
    if CORE_BOOL.match(token):
        return token.lower() == "true"
    if CORE_INT.match(token):
        try:
            return int(token)
        except ValueError as error:
            # Python caps `int()` at 4300 digits, and YAML puts no ceiling
            # on an integer's length — so a value of exactly this shape can
            # raise where every malformed one is reported, escaping the
            # errors that carry a defect to an exit code.
            raise ProtocolYamlError(
                number, f"integer outside the subset: {error}"
            ) from error
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
                lines.append(f"{pad}- {first.strip(WHITESPACE)}")
                lines += others
            elif isinstance(item, list) and item:
                lines.append(f"{pad}-")
                lines += _emit_block(item, indent + INDENT)
            else:
                lines.append(f"{pad}- {_emit_scalar(item)}")
        return lines
    raise TypeError(f"not a collection: {type(data).__name__}")


def _is_plain_key(key: str) -> bool:
    """Whether this text is a plain key on the page, read by both halves.

    A key is written plain and read plain, so what YAML forbids at the start
    of a plain scalar it forbids here — the tag indicator among them, which
    made `!tag: 1` read as a string key on one side and emit as tag syntax
    on the other. A `- ` prefix is the sharper case, being legal in a key's
    characters and not in its position: `dumps({"- item": 1})` wrote
    `- item: 1`, which the reader takes as a sequence, so a mapping went out
    and a list came back.
    """
    if key[0] in INDICATORS or key.startswith("- ") or key == "-":
        return False
    return not any(character in key for character in "{}[],#?|>\t")


def _check_key(key: object) -> None:
    # A space inside a key is content — `token count: 1` is a plain key the
    # reader accepts, and an instrumentation mapping (§10) is where one
    # plausibly appears. Refusing it here made a document this module reads
    # one it cannot write back: state that loads and then fails on save.
    # Leading and trailing whitespace still go, being invisible where the
    # key's identity is the thing, and a tab with them.
    if (
        not isinstance(key, str)
        or not key
        or key != key.strip(WHITESPACE)
        or ":" in key
        or not _is_plain_key(key)
    ):
        raise ValueError(f"not a plain key: {key!r}")
    # A key is written plain, so anything the reader forbids raw would be
    # written raw: a newline in a key emits two lines where the document
    # declared one field, and a control character emits text the reader
    # refuses outright. There is no quoted-key form here to fall back on.
    if "\n" in key or "\r" in key or RAW_FORBIDDEN.search(key):
        raise ValueError(f"key carries a character YAML cannot write plain: {key!r}")
    # The emitting half of the rule the reader applies: this subset has no
    # quoted keys, so a key another reader would resolve away is one this
    # module cannot write at all rather than one it writes carefully.
    if _resolves_as_non_string(key):
        raise ValueError(f"key would resolve as a non-string: {key!r}")
    # The surrogate rule `_quote` applies to a value, applied to the other
    # half of the mapping: UTF-8 cannot carry one on either side, and a key
    # accepted here reaches the save that encodes the file and raises there,
    # after the state it belongs to has been assembled.
    surrogate = next((c for c in key if 0xD800 <= ord(c) <= 0xDFFF), None)
    if surrogate is not None:
        raise ValueError(f"key carries a surrogate, which UTF-8 cannot encode: {key!r}")


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
    # The reader refuses a surrogate escape because UTF-8 cannot carry one;
    # the emitter has to refuse the code point for the same reason, or a
    # value it accepted reaches the save that encodes the file and fails
    # there — after the state it belongs to has been assembled.
    surrogate = next((c for c in value if 0xD800 <= ord(c) <= 0xDFFF), None)
    if surrogate is not None:
        raise ValueError(
            f"value carries a surrogate, which UTF-8 cannot encode: {value!r}"
        )
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
