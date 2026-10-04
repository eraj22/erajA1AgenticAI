import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from app.config import ROOT, settings
from app.models import ArenaRequest, ArenaResponse, ChatRequest
from app.arena import execute
from app.domain import resolve_goal

router = APIRouter()

@router.get('/')
def index():
    return FileResponse(ROOT / 'app/static/index.html')

@router.get('/health')
def health():
    live = [m for m in settings.enabled_models() if m != 'demo']
    return {'status': 'ok', 'implementation': 'ticketpilot', 'live_model_configured': bool(live),
            'default_model': settings.model_name, 'mode': 'live' if settings.model_name in live else 'offline-demo-or-unconfigured'}

@router.get('/arena/manifest')
def manifest():
    value = json.loads((ROOT / 'arena_manifest.json').read_text())
    value['limits'].update(max_steps=settings.max_steps, max_tool_retries=settings.max_tool_retries,
                           run_timeout_seconds=settings.run_timeout_seconds)
    return value

@router.get('/models')
def models():
    return {'models': settings.enabled_models(), 'default': settings.model_name, 'demo_models': ['demo'] if settings.enable_demo else []}

@router.get('/sample-tickets')
def samples():
    return {'tickets': [{k: t[k] for k in ('ticket_id', 'subject', 'category')} for t in json.loads((ROOT / 'data/sample_data.json').read_text())['tickets']]}

@router.post('/arena/run', response_model=ArenaResponse)
async def arena_run(payload: ArenaRequest, request: Request):
    admission = request.app.state.admission
    admission.enter()
    try:
        return await execute(payload, model=settings.model_name)
    finally:
        admission.leave()

@router.post('/chat', response_model=ArenaResponse)
async def chat(payload: ChatRequest, request: Request):
    selected_model = settings.model_name if payload.model == 'unconfigured' else payload.model
    if selected_model not in settings.enabled_models():
        raise HTTPException(400, 'Model is not enabled')
    busy = request.app.state.busy
    if payload.session_id in busy:
        raise HTTPException(409, 'This chat is already running')
    admission = request.app.state.admission
    admission.enter()
    busy.add(payload.session_id)
    memory = request.app.state.memory
    try:
        session = memory.get(payload.session_id)
        goal = resolve_goal(payload.task, session.pending_goal)
        result = await execute(payload, session.messages, selected_model, goal=goal)
        pending = goal if result.status == 'needs_clarification' else None
        memory.add(payload.session_id, payload.task, result.final_response, pending)
        return result
    finally:
        busy.discard(payload.session_id)
        admission.leave()

@router.delete('/chat/{session_id}')
def reset(session_id: str, request: Request):
    if session_id in request.app.state.busy:
        raise HTTPException(409, 'Chat is running')
    request.app.state.memory.clear(session_id)
    return {'status': 'cleared'}
