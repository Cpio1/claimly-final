"""Expire private quarantine and demo-session data. Called by the durable worker."""
from datetime import datetime,timezone
import json
import time
from services.llm.app.contracts import Failure
from .db import objects,get,put,now,encoded

def cleanup(db,storage,*,quarantine_hours=24):
    stamp=time.time();removed=0
    with db.tx(write=True) as c:
        expired=c.execute('SELECT id FROM claimly_sessions WHERE expires<?',(stamp,)).fetchall()
        for session in expired:
            owner=session['id']
            for doc,private in objects(c,owner,'document'):
                storage.delete(private['storage_key'])
            c.execute('DELETE FROM claimly_sessions WHERE id=?',(owner,));removed+=1
        cutoff=stamp-quarantine_hours*3600
        rows=c.execute("SELECT id,session_id,body,private FROM claimly_objects WHERE kind='document'").fetchall()
        for row in rows:
            doc=json.loads(row['body']);private=json.loads(row['private']);owner=row['session_id']
            if private.get('deleted'):
                storage.delete(private['storage_key'])
                c.execute('DELETE FROM claimly_objects WHERE id=? AND session_id=?',(doc['id'],owner));removed+=1
                continue
            created=datetime.fromisoformat(doc['created_at'].replace('Z','+00:00')).timestamp()
            if created>=cutoff or private.get('quality_review') or doc['status']=='ready':continue
            storage.delete(private['storage_key'])
            c.execute('DELETE FROM claimly_objects WHERE id=? AND session_id=?',(doc['id'],owner))
            try:
                entry,ep=get(c,owner,'entry',doc['entry_id'])
                entry['document_ids']=[x for x in entry['document_ids'] if x!=doc['id']]
                if not entry['document_ids'] and not ep.get('admitted'):
                    c.execute('DELETE FROM claimly_objects WHERE id=? AND session_id=?',(entry['id'],owner))
                else:put(c,owner,'entry',entry,ep)
            except Failure:pass
            for jr in c.execute("SELECT id,body,payload FROM claimly_jobs WHERE session_id=? AND status IN ('running','queued')",(owner,)).fetchall():
                if json.loads(jr['payload']).get('document_id')==doc['id']:
                    jb=json.loads(jr['body']);jb.update(status='stale',result=None,error=None,updated_at=now())
                    c.execute("UPDATE claimly_jobs SET status='stale',body=?,lease_token=NULL WHERE id=?",(encoded(jb),jr['id']))
            removed+=1
        # Empty draft entries created before invalid uploads are not ordinary Vault rows.
        for row in c.execute("SELECT id,session_id,body,private FROM claimly_objects WHERE kind='entry'").fetchall():
            body=json.loads(row['body']);private=json.loads(row['private'])
            created=datetime.fromisoformat(body['created_at'].replace('Z','+00:00')).timestamp()
            if created<cutoff and not private.get('admitted') and not body['document_ids']:
                c.execute('DELETE FROM claimly_objects WHERE id=? AND session_id=?',(row['id'],row['session_id']))
    return removed
