import pytest
import json
import time

def test_market_happy_path(direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob):
    # 1. Deploy Reputation contract to dynamically extract the VM's internal Address class
    reputation = direct_deploy("contracts/Reputation.py")
    Address = type(reputation.address)
    
    # 2. Deploy Market contract directly in isolation
    close_ts = int(time.time()) + 100  # Closed in 100 seconds
    dummy_addr = Address(b'\x00' * 20)
    
    market = direct_deploy(
        "contracts/Market.py",
        "Did Company X lay off >1000 in Q3 2025?",
        close_ts,
        ["https://news.example.com/layoffs", "https://blog.example.com/company-x"],
        dummy_addr,
        Address(direct_owner),
        1000  # appeal bond amount
    )
    
    # 3. Alice stakes 5000 units on YES
    direct_vm.sender = direct_alice
    direct_vm.value = 5000
    market.stake(True)
    
    # 4. Bob stakes 3000 units on NO
    direct_vm.sender = direct_bob
    direct_vm.value = 3000
    market.stake(False)
    
    # Verify pools
    details = json.loads(market.get_details())
    assert details["yes_pool"] == 5000
    assert details["no_pool"] == 3000
    assert details["resolved"] is False
    assert details["verdict"] == "OPEN"
    
    # 5. Set up mocks for LLM and Web (using correct MockedWebResponseData dict structure)
    direct_vm.mock_web(
        r"https://news.example.com/layoffs",
        {"method": "GET", "status": 200, "body": "Company X laid off 1200 workers in recent restructuring."}
    )
    direct_vm.mock_web(
        r"https://blog.example.com/company-x",
        {"method": "GET", "status": 200, "body": "Tech giant Company X cut about 1200 employees."}
    )
    direct_vm.mock_llm(
        r".*",
        json.dumps({
            "verdict": "TRUE",
            "confidence": 90,
            "rationale": "Multiple independent sources confirm layoffs of 1200 employees.",
            "sources_used": [0, 1]
        })
    )
    
    # 6. Bypass close_time check by mutating attribute directly
    market.close_time = 0
    
    # 7. Trigger resolution
    direct_vm.sender = owner = Address(direct_owner)
    market.resolve()
    
    # Verify verdict and rationale
    details = json.loads(market.get_details())
    assert details["resolved"] is True
    assert details["verdict"] == "TRUE"
    assert "1200 employees" in details["rationale"]
    
    # 8. Bypass appeal_deadline
    market.appeal_deadline = 0
    
    # 9. Claim winnings for Alice (YES winner)
    direct_vm.sender = direct_alice
    market.claim_winnings()
    
    # Verify Alice's state
    user_state = json.loads(market.get_user_state(Address(direct_alice)))
    assert user_state["claimed"] is True
