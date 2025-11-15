# Schwab Token Refresh Guide

This guide explains how to manage and refresh Schwab API tokens in the Strategy Lab app.

## Overview

Schwab API uses OAuth 2.0 authentication with two types of tokens:
- **Access Token**: Valid for 30 minutes, used for API requests
- **Refresh Token**: Valid for 7 days, used to get new access tokens

## Token Refresh Methods

### Method 1: In-App Token Refresh (Recommended)

The easiest way to refresh your token is directly in the Strategy Lab app:

1. Open the Strategy Lab app (`streamlit run strategy_lab.py`)
2. Look at the sidebar under **📡 Data Provider**
3. You'll see the **Schwab Token Status** section showing:
   - Current token expiration time
   - Time remaining (hours or minutes)
   - Token health indicator (green/yellow/red)

4. Click the **🔄 Refresh Token** button
5. Wait a few seconds for the refresh to complete
6. The app will show the new expiration time

**When to refresh:**
- Yellow warning: Less than 1 hour remaining
- Red error: Token has expired
- Proactive: Anytime you want to ensure fresh credentials

### Method 1b: Full OAuth Reset Inside the App

If the refresh token expires or you paste the wrong redirect URL, you no longer need the CLI. Use the **🔐 Manual OAuth / Re-authenticate** expander in the Schwab section:

1. Confirm the callback URL matches the one registered on developer.schwab.com (defaults to `SCHWAB_CALLBACK_URL`).
2. Click **Open Authorization URL** to launch the Schwab login page.
3. Approve access, then copy the entire redirect URL from the browser address bar.
4. Paste the redirect URL back into the text area and click **Complete OAuth Re-auth**.
5. The app stores the new token, shows the updated expiration, and restarts automatically.

Additional tools inside the expander:
- **🧹 Reset Token File** – backs up and deletes a corrupted `schwab_token.json` before running OAuth again.
- **Authorization URL preview** – handy for verifying the correct callback before signing in.
- Error details surface inline so you know whether missing credentials or mismatched callbacks caused the failure.

### Method 2: Command-Line Token Refresh

Use the command-line script for automated workflows or debugging:

```bash
python force_refresh_token.py
```

**What it does:**
- Reads your current `schwab_token.json`
- Extracts the refresh token
- Requests a new access token from Schwab API
- Updates the token file with new credentials
- Shows new expiration time

**Output example:**
```
🔄 Force Refreshing Schwab Access Token
Current access token expires: 2025-11-11 14:30:00
Time remaining: 25 minutes

✅ Access token refreshed successfully!
New token expires: 2025-11-11 15:00:00
Time until expiration: 30 minutes
```

### Method 3: Automatic Refresh via schwab-py

The `schwab-py` library automatically refreshes tokens when needed during API calls. However, manual refresh is recommended when:
- Token is about to expire before a critical operation
- You want to verify token health
- Running batch operations that might span 30 minutes

## Token Lifecycle

```
Day 0: Initial Authentication
├── Run: python authenticate_schwab.py
├── Creates: schwab_token.json
├── Access Token: 30 minutes
└── Refresh Token: 7 days

Every 30 minutes: Access Token Expires
├── Click: "🔄 Refresh Token" in app
├── OR run: python force_refresh_token.py
└── Gets: New 30-minute access token

Day 7: Refresh Token Expires
├── Token refresh will fail
├── Must re-authenticate
└── Run: python authenticate_schwab.py
```

## Troubleshooting

### Error: "Token refresh failed"

**Possible causes:**
1. Refresh token has expired (after 7 days)
2. Network connectivity issues
3. Schwab API credentials changed

**Solution:**
Re-authenticate to get a fresh token:
```bash
python authenticate_schwab.py
```

### Error: "Token file not found"

**Cause:** The `schwab_token.json` file doesn't exist.

**Solution:**
Run the authentication script:
```bash
python authenticate_schwab.py
```

### Warning: "Token expires in X minutes"

**Cause:** Your access token is about to expire soon.

**Solution:**
Click the "🔄 Refresh Token" button in the app sidebar, or run:
```bash
python force_refresh_token.py
```

## Security Best Practices

1. **Never commit** `schwab_token.json` to version control (it's in `.gitignore`)
2. **Protect your credentials**: Don't share API keys or secrets
3. **Regular refresh**: Refresh tokens proactively before they expire
4. **Monitor status**: Check token status in the app sidebar regularly
5. **Re-authenticate**: If token refresh fails, re-authenticate immediately

## Token File Structure

The `schwab_token.json` file contains:

```json
{
  "creation_timestamp": 1731344400,
  "token": {
    "access_token": "...",
    "refresh_token": "...",
    "expires_in": 1800,
    "expires_at": 1731346200,
    "token_type": "Bearer",
    "scope": "api",
    "id_token": "..."
  }
}
```

**Key fields:**
- `access_token`: Used for API requests (30 min lifetime)
- `refresh_token`: Used to get new access tokens (7 day lifetime)
- `expires_at`: Unix timestamp when access token expires
- `expires_in`: Seconds until access token expires (1800 = 30 minutes)

## Automation Tips

### Scheduled Token Refresh

For long-running processes, you can schedule token refreshes:

```bash
# Refresh token every 25 minutes (before 30-min expiry)
while true; do
    sleep 1500  # 25 minutes
    python force_refresh_token.py
done
```

### Pre-execution Token Check

Before running critical operations:

```bash
# Check token status and refresh if needed
python -c "
from providers.schwab import SchwabClient
client = SchwabClient()
info = client.get_token_info()
if info['minutes_remaining'] < 10:
    print('Refreshing token...')
    client.refresh_token()
"
```

## Quick Reference

| Task | Command | When to Use |
|------|---------|-------------|
| View token status | Check app sidebar | Anytime |
| Refresh token (GUI) | Click "🔄 Refresh Token" | Token expiring soon |
| Refresh token (CLI) | `python force_refresh_token.py` | Automation/scripts |
| Re-authenticate | `python authenticate_schwab.py` | Refresh token expired |
| Test connection | Try fetching a quote in app | After refresh |

## Related Files

- `authenticate_schwab.py` - Initial OAuth authentication
- `force_refresh_token.py` - Manual token refresh script
- `providers/schwab.py` - Schwab API client with refresh methods
- `schwab_token.json` - Token storage (gitignored)
- `config.py` - Provider configuration settings

## Support

If you encounter issues:
1. Check token expiration in app sidebar
2. Try manual refresh: `python force_refresh_token.py`
3. If refresh fails, re-authenticate: `python authenticate_schwab.py`
4. Verify environment variables are set correctly
5. Check Schwab API status at developer.schwab.com

## Notes

- Access tokens expire every 30 minutes (Schwab limitation)
- Refresh tokens expire after 7 days (Schwab limitation)
- The app automatically shows token status when using Schwab provider
- Token refresh is non-disruptive - no need to restart the app
- Multiple refreshes are safe - you can refresh as often as needed
