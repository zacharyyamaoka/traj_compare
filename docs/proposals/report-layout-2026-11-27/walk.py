"""The walkthrough of each prototype: (label, caption, playwright actions). Shared by check.py (which runs them) and
build_gallery.py (which captions the stills they made)."""


# per variant: the walkthrough (label, caption, action) and its fold control
def steps(v):
    W = "pg.evaluate('Kit.pause(); Kit.setTime(Kit.WORST_T)')"
    return {
        "v1": [
            ("Answer first", "The page opens on one verdict line with its facts; each tab names its own answer under its title.", [W]),
            ("One chart, rest folded", "Which joint: the answer line and the elbow chart; the shoulder waits behind “1 more chart”.", ["pg.click('[data-tab=joints]')"]),
            ("Diagnostics: changed first", "15 of 27 channels moved; they come first, grouped in plain words, with when they changed and their peak. The 12 flat ones fold into one line.", ["pg.click('[data-tab=channels]')"]),
            ("Open one channel", "Click a row to open its charts in place; one open at a time keeps the list short.", ["pg.click('[data-channel=path_margin_rad] .chbtn')"]),
            ("3D settings in one popover", "The five sliders and three draw options live behind “View”; at rest the 3D keeps its panel.", ["pg.click('[data-viewsettings]')"]),
        ],
        "v2": [
            ("The dock is the overview", "Ruler, one track per run, and a lane per Diagnostics flag that fired; the playhead crosses all of them.", [W]),
            ("Click an event lane", "Collision · elbow: its charts open in Diagnostics, the lane stays highlighted.", ["pg.click('[data-lanehead=collision]')"]),
            ("Step event to event", "“event ›” jumps the playhead to the next flag onset; 3D and charts follow.", ["pg.click('[data-next-event]')"]),
            ("Add any channel as a lane", "“+ Add a lane” lists all 27 in plain-word groups; a dot marks the ones that changed.", ["pg.click('[data-addlane] summary')"]),
            ("Edge toolbar shows its values", "Each 3D setting is a button that shows its value; one click opens just that slider.", ["pg.keyboard.press('Escape')", "pg.click('[data-addlane] summary')", "pg.click('[data-tool=decay]')"]),
        ],
        "v3": [
            ("Three panes", "3D with its time lane under it, the tab as a dense chart grid, the inspector owning every setting.", [W]),
            ("Search the channel list", "Type “torque”: the inspector's list narrows; ticks choose what Diagnostics shows.", ["pg.click('[data-tab=channels]')", "pg.fill('[data-search]', 'torque')"]),
            ("Tick a channel", "Ticking “Drive power” adds its charts to the grid at once.", ["pg.click('[data-pick=drive_power_w]')"]),
            ("Solo a run", "S on Measured: every chart, the 3D and the lane show only that run.", ["pg.fill('[data-search]', '')", "pg.click('[data-solo=measured]')"]),
            ("Fold the inspector", "Inspector off: the charts take the width; the button brings it back, width remembered.", ["pg.click('[data-solo=measured]')", "pg.click('[data-insp-toggle]')"]),
        ],
        "v4": [
            ("Every chart starts as a strip", "Track: two strips with each run's value at the playhead; one ruler on top, the playhead runs down all of them.", [W]),
            ("27 channels on one screen", "Diagnostics as strips, changed first by family; the flat 12 fold into one line at the end.", ["pg.click('[data-tab=channels]')"]),
            ("Open a strip", "Click a name: that strip opens into a full chart on the same x as the ruler.", ["pg.click('[data-strip=ch-collision-1] .lab')"]),
            ("Raw signals as a table", "All four signals × both joints are eight strips, not eight charts.", ["pg.click('[data-tab=signals]')"]),
            ("Three looks + fine-tune", "The 3D picks a look (Clean / Ghost + comet / Error arrows); the sliders are in one drawer.", ["pg.click('[data-look=comet]')", "pg.click('[data-drawer] summary')"]),
        ],
        "v5": [
            ("Opens at the worst moment", "The moment card says when, what happened and each run's error; the tab leads with “At this moment”.", []),
            ("Next event", "“next event ›” (or ]) jumps to the next flag onset; the card names it.", ["pg.click('[data-next-event]')"]),
            ("Find a channel by typing", "/ or the box: type “torq”, the best match is first, changed ones marked.", ["pg.click('[data-tab=channels]')", "pg.click('[data-palette]')", "pg.keyboard.type('torq')"]),
            ("Pin it", "Enter pins the first hit; its charts join the readout and the grid.", ["pg.keyboard.press('Enter')"]),
            ("Near this moment", "Suggestions are the channels that move within ±0.25 s of the playhead; they change as you scrub.", ["pg.evaluate('Kit.setTime(0.84)')"]),
        ],
    }[v]


