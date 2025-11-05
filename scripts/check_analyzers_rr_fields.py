import sys
from types import ModuleType
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Create a fake data_fetching module
fake = ModuleType('data_fetching')

# Simple helpers

def _get_num_from_row(r, keys, default=float('nan')):
    for k in keys:
        if k in r:
            try:
                v = float(r[k])
                if v == v:
                    return v
            except Exception:
                pass
    return default

fake._get_num_from_row = _get_num_from_row
fake._safe_int = lambda x, d=0: int(float(x)) if x == x else d

# Pricing that returns mid-ish values

def effective_credit(bid, ask, last, **kwargs):
    try:
        b = float(bid)
        a = float(ask)
        if b > 0 and a > 0 and a >= b:
            return b + 0.25*(a-b)
    except Exception:
        pass
    return float(last) if last == last else 1.0


def effective_debit(bid, ask, last, **kwargs):
    try:
        b = float(bid)
        a = float(ask)
        if b > 0 and a > 0 and a >= b:
            return a - 0.25*(a-b)
    except Exception:
        pass
    return float(last) if last == last else 1.0

fake.effective_credit = effective_credit
fake.effective_debit = effective_debit

# Dummy price/expirations/chain

def fetch_price(ticker):
    return 100.0

fake.fetch_price = fetch_price
from datetime import datetime, timedelta
fake.fetch_expirations = lambda t: [(datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')]


def compute_spread_pct(b, a, mid):
    try:
        b = float(b); a = float(a); mid = float(mid)
        if mid > 0:
            return (a-b)/mid*100.0
    except Exception:
        pass
    return 10.0

# Build a minimal chain around S=100

def fetch_chain(ticker, exp):
    # Put/call rows with reasonable IV, OI, volume
    data = [
        # Puts (OTM, strikes below 100)
        {'type':'put','strike':95,'bid':1.80,'ask':2.20,'last':2.00,'oi':1500,'volume':600,'iv':0.25},
        {'type':'put','strike':90,'bid':0.90,'ask':1.20,'last':1.00,'oi':1800,'volume':700,'iv':0.24},
        # Calls (OTM, strikes above 100)
        {'type':'call','strike':105,'bid':1.70,'ask':2.10,'last':1.90,'oi':1400,'volume':550,'iv':0.26},
        {'type':'call','strike':110,'bid':0.85,'ask':1.10,'last':0.95,'oi':1600,'volume':650,'iv':0.25},
    ]
    return pd.DataFrame(data)

fake.fetch_chain = fetch_chain

# Dummy exp risk
fake.check_expiration_risk = lambda **kwargs: {
    'expiration_type':'Weekly (Friday)','risk_level':'HIGH','action':'WARN'
}

# Expose helpers
fake.estimate_next_ex_div = lambda stock: (None, 0.0)

sys.modules['data_fetching'] = fake

# Import analysis now that fakes are in place
import strategy_analysis as sa

# Patch earnings/div info to avoid yfinance usage
def _no_earn(_):
    return None

def _div_zero(stock, S):
    return 0.0, 0.0

sa.get_earnings_date = _no_earn
sa.trailing_dividend_info = _div_zero

# Run analyzers
bps = sa.analyze_bull_put_spread('FAKE', min_days=1, days_limit=60, min_oi=100, max_spread=25.0,
                                 min_roi=0.01, min_cushion=0.0, min_poew=0.0, earn_window=0,
                                 risk_free=0.01, spread_width=5.0)

bcs = sa.analyze_bear_call_spread('FAKE', min_days=1, days_limit=60, min_oi=100, max_spread=25.0,
                                  min_roi=0.01, min_cushion=0.0, min_poew=0.0, earn_window=0,
                                  risk_free=0.01, spread_width=5.0)

for name, df in [('BPS', bps), ('BCS', bcs)]:
    assert not df.empty, f"{name} df is empty"
    for col in ['RiskRewardScore','MC_PnL_p5','MC_ROI_ann_p5%','MC_ExpectedPnL','MC_ROI_ann%']:
        assert col in df.columns, f"{name} missing column {col}"
    # Basic bounds
    assert (df['RiskRewardScore'].dropna().between(0.0,1.0)).all(), f"{name} RiskRewardScore out of bounds"

print('Analyzer checks PASSED')
