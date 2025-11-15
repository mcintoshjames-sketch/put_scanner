#!/bin/bash
# Run all portfolio risk management tests
# Usage: ./run_all_tests.sh [--schwab] [--verbose]

set -e  # Exit on error

SCHWAB_MODE=false
VERBOSE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --schwab)
            SCHWAB_MODE=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --schwab     Require Schwab API (fail if not available)"
            echo "  --verbose    Show detailed output"
            echo "  --help       Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                  # Run all tests with fallback to mock"
            echo "  $0 --schwab         # Run tests, require real Schwab"
            echo "  $0 --schwab --verbose  # Verbose mode with Schwab required"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo "================================================"
echo "Portfolio Risk Management Test Suite"
echo "================================================"
echo ""

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# Test 1: Unit Tests (Mock Data)
echo "================================================"
echo "TEST 1: Unit Tests (Mock Data)"
echo "================================================"
python3 test_portfolio.py
UNIT_TEST_RESULT=$?

if [ $UNIT_TEST_RESULT -eq 0 ]; then
    echo ""
    echo "✅ Unit tests PASSED"
else
    echo ""
    echo "❌ Unit tests FAILED with exit code $UNIT_TEST_RESULT"
    exit $UNIT_TEST_RESULT
fi

echo ""
echo "================================================"
echo "TEST 2: Singleton Pattern"
echo "================================================"
python3 test_singleton.py
SINGLETON_TEST_RESULT=$?

if [ $SINGLETON_TEST_RESULT -eq 0 ]; then
    echo ""
    echo "✅ Singleton tests PASSED"
else
    echo ""
    echo "❌ Singleton tests FAILED with exit code $SINGLETON_TEST_RESULT"
    exit $SINGLETON_TEST_RESULT
fi

echo ""
echo "================================================"
echo "TEST 3: Schwab Integration"
echo "================================================"

if [ "$SCHWAB_MODE" = true ]; then
    export REQUIRE_SCHWAB=true
    export MIN_POSITIONS=1
    echo "Mode: REQUIRED (will fail if Schwab unavailable)"
else
    export REQUIRE_SCHWAB=false
    echo "Mode: OPTIONAL (will fallback to mock data)"
fi

python3 test_schwab_integration.py
INTEGRATION_TEST_RESULT=$?

if [ $INTEGRATION_TEST_RESULT -eq 0 ]; then
    echo ""
    echo "✅ Integration tests PASSED"
else
    echo ""
    echo "❌ Integration tests FAILED with exit code $INTEGRATION_TEST_RESULT"
    exit $INTEGRATION_TEST_RESULT
fi

echo ""
echo "================================================"
echo "TEST 4: VaR and CVaR"
echo "================================================"
python3 test_var.py
VAR_TEST_RESULT=$?

if [ $VAR_TEST_RESULT -eq 0 ]; then
    echo ""
    echo "✅ VaR tests PASSED"
else
    echo ""
    echo "❌ VaR tests FAILED with exit code $VAR_TEST_RESULT"
    exit $VAR_TEST_RESULT
fi

echo ""
echo "================================================"
echo "TEST 5: VaR Integration"
echo "================================================"
python3 test_var_integration.py
VAR_INT_TEST_RESULT=$?

if [ $VAR_INT_TEST_RESULT -eq 0 ]; then
    echo ""
    echo "✅ VaR integration tests PASSED"
else
    echo ""
    echo "❌ VaR integration tests FAILED with exit code $VAR_INT_TEST_RESULT"
    exit $VAR_INT_TEST_RESULT
fi

# Summary
echo ""
echo "================================================"
echo "TEST SUMMARY"
echo "================================================"
echo "✅ Unit Tests:        PASSED"
echo "✅ Singleton Tests:   PASSED"
echo "✅ Integration Tests: PASSED"
echo "✅ VaR Tests:         PASSED"
echo "✅ VaR Integration:   PASSED"
echo "================================================"
echo ""
echo "All tests completed successfully! 🎉"
echo ""
echo "Next steps:"
echo "1. Start Streamlit: streamlit run strategy_lab.py"
echo "2. Go to '📊 Portfolio' tab"
echo "3. Test with real Schwab data"
echo ""
