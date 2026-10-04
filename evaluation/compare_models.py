"""Two configured LIVE models, ten shared tasks. Never synthesizes results."""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.arena import execute
from app.models import ArenaRequest
from evaluation.checks import check_result, action_selection_correct

async def compare(models):
    cases=json.loads(Path(__file__).with_name('model_cases.json').read_text())
    output={'generated_at':datetime.now(timezone.utc).isoformat(),'provider':settings.model_provider,
            'prices_usd_per_million':json.loads(settings.model_prices_json),'models':[]}
    for model in models:
        rows=[]
        for case in cases:
            result=(await execute(ArenaRequest.model_validate(case['request']),model=model)).model_dump()
            checks=check_result(case,result)
            validation=[e for e in result['events'] if e.get('event')=='validation']
            rows.append({'name':case['name'],'success':all(checks.values()),'checks':checks,
                         'correct_action_selection':action_selection_correct(case,result),
                         'valid_decisions':sum(e['passed'] for e in validation),'validated_decisions':len(validation),'response':result})
            print(model,case['name'],result['status'],flush=True)
        metrics=[r['response']['metrics'] for r in rows]
        validated=sum(r['validated_decisions'] for r in rows)
        def total_if_known(field):
            values=[m[field] for m in metrics if m['model_calls']>0]
            return sum(values) if values and all(v is not None for v in values) else None
        output['models'].append({'model':model,'task_success':sum(r['success'] for r in rows)/len(rows),
            'contract_validity':sum(r['valid_decisions'] for r in rows)/validated if validated else None,
            'correct_action_selection':sum(r['correct_action_selection'] for r in rows)/len(rows),
            'average_latency_ms':mean(m['latency_ms'] for m in metrics),
            'input_tokens':total_if_known('input_tokens'),'output_tokens':total_if_known('output_tokens'),
            'estimated_cost_usd':total_if_known('estimated_cost_usd'),'cases':rows})
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--models',nargs=2,required=True)
    p.add_argument('--output',default='evaluation/results/model_comparison.json')
    args=p.parse_args()
    if len(set(args.models))!=2 or any(m=='demo' or m not in settings.enabled_models() for m in args.models):
        p.error('Choose two distinct configured live models; demo cannot fulfill this experiment.')
    output=asyncio.run(compare(args.models))
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(output,indent=2),encoding='utf-8')
    print('Measured results saved. Review correctness and add an evidence-based selection rationale to README.')
    return 0

if __name__=='__main__': raise SystemExit(main())
