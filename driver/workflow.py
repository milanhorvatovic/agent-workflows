"""Workflow composition: the declared structure the state machine executes.

A workflow file composes stages by reference (protocol/spec.md §6.1); each
stage declares its members in record order (§9.4) and its steps' contracts
(§9.1). This module reads those declarations — nothing else: prose stays
prose, and a declaration the files do not carry is an error here rather
than something to infer, because the conformance suite already holds the
declarations complete and an inference layer would quietly outlive it.

The framework directory is the consuming project's copy of the protocol
content — where `workflows/` and `workflows/stages/` live. Resolving it is
project configuration, like the artifact root (§8.1); the driver takes it
as an argument rather than assuming the two share a parent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import PROTOCOL, PROTOCOL_VERSION, implements
from .config import ROLES
from .protocol_yaml import WHITESPACE, ProtocolYamlError, loads

# Composition is the numbered list of stage references, at the first column
# (§6.1: workflows compose stages by reference). A link anywhere else is
# prose about a stage rather than a claim to run it — a workflow that
# discusses a stage it does not compose, or names one inside an example,
# would otherwise execute it silently. This is the same rule the
# declaration surface takes for fences: first column or it is not structure.
STAGE_REFERENCE = re.compile(
    r"^[0-9]+\. \[[^\]]*\]\(stages/([a-z][a-z0-9-]*)\.md\)", re.MULTILINE
)
# The stage schema's member-id shape, carried verbatim: an id it would
# reject becomes a run-state record `load` refuses, one run too late to
# say which declaration wrote it. test_workflow pins the two.
MEMBER_ID = re.compile('^[a-z][a-z0-9]*(-[a-z0-9]+)*$')
# The complete form, anchored to line end — a truncated `### thing (`
# must not declare a step whose contract then associates (the
# conformance suite holds the same rule).
STEP_HEADING = re.compile(
    r"^### (?P<id>[a-z][a-z0-9-]*) \((?P<role>[a-z]+)\)[ \t]*$", re.MULTILINE
)
# A first-column key and its value. The key is captured rather than spelled
# out, because what names it is its resolved value: a document-start marker
# may precede it, the explicit indicator may, a tag or an anchor may, and
# the name itself may be quoted and escaped. Every one of those is the same
# key to a reader that parses the document, and a pattern that matched one
# spelling filed the declarations under the others as prose. `_key_name`
# decides which matches are `metadata`.
KEY_TOKEN = (
    r'(?P<key>"(?:\\.|[^"\\\n])*"|\'(?:\'\'|[^\'\n])*\'|[^\s:#][^:#\n]*?)'
)
METADATA_KEY = re.compile(
    r'^(?:---[ \t]+)?(?:\?[ \t]+)?(?:[!&]\S*[ \t]+){0,2}'
    + KEY_TOKEN
    + r'[ \t]*:(?P<rest>.*)$',
    re.MULTILINE,
)
# YAML's explicit key form spells the same key over two lines — `? metadata`
# and the value on the `:` line beneath — which resolves to `metadata` in
# any reader that parses it. The `rest` group is that value, so both forms
# are read the same way from here on.
EXPLICIT_KEY = re.compile(
    # The indicator may stand alone, its key on the line beneath it: the
    # key is a node like any other and takes its own line as readily as it
    # shares one.
    r'^\?(?:[ \t]+|[ \t]*\n[ \t]+)(?:[!&]\S*[ \t]+){0,2}'
    + KEY_TOKEN
    + r'[ \t]*\n[ \t]*:(?P<rest>.*)$',
    re.MULTILINE,
)
WORKFLOW_KEY = re.compile(r'^[ \t]+[\'"]?workflow[\'"]?[ \t]*:')
WORKFLOW_INLINE = re.compile(r'[{,][ \t]*[\'"]?workflow[\'"]?[ \t]*:')
# Every heading of each level, whatever it says: a contract belongs to the
# nearest heading above it, so what closed a step section matters as much as
# what opened one. CommonMark ends the marker with a space, a tab, or the
# line — `###`, `###\tname`, and `### name` are all headings, and a scan
# that knew only the space would let a contract below one of the others
# bind to a step further up the file.
# A gate is declared as a bullet in the stage's own `## Gates` section —
# the exact level-2 heading, bounded by the next one, so a `### Gates` or
# an inline mention does not open it and a bullet under `## Notes` is not
# a gate.
GATES_HEADING = re.compile(r"^## Gates[ \t]*$", re.MULTILINE)
GATE_BULLET = re.compile(r"^- \*\*(?P<id>[a-z][a-z0-9-]*)\*\*", re.MULTILINE)
# Anything bullet-and-bold in a Gates section is a gate declaration; one
# that then fails GATE_BULLET's id form is a malformed gate to report,
# never one to read as nothing — the conformance suite reads it the same.
GATE_SHAPED = re.compile(r"^- \*\*(?P<raw>[^*\n]+)\*\*", re.MULTILINE)
H3_HEADING = re.compile(r"^###(?=[ \t]|$)", re.MULTILINE)
H2_HEADING = re.compile(r"^##(?=[ \t]|$)", re.MULTILINE)
# One fence model, the conformance suite's: either marker, three or more,
# up to three spaces of indent, closed by a run at least as long or running
# to the end of the file. Discovery consumes outermost fences whole, so a
# fence inside a longer wrapper is part of the example that wraps it and
# never a declaration of its own.
FENCE = re.compile(
    r"^(?P<indent> {0,3})"
    r"(?:(?P<bt>```+)(?P<bti>[^`\n]*)\n(?P<btb>.*?)(?:^ {0,3}(?P=bt)`*[ \t]*$|\Z)"
    r"|(?P<td>~~~+)(?P<tdi>[^\n]*)\n(?P<tdb>.*?)(?:^ {0,3}(?P=td)~*[ \t]*$|\Z))",
    re.DOTALL | re.MULTILINE,
)

VERDICTS = ("PASS", "PASS_WITH_CONDITIONS", "FAIL")

# The four the spec defines (§8.1, §9.2), and the shape a token takes —
# both the conformance suite's, which reads every string of a declaration
# for them. Nothing resolves a fifth: completion substitutes `{N}` alone,
# so an unknown token would enter the manifest as the literal it is and the
# path a later step reads by that name would never exist. `{artifacts}` is
# unknown here on purpose — the executor resolves the manifest's own name,
# and a declaration that authors it is addressing what it cannot know.
PLACEHOLDERS = frozenset({"run", "N", "P", "machine-checks"})
PLACEHOLDER = re.compile(r"(?<!\$)\{([^{}]*)\}")
# The two a path resolves by, matched by that same rule. A raw substring
# substitution would resolve the `{N}` inside a `${N}` the scan above reads
# as text, so a step declaring `phase-${N}.md` would be manifested under a
# name it never wrote — and every later check making the same substitution
# would agree with itself about the corruption.
PHASE = re.compile(r"(?<!\$)\{N\}")
PHASE_SET = re.compile(r"(?<!\$)\{P\}")

# The schemas declare every structure below closed, and §9.5 makes unknown
# keys inside one an authoring error while tolerating unknown siblings of
# the structures themselves. A typo is what the rule is for: `conditionl`
# silently drops a member's conditionality, `onn` drops its routing, and
# `templat` drops the scaffold a later module would have used — each of
# them read, without the rule, as a deliberate omission.
STAGE_KEYS = frozenset({"sequence"})
MEMBER_KEYS = frozenset({"step", "gate", "conditional"})
STEP_KEYS = frozenset({"role", "inputs", "output", "on"})
OUTPUT_KEYS = frozenset({"artifact", "template"})
INPUT_KEYS = frozenset({"artifact", "required"})


class WorkflowError(Exception):
    """The workflow or a stage it composes is missing or malformed."""


@dataclass(frozen=True)
class InputDeclaration:
    artifact: str
    required: bool


@dataclass(frozen=True)
class StepDeclaration:
    """One step's contract (spec §9.1): who acts, what it reads and writes,
    and where each verdict routes. `edges` is empty where the step declares
    no `on` — it then proceeds in composition order, or a loop contract
    consumes its validation verdict."""

    id: str
    role: str
    inputs: tuple[InputDeclaration, ...]
    output_artifact: str
    output_template: str | None
    edges: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Member:
    """One sequence entry (spec §9.4): a step or a gate, in record order,
    `conditional` meaning populated `skipped` until a route reaches it."""

    kind: str  # "step" | "gate"
    id: str
    conditional: bool = False


@dataclass(frozen=True)
class Stage:
    name: str
    members: tuple[Member, ...]
    steps: dict[str, StepDeclaration]

    def member_ids(self) -> tuple[str, ...]:
        return tuple(member.id for member in self.members)


@dataclass(frozen=True)
class Workflow:
    name: str
    stages: tuple[Stage, ...]

    def members(self) -> tuple[tuple[Stage, Member], ...]:
        """Every member of every stage, in composition order — the record
        order §10's populated list follows."""
        return tuple(
            (stage, member) for stage in self.stages for member in stage.members
        )

    def member_kind(self, member_id: str) -> str | None:
        """`"step"`, `"gate"`, or None where the composition declares
        neither — what a record is, read from the declaration rather than
        guessed from the shape of its id."""
        for stage in self.stages:
            for member in stage.members:
                if member.id == member_id:
                    return member.kind
        return None

    def gate_scopes(self) -> dict[str, bool]:
        """Every composed gate, mapped to whether a phase repeats it.

        A stage repeats per phase when its steps write per-phase outputs —
        `{N}` in a declared output — and the gates it declares repeat with
        it. Read from the contracts rather than from the records being
        checked, or omitting a `phase` would decide that the field was
        never required and bypass the check it exists for.
        """
        scopes: dict[str, bool] = {}
        for stage in self.stages:
            phased = any(
                PHASE.search(declaration.output_artifact) is not None
                for declaration in stage.steps.values()
            )
            for member in stage.members:
                if member.kind == "gate":
                    scopes[member.id] = phased
        return scopes

    def entry_gate(self) -> str | None:
        """The gate the entry stage ends at — the decision §10 has accepting
        the class `run.risk` carries — or None where it ends at a step.

        Read from the composition rather than by name: which gate closes
        intake is a fact about the stage the workflow enters at, and an id
        matched by spelling would be a second vocabulary to keep true.
        """
        if not self.stages:
            return None
        last = self.stages[0].members[-1]
        return last.id if last.kind == "gate" else None

    def sequence(self) -> tuple[list[str], int]:
        """Every composed member in record order, and how many of them the
        entry stage declares — §10's list is that stage's alone until the
        intake gate accepts, and the whole of this afterwards."""
        order = [member.id for stage in self.stages for member in stage.members]
        return order, len(self.stages[0].members) if self.stages else 0

    def step(self, step_id: str) -> StepDeclaration | None:
        for stage in self.stages:
            if step_id in stage.steps:
                return stage.steps[step_id]
        return None


def load_workflow(framework: Path, name: str) -> Workflow:
    """Read `workflows/<name>.md` and every stage it composes."""
    if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
        raise WorkflowError(f"not a workflow name: {name!r}")
    path = framework / "workflows" / f"{name}.md"
    try:
        text = path.read_text(encoding="utf-8")
    # Undecodable is malformed, not a missing file: UnicodeDecodeError is a
    # ValueError rather than an OSError, so without this it would leave the
    # driver as a traceback instead of the exit code a defect is reported at.
    except (OSError, UnicodeError) as error:
        raise WorkflowError(f"cannot read workflow {name!r}: {error}") from error
    # The workflow file's own declarations are read for their version even
    # though this module consumes none of them: §9 holds every block to the
    # version it was authored against, and a trigger (§9.3) from a release
    # this driver does not implement, or a block that is not the subset's
    # YAML, is the same mismatched installation a stage file's would be.
    # Executing this file's composition while leaving its own declarations
    # unread is what would make that silent. What the trigger declares is a
    # later module's to act on.
    _blocks(text, f"workflows/{name}.md")
    # Composition order, the first entry naming a stage winning: a list may
    # name one twice, and the stage composes where it is first read.
    slugs: list[str] = []
    for match in STAGE_REFERENCE.finditer(_mask_fences(text)):
        if match.group(1) not in slugs:
            slugs.append(match.group(1))
    if not slugs:
        raise WorkflowError(f"workflow {name!r} composes no stages")
    stages = tuple(_load_stage(framework, slug) for slug in slugs)
    _check_member_ids(stages)
    _check_edges(stages)
    return Workflow(name=name, stages=stages)


def _check_edges(stages: tuple[Stage, ...]) -> None:
    """§9.1: an edge target names a step, a gate, or a stage — and which
    ids exist is a property of the composition, not of any one file, since
    a stage's steps routinely route into the stage that follows.

    Unchecked, a mistyped target is the most expensive kind of authoring
    error this module can pass on: the composition loads, the run directory
    and its bootstrap state are written, and the run fails at the first
    verdict that tries to route — with the state on disk already claiming a
    run that cannot finish. A stage target with no step to resolve to is the
    same failure a declaration later, so it is refused here too.
    """
    members = {member.id for stage in stages for member in stage.members}
    by_name = {stage.name: stage for stage in stages}
    for stage in stages:
        for step_id, declaration in stage.steps.items():
            at = f"{stage.name}: step {step_id!r}"
            for verdict, target in declaration.edges.items():
                if target not in members and target not in by_name:
                    raise WorkflowError(
                        f"{at}: {verdict} routes to {target!r}, which this "
                        f"workflow declares nothing for"
                    )
                targeted = by_name.get(target)
                if targeted is not None and not any(
                    member.kind == "step" for member in targeted.members
                ):
                    raise WorkflowError(
                        f"{at}: {verdict} routes to stage {target!r}, which "
                        f"declares no step to resolve to (spec §9.1)"
                    )


def _without_comment(text: str) -> str:
    """The text up to an unquoted comment, quoted spans already blanked.

    The block-form scan skips comment lines and the inline one read the
    whole of the metadata line, so `metadata: # {workflow: demo}` — a
    comment mentioning the word — read as a flow declaration and stopped
    composition over the example carrying it.
    """
    for index, character in enumerate(text):
        if character == "#" and (index == 0 or text[index - 1] in WHITESPACE):
            return text[:index]
    return text


def _blank_quoted(text: str) -> str:
    """The text with every quoted span replaced by spaces, offsets kept.

    Only structure decides whether a block declares, and a quoted scalar is
    not structure however it reads inside. Escapes are honoured so a quote
    within a double-quoted span does not end it early.

    A quote opens a scalar where a node starts and nowhere else, which is
    after `{`, `[`, `,`, or `:` with nothing but whitespace between — never
    after whitespace alone, which is inside a plain scalar as often as
    before one. Reading it as an opener there blanks the rest of the line
    for want of a partner, so `{note: rock 'n roll, workflow: …}` lost the
    key this scan exists to find and filed a broken declaration as prose.
    """
    out: list[str] = []
    index = 0
    at_node_start = True
    while index < len(text):
        character = text[index]
        if character not in "\"'" or not at_node_start:
            if character in "{[,:":
                at_node_start = True
            elif character not in WHITESPACE:
                at_node_start = False
            out.append(character)
            index += 1
            continue
        end = _closing_quote(text, index)
        if end is None:  # unterminated: nothing after it is structure either
            out.append(" " * (len(text) - index))
            return "".join(out)
        span = text[index : end + 1]
        # A quoted span followed by `:` is a key, and a key is structure: a
        # declaration may be written `metadata: {"workflow": …}`, and
        # blanking that span would lose the very thing this scan looks for
        # and file a malformed declaration as prose. It is written back
        # decoded and unquoted — the key a reader resolves rather than the
        # characters that spell it, since `"workflow"` names the same
        # key and the scan downstream compares text.
        after = text[end + 1 :]
        decoded = _decoded(span) if after.lstrip(" \t").startswith(":") else None
        # Written back only where the value reads as itself. Decoded text
        # rejoins structural text, and whitespace in it would then read as
        # the separator YAML trims: `{"workflow ": …}` names a key with a
        # space that no reader trims, and unquoted it would answer for the
        # key that has none. Anything else is blanked — the two names this
        # scan looks for are plain, so nothing it needs is lost.
        if decoded is not None and PLAIN_TEXT.fullmatch(decoded):
            out.append(decoded)
        else:
            out.append(" " * len(span))
        # The span was a node, so what follows it is not the start of one
        # until a structural character says so — the `:` of a quoted key
        # among them, which the loop reads next.
        at_node_start = False
        index = end + 1
    return "".join(out)


def _check_placeholders(value: str, at: str, what: str) -> None:
    """Every token the value carries is one the spec defines, or the value
    addresses a path nothing will resolve."""
    for token in PLACEHOLDER.findall(value):
        if token in PLACEHOLDERS:
            continue
        known = ", ".join("{" + name + "}" for name in sorted(PLACEHOLDERS))
        # Quoted, as every other value read from a file is here: the
        # token is decoded from the declaration and `resume` prints
        # this error, so a control sequence carried raw would rewrite
        # the line rather than be reported in it.
        unknown = "{" + token + "}"
        raise WorkflowError(
            f"{at}: {what} carries unknown placeholder {unknown!r} "
            f"(the spec defines {known})"
        )


def _closing_quote(text: str, start: int) -> int | None:
    """Where the span opened at `start` ends, or None if it never does.

    Each quoting style escapes its own quote its own way: a double-quoted
    span by a backslash, a single-quoted one by doubling it. Reading `''`
    as a close and a reopen ends the span half a scalar early and exposes
    the rest of it as structure — enough to report `metadata: 'it''s
    {workflow: …}'`, a scalar, as a declaration that failed to parse.
    """
    quote = text[start]
    index = start + 1
    while index < len(text):
        if text[index] == "\\" and quote == '"':
            index += 2
            continue
        if text[index] == quote:
            if quote == "'" and text[index + 1 : index + 2] == "'":
                index += 2
                continue
            return index
        index += 1
    return None


def _declares_workflow(body: str) -> bool:
    """Whether a block that failed to parse was reaching for a declaration.

    It has to be decided on text, the parse having failed, and the question
    is structural: does a first-column `metadata` have `workflow` as its
    *direct* child, which is the shape §9 gives a declaration and the one
    the conformance reader filters on after parsing. A descendant deeper
    down is somebody else's key — `metadata.annotations.workflow` is an
    ordinary example — so occurrence anywhere was never the test, and each
    round that treated it as one traded one misclassification for another.

    Both spellings are read the same way, by depth rather than by pattern:
    the block form's direct children are the lines at the indent the first
    one sets, and the flow form's are the keys at one brace deep. Quoted
    spans are blanked and a trailing comment removed first, since neither
    is structure.
    """
    # A stream may open with U+FEFF, which marks its encoding rather than
    # its content — `loads` drops it, and a scan that kept it would read
    # the mark as the first characters of whatever follows: neither the
    # first-column key nor the root brace is where it looks.
    body = body[1:] if body.startswith("\ufeff") else body
    # An alias is the node its anchor holds, and both are outside this
    # subset — which is why the block failed to parse and why the scan has
    # to read them anyway: `&m metadata` makes `*m:` the key `metadata`,
    # and `&w {workflow: …}` makes `metadata: *w` a declaration. What an
    # anchor holds is taken as the text it was written with, so an alias
    # reads as whatever that text reads as.
    anchors = _anchors(body)
    openings = list(METADATA_KEY.finditer(body)) + list(EXPLICIT_KEY.finditer(body))
    for opening in (
        m
        for m in openings
        if _key_name(m.group("key"), anchors, m.start()) == "metadata"
    ):
        rest = _without_comment(_blank_quoted(opening.group("rest")))
        rest = _resolved(rest, anchors, opening.start())
        if _flow_has_direct_key(rest, "workflow"):
            return True
        # `metadata: |` or `metadata: >` opens a block scalar, and what is
        # indented under it is that string's content — a conforming reader
        # sees `metadata` as text and no declaration at all. A tag or an
        # anchor may stand between the colon and the indicator, and what
        # they annotate is the same block scalar: reading only the first
        # token would scan `!!str |`'s text for keys and find the `workflow`
        # inside a string.
        if _without_properties(rest)[:1] in ("|", ">"):
            continue
        if _block_has_direct_key(body[opening.end() :], "workflow"):
            return True
    return _root_flow_declares(body)


def _root_flow_declares(body: str) -> bool:
    """Whether the document is a flow mapping whose own `metadata` key holds
    `workflow`.

    A `metadata` at the first column is one spelling of the direct child §9
    asks for, and `{metadata: {workflow: …}}` is the other: a reader that
    parses it resolves the same two keys, so a scan anchored to the column
    reads the whole document as prose and composes from whatever blocks are
    left. The document must *open* with the brace — a flow mapping nested
    in a value is somebody else's, and `example.labels.metadata.workflow`
    is as deep a descendant written in braces as it is written in lines.
    """
    # The root node takes a tag or an anchor as readily as any other, and
    # what they annotate is the same mapping: reading the brace without
    # them would file `!!map {metadata: {workflow: …}}` as prose and compose
    # around the declaration it carries.
    # `---` opens the document that follows it, on its own line or ahead of
    # the root on the same one, and what follows is the root this reads.
    flat = _without_properties(
        _without_marker(
            " ".join(_without_comment(_blank_quoted(line)) for line in body.split("\n"))
        )
    )
    if not flat.startswith("{"):
        return False
    end = _flow_key_end(flat, "metadata")
    if end is None:
        return False
    # `workflow` is looked for in what `metadata` holds and not in what
    # follows it: the suffix carries the mapping's later keys too, and
    # `{metadata: {}, example: {workflow: …}}` would answer for a sibling's
    # child — a declaration read out of an example that has none.
    return _flow_has_direct_key(_flow_value(flat[end:]), "workflow")


# What a decoded key may rejoin structural text as: characters that read as
# themselves, with nothing YAML would take for a separator or an indicator.
PLAIN_TEXT = re.compile(r"[A-Za-z0-9_.-]+")

ESCAPE = re.compile(r"\\(?:x([0-9A-Fa-f]{2})|u([0-9A-Fa-f]{4})|U([0-9A-Fa-f]{8})|(.))")
# YAML 1.2's double-quoted escapes, whole: what each names is a character
# the key carries, and what is not here names nothing.
YAML_ESCAPES = {
    "0": "\x00", "a": "\x07", "b": "\x08", "t": "\t", "\t": "\t",
    "n": "\n", "v": "\x0b", "f": "\x0c", "r": "\r", "e": "\x1b",
    " ": " ", '"': '"', "/": "/", "\\": "\\",
    "N": "\x85", "_": "\xa0", "L": "\u2028", "P": "\u2029",
}


ANCHOR_NAME = re.compile(r"&(?P<name>[^\s\[\]{},]+)(?P<value>[ \t]*.*)$")
ALIAS = re.compile(r"^\*(?P<name>[^\s\[\]{},]+)$")


def _anchors(body: str) -> list[tuple[int, str, str]]:
    """Every anchor the block defines, in the order they appear: where it
    was defined, what it is called, and the text it holds — the rest of its
    own line with any comment removed, and the lines indented under it
    where that is where its node continues.

    A list rather than a map, because a name may be defined more than once
    and an alias names the definition before it. Reading the last one in
    the file would answer for a node the alias never saw.
    """
    found: list[tuple[int, str, str]] = []
    offset = 0
    lines = body.split("\n")
    for number, line in enumerate(lines):
        match = _anchor_on(line)
        if match is not None:
            # A comment is not part of what the anchor holds: `&m metadata
            # # a label` anchors `metadata`, and carrying the label with it
            # names a key nothing declares.
            held = _without_comment(_blank_quoted(match.group("value"))).strip(WHITESPACE)
            indent = len(line) - len(line.lstrip(WHITESPACE))
            for following in lines[number + 1 :]:
                if not following.strip():
                    continue
                if len(following) - len(following.lstrip(WHITESPACE)) <= indent:
                    break
                held += "\n" + following
            found.append((offset + match.start("name"), match.group("name"), held))
        offset += len(line) + 1
    return found


def _anchor_on(line: str) -> re.Match | None:
    """The anchor this line defines, if it opens a node with one.

    `&` is an indicator where a node begins and an ordinary character
    everywhere else: `note: x &m metadata` is a plain scalar that contains
    an ampersand, and reading it as a definition would give an alias below
    it a value the document never anchored. A node begins after `:`, `-`,
    `{`, `[`, or `,` with only whitespace between, and at the start of the
    line's own content.
    """
    at_node_start = True
    for index, character in enumerate(line):
        if character == "&" and at_node_start:
            match = ANCHOR_NAME.match(line, index)
            if match is not None:
                return match
        if character in "{[,:-":
            at_node_start = True
        elif character not in WHITESPACE:
            at_node_start = False
    return None


def _anchored(anchors: list[tuple[int, str, str]], name: str, before: int) -> str | None:
    """What `name` held where the alias stands: the last definition ahead of
    it, which is the one YAML resolves an alias against."""
    held = None
    for offset, anchor, text in anchors:
        if anchor == name and offset < before:
            held = text
    return held


def _resolved(text: str, anchors: list[tuple[int, str, str]], offset: int) -> str:
    """An alias standing alone as a value, replaced by what it names."""
    alias = ALIAS.match(text.strip(WHITESPACE))
    if alias is None:
        return text
    held = _anchored(anchors, alias.group("name"), offset)
    return text if held is None else held


def _key_name(
    token: str,
    anchors: list[tuple[int, str, str]] | None = None,
    offset: int = 0,
) -> str:
    """What a captured key names: its resolved value, quoted, aliased, or
    plain."""
    if token[:1] in ("'", '"') and _closing_quote(token, 0) == len(token) - 1:
        return _decoded(token)
    token = token.rstrip(WHITESPACE)
    alias = ALIAS.match(token)
    if alias is not None and anchors is not None:
        held = _anchored(anchors, alias.group("name"), offset)
        if held is not None:
            return held.strip(WHITESPACE)
    return token


def _decoded(span: str) -> str:
    """A quoted scalar's value: the text a reader resolves, without the
    quotes that carried it.

    A key is the value of its node, not the characters spelling it, and
    `"work\\u0066low"` is `workflow` to everything that parses the document.
    Compared raw, the scan that decides whether a block was reaching for a
    declaration answers about the spelling instead — and files the one it
    could not read as prose. Only what YAML's own escapes decode to; an
    unknown escape stands for the character it precedes, which is what a
    reader that rejects the document would have reported rather than read.
    """
    body = span[1:-1]
    if span.startswith("'"):
        return body.replace("''", "'")

    def one(match: re.Match) -> str:
        hex_digits = match.group(1) or match.group(2) or match.group(3)
        if hex_digits is not None:
            code = int(hex_digits, 16)
            return chr(code) if code <= 0x10FFFF else match.group(0)
        # Unknown stays whole. `\e` is ESC and `\f` is a form feed, so
        # dropping a backslash the table does not name would spell the very
        # keys this scan looks for out of text that says something else —
        # and a reader rejecting the document would report it rather than
        # resolve it either way.
        return YAML_ESCAPES.get(match.group(4), match.group(0))

    return ESCAPE.sub(one, body)


def _without_marker(text: str) -> str:
    """The text past a document-start marker, which opens what follows it
    rather than being part of it. `---` alone is the marker; `----` is a
    scalar that begins with dashes."""
    value = text.lstrip(WHITESPACE)
    if value.startswith("---") and value[3:4] in tuple(WHITESPACE) + ("",):
        return value[3:].lstrip(WHITESPACE)
    return value


def _without_properties(rest: str) -> str:
    """The value with its node properties removed — a tag, an anchor, or
    both in either order, which YAML lets precede any node and which say
    nothing about what kind of node follows."""
    value = rest.lstrip(WHITESPACE)
    for _ in range(2):  # a tag and an anchor, in either order
        if value[:1] not in ("!", "&"):
            break
        cut = next(
            (index for index, character in enumerate(value) if character in WHITESPACE),
            len(value),
        )
        value = value[cut:].lstrip(WHITESPACE)
    return value


def _flow_value(rest: str) -> str:
    """What the key ending at the start of `rest` holds: the balanced span
    of a collection it opens, or the text up to the comma or brace that ends
    a scalar at this depth."""
    after = rest.lstrip(WHITESPACE)
    # A key may be quoted, and the quote is not the delimiter: `{'metadata':
    # …}` is the same key, with its closing quote still between the name and
    # the colon.
    if after[:1] in ("'", '"'):
        after = after[1:].lstrip(WHITESPACE)
    if not after.startswith(":"):
        return ""
    after = after[1:].lstrip(WHITESPACE)
    depth = 0
    for index, character in enumerate(after):
        if character in "{[":
            depth += 1
        elif character in "}]":
            if depth == 0:  # the mapping this key belongs to, closing
                return after[:index]
            depth -= 1
            if depth == 0:
                return after[: index + 1]
        elif character == "," and depth == 0:
            return after[:index]
    return after


def _flow_has_direct_key(rest: str, name: str) -> bool:
    """Whether a flow mapping opened on this line has `name` as a key."""
    return _flow_key_end(rest, name) is not None


def _flow_key_end(rest: str, name: str) -> int | None:
    """Where `name` ends, for a key of a flow mapping opened on this line,
    one brace deep — or None where that mapping declares no such key. The
    value follows, which is what makes a nested lookup the same lookup."""
    depth = 0
    for index, character in enumerate(rest):
        if character in "{[":
            depth += 1
        elif character in "}]":
            depth -= 1
        elif depth == 1 and rest.startswith(name, index):
            # A key may be quoted on either side; the quote is not the
            # delimiter, and `{'workflow': …}` is the same key as `{workflow: …}`.
            before = rest[:index].rstrip(WHITESPACE)
            if before.endswith(("'", '"')):
                before = before[:-1].rstrip(WHITESPACE)
            # A flow key carries properties as readily as a block one, and
            # they stand between the key and the `{` or `,` that opens its
            # place: `{!!str workflow: …}` is that key under a tag.
            for _ in range(2):
                cut = max(before.rfind(edge) for edge in (" ", "\t", "{", ","))
                if before[cut + 1 :][:1] not in ("!", "&"):
                    break
                before = before[: cut + 1].rstrip(WHITESPACE)
            # `{? workflow: …}` is the explicit key form in flow, and the
            # indicator stands where the properties do — between the key
            # and the punctuation that opens its place.
            if before.endswith("?"):
                before = before[:-1].rstrip(WHITESPACE)
            after = rest[index + len(name) :].lstrip(WHITESPACE)
            if after.startswith(("'", '"')):
                after = after[1:].lstrip(WHITESPACE)
            if before and before[-1] in "{," and after.startswith(":"):
                return index + len(name)
    return None


def _block_has_direct_key(after: str, name: str) -> bool:
    """A key of the block mapping that follows, at the indent its first
    child sets — a deeper one belongs to whatever opened above it."""
    child_indent: int | None = None
    for line in after.split("\n")[1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(WHITESPACE))
        if indent == 0:
            return False  # a first-column key ends what `metadata` contains
        if child_indent is None:
            child_indent = indent
        if indent != child_indent:
            continue  # deeper: a child of the key above, not of `metadata`
        key = line.strip()
        # The explicit key form names the key on its own line, with the
        # value on the `:` line beneath — `? workflow` is that key as much
        # as `workflow:` is, and the indicator stands where a tag or an
        # anchor does, before the name it belongs to.
        explicit = key.startswith("?") and key[1:2] in tuple(WHITESPACE) + ("",)
        if explicit:
            key = key[1:].lstrip(WHITESPACE)
        key = _without_properties(key)
        quoted = key[:1] in ("'", '"')
        if quoted:
            closing = _closing_quote(key, 0)
            if closing is None:
                continue
            # Decoded and compared as a value, not as text on the page: the
            # quotes end the key, so whitespace inside them is the key's
            # own and `"workflow "` names something `workflow` does not.
            # Only a plain key may carry the space YAML trims before a
            # colon.
            if _decoded(key[: closing + 1]) != name:
                continue
            rest = key[closing + 1 :].lstrip(WHITESPACE)
            if rest.startswith(":") or (explicit and not rest):
                return True
            continue
        if key.startswith(name):
            rest = key[len(name) :].lstrip(WHITESPACE)
            if rest.startswith(":") or (explicit and not rest):
                return True
    return False


def _mask_fences(text: str) -> str:
    """Blank every fenced region, keeping offsets and line numbers intact.

    What is shown inside a code block is a demonstration, not structure — a
    composition entry, a step heading, a declaration. Masking is how prose
    stays prose, and preserving every offset is what lets the scans that
    follow keep pointing into the raw text.
    """

    def blank(match: re.Match) -> str:
        return "".join(character if character == "\n" else " " for character in match.group(0))

    return FENCE.sub(blank, text)


def _declarations(text: str) -> list[tuple[int, str]]:
    """Every declaration fence with the offset it starts at: a `yaml` fence
    of either marker beginning at the first column, which is where §9 places
    a declaration. An indented fence is an example — a legal top-level
    indent and a list item's content indent are the same bytes, so masking
    tolerates CommonMark's three spaces and extraction does not.
    """
    found: list[tuple[int, str]] = []
    for match in FENCE.finditer(text):
        info = (match.group("bti") or match.group("tdi") or "").strip()
        if info != "yaml" or match.group("indent"):
            continue
        body = match.group("btb") if match.group("bt") else match.group("tdb")
        found.append((match.start(), body))
    return found


def _check_member_ids(stages: tuple[Stage, ...]) -> None:
    """§9.4: member ids are unique across stages and distinct from every
    stage id. Both are only checkable once composition is known, and both
    bite here: the workflow concatenates these sequences into one record
    list (§10), where an id two stages share is the duplicate record §10
    forbids and `Workflow.step` would answer for with whichever declaration
    came first — and §9.1's targets are untyped strings, so a member wearing
    a stage's id makes every edge naming it ambiguous."""
    stage_names = {stage.name for stage in stages}
    declared_by: dict[str, str] = {}
    for stage in stages:
        for member in stage.members:
            if member.id in stage_names:
                raise WorkflowError(
                    f"stage {stage.name!r} declares member {member.id!r}, "
                    f"which is a stage id (spec §9.4)"
                )
            owner = declared_by.get(member.id)
            if owner is not None:
                raise WorkflowError(
                    f"member {member.id!r} is declared by stages {owner!r} and "
                    f"{stage.name!r} (spec §9.4)"
                )
            declared_by[member.id] = stage.name


def _load_stage(framework: Path, slug: str) -> Stage:
    path = framework / "workflows" / "stages" / f"{slug}.md"
    rel = f"workflows/stages/{slug}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise WorkflowError(f"cannot read stage {rel}: {error}") from error
    members = _members(text, rel)
    steps = _steps(text, rel)
    declared = {member.id for member in members if member.kind == "step"}
    for member_id in sorted(declared - set(steps)):
        raise WorkflowError(f"{rel}: sequence step {member_id!r} has no step block")
    for step_id in sorted(set(steps) - declared):
        raise WorkflowError(f"{rel}: step {step_id!r} is not in the sequence")
    # §9.4 asks parity of both kinds, and a gate's declaration is its bullet:
    # a sequence naming a gate the stage does not declare blocks the run at a
    # decision nothing describes, and one the stage declares but the sequence
    # omits is a decision population can carry no record for.
    sequenced_gates = {member.id for member in members if member.kind == "gate"}
    declared_gates = _gates(text, rel)
    for gate_id in sorted(sequenced_gates - declared_gates):
        raise WorkflowError(
            f"{rel}: sequence names gate {gate_id!r}, which the stage does not declare"
        )
    for gate_id in sorted(declared_gates - sequenced_gates):
        raise WorkflowError(f"{rel}: gate {gate_id!r} is missing from the sequence")
    return Stage(name=slug, members=members, steps=steps)


def _blocks(text: str, rel: str) -> list[tuple[int, dict]]:
    """Every `metadata.workflow` value in the file's fenced blocks, with the
    text offset it starts at — position is what ties a step block to the
    heading above it."""
    found: list[tuple[int, dict]] = []
    for offset, body in _declarations(text):
        line = text.count("\n", 0, offset) + 1
        try:
            data = loads(body)
        except ProtocolYamlError as error:
            # A `yaml` fence at the first column is where a declaration
            # lives, and it is not the only thing that lives there: a stage
            # may show an example, and an example is free to use YAML this
            # subset does not carry — a flow sequence, a single-quoted
            # scalar. Refusing every such block would stop composition over
            # prose the conformance reader ignores, so the refusal is kept
            # for blocks that were reaching for `metadata` and failed.
            if not _declares_workflow(body):
                continue
            raise WorkflowError(f"{rel}:{line}: {error}") from error
        if not isinstance(data, dict):
            continue
        metadata = data.get("metadata")
        if not isinstance(metadata, dict) or "workflow" not in metadata:
            # A declaration fence carrying something else — the repository's
            # own examples do — is not this module's to read. Absence of the
            # key is what that means; a key that is present decides nothing
            # by its value, `null` included.
            continue
        workflow = metadata["workflow"]
        if not isinstance(workflow, dict):
            # Present and not a mapping is malformed, not absent: it has no
            # version to check and no structures to read, and skipping it
            # would compose a file one of whose declarations is broken.
            raise WorkflowError(
                f"{rel}:{line}: metadata.workflow is not a mapping: {workflow!r}"
            )
        _check_protocol(workflow, rel, line)
        found.append((offset, workflow))
    return found


def _closed(mapping: dict, allowed: frozenset[str], at: str, what: str) -> None:
    """§9.5: unknown keys inside a declared structure are authoring errors."""
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise WorkflowError(f"{at}: {what} has unknown keys: {', '.join(unknown)}")


def _check_protocol(block: dict, rel: str, line: int) -> None:
    """§9: every `metadata.workflow` block declares the protocol version it
    was authored against, and §11 forbids a client silently interpreting
    structures from a version it does not implement — the rule the package's
    `implements` states once for declarations and run state alike."""
    version = block.get("protocol")
    if not isinstance(version, str) or not PROTOCOL_VERSION.fullmatch(version):
        raise WorkflowError(
            f"{rel}:{line}: declaration without a protocol version: {version!r}"
        )
    if not implements(version):
        raise WorkflowError(
            f"{rel}:{line}: declaration is protocol {version}, and this driver "
            f"implements {PROTOCOL} (spec §11)"
        )


def _gates(text: str, rel: str) -> set[str]:
    """Every gate the stage declares, from its `## Gates` section alone.

    Read as a list first and returned as a set only once the list is known
    to hold no duplicate: a set built straight from the page erases the
    multiplicity parity exists to compare, and two `- **check**` bullets
    would answer one sequence entry — a member §9.4 declares twice and
    population records once. A second `## Gates` section is the same loss
    by another route, since it sits past the boundary the first section ends
    at: its gates reach neither parity nor gate scoping, so a sequence that
    omits them passes on the strength of what nothing read.

    Fenced code is masked first, so an example carrying the heading is not a
    second section and its bullets are not gates, and the section ends at the
    next level-2 heading — stages place `## Notes` after it. That boundary is
    the same `H2_HEADING` the step scan closes on: CommonMark ends the marker
    with a space, a tab, or the line, and a boundary that knew only the space
    would read `##\tNotes` as part of this section and its bold bullets as
    gates the sequence rightly omits.
    """
    masked = _mask_fences(text)
    openings = GATES_HEADING.findall(masked)
    if len(openings) > 1:
        raise WorkflowError(
            f"{rel}: {len(openings)} `## Gates` sections, need 1 — gates past "
            f"the first are invisible to the sequence checks (spec §9.4)"
        )
    opening = GATES_HEADING.search(masked)
    if opening is None:
        return set()
    tail = masked[opening.end() :]
    boundary = H2_HEADING.search(tail)
    section = tail if boundary is None else tail[: boundary.start()]
    # A gate whose id fails the form is a typo, and reading it as nothing
    # would leave the stage describing a human decision that parity never
    # asks the sequence for — a gate the run executes straight past.
    for shaped in GATE_SHAPED.finditer(section):
        if not GATE_BULLET.match(section, shaped.start()):
            bullet = "- **" + shaped.group("raw") + "**"
            raise WorkflowError(
                f"{rel}: gate bullet {bullet!r} does not match the "
                f"`- **<id>**` form — ids are lowercase kebab-case (spec §9.4)"
            )
    declared = [match.group("id") for match in GATE_BULLET.finditer(section)]
    for gate_id in declared:
        if declared.count(gate_id) > 1:
            raise WorkflowError(
                f"{rel}: gate {gate_id!r} is declared {declared.count(gate_id)} "
                f"times, and the sequence names each member once (spec §9.4)"
            )
    return set(declared)


def _members(text: str, rel: str) -> tuple[Member, ...]:
    sequences = []
    for _, workflow in _blocks(text, rel):
        if "stage" not in workflow:
            continue
        # Declared and not a mapping is malformed, and filtering it out
        # would let a file pass on the strength of another block that
        # happens to be valid — the declaration is broken either way.
        if not isinstance(workflow["stage"], dict):
            raise WorkflowError(
                f"{rel}: stage is not a mapping: {workflow['stage']!r}"
            )
        sequences.append(workflow["stage"])
    if len(sequences) != 1:
        raise WorkflowError(f"{rel}: {len(sequences)} stage sequence blocks, need 1")
    _closed(sequences[0], STAGE_KEYS, rel, "stage")
    entries = sequences[0].get("sequence")
    if not isinstance(entries, list) or not entries:
        raise WorkflowError(f"{rel}: stage sequence is empty")
    members: list[Member] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise WorkflowError(f"{rel}: sequence entry is not a mapping: {entry!r}")
        _closed(entry, MEMBER_KEYS, rel, "sequence entry")
        # Presence, not truthiness: `gate: null` is a named field with a
        # broken value, and reading it as an absent key would let an entry
        # naming both kinds pass as the one whose value happened to parse.
        kinds = [kind for kind in ("step", "gate") if kind in entry]
        if len(kinds) != 1:
            raise WorkflowError(f"{rel}: sequence entry is not one member: {entry!r}")
        kind = kinds[0]
        member_id = entry[kind]
        # The id shape is the schema's: a member wearing something else
        # becomes a record `load` refuses, one run too late to say why.
        if not isinstance(member_id, str) or not MEMBER_ID.fullmatch(member_id):
            raise WorkflowError(f"{rel}: {kind} id is not a member id: {member_id!r}")
        if any(member.id == member_id for member in members):
            raise WorkflowError(f"{rel}: sequence names {member_id!r} twice")
        # §9.4 admits `conditional: true` and absence, nothing else — the
        # schema declares the field `const: true`. Reading any other value as
        # unconditional would populate a revising member or a conditional
        # gate `pending` rather than `skipped`, and a resume would reach it
        # before the route that is supposed to fire it ever did.
        if "conditional" in entry and entry["conditional"] is not True:
            raise WorkflowError(
                f"{rel}: member {member_id!r} declares conditional "
                f"{entry['conditional']!r} — the form is `true` or absent"
            )
        members.append(
            Member(kind=kind, id=member_id, conditional="conditional" in entry)
        )
    return tuple(members)


def _steps(text: str, rel: str) -> dict[str, StepDeclaration]:
    # Headings come from the masked text: a `### fake (analyst)` inside a
    # fenced example, sitting between a real heading and its contract, would
    # otherwise be the nearest heading and bind that contract to `fake`. The
    # mask keeps every offset, so the association below still holds.
    masked = _mask_fences(text)
    headings = [
        (m.start(), m.group("id"), m.group("role")) for m in STEP_HEADING.finditer(masked)
    ]
    h3_offsets = [m.start() for m in H3_HEADING.finditer(masked)]
    h2_offsets = [m.start() for m in H2_HEADING.finditer(masked)]
    steps: dict[str, StepDeclaration] = {}
    contracts_under: dict[int, int] = {}
    for offset, workflow in _blocks(text, rel):
        if "step" not in workflow:
            continue
        declaration = workflow["step"]
        if not isinstance(declaration, dict):
            raise WorkflowError(f"{rel}: step is not a mapping: {declaration!r}")
        # A contract belongs to the heading nearest above it, and two things
        # close a step section before the contract is reached: an `## `
        # heading, which ends the steps the section held, and a `### ` that
        # is not the declared form, which owns the space beneath it without
        # naming anything. Binding to the last *valid* heading regardless
        # would execute a moved or orphaned contract as the step above it —
        # the association the conformance suite rejects by the same rules.
        nearest_h3 = max((start for start in h3_offsets if start < offset), default=None)
        nearest_h2 = max((start for start in h2_offsets if start < offset), default=None)
        prior = [(start, x, role) for start, x, role in headings if start < offset]
        nearest_valid = prior[-1][0] if prior else None
        if nearest_h3 is not None and nearest_h2 is not None and nearest_h2 > nearest_h3:
            raise WorkflowError(
                f"{rel}: step block below a `## ` heading that closed the step "
                f"section above it — it belongs to no step"
            )
        if nearest_h3 is None:
            raise WorkflowError(f"{rel}: step block above the first step heading")
        if nearest_valid is None or nearest_valid < nearest_h3:
            raise WorkflowError(
                f"{rel}: step block under a heading that does not match "
                f"`### <id> (<role>)` — it would attribute to the previous step"
            )
        _, step_id, heading_role = prior[-1]
        if step_id in steps:
            raise WorkflowError(f"{rel}: step {step_id!r} declares two step blocks")
        step = _step_declaration(declaration, step_id, rel)
        # The heading is what a human executing the prose reads and the
        # contract what this driver executes; a disagreement would run the
        # step as a role its own stage does not name (the conformance suite
        # holds the same rule).
        if step.role != heading_role:
            raise WorkflowError(
                f"{rel}: step {step_id!r} declares role {step.role!r} under a "
                f"heading that says {heading_role!r}"
            )
        steps[step_id] = step
        contracts_under[nearest_valid] = contracts_under.get(nearest_valid, 0) + 1
    # The reverse association, which tracking contracts alone cannot see: a
    # heading with no contract is a step the prose declares and the driver
    # has no role or handoff to execute, and two headings sharing an id are
    # a record population could not tell apart — the sequence naming it
    # would reach whichever contract happened to associate.
    for offset, step_id, _ in headings:
        if contracts_under.get(offset, 0) == 0:
            raise WorkflowError(
                f"{rel}: step {step_id!r} declares no contract block (spec §9.1)"
            )
    seen: set[str] = set()
    for _, step_id, _ in headings:
        if step_id in seen:
            raise WorkflowError(
                f"{rel}: step {step_id!r} is declared by more than one heading "
                f"(spec §10 carries one record per step)"
            )
        seen.add(step_id)
    return steps


def _step_declaration(declaration: dict, step_id: str, rel: str) -> StepDeclaration:
    at = f"{rel}: step {step_id!r}"
    _closed(declaration, STEP_KEYS, at, "step")
    role = declaration.get("role")
    if not isinstance(role, str) or not role:
        raise WorkflowError(f"{at}: missing role")
    # The six are the protocol's (§3.1) and the config routes exactly them,
    # so a seventh is a step nothing can ever execute — caught here, where
    # the file that declares it can be named, rather than after a run
    # directory and its state are already on disk.
    if role not in ROLES:
        raise WorkflowError(f"{at}: {role!r} is not a protocol role")
    output = declaration.get("output")
    if not isinstance(output, dict):
        raise WorkflowError(f"{at}: output is not a mapping: {output!r}")
    _closed(output, OUTPUT_KEYS, at, "output")
    artifact = output.get("artifact")
    if not isinstance(artifact, str) or not artifact:
        raise WorkflowError(f"{at}: missing output artifact")
    _check_placeholders(artifact, at, "output artifact")
    # §8.1 and §9.1: `{P}` resolves to one path per phase, and a step
    # produces one artifact — a phase set of outputs is a stage that
    # repeats, not a step that fans out, which is why the step schema
    # forbids the placeholder here. Completion resolves `{N}` alone, so an
    # output carrying `{P}` would enter the manifest as the literal it is.
    # Read by the pattern rather than as a substring: `${P}` is shell text
    # by the rule that makes `${N}` shell text, and a path is not a phase
    # set for looking like one.
    if PHASE_SET.search(artifact):
        raise WorkflowError(f"{at}: output artifact carries {{P}}: {artifact!r}")
    # A template is a path or it is absent — and `template: null` is neither:
    # declared and empty, it would read as a step that scaffolds nothing,
    # which is what the key's absence already says. Presence is what decides,
    # here as everywhere a declared field carries a default.
    template = output.get("template")
    if "template" in output and (not isinstance(template, str) or not template):
        raise WorkflowError(f"{at}: template is not a path: {template!r}")
    if isinstance(template, str):
        _check_placeholders(template, at, "template")
    inputs: list[InputDeclaration] = []
    # Absence is the only thing that means "no declared inputs". A present
    # `inputs` that is not a list — `false`, `null`, a mapping — is an
    # authoring error, and reading it as absence would drop the step's whole
    # handoff contract rather than report the one line that broke it.
    declared_inputs = declaration.get("inputs", [])
    if not isinstance(declared_inputs, list):
        raise WorkflowError(f"{at}: `inputs` is not a list: {declared_inputs!r}")
    for entry in declared_inputs:
        if not isinstance(entry, dict):
            raise WorkflowError(f"{at}: input is not a mapping: {entry!r}")
        _closed(entry, INPUT_KEYS, at, "input")
        input_artifact = entry.get("artifact")
        if not isinstance(input_artifact, str) or not input_artifact:
            raise WorkflowError(f"{at}: input without an artifact")
        _check_placeholders(input_artifact, at, "input artifact")
        # §9.1 has no default in prose; the schemas require the field only
        # when false matters, and every shipped block states it. Reading
        # absence as required errs toward blocking, never toward silently
        # running without a declared dependency — but only absence: a
        # present non-boolean would otherwise be coerced to required and
        # change what blocks the step without saying so.
        required = entry.get("required", True)
        if not isinstance(required, bool):
            raise WorkflowError(
                f"{at}: input {input_artifact!r} declares required {required!r}, "
                f"which is not a boolean"
            )
        inputs.append(InputDeclaration(artifact=input_artifact, required=required))
    edges: dict[str, str] = {}
    on = declaration.get("on")
    if "on" in declaration:
        # Declared and not a mapping is malformed, and `on: null` most of
        # all: read as absence it drops the step's routing and sends the run
        # on in composition order, which is what a step with no `on` at all
        # means — a broken declaration wearing a valid one's behaviour.
        if not isinstance(on, dict):
            raise WorkflowError(f"{at}: `on` is not a mapping: {on!r}")
        for verdict, target in on.items():
            if verdict not in VERDICTS or not isinstance(target, str) or not target:
                raise WorkflowError(f"{at}: bad edge {verdict!r}: {target!r}")
            edges[verdict] = target
        # §9.1: a declared `on` routes at least PASS and FAIL.
        if "PASS" not in edges or "FAIL" not in edges:
            raise WorkflowError(f"{at}: `on` must route PASS and FAIL")
    return StepDeclaration(
        id=step_id,
        role=role,
        inputs=tuple(inputs),
        output_artifact=artifact,
        output_template=template,
        edges=edges,
    )
