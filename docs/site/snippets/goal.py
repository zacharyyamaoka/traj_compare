import numpy as np
from _fixture import JOINTS, plan
from robot_msgs.trajectory import JointTrajectory
t_ref = np.linspace(0.0, 2.7, 271)                     # the plan ends when its motion ends
target = JointTrajectory(t=t_ref, joint_names=JOINTS, positions=plan(t_ref))
t_run = np.linspace(0.0, 3.4, 341)                     # the run keeps recording while it settles
age = np.clip(t_run - 2.7, 0.0, None)
ring = 0.004 * np.exp(-age / 0.12) * np.sin(25.0 * age)
real = JointTrajectory(t=t_run, joint_names=JOINTS, positions=plan(t_run) + ring[:, None] * np.eye(6)[2])
# --- show
from robot_msgs.compare import goal

stats = goal(target, real, band=0.001)["positions/elbow_joint"]   # band in the joint's unit (rad)
print(f"settled {stats.settling_time:.2f} s after the end; overshoot {stats.overshoot * 1e3:.2f} mrad "
      f"({stats.overshoot_percent:.2f} % of the move); final error {stats.final_error * 1e3:+.3f} mrad")
# --- end
