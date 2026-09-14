#!/usr/bin/env python3
"""Recover failed master conversions only from explicitly re-reviewed, hash-matched JPEGs."""
from __future__ import annotations
import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import collect as core
from adopt_gap_review_20260914 import refresh_source_info
from gap_review_loader import resolve_target
BATCH='batches/gaps-20260914'
REVIEW='reviews/gap-20260914.json'
FOLLOWUP='reviews/gap-preview-followup-20260914.json'

def load(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))
def save(path,obj):core.dump(path,obj)

def main():
    followup=load(FOLLOWUP);spec=load(REVIEW);manifest=ROOT/BATCH/'candidates.json'
    digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
    if digest!=spec['candidateManifestSha256'] or digest!=followup['candidateManifestSha256']:
        raise ValueError('Review evidence manifest changed')
    candidates={c['number']:c for c in load(BATCH+'/candidates.json')['records']}
    adoption=load(BATCH+'/adoption.json')
    failures={r['number']:r for r in adoption.get('failures',[])}
    checked={r['number']:r for r in followup['records']}
    if len(checked)!=followup['reviewedCount']:raise ValueError('Duplicate or missing follow-up records')
    if failures and set(failures)!=set(checked):raise ValueError('Every failed candidate must receive an individual review')
    effective={}
    for role,field in [('primary','primaryNumbers'),('supplementary','supplementaryNumbers'),('exclude','excludeNumbers')]:
        for n in spec[field]:
            if n in effective:raise ValueError('Duplicate original review number')
            effective[n]=role
    for number,review in checked.items():
        candidate=candidates[number]
        if review['assetId']!=candidate['assetId'] or review['previewSha256']!=candidate['previewSha256']:
            raise ValueError('Individual review is not bound to the exact image')
        if review['recommendedRole'] not in ('primary','supplementary','exclude'):raise ValueError('Invalid follow-up decision')
        if not review.get('noteJa') or not review.get('viewedIndividually'):raise ValueError('Actual individual image review required')
        effective[number]=review['recommendedRole']
    for role,field in [('primary','primaryNumbers'),('supplementary','supplementaryNumbers'),('exclude','excludeNumbers')]:
        spec[field]=sorted(n for n,r in effective.items() if r==role)
    spec.setdefault('individualPreviewReviews',{})
    for n,review in checked.items():
        spec['notesJa'][str(n)]=review['noteJa']
        spec['individualPreviewReviews'][str(n)]={'reviewFile':FOLLOWUP,'method':followup['method'],'reviewedAt':followup['reviewedAt'],'previewSha256':review['previewSha256'],'recommendedRole':review['recommendedRole']}
    selected=[candidates[n] for n in checked if effective[n]!='exclude']
    refreshed,new_failures=refresh_source_info(selected)
    old_saved={r['number']:r for r in adoption.get('saved',[])};recovered=[]
    for n,c in refreshed.items():
        try:
            raw=(ROOT/c['previewPath']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=c['previewSha256']:raise ValueError('Preview bytes changed')
            with Image.open(io.BytesIO(raw)) as source:
                if source.format!='JPEG' or getattr(source,'n_frames',1)!=1:raise ValueError('Expected the exact single-frame JPEG that was individually reviewed')
                source.load();im=source.convert('RGB')
            if list(im.size)!=c['previewDimensions'] or min(im.size)<500 or max(im.size)<1000:
                raise ValueError('Reviewed preview resolution does not meet the collection threshold')
            target=resolve_target(ROOT,spec,c);sid=core.slug(target['scientificName']);base=f"reference/images/{sid}/{c['assetId']}"
            files={'master':base+'.jpg','web':base+'.webp','thumbnail':base+'-thumb.webp'}
            web=im.copy();web.thumbnail((1400,1400),Image.Resampling.LANCZOS);web_bytes=io.BytesIO();quality=85
            while True:
                web_bytes.seek(0);web_bytes.truncate();web.save(web_bytes,'WEBP',quality=quality,method=5)
                if web_bytes.tell()<=190000 or quality<=68:break
                quality-=3
            thumb=im.copy();thumb.thumbnail((360,280),Image.Resampling.LANCZOS);thumb_bytes=io.BytesIO();thumb.save(thumb_bytes,'WEBP',quality=78,method=4)
            payloads={'master':raw,'web':web_bytes.getvalue(),'thumbnail':thumb_bytes.getvalue()}
            for kind,data in payloads.items():
                path=ROOT/files[kind];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            info=c['info'];code=c['licenseCode'];source_page=info['descriptionurl']
            record={'schemaVersion':1,'assetId':c['assetId'],'targetId':target['id'],'scientificName':target['scientificName'],'nameJa':target.get('nameJa',''),'collectionTier':target.get('collectionTier','chronoearth'),'source':'Wikimedia Commons','sourceId':str(c['page']['pageid']),'imageTitle':c['imageTitle'],'photoUrl':source_page,'originalUrl':info['url'],'sourceAcquisitionUrl':candidates[n]['info'].get('thumburl') or candidates[n]['info']['url'],'masterInputFile':c['previewPath'],'masterInputKind':'individually_reviewed_saved_JPEG_preview','licenseCode':code,'licenseUrl':c['licenseUrl'],'author':c['author'],'originalAttribution':c['originalAttribution'],'retrievedAt':candidates[n]['sourceMetadataRetrievedAt'],'savedAt':core.NOW(),'origin':'photo_candidate','status':'collected_pending_visual_review','visualReview':{'status':'pending','note':'Actual individual review is applied by the reviewed-collection builder.'},'rightsReview':{'status':'allowed_license_metadata_verified','verifiedAt':c['sourceRefreshedAt'],'commercialReuseAllowedByLicense':True,'attributionRequired':code!='cc0','shareAlikeRequiredForAdaptation':code=='cc-by-sa','otherRights':'not_warranted'},'selectionBasis':c['selectionBasis'],'taxonMatch':'scientific_name_wikipedia_lead' if c['selectionBasis']=='wikipedia_lead_photo' else 'exact_scientific_name_in_file_title_or_description','wikipediaPage':c['wikipediaPage'],'sourceCaption':c['sourceCaption'],'sourceSearchTargetId':c['target']['id'],'files':files,'dimensions':{'sourceDeclaredOriginal':[info['width'],info['height']],'master':list(im.size),'web':list(web.size)},'bytes':{k:len(v) for k,v in payloads.items()},'sha256':{'inputReviewedPreview':c['previewSha256'],**{k:hashlib.sha256(v).hexdigest() for k,v in payloads.items()}},'changes':['Saved JPEG master is the exact previously downloaded, individually reviewed 1280-pixel preview; it is not the original source file','WebP and thumbnail derivatives re-encoded with proportional downsize only; no crop','No generative fill or subject alteration'],'webQuality':quality,'imageInfoEvidence':info,'acquisitionBatch':BATCH,'reviewedPreviewSha256':c['previewSha256'],'reviewedPreviewPath':c['previewPath'],'originalImageSha1AtReview':candidates[n]['info']['sha1'],'originalImageSha1AtAdoption':info['sha1'],'sourceIdentityRecheckedAt':c['sourceRefreshedAt'],'recovery':{'previousFailure':failures.get(n),'individualReviewFile':FOLLOWUP,'basis':'Exact saved preview JPEG visually rechecked, decoded and hashed. No claim that the failed original-thumbnail bytes were saved.'}}
            record['credit']=f"{record['imageTitle']} [{record['scientificName']}] — {record['author']} / Wikimedia Commons, {code.upper()} ({record['licenseUrl']}); source: {source_page}. Original attribution: {record['originalAttribution']}. Saved as the individually reviewed resized JPEG preview; WebP re-encoded, no subject alteration."
            metadata=f"reference/metadata/{sid}/{c['assetId']}.json";save(metadata,record)
            saved={'number':n,'targetId':target['id'],'sourceSearchTargetId':c['target']['id'],'assetId':c['assetId'],'metadataPath':metadata,'recommendedRole':effective[n],'existingPhotoReused':False,'previewToMasterOriginalIdentity':'pass_exact_reviewed_JPEG_bytes','freshLicenseCheck':'pass','recoveryMethod':'individually_reviewed_preview_JPEG'}
            old_saved[n]=saved;recovered.append(saved)
        except Exception as exc:new_failures.append({'number':n,'stage':'reviewed_JPEG_recovery','error':str(exc)})
    save(REVIEW,spec)
    adoption.setdefault('failureHistory',[]).extend(adoption.get('failures',[]))
    adoption.update({'generatedAt':core.NOW(),'phase':'complete' if not new_failures else 'partial_failure_preserved','roleCounts':dict(Counter(effective.values())),'selectedCount':sum(r!='exclude' for r in effective.values()),'savedCount':len(old_saved),'savedTaxa':len({r['targetId'] for r in old_saved.values()}),'saved':sorted(old_saved.values(),key=lambda r:r['number']),'failures':new_failures,'recoveredViaReviewedJPEG':len(recovered),'individualReviewFile':FOLLOWUP})
    save(BATCH+'/adoption.json',adoption)
    save(BATCH+'/recovery.json',{'generatedAt':core.NOW(),'reviewFile':FOLLOWUP,'recovered':recovered,'failures':new_failures,'note':'Successful earlier downloads are unchanged. Only failed conversions use the exact individually reviewed preview JPEG as the saved master.'})
    print(json.dumps({'saved':len(old_saved),'recovered':len(recovered),'failures':new_failures},ensure_ascii=False))
    if new_failures:raise RuntimeError('Some individually reviewed JPEG recoveries still require attention')

if __name__=='__main__':main()
