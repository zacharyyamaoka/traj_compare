from _fixture import JOINTS, fk, q_target, real_repeats, t  # noqa: F401
from robot_msgs.trajectory import PoseTrajectory
def tool(q):
    return PoseTrajectory.from_matrices(t, fk(q), child_frame_id="TCP")
# --- show
from robot_msgs.compare import aggregate

result = aggregate(tool(q_target), [tool(q) for q in real_repeats])   # N >= 2 runs, one reference
bias = result.accuracy.metrics["position"]          # reference − barycentre: what feedforward can fix
spread = result.metrics["position"]                 # per instant RP = l̄ + 3·S_l: what it can't
print(f"{result.runs} runs, coverage {result.coverage:.0%}")
print(f"accuracy  (bias)  rms {bias.rms * 1e3:.2f} mm   max {bias.max_abs * 1e3:.2f} mm")
print(f"repeatability RP  median {spread.median * 1e3:.2f} mm   max {spread.max * 1e3:.2f} mm")
# --- end
