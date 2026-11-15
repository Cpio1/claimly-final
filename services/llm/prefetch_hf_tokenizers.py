"""Explicit public tokenizer/config download; never downloads chat weights or runs paid inference."""
import hashlib
import json
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download
from services.llm.app.config import ROOT, MODEL_EMBED, MODEL_CHAT

def main():
    lock = {}
    api = HfApi()
    for role, repo in [('embedding',MODEL_EMBED),('chat',MODEL_CHAT)]:
        info = api.model_info(repo)
        directory = ROOT/'services/llm/.hf-models'/role
        snapshot_download(repo,revision=info.sha,local_dir=directory,
                          allow_patterns=['tokenizer.json','tokenizer_config.json','special_tokens_map.json',
                                          'config.json','chat_template.jinja','added_tokens.json','vocab.json','merges.txt'])
        lock[role] = {'model':repo,'revision':info.sha,
                      'files':{str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in directory.rglob('*') if p.is_file() and '.cache' not in p.parts}}
        print(role,repo,'tokenizer/config pinned to',info.sha)
    (ROOT/'services/llm/hf-models.lock.json').write_text(json.dumps(lock,indent=2)+'\n')

if __name__=='__main__': main()
