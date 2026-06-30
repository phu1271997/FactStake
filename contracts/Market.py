# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
try:
    from genlayer.std import bigint
except ImportError:
    pass

if not hasattr(gl, 'block'):
    import datetime
    class MockBlock:
        @property
        def timestamp(self):
            return int(datetime.datetime.now().timestamp())
    gl.block = MockBlock()

class Market(gl.Contract):
    # Persistent storage fields
    claim: str
    close_time: bigint
    resolved_time: bigint
    source_urls: DynArray[str]
    verdict: str
    rationale: str
    yes_pool: bigint
    no_pool: bigint
    yes_stakes: TreeMap[Address, bigint]
    no_stakes: TreeMap[Address, bigint]
    claimed: TreeMap[Address, bool]
    resolved: bool
    creator: Address
    reputation_address: Address
    appeal_bonded: bool
    appeal_bond_amount: bigint
    appeal_deadline: bigint
    appealer: Address
    appeal_bond_amount_staked: bigint
    appeal_resolved: bool

    def __init__(self, claim: str, close_time: bigint, urls: DynArray[str], reputation_address: Address, creator: Address, bond_amount: bigint):
        self.claim = claim
        self.close_time = close_time
        
        if isinstance(reputation_address, str) or isinstance(reputation_address, bytes):
            self.reputation_address = Address(reputation_address)
        else:
            self.reputation_address = reputation_address
            
        if isinstance(creator, str) or isinstance(creator, bytes):
            self.creator = Address(creator)
        else:
            self.creator = creator
        self.resolved = False
        self.appeal_bonded = False
        self.yes_pool = bigint(0)
        self.no_pool = bigint(0)
        self.appeal_bond_amount = bond_amount
        self.appealer = Address("0x0000000000000000000000000000000000000000")
        self.appeal_bond_amount_staked = bigint(0)
        self.appeal_resolved = False
        self.resolved_time = bigint(0)
        self.appeal_deadline = bigint(0)
        self.verdict = "OPEN"
        self.rationale = ""
        
        # Populate source_urls without reassigning
        for i in range(len(urls)):
            self.source_urls.append(urls[i])

    # Helper getters to safely handle TreeMap default values
    def _get_yes_stake(self, addr: Address) -> bigint:
        val = self.yes_stakes.get(addr)
        return val if val is not None else bigint(0)

    def _get_no_stake(self, addr: Address) -> bigint:
        val = self.no_stakes.get(addr)
        return val if val is not None else bigint(0)

    def _source_urls(self) -> list[str]:
        urls = []
        for i in range(len(self.source_urls)):
            urls.append(self.source_urls[i])
        return urls

    @gl.public.write.payable
    def stake(self, vote_yes: bool):
        sender = gl.message.sender_address
        amount = bigint(gl.message.value)

        # Edge Case: Stake of 0 value -> reject
        if amount <= 0:
            raise UserError("Stake amount must be greater than zero")

        # Edge Case: Market already resolved or past close time
        if self.resolved:
            raise UserError("Market already resolved")
        if bigint(gl.block.timestamp) >= self.close_time:
            raise UserError("Market closed for staking")

        if vote_yes:
            self.yes_pool += amount
            self.yes_stakes[sender] = self._get_yes_stake(sender) + amount
        else:
            self.no_pool += amount
            self.no_stakes[sender] = self._get_no_stake(sender) + amount

    @gl.public.write
    def resolve(self):
        # Edge Case: Resolution called twice -> idempotency guard
        if self.resolved:
            raise UserError("Market already resolved")
        
        # Edge Case: Market resolved before close time -> reject
        if bigint(gl.block.timestamp) < self.close_time:
            raise UserError("Market close time not reached yet")

        def leader_fn():
            try:
                sources = []
                for url in self._source_urls():
                    try:
                        # Edge Case: web.render fails / URL is dead -> catch and write empty page
                        page = gl.nondet.web.render(url, mode="text")
                        sources.append(page)
                    except Exception:
                        sources.append("")
                
                # If all sources fail, resolve as UNRESOLVABLE
                if all(not src for src in sources):
                    return {
                        "verdict": "UNRESOLVABLE",
                        "confidence": 0,
                        "rationale": "All web sources failed to load.",
                        "sources_used": []
                    }

                prompt = self._build_resolution_prompt(self.claim, sources)
                # LLM returns malformed JSON -> handled by fallback or response_format='json'
                return gl.nondet.exec_prompt(prompt, response_format="json")
            except Exception as e:
                return {
                    "verdict": "UNRESOLVABLE",
                    "confidence": 0,
                    "rationale": f"Resolution error: {str(e)}",
                    "sources_used": []
                }

        def validator_fn(leader_res) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            leader_data = leader_res.calldata
            
            if isinstance(leader_data, str):
                import json
                try:
                    leader_data = json.loads(leader_data)
                except Exception:
                    return False
            
            if not isinstance(leader_data, dict):
                return False

            leader_verdict = leader_data.get("verdict")
            if leader_verdict not in ["TRUE", "FALSE", "UNRESOLVABLE"]:
                return False

            # SEMANTIC agreement: validator re-derives the verdict
            try:
                sources = []
                for url in self._source_urls():
                    try:
                        page = gl.nondet.web.render(url, mode="text")
                        sources.append(page)
                    except Exception:
                        sources.append("")

                if all(not src for src in sources):
                    return leader_verdict == "UNRESOLVABLE"

                prompt = self._build_resolution_prompt(self.claim, sources)
                validator_res = gl.nondet.exec_prompt(prompt, response_format="json")

                validator_data = validator_res
                if isinstance(validator_data, str):
                    import json
                    try:
                        validator_data = json.loads(validator_data)
                    except Exception:
                        return False

                if not isinstance(validator_data, dict):
                    return False

                validator_verdict = validator_data.get("verdict")
                return leader_verdict == validator_verdict
            except Exception:
                return leader_verdict == "UNRESOLVABLE"

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        self._apply_verdict(result)

    def _build_resolution_prompt(self, claim: str, sources: list[str]) -> str:
        sources_text = ""
        for i, src in enumerate(sources):
            trimmed_src = src[:3000] if src else "Empty page"
            sources_text += f"\n--- SOURCE {i+1} ---\n{trimmed_src}\n"
            
        return f"""
You are FactStake's decentralized self-resolving prediction market oracle.
Your task is to resolve the following claim based on the provided web sources:
Claim: "{claim}"

Web Sources:
{sources_text}

Analyze the sources and determine if the claim is:
1. "TRUE" (clear evidence confirms the claim is true)
2. "FALSE" (clear evidence confirms the claim is false or explicitly disproves it)
3. "UNRESOLVABLE" (conflicting evidence, insufficient evidence, dead sources, or cannot be determined)

You must respond in JSON format with the following keys:
- "verdict": must be exactly "TRUE", "FALSE", or "UNRESOLVABLE"
- "confidence": an integer between 0 and 100 representing your confidence
- "rationale": a brief explanation of how you arrived at this verdict
- "sources_used": a list of indices of sources that were relevant
"""

    def _apply_verdict(self, result):
        if isinstance(result, str):
            import json
            try:
                result = json.loads(result)
            except Exception:
                result = {"verdict": "UNRESOLVABLE", "rationale": "Malformed JSON in leader result", "confidence": 0}
        
        self.verdict = result.get("verdict", "UNRESOLVABLE")
        self.rationale = result.get("rationale", "No rationale provided")
        self.resolved = True
        self.resolved_time = bigint(gl.block.timestamp)
        self.appeal_deadline = bigint(gl.block.timestamp) + bigint(86400) # 24 hour appeal window

        # Report to Reputation
        if self.reputation_address != Address("0x0000000000000000000000000000000000000000"):
            try:
                reputation = gl.get_contract_at(self.reputation_address)
                reputation.emit(on='finalized').update_reputation(self.verdict)
            except Exception:
                pass

    @gl.public.write.payable
    def appeal(self):
        # Edge Case: Market resolved before close time -> reject if not resolved yet
        if not self.resolved:
            raise UserError("Market not resolved yet")
        
        # Edge Case: Appeal called twice / deadline passed
        if self.appeal_bonded:
            raise UserError("Appeal already bonded")
        if bigint(gl.block.timestamp) >= self.appeal_deadline:
            raise UserError("Appeal window closed")

        amount = bigint(gl.message.value)
        if amount < self.appeal_bond_amount:
            raise UserError("Insufficient appeal bond amount")

        self.appealer = gl.message.sender_address
        self.appeal_bond_amount_staked = amount
        self.appeal_bonded = True
        self.appeal_resolved = False

    @gl.public.write
    def resolve_appeal(self):
        if not self.appeal_bonded:
            raise UserError("Market not appealed")
        if self.appeal_resolved:
            raise UserError("Appeal already resolved")

        def leader_fn():
            try:
                sources = []
                for url in self._source_urls():
                    try:
                        page = gl.nondet.web.render(url, mode="text")
                        sources.append(page)
                    except Exception:
                        sources.append("")
                
                prompt = self._build_appeal_prompt(self.claim, sources, self.verdict)
                return gl.nondet.exec_prompt(prompt, response_format="json")
            except Exception as e:
                return {
                    "verdict": "UNRESOLVABLE",
                    "confidence": 0,
                    "rationale": f"Appeal resolution error: {str(e)}",
                    "sources_used": []
                }

        def validator_fn(leader_res) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            leader_data = leader_res.calldata
            
            if isinstance(leader_data, str):
                import json
                try:
                    leader_data = json.loads(leader_data)
                except Exception:
                    return False

            if not isinstance(leader_data, dict):
                return False

            leader_verdict = leader_data.get("verdict")
            if leader_verdict not in ["TRUE", "FALSE", "UNRESOLVABLE"]:
                return False

            try:
                sources = []
                for url in self._source_urls():
                    try:
                        page = gl.nondet.web.render(url, mode="text")
                        sources.append(page)
                    except Exception:
                        sources.append("")

                prompt = self._build_appeal_prompt(self.claim, sources, self.verdict)
                validator_res = gl.nondet.exec_prompt(prompt, response_format="json")

                validator_data = validator_res
                if isinstance(validator_data, str):
                    import json
                    try:
                        validator_data = json.loads(validator_data)
                    except Exception:
                        return False

                if not isinstance(validator_data, dict):
                    return False

                validator_verdict = validator_data.get("verdict")
                return leader_verdict == validator_verdict
            except Exception:
                return leader_verdict == "UNRESOLVABLE"

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        self._apply_appeal_verdict(result)

    def _build_appeal_prompt(self, claim: str, sources: list[str], initial_verdict: str) -> str:
        sources_text = ""
        for i, src in enumerate(sources):
            trimmed_src = src[:3500] if src else "Empty page"
            sources_text += f"\n--- SOURCE {i+1} ---\n{trimmed_src}\n"
            
        return f"""
You are FactStake's senior appeal tribunal.
An initial resolution was reached: "{initial_verdict}" for the claim: "{claim}".
A user has disputed this verdict and paid an appeal bond.

Analyze the sources below with extreme precision, cross-referencing all details.
Web Sources:
{sources_text}

You must either CONFIRM the initial verdict or OVERRULE it based on the facts.
Determine if the claim is "TRUE", "FALSE", or "UNRESOLVABLE".

You must respond in JSON format with the following keys:
- "verdict": exactly "TRUE", "FALSE", or "UNRESOLVABLE"
- "confidence": an integer between 0 and 100
- "rationale": explain why you confirmed or overruled the initial verdict, addressing counter-arguments.
- "sources_used": list of indices of sources that were relevant
"""

    def _apply_appeal_verdict(self, result):
        if isinstance(result, str):
            import json
            try:
                result = json.loads(result)
            except Exception:
                result = {"verdict": "UNRESOLVABLE", "rationale": "Malformed JSON in appeal result", "confidence": 0}

        new_verdict = result.get("verdict", "UNRESOLVABLE")
        rationale = result.get("rationale", "No appeal rationale provided")
        
        initial_verdict = self.verdict
        self.verdict = new_verdict
        self.rationale = f"Appeal verdict: {new_verdict}. Rationale: {rationale} (Initial verdict was {initial_verdict})"
        self.appeal_resolved = True

        bond = self.appeal_bond_amount_staked
        appealer = self.appealer

        if new_verdict == initial_verdict:
            # Appeal failed: Bond is added to the winning pool
            if new_verdict == "TRUE":
                self.yes_pool += bond
            elif new_verdict == "FALSE":
                self.no_pool += bond
            else:
                gl.get_contract_at(appealer).emit_transfer(value=u256(bond))
        else:
            # Appeal succeeded: Overruled! refund bond to appealer
            gl.get_contract_at(appealer).emit_transfer(value=u256(bond))

        # Report final status to Reputation
        if self.reputation_address != Address("0x0000000000000000000000000000000000000000"):
            try:
                reputation = gl.get_contract_at(self.reputation_address)
                reputation.emit(on='finalized').update_reputation(self.verdict)
            except Exception:
                pass

    @gl.public.write
    def claim_winnings(self):
        sender = gl.message.sender_address

        if not self.resolved:
            raise UserError("Market not resolved yet")

        # If appealed, must wait until appeal is resolved
        if self.appeal_bonded and not self.appeal_resolved:
            raise UserError("Appeal pending resolution")
        
        # If not appealed, must wait for appeal deadline
        if not self.appeal_bonded and bigint(gl.block.timestamp) < self.appeal_deadline:
            raise UserError("Appeal window still open")

        # Edge Case: Double-claim of winnings -> guard with claimed flag
        if self.claimed.get(sender):
            raise UserError("Winnings already claimed")

        yes_stake = self._get_yes_stake(sender)
        no_stake = self._get_no_stake(sender)
        
        payout = bigint(0)

        # Edge Case: Pool on one side = 0 (no opposing stake) OR UNRESOLVABLE -> refund original stakes
        if self.verdict == "UNRESOLVABLE" or self.yes_pool == bigint(0) or self.no_pool == bigint(0):
            payout = yes_stake + no_stake
        elif self.verdict == "TRUE":
            if yes_stake > 0:
                payout = yes_stake * (self.yes_pool + self.no_pool) // self.yes_pool
        elif self.verdict == "FALSE":
            if no_stake > 0:
                payout = no_stake * (self.yes_pool + self.no_pool) // self.no_pool

        if payout <= 0:
            raise UserError("No winnings to claim")

        self.claimed[sender] = True
        
        # R15: Transfer native token via emit_transfer
        gl.get_contract_at(sender).emit_transfer(value=u256(payout))

    # Read-only views for frontend
    @gl.public.view
    def get_details(self) -> str:
        return f'{{"claim": "{self.claim}", "close_time": {str(self.close_time)}, "yes_pool": {str(self.yes_pool)}, "no_pool": {str(self.no_pool)}, "resolved": {str(self.resolved).lower()}, "verdict": "{self.verdict}", "rationale": "{self.rationale.replace(chr(34), chr(39))}", "appeal_bonded": {str(self.appeal_bonded).lower()}, "appeal_resolved": {str(self.appeal_resolved).lower()}, "appeal_bond_amount": {str(self.appeal_bond_amount)}, "appeal_deadline": {str(self.appeal_deadline)}}}'

    @gl.public.view
    def get_user_state(self, user: Address) -> str:
        yes_stk = self._get_yes_stake(user)
        no_stk = self._get_no_stake(user)
        is_claimed = self.claimed.get(user)
        is_claimed_val = "true" if is_claimed else "false"
        return f'{{"yes_stake": {str(yes_stk)}, "no_stake": {str(no_stk)}, "claimed": {is_claimed_val}}}'

Contract = Market
