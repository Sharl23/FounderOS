"""Optional manual API smoke test. Uses live model; never invents results."""
import json, os, sys, urllib.request, urllib.error
BASE = os.getenv('FOUNDEROS_URL','http://localhost:8000')

def post(path, obj, token=None):
    headers={'Content-Type':'application/json'}
    if token: headers['X-Project-Token']=token
    req=urllib.request.Request(BASE+path, data=json.dumps(obj).encode(),headers=headers)
    with urllib.request.urlopen(req,timeout=180) as resp: return json.load(resp)

if __name__=='__main__':
    project=post('/api/projects', {'idea':'A minimal study planner app for Cairo university students with no paid APIs.',
                                  'budget':'100 USD','timeline':'4 weeks','target_market':'Cairo'})
    pid,token=project['project_id'],project['access_token']
    print('Created project',pid,'\nToken (DO NOT SHARE OR COMMIT):',token)
    print('Refinement:',json.dumps(post(f'/api/projects/{pid}/refine',{},token),indent=2))
    print('Discovery:',json.dumps(post(f'/api/projects/{pid}/phases/discover/run',{},token),indent=2))
    print('Stopped at mandatory founder gate; no auto-approval performed.')
