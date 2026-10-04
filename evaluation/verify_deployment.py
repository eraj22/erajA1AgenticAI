"""Public HTTPS interface, required APIs and clarification without login."""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
import httpx

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',required=True)
    parser.add_argument('--output',default='evaluation/results/deployment_verification.json')
    parser.add_argument('--pause-seconds',type=float,default=0,help='Delay between live provider runs')
    args=parser.parse_args()
    if args.pause_seconds < 0 or args.pause_seconds > 120: parser.error('--pause-seconds must be between 0 and 120')
    url=args.url.rstrip('/')
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname in ('localhost','127.0.0.1','::1') or not parsed.hostname:
        parser.error('Supply the public HTTPS application URL.')
    checks={}
    with httpx.Client(base_url=url,timeout=65,follow_redirects=False) as c:
        for route in ['/','/health','/arena/manifest','/docs']:
            response=c.get(route); checks[route]={'http_status':response.status_code,'passed':response.status_code==200}
        health=c.get('/health').json()
        checks['live_model']={'passed':health.get('live_model_configured') is True and health.get('mode')=='live'}
        r=c.post('/arena/run',json={'task':'Triage T1001'})
        checks['arena']={'http_status':r.status_code,'passed':r.status_code==200 and r.json().get('status')=='completed','response':r.json()}
        if args.pause_seconds and r.json().get('metrics',{}).get('model_calls',0):
            time.sleep(args.pause_seconds)
        sid=str(uuid4())
        a=c.post('/chat',json={'session_id':sid,'task':'Triage ticket','model':health.get('default_model')})
        if args.pause_seconds and a.status_code==200 and a.json().get('metrics',{}).get('model_calls',0):
            time.sleep(args.pause_seconds)
        b=c.post('/chat',json={'session_id':sid,'task':'T1001','model':health.get('default_model')})
        checks['clarification']={'passed':a.status_code==b.status_code==200 and a.json().get('status')=='needs_clarification' and b.json().get('status')=='completed'}
        c.delete('/chat/'+sid)
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'url':url,'passed':all(v['passed'] for v in checks.values()),'checks':checks}
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));return 0 if report['passed'] else 1

if __name__=='__main__': raise SystemExit(main())
