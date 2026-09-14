#!/usr/bin/env python3
"""Round 2: new candidates for unresolved taxa; no automatic visual approval."""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, io, json, re, sys
from collections import Counter
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import collect as core
BATCH='batches/gaps-round2-20260914'
REVIEW='reviews/round2-decisions-20260914.json'
LIC=re.compile(r'https://creativecommons\.org/(licenses/by(?:-sa)?/(?:[1-4]\.0|2\.5)(?:/[a-z-]+)?|publicdomain/zero/1\.0)/?')
BAD=re.compile(r'\b(drawing|illustration|painting|engraving|diagram|map|spectrogram|protein|phylogenetic|taxidermy|skeleton|skull|model|statue|sculpture|replica|footprints?|dead specimen|preserved specimen|pinned specimen|ai.generated|generative ai)\b',re.I)
PART=re.compile(r'\b(flowers?|fruits?|leaves|leaf|bark|seeds?|portrait|head|detail|close.up|bud|pollen|feathers?|eggs?)\b',re.I)
WHOLE=re.compile(r'\b(habit|habitus|whole|tree|plant|shrub|wuchs|arbre|baum|entire|full.body|standing|walking)\b',re.I)

def load(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))
def save(path,obj):core.dump(path,obj)
def sha(data):return hashlib.sha256(data).hexdigest()

def observed_assets():
    seen=set()
    for folder in ('metadata','reference/metadata'):
        for p in (ROOT/folder).glob('*/*.json'):
            r=json.loads(p.read_text());seen.add((r['targetId'],r['assetId']))
    old=ROOT/'batches/gaps-20260914/candidates.json'
    if old.exists():
        for r in load(str(old.relative_to(ROOT)))['records']:seen.add((r['target']['id'],r['assetId']))
    return seen

def commons_candidates(t,seen,focused):
    name=t['scientificName'];q='"'+name+'" '+('habit ' if focused else '')+'filetype:bitmap -drawing -illustration -map -diagram -protein'
    j=core.get(core.COMMONS,{'action':'query','format':'json','formatversion':2,'generator':'search','gsrsearch':q,'gsrnamespace':6,'gsrlimit':20 if focused else 35,'prop':'imageinfo','iiprop':'url|extmetadata|size|mime|sha1','iiurlwidth':1600})
    candidates=[]
    for p in j.get('query',{}).get('pages',[]):
        info=(p.get('imageinfo') or [{}])[0];m=info.get('extmetadata',{});val=lambda k:core.clean(m.get(k,{}).get('value',''))
        codeurl=val('LicenseUrl').replace('http:','https:');author=val('Artist');title=p['title'];caption=val('ImageDescription');cats=val('Categories')
        pid='commons-'+str(p['pageid']);w,h=info.get('width',0),info.get('height',0)
        if (t['id'],pid) in seen or not LIC.fullmatch(codeurl) or not author:continue
        if info.get('mime') not in ('image/jpeg','image/png','image/webp') or min(w,h)<500 or max(w,h)<1000:continue
        if max(w,h)/min(w,h)>3 or BAD.search(title):continue
        if BAD.search(caption[:400]) and not re.search('micrograph|microscop',caption,re.I):continue
        literal=(title+' '+caption).replace('_',' ').lower()
        if name.lower() not in literal:continue
        code='cc0' if '/zero/' in codeurl else 'cc-by-sa' if '/by-sa/' in codeurl else 'cc-by'
        score=10*bool(WHOLE.search(title))+6*bool(WHOLE.search(caption[:300]))-12*bool(PART.search(title))-3*bool(PART.search(caption[:180]))
        score+=6*bool(re.search('Quality images|Featured pictures',cats,re.I))+min(3,min(w,h)/1000)
        score+=6*bool(re.search('micrograph|microscopy|SEM|TEM',title,re.I))
        candidates.append({'target':t,'assetId':pid,'source':'Wikimedia Commons','sourceId':str(p['pageid']),'photoUrl':info.get('descriptionurl'),'sourceUrl':info.get('thumburl') or info['url'],'originalUrl':info['url'],'licenseCode':code,'licenseUrl':codeurl,'author':author,'originalAttribution':val('Attribution') or val('Credit'),'imageTitle':val('ObjectName') or title,'caption':caption,'sourceTitle':title,'imageInfoEvidence':info,'score':score,'originalSha1':info.get('sha1'),'acquiredAt':core.NOW(),'identityBasis':'exact_scientific_name_in_title_or_caption_not_independent_reidentification'})
    return candidates

def inat_candidates(t,seen):
    try:candidates,detail=core.inat_candidates(t)
    except Exception:return []
    out=[]
    for c in candidates:
        aid='inat-'+c['sourceId']
        if (t['id'],aid) in seen:continue
        if c['taxonMatch']!='exact_scientific_name':continue
        author=c.get('author','')
        if c['licenseCode']!='cc0' and author.lower() in ('no rights reserved','some rights reserved','unknown','anonymous'):continue
        out.append({'target':t,'assetId':aid,**{k:v for k,v in c.items() if k not in ('assetId','target')},'sourceUrl':c['downloadUrl'],'caption':t['scientificName']+' — '+c['selectionBasis'],'sourceTitle':t['scientificName'],'score':c['selectionScore']-4,'acquiredAt':core.NOW(),'identityBasis':'iNaturalist_exact_taxon_photo_or_research_grade_observation'})
    return out

def acquire_target(t,seen):
    errors=[];cs=[]
    for focused in (True,False):
        try:cs.extend(commons_candidates(t,seen,focused))
        except Exception as e:errors.append(str(e))
    # Add a different observation source instead of repeatedly selecting the same Commons files.
    cs.extend(inat_candidates(t,seen))
    unique={c['assetId']:c for c in cs};cs=sorted(unique.values(),key=lambda c:c['score'],reverse=True)
    # Preserve source diversity when available, rather than three near-identical views.
    chosen=[];commons=[c for c in cs if c['source']=='Wikimedia Commons'];inat=[c for c in cs if c['source']=='iNaturalist']
    order=commons[:2]+inat[:1]+commons[2:]+inat[1:]
    hashes=set()
    for c in order[:12]:
        if len(chosen)>=3:break
        try:
            raw=core.get(c['sourceUrl'],binary=True);im=Image.open(io.BytesIO(raw))
            if getattr(im,'n_frames',1)!=1:raise ValueError('animated_source_excluded')
            im.load();im=ImageOps.exif_transpose(im).convert('RGB')
            if min(im.size)<500 or max(im.size)<1000:raise ValueError('insufficient_saved_resolution')
            im.thumbnail((1600,1600),Image.Resampling.LANCZOS);buf=io.BytesIO();im.save(buf,'JPEG',quality=92,optimize=True)
            data=buf.getvalue();digest=sha(data)
            if digest in hashes:continue
            hashes.add(digest);path=f"{BATCH}/previews/{core.slug(t['scientificName'])}--{c['assetId']}.jpg"
            (ROOT/path).parent.mkdir(parents=True,exist_ok=True);(ROOT/path).write_bytes(data)
            c.update({'previewPath':path,'previewSha256':digest,'sourceDownloadSha256':sha(raw),'previewDimensions':list(im.size),'status':'candidate_pending_actual_visual_review'})
            chosen.append(c)
        except Exception as e:errors.append(c['assetId']+': '+str(e))
    return chosen,{'targetId':t['id'],'scientificName':t['scientificName'],'candidateCount':len(chosen),'eligibleCandidates':len(cs),'errors':errors}

def gather():
    if (ROOT/BATCH/'candidates.json').exists():raise ValueError('Immutable round already exists; do not overwrite')
    current=load('reports/curation-status.json');save(BATCH+'/baseline.json',current)
    targets={t['id']:t for t in load('data/targets.json')['records']}
    gaps=[targets[t['id']] for t in load('reports/primary-gaps.json')]
    gaps.sort(key=lambda t:(t.get('collectionTier')!='chronoearth',t['scientificName'].lower()))
    seen=observed_assets();records=[];results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(acquire_target,t,seen):t for t in gaps}
        for n,f in enumerate(concurrent.futures.as_completed(futures),1):
            try:cs,r=f.result();records.extend(cs);results.append(r)
            except Exception as e:results.append({'targetId':futures[f]['id'],'error':str(e)})
            if n%20==0:print(json.dumps({'processedTargets':n,'gapTargets':len(gaps),'savedNewCandidates':len(records)}),flush=True)
    rank={t['id']:n for n,t in enumerate(gaps)};records.sort(key=lambda r:(rank[r['target']['id']],-r['score'],r['assetId']))
    for n,r in enumerate(records,1):r['number']=n
    save(BATCH+'/candidates.json',{'schemaVersion':1,'generatedAt':core.NOW(),'records':records});save(BATCH+'/results.json',results)
    folder=ROOT/BATCH/'sheets';folder.mkdir(parents=True,exist_ok=True)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',15)
    for start in range(0,len(records),20):
        sheet=Image.new('RGB',(1800,1520),'white');draw=ImageDraw.Draw(sheet)
        for n,r in enumerate(records[start:start+20]):
            x=n%5*360;y=n//5*380
            with Image.open(ROOT/r['previewPath']) as im:
                im=ImageOps.contain(im,(350,315));sheet.paste(im,(x+(360-im.width)//2,y+(315-im.height)//2))
            draw.text((x+5,y+321),f"{r['number']:04d} {r['target']['scientificName']}"[:42],font=font,fill='black')
            draw.text((x+5,y+345),r['assetId']+' '+r['licenseCode'],font=font,fill='black')
        sheet.save(folder/f'round2-{start//20+1:03d}.jpg',quality=93)
    save(BATCH+'/status.json',{'generatedAt':core.NOW(),'gapTargets':len(gaps),'candidateImages':len(records),'candidateTaxa':len({r['target']['id'] for r in records}),'sourceCounts':dict(Counter(r['source'] for r in records)),'licenseCounts':dict(Counter(r['licenseCode'] for r in records)),'candidateManifestSha256':sha((ROOT/BATCH/'candidates.json').read_bytes()),'adoptedCount':0,'visualReview':'pending'})
    print(json.dumps(load(BATCH+'/status.json')),flush=True)

def validate_review():
    spec=load(REVIEW);raw=(ROOT/BATCH/'candidates.json').read_bytes()
    if sha(raw)!=spec['candidateManifestSha256']:raise ValueError('Candidate review hash mismatch')
    candidates={r['number']:r for r in json.loads(raw)['records']};roles={}
    for role,field in [('primary','primaryNumbers'),('supplementary','supplementaryNumbers'),('exclude','excludeNumbers')]:
        for n in spec.get(field,[]):
            if n in roles or n not in candidates:raise ValueError('Duplicate/unknown decision')
            roles[n]=role
    if set(roles)!=set(candidates) or len(roles)!=spec['reviewedCount']:raise ValueError('Every candidate needs an explicit review')
    return spec,candidates,roles

def adopt():
    spec,cs,roles=validate_review();saved=[];failures=[]
    for n in sorted(cs):
        if roles[n]=='exclude':continue
        c=cs[n];t=c['target']
        try:
            b=(ROOT/c['previewPath']).read_bytes()
            if sha(b)!=c['previewSha256']:raise ValueError('Reviewed bytes changed')
            with Image.open(io.BytesIO(b)) as source:source.load();im=source.convert('RGB')
            base=f"reference/images/{core.slug(t['scientificName'])}/{c['assetId']}"
            paths={'master':base+'.jpg','web':base+'.webp','thumbnail':base+'-thumb.webp'}
            meta=f"reference/metadata/{core.slug(t['scientificName'])}/{c['assetId']}.json"
            if (ROOT/meta).exists():raise ValueError('Existing metadata must not be overwritten by a new candidate')
            web=im.copy();web.thumbnail((1400,1400),Image.Resampling.LANCZOS);wb=io.BytesIO();quality=85
            while True:
                wb.seek(0);wb.truncate();web.save(wb,'WEBP',quality=quality,method=5)
                if wb.tell()<=190000 or quality<=68:break
                quality-=3
            thumb=im.copy();thumb.thumbnail((360,280),Image.Resampling.LANCZOS);tb=io.BytesIO();thumb.save(tb,'WEBP',quality=78,method=4)
            payload={'master':b,'web':wb.getvalue(),'thumbnail':tb.getvalue()}
            for k,v in payload.items():
                p=ROOT/paths[k];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v)
            rec={k:v for k,v in c.items() if k not in ('target','number','score','status')}
            rec.update({'schemaVersion':1,'targetId':t['id'],'scientificName':t['scientificName'],'nameJa':t.get('nameJa',''),'collectionTier':t.get('collectionTier'),'files':paths,'dimensions':{'master':list(im.size),'web':list(web.size)},'bytes':{k:len(v) for k,v in payload.items()},'sha256':{k:sha(v) for k,v in payload.items()},'status':'collected_pending_visual_review','origin':'photo_candidate','acquisitionBatch':BATCH,'retrievedAt':c['acquiredAt'],'savedAt':core.NOW(),'visualReview':{'status':'pending'},'rightsReview':{'status':'allowed_license_metadata_verified_at_acquisition','verifiedAt':c['acquiredAt'],'commercialReuseAllowedByLicense':True,'attributionRequired':c['licenseCode']!='cc0','shareAlikeRequiredForAdaptation':c['licenseCode']=='cc-by-sa','otherRights':'not_warranted'},'changes':['Master is the exact downloaded and visually screened proportional JPEG derivative, not original source bytes','WebP/thumbnail re-encoding and proportional downsize; no crop','No generated content or subject alteration'],'webQuality':quality})
            rec['credit']=f"{rec['imageTitle']} [{rec['scientificName']}] — {rec['author']} / {rec['source']}, {rec['licenseCode']} ({rec['licenseUrl']}); source: {rec['photoUrl']}. Resized and re-encoded; no subject alteration."
            save(meta,rec);saved.append({'number':n,'targetId':t['id'],'assetId':c['assetId'],'metadataPath':meta,'recommendedRole':roles[n]})
        except Exception as e:failures.append({'number':n,'error':str(e)})
    save(BATCH+'/adoption.json',{'generatedAt':core.NOW(),'saved':saved,'savedCount':len(saved),'failures':failures,'roleCounts':dict(Counter(roles.values())),'candidateManifestSha256':spec['candidateManifestSha256'],'reviewedCount':len(roles),'masterUsesExactReviewedBytes':True})
    if failures:raise ValueError('Selected photos need repair: '+str(failures))

def apply_decisions(decisions,evidence):
    if not (ROOT/REVIEW).exists():return
    spec,cs,roles=validate_review();applied=0
    for n,c in cs.items():
        role=roles[n]
        if role=='exclude':continue
        meta=ROOT/f"reference/metadata/{core.slug(c['target']['scientificName'])}/{c['assetId']}.json"
        if not meta.exists():continue
        r=json.loads(meta.read_text())
        if r.get('acquisitionBatch')!=BATCH or r['sha256']['master']!=c['previewSha256']:raise ValueError('Saved master differs from reviewed image')
        decisions[c['target']['id']+'|'+c['assetId']]={'status':'screened','recommendedRole':role,'reviewer':spec['reviewer'],'reviewedAt':spec['reviewedAt'],'method':spec['method'],'reviewFile':REVIEW,'snapshotNumber':n,'previewSha256':c['previewSha256'],'candidateManifestSha256':spec['candidateManifestSha256'],'noteJa':spec.get('notesJa',{}).get(str(n),'主体の主要な形を画像一覧で確認。' if role=='primary' else '部分・生態等の補足写真。'),'speciesIdentity':'source_caption_or_exact_taxon_checked_not_expert_reidentification','fullResolutionInspection':'contact_sheet_review_not_pixel_level_audit'};applied+=1
    evidence.append({'file':REVIEW,'count':len(roles),'adoptedPhotoPairs':applied,'rejectedCandidates':sum(v=='exclude' for v in roles.values()),'kind':'round2_actual_visual_review'})

def rebuild():
    import run_reviewed_build as runner
    original=runner._original_reviews
    def merged():
        d,e=original();apply_decisions(d,e);return d,e
    runner._original_reviews=merged;runner.main()
    before=load(BATCH+'/baseline.json');after=load('reports/curation-status.json');ad=load(BATCH+'/adoption.json')
    keys=('acceptedPhotographs','acceptedTaxonCoverage','primaryReadyTaxa','chronoearthPrimaryReadyTaxa')
    report={'generatedAt':core.NOW(),'before':{k:before[k] for k in keys},'after':{k:after[k] for k in keys},'change':{k:after[k]-before[k] for k in keys},'newPhotoFiles':ad['savedCount'],'reviewedCandidates':ad['reviewedCount'],'roleCounts':ad['roleCounts'],'primaryGapsRemaining':after['targetCount']-after['primaryReadyTaxa'],'chronoearthPrimaryGapsRemaining':after['chronoearthTargetCount']-after['chronoearthPrimaryReadyTaxa'],'failures':ad['failures']}
    save('reports/continuation-round2-20260914.json',report);print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('gather','adopt','rebuild'));a=p.parse_args()
    {'gather':gather,'adopt':adopt,'rebuild':rebuild}[a.mode]()
