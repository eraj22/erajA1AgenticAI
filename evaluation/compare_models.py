"""Two configured LIVE models, ten shared tasks. Never synthesizes results."""
import argparse
import asyncio
import json
import sys
from uuid import uuid4
from urllib.parse import urlparse
import httpx
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.arena import execute
from app.models import ArenaRequest
from evaluation.checks import check_result, action_selection_correct

async def compare(models, url=None, pause_seconds=0):
    cases=json.loads(Path(__file__).with_name('model_cases.json').read_text())
    output={'generated_at':datetime.now(timezone.utc).isoformat(),
            'provider': 'groq' if url else settings.model_provider,
            'prices_usd_per_million': None if url else json.loads(settings.model_prices_json),
            'execution': 'deployed' if url else 'local', 'base_url': url, 'models':[]}
    async with httpx.AsyncClient(timeout=50) as client:
      for model in models:
        rows=[]
        for case in cases:
            if url:
                body={**case['request'], 'session_id': str(uuid4()), 'model': model}
                response=await client.post(url.rstrip('/')+'/chat', json=body)
                response.raise_for_status()
                result=response.json()
            else:
                result=(await execute(ArenaRequest.model_validate(case['request']),model=model)).model_dump()
            checks=check_result(case,result)
            validation=[e for e in result['events'] if e.get('event')=='validation']
            rows.append({'name':case['name'],'success':all(checks.values()),'checks':checks,
                         'correct_action_selection':action_selection_correct(case,result),
                         'valid_decisions':sum(e['passed'] for e in validation),'validated_decisions':len(validation),'response':result})
            print(model,case['name'],result['status'],flush=True)
            if url and result['metrics']['model_calls'] and pause_seconds:
                await asyncio.sleep(pause_seconds)
        metrics=[r['response']['metrics'] for r in rows]
        validated=sum(r['validated_decisions'] for r in rows)
        def total_if_known(field):
            values=[m[field] for m in metrics if m['model_calls']>0]
            return sum(values) if values and all(v is not None for v in values) else None
        usage_observed=[m for m in metrics if m['model_calls']>0 and m['input_tokens'] is not None
        output['models'].append({'model':model,'task_success':sum(r['success'] for r in rows)/len(rows),
            'contract_validity':sum(r['valid_decisions'] for r in rows)/validated if validated else None,
            'correct_action_selection':sum(r['correct_action_selection'] for r in rows)/len(rows),
            'average_latency_ms':mean(m['latency_ms'] for m in metrics),
            'input_tokens':total_if_known('input_tokens'),'output_tokens':total_if_known('output_tokens'),
            'estimated_cost_usd':total_if_known('estimated_cost_usd'),
            'usage_coverage':{'observed_runs':len(usage_observed),
                              'model_call_runs':sum(m['model_calls']>0 for m in metrics)},
            'observed_input_tokens':sum(m['input_tokens'] for m in usage_observed),
            'observed_output_tokens':sum(m['output_tokens'] for m in usage_observed),
            'observed_cost_usd':sum(m['estimated_cost_usd'] for m in usage_observed
                                    if m['estimated_cost_usd'] is not None),
            'cases':rows})
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--models',nargs=2,required=True)
    p.add_argument('--url',help='Public HTTPS service URL; runs comparison through /chat without a local API key')
    p.add_argument('--pause-seconds',type=float,default=0,help='Delay after each remote model run to respect provider token limits')
    p.add_argument('--output',default='evaluation/results/model_comparison.json')
    args=p.parse_args()
    if args.url and (urlparse(args.url).scheme!='https' or not urlparse(args.url).netloc):
        p.error('--url must be the public HTTPS service URL')
    if args.pause_seconds < 0 or args.pause_seconds > 120:
        p.error('--pause-seconds must be between 0 and 120')
    if len(set(args.models))!=2 or any(m=='demo' or (not args.url and m not in settings.enabled_models()) for m in args.models):
        p.error('Choose two distinct configured live models; demo cannot fulfill this experiment.')
    output=asyncio.run(compare(args.models,args.url,args.pause_seconds))
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(output,indent=2),encoding='utf-8')
    print('Measured results saved. Review correctness and add an evidence-based selection rationale to README.')
    return 0

if __name__=='__main__': raise SystemExit(main())
