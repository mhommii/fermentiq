"""Shared report text: run ids, plain-language observations and questions for review."""

from datetime import datetime


SEVERITIES = ["critical", "major", "minor"]


def run_id(record):
    """e.g. 'group-a_2026-01-15' (group + run date), used for file and folder names."""
    date = record.process.loc[record.process["used"], "raw_date"].iloc[0]
    try:
        date = datetime.strptime(date, "%d/%m/%y").strftime("%Y-%m-%d")
    except ValueError:
        date = date.replace("/", "-")
    group = record.header.get("group_id") or "batch"
    return f"{group}_{date}".lower().replace(" ", "-")


# ---------- report ----------

def interpretation(findings, kin):
    """Plain-language bullet points about the run, based on the results."""
    df, mu, rates = kin["table"], kin["mu_max"], kin["rates"]
    checks = set(findings["check"])
    lag = "from the start (no visible lag phase)" if rates["phase"].iloc[0] == "exponential" \
        else f"after a lag of about {rates['t_end_h'].iloc[0]:.1f} h"
    bullets = [f"The culture grew exponentially {lag}, at μmax ≈ {mu['mu_max_per_h']:.2f} h⁻¹ "
               f"(doubling every ~{mu['doubling_time_min']:.0f} min)."]

    slowed = rates[(rates["t_start_h"] >= mu["t_end_h"] - 1e-9) & (rates["phase"] != "exponential")]
    if len(slowed):
        s = slowed.iloc[0]
        bullets.append(
            f"Growth first slowed between samples {s['from_sample']} and {s['to_sample']} "
            f"(≈ {s['t_start_h']:.1f}–{s['t_end_h']:.1f} h), when the probe pH was {s['ph_probe_end']:.2f}. "
            f"pH went from {df['ph_probe'].iloc[0]:.1f} to {df['ph_probe'].iloc[-1]:.1f} by the end of the run. "
            "If pH wasn't controlled, acidification may have limited growth. A pH-controlled run would test this.")
    if "od_near_saturation" in checks:
        bullets.append("Samples flagged \"possibly underestimated\" were read near the spectrophotometer's limit "
                       "without dilution. Growth rates for intervals touching them are unreliable, so they were "
                       "excluded from the logistic fit.")
    if "pellet_vs_od" in checks:
        bullets.append("Pellet weights don't follow OD, so they can't be used as a biomass measurement in this run.")
    return "\n".join(f"- {b}" for b in bullets)


def questions_for_review(findings, df):
    """Turn findings into questions to bring to the professor / group."""
    def rows(check):
        return findings[findings["check"] == check]

    questions = []
    for _, f in rows("time_cross_page").iterrows():
        questions.append(f"Sample {f['sample']}: which time is correct, {f['recorded']} or {f['expected']}?")
    for _, f in rows("pellet_negative").iterrows():
        questions.append(f"Sample {f['sample']}: what were the real tube weights? "
                         "The tube + pellet weighs less than the empty tube.")
    if len(rows("od_near_saturation")):
        questions.append("What is our spectrophotometer's linear range? Should we dilute earlier than A = 1.0?")
    if len(rows("ph_offset")):
        questions.append("When were the bioreactor pH probe and the bench pH meter last calibrated, and which do we trust?")
    ph_drop = df["ph_probe"].iloc[0] - df["ph_probe"].min()
    if ph_drop > 0.5:
        questions.append(f"pH fell from {df['ph_probe'].iloc[0]:.1f} to {df['ph_probe'].min():.1f} without control. "
                         "What in the medium caused the acidification, and could it have slowed growth?")
    if len(rows("od_replicate_missing")):
        questions.append("Why was the replicate #2 absorbance not measured?")
    unknown = ", ".join(rows("initials_unknown")["recorded"])
    if unknown:
        questions.append(f"Who do these initials belong to (not on the member list): {unknown}?")
    return "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1)) or "None. No open questions."
