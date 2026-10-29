# data-ui difference(a, b) fixture

Verbatim copy of `gallery/robotics/fixtures/difference/` (the `*.json` files and `README.upstream.md`, the README) and
`gallery/robotics/fixture.py` from data-ui commit `6f4a72e` (integrate/packet, PEP 0010 P1a; contract text in
`gallery/robotics/CONTRACT.md` section 5). Seed 20261029; numpy 2.5.4, scipy 1.18.1 (see provenance.json).

One edit: `fixture.py`'s `FIXTURE` path points at this directory (`HERE`) instead of `HERE / "fixtures" / "difference"`.
Refresh: `git -C /home/bam/data-ui archive 6f4a72e gallery/robotics`, copy the same files, re-apply that one edit.
