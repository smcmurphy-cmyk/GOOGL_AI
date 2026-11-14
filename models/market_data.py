from pydantic import BaseModel, Field
from typing import List, Literal
from datetime import date

class UnderlyingQuote(BaseModel):
    ticker: str
    price: float
    timestamp: str

class OptionContract(BaseModel):
    ticker: str
    strike: float
    expiration: date
    option_type: Literal["call", "put"]
    
    # Pricing & Liquidity
    bid: float
    ask: float
    last_price: float = Field(default=0.0)
    volume: int
    open_interest: int
    
    # Greeks & Volatility
    implied_volatility: float
    delta: float
    gamma: float
    theta: float
    vega: float
    
    @property
    def mid_price(self) -> float:
        """Helper to quickly calculate the mid-price for spread construction."""
        return (self.bid + self.ask) / 2.0
        
    @property
    def spread_width(self) -> float:
        """Helper to evaluate liquidity."""
        return self.ask - self.bid

class OptionsChain(BaseModel):
    underlying: UnderlyingQuote
    contracts: List[OptionContract]