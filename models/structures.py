from pydantic import BaseModel, Field, computed_field
from typing import List, Optional
from models.market_data import OptionContract

class Leg(BaseModel):
    """
    Represents a single leg in any options strategy.
    """
    contract: OptionContract
    action: str  # "BUY" or "SELL"
    ratio: int = 1

class OptionStructure(BaseModel):
    """
    Universal model for single or multi-leg options structures.
    """
    strategy_type: str
    legs: List[Leg]
    net_premium: float
    max_risk: float
    probability_of_profit: Optional[float] = None
    contract_multiplier: int = Field(100, description="Standard options multiplier")

    @computed_field
    def r_multiple(self) -> float:
        if self.max_risk <= 0:
            return 0.0
        # For a credit spread, reward is the premium collected.
        # This is a proxy calculation that you can refine based on structure.
        return self.net_premium / self.max_risk

    @computed_field
    def net_delta(self) -> float:
        total_delta = 0.0
        for leg in self.legs:
            leg_delta = leg.contract.delta if leg.contract.delta else 0.0
            if leg.action == "BUY":
                total_delta += leg_delta * leg.ratio
            elif leg.action == "SELL":
                total_delta -= leg_delta * leg.ratio
        return total_delta

    @computed_field
    def net_theta(self) -> float:
        total_theta = 0.0
        for leg in self.legs:
            leg_theta = leg.contract.theta if leg.contract.theta else 0.0
            if leg.action == "BUY":
                total_theta += leg_theta * leg.ratio
            elif leg.action == "SELL":
                total_theta -= leg_theta * leg.ratio
        return total_theta