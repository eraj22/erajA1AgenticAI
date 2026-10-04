"""Arena requests are isolated; chat history is supplied explicitly."""
import logging
from time import perf_counter
from app.agent import run_agent
from app.models import ArenaResponse

log = logging.getLogger('arena')

async def execute(request, history=None, model='demo', goal=None, model_client=None):
    started = perf_counter()
    try:
        result = await run_agent(request.model_copy(deep=True), history or [], model, goal, model_client)
        result = ArenaResponse.model_validate(result)
    except Exception:
        # Do not log raw prompts, provider exceptions, API keys, or customer text.
        log.error('agent_internal_error request=%s', request.request_id)
        result = ArenaResponse(request_id=request.request_id, status='failed',
                               final_response='The run stopped due to an internal error.', stop_reason='internal_error')
    result.metrics.latency_ms = (perf_counter() - started) * 1000
    if len(result.model_dump_json().encode()) > 50000:
        result = ArenaResponse(request_id=request.request_id, status='failed',
            final_response='The response exceeded its size limit.', stop_reason='response_too_large',
            steps=result.steps, metrics=result.metrics)
    log.info('request=%s status=%s steps=%s stop=%s', request.request_id, result.status, result.steps, result.stop_reason)
    return result
