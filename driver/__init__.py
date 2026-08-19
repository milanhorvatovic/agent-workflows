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
    major, minor = (int(part) for part in version.split("."))
    implemented_major, implemented_minor = (int(part) for part in PROTOCOL.split("."))
    return major == implemented_major and minor <= implemented_minor
