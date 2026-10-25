"""Hybrid coder v2: rule-based extraction + LLM coding WITH answers in context."""
import re, json, os, sys, time, urllib.request
from collections import Counter

DIR='/Users/simonwang/Workspace/wangfukcourtfirereport/data/markdown_all'

def clean(path):
    keep=[]
    for ln in open(path).read().split('\n'):
        if ln.startswith('<!-- page'): continue
        if re.fullmatch(r'\s*\d{1,3}\s*',ln): continue
        if re.fullmatch(r'\s*Page \d+\s*',ln): continue
        keep.append(ln)
    return '\n'.join(keep)

TURN=re.compile(r'(?m)^\s*([A-Z][A-Z \.\'\-]{2,60}):\s*')
BLK =re.compile(r'(?m)^\s*((?:Cross-)?(?:Re-)?Examination|Questions?)\s+by\s+([A-Z][A-Za-z \.\'\-]{2,60})\s*$')
WIT =re.compile(r'(?m)^\s*([A-Z][A-Z .,\'\-]{3,60})\s*\((affirmed|sworn)\)')

def parse(path):
    text=clean(path)
    blocks=[(m.start(),m.group(1),m.group(2).strip()) for m in BLK.finditer(text)]
    ms=list(TURN.finditer(text)); turns=[]
    for i,m in enumerate(ms):
        end=ms[i+1].start() if i+1<len(ms) else len(text)
        turns.append((m.start(), m.group(1).strip(), re.sub(r'\s+',' ',text[m.end():end]).strip()))
    out=[]
    for bi,(pos,kind,examiner) in enumerate(blocks):
        bend=blocks[bi+1][0] if bi+1<len(blocks) else len(text)
        decls=[m for m in WIT.finditer(text[:pos])]
        witness=decls[-1].group(1).strip() if decls else '?'
        qa=[]
        for ti,(s,spk,body) in enumerate(turns):
            if not (pos<=s<bend): continue
            if '?' not in body or 'A transcript by Epiq' in body: continue
            # collect the answer: following turns until the next question turn
            ans=[]
            for s2,spk2,b2 in turns[ti+1:ti+6]:
                if s2>=bend: break
                same = spk2.split(',')[0].strip() == witness.split(',')[0].strip()
                if '?' in b2 and not same: break
                if same: ans.append(b2)
                if len(' '.join(ans))>500: break
            qa.append({'speaker':spk,'q':body,'a':' '.join(ans)[:500]})
        out.append(dict(block=bi,kind=kind,examiner=examiner,witness=witness,n_q=len(qa),qa=qa))
    return out

PROMPT = """Code questions asked at a Hong Kong public inquiry into a fatal fire. Each item gives the question and the witness's answer.

IMPLEMENTATION - the answer requires knowing what was done, by whom, whether a procedure was followed, what happened, what a document says, or how a rule was applied in a particular case.
FORMULATION - the answer requires knowing why a rule, standard, guideline, penalty or delegation of authority was set as it was; who chose it; what alternatives were considered; or whether the rule itself was adequate.
PROCEDURAL - the question concerns the conduct of the hearing, a document reference, or a clarification with no substantive content.

Decisive test: could an officer who only applies the rule answer this? If yes, it is IMPLEMENTATION.

Worked examples:
- "Why do you not notify them in advance?" answered "We have to make an appointment" -> IMPLEMENTATION (the witness's own operational practice, not a policy choice).
- "Why is natural lighting required?" answered by explaining the purpose of the building regulation -> FORMULATION (the rationale of the rule itself).
- "Can we say this does not comply with section 16?" answered by applying the section to the facts -> IMPLEMENTATION.
- "What about imprisonment in relation to collusion?" answered by describing the statutory maximum -> FORMULATION (the penalty regime).
- "Let's go to page 650" -> PROCEDURAL.

Return ONLY a JSON array:
[{"i":1,"c":"IMPLEMENTATION","why":"short reason"}]

Items:
"""

def call(items, model='deepseek-chat'):
    key=os.environ['DEEPSEEK_API_KEY']
    body='\n'.join(f'{i+1}. Q: {it["q"][:450]}\n   A: {it["a"][:350]}' for i,it in enumerate(items))
    payload={'model':model,'messages':[{'role':'user','content':PROMPT+body}],'temperature':0,'max_tokens':2500}
    req=urllib.request.Request('https://api.deepseek.com/chat/completions',
        data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json','Authorization':f'Bearer {key}'})
    with urllib.request.urlopen(req,timeout=180) as r:
        txt=json.loads(r.read())['choices'][0]['message']['content']
    m=re.search(r'\[.*\]',txt,re.S)
    if not m: raise ValueError(txt[:200])
    return json.loads(m.group(0))

def code(qa,batch=25):
    out=[]
    for i in range(0,len(qa),batch):
        ch=qa[i:i+batch]
        for a in range(3):
            try:
                res=call(ch); got={r['i']:r for r in res}
                out+=[got.get(j+1,{'c':'UNCODED','why':''}) for j in range(len(ch))]
                break
            except Exception as e:
                if a==2: print('fail',e,file=sys.stderr); out+=[{'c':'ERROR','why':''}]*len(ch)
                time.sleep(2)
    return out

if __name__=='__main__':
    blocks=parse(sys.argv[1])
    allqa=[x for b in blocks for x in b['qa']]
    print(f"blocks={len(blocks)} questions={len(allqa)}")
    res=code(allqa)
    k=0
    for b in blocks:
        b['codes']=[r['c'] for r in res[k:k+b['n_q']]]
        b['why']=[r.get('why','') for r in res[k:k+b['n_q']]]
        k+=b['n_q']
    print('codes:',dict(Counter(c for b in blocks for c in b['codes'])))
    json.dump(blocks,open('/tmp/pilot/coded2.json','w'),indent=1)
    for b in blocks:
        c=Counter(b['codes'])
        print(f"  [{b['block']}] {b['witness'][:24]:<24} Q={b['n_q']:3d} impl={c['IMPLEMENTATION']:3d} form={c['FORMULATION']:3d} proc={c['PROCEDURAL']:3d}")
