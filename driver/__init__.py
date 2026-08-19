"""Python reference driver for the agent-workflows protocol (stdlib only).

The guaranteed execution floor — a human or a capable harness can substitute
at any step. Modules land one PR at a time; the command surface and the
config contract came first so every later module plugs into a stable frame.
"""

# The protocol version this driver implements: the version of the protocol
# content it ships beside (spec §11). New runs execute under it, and every
# declaration the driver reads is checked against it, since §11 forbids
# silently interpreting structures from a version this one does not
# implement.
PROTOCOL = "0.2"
