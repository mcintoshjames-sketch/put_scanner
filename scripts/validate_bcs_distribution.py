import math
import numpy as np


def lognormal_region_probs(S0: float, mu: float, sigma: float, T: float, Ks: float, Kl: float):
    """Analytic probabilities that S_T falls in regions:
    P(S_T <= Ks), P(Ks < S_T < Kl), P(S_T >= Kl)
    for GBM with drift mu and vol sigma.
    """
    if sigma <= 0 or T <= 0 or S0 <= 0 or Ks <= 0 or Kl <= 0:
        return (float("nan"), float("nan"), float("nan"))

    m = (mu - 0.5 * sigma * sigma) * T
    s = sigma * math.sqrt(T)
    def _phi(x):
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    z_Ks = (math.log(Ks / S0) - m) / s
    z_Kl = (math.log(Kl / S0) - m) / s
    p_le_Ks = _phi(z_Ks)
    p_le_Kl = _phi(z_Kl)
    p_mid = max(0.0, min(1.0, p_le_Kl - p_le_Ks))
    p_lo = max(0.0, min(1.0, p_le_Ks))
    p_hi = max(0.0, min(1.0, 1.0 - p_le_Kl))
    # Normalize small numerical drift
    total = p_lo + p_mid + p_hi
    if total > 0:
        p_lo /= total
        p_mid /= total
        p_hi /= total
    return p_lo, p_mid, p_hi


def simulate_paths(S0: float, mu: float, sigma: float, T: float, n: int, seed: int | None = 1234):
    rng = np.random.default_rng(seed)
    Z = rng.standard_normal(n)
    drift = (mu - 0.5 * sigma * sigma) * T
    vol = sigma * math.sqrt(T)
    S_T = S0 * np.exp(drift + vol * Z)
    return S_T


def classify_bcs_pnl(S_T: np.ndarray, Ks: float, Kl: float, net_credit_ps: float):
    """Classify P&L outcomes for a bear call spread per contract.
    Returns counts in (profit_only, partial_loss, max_loss) bins.
    """
    # Per share profit in regions
    # Profit-only region: S_T <= Ks -> pnl_ps = net_credit_ps
    # Partial loss: Ks < S_T < Kl -> pnl_ps = net_credit_ps - (S_T - Ks)
    # Max loss: S_T >= Kl -> pnl_ps = net_credit_ps - (Kl - Ks)
    pnl_ps = np.full_like(S_T, net_credit_ps)
    spread_loss = np.maximum(0.0, S_T - Ks) - np.maximum(0.0, S_T - Kl)
    pnl_ps = pnl_ps - spread_loss
    pnl_contract = pnl_ps * 100.0

    profit_only = np.sum(S_T <= Ks)
    partial_loss = np.sum((S_T > Ks) & (S_T < Kl))
    max_loss = np.sum(S_T >= Kl)
    return pnl_contract, int(profit_only), int(partial_loss), int(max_loss)


def validate_bcs_distribution(
    S0: float,
    sigma: float,
    days: int,
    Ks: float,
    Kl: float,
    net_credit_contract: float,
    mu: float = 0.0,
    n_paths: int = 100_000,
    seed: int | None = 42,
):
    T = max(days, 0) / 365.0
    net_credit_ps = net_credit_contract / 100.0

    # Analytic expected region probabilities
    p_lo, p_mid, p_hi = lognormal_region_probs(S0, mu, sigma, T, Ks, Kl)

    # Monte Carlo paths
    S_T = simulate_paths(S0, mu, sigma, T, n_paths, seed)
    pnl_contract, c_lo, c_mid, c_hi = classify_bcs_pnl(S_T, Ks, Kl, net_credit_ps)

    # Frequencies
    f_lo = c_lo / n_paths
    f_mid = c_mid / n_paths
    f_hi = c_hi / n_paths

    # Summary
    summary = {
        "inputs": {
            "S0": S0,
            "sigma": sigma,
            "days": days,
            "T": T,
            "Ks": Ks,
            "Kl": Kl,
            "width": Kl - Ks,
            "net_credit_contract": net_credit_contract,
            "mu": mu,
            "n_paths": n_paths,
        },
        "expected_probs": {"profit_only(S_T<=Ks)": p_lo, "partial_loss(Ks<S_T<Kl)": p_mid, "max_loss(S_T>=Kl)": p_hi},
        "empirical_freqs": {"profit_only": f_lo, "partial_loss": f_mid, "max_loss": f_hi},
        "counts": {"profit_only": c_lo, "partial_loss": c_mid, "max_loss": c_hi},
        "pnl_stats": {
            "mean": float(np.mean(pnl_contract)),
            "std": float(np.std(pnl_contract)),
            "p5": float(np.percentile(pnl_contract, 5)),
            "p50": float(np.percentile(pnl_contract, 50)),
            "p95": float(np.percentile(pnl_contract, 95)),
            "min": float(np.min(pnl_contract)),
            "max": float(np.max(pnl_contract)),
        },
    }
    return summary


if __name__ == "__main__":
    # Default scenario tailored to the user's contract: QQQ 644/649 BCS
    # Assumptions (override here if needed):
    # - Current price near the short strike to emphasize mid-region probability
    # - 13 days to expiry, vol 25%, drift 0.0 (risk-neutral)
    S0 = 640.0           # Assumption — set close to Ks to test mid-region mass
    sigma = 0.25         # 25% annualized IV
    days = 13            # ~two weeks
    Ks = 644.0
    Kl = 649.0
    net_credit_contract = 21.0  # $21/contract (~$0.21 per share)
    mu = 0.0
    n_paths = 100_000

    res = validate_bcs_distribution(S0, sigma, days, Ks, Kl, net_credit_contract, mu=mu, n_paths=n_paths, seed=123)

    print("\n=== Bear Call Spread MC Validation (QQQ 644/649) ===")
    print("Inputs:")
    for k, v in res["inputs"].items():
        print(f"  {k}: {v}")
    print("\nExpected region probabilities (lognormal):")
    for k, v in res["expected_probs"].items():
        print(f"  {k}: {v*100:.2f}%")
    print("\nEmpirical MC frequencies:")
    for k, v in res["empirical_freqs"].items():
        print(f"  {k}: {v*100:.2f}%  (count={res['counts'][k]})")
    print("\nPnL per contract stats (USD):")
    for k, v in res["pnl_stats"].items():
        print(f"  {k}: {v:.2f}")

    # Simple validation: mid-region frequency should be non-negligible if S0 is near Ks
    expected_mid = res["expected_probs"]["partial_loss(Ks<S_T<Kl)"]
    empirical_mid = res["empirical_freqs"]["partial_loss"]
    if expected_mid > 0.10 and empirical_mid < expected_mid * 0.5:
        print("\n[WARN] Empirical mid-region mass is much lower than analytic expectation.")
    else:
        print("\n[OK] Empirical region frequencies align with analytic expectations.")
