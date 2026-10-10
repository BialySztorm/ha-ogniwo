"""Tests for the Ogniwo integration.

The fixtures are a recorded Pello D controller, inherited from ha-pello. It
answers the same register API and reports the same registers as the eCoal
controllers this integration targets, so it is what the generic rules are
tested against until a dump of an Ogniwo boiler replaces it. That is also why
the asserted hardware type reads `pello_D`.
"""

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    """Read a recorded controller response, keeping its original line endings."""
    return (FIXTURES / name).read_text(encoding="utf-8", newline="")


def write_response(tid: str, status: str = "ok") -> str:
    """Build the controller's answer to a register change."""
    reg = f'<reg vid="0" tid="{tid}" status="{status}"/>'
    return f'<cmd status="ok"><device id="0">{reg}</device></cmd>'
