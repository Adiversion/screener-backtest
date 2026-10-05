"""Small shared statistics helpers for the study and diagnostic scripts.

These were previously copy-pasted into each script; keeping one implementation
means a fix to the significance test lands everywhere at once.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def t_stat(diffs) -> float:
    """One-sample t-statistic of the mean.

    Returns NaN when the sample is too small or has no dispersion, because a
    t-statistic is undefined there rather than zero.
    """
    d = pd.Series(diffs).dropna()
    if len(d) < 3 or d.std() == 0:
        return float("nan")
    return float(d.mean() / (d.std() / np.sqrt(len(d))))
