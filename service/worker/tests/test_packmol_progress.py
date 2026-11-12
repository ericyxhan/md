"""Tests for packmol progress parsing.

Packmol rewrites its solution file after every GENCAN loop, so the presence
of the output file says nothing about how far the packing has progressed.  The
worker therefore parses packmol's log instead.
"""

from __future__ import annotations

from pathlib import Path

from prep_worker import (
    _packmol_block_budget,
    _packmol_log_state,
    _packmol_progress,
)

INP_TEMPLATE = """tolerance 2.0
filetype pdb
output {output}

add_amber_ter
amber_ter_preserve
nloop 100

structure PROT0.pdb
  number 1
  radius 1.5
end structure

structure POPC.pdb
  nloop 20
  number 323
  inside box -74.69 -74.69 -23.0 74.69 74.69 0.0
end structure

structure WAT.pdb
  nloop 20
  number 61178
  inside box -74.69 -74.69 -23.0 74.69 74.69 23.0
end structure

structure K+.pdb
  nloop 20
  number 160
end structure
"""

LOG_BLOCK_HEADER = """--------------------------------------------------------------------------------
  Packing molecules of type:            {block}
--------------------------------------------------------------------------------

"""

LOG_LOOP = """  Starting GENCAN loop:            {loop}
  Scaling radii by:    1.1000000000000001
--------------------------------------------------------------------------------
  Packing:|0                                                        100%|

  Function value from last GENCAN loop: f = .40462E+05
  Improvement from best function value:     6.26 %

  Current solution written to file: {output}
--------------------------------------------------------------------------------
"""


def _write_inputs(
    tmp_path: Path, *, loops_per_block: list[int]
) -> Path:
    """Write a packmol input and log with the given loop counts per block."""
    output = tmp_path / "embedded.pdb"
    (tmp_path / "packmol.inp").write_text(
        INP_TEMPLATE.format(output=output), encoding="utf-8"
    )

    chunks: list[str] = []
    for block, count in enumerate(loops_per_block, start=2):
        chunks.append(LOG_BLOCK_HEADER.format(block=block))
        for index in range(count):
            chunks.append(
                LOG_LOOP.format(output=output, loop=index)
            )
    (tmp_path / "packmol.log").write_text("".join(chunks), encoding="utf-8")
    return tmp_path


def test_block_budget_reads_nloop_and_molecule_counts(tmp_path: Path) -> None:
    output = tmp_path / "embedded.pdb"
    (tmp_path / "packmol.inp").write_text(
        INP_TEMPLATE.format(output=output), encoding="utf-8"
    )
    budget = _packmol_block_budget(tmp_path / "packmol.inp")
    assert budget == [
        ("PROT0.pdb", 100, 1),
        ("POPC.pdb", 20, 323),
        ("WAT.pdb", 20, 61178),
        ("K+.pdb", 20, 160),
    ]


def test_progress_starts_low_and_never_reports_complete(tmp_path: Path) -> None:
    work_dir = _write_inputs(tmp_path, loops_per_block=[1])
    percent, message = _packmol_progress(work_dir)
    assert 0.0 < percent < 99.0
    assert "packing" in message
    # The phase must never claim the run is finished while packmol is alive.
    assert "complete" not in message.lower()


def test_progress_moves_while_the_first_block_runs(tmp_path: Path) -> None:
    """A protein is one molecule out of ~80k, so molecule share alone would
    read as stuck.  The blend with block progress keeps the bar moving."""
    work_dir = _write_inputs(tmp_path, loops_per_block=[1])
    first, _ = _packmol_progress(work_dir)

    # Start a second block: block progress must advance.
    (work_dir / "packmol.log").write_text(
        (work_dir / "packmol.log").read_text(encoding="utf-8")
        + LOG_BLOCK_HEADER.format(block=3)
        + LOG_LOOP.format(output=tmp_path / "embedded.pdb", loop=0),
        encoding="utf-8",
    )
    second, _ = _packmol_progress(work_dir)

    assert second > first


def test_blocks_that_finish_in_one_loop_are_still_counted(tmp_path: Path) -> None:
    """A block may converge after a single GENCAN loop, so the loop counter
    never leaves zero.  The "Packing molecules of type" header is used
    instead, which keeps the block count correct."""
    work_dir = _write_inputs(tmp_path, loops_per_block=[1, 1, 1])
    _percent, message = _packmol_progress(work_dir)
    # Three blocks started, so the third is in progress.
    assert "block 3/4" in message
    assert "WAT.pdb" in message


def test_progress_advances_monotonically(tmp_path: Path) -> None:
    work_dir = _write_inputs(tmp_path, loops_per_block=[2])
    first, _ = _packmol_progress(work_dir)

    (work_dir / "packmol.log").write_text(
        (work_dir / "packmol.log").read_text(encoding="utf-8") * 3,
        encoding="utf-8",
    )
    second, _ = _packmol_progress(work_dir)

    assert second >= first


def test_progress_reports_which_block_is_being_packed(tmp_path: Path) -> None:
    work_dir = _write_inputs(tmp_path, loops_per_block=[2, 2, 2])
    _percent, message = _packmol_progress(work_dir)
    # Three blocks have started, so the third one is the one in progress.
    assert "block 3/4" in message
    assert "WAT.pdb" in message


def test_missing_log_is_not_an_error(tmp_path: Path) -> None:
    percent, message = _packmol_progress(tmp_path)
    assert percent == 0.0
    assert "starting" in message


def test_progress_is_parsed_incrementally_as_the_log_grows(
    tmp_path: Path,
) -> None:
    """The log is parsed a line at a time as packmol appends to it.

    Only the bytes appended since the last poll are read, so a long run does
    not re-read the whole log every couple of seconds.
    """

    output = tmp_path / "embedded.pdb"
    (tmp_path / "packmol.inp").write_text(
        INP_TEMPLATE.format(output=output), encoding="utf-8"
    )
    log_path = tmp_path / "packmol.log"
    log_path.write_text("", encoding="utf-8")

    def reference(text: str) -> tuple[int, int]:
        blocks = 0
        loop = 0
        for line in text.splitlines():
            if "Packing molecules of type:" in line:
                blocks += 1
                loop = 0
            elif "Starting GENCAN loop:" in line:
                loop = int(line.rsplit(":", 1)[1])
        return blocks, loop

    written = ""
    for line in LOG_BLOCK_HEADER.format(block=2).splitlines(keepends=True):
        written += line
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        assert _packmol_log_state(log_path) == reference(written)

    # A marker split across two writes must still be counted.
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("Packing molecules of type:")
    assert _packmol_log_state(log_path) == reference(written)

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("  2\n")
    written += "Packing molecules of type:  2\n"
    assert _packmol_log_state(log_path) == reference(written)
