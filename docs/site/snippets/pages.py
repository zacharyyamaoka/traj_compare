import tempfile
from _fixture import BELT, JOINTS, fk, q_real, q_sim, q_target, t, t_real, t_sim  # noqa: F401
out_dir = tempfile.mkdtemp()
# --- show
from traj_compare import Comparison, Situation, write_comparison_report

target = Situation(name="target", title="Target", t=t, q=q_target)
sim = Situation(name="sim", title="Sim", t=t_sim, q=q_sim)
real = Situation(name="real", title="Real", t=t_real, q=q_real)

def page(title, reference, *runs):
    # traj_compare's Comparison is the page model: `target` is simply its reference
    return Comparison(title=title, joint_names=JOINTS, fk=fk, vec_dirs=[("Conveyor", BELT)],
                      target=reference, situations=list(runs), group="belt", group_title="Belt track")

pages = [page("Target → Sim", target, sim),
         page("Target → Real", target, real),
         page("Sim → Real", sim, real)]          # errors read "Sim − real" on this page
report = write_comparison_report(pages, out_dir)
# --- end
print(report.name, "with pages:", ", ".join(p.title for p in pages))
