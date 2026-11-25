/* V2 "Two viewers, the filter carried": Open target view (a Targets or a Runs row) opens common/target.html as its own
   page in this tab, the runs the rail keeps for that target checked (keep=), and back= this workbench URL with its
   filter, so the target view's breadcrumb returns to exactly this filter. "Selected" = the target view's checkboxes. */
import { host } from './host-common.js';

const api = host({ variant: 'v2' });
api.onDrill('Open target view', (row) => {
  if (!row) return;
  const keep = api.keptLines(row.target_key);
  location.href = api.targetUrl(row, { keep: keep.join(','), back: location.href });
});
