import sys
from streamlit.web import cli as stcli

if __name__ == "__main__":
    # Launch the Strategy Lab app via Streamlit CLI
    # Headless so it doesn't try to prompt in some environments
    sys.argv = [
        "streamlit", "run", "strategy_lab.py",
        "--server.headless=true",
    ]
    sys.exit(stcli.main())
