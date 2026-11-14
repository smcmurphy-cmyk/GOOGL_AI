from typing import List
from models.structures import OptionStructure

def evaluate_and_rank(structures: List[OptionStructure]) -> List[OptionStructure]:
    """
    Evaluates and ranks generated options structures based on statistical expectancy.
    """
    if not structures:
        return []
        
    def calculate_expectancy(structure: OptionStructure) -> float:
        # Default to a 50% probability if delta-based PoP is missing
        pop = structure.probability_of_profit if structure.probability_of_profit is not None else 0.50
        
        reward = structure.net_premium
        risk = structure.max_risk
        
        # Mathematical Expectancy = (Win Probability * Reward) - (Loss Probability * Risk)
        expectancy = (pop * reward) - ((1.0 - pop) * risk)
        return expectancy

    # Sort structures by highest mathematical expectancy
    ranked_structures = sorted(structures, key=calculate_expectancy, reverse=True)
    
    return ranked_structures