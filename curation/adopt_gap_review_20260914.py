#!/usr/bin/env python3
"""Adopt explicitly screened photographs, preserving immutable preview evidence."""
from __future__ import annotations
import concurrent.futures
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import collect as core
import collect_reference as reference
from gap_review_loader import resolve_target

BATCH='batches/gaps-20260914'
REVIEW='reviews/gap-20260914.json'
LICENSE_URL=re.compile(r'https://creativecommons\.org/(licenses/by(?:-sa)?/(?:[1-4]\.0|2\.5)(?:/[a-z-]+)?|publicdomain/zero/1\.0)/?')

def load(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))
def save(path,obj):core.dump(path,obj)

def refresh_source_info(candidates):
    refreshed={};errors=[]
    for start in range(0,len(candidates),20):
        batch=candidates[start:start+20]
        try:
            data=core.get(core.COMMONS,{'action':'query','format':'json','formatversion':2,'pageids':'|'.join(str(c['page']['pageid']) for c in batch),'prop':'imageinfo','iiprop':'url|extmetadata|size|mime|sha1','iiurlwidth':2048})
            pages={str(p['pageid']):p for p in data.get('query',{}).get('pages',[])}
        except Exception as exc:
            errors.extend({'number':c['number'],'stage':'source_refresh','error':str(exc)} for c in batch)
            continue
        for c in batch:
            try:
                page=pages[str(c['page']['pageid'])];info=page['imageinfo'][0]
                old_sha=c['info'].get('sha1');new_sha=info.get('sha1')
                if not old_sha or old_sha!=new_sha:raise ValueError('Original image changed since visual preview; manual re-review required')
                metadata=info.get('extmetadata',{})
                value=lambda k:core.clean(metadata.get(k,{}).get('value',''))
                url=value('LicenseUrl').replace('http:','https:')
                if not LICENSE_URL.fullmatch(url):raise ValueError('Fresh metadata lacks an allowed commercial-use license')
                code='cc0' if '/zero/' in url else 'cc-by-sa' if '/by-sa/' in url else 'cc-by'
                if code!=c['licenseCode'] or url.rstrip('/')!=c['licenseUrl'].rstrip('/'):
                    raise ValueError('License changed since selection; preserve evidence and require re-review')
                author=value('Artist')
                if not author:raise ValueError('Author missing from fresh metadata')
                if info.get('mime') not in ('image/jpeg','image/png','image/webp'):raise ValueError('Not a supported photographic file')
                record=copy.deepcopy(c)
                record.update({'page':page,'info':info,'author':author,'imageTitle':value('ObjectName') or page['title'],'originalAttribution':value('Attribution') or value('Credit'),'licenseCode':code,'licenseUrl':url,'sourceRefreshedAt':core.NOW()})
                refreshed[c['number']]=record
            except Exception as exc:
                errors.append({'number':c['number'],'stage':'source_identity_or_license','error':str(exc)})
    return refreshed,errors

def adopt_one(candidate,role,spec):
    c=copy.deepcopy(candidate);original_target=c['target'];target=resolve_target(ROOT,spec,c)
    c['target']=target
    preview=ROOT/c['previewPath']
    if not preview.is_file() or hashlib.sha256(preview.read_bytes()).hexdigest()!=c['previewSha256']:
        raise ValueError('Saved preview does not match the visually screened bytes')
    relative=f"reference/metadata/{core.slug(target['scientificName'])}/{c['assetId']}.json"
    existed=(ROOT/relative).exists()
    if existed:
        record=load(relative)
        source_sha=(record.get('imageInfoEvidence') or {}).get('sha1')
        if record.get('targetId')!=target['id'] or source_sha!=c['info']['sha1']:
            raise ValueError('Existing photo identity differs; no overwrite permitted')
    else:
        reference.collect_image(c)
        record=load(relative)
    record.update({'selectionBasis':c['selectionBasis'],'taxonMatch':'caption_explicit_target_correction' if target['id']!=original_target['id'] else 'scientific_name_wikipedia_lead' if c['selectionBasis']=='wikipedia_lead_photo' else 'exact_scientific_name_in_file_title_or_description','sourceCaption':c['sourceCaption'],'sourceSearchTargetId':original_target['id'],'targetCorrection':spec.get('retargetedCandidates',{}).get(str(c['number'])),'acquisitionBatch':BATCH,'reviewedPreviewSha256':c['previewSha256'],'reviewedPreviewPath':c['previewPath'],'originalImageSha1AtReview':candidate['info']['sha1'],'originalImageSha1AtAdoption':c['info']['sha1'],'sourceIdentityRecheckedAt':c['sourceRefreshedAt']})
    for kind in ('master','web'):
        data=(ROOT/record['files'][kind]).read_bytes()
        if hashlib.sha256(data).hexdigest()!=record['sha256'][kind]:raise ValueError('Saved image checksum mismatch')
    save(relative,record)
    return {'number':c['number'],'targetId':target['id'],'sourceSearchTargetId':original_target['id'],'assetId':c['assetId'],'metadataPath':relative,'recommendedRole':role,'existingPhotoReused':existed,'previewToMasterOriginalIdentity':'pass','freshLicenseCheck':'pass'}

def main():
    manifest_path=ROOT/BATCH/'candidates.json';spec=load(REVIEW)
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest()!=spec['candidateManifestSha256']:
        raise ValueError('Immutable candidate manifest hash mismatch')
    candidates={c['number']:c for c in load(BATCH+'/candidates.json')['records']};roles={}
    for role,field in [('primary','primaryNumbers'),('supplementary','supplementaryNumbers'),('exclude','excludeNumbers')]:
        for number in spec.get(field,[]):
            if number in roles or number not in candidates:raise ValueError('Unknown or duplicate review number')
            roles[number]=role
    if len(roles)!=spec['reviewedCount'] or set(roles)!=set(candidates):raise ValueError('Review must classify every candidate exactly once')
    selected=[candidates[n] for n in sorted(roles) if roles[n]!='exclude']
    for c in selected:resolve_target(ROOT,spec,c)
    (ROOT/'reference/images').mkdir(parents=True,exist_ok=True)
    (ROOT/'reference/metadata').mkdir(parents=True,exist_ok=True)
    refreshed,failures=refresh_source_info(selected);saved=[]
    def progress(phase):
        report={'generatedAt':core.NOW(),'phase':phase,'reviewFile':REVIEW,'candidateManifestSha256':spec['candidateManifestSha256'],'reviewedCount':len(roles),'roleCounts':dict(Counter(roles.values())),'selectedCount':len(selected),'savedCount':len(saved),'savedTaxa':len({r['targetId'] for r in saved}),'saved':sorted(saved,key=lambda r:r['number']),'failures':failures,'sourceLicenseAndOriginalImageIdentityRechecked':True,'note':'Only explicitly selected photographs are adopted. Rejected previews remain separate audit evidence. A taxon correction requires an exact existing target and an explicit scientific name in the original source caption.'}
        save(BATCH+'/adoption.json',report)
        print(json.dumps({k:report[k] for k in ('phase','selectedCount','savedCount','savedTaxa')}),flush=True)
    progress('adopting')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(adopt_one,c,roles[n],spec):n for n,c in refreshed.items()}
        for count,future in enumerate(concurrent.futures.as_completed(futures),1):
            number=futures[future]
            try:saved.append(future.result())
            except Exception as exc:failures.append({'number':number,'stage':'download_and_save','error':str(exc)})
            if count%50==0:progress('adopting')
    progress('complete' if not failures else 'partial_failure_preserved')
    if failures:raise RuntimeError(f'{len(failures)} selected images require retry or review; partial files and evidence preserved')

if __name__=='__main__':main()
