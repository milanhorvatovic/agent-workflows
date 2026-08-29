"""Python reference driver for the agent-workflows protocol (stdlib only).

The guaranteed execution floor — a human or a capable harness can substitute
at any step. Modules land one PR at a time; the command surface and the
config contract came first so every later module plugs into a stable frame.
"""

import re

# The protocol version this driver implements: the version of the protocol
# content it ships beside (spec §11). New runs execute under it, and every
# declaration the driver reads is checked against it, since §11 forbids
# silently interpreting structures from a version this one does not
# implement.
PROTOCOL = "0.2"

# `<major>.<minor>`, the shape §11 gives the field wherever it appears — in
# a `metadata.workflow` block and in a run's own state alike.
PROTOCOL_VERSION = re.compile(r"^[0-9]+\.[0-9]+$")

# The request the run was created from (§8.7). It is not a step's output —
# nothing precedes the first step to produce it — so the executor lands it at
# creation and manifests it, which is what lets the entry step declare what it
# restates instead of reaching for something no surface carries (§9.1). The
# path is the protocol's rather than any one module's: creation writes it,
# the declaration reader refuses a step that claims it as an output, and the
# state reader requires it in every manifest.
REQUEST_FILE = "request.md"
REQUEST_ARTIFACT = f"{{run}}/{REQUEST_FILE}"

def names_request(artifact: str) -> bool:
    """Whether a declared path names the run's request, case folding aside.

    `{run}/REQUEST.md` is a different string and the same file wherever the
    filesystem folds case — macOS and Windows by default — so a rule that
    compared exactly would let a step declare the request as its output, or a
    lineage record name it as an import, and overwrite the one artifact §8.7
    says nothing in the run rewrites. §8.6 already settled that string equality
    is the wrong test where platforms fold: it decides self-import by directory
    identity for the same reason, and this is that reasoning applied to a name.

    `casefold` reserves more than any one filesystem aliases, and that is the
    choice rather than an accident. Three non-ASCII characters fold into this
    path — every codepoint was enumerated — and they do not divide evenly.
    `ſ` (U+017F) upper-cases to `S`, one code unit to one, which is what an
    upcase table expresses: `{run}/requeſt.md` genuinely is the request on
    NTFS, and an A–Z table would have missed it. `ﬅ` and `ﬆ` fold to `st`, one
    character to two, which such a table cannot do — so those two stay distinct
    on the filesystems this driver is known to run on, and refusing them
    reserves a name nothing aliases.

    Reserving them anyway, because the two errors are not the same size. A name
    wrongly refused is a declaration that fails loudly and gets renamed; a name
    wrongly allowed, on some filesystem that does fold wider than NTFS, silently
    overwrites the request mid-run — which is the failure §8.7 exists to
    prevent, and the one no reader would see. The approximation is static by
    necessity: these are declarations, checked without a filesystem to ask.
    """
    return artifact.casefold() == REQUEST_ARTIFACT


def implements(version: str) -> bool:
    """Whether this driver implements a well-formed declared version (§11).

    A different major is the case §11 names outright: structures from it
    must not be interpreted silently. A newer minor is that case too while
    the protocol is `0.x`, where any minor MAY carry breaking changes — the
    driver and the protocol content it reads ship as one release, so a
    newer minor is a mismatched installation rather than a document to
    guess at. An earlier minor is left readable: where its shapes differ,
    the load fails on the declaration it is missing, which says more than
    its version number would.
    """
    # A value that is not a version is not one this driver implements.
    # Read as components, `""`, `"."`, and `"0"` all normalize to the zero
    # the major already is, so each came back true — and this helper is
    # exported, answering for callers that do not prevalidate as the
    # driver's own do.
    if not PROTOCOL_VERSION.fullmatch(version):
        return False
    major, minor = _components(version)
    implemented_major, implemented_minor = _components(PROTOCOL)
    return major == implemented_major and minor <= implemented_minor


def _components(version: str) -> tuple[tuple[int, str], tuple[int, str]]:
    """A version as two comparable components, without converting either to
    an integer. The schema puts no ceiling on a component's digits, and
    Python 3.11 caps `int()` at 4300 of them — so a version this shape but
    absurdly long would raise where every other malformed one is reported,
    escaping the workflow and state errors that carry a defect to the exit
    code. Length then digits orders the same way the numbers would, once
    the leading zeros the schema permits are gone.
    """
    major, _, minor = version.partition(".")
    return tuple(  # type: ignore[return-value]
        (len(part.lstrip("0")), part.lstrip("0")) for part in (major, minor)
    )
