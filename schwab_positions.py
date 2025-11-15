"""Schwab API Positions Integration.

Retrieves option and stock positions from Schwab API and converts them
to portfolio manager Position objects with Greeks calculated.

Author: Options Strategy Lab
Created: 2025-11-15
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import logging

from portfolio_manager import Position
from options_math import call_delta, put_delta, option_gamma, option_vega, call_theta, put_theta

logger = logging.getLogger(__name__)


def fetch_schwab_positions(provider) -> Tuple[List[Position], Optional[str]]:
    """Fetch positions from Schwab API and convert to Position objects.
    
    Args:
        provider: Schwab provider instance (from providers/)
        
    Returns:
        Tuple of (positions_list, error_message)
        Returns ([], error_msg) if failed
    """
    try:
        # Get account numbers first
        account_numbers = provider.get_account_numbers()
        if not account_numbers or len(account_numbers) == 0:
            return [], "No Schwab accounts found"
        
        # Use first account's hash value
        account_hash = account_numbers[0].get('hashValue', '')
        if not account_hash:
            return [], "Account hash value not found"
        
        # Get account info with positions
        account_data = provider.get_account_info(account_id=account_hash)
        
        # Extract positions from account data
        positions_data = account_data.get('securitiesAccount', {}).get('positions', [])
        if not positions_data:
            logger.info("No positions found in Schwab account")
            return [], None  # Empty portfolio is valid
        
        positions = []
        errors = []
        
        for pos_data in positions_data:
            try:
                position = _parse_schwab_position(pos_data, account_hash, provider)
                if position:
                    positions.append(position)
            except Exception as e:
                symbol = pos_data.get('instrument', {}).get('symbol', 'Unknown')
                error_msg = f"Error parsing position {symbol}: {e}"
                logger.warning(error_msg)
                errors.append(error_msg)
        
        # Return positions with optional error summary
        error_summary = None
        if errors:
            error_summary = f"Loaded {len(positions)} positions with {len(errors)} errors"
        
        logger.info(f"Loaded {len(positions)} positions from Schwab account {account_hash[:8]}...")
        return positions, error_summary
        
    except Exception as e:
        error_msg = f"Failed to fetch Schwab positions: {e}"
        logger.error(error_msg)
        return [], error_msg


def _parse_schwab_position(pos_data: Dict, account_id: str, provider) -> Optional[Position]:
    """Parse a single Schwab position into a Position object.
    
    Args:
        pos_data: Position data from Schwab API
        account_id: Schwab account ID
        provider: Schwab provider for fetching quotes
        
    Returns:
        Position object or None if position should be skipped
    """
    instrument = pos_data.get('instrument', {})
    asset_type = instrument.get('assetType', '')
    symbol = instrument.get('symbol', '')
    
    if not symbol:
        logger.warning("Skipping position with no symbol")
        return None
    
    # Basic position data
    quantity = float(pos_data.get('longQuantity', 0)) - float(pos_data.get('shortQuantity', 0))
    if quantity == 0:
        return None  # Skip zero positions
    
    market_value = float(pos_data.get('marketValue', 0))
    average_price = float(pos_data.get('averagePrice', 0))
    
    # Calculate current price from market value and quantity
    # For options, market_value is already in dollars (not per-contract)
    if asset_type == 'OPTION':
        current_price = market_value / 100.0 if quantity != 0 else 0  # Convert to per-share price
    else:
        current_price = market_value / abs(quantity) if quantity != 0 else 0
    
    # Calculate P&L
    cost_basis = average_price * abs(quantity) * (100 if asset_type == 'OPTION' else 1)
    unrealized_pnl = market_value - (cost_basis * (1 if quantity > 0 else -1))
    
    retrieved_at = datetime.now(timezone.utc)
    
    # Handle stocks
    if asset_type == 'EQUITY':
        # For stocks, delta = 1.0 per share
        return Position(
            symbol=symbol,
            quantity=quantity,
            position_type='STOCK',
            strike=None,
            expiration=None,
            current_price=current_price,
            underlying_price=current_price,
            delta=1.0 * (1 if quantity > 0 else -1),
            gamma=0.0,
            vega=0.0,
            theta=0.0,
            market_value=market_value,
            cost_basis=cost_basis,
            unrealized_pnl=unrealized_pnl,
            account_id=account_id,
            retrieved_at=retrieved_at
        )
    
    # Handle options
    elif asset_type == 'OPTION':
        # Get underlying symbol from instrument
        underlying_symbol = instrument.get('underlyingSymbol', '')
        if not underlying_symbol:
            logger.warning(f"Option {symbol} missing underlying symbol")
            return None
        
        # Get option details from instrument (Schwab provides these directly)
        put_call = instrument.get('putCall', '')  # 'CALL' or 'PUT'
        position_type = put_call  # Use directly
        
        # Parse option details from symbol (format: "NVDA  251212C00260000")
        # Format: SYMBOL(spaces)YYMMDD(C/P)STRIKE(8 digits with 3 decimals)
        try:
            # Clean up symbol and split
            symbol_clean = symbol.strip()
            
            # Find the date part (6 digits YYMMDD)
            # It comes after the underlying symbol and spaces
            import re
            match = re.search(r'(\d{6})([CP])(\d{8})', symbol_clean)
            if not match:
                raise ValueError(f"Cannot parse option symbol format: {symbol}")
            
            exp_date_str = match.group(1)  # YYMMDD
            put_call_char = match.group(2)  # C or P
            strike_str = match.group(3)    # 8 digits
            
            # Parse expiration date
            exp_year = 2000 + int(exp_date_str[:2])
            exp_month = int(exp_date_str[2:4])
            exp_day = int(exp_date_str[4:6])
            expiration = f"{exp_year:04d}-{exp_month:02d}-{exp_day:02d}"
            
            # Parse strike (8 digits with 3 decimal places)
            strike = float(strike_str) / 1000.0
            
            # Verify position_type matches the symbol
            if not position_type:
                position_type = 'CALL' if put_call_char == 'C' else 'PUT'
            
        except Exception as e:
            logger.error(f"Failed to parse option symbol {symbol}: {e}")
            return None
        
        # Get underlying price
        underlying_price = 0.0
        try:
            quote = provider.get_quote(underlying_symbol)
            if quote:
                # Log what we received for debugging
                logger.info(f"Schwab quote for {underlying_symbol}: {list(quote.keys())[:10]}")
                
                # Schwab API returns nested structure - check for 'quote' key
                quote_data = quote.get('quote', quote)  # Use nested 'quote' if available
                
                # Try different possible keys for last price
                underlying_price = float(
                    quote_data.get('lastPrice') or 
                    quote_data.get('last') or 
                    quote_data.get('regularMarketPrice') or 
                    quote_data.get('mark') or 
                    quote_data.get('close') or
                    quote_data.get('previousClose') or
                    quote_data.get('closePrice') or
                    0
                )
                if underlying_price == 0:
                    # Log full quote for debugging
                    logger.error(f"Quote returned for {underlying_symbol} but no valid price.")
                    logger.error(f"Top-level keys: {list(quote.keys())}")
                    logger.error(f"quote_data keys: {list(quote_data.keys())}")
                    logger.error(f"quote_data sample: {dict(list(quote_data.items())[:5])}")
                else:
                    logger.info(f"✓ Got {underlying_symbol} underlying price: ${underlying_price:.2f}")
            else:
                logger.error(f"No quote returned for {underlying_symbol}")
        except Exception as e:
            logger.error(f"Error fetching quote for {underlying_symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # If we still don't have underlying price, DO NOT use strike as fallback
        # This causes incorrect VaR calculations
        if underlying_price == 0:
            logger.error(
                f"⚠️ CRITICAL: Cannot determine underlying price for {underlying_symbol}. "
                f"Strike=${strike} is NOT a valid substitute for VaR. "
                f"VaR calculation will be inaccurate. "
                f"Check Schwab API quote response or manually set underlying price."
            )
            # Still set to strike as absolute last resort, but log it clearly
            underlying_price = strike
        
        # Calculate Greeks
        delta, gamma, vega, theta = 0.0, 0.0, 0.0, 0.0
        if underlying_price > 0 and current_price > 0:
            try:
                # Calculate days to expiration
                exp_dt = datetime.strptime(expiration, '%Y-%m-%d')
                now_dt = datetime.now()
                dte = (exp_dt - now_dt).days
                
                logger.info(f"Calculating Greeks: S=${underlying_price:.2f}, K=${strike:.2f}, C=${current_price:.2f}, DTE={dte}")
                
                if dte > 0:
                    # Use implied volatility from option price or default
                    iv = 0.30  # Default 30% IV, could enhance by backing out IV
                    risk_free_rate = 0.05  # 5% default
                    
                    # Calculate time to expiration in years
                    T = dte / 365.0
                    
                    # Calculate Greeks using individual functions
                    if position_type == 'CALL':
                        delta = call_delta(underlying_price, strike, risk_free_rate, iv, T)
                        theta = call_theta(underlying_price, strike, risk_free_rate, iv, T)
                    else:
                        delta = put_delta(underlying_price, strike, risk_free_rate, iv, T)
                        theta = put_theta(underlying_price, strike, risk_free_rate, iv, T)
                    
                    # Gamma and Vega are same for calls and puts
                    gamma = option_gamma(underlying_price, strike, risk_free_rate, iv, T)
                    vega = option_vega(underlying_price, strike, risk_free_rate, iv, T)
                    
                    logger.info(f"Greeks calculated: delta={delta:.4f}, gamma={gamma:.4f}, vega={vega:.4f}, theta={theta:.4f}")
                else:
                    logger.warning(f"DTE={dte} is not positive, skipping Greeks calculation")
                    
            except Exception as e:
                logger.error(f"Error calculating Greeks for {symbol}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            logger.warning(f"Cannot calculate Greeks: underlying_price={underlying_price}, current_price={current_price}")
        
        return Position(
            symbol=underlying_symbol,  # Use underlying symbol
            quantity=quantity,
            position_type=position_type,
            strike=strike,
            expiration=expiration,
            current_price=current_price,
            underlying_price=underlying_price,
            delta=delta,
            gamma=gamma,
            vega=vega,
            theta=theta,
            market_value=market_value,
            cost_basis=cost_basis,
            unrealized_pnl=unrealized_pnl,
            account_id=account_id,
            retrieved_at=retrieved_at
        )
    
    else:
        logger.warning(f"Unsupported asset type: {asset_type} for {symbol}")
        return None


def get_mock_positions() -> List[Position]:
    """Create mock positions for testing without Schwab API.
    
    Returns:
        List of mock Position objects
    """
    now = datetime.now(timezone.utc)
    
    return [
        # Long stock position
        Position(
            symbol='AAPL',
            quantity=100,
            position_type='STOCK',
            current_price=180.00,
            underlying_price=180.00,
            delta=100.0,  # 100 shares * 1.0 delta
            gamma=0.0,
            vega=0.0,
            theta=0.0,
            market_value=18000.0,
            cost_basis=17000.0,
            unrealized_pnl=1000.0,
            account_id='MOCK',
            retrieved_at=now
        ),
        # Short put (CSP)
        Position(
            symbol='AAPL',
            quantity=-1,
            position_type='PUT',
            strike=175.0,
            expiration='2025-01-17',
            current_price=3.50,
            underlying_price=180.00,
            delta=0.30,  # Delta for OTM put
            gamma=0.05,
            vega=0.15,
            theta=-0.05,
            market_value=-350.0,
            cost_basis=-500.0,
            unrealized_pnl=150.0,
            account_id='MOCK',
            retrieved_at=now
        ),
        # Long call
        Position(
            symbol='MSFT',
            quantity=2,
            position_type='CALL',
            strike=400.0,
            expiration='2025-02-21',
            current_price=12.50,
            underlying_price=405.00,
            delta=0.60,
            gamma=0.03,
            vega=0.20,
            theta=-0.08,
            market_value=2500.0,
            cost_basis=2000.0,
            unrealized_pnl=500.0,
            account_id='MOCK',
            retrieved_at=now
        )
    ]
