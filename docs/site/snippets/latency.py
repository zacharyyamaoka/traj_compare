from _fixture import JOINTS, q_real, q_target, t, t_real  # noqa: F401
from robot_msgs.trajectory import JointTrajectory
target = JointTrajectory(t=t, joint_names=JOINTS, positions=q_target)
real = JointTrajectory(t=t_real, joint_names=JOINTS, positions=q_real)
# --- show
from robot_msgs.compare import compare, estimate_time_offset

estimate = estimate_time_offset(target, real, max_offset_s=0.25)
print(f"real runs {estimate.offset_s * 1e3:.1f} ms late; "
      f"position rms {estimate.rms_before:.5f} -> {estimate.rms_after:.5f} rad")

shifted = compare(target, real, time_offset_s=estimate.offset_s)   # explicit, never applied for you
print(f"elbow rms after the shift: {shifted.metrics['positions/elbow_joint'].rms * 1e3:.2f} mrad")
# --- end
