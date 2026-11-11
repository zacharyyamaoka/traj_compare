from _fixture import JOINTS, q_real, q_sim, q_target, t, t_real, t_sim  # noqa: F401
# --- show
from robot_msgs.compare import compare
from robot_msgs.trajectory import JointTrajectory

target = JointTrajectory(t=t, joint_names=JOINTS, positions=q_target)
sim = JointTrajectory(t=t_sim, joint_names=JOINTS, positions=q_sim)
real = JointTrajectory(t=t_real, joint_names=JOINTS, positions=q_real)

pairs = {
    "target → sim": compare(target, sim),    # is the controller good enough, in sim?
    "target → real": compare(target, real),  # does the robot do what we commanded?
    "sim → real": compare(sim, real),        # is the sim a faithful twin? (no target involved)
}
for name, result in pairs.items():
    elbow = result.metrics["positions/elbow_joint"]
    print(f"{name:14} elbow rms {elbow.rms * 1e3:5.2f} mrad  max {elbow.max_abs * 1e3:5.2f} mrad  "
          f"coverage {result.coverage:4.0%}  dropped {result.dropped}")
# --- end
