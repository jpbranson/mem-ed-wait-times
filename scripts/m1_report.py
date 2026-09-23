"""Produce the bounded evidence JSON used by docs/m1-validation.md."""

import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from edwait.analysis import BaselineIndex, DEFAULT_POLICY
from edwait.data import timestamp
from scripts.m1_replay import summarize


def main():
    report=json.loads(Path('.cache/m1-replay.json').read_text(encoding='utf-8'))
    rows=json.loads(Path('.cache/m1-comparisons.json').read_text(encoding='utf-8'))['28d-radius1']
    later=[r for r in rows if timestamp(r['at'])>=timestamp('2026-09-07T00:00:00Z')]
    examples=[]
    for facility in ['memphis','desoto','crittenden','arlington','baptist-medical-center-yazoo']:
        cases=[r for r in later if r['facility']==facility and r['delta'] is not None]
        examples.extend([dict(min(cases,key=lambda r:r['delta']),example='low_deviation'),
                         dict(max(cases,key=lambda r:r['delta']),example='high_deviation')])
    examples.append(dict(next(r for r in rows if r['delta'] is None),example='sparse_startup'))
    examples.append(dict(next(r for r in rows if r['group']=='all_days' and r['delta'] is not None),example='broader_fallback'))
    snapshot=json.loads(Path('.cache/m1-history.json').read_text(encoding='utf-8'))
    index=BaselineIndex(snapshot['records'])
    for example in examples:
        example['trend']=index.trend(example['facility'],example['at'],example['value'])
    sensitivity=[]
    for tail in (5,10,15):
        for minimum in (5,10,15):
            entry={'tail_percent':tail,'minimum_minutes':minimum}
            selection=[r for r in rows if timestamp(r['at'])<timestamp('2026-09-07T00:00:00Z')]
            for label,period in [('selection',selection),('later',later)]:
                supported=[r for r in period if r['delta'] is not None]
                count=sum((r['percentile']>=100-tail and r['delta']>=minimum) or
                          (r['percentile']<=tail and r['delta']<=-minimum) for r in supported)
                entry[label]={'supported':len(supported),'flagged':count,'fraction':count/len(supported)}
            sensitivity.append(entry)
    report['selected_policy']=DEFAULT_POLICY
    report['selected_candidate']='28d-radius1'
    report['unusualness_sensitivity']=sensitivity
    report['later_by_facility']={f:summarize([r for r in later if r['facility']==f]) for f in sorted({r['facility'] for r in later})}
    report['examples']=examples
    Path('docs/m1-replay-evidence.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'examples':len(examples),'unusualness_sensitivity':sensitivity},indent=2))


if __name__ == '__main__':
    main()
