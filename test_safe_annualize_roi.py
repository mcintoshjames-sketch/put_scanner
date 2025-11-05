import numpy as np
import math
from options_math import safe_annualize_roi


def test_scalar_basic():
    # 10% over 30 days
    val = float(safe_annualize_roi(0.10, 30))
    assert math.isfinite(val)
    # Should annualize higher than cycle ROI for < 365d
    assert val > 0.10


def test_days_leq_zero_nan():
    out = safe_annualize_roi(0.10, 0)
    assert np.isnan(out)


def test_base_nonpositive_nan():
    # ROI <= -100% -> invalid base
    out = safe_annualize_roi(-1.000001, 30)
    assert np.isnan(out)


def test_vector_shape_and_finiteness():
    vals = np.array([-0.9, -0.5, 0.0, 0.1, 1.0])
    out = safe_annualize_roi(vals, 45)
    assert out.shape == vals.shape
    # allow NaNs only when base <= 0
    base = 1.0 + vals
    mask_invalid = base <= 0
    assert np.all(np.isfinite(out[~mask_invalid]))


def test_large_roi_is_finite_due_to_clipping():
    # Extremely large ROI should be finite due to exponent clipping
    out = float(safe_annualize_roi(1e6, 7))
    assert math.isfinite(out)
