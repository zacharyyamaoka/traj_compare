import numpy as np
from robot_msgs.trajectory import PoseTrajectory
t = np.linspace(0.0, 10.0, 1001)
route = np.column_stack([np.zeros_like(t), 0.35 * t, np.zeros_like(t)])
def poses(p):
    m = np.tile(np.eye(4), (len(t), 1, 1)); m[:, :3, 3] = p; return m  # noqa: E702
reference = PoseTrajectory.from_matrices(t, poses(route), child_frame_id="TCP")
offset_run = PoseTrajectory.from_matrices(t, poses(route + [0.004, 0, 0]), child_frame_id="TCP")
drifting_run = PoseTrajectory.from_matrices(t, poses(route + np.column_stack([0 * t, 1e-3 * t, 0 * t])), child_frame_id="TCP")
# --- show
from robot_msgs.compare import relative_error

for name, run in (("4 mm offset", offset_run), ("1 mm/s drift", drifting_run)):
    window = relative_error(reference, run, delta=0.5, unit="s")["relative/0.5s/position"]
    print(f"{name:13} drift per 0.5 s: rms {window.rms * 1e3:.3f} mm")   # an offset cancels, drift doesn't
# --- end
