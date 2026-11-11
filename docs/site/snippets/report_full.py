import tempfile
import numpy as np
from _fixture import BELT, JOINTS, fk, q_sim, q_target, real_repeats, t, t_sim  # noqa: F401
from robot_msgs.compare import JointTolerance, PoseTolerance, Tolerances
from traj_compare import Comparison, Situation, write_comparison_report
out_dir = tempfile.mkdtemp()
UP = np.array([0.0, 0.0, 1.0])
target = Situation(name="target", title="Target", t=t, q=q_target)
sim = Situation(name="sim", title="Sim", t=t_sim, q=q_sim)
reals = [Situation(name=f"real_{i + 1}", title=f"Real {i + 1}", t=t, q=q) for i, q in enumerate(real_repeats)]
# --- show
page = Comparison(
    title="Belt track", joint_names=JOINTS, fk=fk, tcp_frame="TCP",
    target=target, situations=[sim, *reals],
    vec_dirs=[("Conveyor", BELT)],
    error_axes=[("along belt", BELT), ("across belt", np.cross(BELT, UP)), ("up", UP)],
    tolerances=Tolerances(path=tuple(JointTolerance(name=j, position=0.02) for j in JOINTS)),
    tcp_tolerances=Tolerances(path=PoseTolerance(position=0.010), goal=PoseTolerance(position=0.002)),
    estimate_latency=True,                 # est. latency column per run
    goal_band=0.002, tcp_goal_band=0.002,  # settling column (rad / m)
    repeat_groups={"Real ×3": ["real_1", "real_2", "real_3"]},   # ISO 9283 card
)
report = write_comparison_report([page], out_dir, rerun=True)   # needs the rerun extra
# --- end
import json, re  # noqa: E401
html = report.read_text("utf-8")
data = json.loads(re.search(r'id="traj-compare-data">(.*?)</script>', html, re.S).group(1).replace("<\\/", "</"))
stats = data["comparisons"][0]["statistics"]
print("statistics columns:", " | ".join(stats["columns"]))
print("aggregates:", list(data["comparisons"][0]["aggregates"]))
print("rerun:", data["comparisons"][0]["rerun"]["rrd"], "sdk", data["comparisons"][0]["rerun"]["sdk"])
