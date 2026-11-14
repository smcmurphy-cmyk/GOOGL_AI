import asyncio
from config.settings import config

# Import pipeline states
from data_ingestion.schwab_fetcher import get_live_market_data as get_schwab_data, get_valid_access_token
from data_ingestion.cboe_fetcher import get_market_data as get_cboe_data
from core_logic.regime_classifier import classify_regime
from core_logic.structure_builder import generate_structures
from core_logic.expectancy_scorer import evaluate_and_rank
from core_logic.portfolio_risk import portfolio_gatekeeper
from synthesis.agent_llm import generate_trade_thesis
from dissemination.sheet_webhook import post_to_sheet

# FIX: Import the new yfinance volatility module
from utils.volatility import get_real_iv_rank

# Hardcoded for the test run. Later, move this to config/universe.py
MEGA_CAP_TICKERS = ["TSLA", "QQQ", "SPY"]

async def run_pipeline(ticker: str, session_open_risk_usd: float, access_token: str = None):
    print(f"\n--- Starting Pipeline for {ticker} ---")
    print("[1/6] Ingesting Market Data...")
    
    # 1. Route the data ingestion
    if config.use_live_schwab_data:
        chain = await get_schwab_data(ticker, access_token=access_token) 
    else:
        print("  [Data] Using delayed CBOE feed (Weekend/Testing mode)...")
        chain = get_cboe_data(ticker)
        
    if not chain or not chain.contracts:
        return session_open_risk_usd
    
    # FIX: Corrected indentation
    live_iv_rank = get_real_iv_rank(ticker)

    print("[2/6] Classifying Macro Regime...")
    
    regime = classify_regime(chain, live_iv_rank)
    print(f"      -> {regime.regime_type} (GEX: ${regime.net_gex:,.0f})") 

    if not regime.is_tradeable:
        print(f"[-] {ticker} regime is UNCERTAIN. Skipping.") 
        return session_open_risk_usd 

    # STATE 3: STRUCTURE GENERATION
    print("[3/6] Generating Defined-Risk Structures...")
    structures = generate_structures(chain, regime)
    if not structures:
        print(f"[-] No valid structures found for {ticker} in current regime.")
        return session_open_risk_usd 

    # STATE 4: EXPECTANCY SCORING
    print(f"[4/6] Scoring Expectancy on {len(structures)} candidate structures...")
    
    # FIX: Passed regime and ticker into the upgraded scorer
    scored_plays = evaluate_and_rank(structures, regime, ticker, account_balance=10000.0)
    
    if not scored_plays:
        print("[-] No structures passed the strict R-Multiple and Risk limits.")
        return session_open_risk_usd 
        
    top_play = scored_plays[0]
    
    # FIX: Mapped attribute to the new expectancy_score field
    print(f"      -> Top Play: {top_play.structure.strategy_type} | Score: {top_play.expectancy_score:.2f}")

    # STATE 5: PORTFOLIO GATEKEEPER
    print("[5/6] Checking Portfolio Risk Budget...")
    if not portfolio_gatekeeper(top_play, session_open_risk_usd, account_balance=10000.0):
        print("[-] Trade rejected: Executing this would breach maximum daily risk.")
        return session_open_risk_usd 

    # STATE 6: SYNTHESIS & DISSEMINATION
    print("[6/6] Synthesizing LLM Thesis and Dispatching Webhook...")
    thesis = generate_trade_thesis(ticker, regime, top_play)
    
    # POST to webhook (Ensure your .env has WEBHOOK_URL defined)
    success = await post_to_sheet(ticker, regime, top_play, thesis)
    
    if success:
        print("[+] Alert successfully dispatched!")
        # FIX: Mapped risk tracking to the new OptionStructure max_risk field
        return session_open_risk_usd + top_play.structure.max_risk
    else:
        print("[-] Failed to dispatch webhook.")
        return session_open_risk_usd 

async def main():
    print("INITIALIZING MEGA-CAP OPTIONS AGENT...")
    
    # Fetch the Access Token ONCE per session to avoid rate limits
    session_access_token = None
    if config.use_live_schwab_data:
        print("[+] Authenticating with Schwab API...")
        session_access_token = await get_valid_access_token()
        print("[+] Live Token Acquired.")

    # Track accumulated risk across the session to feed the gatekeeper
    session_open_risk_usd = 0.0 
    
    for ticker in MEGA_CAP_TICKERS:
        session_open_risk_usd = await run_pipeline(
            ticker, 
            session_open_risk_usd, 
            access_token=session_access_token
        ) 
        await asyncio.sleep(2) 
        
    print("\nSESSION COMPLETE.") 
    print(f"Total Projected Risk Allocated: ${session_open_risk_usd:,.2f}")

if __name__ == "__main__":
    asyncio.run(main())