from _fixture import JOINTS, q_real, q_target, t  # noqa: F401
import numpy as np
from robot_msgs.compare import JointTolerance, Tolerances, check
from robot_msgs.trajectory import JointTrajectory
reference = JointTrajectory(t=t, joint_names=JOINTS, positions=q_target).with_derivatives()
late = JointTrajectory(t=t, joint_names=JOINTS, positions=q_target + np.where(t[:, None] > 1.5, 0.01, 0.0) * np.eye(6)[2])
tolerances = Tolerances(path=(JointTolerance(name="elbow_joint", position=0.005),))
def read_joint_state(index):
    return late[index]
# --- show
from robot_msgs.compare import ToleranceMonitor

monitor = ToleranceMonitor(tolerances, joint_names=JOINTS, end_time=reference.t[-1])
for index, now in enumerate(reference.t):                  # one controller tick per sample
    outcome = monitor.step(now, reference[index], read_joint_state(index))
    if outcome is not None and not outcome.ok:
        print(f"abort at t={now:.2f} s: {outcome.error_string}")   # same verdict check() gives
        break
# --- end
offline = check(reference, late, tolerances)
assert offline.error_code == outcome.error_code and offline.violations[0].t == outcome.violations[0].t
print(f"offline check(): {offline.code_name} at t={offline.violations[0].t:.2f} s  (identical)")
