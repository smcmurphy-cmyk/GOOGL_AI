from pydantic import BaseModel
from typing import List
from models.market_data import OptionContract

class Leg(BaseModel):
    contract: OptionContract
    action: str  # "BUY" or "SELL"
    ratio: int

class OptionStructure(BaseModel):
    strategy_type: str
    legs: List[Leg]
    net_premium: float  # Signed correctly in builder: Credit is positive, Debit is negative
    max_risk: float
    probability_of_profit: float

    # PHASE 2 FIX: Scale Greeks by 100 to represent true dollar-exposure per contract
    @property
    def net_delta(self) -> float:
        return sum(
            (leg.contract.delta * 100 * leg.ratio) if leg.action == "BUY" 
            else (-leg.contract.delta * 100 * leg.ratio) 
            for leg in self.legs if leg.contract.delta is not None
        )

    @property
    def net_theta(self) -> float:
        return sum(
            (leg.contract.theta * 100 * leg.ratio) if leg.action == "BUY" 
            else (-leg.contract.theta * 100 * leg.ratio) 
            for leg in self.legs if leg.contract.theta is not None
        )
        
    @property
    def net_gamma(self) -> float:
        return sum(
            (leg.contract.gamma * 100 * leg.ratio) if leg.action == "BUY" 
            else (-leg.contract.gamma * 100 * leg.ratio) 
            for leg in self.legs if leg.contract.gamma is not None
        )