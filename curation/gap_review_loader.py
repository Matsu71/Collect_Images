"""Bind visual decisions to immutable photos and validate any explicit taxon correction."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path


def resolve_target(root: Path, spec: dict, candidate: dict) -> dict:
    correction=spec.get('retargetedCandidates',{}).get(str(candidate['number']))
    if not correction:return candidate['target']
    targets=json.loads((root/'data/targets.json').read_text(encoding='utf-8'))['records']
    target=next((t for t in targets if t['id']==correction['targetId']),None)
    if not target or target['scientificName']!=correction['scientificName']:
        raise ValueError('Retargeted organism is not an exact existing collection target')
    if target['scientificName'].lower() not in candidate.get('sourceCaption','').lower():
        raise ValueError('Source caption does not explicitly name the corrected subject')
    if not correction.get('reasonJa'):raise ValueError('A target correction needs its explicit reason')
    return target


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
            target=resolve_target(root,spec,c)
            paths=list((root/'reference/metadata').glob('*/'+c['assetId']+'.json'))
            matches=[]
            for p in paths:
                r=json.loads(p.read_text())
                if r['targetId']==target['id'] and r.get('reviewedPreviewSha256')==c['previewSha256']:
                    matches.append(r)
            if not matches:awaiting+=1;continue
            default=spec.get('defaultNotesJa',{}).get(role,'主体の輪郭・主要な形が一覧上で明瞭。' if role=='primary' else '部分・別角度・生態等の補足写真。')
            decisions[target['id']+'|'+c['assetId']]={
                'status':'screened','recommendedRole':role,'reviewer':spec['reviewer'],
                'reviewedAt':spec['reviewedAt'],'method':spec['method'],
                'reviewFile':'reviews/gap-20260914.json','snapshotNumber':n,
                'candidateManifestSha256':spec['candidateManifestSha256'],
                'previewPath':c['previewPath'],'previewSha256':c['previewSha256'],
                'sourceCaption':c.get('sourceCaption',''),
                'sourceSearchTargetId':c['target']['id'],
                'targetCorrection':spec.get('retargetedCandidates',{}).get(str(n)),
                'noteJa':spec.get('notesJa',{}).get(str(n),default),
                'speciesIdentity':'source_name_and_caption_checked_not_independently_reidentified',
                'fullResolutionInspection':'contact_sheet_screening; source_preview_up_to_1280px_retained'
            };adopted+=1
    if len(visited)!=spec['reviewedCount'] or visited!=set(candidates):
        raise ValueError('Gap-review must partition every candidate exactly once')
    evidence.append({'file':'reviews/gap-20260914.json','count':len(visited),'candidateManifestSha256':spec['candidateManifestSha256'],'adoptedPhotoPairs':adopted,'rejectedPreviewCandidates':excluded,'selectedAwaitingMasterSave':awaiting,'explicitTargetCorrections':len(spec.get('retargetedCandidates',{})),'kind':'new_gap_photos_visual_screening'})
