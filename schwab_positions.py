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
        # Get account info
        accounts = provider.get_accounts()
        if not accounts or len(accounts) == 0:
            return [], "No Schwab accounts found"
        
        # Use first account
        account = accounts[0]
        account_id = account.get('securitiesAccount', {}).get('accountNumber', 'Unknown')
        
        # Get positions
        positions_data = account.get('securitiesAccount', {}).get('positions', [])
        if not positions_data:
            logger.info("No positions found in Schwab account")
            return [], None  # Empty portfolio is valid
        
        positions = []
        errors = []
        
        for pos_data in positions_data:
            try:
                position = _parse_schwab_position(pos_data, account_id, provider)
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
        
        logger.info(f"Loaded {len(positions)} positions from Schwab account {account_id}")
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
    current_price = float(pos_data.get('currentDayProfitLoss', 0)) / quantity if quantity != 0 else 0
    
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
        option_deliverables = instrument.get('optionDeliverables', [])
        if not option_deliverables:
            logger.warning(f"Option {symbol} missing deliverables")
            return None
        
        deliverable = option_deliverables[0]
        underlying_symbol = deliverable.get('symbol', symbol.split('_')[0])
        
        # Parse option details from symbol (format: AAPL_120124C150)
        try:
            parts = symbol.split('_')
            if len(parts) != 2:
                raise ValueError(f"Invalid option symbol format: {symbol}")
            
            option_part = parts[1]
            # Parse date (MMDDYY)
            exp_date_str = option_part[:6]
            exp_month = int(exp_date_str[:2])
            exp_day = int(exp_date_str[2:4])
            exp_year = 2000 + int(exp_date_str[4:6])
            expiration = f"{exp_year:04d}-{exp_month:02d}-{exp_day:02d}"
            
            # Parse call/put and strike
            put_call = option_part[6]  # 'C' or 'P'
            strike = float(option_part[7:]) / 1000.0  # Strike in thousandths
            
            position_type = 'CALL' if put_call == 'C' else 'PUT'
            
        except Exception as e:
            logger.error(f"Failed to parse option symbol {symbol}: {e}")
            return None
        
        # Get underlying price
        try:
            quote = provider.get_quote(underlying_symbol)
            if not quote:
                logger.warning(f"Could not get quote for {underlying_symbol}")
                underlying_price = 0.0
            else:
                underlying_price = float(quote.get('lastPrice', 0))
        except Exception as e:
            logger.warning(f"Error fetching quote for {underlying_symbol}: {e}")
            underlying_price = 0.0
        
        # Calculate Greeks
        delta, gamma, vega, theta = 0.0, 0.0, 0.0, 0.0
        if underlying_price > 0 and current_price > 0:
            try:
                # Calculate days to expiration
                exp_dt = datetime.strptime(expiration, '%Y-%m-%d')
                now_dt = datetime.now()
                dte = (exp_dt - now_dt).days
                
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
                    
            except Exception as e:
                logger.warning(f"Error calculating Greeks for {symbol}: {e}")
        
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
