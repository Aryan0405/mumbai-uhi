# AGENTS.md - standing rules for this repo (mumbai-uhi)

Chat instructions from the user override this file.

## Environment
- Run ALL Python as: conda run -n uhi_test python <script.py>. Python env: currently uhi_test (uhi is blocked by Application Control for pandas and scipy.sparse DLLs). Env decision is pending with the user. Do not create, delete or install into envs unless the user says so.
- Never call python.exe by path. Never use python -c. Never use heredocs. Write a script file, run it.
- No pip or conda installs, ever unless explicitly authorized by the user. If a package is missing, stop and report the exact install command.
- PowerShell only: no &&, no ||, no head, no grep, no dir /b, no 2>nul. Run commands one at a time.
- One command per shell call. No &&, no python -c, no heredocs.
- No background jobs. Do not list or report processes.

## Data safety
- Read only: data/composites*, data/processed/cells_500m.csv, data/processed/cells_500m.geojson, data/processed/cells_kmeans.csv.
- No synthetic data (null-model replicates are allowed only inside a null-model script and must never be saved as data).
- Do not edit src/cell_stats.py, src/build_status.py or STATUS.md unless the prompt names them.

## Scripts and logs
- Every script writes its own utf-8 log with Python (open(path, "w", encoding="utf-8")). Never use shell redirection.
- A script given an output path must never overwrite an input or a deliverable. Scripts print their own log; show it in the transcript.
- After each script, show its log in the transcript with Get-Content in chunks of at most 60 lines (Select-Object -Skip N -First 60), until the whole log is shown. The reviewer audits the transcript, not your summary.
- Never retype a number. The final message contains commentary and a checklist only. If a number is not in a log from this round, leave it out.
- Tests run through pytest only. A test file with no collected tests is a failure. Report the pass count from pytest output and compare it with the count I expected.
- Never report a requested count as the actual count. Log headers must print the actual number of replicates run.

## Gates and honesty
- If a gate or assertion fails, STOP and report. Never loosen a gate.
- Never write PASS. Use DONE, NOT DONE or NOT MEASURABLE with the reason.
- Do not attribute instructions to the user that they did not give.
- Do only what the prompt lists. Do not start the next phase.

## Git
- Commit only the files the prompt names. Message describes only that round. No push.
- After the commit run git status and git log --format="%h %s" -3. Report the commit hash only from that output.
- No em dashes or en dashes in any file or commit message.

## Project facts (do not reopen without the user)
- 500 m grid, 84 rows x 48 cols, EPSG:32643. in_bmc 2005 cells, core 1794 cells (core = in_bmc and not partial_bmc and not water_dominated).
- Primary density: pop_density_land on core cells. pop_density_full and pop_density_bmc stay for sensitivity analysis.
- K-Means features: z-scored lst_mean, ndvi_mean, ndbi_mean (ddof=0).
- Thermal band is natively 100 m. LST is a composite of clear days, March heavy. Never call it peak heat.