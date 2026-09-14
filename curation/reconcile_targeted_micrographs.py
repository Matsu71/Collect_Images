#!/usr/bin/env python3
"""Reconcile a partially completed acquisition without re-downloading existing photographs."""
from __future__ import annotations
import hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import collect as core
BATCH='batches/targeted-micrographs-20260914'
ENTRIES=[
 ('org-prochlorococcus-marinus','82895983','reference/metadata/prochlorococcus-marinus/commons-82895983.json'),
 ('org-candidatus-prometheoarchaeum-syntrophicum','117990073','reference/metadata/candidatus-prometheoarchaeum-syntrophicum/commons-117990073.json')
]

def main():
    output=ROOT/'targeted-review';output.mkdir(exist_ok=True);records=[]
    for target_id,page_id,relative in ENTRIES:
        metadata_path=ROOT/relative
        rec=json.loads(metadata_path.read_text(encoding='utf-8'))
        original_metadata_hash=hashlib.sha256(metadata_path.read_bytes()).hexdigest()
        if rec['targetId']!=target_id or rec['sourceId']!=page_id:raise ValueError('Unexpected existing image identity')
        response=core.get(core.COMMONS,{'action':'query','format':'json','formatversion':2,'pageids':page_id,'prop':'imageinfo','iiprop':'url|extmetadata|size|mime|sha1'})
        pages=response.get('query',{}).get('pages',[])
        if len(pages)!=1 or not pages[0].get('imageinfo'):raise ValueError('Exact named source missing')
        current=pages[0]['imageinfo'][0];old=rec.get('imageInfoEvidence') or {}
        if not current.get('sha1') or current['sha1']!=old.get('sha1'):raise ValueError('Original source image changed; new review required')
        licence=core.clean(current.get('extmetadata',{}).get('LicenseUrl',{}).get('value','')).replace('http:','https:')
        licence=re.sub(r'/deed\.[A-Za-z_-]+/?$','/',licence)
        if licence.rstrip('/')!=rec['licenseUrl'].rstrip('/'):raise ValueError('Source licence differs from recorded licence')
        if rec['licenseCode'] not in ('cc0','cc-by','cc-by-sa'):raise ValueError('Unsupported commercial-use licence')
        local=ROOT/rec['files']['master']
        if local.is_file():body=local.read_bytes()
        else:body=subprocess.check_output(['git','show','HEAD:'+rec['files']['master']],cwd=ROOT)
        digest=hashlib.sha256(body).hexdigest()
        if digest!=rec['sha256']['master']:raise ValueError('Saved image checksum mismatch')
        filename=core.slug(rec['scientificName'])+'--'+rec['assetId']+'.jpg'
        (output/filename).write_bytes(body)
        (output/(filename[:-4]+'.json')).write_bytes(metadata_path.read_bytes())
        if hashlib.sha256(metadata_path.read_bytes()).hexdigest()!=original_metadata_hash:raise ValueError('Existing source metadata was altered')
        newly_saved=rec.get('acquisitionBatch')==BATCH
        records.append({'targetId':target_id,'scientificName':rec['scientificName'],'assetId':rec['assetId'],'metadataPath':relative,'masterSha256':digest,'reviewFile':filename,'newToThisBatch':newly_saved,'existingEarlierPhotoNotDuplicated':not newly_saved,'originalAcquisitionBatch':rec.get('acquisitionBatch'),'licenceCode':rec['licenseCode'],'licenceUrl':rec['licenseUrl'],'sourcePage':rec['photoUrl'],'sourceOriginalSha1Rechecked':current['sha1'],'sourceLicenceRecheck':'pass','sourceMetadataUnchanged':True,'freshImageInfoEvidence':current})
    report={'generatedAt':core.NOW(),'phase':'reconciled_successfully','newImageCount':sum(r['newToThisBatch'] for r in records),'existingEarlierImagesReused':sum(r['existingEarlierPhotoNotDuplicated'] for r in records),'records':records,'sourceAndStoredHashes':'pass','savedMetadataUnchanged':'pass','recoveryNote':'The initial run saved Prochlorococcus and then correctly stopped before overwriting an older Promethearchaeum photograph. Both saved files are now verified and the older image is not counted as a new acquisition. Actual visual review is a separate record.'}
    core.dump(BATCH+'/acquisition.json',report)
    (output/'index.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='records'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
