import numpy as np
from robot_msgs.compare import compare
from robot_msgs.trajectory import PoseTrajectory
t = np.linspace(0.0, 1.0, 501)
def poses(x):
    m = np.tile(np.eye(4), (len(t), 1, 1)); m[:, 0, 3] = x; return m  # noqa: E702
reference = PoseTrajectory.from_matrices(t, poses(0.3 * t), child_frame_id="TCP")
slow_start = PoseTrajectory.from_matrices(t, poses(0.3 * t**2), child_frame_id="TCP")   # right path, wrong speed
# --- show
from robot_msgs.compare import frechet

print(f"Fréchet {frechet(reference, slow_start) * 1e3:.2f} mm "          # shape only: near 0
      f"vs same-instant max {compare(reference, slow_start).metrics['position'].max_abs * 1e3:.1f} mm")
# --- end
