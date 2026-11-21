# MARCUS gold-set score

Recall in %, macro (mean over papers) with paper-level bootstrap 95% CI. Full = full InChIKey; skeleton = InChIKey first block (stereo-agnostic).

> Precision is not reported. COCONUT lists only the natural products it links to a DOI; the papers also draw intermediates, known reference compounds, reagents and partial structures, so a prediction that matches nothing in COCONUT is not necessarily wrong.

- warning: 5 duplicate (system, paper) run line(s); the latest started_at was kept

| split | system | papers run/total | recall full | recall skeleton | micro recall full | recall full grouped | mean best Tanimoto | invalid SMILES % | papers w/ page errors | segments/paper median (max) |
|---|---|---|---|---|---|---|---|---|---|---|
| dev | v1-976396a5/decimer | 1/50 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 [0.0, 0.0] | 0.536 [0.536, 0.536] | 37.5 | 1 | 8 (8) |
| test | v1-976396a5/decimer | 1/50 | 45.5 [45.5, 45.5] | 80.0 [80.0, 80.0] | 45.5 | 50.0 [50.0, 50.0] | 0.869 [0.869, 0.869] | 21.4 | 0 | 14 (14) |
| dev | v1-976396a5/decimer-hand | 1/50 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 [0.0, 0.0] | 0.653 [0.653, 0.653] | 37.5 | 0 | 16 (16) |
| test | v1-976396a5/decimer-hand | 1/50 | 54.5 [54.5, 54.5] | 90.0 [90.0, 90.0] | 54.5 | 60.0 [60.0, 60.0] | 0.911 [0.911, 0.911] | 14.3 | 0 | 14 (14) |
| dev | v1-976396a5/molnextr | 1/50 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 [0.0, 0.0] | 0.661 [0.661, 0.661] | 43.8 | 1 | 16 (16) |
| test | v1-976396a5/molnextr | 1/50 | 54.5 [54.5, 54.5] | 90.0 [90.0, 90.0] | 54.5 | 60.0 [60.0, 60.0] | 0.911 [0.911, 0.911] | 0.0 | 0 | 14 (14) |
| dev | v1-976396a5/molscribe | 1/50 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 [0.0, 0.0] | 0.068 [0.068, 0.068] | 0.0 | 1 | 1 (1) |
| test | v1-976396a5/molscribe | 1/50 | 63.6 [63.6, 63.6] | 90.0 [90.0, 90.0] | 63.6 | 70.0 [70.0, 70.0] | 0.911 [0.911, 0.911] | 7.1 | 1 | 14 (14) |
| dev | v2-r1b-f40a0d0+recycle/decimer | 1/50 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 [0.0, 0.0] | 0.653 [0.653, 0.653] | 31.2 | 0 | 16 (16) |
| test | v2-r1b-f40a0d0+recycle/decimer | 1/50 | 45.5 [45.5, 45.5] | 80.0 [80.0, 80.0] | 45.5 | 50.0 [50.0, 50.0] | 0.869 [0.869, 0.869] | 21.4 | 0 | 14 (14) |
| dev | v2-r1b-f40a0d0+recycle/decimer-hand | 1/50 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 [0.0, 0.0] | 0.653 [0.653, 0.653] | 37.5 | 0 | 16 (16) |
| test | v2-r1b-f40a0d0+recycle/decimer-hand | 1/50 | 54.5 [54.5, 54.5] | 90.0 [90.0, 90.0] | 54.5 | 60.0 [60.0, 60.0] | 0.911 [0.911, 0.911] | 14.3 | 0 | 14 (14) |
| dev | v2-r1b-f40a0d0+recycle/molnextr | 1/50 | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 0.0 | 0.0 [0.0, 0.0] | 0.661 [0.661, 0.661] | 43.8 | 0 | 16 (16) |
| test | v2-r1b-f40a0d0+recycle/molnextr | 1/50 | 54.5 [54.5, 54.5] | 90.0 [90.0, 90.0] | 54.5 | 60.0 [60.0, 60.0] | 0.911 [0.911, 0.911] | 0.0 | 0 | 14 (14) |
| dev | v2-r1b-f40a0d0+recycle/molscribe | 1/50 | 0.0 [0.0, 0.0] | 16.7 [16.7, 16.7] | 0.0 | 0.0 [0.0, 0.0] | 0.848 [0.848, 0.848] | 18.8 | 0 | 16 (16) |
| test | v2-r1b-f40a0d0+recycle/molscribe | 1/50 | 63.6 [63.6, 63.6] | 90.0 [90.0, 90.0] | 63.6 | 70.0 [70.0, 70.0] | 0.911 [0.911, 0.911] | 7.1 | 0 | 14 (14) |

## Paired comparison (same papers; diff = B - A, recall in points)

| split | A vs B | papers | diff recall full [CI] | B better / A better / tie | sign p | diff recall skeleton [CI] |
|---|---|---|---|---|---|---|
| dev | v1-976396a5/decimer vs v1-976396a5/decimer-hand | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/decimer vs v1-976396a5/molnextr | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/decimer vs v1-976396a5/molscribe | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/decimer vs v2-r1b-f40a0d0+recycle/decimer | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/decimer vs v2-r1b-f40a0d0+recycle/decimer-hand | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/decimer vs v2-r1b-f40a0d0+recycle/molnextr | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/decimer vs v2-r1b-f40a0d0+recycle/molscribe | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 16.7 [16.7, 16.7] |
| dev | v1-976396a5/decimer-hand vs v1-976396a5/molnextr | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/decimer-hand vs v1-976396a5/molscribe | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/decimer-hand vs v2-r1b-f40a0d0+recycle/decimer | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/decimer-hand vs v2-r1b-f40a0d0+recycle/decimer-hand | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/decimer-hand vs v2-r1b-f40a0d0+recycle/molnextr | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/decimer-hand vs v2-r1b-f40a0d0+recycle/molscribe | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 16.7 [16.7, 16.7] |
| dev | v1-976396a5/molnextr vs v1-976396a5/molscribe | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/molnextr vs v2-r1b-f40a0d0+recycle/decimer | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/molnextr vs v2-r1b-f40a0d0+recycle/decimer-hand | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/molnextr vs v2-r1b-f40a0d0+recycle/molnextr | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/molnextr vs v2-r1b-f40a0d0+recycle/molscribe | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 16.7 [16.7, 16.7] |
| dev | v1-976396a5/molscribe vs v2-r1b-f40a0d0+recycle/decimer | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/molscribe vs v2-r1b-f40a0d0+recycle/decimer-hand | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/molscribe vs v2-r1b-f40a0d0+recycle/molnextr | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v1-976396a5/molscribe vs v2-r1b-f40a0d0+recycle/molscribe | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 16.7 [16.7, 16.7] |
| dev | v2-r1b-f40a0d0+recycle/decimer vs v2-r1b-f40a0d0+recycle/decimer-hand | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v2-r1b-f40a0d0+recycle/decimer vs v2-r1b-f40a0d0+recycle/molnextr | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v2-r1b-f40a0d0+recycle/decimer vs v2-r1b-f40a0d0+recycle/molscribe | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 16.7 [16.7, 16.7] |
| dev | v2-r1b-f40a0d0+recycle/decimer-hand vs v2-r1b-f40a0d0+recycle/molnextr | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| dev | v2-r1b-f40a0d0+recycle/decimer-hand vs v2-r1b-f40a0d0+recycle/molscribe | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 16.7 [16.7, 16.7] |
| dev | v2-r1b-f40a0d0+recycle/molnextr vs v2-r1b-f40a0d0+recycle/molscribe | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 16.7 [16.7, 16.7] |
| test | v1-976396a5/decimer vs v1-976396a5/decimer-hand | 1 | 9.1 [9.1, 9.1] | 1 / 0 / 0 | 1 | 10.0 [10.0, 10.0] |
| test | v1-976396a5/decimer vs v1-976396a5/molnextr | 1 | 9.1 [9.1, 9.1] | 1 / 0 / 0 | 1 | 10.0 [10.0, 10.0] |
| test | v1-976396a5/decimer vs v1-976396a5/molscribe | 1 | 18.2 [18.2, 18.2] | 1 / 0 / 0 | 1 | 10.0 [10.0, 10.0] |
| test | v1-976396a5/decimer vs v2-r1b-f40a0d0+recycle/decimer | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| test | v1-976396a5/decimer vs v2-r1b-f40a0d0+recycle/decimer-hand | 1 | 9.1 [9.1, 9.1] | 1 / 0 / 0 | 1 | 10.0 [10.0, 10.0] |
| test | v1-976396a5/decimer vs v2-r1b-f40a0d0+recycle/molnextr | 1 | 9.1 [9.1, 9.1] | 1 / 0 / 0 | 1 | 10.0 [10.0, 10.0] |
| test | v1-976396a5/decimer vs v2-r1b-f40a0d0+recycle/molscribe | 1 | 18.2 [18.2, 18.2] | 1 / 0 / 0 | 1 | 10.0 [10.0, 10.0] |
| test | v1-976396a5/decimer-hand vs v1-976396a5/molnextr | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| test | v1-976396a5/decimer-hand vs v1-976396a5/molscribe | 1 | 9.1 [9.1, 9.1] | 1 / 0 / 0 | 1 | 0.0 [0.0, 0.0] |
| test | v1-976396a5/decimer-hand vs v2-r1b-f40a0d0+recycle/decimer | 1 | -9.1 [-9.1, -9.1] | 0 / 1 / 0 | 1 | -10.0 [-10.0, -10.0] |
| test | v1-976396a5/decimer-hand vs v2-r1b-f40a0d0+recycle/decimer-hand | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| test | v1-976396a5/decimer-hand vs v2-r1b-f40a0d0+recycle/molnextr | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| test | v1-976396a5/decimer-hand vs v2-r1b-f40a0d0+recycle/molscribe | 1 | 9.1 [9.1, 9.1] | 1 / 0 / 0 | 1 | 0.0 [0.0, 0.0] |
| test | v1-976396a5/molnextr vs v1-976396a5/molscribe | 1 | 9.1 [9.1, 9.1] | 1 / 0 / 0 | 1 | 0.0 [0.0, 0.0] |
| test | v1-976396a5/molnextr vs v2-r1b-f40a0d0+recycle/decimer | 1 | -9.1 [-9.1, -9.1] | 0 / 1 / 0 | 1 | -10.0 [-10.0, -10.0] |
| test | v1-976396a5/molnextr vs v2-r1b-f40a0d0+recycle/decimer-hand | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| test | v1-976396a5/molnextr vs v2-r1b-f40a0d0+recycle/molnextr | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| test | v1-976396a5/molnextr vs v2-r1b-f40a0d0+recycle/molscribe | 1 | 9.1 [9.1, 9.1] | 1 / 0 / 0 | 1 | 0.0 [0.0, 0.0] |
| test | v1-976396a5/molscribe vs v2-r1b-f40a0d0+recycle/decimer | 1 | -18.2 [-18.2, -18.2] | 0 / 1 / 0 | 1 | -10.0 [-10.0, -10.0] |
| test | v1-976396a5/molscribe vs v2-r1b-f40a0d0+recycle/decimer-hand | 1 | -9.1 [-9.1, -9.1] | 0 / 1 / 0 | 1 | 0.0 [0.0, 0.0] |
| test | v1-976396a5/molscribe vs v2-r1b-f40a0d0+recycle/molnextr | 1 | -9.1 [-9.1, -9.1] | 0 / 1 / 0 | 1 | 0.0 [0.0, 0.0] |
| test | v1-976396a5/molscribe vs v2-r1b-f40a0d0+recycle/molscribe | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| test | v2-r1b-f40a0d0+recycle/decimer vs v2-r1b-f40a0d0+recycle/decimer-hand | 1 | 9.1 [9.1, 9.1] | 1 / 0 / 0 | 1 | 10.0 [10.0, 10.0] |
| test | v2-r1b-f40a0d0+recycle/decimer vs v2-r1b-f40a0d0+recycle/molnextr | 1 | 9.1 [9.1, 9.1] | 1 / 0 / 0 | 1 | 10.0 [10.0, 10.0] |
| test | v2-r1b-f40a0d0+recycle/decimer vs v2-r1b-f40a0d0+recycle/molscribe | 1 | 18.2 [18.2, 18.2] | 1 / 0 / 0 | 1 | 10.0 [10.0, 10.0] |
| test | v2-r1b-f40a0d0+recycle/decimer-hand vs v2-r1b-f40a0d0+recycle/molnextr | 1 | 0.0 [0.0, 0.0] | 0 / 0 / 1 | 1 | 0.0 [0.0, 0.0] |
| test | v2-r1b-f40a0d0+recycle/decimer-hand vs v2-r1b-f40a0d0+recycle/molscribe | 1 | 9.1 [9.1, 9.1] | 1 / 0 / 0 | 1 | 0.0 [0.0, 0.0] |
| test | v2-r1b-f40a0d0+recycle/molnextr vs v2-r1b-f40a0d0+recycle/molscribe | 1 | 9.1 [9.1, 9.1] | 1 / 0 / 0 | 1 | 0.0 [0.0, 0.0] |
