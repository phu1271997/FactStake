import pytest
import json
import time

def test_market_dead_url_unresolvable(direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob):
    reputation = direct_deploy("contracts/Reputation.py")
    Address = type(reputation.address)
    
    dummy_addr = Address(b'\x00' * 20)
    market = direct_deploy(
        "contracts/Market.py",
        "Did company X file for bankruptcy?",
        int(time.time()) + 100,
        ["https://failed-url.example.com"],
        dummy_addr,
        Address(direct_owner),
        1000
    )
    
    # Alice and Bob stake
    direct_vm.sender = direct_alice
    direct_vm.value = 5000
    market.stake(True)
    
    direct_vm.sender = direct_bob
    direct_vm.value = 3000
    market.stake(False)
    
    # Web mock fails/empty
    direct_vm.mock_web(r"https://failed-url.example.com", {"method": "GET", "status": 500, "body": "Internal Server Error"})
    direct_vm.mock_llm(
        r".*",
        json.dumps({
            "verdict": "UNRESOLVABLE",
            "confidence": 0,
            "rationale": "All web sources failed to load.",
            "sources_used": []
        })
    )
    
    # Close time bypass
    market.close_time = 0
    
    # Resolve
    direct_vm.sender = direct_owner
    market.resolve()
    
    details = json.loads(market.get_details())
    assert details["verdict"] == "UNRESOLVABLE"
    
    # Pass appeal window bypass
    market.appeal_deadline = 0
    
    # Both claim and get refund (Alice: 5000, Bob: 3000)
    direct_vm.sender = direct_alice
    market.claim_winnings()
    
    direct_vm.sender = direct_bob
    market.claim_winnings()
    
    # Verify both claimed
    user_alice = json.loads(market.get_user_state(Address(direct_alice)))
    user_bob = json.loads(market.get_user_state(Address(direct_bob)))
    assert user_alice["claimed"] is True
    assert user_bob["claimed"] is True

def test_market_one_sided_pool_refund(direct_vm, direct_deploy, direct_owner, direct_alice):
    reputation = direct_deploy("contracts/Reputation.py")
    Address = type(reputation.address)
    
    dummy_addr = Address(b'\x00' * 20)
    market = direct_deploy(
        "contracts/Market.py",
        "Is today Tuesday?",
        int(time.time()) + 100,
        ["https://calendar.example.com"],
        dummy_addr,
        Address(direct_owner),
        1000
    )
    
    # Only Alice stakes
    direct_vm.sender = direct_alice
    direct_vm.value = 5000
    market.stake(True)
    
    direct_vm.mock_web(r"https://calendar.example.com", {"method": "GET", "status": 200, "body": "Today is Tuesday"})
    direct_vm.mock_llm(
        r".*",
        json.dumps({
            "verdict": "TRUE",
            "confidence": 100,
            "rationale": "It is Tuesday",
            "sources_used": [0]
        })
    )
    
    # Close time bypass
    market.close_time = 0
    
    direct_vm.sender = direct_owner
    market.resolve()
    
    # Pass appeal window bypass
    market.appeal_deadline = 0
    
    # Alice claims (gets her 5000 refund because other pool was 0)
    direct_vm.sender = direct_alice
    market.claim_winnings()
    
    user_alice = json.loads(market.get_user_state(Address(direct_alice)))
    assert user_alice["claimed"] is True

def test_market_appeal_flow(direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob):
    reputation = direct_deploy("contracts/Reputation.py")
    Address = type(reputation.address)
    
    dummy_addr = Address(b'\x00' * 20)
    market = direct_deploy(
        "contracts/Market.py",
        "Did startup Y raise Series A?",
        int(time.time()) + 100,
        ["https://startup-news.com/raise"],
        dummy_addr,
        Address(direct_owner),
        1000
    )
    
    # Alice YES, Bob NO
    direct_vm.sender = direct_alice
    direct_vm.value = 5000
    market.stake(True)
    
    direct_vm.sender = direct_bob
    direct_vm.value = 3000
    market.stake(False)
    
    # Initial resolve mocks (Leader says TRUE)
    direct_vm.mock_web(r"https://startup-news.com/raise", {"method": "GET", "status": 200, "body": "Startup Y raised 5M"})
    direct_vm.mock_llm(
        r".*",
        json.dumps({
            "verdict": "TRUE",
            "confidence": 70,
            "rationale": "Seems true",
            "sources_used": [0]
        })
    )
    
    market.close_time = 0
    
    direct_vm.sender = direct_owner
    market.resolve()
    
    # Bob appeals (stakes 1000 bond)
    direct_vm.sender = direct_bob
    direct_vm.value = 1000
    market.appeal()
    
    # Clear previous mocks to allow the new overrule mock to match the catch-all pattern
    direct_vm.clear_mocks()
    
    # Appeal resolve mocks (Overrules to FALSE)
    direct_vm.mock_web(r"https://startup-news.com/raise", {"method": "GET", "status": 200, "body": "Startup Y denies Series A rumor"})
    direct_vm.mock_llm(
        r".*",
        json.dumps({
            "verdict": "FALSE",
            "confidence": 95,
            "rationale": "It was a rumor, startup Y denied it.",
            "sources_used": [0]
        })
    )
    
    direct_vm.sender = direct_owner
    market.resolve_appeal()
    
    # Verify final verdict is FALSE
    details = json.loads(market.get_details())
    assert details["verdict"] == "FALSE"
    assert "Appeal verdict: FALSE" in details["rationale"]
    
    # Bob claims winnings (NO wins!)
    direct_vm.sender = direct_bob
    market.claim_winnings()
    user_bob = json.loads(market.get_user_state(Address(direct_bob)))
    assert user_bob["claimed"] is True

def test_reputation_isolated(direct_vm, direct_deploy, direct_owner):
    reputation = direct_deploy("contracts/Reputation.py")
    Address = type(reputation.address)
    mock_market = Address(b'\x01' * 20)
    
    # Register a mock market address
    direct_vm.sender = direct_owner
    reputation.register_market(mock_market)
    
    # Check stats
    stats = json.loads(reputation.get_stats())
    assert stats["total_markets"] == 1
    
    # Check status
    assert reputation.get_market_status(mock_market) == "REGISTERED"
