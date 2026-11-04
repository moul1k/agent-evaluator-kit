"""Scenario-group bootstrap; related variants never count as independent samples."""

import random


def bootstrap_detection(references, predictions, case_meetings, samples=1000, seed=42):
    groups = {}
    for key, reference in references.items():
        group = groups.setdefault(case_meetings[key[0]], [0, 0])
        group[1] += reference == "fail"
        group[0] += reference == "fail" and predictions.get(key) == "fail"
    if len(groups) < 2:
        return None
    values = list(groups.values())
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        draw = rng.choices(values, k=len(values))
        denominator = sum(v[1] for v in draw)
        if denominator:
            estimates.append(sum(v[0] for v in draw) / denominator)
    if not estimates:
        return None
    estimates.sort()
    return {
        "lower": estimates[int((len(estimates) - 1) * 0.025)],
        "upper": estimates[int((len(estimates) - 1) * 0.975)],
        "method": "group-cluster percentile bootstrap",
        "seed": seed,
        "resamples": samples,
        "valid_resamples": len(estimates),
        "meetings": len(groups),
    }
