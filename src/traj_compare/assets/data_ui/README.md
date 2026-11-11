# data-ui trajectory contract schemas

Verbatim copies of `gallery/robotics/schemas/{runs,samples,poses,diff_poses,diff_samples,links,media,devices}.schema.json` and
`channels.json` from the data-ui checkout (`/home/bam/data-ui`, contract version 1, last changed at `6a72343f`, 2026-10-29).
`traj_compare.data_ui` embeds each table's field list from them, so a file declares the contract's units. `tests/test_data_ui.py`
fails when the checkout's copies differ; refresh by copying the same files again.
