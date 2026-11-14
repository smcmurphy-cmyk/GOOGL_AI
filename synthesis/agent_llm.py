import os
from google import genai
from google.genai import types
from models.alerts import ScoredPlay
from models.regime import RegimeState
from config.settings import config

def generate_trade_thesis(ticker: str, regime: RegimeState, play: ScoredPlay) -> str:
    """
    Leverages the Google GenAI SDK to synthesize a 1-2 sentence quantitative thesis 
    based on the structured multi-leg output of the Expectancy Scorer.
    """
    client = genai.Client(api_key=config.google_api_key)
    
    system_instruction = (
        "You are an expert quantitative options trading assistant. "
        "Your task is to write a concise, 1-2 sentence webhook alert summarizing a directional options trade. "
        "Explicitly state WHY the trade was selected by connecting the GEX regime to the chosen strikes and its defined risk-to-reward targets. "
        "Do not offer financial advice; maintain a strictly quantitative and professional tone."
    )
    
    strategy = play.structure.strategy_type.replace('_', ' ').title()
    
    # Safely extract legs from the structure list
    short_leg = next((leg for leg in play.structure.legs if leg.action == "SELL"), None)
    long_leg = next((leg for leg in play.structure.legs if leg.action == "BUY"), None)
    
    strikes_str = f"Short {short_leg.contract.strike if short_leg else 'N/A'} / Long {long_leg.contract.strike if long_leg else 'N/A'}"
    
    target_exit = play.exits.profit_target_pct if play.exits else 0.50
    stop_loss = play.exits.stop_loss_pct if play.exits else 1.00
    invalidation = play.exits.invalidation_level if play.exits else 'N/A'
    
    prompt_payload = f"""
    Ticker: {ticker}
    Macro Regime: {regime.regime_type} (Net GEX: ${regime.net_gex:,.0f})
    Structure: {strategy}
    Strikes: {strikes_str}
    Entry Premium: ${play.structure.net_premium:.2f}
    Max Risk: ${play.structure.max_risk:.2f}
    Target Exit (Pct of Max Profit): {target_exit * 100}%
    Stop Loss (Pct of Max Risk): {stop_loss * 100}%
    Invalidation Level: {invalidation}
    Mathematical Expectancy Score: {play.expectancy_score:.2f}
    
    Generate the alert thesis now.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=prompt_payload,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.1,  
            )
        )
        return response.text.strip()
    except Exception as e:
        return f"System alert generated for {ticker} {strategy} based on {regime.regime_type} metrics. (LLM synthesis failed: {e})"