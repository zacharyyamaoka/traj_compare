from _fixture import JOINTS, fk, q_real, q_target, t, t_real  # noqa: F401
import tempfile; out_dir = tempfile.mkdtemp()  # noqa: E702
# --- show
from robot_msgs.trajectory import JointTrajectory, PoseTrajectory
from traj_compare import Comparison, Situation, write_comparison_report

target = JointTrajectory(t=t, joint_names=JOINTS, positions=q_target)
real = JointTrajectory(t=t_real, joint_names=JOINTS, positions=q_real)
result = target.compare(real)                 # error = target − real, on real's own samples
print(f"elbow rms {result.metrics['positions/elbow_joint'].rms:.4f} rad, coverage {result.coverage:.0%}")

tcp = lambda run: PoseTrajectory.from_matrices(run.t, fk(run.positions), child_frame_id="TCP")
print(f"TCP lag {tcp(target).compare(tcp(real)).metrics['lag'].median * 1e3:.1f} mm")  # + = behind

page = Comparison(title="Belt track", joint_names=JOINTS, fk=fk,
                  target=Situation(name="target", t=t, q=q_target),
                  situations=[Situation(name="real", title="Real", t=t_real, q=q_real)])
write_comparison_report([page], out_dir, rerun=True)   # report.html + rerun/belt-track.rrd
# --- end
