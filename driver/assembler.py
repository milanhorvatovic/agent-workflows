"""Context assembly: what one step is given to execute, and the scaffold its
output starts from (protocol/spec.md §8.3, §9.1).

Assembly is deterministic by construction — the same run, step, and framework
produce the same bytes. Nothing here decides what a step needs: the role comes
from the step's contract, the instructions from the skill that declares that
contract, the reference files from the ones the skill's own body names, and
the material from the artifacts the contract declares as inputs, resolved
against this run's manifest. An executor materializes only what is declared
(§9.1), so a skill whose prose reaches for an artifact its contract omits gets
prose and no artifact — which is the defect the completeness rule exists to
make visible, not one to paper over here.

The framework directory is a checkout of the protocol content: `workflows/`
and `workflows/stages/` as the composition module reads them, and `roles/` and
`skills/` as this one does. The `.agents/skills/` copies `setup/` installs into
a consuming project are for that project's harness to route to; the driver
executes from the framework it was configured with.

What this module does not do: it never invokes anything (the backend module
owns that), never satisfies an input from an earlier run (§8.4's cache is
judgment, and it lands with the artifact-manager work), and never writes
content into an artifact — `scaffold` puts the structure §8.3 asks for in
place, and every placeholder in it is the step's to fill.
"""

from __future__ import annotations

import contextlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from .protocol_yaml import ProtocolYamlError, loads
from .state import _NOFOLLOW, _NONBLOCK, RunState, StateError, is_link, run_directory
from .workflow import (
    PHASE,
    PHASE_SET,
    RUN_RELATIVE,
    StepDeclaration,
    Workflow,
    WorkflowError,
    check_protocol,
    family,
    mask_fences,
    step_declaration,
)

# Skill packages carry the framework's vendor prefix, and a step-bound skill
# is named for the step it declares (skills/README.md). The name is how the
# pair is found; what makes it the binding is the contract inside, which
# `_check_parity` holds to the stage's own — the same two-part rule the
# conformance suite applies to this repository's copy of the same files.
SKILL_PREFIX = "awf-"
SKILL_FILE = "SKILL.md"

# Frontmatter is the skill's declaration carrier (§9): the first line opens it
# and the next line holding `---` alone closes it. Anchored at the start of the
# file, because the same three characters further down are a thematic break in
# the body. The literal is the conformance suite's own, carried verbatim and
# pinned by a test: the two cannot share an implementation — that one parses
# through a YAML library this package may not import — so what they share is
# the rule, and a driver reading frontmatter the suite would not have accepted
# runs a skill CI never validated.
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)

# A reference the skill's body names, wherever it names it — inside backticks
# in every shipped body, but the backticks are typography rather than syntax
# and a body that dropped them would still be naming the file. Dotted parts
# are taken only where something follows the dot, so a sentence ending
# "`references/shipping.md`." names shipping.md rather than a file that does
# not exist. Slash-separated segments too: a package may nest its references,
# and a pattern stopping at the first one would take `references/guides` out
# of `references/guides/style.md` — not merely missing the file but refusing
# the skill for naming a directory. Nothing here can spell `..`, since every
# segment must open with a character the dot class excludes.
REFERENCE = re.compile(r"references/[A-Za-z0-9_-]+(?:[./][A-Za-z0-9_-]+)*")

RUN_PREFIX = "{run}/"


class AssemblyError(Exception):
    """The framework content a step needs is missing, malformed, or disagrees
    with the stage that composes it."""


class BlockedError(AssemblyError):
    """§9.1: a required input is missing, which blocks the step.

    Distinct from the rest because it says nothing is wrong with the
    installation — the run has simply not produced this artifact yet, which is
    a position to report rather than a defect to fix.
    """


@dataclass(frozen=True)
class Material:
    """One piece of the assembled context: where it came from and what it says.

    `source` is the path as a reader would cite it — `roles/planner.md`,
    `skills/awf-plan-create/references/bugfix.md`, `{run}/brief.md` — so every
    line of an assembled prompt traces back to a file.
    """

    kind: str  # "role" | "skill" | "reference" | "input" | "template"
    source: str
    text: str


@dataclass(frozen=True)
class Skill:
    """The skill package a step executes from."""

    step_id: str
    directory: Path
    body: str
    # The template the step's output is scaffolded from (§8.3) as declared, or
    # None where the step scaffolds nothing — which is what a step writing an
    # artifact an earlier step already created declares. Held to the segment
    # rule by the reader that produced this, so `scaffold` does not check the
    # spelling again: `load_skill` is the boundary.
    template: str | None
    # And the directory it resolves against, which is the directory of the file
    # that declared it — a stage's template is beside the stage, a skill's
    # beside the skill. The conformance suite states that rule and tests it, so
    # resolving both against the package would read a different file than the
    # one a stage's declaration was validated against.
    template_dir: Path | None
    # The reference files the body names, in first-mention order, minus the
    # template: that one reaches the step as the scaffold rather than as
    # reading material, and including it twice would put the same structure in
    # the prompt under two labels.
    references: tuple[str, ...]


@dataclass(frozen=True)
class Assembly:
    """Everything one invocation of one step is given."""

    step_id: str
    role: str
    # The step's declared output with `{N}` resolved — the artifact this
    # invocation is expected to leave behind.
    output: str
    output_path: Path
    materials: tuple[Material, ...]
    prompt: str


def load_skill(framework: Path, step_id: str, declaration: StepDeclaration) -> Skill:
    """Read the skill bound to `step_id` and hold it to the stage's contract."""
    package = f"{SKILL_PREFIX}{step_id}"
    rel = f"skills/{package}/{SKILL_FILE}"
    # The package directory first, then the entry point inside it. Containing
    # only the leaf would leave a linked package directory whole — everything
    # under it resolves within itself and passes — and containing only the
    # directory would leave the leaf, which is how a valid skill file outside
    # the framework reaches the prompt. Both, and the references and template
    # below inherit a directory already known to be inside.
    directory = _within(_content_root(framework, "skills"), package, f"skills/{package}")
    # Undecodable is malformed rather than absent, the distinction the
    # composition module draws for the same reason: UnicodeError is a
    # ValueError, and without it here a skill that is not UTF-8 leaves the
    # driver as a traceback instead of the defect it is. `_read` reports
    # both, and refuses a FIFO in the file's place rather than blocking on
    # it.
    text = _read(_within(directory, SKILL_FILE, rel), rel)
    match = FRONTMATTER.match(text)
    if match is None:
        raise AssemblyError(f"{rel}: no frontmatter, and §9 declares in it")
    try:
        data = loads(match.group(1) + "\n")
    except ProtocolYamlError as error:
        raise AssemblyError(f"{rel}: frontmatter: {error}") from error
    body = text[match.end() :]
    declared = _skill_step(data, step_id, rel)
    _check_parity(declared, declaration, rel, step_id)
    template, template_dir = _template(
        declared,
        declaration,
        rel,
        step_id,
        directory,
        _content_root(framework, "workflows", "stages"),
    )
    # Named in the body and present on disk, in that order: the body is what
    # says a reference belongs to this skill's method, and a path it names
    # that nothing backs is a broken package rather than an optional extra —
    # the step would be told to load a file the executor cannot hand it.
    # Fenced content is masked first, by the one fence model this repository
    # reads declarations through: a path inside an example is that example's,
    # and loading it would put a demonstration in the step's context — or,
    # where the example names a file that was never meant to exist, refuse a
    # skill for illustrating something.
    references: list[str] = []
    for name in REFERENCE.findall(mask_fences(body)):
        if name == template or name in references:
            continue
        if not _within(directory, name, _skill_source(step_id, name)).is_file():
            raise AssemblyError(f"{rel}: names {name}, which is not a file")
        references.append(name)
    return Skill(
        step_id=step_id,
        directory=directory,
        body=body,
        template=template,
        template_dir=template_dir,
        references=tuple(references),
    )


def _skill_step(data: object, step_id: str, rel: str) -> StepDeclaration:
    """The `metadata.workflow.step` a skill's frontmatter declares (§9.1)."""
    metadata = data.get("metadata") if isinstance(data, dict) else None
    workflow = metadata.get("workflow") if isinstance(metadata, dict) else None
    if not isinstance(workflow, dict):
        raise AssemblyError(
            f"{rel}: no `metadata.workflow` declaration — a step-bound skill "
            f"carries the contract it executes (spec §9.1)"
        )
    # §9 holds every block to the version it was authored against, and §11
    # forbids interpreting one from a version this driver does not implement
    # — a skill from a mismatched release ships prose written against
    # contracts this run does not execute. The composition module's check is
    # the one this calls rather than a second copy of the rule: two checks of
    # one clause are two things to keep in step, and the frontmatter carrier
    # is owed exactly what a stage's fenced block is owed. Line 1, the
    # frontmatter opening the file.
    try:
        check_protocol(workflow, rel, 1)
    except WorkflowError as error:
        raise AssemblyError(str(error)) from error
    declaration = workflow.get("step")
    if not isinstance(declaration, dict):
        raise AssemblyError(f"{rel}: `metadata.workflow.step` is not a mapping")
    # Parsed by the composition module's own reader, so the two carriers are
    # held to one definition of what a step declaration is; re-implementing it
    # here is how the copies would come to accept different things.
    try:
        return step_declaration(declaration, step_id, rel)
    except WorkflowError as error:
        raise AssemblyError(str(error)) from error


def _check_parity(
    declared: StepDeclaration, composed: StepDeclaration, rel: str, step_id: str
) -> None:
    """Two copies of one contract must agree (spec §9.1).

    The stage is what composes the run and the skill is what the step executes
    from, so a disagreement is not a preference to resolve: the run would
    execute prose written against inputs it was never given, or a role its own
    stage does not name. Conformance holds this repository's copies to it; the
    driver holds the framework it was pointed at, which no CI has seen.

    The template is compared separately (`_template`) — either carrier may
    declare it and the shipped stages declare none, so equality here would
    fault every real pairing.
    """
    for what, mine, theirs in (
        ("role", declared.role, composed.role),
        ("inputs", declared.inputs, composed.inputs),
        ("output artifact", declared.output_artifact, composed.output_artifact),
        ("edges", declared.edges, composed.edges),
    ):
        if mine != theirs:
            raise AssemblyError(
                f"{rel}: step {step_id!r} declares {what} {mine!r}, and the stage "
                f"composing it declares {theirs!r} — two copies of one contract "
                f"must agree (spec §9.1)"
            )


def _template(
    declared: StepDeclaration,
    composed: StepDeclaration,
    rel: str,
    step_id: str,
    skill_dir: Path,
    stage_dir: Path,
) -> tuple[str | None, Path | None]:
    """The template the output is scaffolded from, and the directory it
    resolves against, from whichever carrier declares it (§8.3).

    A declared template is relative to the file that declares it — the
    conformance suite states exactly that and tests a stage's template living
    beside the stage — so the carrier decides the base. Resolving both against
    the skill package would read a different file than the one a stage's
    declaration was checked against, which is a stage passing CI and a driver
    reading somewhere else.

    Which is also why a template may be declared by one carrier only. The rest
    of the contract is two copies of one thing and agreement is string
    equality; a template is not, because the same string under two bases names
    two files. Equal spellings would then read as agreement while the stage was
    validated against one file and this module read the other — so both
    declaring is refused whatever they say, and the parity rule the rest of the
    contract follows is the reason rather than the exception.
    """
    if declared.output_template is not None and composed.output_template is not None:
        raise AssemblyError(
            f"{rel}: step {step_id!r} and the stage composing it both declare a "
            f"template ({declared.output_template!r}, {composed.output_template!r}) "
            f"— a template resolves against the file declaring it, so one carrier "
            f"declares it or the two name different files (spec §8.3)"
        )
    if declared.output_template is not None:
        return declared.output_template, skill_dir
    if composed.output_template is not None:
        return composed.output_template, stage_dir
    return None, None


def resolve(artifact: str, declaration: StepDeclaration, state: RunState) -> tuple[str, ...]:
    """The `{run}`-relative paths one declared artifact names in this run (§8.1).

    `{N}` is the phase the step is executing and resolves to exactly one path.
    `{P}` is every phase *other than* this step's that the run has produced
    this artifact for, resolved against the manifest — which is what §8.1
    makes the answer, so a phase the manifest does not record is not one `{P}`
    names. Which phase is the step's own is settled by the step's own output
    and never by run state: `run.phase` still names the last phase while the
    stages after it run, so a step whose output carries no phase excludes
    nothing and reads them all.
    """
    phase = state.phase if state.phase is not None else 1
    if not PHASE_SET.search(artifact):
        return (PHASE.sub(str(phase), artifact),)
    # One declaration, two different phases, is not something `family` can
    # express — it makes every token in a path the same phase — so a path
    # mixing them would silently resolve as though they agreed.
    if PHASE.search(artifact):
        raise AssemblyError(
            f"step {declaration.id!r}: input {artifact!r} carries both {{N}} and "
            f"{{P}}, which name different phases (spec §8.1)"
        )
    excluded = str(phase) if PHASE.search(declaration.output_artifact) else None
    pattern = family(artifact)
    found: dict[str, str] = {}
    for entry in state.artifacts:
        match = pattern.fullmatch(entry)
        if match is not None and match.group("phase") != excluded:
            found[match.group("phase")] = entry
    # Ordered by length then digits rather than by `int`, which orders the
    # same way once `family` has excluded leading zeros and does not raise:
    # the manifest is a document this driver reads and did not necessarily
    # write, `int()` caps at 4300 digits, and a phase number past that would
    # leave the driver as a traceback instead of the set it was asked for —
    # the reason the package compares protocol versions without converting
    # them either.
    return tuple(found[digits] for digits in sorted(found, key=lambda d: (len(d), d)))


def assemble(
    framework: Path, run_dir: Path, state: RunState, workflow: Workflow, step_id: str
) -> Assembly:
    """Everything `step_id` is given to execute, in one deterministic order."""
    declaration = workflow.step(step_id)
    if declaration is None:
        raise AssemblyError(f"{step_id!r} is not a declared step (spec §9.1)")
    skill = load_skill(framework, step_id, declaration)
    materials = [
        Material(
            "role",
            f"roles/{declaration.role}.md",
            _role(framework, declaration.role),
        ),
        Material("skill", f"skills/{SKILL_PREFIX}{step_id}/{SKILL_FILE}", skill.body),
    ]
    for name in skill.references:
        source = _skill_source(step_id, name)
        materials.append(
            Material("reference", source, _read(_within(skill.directory, name, source), source))
        )
    materials.extend(_inputs(run_dir, state, declaration))
    if skill.template is not None:
        source = _template_source(skill)
        materials.append(
            Material(
                "template",
                source,
                _read(_within(skill.template_dir, skill.template, source), source),
            )
        )
    output = resolve(declaration.output_artifact, declaration, state)[0]
    return Assembly(
        step_id=step_id,
        role=declaration.role,
        output=output,
        output_path=_under(run_dir, output),
        materials=tuple(materials),
        prompt=_render(state, skill, declaration, output, materials),
    )


def _inputs(run_dir: Path, state: RunState, declaration: StepDeclaration) -> list[Material]:
    """Every declared input this run can satisfy, in declaration order.

    The manifest decides what the run holds (§8.2) — it records what steps
    produced and what the run imported (§8.6), which is exactly the set an
    input may resolve to. A required input the manifest does not name blocks
    the step (§9.1); an optional one is simply absent, and an optional one
    satisfied from an earlier run is §8.4's cache, which this module does not
    reach for: nothing here judges freshness.
    """
    manifest = set(state.artifacts)
    held: list[str] = []
    # Every requirement settled before anything is read, so a step blocked on
    # its third input reports that rather than whatever the first two happened
    # to fail at — and a run that cannot start this step does not spend a read
    # finding out.
    for declared in declaration.inputs:
        satisfied = [
            path for path in resolve(declared.artifact, declaration, state) if path in manifest
        ]
        if declared.required and not satisfied:
            raise BlockedError(
                f"step {declaration.id!r} requires {declared.artifact}, which this "
                f"run has not produced (spec §9.1)"
            )
        held.extend(satisfied)
    return [Material("input", path, _read_artifact(run_dir, path)) for path in held]


def _role(framework: Path, role: str) -> str:
    """A role definition's body, its frontmatter dropped.

    The frontmatter is the index's routing surface rather than instruction —
    reproducing the `description` a generator wrote from the body would spend
    the step's context restating what follows it.
    """
    source = f"roles/{role}.md"
    # Held under `roles/` the way a reference is held under its package: this
    # is prompt material like any other, and a framework carrying
    # `roles/analyst.md -> /outside/secret` would put that file in front of the
    # configured backend. The role name is one of the six the contract already
    # holds it to, so the name cannot escape; the file it points at can.
    text = _read(_within(_content_root(framework, "roles"), f"{role}.md", source), source)
    match = FRONTMATTER.match(text)
    return text[match.end() :] if match is not None else text


def _skill_source(step_id: str, name: str) -> str:
    return f"skills/{SKILL_PREFIX}{step_id}/{name}"


def _template_source(skill: Skill) -> str:
    """The template named by the carrier that declared it, so a refusal
    points at the file a reader would open."""
    if skill.template_dir == skill.directory:
        return _skill_source(skill.step_id, skill.template)
    return f"workflows/stages/{skill.template}"


def _read_bytes(path: Path, source: str) -> bytes:
    """Framework content, reported by the path a declaration names.

    An absolute path is what the process happens to have resolved; `source` is
    what the reader can look up — the same form every other refusal in this
    module carries.

    Opened non-blocking and checked for a regular file before it is read, as
    an artifact is: a FIFO anywhere the framework is read — a skill body, a
    role, a template — would block the open until something wrote the other
    end, and a command that never returns is worse than one reporting a
    defective framework.
    """
    try:
        descriptor = os.open(path, os.O_RDONLY | _NONBLOCK)
    except OSError as error:
        raise AssemblyError(f"cannot read {source}: {error}") from error
    try:
        stream = os.fdopen(descriptor, "rb")
    except OSError as error:
        os.close(descriptor)
        raise AssemblyError(f"cannot read {source}: {error}") from error
    try:
        with stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise AssemblyError(f"{source} is not a regular file")
            return stream.read()
    except OSError as error:
        raise AssemblyError(f"cannot read {source}: {error}") from error


def _read(path: Path, source: str) -> str:
    """The same, decoded with universal newlines — every framework file this
    module reads is UTF-8 text.

    The translation is not cosmetic: the conformance suite reads these files
    through `read_text`, which performs it, and this module's rules are the
    suite's rules. Without it a CRLF skill would pass CI and then be refused
    here for having no frontmatter, since the pattern the two share matches
    `\\n`. `_read_bytes` stays raw for the one caller that must not translate
    — a template copied byte for byte into a run.
    """
    try:
        text = _read_bytes(path, source).decode("utf-8")
    except UnicodeError as error:
        raise AssemblyError(f"cannot read {source}: {error}") from error
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _within(base: Path, relative: str, source: str) -> Path:
    """A declared package path, resolved and held inside the directory it was
    declared relative to.

    The spelling is checked where the declaration is read, and a spelling is
    only half of it: `references/x.md` may itself be a link to somewhere else
    entirely, and what this module does with the file is put it in a prompt or
    copy it into a run. Links are resolved and the result must still be under
    the base — the containment the conformance suite applies to the same
    declarations, applied again here because the framework the driver was
    pointed at is not the one CI checked.
    """
    # `RuntimeError` beside `OSError`: on the Python versions this driver
    # supports below 3.13, `resolve()` raises it for a symlink loop rather
    # than returning the path. It is not an `OSError`, so a loop anywhere in
    # the framework would escape the command surface as a traceback instead of
    # the framework-defect exit the README documents.
    try:
        anchor = base.resolve()
        resolved = (base / relative).resolve()
    except (OSError, RuntimeError) as error:
        raise AssemblyError(f"cannot read {source}: {error}") from error
    if not resolved.is_relative_to(anchor):
        raise AssemblyError(f"{source} resolves outside the directory declaring it")
    return resolved


def _content_root(framework: Path, *parts: str) -> Path:
    """A directory the framework holds its content in, verified level by level.

    Resolving a base before anchoring on it lets the anchor escape: a linked
    `skills/` resolves outside the framework, everything beneath it resolves
    within *that*, and the per-entry check below passes while external
    instructions enter the prompt. Each level is therefore held to the one
    above it, up to the configured framework itself — which may be a link, that
    being the operator's configuration rather than an escape from it.
    """
    root = framework
    for index, part in enumerate(parts):
        root = _within(root, part, "/".join(parts[: index + 1]))
    return root


def _components(artifact: str) -> list[str]:
    """A declared `{run}`-relative path as the components under the run.

    The prefix is the schema's — every declared artifact is anchored at
    `{run}/`, with no absolute form and no dot segments (§8.6, the pattern the
    composition module holds every declaration to) — so stripping it is the
    whole of the mapping and there is nothing left to normalize away.
    """
    # The whole pattern, not the prefix alone. This is a boundary rather than
    # an internal step: `scaffold` takes its artifact from a caller, and a
    # value like `{run}/../../out.md` splits into components `..` opens as
    # directories — creating the scaffold outside the run, which is the escape
    # the pattern exists to refuse. Backslash traversal is the same escape on
    # Windows, and the same pattern bars it.
    if not RUN_RELATIVE.match(artifact):
        raise AssemblyError(f"{artifact!r} is not a {{run}}-relative artifact path")
    return artifact[len(RUN_PREFIX) :].split("/")


def _under(run_dir: Path, artifact: str) -> Path:
    return run_dir.joinpath(*_components(artifact))


@contextlib.contextmanager
def _containing(run_dir: Path, relative: list[str], artifact: str, create: bool):
    """Hold the directory an artifact sits in, bound to the run's own.

    An artifact's path is schema-constrained and cannot escape by spelling —
    no absolute form, no `..` — but a link at any component redirects without
    changing the path, and this module both reads artifacts into a prompt and
    writes a scaffold into one. Where the platform can bind a file operation
    to a directory already open, each component is opened relative to the one
    above it and `O_NOFOLLOW` faults a link at the open itself, so nothing on
    the way down can be re-pointed after it was checked; where it cannot, the
    components are checked instead, which closes the case a link is already
    in place and leaves the window state.py documents for the same trade.

    Yields `(descriptor, path)`, exactly one of which is not None: the
    descriptor where the platform binds, the resolved directory otherwise.
    `create` makes the intermediate directories a nested output needs, made
    bound as well so a link cannot be what one of them lands in.
    """
    try:
        with run_directory(run_dir, None) as directory:
            if directory is None:
                path = run_dir
                for name in relative[:-1]:
                    path = path / name
                    if create:
                        path.mkdir(exist_ok=True)
                    if is_link(path):
                        raise AssemblyError(f"cannot use {artifact}: {path} is a link")
                if is_link(path / relative[-1]):
                    raise AssemblyError(
                        f"cannot use {artifact}: {path / relative[-1]} is a link"
                    )
                yield None, path
                return
            opened: list[int] = []
            try:
                for name in relative[:-1]:
                    parent = opened[-1] if opened else directory
                    if create:
                        try:
                            os.mkdir(name, dir_fd=parent)
                        except FileExistsError:
                            pass
                    opened.append(
                        os.open(
                            name,
                            os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW,
                            dir_fd=parent,
                        )
                    )
                yield (opened[-1] if opened else directory), None
            finally:
                for handle in opened:
                    os.close(handle)
    except OSError as error:
        raise AssemblyError(f"cannot use {artifact}: {error}") from error
    except StateError as error:
        raise AssemblyError(str(error)) from error


def _is_link_at(directory: int | None, path: Path | None, name: str) -> bool:
    """Whether `name` in the held directory is a link, read without following
    it — bound to the descriptor where there is one."""
    if directory is None:
        return is_link(path / name)
    try:
        return stat.S_ISLNK(os.lstat(name, dir_fd=directory).st_mode)
    except OSError:
        # Gone between the failed create and this look: nothing is there to
        # redirect, so it is not the case this guard exists for.
        return False


def _is_regular_at(directory: int | None, path: Path | None, name: str) -> bool:
    """Whether `name` in the held directory is a regular file, read without
    following a link — bound to the descriptor where there is one."""
    try:
        mode = (
            os.lstat(name, dir_fd=directory).st_mode
            if directory is not None
            else (path / name).lstat().st_mode
        )
    except OSError as error:
        # Nothing here is evidence of a regular file. A permission or I/O
        # failure says the name could not be read, and reporting that as an
        # artifact already in place hands the step a scaffold nobody wrote;
        # ENOENT says the name vanished between the create that found it taken
        # and this look, which is a race to report rather than a state to
        # claim. Both leave through the caller's own failure path.
        raise AssemblyError(f"cannot check {name}: {error}") from error
    return stat.S_ISREG(mode)


def _read_artifact(run_dir: Path, artifact: str) -> str:
    """Read one of this run's artifacts, bound to the run's own directory."""
    relative = _components(artifact)
    with _containing(run_dir, relative, artifact, create=False) as (directory, path):
        # `O_NOFOLLOW` says the name is not a link and nothing about what kind
        # of file it is. A FIFO in an artifact's place would block this open
        # until something wrote the other end — a command that hangs rather
        # than reporting, which is worse than any refusal — so the open is
        # non-blocking where the platform has it and the descriptor is checked
        # before it is read, exactly as the state file's is. One open serves
        # both branches, the bound one naming the leaf relative to a
        # descriptor and the other naming the path it resolved.
        try:
            descriptor = os.open(
                relative[-1] if directory is not None else os.fspath(path / relative[-1]),
                os.O_RDONLY | _NOFOLLOW | _NONBLOCK,
                dir_fd=directory,
            )
        except OSError as error:
            raise AssemblyError(f"cannot read {artifact}: {error}") from error
        try:
            stream = os.fdopen(descriptor, "r", encoding="utf-8")
        except OSError as error:
            # `fdopen` takes ownership only once it returns one, so a failure
            # here leaves the descriptor this function's to close.
            os.close(descriptor)
            raise AssemblyError(f"cannot read {artifact}: {error}") from error
        try:
            with stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise AssemblyError(f"{artifact} is not a regular file")
                return stream.read()
        except (OSError, UnicodeError) as error:
            raise AssemblyError(f"cannot read {artifact}: {error}") from error


def scaffold(skill: Skill, run_dir: Path, artifact: str) -> bool:
    """Create the step's output from its template (§8.3); return whether it wrote.

    Scaffolding creates and MUST NOT overwrite: a step revising, re-entering,
    or appending is given the artifact it already has, and re-scaffolding
    would discard the content it was given to work from — a gate's recorded
    direction (§7) among it. Copied byte for byte, because a scaffolded
    artifact MUST carry every placeholder its template defines until the step
    fills one, and read as bytes for the same reason: text mode translates
    line endings, so a CRLF template would reach the run as something other
    than the file the contract named.

    Named by its `{run}`-relative path rather than a resolved one, so the
    write is bound to the run directory the way every read is — a scaffold is
    the one thing here that creates a file, and following a link out of the
    run would put an artifact where nothing in the run can see it.
    """
    if skill.template is None:
        return False
    source = _template_source(skill)
    text = _read_bytes(_within(skill.template_dir, skill.template, source), source)
    relative = _components(artifact)
    with _containing(run_dir, relative, artifact, create=True) as (directory, path):
        # `O_EXCL` is the no-overwrite rule enforced by the open rather than by
        # a prior existence check: between a check and a write the file can
        # appear, and the content this would discard is exactly what the rule
        # protects. It refuses a link at the name too, so `O_NOFOLLOW` is the
        # belt to its braces rather than the guard.
        try:
            descriptor = os.open(
                relative[-1] if directory is not None else os.fspath(path / relative[-1]),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
                0o666,
                dir_fd=directory,
            )
        except FileExistsError:
            # `O_EXCL` answers EEXIST for a link as readily as for a file, and
            # the two mean opposite things: an artifact already there is the
            # step's to work from, while a link at the name redirects the run's
            # own artifact somewhere the run cannot see. The checked branch
            # refuses that before it opens anything, so the bound one asks
            # after — without it the same tree would report "already
            # scaffolded" on one platform and a defect on the other.
            if _is_link_at(directory, path, relative[-1]):
                raise AssemblyError(f"cannot scaffold {artifact}: the name is a link")
            # And EEXIST says a name is taken, not that what holds it is the
            # artifact this step works from. A directory, a FIFO, or a socket
            # reaches here too, is no link, and would be reported as a scaffold
            # already in place — the same refusal the read side makes, for the
            # same reason: only a regular file is an artifact.
            if not _is_regular_at(directory, path, relative[-1]):
                raise AssemblyError(f"{artifact} is not a regular file")
            return False
        except OSError as error:
            raise AssemblyError(f"cannot scaffold {artifact}: {error}") from error
        try:
            # `fdopen` takes ownership only once it returns a stream, so a
            # failure there leaves the descriptor this function's to close —
            # the leak repeated failures would otherwise accumulate one at a
            # time. Wrapping the open in the same block as the write keeps one
            # cleanup path for both, which is what the two failures need.
            try:
                stream = os.fdopen(descriptor, "wb")
            except BaseException:
                os.close(descriptor)
                raise
            with stream:
                stream.write(text)
        except OSError as error:
            # The name this call created is removed with it. Left behind, an
            # empty or partial scaffold is what the next `O_EXCL` reports as
            # EEXIST — and this function reads that as an artifact the step
            # already has, so a failed copy would be handed to the step as
            # content to work from. Only the file this call created: the
            # branch that found one already there returned above without
            # reaching here, which is what makes the removal safe.
            with contextlib.suppress(OSError):
                if directory is None:
                    os.unlink(path / relative[-1])
                else:
                    os.unlink(relative[-1], dir_fd=directory)
            raise AssemblyError(f"cannot scaffold {artifact}: {error}") from error
    return True


def _render(
    state: RunState,
    skill: Skill,
    declaration: StepDeclaration,
    output: str,
    materials: list[Material],
) -> str:
    """One step's context as the text a prompt-in/text-out backend sends.

    Every material appears under a heading naming its file, its content
    unaltered but for the blank lines around it, so a reader — human or agent
    — can trace any line back to what declared it. Reproducing rather than
    summarizing is deliberate for the artifacts most of all: an artifact is
    the protocol's handoff medium (§8.2), and a driver that condensed one
    would be deciding what the next step gets to see.
    """
    phase = state.phase if state.phase is not None else 1
    lines = [
        f"# agent-workflows step: {skill.step_id}",
        "",
        f"- Run: {state.run_id}",
        f"- Workflow: {state.workflow}",
        f"- Phase: {phase}",
        f"- Role: {declaration.role}",
        f"- Output: {output}",
        "",
        "Each section below holds the content of one file, named in its "
        "heading; a heading inside a section belongs to that file.",
    ]
    for material in materials:
        lines += [
            "",
            "---",
            "",
            f"## {material.kind}: {material.source}",
            "",
            material.text.strip("\n"),
        ]
    return "\n".join(lines) + "\n"
