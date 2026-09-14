"""Load individual reviews of exact, already saved source photographs."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

REVIEW='reviews/targeted-micrographs-20260914.json'

def apply(root: Path, decisions: dict, evidence: list) -> None:
    p=root/REVIEW
    if not p.exists():return
    spec=json.loads(p.read_text(encoding='utf-8'))
    rows=spec['records'];seen=set();applied=0
    if len(rows)!=spec['reviewedCount']:raise ValueError('Individual review count mismatch')
    for item in rows:
        path=(root/item['metadataPath']).resolve()
        if not path.is_relative_to(root/'reference/metadata'):raise ValueError('Invalid metadata review path')
        rec=json.loads(path.read_text(encoding='utf-8'));key=rec['targetId']+'|'+rec['assetId']
        if key in seen:raise ValueError('Duplicate individual review')
        seen.add(key)
        if rec['targetId']!=item['targetId'] or rec['assetId']!=item['assetId']:raise ValueError('Reviewed image identity mismatch')
        if rec['acquisitionBatch']!='batches/targeted-micrographs-20260914':raise ValueError('Unexpected acquisition batch')
        master=root/rec['files']['master'];digest=hashlib.sha256(master.read_bytes()).hexdigest()
        if digest!=item['masterSha256'] or digest!=rec['sha256']['master']:raise ValueError('Review is not bound to the actual saved image')
        role=item['recommendedRole']
        if role not in ('primary','supplementary','exclude'):raise ValueError('Invalid role')
        if not item.get('viewedIndividually') or not item.get('noteJa'):raise ValueError('Actual individual review required')
        decisions[key]={'status':'screened','recommendedRole':role,'reviewer':spec['reviewer'],'reviewedAt':spec['reviewedAt'],'method':spec['method'],'reviewFile':REVIEW,'noteJa':item['noteJa'],'masterSha256':digest,'sourceIdentityEvidence':rec['sourceIdentityEvidence'],'sourceAlreadyProcessedNote':rec['sourceAlreadyProcessedNote'],'speciesIdentity':'explicit_source_taxon_mapping_not_independent_reidentification','fullResolutionInspection':'saved_JPEG_viewed_individually_not_original_source_pixel_audit'}
        applied+=1
    evidence.append({'file':REVIEW,'count':len(rows),'adoptedPhotoPairs':applied,'kind':'individually_viewed_exact_source_micrographs'})
