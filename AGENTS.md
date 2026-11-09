# AGENTS.md: standing rules for this repo (mumbai-uhi)

Chat instructions from the user override this file.

## Environment
- Run ALL Python as: conda run -n uhi_test python <script.py>
- uhi_test is the working env since 2026-11-09. The env uhi is blocked by Windows Application Control (pandas and scipy.sparse DLLs). Do not create, delete, modify or install into envs.
- No pip or conda installs unless the user explicitly authorizes that exact command. If a package is missing, STOP and report the exact install command.
- Never call python.exe by path. No python -c. No heredocs. Write a script file, run it.
- PowerShell only. One command per shell call. No &&, no ||, no shell redirection, no background jobs.

## Data safety
- Read only: data/composites*, data/processed/cells_500m.csv, data/processed/cells_500m.geojson, data/processed/cells_kmeans.csv.
- No synthetic data, except null-model replicates inside a null-model script, never saved as data.
- Do not edit src/cell_stats.py, src/build_status.py or STATUS.md unless the prompt names them.

## Scripts and logs
- Every script writes its own utf-8 log with Python (open(path, "w", encoding="utf-8")). The first log lines are the python, numpy, scipy, pandas and scikit-learn versions.
- A script given an output path must never overwrite an input or a deliverable. Scratch scripts must not share a name pattern with deliverables.
- Show each log in the transcript with Get-Content in chunks of at most 60 lines until the whole log is shown. If any tool result says "earlier lines", re-read the missing part before reporting.
- Never retype a number or hash. The final message contains commentary and a checklist only. If a number is not in a log from this round, leave it out.
- The final message is written fresh from this round's tool output. Never reuse a report from an earlier round.
- Tests run through pytest only. A test file with no collected tests is a failure. Compare the pytest pass count with the count the prompt expects.
- Log headers print the actual number of replicates run, never the requested number.

## Gates and honesty
- If a gate or assertion fails, STOP and report. Never loosen a gate.
- A tolerance or expected value may only be changed by a user message that names the new value.
- Never write PASS. Use DONE, NOT DONE or NOT MEASURABLE with the reason.
- Do not attribute instructions to the user that they did not give.
- Do only what the prompt lists. Do not start the next phase.

## Git
- Commit only the files the prompt names. The message describes only that round. No push.
- After the commit run git status --short and git log --format="%h %s" -3. Report the commit hash only from that output.
- No em dashes or en dashes in any file or commit message.

## Project facts (do not reopen without the user)
- 500 m grid, 84 rows x 48 cols, EPSG:32643. in_bmc 2005 cells, core 1794 cells (core = in_bmc and not partial_bmc and not water_dominated).
- Primary density: pop_density_land on core cells. pop_density_full and pop_density_bmc stay for sensitivity analysis.
- K-Means features: z-scored lst_mean, ndvi_mean, ndbi_mean (ddof=0).
- Thermal band is natively 100 m. LST is a composite of clear days, March heavy. Never call it peak heat.
