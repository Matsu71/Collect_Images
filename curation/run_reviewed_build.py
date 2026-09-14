#!/usr/bin/env python3
"""Reviewed builder: explicit author gaps, individual follow-up, and all gap-photo rounds."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import build_collection as build
import gap_review_loader
import round2_photos
import round3_photos
import targeted_review_loader

ROOT=Path(__file__).resolve().parents[1]
DETAIL=ROOT/'reports/detail-sample-review.json'
UNKNOWN_AUTHOR='作者名未取得（CC0・出典参照）'
PLACEHOLDERS={'no rights reserved','some rights reserved','all rights reserved','unknown','anonymous'}
_original_verify=build.verify_record
_original_reviews=build.read_reviews

def verify_record(record):
    author=build.text(record.get('author',''))
    if author.lower() in PLACEHOLDERS:
        if record.get('licenseCode')!='cc0':
            raise ValueError('Attribution-required photo lacks a real author name')
        record['authorApiValueBeforeNormalization']=record.get('author')
        record['author']=UNKNOWN_AUTHOR
        record['authorStatus']='not_provided_by_photo_api'
        record['authorNote']='CC0 does not require attribution as a copyright-license condition. The original photo page is retained; a rights notice is not presented as a person name.'
    else:
        record['authorStatus']='source_supplied_not_independently_verified'
    lu=record.get('licenseUrl','')
    expected='cc0' if '/publicdomain/zero/' in lu else 'cc-by-sa' if '/licenses/by-sa/' in lu else 'cc-by' if '/licenses/by/' in lu else None
    if record.get('licenseCode')!=expected:raise ValueError('License code and original license URL disagree')
    _original_verify(record)

def read_reviews():
    decisions,evidence=_original_reviews()
    report=json.loads(DETAIL.read_text(encoding='utf-8'))
    for item in report['records']:
        k=build.key(item)
        if k not in decisions:raise ValueError('Detailed review must match an already screened image: '+k)
        paths=list((ROOT/'metadata').glob('*/'+item['assetId']+'.json'))+list((ROOT/'reference/metadata').glob('*/'+item['assetId']+'.json'))
        matching=[]
        for path in paths:
            r=json.loads(path.read_text(encoding='utf-8'))
            if r.get('targetId')==item['targetId'] and r['sha256']['master']==item['masterSha256']:
                matching.append(r)
        if not matching:raise ValueError('Detailed review image/hash no longer matches: '+k)
        previous=decisions[k]
        decisions[k]={**previous,'priorContactSheetRole':previous['recommendedRole'],'recommendedRole':item['recommendedRole'],'noteJa':item['noteJa'],'individualJpegReview':{'reviewFile':'reports/detail-sample-review.json','method':report['method'],'reviewedAt':report['reviewedAt'],'masterSha256':item['masterSha256']},'fullResolutionInspection':'saved_JPEG_viewed_individually_not_pixel_by_pixel_audit'}
    evidence.append({'file':'reports/detail-sample-review.json','count':len(report['records']),'kind':'additional_individual_JPEG_followup_not_additional_images'})
    gap_review_loader.apply(ROOT,decisions,evidence)
    if not any(item.get('file')==round2_photos.REVIEW for item in evidence):
        round2_photos.apply_decisions(decisions,evidence)
    if not any(item.get('file')==round3_photos.REVIEW for item in evidence):
        round3_photos.apply_decisions(decisions,evidence)
    targeted_review_loader.apply(ROOT,decisions,evidence)
    return decisions,evidence

def main():
    build.verify_record=verify_record
    build.read_reviews=read_reviews
    build.main()
    p=ROOT/'reports/curation-status.json'
    status=json.loads(p.read_text(encoding='utf-8'))
    records=json.loads((ROOT/'collection/assets.json').read_text(encoding='utf-8'))['records']
    status['acceptedCC0PhotoPairsWithoutAuthorName']=sum(r.get('authorStatus')=='not_provided_by_photo_api' for r in records)
    status['authorMetadataNote']='Unavailable CC0 photographer names are explicitly marked. Rights notices are never used as photographer names. Other author names are copied from source metadata, not independently verified.'
    status['individualSavedJpegSampleReviewed']=len(json.loads(DETAIL.read_text())['records'])
    status['licenseCodeToUrlConsistency']='pass'
    status['gapBatchAcceptedPhotoPairs']=sum(r.get('acquisitionBatch')=='batches/gaps-20260914' for r in records)
    status['round2AcceptedPhotoPairs']=sum(r.get('acquisitionBatch')==round2_photos.BATCH for r in records)
    status['round3AcceptedPhotoPairs']=sum(r.get('acquisitionBatch')==round3_photos.BATCH for r in records)
    status['targetedMicrographAcceptedPhotoPairs']=sum(r.get('acquisitionBatch')=='batches/targeted-micrographs-20260914' for r in records)
    p.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
