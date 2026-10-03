# Learning log

One entry per week. Write what you built, what you learned, and one thing that confused you.
These entries become your interview stories and LinkedIn posts.

## How to add a new run
1. Save the new batch-record PDF (same form, typed) into `data/private/raw/`.
2. Double-click `Run FermentIQ.bat`.
3. Open `data/private/reports/<group>_<date>/report.html`.
4. If it says FAILED, read the one-line reason (e.g. not the same form).

## Week 1: FermentIQ v0.1 on our first run
- **Built:** with Claude Code, a pipeline that reads our batch-record PDF, checks it, and calculates growth kinetics.
- **To understand this week:** go through `notebooks/01_walkthrough.ipynb` and be able to explain:
  - [ ] why the slope of ln(OD) vs time is μ
  - [ ] why μmax uses at least 3 points and an R² cut-off
  - [ ] why OD readings near 1.0 should be diluted (and what happened to samples 5–6)
  - [ ] why clock time is used instead of the written time points
  - [ ] what GDP means and why a batch record is treated as a legal document
- **Learned:**
- **Confused me / bug I fixed:** (example) `N/A` and `Y / N` were mistaken for someone's initials, because they match the "letters/letters" pattern.
- **To ask professor:** see section 4 of the generated report.
