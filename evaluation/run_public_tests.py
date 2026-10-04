"""HTTP checks against a local or public service; live calls can incur cost."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluation.checks import check_result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8000')
    parser.add_argument('--output',default='evaluation/results/public_results.json')
    args=parser.parse_args()
    cases=json.loads(Path(__file__).with_name('public_cases.json').read_text())
    rows=[]
    with httpx.Client(base_url=args.url.rstrip('/'),timeout=65) as client:
        health=client.get('/health'); health.raise_for_status()
        manifest=client.get('/arena/manifest'); manifest.raise_for_status()
        for case in cases:
            try:
                response=client.post('/arena/run',json=case['request']); response.raise_for_status()
                result=response.json()
                checks=check_result(case,result)
                rows.append({'name':case['name'],'passed':all(checks.values()),'checks':checks,'response':result})
            except (httpx.HTTPError,ValueError,KeyError) as exc:
                rows.append({'name':case['name'],'passed':False,'error_type':type(exc).__name__})
            print(('PASS ' if rows[-1]['passed'] else 'FAIL ')+case['name'])
        model=health.json().get('default_model','')
        session='public-evaluation-clarification'
        first=client.post('/chat',json={'session_id':session,'task':'Triage ticket','model':model})
        second=client.post('/chat',json={'session_id':session,'task':'T1001','model':model})
        valid=first.status_code==second.status_code==200 and first.json().get('status')=='needs_clarification' and second.json().get('status')=='completed'
        rows.append({'name':'Multi-turn clarification','passed':valid,'responses':[first.json(),second.json()]})
        client.delete('/chat/'+session)
    output={'generated_at':datetime.now(timezone.utc).isoformat(),'base_url':args.url,
            'mode':health.json().get('mode'),'health':health.json(),'manifest':manifest.json(),
            'passed':sum(r['passed'] for r in rows),'total':len(rows),
            'notice':'Local/scripted results are not live-model reliability evidence or an Arena score.','cases':rows}
    path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(f"{output['passed']}/{output['total']} checks passed")
    return 0 if output['passed']==output['total'] else 1

if __name__=='__main__': raise SystemExit(main())

