"""Deterministic domain constraints; no matching of Arena example phrases."""
import re
from app.models import Ticket

POLICY = {
    'teams': {'billing': 'billing', 'technical': 'engineering', 'account': 'account_support', 'general': 'general_support'},
    'priority': 'Security risk or all-users outage: urgent. Other outage or team impact: at least high. Otherwise normal or low.',
    'boundary': 'Sandbox triage and unsent drafts only. No sending, refunds, deletion, account changes, or arbitrary tools.',
    'completion': 'Read one authorized ticket, validate its triage, and save one unsent reply draft.',
}

def ticket_ids(text):
    return list(dict.fromkeys(re.findall(r'\bT[0-9]{4}\b', text.upper())))

def requests_real_world_action(text):
    """Reject explicit consequential requests before exposing sandbox tools.

    This checks only the active user goal. Ticket bodies and external notes never
    enter this authority gate; the tool allowlist remains the final boundary.
    """
    text = text.lower()
    if re.search(r'\b(?:issue|process|grant|give|make)\b.{0,40}\brefund\b', text) or re.search(
            r'\brefund\s+(?:the|this|customer|user|ticket|charge|payment)\b', text):
        return True
    if re.search(r'\b(delete|erase)\b', text):
        return True
    if re.search(r'\b(send|deliver|dispatch|post)\b', text) and re.search(
            r'\b(customer|user|person|message|email|reply|notification|letter)\b', text):
        return True
    if re.search(r'\bemail\s+(?:(?:the|a|an)\s+)?(?:customer|user|person)\b', text):
        return True
    if re.search(r'\b(change|modify|update|reset|disable)\b', text) and re.search(
            r'\b(account|password|credential|subscription|payment)\b', text):
        return True
    if re.search(r'\b(reveal|show|expose|print)\b', text) and re.search(
            r'\b(key|secret|password|credential|token)\b', text):
        return True
    return False

def required_team(ticket: Ticket):
    return 'security' if ticket.security_risk else POLICY['teams'][ticket.category]

def minimum_priority(ticket: Ticket):
    if ticket.security_risk or (ticket.service_down and ticket.impact == 'all_users'):
        return 'urgent'
    if ticket.service_down or ticket.impact == 'team':
        return 'high'
    return 'low'

def resolve_goal(task, pending_goal=None):
    # A bare identifier answers a clarification; a new explicit request replaces it.
    if pending_goal and re.fullmatch(r'\s*T[0-9]{4}\s*[.!]?\s*', task, re.I):
        return re.sub(r'\bT[0-9]{4}\b', task.strip().rstrip('.!').upper(), pending_goal, flags=re.I) + '\nUser clarification: ' + task.strip()
    return task
