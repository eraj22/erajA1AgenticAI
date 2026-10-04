"""HTTP checks against a local or public service; live calls can incur cost."""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluation.checks import check_result

def post_with_connect_retries(client, route, body):
    for attempt in range(3):
        try:
            return client.post(route,json=body)
        except httpx.ConnectError:
            if attempt==2: raise
            time.sleep(2*(attempt+1))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8000')
    parser.add_argument('--output',default='evaluation/results/public_results.json')
    parser.add_argument('--pause-seconds',type=float,default=0,help='Delay after live model runs for provider token limits')
    args=parser.parse_args()
    if args.pause_seconds < 0 or args.pause_seconds > 120: parser.error('--pause-seconds must be between 0 and 120')
    cases=json.loads(Path(__file__).with_name('public_cases.json').read_text())
    rows=[]
    with httpx.Client(base_url=args.url.rstrip('/'),timeout=65) as client:
        health=client.get('/health'); health.raise_for_status()
        manifest=client.get('/arena/manifest'); manifest.raise_for_status()
        for case in cases:
            try:
                response=post_with_connect_retries(client,'/arena/run',case['request']); response.raise_for_status()
                result=response.json()
                checks=check_result(case,result)
                rows.append({'name':case['name'],'passed':all(checks.values()),'checks':checks,'response':result})
            except (httpx.HTTPError,ValueError,KeyError) as exc:
                rows.append({'name':case['name'],'passed':False,'error_type':type(exc).__name__})
            print(('PASS ' if rows[-1]['passed'] else 'FAIL ')+case['name'],flush=True)
            if args.pause_seconds and rows[-1].get('response',{}).get('metrics',{}).get('model_calls',0):
                time.sleep(args.pause_seconds)
        model=health.json().get('default_model','')
        session=str(uuid4())
        try:
            first=post_with_connect_retries(client,'/chat',{'session_id':session,'task':'Triage ticket','model':model})
            if args.pause_seconds and first.status_code==200 and first.json().get('metrics',{}).get('model_calls',0):
                time.sleep(args.pause_seconds)
            second=post_with_connect_retries(client,'/chat',{'session_id':session,'task':'T1001','model':model})
            valid=first.status_code==second.status_code==200 and first.json().get('status')=='needs_clarification' and second.json().get('status')=='completed'
            rows.append({'name':'Multi-turn clarification','passed':valid,'responses':[first.json(),second.json()]})
        except (httpx.HTTPError,ValueError,KeyError) as exc:
            rows.append({'name':'Multi-turn clarification','passed':False,'error_type':type(exc).__name__})
        try: client.delete('/chat/'+session)
        except httpx.HTTPError: pass
    output={'generated_at':datetime.now(timezone.utc).isoformat(),'base_url':args.url,
            'mode':health.json().get('mode'),'health':health.json(),'manifest':manifest.json(),
            'passed':sum(r['passed'] for r in rows),'total':len(rows),
            'notice':('Measured live-model public checks; not the hidden Arena score.' if health.json().get('mode')=='live'
                      else 'Local/scripted results are not live-model reliability evidence or an Arena score.'),'cases':rows}
    path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(f"{output['passed']}/{output['total']} checks passed")
    return 0 if output['passed']==output['total'] else 1

if __name__=='__main__': raise SystemExit(main())
