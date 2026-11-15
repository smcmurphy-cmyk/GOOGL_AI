import datetime
from models.market_data import OptionsChain, OptionContract, UnderlyingQuote
from utils.greeks import calculate_gex_profile

def create_mock_contract(strike, opt_type, gamma, oi):
    return OptionContract(
        ticker="TEST", strike=strike, expiration=datetime.date.today() + datetime.timedelta(days=1),
        option_type=opt_type, bid=1.0, ask=1.1, last_price=1.05, volume=100, open_interest=oi,
        implied_volatility=0.5, delta=0.5, gamma=gamma, theta=-0.1, vega=0.1
    )

def test_gamma_flip():
    print("--- RUNNING GREEKS AUDIT ---")
    spot = 100.0
    underlying = UnderlyingQuote(ticker="TEST", price=spot, timestamp="2026-11-15T00:00:00Z")

    # TEST A: Normal Chain (Should cross zero between 95 and 105)
    contracts_a = [
        create_mock_contract(95.0, "put", 0.05, 5000),   # Heavy Puts (Negative GEX)
        create_mock_contract(100.0, "put", 0.02, 1000),  # Lighter Puts
        create_mock_contract(105.0, "call", 0.06, 6000), # Heavy Calls (Positive GEX)
    ]
    chain_a = OptionsChain(underlying=underlying, contracts=contracts_a)
    profile_a = calculate_gex_profile(chain_a)
    
    print(f"Test A (Normal): Gamma Flip = {profile_a.gamma_flip} | Expected: 105.0")
    if profile_a.gamma_flip == 105.0:
        print("[+] PASS: Zero-crossing accurately detected.")
    else:
        print("[-] FAIL: Incorrect crossing.")

    # TEST B: Skewed Chain (No zero crossing, dealers short gamma everywhere)
    contracts_b = [
        create_mock_contract(95.0, "put", 0.05, 5000),
        create_mock_contract(100.0, "put", 0.06, 6000),
        create_mock_contract(105.0, "put", 0.04, 4000),
    ]
    chain_b = OptionsChain(underlying=underlying, contracts=contracts_b)
    profile_b = calculate_gex_profile(chain_b)
    
    print(f"\nTest B (Skewed): Gamma Flip = {profile_b.gamma_flip} | Expected: None")
    if profile_b.gamma_flip is None:
        print("[+] PASS: Correctly defaulted to None when no crossing exists.")
    else:
        print("[-] FAIL: Falsely detected a crossing.")

if __name__ == "__main__":
    test_gamma_flip()