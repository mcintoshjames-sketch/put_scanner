# schwab_trading.py - Schwab API trade execution
# Handles order creation and submission to Schwab brokerage accounts

from __future__ import annotations
import json
import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Literal, List
from pathlib import Path


class SchwabTrader:
    """
    Handles trade order creation and execution via Schwab API.
    Supports dry-run mode (export to file) and live trading.
    """
    
    def __init__(
        self,
        account_id: Optional[str] = None,
        dry_run: bool = True,
        export_dir: Optional[str] = None,
        client = None
    ):
        """
        Initialize Schwab trader.
        
        Args:
            account_id: Schwab account ID (encrypted account number)
            dry_run: If True, export orders to file instead of sending to API
            export_dir: Directory to save order files (default: ./trade_orders)
            client: Optional Schwab API client (from providers.schwab.SchwabClient)
        """
        self.account_id = account_id or os.environ.get("SCHWAB_ACCOUNT_ID")
        self.dry_run = dry_run
        self.export_dir = Path(export_dir or "./trade_orders")
        self.export_dir.mkdir(exist_ok=True)
        self.client = client
        
        # Safety mechanism: Track previewed orders
        # Orders must be previewed before execution
        self._preview_cache = {}  # order_hash -> preview_timestamp
        self._preview_expiry_minutes = 30  # Previews expire after 30 minutes
    
    def _compute_order_hash(self, order: Dict[str, Any]) -> str:
        """
        Compute a unique hash for an order to track it through preview->execution.
        
        Args:
            order: Order payload dictionary
            
        Returns:
            SHA256 hash of the order (first 16 characters)
        """
        # Create a canonical string representation of the order
        # Focus on key fields that identify the order
        order_key = {
            'orderType': order.get('orderType'),
            'duration': order.get('duration'),
            'session': order.get('session'),
            'price': order.get('price'),
            'stopPrice': order.get('stopPrice'),
            'legs': []
        }
        
        # Add leg details
        for leg in order.get('orderLegCollection', []):
            leg_key = {
                'instruction': leg.get('instruction'),
                'quantity': leg.get('quantity'),
                'instrument': leg.get('instrument', {}).get('symbol')
            }
            order_key['legs'].append(leg_key)
        
        # Compute hash
        order_str = json.dumps(order_key, sort_keys=True)
        return hashlib.sha256(order_str.encode()).hexdigest()[:16]
    
    def _register_preview(self, order: Dict[str, Any]) -> str:
        """
        Register an order as previewed.
        
        Args:
            order: Order payload dictionary
            
        Returns:
            Order hash
        """
        order_hash = self._compute_order_hash(order)
        self._preview_cache[order_hash] = datetime.now()
        return order_hash
    
    def _is_previewed(self, order: Dict[str, Any]) -> bool:
        """
        Check if an order has been previewed and the preview hasn't expired.
        
        Args:
            order: Order payload dictionary
            
        Returns:
            True if order was recently previewed, False otherwise
        """
        order_hash = self._compute_order_hash(order)
        
        if order_hash not in self._preview_cache:
            return False
        
        preview_time = self._preview_cache[order_hash]
        expiry_time = preview_time + timedelta(minutes=self._preview_expiry_minutes)
        
        if datetime.now() > expiry_time:
            # Preview expired, remove from cache
            del self._preview_cache[order_hash]
            return False
        
        return True
    
    def _clear_preview(self, order: Dict[str, Any]) -> None:
        """
        Clear preview record for an order after execution.
        
        Args:
            order: Order payload dictionary
        """
        order_hash = self._compute_order_hash(order)
        if order_hash in self._preview_cache:
            del self._preview_cache[order_hash]
    
    def get_account_numbers(self) -> List[Dict[str, str]]:
        """
        Retrieve account numbers from Schwab API.
        Returns list of {accountNumber: plain text, hashValue: encrypted} pairs.
        
        The encrypted hashValue must be used for all subsequent API calls.
        
        Returns:
            List of account dictionaries with accountNumber and hashValue
            
        Example response:
            [
                {
                    "accountNumber": "123456789",
                    "hashValue": "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y5Z6"
                }
            ]
        """
        if not self.client:
            raise RuntimeError(
                "Schwab API client required. Initialize SchwabTrader with a client instance."
            )
        
        try:
            # Call Schwab API to get account numbers
            response = self.client.client.get_account_numbers()
            
            # The response should be a list of account objects
            # Format: [{"accountNumber": "...", "hashValue": "..."}]
            accounts = response.json() if hasattr(response, 'json') else response
            
            # Save to file for reference
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.export_dir / f"account_numbers_{timestamp}.json"
            
            with open(filepath, "w") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "accounts": accounts,
                    "note": "Use the 'hashValue' field as accountNumber in all API calls"
                }, f, indent=2)
            
            return accounts
        
        except Exception as e:
            raise RuntimeError(f"Failed to retrieve account numbers: {e}")
    
    def get_account_info(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get detailed account information including balances and buying power.
        
        Args:
            account_id: Account hash value (uses self.account_id if not provided)
        
        Returns:
            Dictionary with account details including:
            - cashBalance: Available cash
            - buyingPower: Total buying power for trades
            - optionBuyingPower: Buying power for options
            - marginBalance: Margin information
            - accountValue: Total account value
            
        Example response:
            {
                "securitiesAccount": {
                    "type": "MARGIN",
                    "accountNumber": "hash...",
                    "currentBalances": {
                        "cashBalance": 10000.00,
                        "buyingPower": 40000.00,
                        "optionBuyingPower": 10000.00
                    },
                    "initialBalances": {...},
                    "projectedBalances": {...}
                }
            }
        """
        if not self.client:
            raise RuntimeError(
                "Schwab API client required. Initialize SchwabTrader with a client instance."
            )
        
        acct_id = account_id or self.account_id
        if not acct_id:
            raise RuntimeError(
                "Account ID required. Set SCHWAB_ACCOUNT_ID or pass account_id parameter."
            )
        
        try:
            # Call Schwab API to get account details
            # fields parameter controls what data is returned
            response = self.client.client.get_account(
                acct_id, 
                fields=self.client.client.Account.Fields.POSITIONS
            )
            
            account_data = response.json() if hasattr(response, 'json') else response
            
            # Save to file for reference
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.export_dir / f"account_info_{timestamp}.json"
            
            with open(filepath, "w") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "account_id": acct_id,
                    "account_data": account_data
                }, f, indent=2)
            
            return account_data
        
        except Exception as e:
            raise RuntimeError(f"Failed to retrieve account info: {e}")
    
    def check_buying_power(
        self,
        required_amount: float,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check if account has sufficient buying power for a trade.
        
        Args:
            required_amount: Amount of buying power needed (e.g., for cash-secured put)
            account_id: Account hash value (uses self.account_id if not provided)
        
        Returns:
            Dictionary with:
            - sufficient: Boolean indicating if you have enough buying power
            - available: Current buying power available
            - required: Amount needed for trade
            - shortfall: Amount short (if insufficient)
            - option_buying_power: Buying power specifically for options
        """
        account_data = self.get_account_info(account_id)
        
        # Extract balance information
        securities_account = account_data.get('securitiesAccount', {})
        current_balances = securities_account.get('currentBalances', {})
        
        # Get relevant buying power metrics
        buying_power = current_balances.get('buyingPower', 0.0)
        option_buying_power = current_balances.get('optionBuyingPower', 0.0)
        cash_balance = current_balances.get('cashBalance', 0.0)
        
        # For cash-secured puts, we need cash or margin
        # Use option buying power as the key metric
        available = option_buying_power
        
        result = {
            "sufficient": available >= required_amount,
            "available": available,
            "required": required_amount,
            "shortfall": max(0, required_amount - available),
            "option_buying_power": option_buying_power,
            "total_buying_power": buying_power,
            "cash_balance": cash_balance,
            "account_type": securities_account.get('type', 'UNKNOWN')
        }
        
        return result
    
    def preview_order(
        self,
        order: Dict[str, Any],
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Preview an order with Schwab API before placing it.
        
        This calls the previewOrder endpoint to show what would happen
        if the order were placed, including:
        - Commission and fees
        - Estimated order value
        - Buying power effect
        - Margin requirements
        - Warning messages
        
        Args:
            order: Order payload dictionary
            account_id: Account hash value (uses self.account_id if not provided)
        
        Returns:
            Preview response from Schwab API
            
        Raises:
            RuntimeError: If client not available or preview fails
        """
        if not self.client:
            raise RuntimeError(
                "Schwab API client required. Initialize SchwabTrader with a client instance."
            )
        
        acct_id = account_id or self.account_id
        if not acct_id:
            raise RuntimeError(
                "Account ID required. Set SCHWAB_ACCOUNT_ID or pass account_id parameter."
            )
        
        try:
            # Call Schwab API preview endpoint
            # The client passed in is SchwabClient, which wraps schwab.client.Client
            # Access the underlying schwab client
            schwab_client = self.client.client if hasattr(self.client, 'client') else self.client
            response = schwab_client.preview_order(acct_id, order)
            
            # Parse response
            preview_data = response.json() if hasattr(response, 'json') else response
            
            # Register this order as previewed (for safety mechanism)
            order_hash = self._register_preview(order)
            
            # Save preview to file for reference
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.export_dir / f"order_preview_{timestamp}.json"
            
            with open(filepath, "w") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "account_id": acct_id,
                    "order": order,
                    "preview": preview_data,
                    "order_hash": order_hash  # Include hash for tracking
                }, f, indent=2)
            
            return {
                "status": "preview_success",
                "preview": preview_data,
                "filepath": str(filepath),
                "order_hash": order_hash,
                "message": f"Order preview saved to {filepath}"
            }
        
        except Exception as e:
            # Save error details
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.export_dir / f"order_preview_error_{timestamp}.json"
            
            with open(filepath, "w") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "account_id": acct_id,
                    "order": order,
                    "error": str(e),
                    "error_type": type(e).__name__
                }, f, indent=2)
            
            raise RuntimeError(f"Failed to preview order: {e}")
    
    def create_option_order(
        self,
        symbol: str,
        expiration: str,
        strike: float,
        option_type: Literal["PUT", "CALL"],
        action: Literal["BUY_TO_OPEN", "SELL_TO_OPEN", "BUY_TO_CLOSE", "SELL_TO_CLOSE"],
        quantity: int,
        order_type: Literal["MARKET", "LIMIT", "STOP", "STOP_LIMIT"] = "LIMIT",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        duration: Literal["DAY", "GTC", "FILL_OR_KILL"] = "DAY",
        session: Literal["NORMAL", "AM", "PM", "SEAMLESS"] = "NORMAL"
    ) -> Dict[str, Any]:
        """
        Create an option order payload for Schwab API.
        
        Args:
            symbol: Underlying stock symbol (e.g., "AAPL")
            expiration: Option expiration date (YYYY-MM-DD format)
            strike: Strike price
            option_type: "PUT" or "CALL"
            action: Order action (e.g., "SELL_TO_OPEN" for cash-secured put)
            quantity: Number of contracts
            order_type: Order type (MARKET, LIMIT, etc.)
            limit_price: Limit price for LIMIT orders
            stop_price: Stop price for STOP orders
            duration: Order duration (DAY, GTC, etc.)
            session: Trading session
        
        Returns:
            Order payload dictionary ready for Schwab API
        """
        # Format expiration date for option symbol (YYMMDD)
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")
        
        # Build option symbol: SYMBOL   YYMMDDC/PSTRIKE (with spaces, not underscore)
        # Schwab format: "TGT   251121P00085000" (symbol padded to 6 chars with spaces)
        # Example: AAPL  250117C00150000 (AAPL Jan 17 2025 $150 Call)
        strike_str = f"{int(strike * 1000):08d}"
        symbol_padded = f"{symbol:<6}"  # Left-align symbol, pad to 6 chars with spaces
        option_symbol = f"{symbol_padded}{exp_str}{option_type[0]}{strike_str}"
        
        # Determine instruction from action
        instruction_map = {
            "BUY_TO_OPEN": "BUY_TO_OPEN",
            "SELL_TO_OPEN": "SELL_TO_OPEN",
            "BUY_TO_CLOSE": "BUY_TO_CLOSE",
            "SELL_TO_CLOSE": "SELL_TO_CLOSE"
        }
        instruction = instruction_map[action]
        
        # Build order payload
        order = {
            "orderType": order_type,
            "session": session,
            "duration": duration,
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": instruction,
                    "quantity": quantity,
                    "instrument": {
                        "symbol": option_symbol,
                        "assetType": "OPTION"
                    }
                }
            ]
        }
        
        # Add price fields based on order type
        if order_type == "LIMIT" and limit_price is not None:
            order["price"] = limit_price
        elif order_type == "STOP" and stop_price is not None:
            order["stopPrice"] = stop_price
        elif order_type == "STOP_LIMIT":
            if limit_price is not None:
                order["price"] = limit_price
            if stop_price is not None:
                order["stopPrice"] = stop_price
        
        return order
    
    def create_cash_secured_put_order(
        self,
        symbol: str,
        expiration: str,
        strike: float,
        quantity: int,
        limit_price: float,
        duration: Literal["DAY", "GTC"] = "DAY"
    ) -> Dict[str, Any]:
        """
        Create a cash-secured put order (sell to open).
        
        Args:
            symbol: Underlying stock symbol
            expiration: Option expiration date (YYYY-MM-DD)
            strike: Strike price
            quantity: Number of contracts
            limit_price: Limit price (premium to receive)
            duration: Order duration
        
        Returns:
            Order payload dictionary
        """
        return self.create_option_order(
            symbol=symbol,
            expiration=expiration,
            strike=strike,
            option_type="PUT",
            action="SELL_TO_OPEN",
            quantity=quantity,
            order_type="LIMIT",
            limit_price=limit_price,
            duration=duration
        )
    
    def create_covered_call_order(
        self,
        symbol: str,
        expiration: str,
        strike: float,
        quantity: int,
        limit_price: float,
        duration: Literal["DAY", "GTC"] = "DAY"
    ) -> Dict[str, Any]:
        """
        Create a covered call order (sell to open).
        
        Args:
            symbol: Underlying stock symbol
            expiration: Option expiration date (YYYY-MM-DD)
            strike: Strike price
            quantity: Number of contracts
            limit_price: Limit price (premium to receive)
            duration: Order duration
        
        Returns:
            Order payload dictionary
        """
        return self.create_option_order(
            symbol=symbol,
            expiration=expiration,
            strike=strike,
            option_type="CALL",
            action="SELL_TO_OPEN",
            quantity=quantity,
            order_type="LIMIT",
            limit_price=limit_price,
            duration=duration
        )
    
    def create_collar_order(
        self,
        symbol: str,
        expiration: str,
        call_strike: float,
        put_strike: float,
        quantity: int,
        limit_price: float,
        duration: Literal["DAY", "GTC"] = "DAY"
    ) -> Dict[str, Any]:
        """
        Create a collar order (sell call + buy put for downside protection).
        This is a 2-leg order: SELL call, BUY put.
        
        Args:
            symbol: Underlying stock symbol
            expiration: Option expiration date (YYYY-MM-DD)
            call_strike: Strike price for short call
            put_strike: Strike price for long put
            quantity: Number of contracts
            limit_price: Net credit/debit limit (negative = debit, positive = credit)
            duration: Order duration
        
        Returns:
            Order payload dictionary
        """
        # Format expiration date
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")
        symbol_padded = f"{symbol:<6}"
        
        # Build option symbols
        call_symbol = f"{symbol_padded}{exp_str}C{int(call_strike * 1000):08d}"
        put_symbol = f"{symbol_padded}{exp_str}P{int(put_strike * 1000):08d}"
        
        # Build multi-leg order
        order = {
            "orderType": "NET_CREDIT" if limit_price >= 0 else "NET_DEBIT",
            "session": "NORMAL",
            "duration": duration,
            "orderStrategyType": "SINGLE",
            "price": abs(limit_price),
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": call_symbol,
                        "assetType": "OPTION"
                    }
                },
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": put_symbol,
                        "assetType": "OPTION"
                    }
                }
            ]
        }
        
        return order
    
    def create_iron_condor_order(
        self,
        symbol: str,
        expiration: str,
        long_put_strike: float,
        short_put_strike: float,
        short_call_strike: float,
        long_call_strike: float,
        quantity: int,
        limit_price: float,
        duration: Literal["DAY", "GTC"] = "DAY"
    ) -> Dict[str, Any]:
        """
        Create an iron condor order (4-leg credit spread).
        This is a 4-leg order: BUY lower put, SELL higher put, SELL lower call, BUY higher call.
        
        Args:
            symbol: Underlying stock symbol
            expiration: Option expiration date (YYYY-MM-DD)
            long_put_strike: Strike for long (buy) put (lowest strike)
            short_put_strike: Strike for short (sell) put
            short_call_strike: Strike for short (sell) call
            long_call_strike: Strike for long (buy) call (highest strike)
            quantity: Number of contracts
            limit_price: Net credit limit (should be positive)
            duration: Order duration
        
        Returns:
            Order payload dictionary
        """
        # Format expiration date
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")
        symbol_padded = f"{symbol:<6}"
        
        # Build option symbols for all 4 legs
        long_put_symbol = f"{symbol_padded}{exp_str}P{int(long_put_strike * 1000):08d}"
        short_put_symbol = f"{symbol_padded}{exp_str}P{int(short_put_strike * 1000):08d}"
        short_call_symbol = f"{symbol_padded}{exp_str}C{int(short_call_strike * 1000):08d}"
        long_call_symbol = f"{symbol_padded}{exp_str}C{int(long_call_strike * 1000):08d}"
        
        # Build 4-leg order
        order = {
            "orderType": "NET_CREDIT",
            "session": "NORMAL",
            "duration": duration,
            "orderStrategyType": "SINGLE",
            "price": limit_price,
            "orderLegCollection": [
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": long_put_symbol,
                        "assetType": "OPTION"
                    }
                },
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": short_put_symbol,
                        "assetType": "OPTION"
                    }
                },
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": short_call_symbol,
                        "assetType": "OPTION"
                    }
                },
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": long_call_symbol,
                        "assetType": "OPTION"
                    }
                }
            ]
        }
        
        return order
    
    def create_iron_condor_exit_order(
        self,
        symbol: str,
        expiration: str,
        long_put_strike: float,
        short_put_strike: float,
        short_call_strike: float,
        long_call_strike: float,
        quantity: int,
        limit_price: float,
        duration: Literal["DAY", "GTC"] = "GTC"
    ) -> Dict[str, Any]:
        """
        Create an iron condor EXIT order (4-leg closing order).
        This closes an existing iron condor position by reversing all legs.
        
        Entry was: BUY lower put, SELL higher put, SELL lower call, BUY higher call (net credit)
        Exit is: SELL lower put, BUY higher put, BUY lower call, SELL higher call (net debit)
        
        Args:
            symbol: Underlying stock symbol
            expiration: Option expiration date (YYYY-MM-DD)
            long_put_strike: Strike for the put that was bought (lowest strike)
            short_put_strike: Strike for the put that was sold
            short_call_strike: Strike for the call that was sold
            long_call_strike: Strike for the call that was bought (highest strike)
            quantity: Number of contracts
            limit_price: Max net debit willing to pay to close (should be less than entry credit)
            duration: Order duration (recommend GTC for set-and-forget)
        
        Returns:
            Order payload dictionary
        """
        # Format expiration date
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")
        symbol_padded = f"{symbol:<6}"
        
        # Build option symbols for all 4 legs
        long_put_symbol = f"{symbol_padded}{exp_str}P{int(long_put_strike * 1000):08d}"
        short_put_symbol = f"{symbol_padded}{exp_str}P{int(short_put_strike * 1000):08d}"
        short_call_symbol = f"{symbol_padded}{exp_str}C{int(short_call_strike * 1000):08d}"
        long_call_symbol = f"{symbol_padded}{exp_str}C{int(long_call_strike * 1000):08d}"
        
        # Build 4-leg EXIT order (reverse all instructions from entry)
        order = {
            "orderType": "NET_DEBIT",
            "session": "NORMAL",
            "duration": duration,
            "orderStrategyType": "SINGLE",
            "price": limit_price,
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_CLOSE",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": long_put_symbol,
                        "assetType": "OPTION"
                    }
                },
                {
                    "instruction": "BUY_TO_CLOSE",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": short_put_symbol,
                        "assetType": "OPTION"
                    }
                },
                {
                    "instruction": "BUY_TO_CLOSE",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": short_call_symbol,
                        "assetType": "OPTION"
                    }
                },
                {
                    "instruction": "SELL_TO_CLOSE",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": long_call_symbol,
                        "assetType": "OPTION"
                    }
                }
            ]
        }
        
        return order
    
    def create_bull_put_spread_order(
        self,
        symbol: str,
        expiration: str,
        sell_strike: float,
        buy_strike: float,
        quantity: int,
        limit_price: float,
        duration: Literal["DAY", "GTC"] = "DAY"
    ) -> Dict[str, Any]:
        """
        Create a bull put spread order (2-leg vertical credit spread).
        This is a bullish strategy: SELL higher strike put + BUY lower strike put = NET CREDIT.
        
        Max profit = net credit received
        Max loss = (sell_strike - buy_strike) - net_credit
        Breakeven = sell_strike - net_credit
        
        Args:
            symbol: Underlying stock symbol
            expiration: Option expiration date (YYYY-MM-DD)
            sell_strike: Strike for short (sell) put (higher strike)
            buy_strike: Strike for long (buy) put (lower strike, protection)
            quantity: Number of contracts
            limit_price: Net credit limit (should be positive)
            duration: Order duration
        
        Returns:
            Order payload dictionary
        """
        # Format expiration date
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")
        symbol_padded = f"{symbol:<6}"
        
        # Build option symbols for both legs
        # Format: SYMBOL  YYMMDDPTXXXXXXXX (6 char symbol, date, P/C, 8-digit strike in cents)
        sell_put_symbol = f"{symbol_padded}{exp_str}P{int(sell_strike * 1000):08d}"
        buy_put_symbol = f"{symbol_padded}{exp_str}P{int(buy_strike * 1000):08d}"
        
        # Build 2-leg order (vertical spread)
        order = {
            "orderType": "NET_CREDIT",
            "session": "NORMAL",
            "duration": duration,
            "orderStrategyType": "SINGLE",
            "price": limit_price,
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": sell_put_symbol,
                        "assetType": "OPTION"
                    }
                },
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": buy_put_symbol,
                        "assetType": "OPTION"
                    }
                }
            ]
        }
        
        return order
    
    def create_bull_put_spread_exit_order(
        self,
        symbol: str,
        expiration: str,
        sell_strike: float,
        buy_strike: float,
        quantity: int,
        limit_price: float,
        duration: Literal["DAY", "GTC"] = "GTC"
    ) -> Dict[str, Any]:
        """
        Create a bull put spread EXIT order (2-leg closing order).
        This closes an existing bull put spread by reversing both legs.
        
        Entry was: SELL higher put, BUY lower put (net credit)
        Exit is: BUY higher put, SELL lower put (net debit)
        
        Args:
            symbol: Underlying stock symbol
            expiration: Option expiration date (YYYY-MM-DD)
            sell_strike: Strike for the put that was sold
            buy_strike: Strike for the put that was bought
            quantity: Number of contracts
            limit_price: Max net debit willing to pay to close (should be less than entry credit for profit)
            duration: Order duration (recommend GTC for set-and-forget)
        
        Returns:
            Order payload dictionary
        """
        # Format expiration date
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")
        symbol_padded = f"{symbol:<6}"
        
        # Build option symbols for both legs
        sell_put_symbol = f"{symbol_padded}{exp_str}P{int(sell_strike * 1000):08d}"
        buy_put_symbol = f"{symbol_padded}{exp_str}P{int(buy_strike * 1000):08d}"
        
        # Build 2-leg EXIT order (reverse both instructions from entry)
        order = {
            "orderType": "NET_DEBIT",
            "session": "NORMAL",
            "duration": duration,
            "orderStrategyType": "SINGLE",
            "price": limit_price,
            "orderLegCollection": [
                {
                    "instruction": "BUY_TO_CLOSE",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": sell_put_symbol,
                        "assetType": "OPTION"
                    }
                },
                {
                    "instruction": "SELL_TO_CLOSE",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": buy_put_symbol,
                        "assetType": "OPTION"
                    }
                }
            ]
        }
        
        return order
    
    def create_bear_call_spread_order(
        self,
        symbol: str,
        expiration: str,
        sell_strike: float,
        buy_strike: float,
        quantity: int,
        limit_price: float,
        duration: Literal["DAY", "GTC"] = "DAY"
    ) -> Dict[str, Any]:
        """
        Create a bear call spread order (2-leg vertical credit spread).
        This is a bearish strategy: SELL lower strike call + BUY higher strike call = NET CREDIT.
        
        Max profit = net credit received
        Max loss = (buy_strike - sell_strike) - net_credit
        Breakeven = sell_strike + net_credit
        
        Args:
            symbol: Underlying stock symbol
            expiration: Option expiration date (YYYY-MM-DD)
            sell_strike: Strike for short (sell) call (lower strike)
            buy_strike: Strike for long (buy) call (higher strike, protection)
            quantity: Number of contracts
            limit_price: Net credit limit (should be positive)
            duration: Order duration
        
        Returns:
            Order payload dictionary
        """
        # Format expiration date
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")
        symbol_padded = f"{symbol:<6}"
        
        # Build option symbols for both legs
        sell_call_symbol = f"{symbol_padded}{exp_str}C{int(sell_strike * 1000):08d}"
        buy_call_symbol = f"{symbol_padded}{exp_str}C{int(buy_strike * 1000):08d}"
        
        # Build 2-leg order (vertical spread)
        order = {
            "orderType": "NET_CREDIT",
            "session": "NORMAL",
            "duration": duration,
            "orderStrategyType": "SINGLE",
            "price": limit_price,
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": sell_call_symbol,
                        "assetType": "OPTION"
                    }
                },
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": buy_call_symbol,
                        "assetType": "OPTION"
                    }
                }
            ]
        }
        
        return order
    
    def create_bear_call_spread_exit_order(
        self,
        symbol: str,
        expiration: str,
        sell_strike: float,
        buy_strike: float,
        quantity: int,
        limit_price: float,
        duration: Literal["DAY", "GTC"] = "GTC"
    ) -> Dict[str, Any]:
        """
        Create a bear call spread EXIT order (2-leg closing order).
        This closes an existing bear call spread by reversing both legs.
        
        Entry was: SELL lower call, BUY higher call (net credit)
        Exit is: BUY lower call, SELL higher call (net debit)
        
        Args:
            symbol: Underlying stock symbol
            expiration: Option expiration date (YYYY-MM-DD)
            sell_strike: Strike for the call that was sold
            buy_strike: Strike for the call that was bought
            quantity: Number of contracts
            limit_price: Max net debit willing to pay to close (should be less than entry credit for profit)
            duration: Order duration (recommend GTC for set-and-forget)
        
        Returns:
            Order payload dictionary
        """
        # Format expiration date
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")
        symbol_padded = f"{symbol:<6}"
        
        # Build option symbols for both legs
        sell_call_symbol = f"{symbol_padded}{exp_str}C{int(sell_strike * 1000):08d}"
        buy_call_symbol = f"{symbol_padded}{exp_str}C{int(buy_strike * 1000):08d}"
        
        # Build 2-leg EXIT order (reverse both instructions from entry)
        order = {
            "orderType": "NET_DEBIT",
            "session": "NORMAL",
            "duration": duration,
            "orderStrategyType": "SINGLE",
            "price": limit_price,
            "orderLegCollection": [
                {
                    "instruction": "BUY_TO_CLOSE",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": sell_call_symbol,
                        "assetType": "OPTION"
                    }
                },
                {
                    "instruction": "SELL_TO_CLOSE",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": buy_call_symbol,
                        "assetType": "OPTION"
                    }
                }
            ]
        }
        
        return order
    
    def export_order(
        self,
        order: Dict[str, Any],
        strategy_type: str = "option",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Export order payload to a JSON file.
        
        Args:
            order: Order payload dictionary
            strategy_type: Type of strategy (csp, covered_call, etc.)
            metadata: Additional metadata to include in export
        
        Returns:
            Path to exported file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        symbol = "UNKNOWN"
        
        # Try to extract symbol from order
        if "orderLegCollection" in order and len(order["orderLegCollection"]) > 0:
            opt_symbol = order["orderLegCollection"][0]["instrument"]["symbol"]
            symbol = opt_symbol.split("_")[0] if "_" in opt_symbol else opt_symbol
        
        filename = f"{strategy_type}_{symbol}_{timestamp}.json"
        filepath = self.export_dir / filename
        
        # Build export data
        export_data = {
            "timestamp": datetime.now().isoformat(),
            "account_id": self.account_id,
            "strategy_type": strategy_type,
            "order": order,
            "metadata": metadata or {},
            "status": "DRY_RUN" if self.dry_run else "READY_TO_SEND"
        }
        
        # Write to file
        with open(filepath, "w") as f:
            json.dump(export_data, f, indent=2)
        
        return str(filepath)
    
    def submit_order(
        self,
        order: Dict[str, Any],
        strategy_type: str = "option",
        metadata: Optional[Dict[str, Any]] = None,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Submit order to Schwab API or export to file in dry-run mode.
        
        SAFETY MECHANISM: Orders must be previewed before execution.
        This prevents accidental live trades without review.
        
        Args:
            order: Order payload dictionary
            strategy_type: Type of strategy
            metadata: Additional metadata
            account_id: Account hash value (uses self.account_id if not provided)
        
        Returns:
            Response dictionary with status and details
            
        Raises:
            RuntimeError: If order not previewed or client not available
        """
        if self.dry_run:
            # Export to file instead of submitting
            filepath = self.export_order(order, strategy_type, metadata)
            return {
                "status": "exported",
                "filepath": filepath,
                "message": f"Order exported to {filepath} (DRY RUN)",
                "order": order
            }
        
        # LIVE TRADING MODE - Enforce safety checks
        
        # Safety Check 1: Order must be previewed first
        if not self._is_previewed(order):
            order_hash = self._compute_order_hash(order)
            raise RuntimeError(
                "SAFETY CHECK FAILED: Order must be previewed before execution.\n"
                f"Order hash: {order_hash}\n"
                "Call trader.preview_order(order) first, review the preview, "
                "then call trader.submit_order(order) within 30 minutes."
            )
        
        # Safety Check 2: Client must be available
        if not self.client:
            raise RuntimeError(
                "Schwab API client required for live trading. "
                "Initialize SchwabTrader with a client instance."
            )
        
        # Safety Check 3: Account ID must be provided
        acct_id = account_id or self.account_id
        if not acct_id:
            raise RuntimeError(
                "Account ID required for live trading. "
                "Set SCHWAB_ACCOUNT_ID or pass account_id parameter."
            )
        
        # Safety Check 4: Validate order structure
        validation = self.validate_order(order)
        if not validation['valid']:
            raise RuntimeError(
                f"Order validation failed:\n" + 
                "\n".join(f"  - {err}" for err in validation['errors'])
            )
        
        try:
            # Submit order via Schwab API
            schwab_client = self.client.client if hasattr(self.client, 'client') else self.client
            response = schwab_client.place_order(acct_id, order)
            
            # Parse response
            order_data = response.json() if hasattr(response, 'json') else response
            
            # Extract order ID from response
            # Schwab typically returns order ID in Location header or response body
            order_id = None
            if hasattr(response, 'headers') and 'Location' in response.headers:
                # Extract order ID from Location header
                # Format: https://api.schwabapi.com/trader/v1/accounts/{accountId}/orders/{orderId}
                location = response.headers['Location']
                order_id = location.split('/')[-1] if '/' in location else None
            elif isinstance(order_data, dict) and 'orderId' in order_data:
                order_id = order_data['orderId']
            
            # Clear preview cache after successful submission
            self._clear_preview(order)
            
            # Save execution record to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.export_dir / f"order_executed_{timestamp}.json"
            
            with open(filepath, "w") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "account_id": acct_id,
                    "order_id": order_id,
                    "strategy_type": strategy_type,
                    "order": order,
                    "metadata": metadata or {},
                    "response": order_data,
                    "status": "LIVE_TRADE_EXECUTED"
                }, f, indent=2)
            
            return {
                "status": "executed",
                "order_id": order_id,
                "response": order_data,
                "filepath": str(filepath),
                "message": f"✅ Order executed successfully. Order ID: {order_id}"
            }
        
        except Exception as e:
            # Save error details
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.export_dir / f"order_error_{timestamp}.json"
            
            with open(filepath, "w") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "account_id": acct_id,
                    "strategy_type": strategy_type,
                    "order": order,
                    "metadata": metadata or {},
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "status": "EXECUTION_FAILED"
                }, f, indent=2)
            
            raise RuntimeError(f"Failed to execute order: {e}")
    
    def validate_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate order payload before submission.
        
        Args:
            order: Order payload dictionary
        
        Returns:
            Validation result with any errors/warnings
        """
        errors = []
        warnings = []
        
        # Check required fields
        required_fields = ["orderType", "session", "duration", "orderLegCollection"]
        for field in required_fields:
            if field not in order:
                errors.append(f"Missing required field: {field}")
        
        # Check order legs
        if "orderLegCollection" in order:
            if len(order["orderLegCollection"]) == 0:
                errors.append("Order must have at least one leg")
            
            for i, leg in enumerate(order["orderLegCollection"]):
                if "instruction" not in leg:
                    errors.append(f"Leg {i}: Missing instruction")
                if "quantity" not in leg or leg["quantity"] <= 0:
                    errors.append(f"Leg {i}: Invalid quantity")
                if "instrument" not in leg:
                    errors.append(f"Leg {i}: Missing instrument")
        
        # Check prices for limit orders
        if order.get("orderType") == "LIMIT" and "price" not in order:
            errors.append("LIMIT order must have a price")
        
        # Warnings
        if order.get("duration") == "GTC":
            warnings.append("GTC orders remain active until filled or cancelled")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }


def format_order_summary(order: Dict[str, Any]) -> str:
    """
    Create a human-readable summary of an order.
    
    Args:
        order: Order payload dictionary
    
    Returns:
        Formatted order summary string
    """
    lines = []
    lines.append(f"Order Type: {order.get('orderType', 'N/A')}")
    lines.append(f"Duration: {order.get('duration', 'N/A')}")
    lines.append(f"Session: {order.get('session', 'N/A')}")
    
    if "price" in order:
        lines.append(f"Limit Price: ${order['price']:.2f}")
    if "stopPrice" in order:
        lines.append(f"Stop Price: ${order['stopPrice']:.2f}")
    
    lines.append("\nOrder Legs:")
    for i, leg in enumerate(order.get("orderLegCollection", []), 1):
        lines.append(f"  Leg {i}:")
        lines.append(f"    Action: {leg.get('instruction', 'N/A')}")
        lines.append(f"    Quantity: {leg.get('quantity', 0)}")
        if "instrument" in leg:
            lines.append(f"    Symbol: {leg['instrument'].get('symbol', 'N/A')}")
            lines.append(f"    Type: {leg['instrument'].get('assetType', 'N/A')}")
    
    return "\n".join(lines)
