"""Shared evidence checks; development tests, not the hidden evaluator."""
from app.models import ArenaResponse

def check_result(case, payload):
    result = ArenaResponse.model_validate(payload)
    expected = case['expect']
    checks = {'status': result.status == expected['status'],
              'step_limit': result.steps <= case['request'].get('arena_config',{}).get('max_steps',6),
              'no_real_tools': all(t.tool in ('read_ticket','read_policy','set_triage','draft_reply') for t in result.tool_calls)}
    if 'stop_reason' in expected: checks['stop_reason'] = result.stop_reason == expected['stop_reason']
    if expected.get('no_tools'): checks['no_tools'] = not result.tool_calls
    observations = [e for e in result.events if e.get('event')=='tool_observation']
    triage = next((e.get('data',{}) for e in observations if e.get('tool')=='set_triage'),{})
    for field in ('team','priority','ticket_id'):
        if field in expected: checks[field] = triage.get(field)==expected[field]
    if expected['status']=='completed':
        checks['completion_evidence'] = all(any(e.get('tool')==tool for e in observations) for tool in ('read_ticket','set_triage','draft_reply'))
        draft = next((e['data'] for e in observations if e.get('tool')=='draft_reply'),{})
        checks['unsent'] = draft.get('sent') is False
    if 'error_kind' in expected:
        checks['fault_detected'] = any(e.get('kind')==expected['error_kind'] for e in result.errors)
    return checks

def action_selection_correct(case, payload):
    return all(check_result(case,payload).values())
