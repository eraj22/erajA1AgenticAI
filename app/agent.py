"""The runtime owns validation, capabilities, recovery and all stopping rules."""
import asyncio
import json
from time import perf_counter
from pydantic import ValidationError
from app.config import settings
from app.domain import ticket_ids
from app.models import AgentDecision, AgentState, ArenaResponse, Metrics, ToolTrace
from app.prompts import build_messages
from app.providers import get_model, ProviderError, DailyBudgetReached
from app.tools import Sandbox, Rejected, ToolFailure

async def run_agent(request, history, model, goal=None, model_client=None):
    state = AgentState(goal=goal or request.task, authorized_ticket_ids=ticket_ids(goal or request.task))
    sandbox = Sandbox(state)
    metrics = Metrics()
    events, errors, traces = [], [], []
    known_usage = True
    used_tokens, used_cost = 0, 0.0
    price = json.loads(settings.model_prices_json).get(model)
    deadline = perf_counter() + settings.run_timeout_seconds
    max_steps = min(request.arena_config.max_steps, settings.max_steps)

    def finish(status, reason, message):
        events.append({'step': state.steps, 'event': 'agent_stop', 'reason': reason})
        return ArenaResponse(request_id=request.request_id, status=status, final_response=message,
                             stop_reason=reason, steps=state.steps, tool_calls=traces,
                             errors=errors, events=events, metrics=metrics)

    if not state.authorized_ticket_ids:
        return finish('needs_clarification', 'missing_ticket_id',
                      'Which sample ticket should I triage? Provide one identifier, such as T1001.')
    if len(state.authorized_ticket_ids) > 1:
        return finish('needs_clarification', 'ambiguous_ticket_id',
                      'This agent handles one ticket per run. Please send a new request naming exactly one ticket.')
    if state.authorized_ticket_ids[0] not in sandbox.records:
        return finish('needs_clarification', 'unknown_ticket_id',
                      'That ticket is not in the sample queue. Choose an existing ticket from the interface.')
    try:
        client = model_client or get_model(model)
    except ProviderError as exc:
        return finish('failed', exc.code, 'A live model is not configured. Set the provider, model identifier and API key on the server.')
    if model == 'demo':
        events.append({'step': 0, 'event': 'demo_notice', 'message': 'Scripted offline demo; not an LLM or model-comparison result.'})
    contract_failures = provider_failures = 0

    try:
        async with asyncio.timeout(settings.run_timeout_seconds):
            while state.steps < max_steps:
                messages = build_messages(state, history, request.external_context)
                prompt_bytes = sum(len(m['content'].encode('utf-8')) for m in messages)
                if prompt_bytes > settings.max_context_bytes:
                    return finish('budget_exceeded', 'context_budget_reached', 'The combined input and history exceed the context limit. Start a new chat or shorten the input.')
                # Conservative reservation: one token per UTF-8 byte plus protocol overhead.
                reserve_input = prompt_bytes + 1024
                reserve_tokens = reserve_input + settings.max_output_tokens
                reserve_cost = (reserve_input * price['input'] + settings.max_output_tokens * price['output']) / 1_000_000 if price else 0
                if used_tokens + reserve_tokens > settings.max_run_tokens:
                    return finish('budget_exceeded', 'token_budget_reached', 'The run stopped before another model call would exceed its token budget.')
                if price and used_cost + reserve_cost > settings.max_run_cost_usd:
                    return finish('budget_exceeded', 'cost_budget_reached', 'The run stopped before another model call would exceed its cost budget.')
                state.steps += 1
                metrics.model_calls += 1
                started = perf_counter()
                try:
                    result = await client.decide(messages, state)
                except DailyBudgetReached:
                    metrics.model_calls -= 1
                    state.steps -= 1
                    return finish('budget_exceeded', 'daily_model_budget_reached', 'The server model-call allowance has been reached. Try after the daily reset.')
                except ProviderError as exc:
                    provider_failures += 1
                    used_tokens += reserve_tokens
                    used_cost += reserve_cost
                    known_usage = False
                    metrics.input_tokens = metrics.output_tokens = metrics.estimated_cost_usd = None
                    errors.append({'step': state.steps, 'kind': 'provider_error', 'code': exc.code})
                    if exc.retryable and provider_failures <= settings.max_contract_retries:
                        events.append({'step': state.steps, 'event': 'provider_retry', 'code': exc.code})
                        await asyncio.sleep(min(0.2 * provider_failures, max(0, deadline - perf_counter())))
                        continue
                    return finish('failed', exc.code, 'The model provider could not complete the request. No external action was performed.')
                events.append({'step': state.steps, 'event': 'model_decision', 'latency_ms': round((perf_counter() - started) * 1000, 2)})
                if result.input_tokens is None or result.output_tokens is None:
                    known_usage = False
                    used_tokens += reserve_tokens
                    used_cost += reserve_cost
                else:
                    used_tokens += result.input_tokens + result.output_tokens
                    if price:
                        used_cost += (result.input_tokens * price['input'] + result.output_tokens * price['output']) / 1_000_000
                    if known_usage:
                        metrics.input_tokens = (metrics.input_tokens or 0) + result.input_tokens
                        metrics.output_tokens = (metrics.output_tokens or 0) + result.output_tokens
                        metrics.estimated_cost_usd = used_cost if price else None
                if not known_usage:
                    metrics.input_tokens = metrics.output_tokens = metrics.estimated_cost_usd = None
                if used_tokens > settings.max_run_tokens or (price and used_cost > settings.max_run_cost_usd):
                    return finish('budget_exceeded', 'reported_usage_budget_reached', 'Provider-reported usage reached the configured budget.')
                raw = result.raw
                if request.arena_config.fault.type == 'invalid_agent_decision' and not state.fault_used:
                    raw = '{"status": 17, "action": "not_a_tool"}'
                    state.fault_used = True
                    events.append({'step': state.steps, 'event': 'fault_injected', 'type': 'invalid_agent_decision'})
                try:
                    decision = AgentDecision.model_validate_json(raw, strict=True)
                    if decision.status == 'continue':
                        if decision.action is None:
                            raise Rejected('A continue decision requires an action.')
                        args = sandbox.validate(decision.action, decision.arguments)
                    else:
                        if decision.action is not None or decision.arguments:
                            raise Rejected('Terminal decisions cannot execute actions.')
                        if decision.status == 'completed' and not (state.ticket and state.triage and state.draft):
                            raise Rejected('Completion requires a read ticket, valid triage and an unsent draft.')
                        if decision.status == 'needs_clarification' and not decision.user_message:
                            raise Rejected('A clarification requires a question.')
                except (ValidationError, Rejected, ValueError) as exc:
                    contract_failures += 1
                    detail = str(exc) if isinstance(exc, Rejected) else 'Decision or tool arguments failed typed schema validation.'
                    errors.append({'step': state.steps, 'kind': 'contract_error', 'message': detail})
                    state.observations.append({'type': 'validation_error', 'message': detail})
                    events.append({'step': state.steps, 'event': 'validation', 'passed': False, 'message': detail})
                    if contract_failures > settings.max_contract_retries:
                        return finish('contract_error', 'contract_retries_exhausted', 'The model could not produce a valid permitted decision within the repair limit.')
                    continue
                events.append({'step': state.steps, 'event': 'validation', 'passed': True, 'status': decision.status, 'action': decision.action})
                if decision.status != 'continue':
                    if decision.status == 'completed':
                        message = f'Sandbox triage complete for {state.ticket.ticket_id}.\nPriority: {state.triage.priority}\nTeam: {state.triage.team}\nReason: {state.triage.rationale}\n\nUnsent reply draft:\n{state.draft.text}\n\nNo real message or account change was made.'
                        return finish('completed', 'goal_completed', message)
                    reason = {'needs_clarification': 'clarification_required', 'blocked': 'autonomy_boundary', 'failed': 'model_stopped'}[decision.status]
                    return finish(decision.status, reason, decision.user_message or 'This action is outside the sandbox agent scope.')
                for attempt in range(1, settings.max_tool_retries + 2):
                    started = perf_counter()
                    try:
                        observation = await sandbox.execute(decision.action, args, request.arena_config.fault.type)
                        outcome = 'success'
                    except ToolFailure as exc:
                        outcome = exc.outcome
                    traces.append(ToolTrace(step=state.steps, tool=decision.action, attempt=attempt, outcome=outcome,
                                            latency_ms=(perf_counter() - started) * 1000))
                    if outcome == 'success':
                        state.observations.append({'tool': decision.action, 'data': observation, 'text_trust': 'untrusted'})
                        events.append({'step': state.steps, 'event': 'tool_observation', 'tool': decision.action, 'data': observation})
                        break
                    errors.append({'step': state.steps, 'kind': 'tool_error', 'tool': decision.action, 'attempt': attempt, 'outcome': outcome})
                else:
                    return finish('tool_error', 'tool_retries_exhausted', 'The sandbox tool failed after bounded retries. The run stopped safely.')
            return finish('budget_exceeded', 'step_budget_reached', 'The run reached its decision limit before validated completion.')
    except TimeoutError:
        return finish('budget_exceeded', 'time_budget_reached', 'The run reached its time limit and stopped.')
