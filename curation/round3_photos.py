#!/usr/bin/env python3
"""Round 3: category search and alternate observations; immutable, review-gated photo files."""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, io, json, re, sys
from collections import Counter
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import collect as core
import round2_photos as previous
BATCH='batches/gaps-round3-20260914'
REVIEW='reviews/round3-decisions-20260914.json'
LIC=previous.LIC
BAD=re.compile(r'\b(drawing|illustration|painting|engraving|diagram|distribution map|spectrogram|protein structure|phylogenetic|taxidermy|skeleton|skull|replica|statue|sculpture|3d.model|footprints?|dead specimen|preserved specimen|pinned specimen|generative ai|ai.generated)\b',re.I)
PART=re.compile(r'\b(flowers?|fruits?|leaves|leaf|bark|seeds?|portrait|head|detail|close.up|buds?|pollen|feathers?|eggs?)\b',re.I)
WHOLE=re.compile(r'\b(habit|habitus|whole|wuchs|baum|arbre|entire|full.body|standing|walking|tree|shrub)\b',re.I)

def load(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def save(p,v):core.dump(p,v)
def sha(b):return hashlib.sha256(b).hexdigest()

def seen_assets():
    seen=set()
    for folder in ('metadata','reference/metadata'):
        for p in (ROOT/folder).glob('*/*.json'):
            r=json.loads(p.read_text());seen.add((r['targetId'],r['assetId']))
    for p in (ROOT/'batches').glob('*/candidates.json'):
        for c in json.loads(p.read_text()).get('records',[]):seen.add((c['target']['id'],c['assetId']))
    return seen

def commons_query(target,params,seen):
    common={'action':'query','format':'json','formatversion':2,'prop':'imageinfo','iiprop':'url|extmetadata|size|mime|sha1','iiurlwidth':1600}
    data=core.get(core.COMMONS,{**common,**params});out=[]
    for page in data.get('query',{}).get('pages',[]):
        info=(page.get('imageinfo') or [{}])[0];m=info.get('extmetadata',{});value=lambda k:core.clean(m.get(k,{}).get('value',''))
        aid='commons-'+str(page['pageid']);title=page['title'];caption=value('ImageDescription');cats=value('Categories')
        url=value('LicenseUrl').replace('http:','https:');author=value('Artist');w,h=info.get('width',0),info.get('height',0)
        if (target['id'],aid) in seen or not LIC.fullmatch(url) or not author:continue
        if info.get('mime') not in ('image/jpeg','image/png','image/webp') or min(w,h)<500 or max(w,h)<1000:continue
        if max(w,h)/min(w,h)>3 or BAD.search(title+' '+caption[:500]):continue
        if target['scientificName'].lower() not in (title+' '+caption).replace('_',' ').lower():continue
        code='cc0' if '/zero/' in url else 'cc-by-sa' if '/by-sa/' in url else 'cc-by'
        score=12*bool(WHOLE.search(title))+5*bool(WHOLE.search(caption[:250]))-11*bool(PART.search(title))-3*bool(PART.search(caption[:140]))
        score+=5*bool(re.search('Quality images|Featured pictures',cats,re.I))+min(3,min(w,h)/900)
        if re.search('micrograph|SEM|TEM|microscopy',title,re.I):score+=6
        out.append({'target':target,'assetId':aid,'source':'Wikimedia Commons','sourceId':str(page['pageid']),'photoUrl':info['descriptionurl'],'sourceUrl':info.get('thumburl') or info['url'],'originalUrl':info['url'],'licenseCode':code,'licenseUrl':url,'author':author,'imageTitle':value('ObjectName') or title,'originalAttribution':value('Attribution') or value('Credit'),'sourceTitle':title,'caption':caption,'imageInfoEvidence':info,'score':score,'acquiredAt':core.NOW(),'identityBasis':'exact_scientific_name_in_source_title_or_caption','sourceSearchRoute':params.get('generator')})
    return out

def observation_candidates(target,seen):
    taxon,match=core.inat_taxon(target)
    if not taxon or match!='exact_scientific_name' or taxon.get('extinct'):return []
    data=core.get(core.API+'/observations',{'taxon_id':taxon['id'],'photos':'true','photo_license':'cc0,cc-by,cc-by-sa','quality_grade':'research','per_page':30,'page':2,'order_by':'votes','order':'desc'})
    out=[]
    for obs in data.get('results',[]):
        ot=obs.get('taxon') or {}
        if taxon['id']!=ot.get('id') and taxon['id'] not in ot.get('ancestor_ids',[]):continue
        for p in obs.get('photos',[])[:2]:
            aid='inat-'+str(p['id']);code=p.get('license_code')
            if (target['id'],aid) in seen or code not in core.ALLOWED or p.get('flags'):continue
            attribution=core.clean(p.get('attribution'))
            author=core.clean(p.get('attribution_name') or p.get('native_realname') or p.get('native_username'))
            if not author and attribution.lower().startswith('(c)'):author=re.sub(r'^\(c\)\s*|,?\s*some rights reserved.*$','',attribution,flags=re.I).strip()
            if not author and code=='cc0':author='unknown'
            if not author:continue
            url=p.get('original_url') or re.sub(r'/(square|small|medium|large)\.', '/original.',p.get('url',''))
            if not url.startswith(('https://inaturalist-open-data.s3.amazonaws.com/','https://static.inaturalist.org/','https://static.inaturalist.ca/')):continue
            out.append({'target':target,'assetId':aid,'source':'iNaturalist','sourceId':str(p['id']),'photoUrl':f"https://www.inaturalist.org/photos/{p['id']}",'sourceUrl':url,'originalUrl':url,'licenseCode':code,'licenseUrl':core.ALLOWED[code],'author':author,'originalAttribution':attribution,'imageTitle':target['scientificName'],'sourceTitle':target['scientificName'],'caption':target['scientificName']+'; research-grade observation; '+core.clean(obs.get('description')),'photoApiEvidence':p,'observationUrl':f"https://www.inaturalist.org/observations/{obs['id']}",'observationTaxon':ot,'observationQualityGrade':obs.get('quality_grade'),'score':min(7,obs.get('faves_count',0)/3),'acquiredAt':core.NOW(),'identityBasis':'exact_iNaturalist_taxon_with_research_grade_observation'})
    return out

def gather_one(target,seen):
    candidates=[];errors=[]
    queries=[{'generator':'categorymembers','gcmtitle':'Category:'+target['scientificName'],'gcmtype':'file','gcmlimit':50},
             {'generator':'search','gsrsearch':'"'+target['scientificName']+'" filetype:bitmap -drawing -illustration -diagram -map','gsrnamespace':6,'gsrlimit':50,'gsroffset':35}]
    for params in queries:
        try:candidates.extend(commons_query(target,params,seen))
        except Exception as e:errors.append(str(e))
    try:candidates.extend(observation_candidates(target,seen))
    except Exception as e:errors.append(str(e))
    unique={c['assetId']:c for c in candidates};ranked=sorted(unique.values(),key=lambda c:c['score'],reverse=True)
    # Up to two category/search photos and one distinct observation, then fill remaining slots.
    cm=[c for c in ranked if c['source']=='Wikimedia Commons'];ino=[c for c in ranked if c['source']=='iNaturalist']
    ordered=cm[:2]+ino[:1]+cm[2:]+ino[1:];saved=[];hashes=set()
    for c in ordered[:12]:
        if len(saved)>=3:break
        try:
            raw=core.get(c['sourceUrl'],binary=True)
            with Image.open(io.BytesIO(raw)) as source:
                if getattr(source,'n_frames',1)!=1:raise ValueError('multi_frame_file_requires_separate_review')
                source.load();im=ImageOps.exif_transpose(source).convert('RGB')
            if min(im.size)<500 or max(im.size)<1000 or max(im.size)/min(im.size)>3:raise ValueError('saved_resolution_or_aspect_ratio')
            im.thumbnail((1600,1600),Image.Resampling.LANCZOS);buf=io.BytesIO();im.save(buf,'JPEG',quality=92,optimize=True);b=buf.getvalue()
            if sha(b) in hashes:continue
            hashes.add(sha(b));p=f"{BATCH}/previews/{core.slug(target['scientificName'])}--{c['assetId']}.jpg"
            (ROOT/p).parent.mkdir(parents=True,exist_ok=True);(ROOT/p).write_bytes(b)
            c.update({'previewPath':p,'previewSha256':sha(b),'previewDimensions':list(im.size),'sourceDownloadSha256':sha(raw),'status':'unreviewed_candidate'});saved.append(c)
        except Exception as e:errors.append(c['assetId']+': '+str(e))
    return saved,{'targetId':target['id'],'scientificName':target['scientificName'],'savedCandidates':len(saved),'eligibleCandidates':len(ranked),'errors':errors}

def gather():
    if (ROOT/BATCH/'candidates.json').exists():raise ValueError('Immutable candidate manifest already exists')
    baseline=load('reports/curation-status.json');save(BATCH+'/baseline.json',baseline)
    alltargets={t['id']:t for t in load('data/targets.json')['records']};gaps=load('reports/primary-gaps.json');save(BATCH+'/target-gaps.json',gaps)
    targets=[alltargets[t['id']] for t in gaps];targets.sort(key=lambda t:(t.get('collectionTier')!='chronoearth',t['scientificName']))
    seen=seen_assets();records=[];results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        fs={pool.submit(gather_one,t,seen):t for t in targets}
        for n,f in enumerate(concurrent.futures.as_completed(fs),1):
            try:cs,r=f.result();records.extend(cs);results.append(r)
            except Exception as e:results.append({'targetId':fs[f]['id'],'error':str(e)})
            if n%10==0:print(json.dumps({'processed':n,'targets':len(targets),'savedCandidates':len(records)}),flush=True)
    rank={t['id']:i for i,t in enumerate(targets)};records.sort(key=lambda c:(rank[c['target']['id']],-c['score'],c['assetId']))
    for n,c in enumerate(records,1):c['number']=n
    save(BATCH+'/candidates.json',{'schemaVersion':1,'generatedAt':core.NOW(),'records':records});save(BATCH+'/results.json',results)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',16);folder=ROOT/BATCH/'sheets';folder.mkdir(parents=True,exist_ok=True)
    for start in range(0,len(records),16):
        sheet=Image.new('RGB',(1800,1720),'white');draw=ImageDraw.Draw(sheet)
        for n,c in enumerate(records[start:start+16]):
            x=n%4*450;y=n//4*430
            with Image.open(ROOT/c['previewPath']) as im:
                im=ImageOps.contain(im,(440,360));sheet.paste(im,(x+(450-im.width)//2,y+(360-im.height)//2))
            draw.text((x+6,y+366),f"{c['number']:03d} {c['target']['scientificName']}"[:49],font=font,fill='black')
            draw.text((x+6,y+392),c['assetId']+' '+c['licenseCode'],font=font,fill='black')
        sheet.save(folder/f'round3-{start//16+1:03d}.jpg',quality=92)
    save(BATCH+'/status.json',{'generatedAt':core.NOW(),'gapTargets':len(targets),'newCandidateImages':len(records),'candidateTaxa':len({c['target']['id'] for c in records}),'sourceCounts':dict(Counter(c['source'] for c in records)),'candidateManifestSha256':sha((ROOT/BATCH/'candidates.json').read_bytes()),'adoptedCount':0,'visualReview':'pending'})
    print(json.dumps(load(BATCH+'/status.json')),flush=True)

def review_data():
    spec=load(REVIEW);raw=(ROOT/BATCH/'candidates.json').read_bytes()
    if sha(raw)!=spec['candidateManifestSha256']:raise ValueError('Immutable candidate manifest hash mismatch')
    candidates={c['number']:c for c in json.loads(raw)['records']};roles={}
    for role,field in [('primary','primaryNumbers'),('supplementary','supplementaryNumbers'),('exclude','excludeNumbers')]:
        for n in spec.get(field,[]):
            if n not in candidates or n in roles:raise ValueError('Unknown or duplicated review number')
            roles[n]=role
    if set(roles)!=set(candidates) or len(roles)!=spec['reviewedCount']:raise ValueError('Every candidate must be explicitly reviewed')
    return spec,candidates,roles

def adopt():
    spec,cs,roles=review_data();saved=[];failures=[]
    for n,c in cs.items():
        if roles[n]=='exclude':continue
        t=c['target'];meta=f"reference/metadata/{core.slug(t['scientificName'])}/{c['assetId']}.json"
        try:
            b=(ROOT/c['previewPath']).read_bytes()
            if sha(b)!=c['previewSha256']:raise ValueError('Image bytes differ from actual reviewed image')
            if (ROOT/meta).exists():
                old=load(meta)
                if old.get('acquisitionBatch')!=BATCH or old['sha256']['master']!=sha(b):raise ValueError('Existing distinct asset cannot be overwritten')
                saved.append({'number':n,'targetId':t['id'],'assetId':c['assetId'],'metadataPath':meta,'recommendedRole':roles[n],'alreadySaved':True});continue
            with Image.open(io.BytesIO(b)) as source:source.load();im=source.convert('RGB')
            base=f"reference/images/{core.slug(t['scientificName'])}/{c['assetId']}";paths={'master':base+'.jpg','web':base+'.webp','thumbnail':base+'-thumb.webp'}
            web=im.copy();web.thumbnail((1400,1400),Image.Resampling.LANCZOS);wb=io.BytesIO();q=85
            while True:
                wb.seek(0);wb.truncate();web.save(wb,'WEBP',quality=q,method=5)
                if wb.tell()<=190000 or q<=68:break
                q-=3
            thumb=im.copy();thumb.thumbnail((360,280),Image.Resampling.LANCZOS);tb=io.BytesIO();thumb.save(tb,'WEBP',quality=78,method=4)
            payload={'master':b,'web':wb.getvalue(),'thumbnail':tb.getvalue()}
            for k,v in payload.items():
                p=ROOT/paths[k];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v)
            rec={k:v for k,v in c.items() if k not in ('target','number','score','status')}
            rec.update({'schemaVersion':1,'targetId':t['id'],'scientificName':t['scientificName'],'nameJa':t.get('nameJa',''),'collectionTier':t.get('collectionTier'),'files':paths,'dimensions':{'master':list(im.size),'web':list(web.size)},'bytes':{k:len(v) for k,v in payload.items()},'sha256':{k:sha(v) for k,v in payload.items()},'origin':'photo_candidate','status':'collected_pending_visual_review','visualReview':{'status':'pending'},'acquisitionBatch':BATCH,'retrievedAt':c['acquiredAt'],'savedAt':core.NOW(),'rightsReview':{'status':'allowed_photo_license_verified_at_acquisition','verifiedAt':c['acquiredAt'],'commercialReuseAllowedByLicense':True,'attributionRequired':c['licenseCode']!='cc0','shareAlikeRequiredForAdaptation':c['licenseCode']=='cc-by-sa','otherRights':'not_warranted'},'changes':['Master is the exact saved and visually reviewed 1600px-or-smaller JPEG derivative, not original source bytes','WebP/thumbnail proportional resizing and re-encoding only; no crop or generative alteration'],'webQuality':q})
            rec['credit']=f"{rec['imageTitle']} [{rec['scientificName']}] — {rec['author']} / {rec['source']}, {rec['licenseCode']} ({rec['licenseUrl']}); source: {rec['photoUrl']}. Proportionally resized and re-encoded; no subject alteration."
            save(meta,rec);saved.append({'number':n,'targetId':t['id'],'assetId':c['assetId'],'metadataPath':meta,'recommendedRole':roles[n]})
        except Exception as e:failures.append({'number':n,'error':str(e)})
    save(BATCH+'/adoption.json',{'generatedAt':core.NOW(),'reviewedCount':len(roles),'roleCounts':dict(Counter(roles.values())),'savedCount':len(saved),'saved':saved,'failures':failures,'masterEqualsReviewedJPEG':True})
    if failures:raise ValueError(str(failures))

def apply_decisions(decisions,evidence):
    if not (ROOT/REVIEW).exists():return
    spec,cs,roles=review_data();applied=0
    for n,c in cs.items():
        if roles[n]=='exclude':continue
        meta=ROOT/f"reference/metadata/{core.slug(c['target']['scientificName'])}/{c['assetId']}.json"
        if not meta.exists():continue
        r=json.loads(meta.read_text())
        if r.get('acquisitionBatch')!=BATCH or r['sha256']['master']!=c['previewSha256']:raise ValueError('Review does not match saved master')
        decisions[c['target']['id']+'|'+c['assetId']]={'status':'screened','recommendedRole':roles[n],'reviewer':spec['reviewer'],'reviewedAt':spec['reviewedAt'],'method':spec['method'],'reviewFile':REVIEW,'snapshotNumber':n,'candidateManifestSha256':spec['candidateManifestSha256'],'previewSha256':c['previewSha256'],'noteJa':spec.get('notesJa',{}).get(str(n),'主体の主要な形を画像一覧で確認。' if roles[n]=='primary' else '部分・生態等の補足用。'),'speciesIdentity':'source_caption_or_exact_taxon_checked_not_expert_reidentification','fullResolutionInspection':'contact_sheet_screening_not_pixel_level_audit'};applied+=1
    evidence.append({'file':REVIEW,'count':len(roles),'adoptedPhotoPairs':applied,'excludedCandidateCount':sum(r=='exclude' for r in roles.values()),'kind':'round3_actual_visual_review'})

def rebuild():
    import run_reviewed_build as runner
    old=runner._original_reviews
    def merged():
        d,e=old();apply_decisions(d,e);return d,e
    runner._original_reviews=merged;runner.main()
    before=load(BATCH+'/baseline.json');after=load('reports/curation-status.json');adoption=load(BATCH+'/adoption.json');keys=('acceptedPhotographs','acceptedTaxonCoverage','primaryReadyTaxa','chronoearthPrimaryReadyTaxa')
    save('reports/continuation-round3-20260914.json',{'generatedAt':core.NOW(),'before':{k:before[k] for k in keys},'after':{k:after[k] for k in keys},'change':{k:after[k]-before[k] for k in keys},'newSavedPhotoCount':adoption['savedCount'],'reviewedCandidates':adoption['reviewedCount'],'roleCounts':adoption['roleCounts'],'primaryGapsRemaining':after['targetCount']-after['primaryReadyTaxa'],'chronoearthPrimaryGapsRemaining':after['chronoearthTargetCount']-after['chronoearthPrimaryReadyTaxa'],'failures':adoption['failures']})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('gather','adopt','rebuild'));a=p.parse_args();{'gather':gather,'adopt':adopt,'rebuild':rebuild}[a.mode]()
