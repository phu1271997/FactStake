# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
try:
    from genlayer.std import bigint
except ImportError:
    pass

class Reputation(gl.Contract):
    market_records: TreeMap[Address, str]
    unresolvable_markets: DynArray[Address]
    total_markets_count: bigint
    unresolvable_count: bigint

    def __init__(self):
        self.total_markets_count = bigint(0)
        self.unresolvable_count = bigint(0)

    @gl.public.write
    def register_market(self, market: Address):
        self.market_records[market] = "REGISTERED"
        self.total_markets_count += bigint(1)

    @gl.public.write
    def update_reputation(self, verdict: str):
        market = gl.message.sender_address
        status = self.market_records.get(market)
        if status is None:
            raise UserError("Market not registered")
        
        # Track transitions to/from UNRESOLVABLE
        if verdict == "UNRESOLVABLE" and status != "UNRESOLVABLE":
            self.unresolvable_markets.append(market)
            self.unresolvable_count += bigint(1)
        elif status == "UNRESOLVABLE" and verdict != "UNRESOLVABLE":
            if self.unresolvable_count > bigint(0):
                self.unresolvable_count -= bigint(1)
                
        self.market_records[market] = verdict

    @gl.public.view
    def get_stats(self) -> str:
        return f'{{"total_markets": {str(self.total_markets_count)}, "unresolvable_markets": {str(self.unresolvable_count)}}}'

    @gl.public.view
    def get_unresolvable_markets(self) -> DynArray[Address]:
        return self.unresolvable_markets

    @gl.public.view
    def get_market_status(self, market: Address) -> str:
      status = self.market_records.get(market)
      return status if status is not None else "UNREGISTERED"

Contract = Reputation
