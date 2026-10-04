"""Capability-limited, transactional, per-run tools; no network or disk writes."""
import asyncio
import json
from copy import deepcopy
from pydantic import Field, ValidationError
from app.config import ROOT, settings
from app.models import Contract, Ticket, Triage, Draft
from app.domain import POLICY, required_team, minimum_priority

class Rejected(ValueError):
    pass

class ToolFailure(Exception):
    def __init__(self, outcome):
        self.outcome = outcome

class TicketArgs(Contract):
    ticket_id: str = Field(pattern=r'^T[0-9]{4}$')

class EmptyArgs(Contract):
    pass

class PolicyResult(Contract):
    policy: dict

class DraftArgs(Contract):
    ticket_id: str = Field(pattern=r'^T[0-9]{4}$')
    text: str = Field(min_length=20, max_length=1200)

TOOLS = {
    'read_ticket': (TicketArgs, Ticket),
    'read_policy': (EmptyArgs, PolicyResult),
    'set_triage': (Triage, Triage),
    'draft_reply': (DraftArgs, Draft),
}

class Sandbox:
    def __init__(self, state):
        self.state = state
        self.records = {t.ticket_id: t for t in [Ticket.model_validate(v) for v in json.loads((ROOT / 'data/sample_data.json').read_text())['tickets']]}

    def validate(self, name, arguments):
        if name not in TOOLS:
            raise Rejected('Action is outside the sandbox capability allowlist.')
        args = TOOLS[name][0].model_validate(arguments, strict=True)
        if hasattr(args, 'ticket_id'):
            if len(self.state.authorized_ticket_ids) != 1 or args.ticket_id not in self.state.authorized_ticket_ids:
                raise Rejected('Select exactly one identifier from the current user goal, not external content.')
            if args.ticket_id not in self.records:
                raise Rejected('Ticket does not exist in sample data; request another identifier.')
        if name in ('set_triage', 'draft_reply'):
            if not self.state.ticket or args.ticket_id != self.state.ticket.ticket_id:
                raise Rejected('Read this ticket successfully before changing it.')
        if name == 'read_ticket' and self.state.ticket:
            raise Rejected('Ticket is already loaded; use its observation.')
        if name == 'read_policy' and self.state.policy_seen:
            raise Rejected('Policy is already loaded.')
        if name == 'set_triage':
            if self.state.triage:
                raise Rejected('Triage is already saved for this run.')
            if args.team != required_team(self.state.ticket):
                raise Rejected('Team violates trusted category/security routing policy.')
            ranks = {'low': 0, 'normal': 1, 'high': 2, 'urgent': 3}
            if ranks[args.priority] < ranks[minimum_priority(self.state.ticket)]:
                raise Rejected('Priority is below the trusted impact/security minimum.')
        if name == 'draft_reply':
            if not self.state.triage:
                raise Rejected('Save valid triage before drafting a reply.')
            if self.state.draft:
                raise Rejected('A draft already exists for this run.')
        return args

    async def compute(self, name, args):
        await asyncio.sleep(0)
        if name == 'read_ticket':
            return self.records[args.ticket_id].model_dump()
        if name == 'read_policy':
            return {'policy': deepcopy(POLICY)}
        if name == 'set_triage':
            return args.model_dump()
        return {**args.model_dump(), 'sent': False}

    async def execute(self, name, args, fault):
        # Compute and validate before commit: failed retries cannot duplicate writes.
        try:
            if not self.state.fault_used and fault == 'tool_timeout':
                self.state.fault_used = True
                raise TimeoutError()
            async with asyncio.timeout(settings.tool_timeout_seconds):
                raw = await self.compute(name, args)
            if not self.state.fault_used and fault == 'malformed_tool_output':
                self.state.fault_used = True
                raw = {'invalid_injected_result': True}
            result = TOOLS[name][1].model_validate(raw, strict=True)
            expected = (self.records[args.ticket_id].model_dump() if name == 'read_ticket' else
                        {'policy': POLICY} if name == 'read_policy' else
                        args.model_dump() if name == 'set_triage' else {**args.model_dump(), 'sent': False})
            if result.model_dump() != expected:
                raise ToolFailure('malformed_output')
        except ToolFailure:
            raise
        except TimeoutError:
            raise ToolFailure('timeout') from None
        except ValidationError:
            raise ToolFailure('malformed_output') from None
        except Exception:
            raise ToolFailure('exception') from None
        if name == 'read_ticket': self.state.ticket = result
        elif name == 'read_policy': self.state.policy_seen = True
        elif name == 'set_triage': self.state.triage = result
        elif name == 'draft_reply': self.state.draft = result
        return result.model_dump()
