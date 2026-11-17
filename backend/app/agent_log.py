"""Agent action log: one row per agent action, exported as the root decision_log.json.

Required keys per entry: timestamp, agent, action, sources (list of URLs), model (string or null),
cost (USD number; 0 for local models), approved_by ("founder" for gated actions, else null).
"""
from __future__ import annotations
import json
import uuid

from .db import now

RUN_TAG = None   # set by the demo runner so one run's log can be exported on its own


def record(db, pid, agent: str, action: str, *, sources=None, model=None, approved_by=None, outcome=None, detail=None, cost=0.0):
    if isinstance(model, str) and model.startswith('NOT_CALLED'):   # the step skipped the model (e.g. safety block): no AI ran
        detail = {**(detail or {}), 'model_not_called': model}
        model = None
    sources = [s for s in (sources or []) if isinstance(s, str) and s.startswith(('http://', 'https://'))]
    db.execute('INSERT INTO agent_actions(id,project_id,run_tag,ts,agent,action,sources_json,model,cost,approved_by,outcome,detail_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
               (uuid.uuid4().hex, pid, RUN_TAG, now(), agent, action, json.dumps(sorted(set(sources))), model, float(cost),
                approved_by, outcome, json.dumps(detail or {}, ensure_ascii=False, default=str)))


def entries(db, pid=None, run_tag=None) -> list[dict]:
    sql, args = 'SELECT * FROM agent_actions WHERE 1=1', []
    if pid:
        sql += ' AND project_id=?'
        args.append(pid)
    if run_tag:
        sql += ' AND run_tag=?'
        args.append(run_tag)
    rows = db.execute(sql + ' ORDER BY ts, rowid', args).fetchall()
    out = []
    for r in rows:
        e = {'timestamp': r['ts'], 'agent': r['agent'], 'action': r['action'], 'sources': json.loads(r['sources_json']),
             'model': r['model'], 'cost': r['cost'], 'approved_by': r['approved_by']}
        if r['outcome'] is not None:
            e['outcome'] = r['outcome']
        e['venture_id'] = r['project_id']
        out.append(e)
    return out
