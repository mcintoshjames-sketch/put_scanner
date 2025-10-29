# schwab_trading.py - Schwab API trade execution
# Handles order creation and submission to Schwab brokerage accounts

from __future__ import annotations
import json
import os
from datetime import datetime
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
            
            # Save preview to file for reference
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.export_dir / f"order_preview_{timestamp}.json"
            
            with open(filepath, "w") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "account_id": acct_id,
                    "order": order,
                    "preview": preview_data
                }, f, indent=2)
            
            return {
                "status": "preview_success",
                "preview": preview_data,
                "filepath": str(filepath),
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
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Submit order to Schwab API or export to file in dry-run mode.
        
        Args:
            order: Order payload dictionary
            strategy_type: Type of strategy
            metadata: Additional metadata
        
        Returns:
            Response dictionary with status and details
        """
        if self.dry_run:
            # Export to file instead of submitting
            filepath = self.export_order(order, strategy_type, metadata)
            return {
                "status": "exported",
                "filepath": filepath,
                "message": f"Order exported to {filepath}",
                "order": order
            }
        else:
            # TODO: Implement live trading with Schwab API
            # This would use the schwab-py client to submit the order
            raise NotImplementedError(
                "Live trading not yet implemented. Use dry_run=True to export orders."
            )
    
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
