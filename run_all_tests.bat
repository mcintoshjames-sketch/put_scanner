@echo off
REM Run all portfolio risk management tests on Windows
REM Usage: run_all_tests.bat [--schwab] [--verbose]

setlocal enabledelayedexpansion

set SCHWAB_MODE=false
set VERBOSE=false

:parse_args
if "%1"=="" goto end_parse
if /i "%1"=="--schwab" (
    set SCHWAB_MODE=true
    shift
    goto parse_args
)
if /i "%1"=="--verbose" (
    set VERBOSE=true
    shift
    goto parse_args
)
if /i "%1"=="--help" (
    echo Usage: %0 [OPTIONS]
    echo.
    echo Options:
    echo   --schwab     Require Schwab API ^(fail if not available^)
    echo   --verbose    Show detailed output
    echo   --help       Show this help message
    echo.
    echo Examples:
    echo   %0                  # Run all tests with fallback to mock
    echo   %0 --schwab         # Run tests, require real Schwab
    echo   %0 --schwab --verbose  # Verbose mode with Schwab required
    exit /b 0
)
echo Unknown option: %1
echo Use --help for usage information
exit /b 1

:end_parse

echo ================================================
echo Portfolio Risk Management Test Suite
echo ================================================
echo.

REM Activate virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
)

REM Test 1: Unit Tests
echo ================================================
echo TEST 1: Unit Tests ^(Mock Data^)
echo ================================================
python test_portfolio.py
if errorlevel 1 (
    echo.
    echo ❌ Unit tests FAILED
    exit /b 1
)
echo.
echo ✅ Unit tests PASSED

REM Test 2: Singleton
echo.
echo ================================================
echo TEST 2: Singleton Pattern
echo ================================================
python test_singleton.py
if errorlevel 1 (
    echo.
    echo ❌ Singleton tests FAILED
    exit /b 1
)
echo.
echo ✅ Singleton tests PASSED

REM Test 3: Integration
echo.
echo ================================================
echo TEST 3: Schwab Integration
echo ================================================

if "%SCHWAB_MODE%"=="true" (
    set REQUIRE_SCHWAB=true
    set MIN_POSITIONS=1
    echo Mode: REQUIRED ^(will fail if Schwab unavailable^)
) else (
    set REQUIRE_SCHWAB=false
    echo Mode: OPTIONAL ^(will fallback to mock data^)
)

python test_schwab_integration.py
if errorlevel 1 (
    echo.
    echo ❌ Integration tests FAILED
    exit /b 1
)
echo.
echo ✅ Integration tests PASSED

REM Summary
echo.
echo ================================================
echo TEST SUMMARY
echo ================================================
echo ✅ Unit Tests:        PASSED
echo ✅ Singleton Tests:   PASSED
echo ✅ Integration Tests: PASSED
echo ================================================
echo.
echo All tests completed successfully! 🎉
echo.
echo Next steps:
echo 1. Start Streamlit: streamlit run strategy_lab.py
echo 2. Go to '📊 Portfolio' tab
echo 3. Test with real Schwab data
echo.

endlocal
