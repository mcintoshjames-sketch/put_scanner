"""Portfolio Manager - Track positions and aggregate risk metrics.

This module provides portfolio-level risk management by:
1. Retrieving positions from Schwab API
2. Calculating portfolio Greeks (Delta, Gamma, Vega, Theta)
3. Computing net exposure and concentration metrics
4. Tracking correlation between positions

Author: Options Strategy Lab
Created: 2025-11-15
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import logging

import pandas as pd
import numpy as np

# VaR calculations
try:
    from risk_metrics.var_calculator import VaRResult, calculate_portfolio_var
    VAR_AVAILABLE = True
except ImportError:
    VAR_AVAILABLE = False
    VaRResult = None  # type: ignore
    calculate_portfolio_var = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents a single option or stock position."""
    
    symbol: str
    quantity: float  # Positive for long, negative for short
    position_type: str  # 'STOCK', 'CALL', 'PUT'
    
    # Option-specific fields (None for stock)
    strike: Optional[float] = None
    expiration: Optional[str] = None  # YYYY-MM-DD format
    
    # Market data
    current_price: float = 0.0
    underlying_price: float = 0.0
    
    # Greeks (for options)
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    theta: float = 0.0
    
    # Position metrics
    market_value: float = 0.0
    cost_basis: float = 0.0
    unrealized_pnl: float = 0.0
    
    # Metadata
    account_id: str = ""
    retrieved_at: Optional[datetime] = None


@dataclass
class PortfolioMetrics:
    """Aggregated portfolio-level risk metrics."""
    
    # Greeks totals
    total_delta: float = 0.0
    total_gamma: float = 0.0
    total_vega: float = 0.0
    total_theta: float = 0.0
    
    # Exposure metrics
    net_market_value: float = 0.0
    gross_market_value: float = 0.0
    long_exposure: float = 0.0
    short_exposure: float = 0.0
    
    # Concentration metrics
    max_position_pct: float = 0.0
    max_sector_pct: float = 0.0
    num_positions: int = 0
    num_underlyings: int = 0
    
    # Strategy breakdown
    strategy_counts: Optional[Dict[str, int]] = None
    
    # Risk metrics
    portfolio_beta: float = 1.0
    correlation_score: float = 0.0
    
    def __post_init__(self):
        if self.strategy_counts is None:
            self.strategy_counts = {}


class PortfolioManager:
    """Manages portfolio positions and calculates aggregate risk metrics."""
    
    def __init__(self):
        self.positions: List[Position] = []
        self.metrics: Optional[PortfolioMetrics] = None
        self.last_refresh: Optional[datetime] = None
        
    def load_positions(self, positions: List[Position]) -> None:
        """Load positions into the manager.
        
        Args:
            positions: List of Position objects
        """
        self.positions = positions
        self.last_refresh = datetime.now(timezone.utc)
        self._calculate_metrics()
        
    def _calculate_metrics(self) -> None:
        """Calculate aggregate portfolio metrics from current positions."""
        if not self.positions:
            self.metrics = PortfolioMetrics()
            return
            
        metrics = PortfolioMetrics()
        
        # Aggregate Greeks
        for pos in self.positions:
            # Multiply by quantity (negative for short positions)
            metrics.total_delta += pos.delta * pos.quantity
            metrics.total_gamma += pos.gamma * pos.quantity
            metrics.total_vega += pos.vega * pos.quantity
            metrics.total_theta += pos.theta * pos.quantity
            
            # Market value (absolute for gross, signed for net)
            metrics.net_market_value += pos.market_value
            metrics.gross_market_value += abs(pos.market_value)
            
            if pos.market_value > 0:
                metrics.long_exposure += pos.market_value
            else:
                metrics.short_exposure += abs(pos.market_value)
        
        # Count positions and underlyings
        metrics.num_positions = len(self.positions)
        underlyings = set(pos.symbol for pos in self.positions)
        metrics.num_underlyings = len(underlyings)
        
        # Calculate concentration
        if metrics.gross_market_value > 0:
            max_position_value = max(abs(pos.market_value) for pos in self.positions)
            metrics.max_position_pct = (max_position_value / metrics.gross_market_value) * 100.0
        
        # Strategy counts
        strategy_counts = {}
        for pos in self.positions:
            if pos.position_type == 'STOCK':
                strategy = 'STOCK'
            elif pos.quantity > 0:
                strategy = f'LONG_{pos.position_type}'
            else:
                strategy = f'SHORT_{pos.position_type}'
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        metrics.strategy_counts = strategy_counts
        
        self.metrics = metrics
        
    def get_positions_df(self) -> pd.DataFrame:
        """Return positions as a DataFrame for display.
        
        Returns:
            DataFrame with position details
        """
        if not self.positions:
            return pd.DataFrame()
            
        data = []
        for pos in self.positions:
            row = {
                'Symbol': pos.symbol,
                'Type': pos.position_type,
                'Qty': pos.quantity,
                'Strike': pos.strike if pos.strike else '-',
                'Exp': pos.expiration if pos.expiration else '-',
                'Price': f'${pos.current_price:.2f}',
                'Value': f'${pos.market_value:,.2f}',
                'P&L': f'${pos.unrealized_pnl:,.2f}',
                'Delta': f'{pos.delta * pos.quantity:.2f}',
                'Gamma': f'{pos.gamma * pos.quantity:.4f}',
                'Vega': f'{pos.vega * pos.quantity:.2f}',
                'Theta': f'{pos.theta * pos.quantity:.2f}',
            }
            data.append(row)
            
        return pd.DataFrame(data)
    
    def get_metrics_summary(self) -> Dict[str, str]:
        """Return portfolio metrics as a dictionary for display.
        
        Returns:
            Dictionary with formatted metrics
        """
        if not self.metrics:
            return {}  # type: ignore
            
        return {
            'Total Delta': f'{self.metrics.total_delta:.2f}',
            'Total Gamma': f'{self.metrics.total_gamma:.4f}',
            'Total Vega': f'{self.metrics.total_vega:.2f}',
            'Total Theta': f'{self.metrics.total_theta:.2f}',
            'Net Value': f'${self.metrics.net_market_value:,.2f}',
            'Gross Exposure': f'${self.metrics.gross_market_value:,.2f}',
            'Long Exposure': f'${self.metrics.long_exposure:,.2f}',
            'Short Exposure': f'${self.metrics.short_exposure:,.2f}',
            'Positions': str(self.metrics.num_positions),
            'Underlyings': str(self.metrics.num_underlyings),
            'Max Position %': f'{self.metrics.max_position_pct:.1f}%',
        }
    
    def get_greeks_by_underlying(self) -> pd.DataFrame:
        """Aggregate Greeks by underlying symbol.
        
        Returns:
            DataFrame with Greeks summed by underlying
        """
        if not self.positions:
            return pd.DataFrame()
            
        greeks_by_symbol = {}
        
        for pos in self.positions:
            if pos.symbol not in greeks_by_symbol:
                greeks_by_symbol[pos.symbol] = {
                    'Delta': 0.0,
                    'Gamma': 0.0,
                    'Vega': 0.0,
                    'Theta': 0.0,
                    'Value': 0.0,
                    'Positions': 0
                }
            
            greeks_by_symbol[pos.symbol]['Delta'] += pos.delta * pos.quantity
            greeks_by_symbol[pos.symbol]['Gamma'] += pos.gamma * pos.quantity
            greeks_by_symbol[pos.symbol]['Vega'] += pos.vega * pos.quantity
            greeks_by_symbol[pos.symbol]['Theta'] += pos.theta * pos.quantity
            greeks_by_symbol[pos.symbol]['Value'] += pos.market_value
            greeks_by_symbol[pos.symbol]['Positions'] += 1
        
        # Convert to DataFrame
        data = []
        for symbol, metrics in greeks_by_symbol.items():
            data.append({
                'Symbol': symbol,
                'Positions': metrics['Positions'],
                'Delta': f"{metrics['Delta']:.2f}",
                'Gamma': f"{metrics['Gamma']:.4f}",
                'Vega': f"{metrics['Vega']:.2f}",
                'Theta': f"{metrics['Theta']:.2f}",
                'Value': f"${metrics['Value']:,.2f}"
            })
        
        df = pd.DataFrame(data)
        if not df.empty:
            # Sort by absolute value
            df['_abs_value'] = df['Value'].str.replace('$', '').str.replace(',', '').astype(float).abs()
            df = df.sort_values('_abs_value', ascending=False).drop('_abs_value', axis=1)
        
        return df
    
    def check_risk_alerts(self) -> List[str]:
        """Check for risk concentration alerts.
        
        Returns:
            List of alert messages
        """
        alerts = []
        
        if not self.metrics:
            return alerts
        
        # Delta imbalance
        if abs(self.metrics.total_delta) > 100:
            direction = "bullish" if self.metrics.total_delta > 0 else "bearish"
            alerts.append(f"⚠️ High portfolio delta ({self.metrics.total_delta:.0f}) - {direction} bias")
        
        # High Gamma
        if abs(self.metrics.total_gamma) > 5.0:
            alerts.append(f"⚠️ High gamma exposure ({self.metrics.total_gamma:.2f}) - position sensitive to price moves")
        
        # Position concentration
        if self.metrics.max_position_pct > 30:
            alerts.append(f"⚠️ Single position represents {self.metrics.max_position_pct:.1f}% of portfolio")
        
        # Limited diversification
        if self.metrics.num_underlyings < 5 and self.metrics.num_positions > 5:
            alerts.append(f"⚠️ Only {self.metrics.num_underlyings} underlyings for {self.metrics.num_positions} positions")
        
        return alerts
    
    def calculate_var(
        self,
        historical_prices: Optional[pd.DataFrame] = None,
        confidence_level: float = 0.95,
        time_horizon_days: int = 1,
        method: str = 'historical'
    ) -> Optional[VaRResult]:
        """Calculate portfolio Value at Risk.
        
        Args:
            historical_prices: DataFrame with columns=symbols, index=dates
            confidence_level: Confidence level (0.90, 0.95, or 0.99)
            time_horizon_days: Time horizon in days (typically 1 or 10)
            method: 'parametric' or 'historical'
            
        Returns:
            VaRResult or None if VaR calculation unavailable
        """
        if not VAR_AVAILABLE:
            logger.warning("VaR calculation not available - risk_metrics package not imported")
            return None
            
        if not self.positions:
            return None
        
        if historical_prices is None or historical_prices.empty:
            logger.warning("No historical price data provided for VaR calculation")
            return None
        
        # Convert positions to dict format for var_calculator
        positions_data = []
        for pos in self.positions:
            positions_data.append({
                'symbol': pos.symbol,
                'quantity': pos.quantity,
                'current_price': pos.current_price if pos.position_type == 'STOCK' else pos.underlying_price,
                'position_type': pos.position_type
            })
        
        try:
            var_result = calculate_portfolio_var(  # type: ignore
                positions=positions_data,
                historical_prices=historical_prices,
                confidence_level=confidence_level,
                time_horizon_days=time_horizon_days,
                method=method
            )
            return var_result
        except Exception as e:
            logger.error(f"VaR calculation failed: {e}")
            return None


# Global portfolio manager instance
_portfolio_manager = PortfolioManager()


def get_portfolio_manager() -> PortfolioManager:
    """Get the global portfolio manager instance.
    
    Returns:
        PortfolioManager singleton
    """
    return _portfolio_manager
