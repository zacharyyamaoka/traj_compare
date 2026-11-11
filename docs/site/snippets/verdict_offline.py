from _fixture import JOINTS, q_real, q_sim, q_target, t, t_real, t_sim  # noqa: F401
from robot_msgs.trajectory import JointTrajectory
target = JointTrajectory(t=t, joint_names=JOINTS, positions=q_target).with_derivatives()
sim = JointTrajectory(t=t_sim, joint_names=JOINTS, positions=q_sim).with_derivatives()
real = JointTrajectory(t=t_real, joint_names=JOINTS, positions=q_real).with_derivatives()
# --- show
from robot_msgs.compare import JointTolerance, Tolerances, check

tolerances = Tolerances(
    path=tuple(JointTolerance(name=joint, position=0.02) for joint in JOINTS),    # rad, every sample
    goal=tuple(JointTolerance(name=joint, position=0.002) for joint in JOINTS),   # rad, after the end
    goal_time_tolerance=0.5,           # s after the reference ends to meet the goal
    stopped_velocity_tolerance=0.01,   # rad/s, every joint, in the goal phase
)
for name, run in (("sim", sim), ("real", real)):
    outcome = check(target, run, tolerances)
    print(f"{name}: {outcome.code_name} ({outcome.error_code})")
    if outcome.violations:
        first = outcome.violations[0]           # the earliest breach: phase, metric, t, error, limit
        print(f"   {first.phase} {first.metric}: error {first.error:+.4f} rad, limit {first.limit} at t={first.t:.2f} s")
    else:
        path = {k: v for k, v in outcome.margins.items() if k.startswith("path/")}
        metric = min(path, key=path.get)        # margin = limit − worst |error|; negative = violated
        print(f"   goal met {outcome.goal_time:.2f} s after the end; tightest {metric}: {path[metric]:.4f} rad")
# --- end
