# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
try:
    from genlayer.std import bigint
except ImportError:
    pass

class MarketFactory(gl.Contract):
    market_code: str
    reputation_address: Address
    markets: DynArray[Address]

    def __init__(self, market_code: str, reputation_address: Address):
        self.market_code = market_code
        if isinstance(reputation_address, str) or isinstance(reputation_address, bytes):
            self.reputation_address = Address(reputation_address)
        else:
            self.reputation_address = reputation_address

    @gl.public.write
    def create_market(self, claim: str, close_delay: bigint, urls: DynArray[str], bond_amount: bigint) -> Address:
        close_time = bigint(gl.block.timestamp) + close_delay
        salt_nonce = u256(len(self.markets) + 1)
        
        # Deploy Market contract
        code_bytes = self.market_code.encode('utf-8') if isinstance(self.market_code, str) else self.market_code
        child_address = gl.deploy_contract(
            code=code_bytes,
            args=[claim, close_time, urls, self.reputation_address, gl.message.sender_address, bond_amount],
            salt_nonce=salt_nonce,
            on='finalized'
        )
        
        # Register in Reputation contract
        reputation = gl.get_contract_at(self.reputation_address)
        reputation.emit(on='finalized').register_market(child_address)
        
        self.markets.append(child_address)
        return child_address

    @gl.public.view
    def get_markets(self) -> DynArray[Address]:
        return self.markets

Contract = MarketFactory
