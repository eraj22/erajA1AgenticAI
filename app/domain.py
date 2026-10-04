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

