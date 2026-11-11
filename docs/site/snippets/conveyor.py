import numpy as np
from _fixture import JOINTS, fk, q_real, q_sim, q_target, t, t_real, t_sim  # noqa: F401
from traj_compare import Comparison, Situation
from traj_compare.analysis import analyze_comparison
# --- show
BELT = np.array([0.0, 1.0, 0.0])          # conveyor direction in the world frame
UP = np.array([0.0, 0.0, 1.0])

page = Comparison(
    title="Belt track", joint_names=JOINTS, fk=fk, tcp_frame="TCP",
    target=Situation(name="target", title="Target", t=t, q=q_target),
    situations=[Situation(name="sim", title="Sim", t=t_sim, q=q_sim),
                Situation(name="real", title="Real", t=t_real, q=q_real)],
    vec_dirs=[("Conveyor", BELT)],        # Vec[Conveyor]_d: signed TCP speed along the belt
    error_axes=[("along belt", BELT), ("across belt", np.cross(BELT, UP)), ("up", UP)],
)
# --- end
payload = analyze_comparison(page)
print("error axes:", payload["error_axes"], "| vec:", payload["vec_labels"])
