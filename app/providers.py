"""Small async provider adapters; scripted demo is explicitly not a language model."""
import json
import re
import time
from dataclasses import dataclass
import httpx
from app.config import settings
from app.domain import required_team, minimum_priority
from app.models import AgentDecision

class ProviderError(Exception):
    def __init__(self, code, retryable=False):
        self.code, self.retryable = code, retryable

class DailyBudgetReached(Exception):
    pass

@dataclass
class ModelResult:
    raw: str
    input_tokens: int | None = None
    output_tokens: int | None = None

class DailyCalls:
    def __init__(self):
        self.day, self.calls = -1, 0

    def reserve(self):
        day = int(time.time() // 86400)
        if day != self.day:
            self.day, self.calls = day, 0
        if self.calls >= settings.max_daily_model_calls:
            raise DailyBudgetReached()
        self.calls += 1

daily_calls = DailyCalls()

class DemoModel:
    """Deliberately restricted deterministic demonstration, never evaluation evidence."""
    async def decide(self, messages, state):
        goal = state.goal.split('\nUser clarification: ')[0].strip()
        if not re.fullmatch(r'(?:please\s+)?triage(?:\s+(?:ticket|the ticket))?(?:\s+T[0-9]{4})?\s*[.!]?', goal, re.I) and not re.fullmatch(r'T[0-9]{4}', goal, re.I):
            d = {'status': 'blocked', 'user_message': 'Offline demo accepts only “Triage T1001” or “Triage ticket”. Configure a live model for natural-language requests.'}
        elif not state.ticket:
            d = {'status': 'continue', 'action': 'read_ticket', 'arguments': {'ticket_id': state.authorized_ticket_ids[0]}}
        elif not state.triage:
            p = minimum_priority(state.ticket)
            d = {'status': 'continue', 'action': 'set_triage', 'arguments': {
                'ticket_id': state.ticket.ticket_id, 'team': required_team(state.ticket),
                'priority': 'normal' if p == 'low' else p,
                'rationale': 'Applied the trusted category, impact, outage and security routing policy.'}}
        elif not state.draft:
            d = {'status': 'continue', 'action': 'draft_reply', 'arguments': {
                'ticket_id': state.ticket.ticket_id,
                'text': f'Thank you for reporting ticket {state.ticket.ticket_id}. Your report is prepared for review by our {state.triage.team.replace("_", " ")} team. This is an unsent draft; no fix, refund or account change has been performed.'}}
        else:
            d = {'status': 'completed'}
        return ModelResult(json.dumps(d))

class LiveModel:
    def __init__(self, name, transport=None):
        if not re.fullmatch(r'[A-Za-z0-9._-]{1,120}', name):
            raise ProviderError('invalid_model_identifier')
        self.name, self.transport = name, transport

    async def decide(self, messages, state):
        daily_calls.reserve()
        if settings.model_provider == 'gemini':
            key = settings.gemini_api_key.get_secret_value()
            url = f'https://generativelanguage.googleapis.com/v1beta/models/{self.name}:generateContent'
            headers = {'x-goog-api-key': key}
            payload = {
                'systemInstruction': {'parts': [{'text': messages[0]['content']}]},
                'contents': [{'role': 'user', 'parts': [{'text': messages[1]['content']}]}],
                'generationConfig': {'temperature': 0, 'maxOutputTokens': settings.max_output_tokens,
                                     'responseMimeType': 'application/json',
                                     'responseJsonSchema': AgentDecision.model_json_schema()},
            }
        elif settings.model_provider == 'anthropic':
            key = settings.anthropic_api_key.get_secret_value()
            url = 'https://api.anthropic.com/v1/messages'
            headers = {'x-api-key': key, 'anthropic-version': '2023-06-01'}
            payload = {'model': self.name, 'system': messages[0]['content'],
                       'messages': [messages[1]], 'max_tokens': settings.max_output_tokens}
        else:
            raise ProviderError('provider_not_configured')
        if not key:
            raise ProviderError('provider_key_missing')
        try:
            async with httpx.AsyncClient(timeout=settings.model_timeout_seconds, transport=self.transport) as client:
                response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                raise ProviderError('provider_rate_limit' if response.status_code == 429 else 'provider_http_error',
                                    response.status_code == 429 or response.status_code >= 500)
            data = response.json()
            if settings.model_provider == 'gemini':
                candidate = data.get('candidates', [{}])[0]
                raw = ''.join(p.get('text', '') for p in candidate.get('content', {}).get('parts', []) if not p.get('thought'))
                usage = data.get('usageMetadata', {})
                incoming = usage.get('promptTokenCount')
                outgoing = usage.get('candidatesTokenCount')
                if outgoing is not None:
                    outgoing += usage.get('thoughtsTokenCount', 0)
            else:
                raw = ''.join(p.get('text', '') for p in data.get('content', []) if p.get('type') == 'text')
                usage = data.get('usage', {})
                incoming, outgoing = usage.get('input_tokens'), usage.get('output_tokens')
            if not raw:
                raise ProviderError('provider_empty_response', True)
            if len(raw.encode()) > 20000:
                raise ProviderError('provider_output_too_large')
            # Missing or malformed usage stays unknown rather than fabricating zero.
            incoming = incoming if type(incoming) is int and incoming >= 0 else None
            outgoing = outgoing if type(outgoing) is int and outgoing >= 0 else None
            return ModelResult(raw, incoming, outgoing)
        except httpx.TimeoutException:
            raise ProviderError('provider_timeout', True) from None
        except httpx.RequestError:
            raise ProviderError('provider_unavailable', True) from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError('provider_malformed_response', True) from None

def get_model(name):
    if name not in settings.enabled_models():
        raise ProviderError('model_not_configured')
    return DemoModel() if name == 'demo' else LiveModel(name)
