"""Load gap-photo visual decisions without treating an unreviewed download as approved."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path


def apply(root: Path, decisions: dict, evidence: list) -> None:
    review=root/'reviews/gap-20260914.json'
    manifest=root/'batches/gaps-20260914/candidates.json'
    if not review.exists():return
    if not manifest.exists():raise ValueError('Visual decisions lack their candidate manifest')
    spec=json.loads(review.read_text(encoding='utf-8'))
    if hashlib.sha256(manifest.read_bytes()).hexdigest()!=spec['candidateManifestSha256']:
        raise ValueError('Gap-review snapshot no longer matches the recorded hash')
    candidates={c['number']:c for c in json.loads(manifest.read_text())['records']}
    visited=set();adopted=0;excluded=0;awaiting=0
    for role,field in [('primary','primaryNumbers'),('supplementary','supplementaryNumbers'),('exclude','excludeNumbers')]:
        for n in spec.get(field,[]):
            if n in visited or n not in candidates:raise ValueError('Unknown or duplicate reviewed candidate')
            visited.add(n);c=candidates[n]
            if role=='exclude':excluded+=1;continue
            paths=list((root/'reference/metadata').glob('*/'+c['assetId']+'.json'))
            matches=[]
            for p in paths:
                r=json.loads(p.read_text())
                if r['targetId']==c['target']['id'] and r.get('reviewedPreviewSha256')==c['previewSha256']:
                    matches.append(r)
            if not matches:awaiting+=1;continue
            decisions[c['target']['id']+'|'+c['assetId']]={
                'status':'screened','recommendedRole':role,'reviewer':spec['reviewer'],
                'reviewedAt':spec['reviewedAt'],'method':spec['method'],
                'reviewFile':'reviews/gap-20260914.json','snapshotNumber':n,
                'candidateManifestSha256':spec['candidateManifestSha256'],
                'previewPath':c['previewPath'],'previewSha256':c['previewSha256'],
                'sourceCaption':c.get('sourceCaption',''),
                'noteJa':spec.get('notesJa',{}).get(str(n),'主体の輪郭・主要な形が一覧上で明瞭。' if role=='primary' else '部分・別角度・生態等の補足写真。'),
                'speciesIdentity':'source_name_and_caption_checked_not_independently_reidentified',
                'fullResolutionInspection':'contact_sheet_screening; source_preview_up_to_1280px_retained'
            };adopted+=1
    if len(visited)!=spec['reviewedCount']:raise ValueError('Gap-review count does not match its decisions')
    evidence.append({'file':'reviews/gap-20260914.json','count':len(visited),'candidateManifestSha256':spec['candidateManifestSha256'],'adoptedPhotoPairs':adopted,'rejectedPreviewCandidates':excluded,'selectedAwaitingMasterSave':awaiting,'kind':'new_gap_photos_visual_screening'})
