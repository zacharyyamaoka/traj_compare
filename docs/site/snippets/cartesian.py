from _fixture import JOINTS, fk, q_real, q_target, t, t_real  # noqa: F401
from robot_msgs.trajectory import JointTrajectory
target = JointTrajectory(t=t, joint_names=JOINTS, positions=q_target)
real = JointTrajectory(t=t_real, joint_names=JOINTS, positions=q_real)
# --- show
from robot_msgs.trajectory import PoseTrajectory

def tool(run, frame="TCP"):
    """One PoseTrajectory per point you care about: TCP, a five-bar's L2 tip, a coupler point."""
    return PoseTrajectory.from_matrices(run.t, fk(run.positions), child_frame_id=frame)

result = tool(target).compare(tool(real))
for name in ("position", "lag", "cross_track", "contour", "lag_time", "rotation"):
    stats = result.metrics[name]
    print(f"{name:12} rms {stats.rms:.5f}  median {stats.median:+.5f}  max_abs {stats.max_abs:.5f}")
# --- end
