# Strategy Lab Refactoring Plan

## 🎯 Goal
Reduce `strategy_lab.py` from 8,491 lines to ~3,500 lines through safe, incremental refactoring.

## 🔒 Safety Principles
1. **One module at a time** - commit and test after each extraction
2. **Backward compatibility** - all imports work as before
3. **No logic changes** - only move code, don't modify
4. **Test after each step** - verify app loads and scans work
5. **Git checkpoint** - commit after each successful extraction

## 📊 Refactoring Sequence

### ✅ Phase 1: Pure Functions (No Dependencies)

#### **STEP 1: Extract Options Math** 
**Priority:** 🔴 High | **Risk:** 🟢 Low | **Impact:** ~413 lines

**Create:** `options_math.py`

**Move from strategy_lab.py (lines 796-1209):**
- Black-Scholes pricing functions
- Greeks calculations (delta, gamma, theta, vega)
- Monte Carlo simulation
- Expected move calculations

**Dependencies:** Only `math`, `numpy` (no circular deps)

**Testing:**
```bash
# Test imports
python3 -c "from options_math import bs_call_price, mc_pnl; print('✅ Import OK')"

# Test Black-Scholes
python3 -c "from options_math import bs_call_price; print(bs_call_price(100, 100, 0.05, 0.0, 0.25, 0.25))"

# Run full app
streamlit run strategy_lab.py
```

**Verification Checklist:**
- [ ] File compiles without errors
- [ ] All math functions importable
- [ ] App loads without errors
- [ ] Scan produces results
- [ ] Monte Carlo tab works
- [ ] Stress test tab works

---

### ✅ Phase 2: Strategy Analyzers (Depend on Math)

#### **STEP 2: Extract Strategy Analysis**
**Priority:** 🔴 High | **Risk:** 🟡 Medium | **Impact:** ~1,837 lines

**Create:** `strategy_analysis.py`

**Move from strategy_lab.py (lines 1210-3047):**
- `analyze_csp()`
- `analyze_cc()`
- `analyze_collar()`
- `analyze_iron_condor()`
- `analyze_bull_put_spread()`
- `analyze_bear_call_spread()`
- `prescreen_tickers()`

**Dependencies:** 
- `options_math` (from Step 1)
- `yfinance`, `pandas`
- Data fetching functions (keep in main file for now)

**Testing:**
```bash
# Test imports
python3 -c "from strategy_analysis import analyze_csp; print('✅ Import OK')"

# Run scans
streamlit run strategy_lab.py
# Click "Scan Strategies" and verify all tabs populate
```

**Verification Checklist:**
- [ ] All analyzer functions work
- [ ] CSP scan produces results
- [ ] CC scan produces results  
- [ ] Collar scan produces results
- [ ] IC/spreads scan produces results
- [ ] Scoring/ranking works correctly

---

### ✅ Phase 3: UI Components

#### **STEP 3: Extract UI Helpers**
**Priority:** 🟡 Medium | **Risk:** 🟡 Medium | **Impact:** ~778 lines

**Create:** `ui_components.py`

**Move from strategy_lab.py (lines 4482-5260):**
- Sidebar configuration
- Settings management
- Diagnostics display
- Provider selection UI

**Dependencies:**
- `streamlit`
- `strategy_analysis`

**Testing:**
```bash
streamlit run strategy_lab.py
# Verify sidebar renders correctly
# Check all settings work
```

---

### ✅ Phase 4: Individual Strategy Tabs

#### **STEP 4: Extract Tab Modules**
**Priority:** 🟡 Medium | **Risk:** 🟢 Low | **Impact:** ~3,400 lines total

**Create:** `tabs/` directory with:
- `tab_csp.py`
- `tab_cc.py`
- `tab_collar.py`
- `tab_iron_condor.py`
- `tab_bull_put.py`
- `tab_bear_call.py`
- `tab_compare.py` (largest - ~1,742 lines)
- `tab_risk.py`
- `tab_playbook.py`
- `tab_runbook.py`
- `tab_stress.py`
- `tab_overview.py`
- `tab_roll.py`

**Testing:** Open each tab and verify functionality

---

### ✅ Phase 5: Utilities & Helpers

#### **STEP 5: Extract Utilities**
**Priority:** 🟢 Low | **Risk:** 🟢 Low | **Impact:** ~1,000 lines

**Create:** `utils/` directory:
- `data_fetching.py` - price, chain, expirations
- `safety_checks.py` - expiration risk
- `best_practices.py` - quality filters
- `runbook_helpers.py` - order generation logic

---

## 📈 Progress Tracking

| Step | Status | Lines Moved | Lines Remaining | Commits |
|------|--------|-------------|-----------------|---------|
| **Baseline** | ✅ | 0 | 8,491 | 4c4054d |
| **Step 1: Math** | ✅ **COMPLETE** | 413 | 8,092 | 081abcc, ffb2523 |
| **Step 2: Analyzers** | ⏳ | 1,837 | ~6,241 | - |
| **Step 3: UI** | ⏳ | 778 | ~5,463 | - |
| **Step 4: Tabs** | ⏳ | 3,400 | ~2,063 | - |
| **Step 5: Utils** | ⏳ | ~500 | ~1,563 | - |
| **Target** | 🎯 | ~6,928 | ~3,500 | - |

### Step 1 Complete ✅:
- ✅ Created options_math.py (547 lines)
- ✅ Module compiles successfully
- ✅ All imports work
- ✅ Test script passes (6 tests)
- ✅ Updated strategy_lab.py imports
- ✅ Fixed missing helper function imports (_bs_d1_d2, _norm_cdf)
- ✅ Removed duplicate _norm_cdf definition
- **Final:** strategy_lab.py reduced from 8,491 → 8,092 lines (399 lines removed)

---

## 🧪 Testing Protocol

After **each** step:

1. **Syntax Check:**
   ```bash
   python3 -m py_compile strategy_lab.py
   python3 -m py_compile <new_module>.py
   ```

2. **Import Test:**
   ```bash
   python3 -c "from <new_module> import *"
   ```

3. **App Load Test:**
   ```bash
   streamlit run strategy_lab.py &
   sleep 5
   curl -s http://localhost:8501 > /dev/null && echo "✅ App loads"
   ```

4. **Functional Test:**
   - Open app in browser
   - Run a scan with 2-3 tickers
   - Verify all tabs work
   - Check no errors in terminal

5. **Git Checkpoint:**
   ```bash
   git add .
   git commit -m "Step X: Extract <module>"
   git push origin main
   ```

---

## 🚨 Rollback Plan

If any step fails:
```bash
git reset --hard HEAD~1  # Undo last commit
git push origin main --force  # Update remote
```

---

## 📝 Next Action

**Ready to start with Step 1: Extract Options Math?**
- Safest extraction (pure functions)
- Clear boundaries (lines 796-1209)
- No circular dependencies
- Easy to test

Proceed? (y/n)
