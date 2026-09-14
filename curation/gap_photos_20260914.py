#!/usr/bin/env python3
"""Gap-first acquisition. Preview and visual approval precede master-image adoption."""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, io, json, re, sys, time
from pathlib import Path
from collections import Counter
from PIL import Image, ImageDraw, ImageFont, ImageOps
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import collect as core
import collect_reference as ref
BATCH='batches/gaps-20260914'
PREFIX=ROOT/BATCH
BAD=re.compile(r'\b(drawing|illustration|painting|lithograph|engraving|sculpture|statue|diagram|phylogeny|phylogenetic|distribution map|protein structure|molecular structure|taxidermy|skeleton|skull|mounted specimen|dead specimen|preserved specimen|pinned specimen|ai.generated|generative ai|footprints?|tracks|spectrogram)\b',re.I)
PART=re.compile(r'\b(leaf|leaves|flower|flowers|bark|fruit|fruits|seed|seeds|portrait|head|close.up|detail|egg|eggs|larva|larvae|pupa|pupae|wing|wings|feather|feathers)\b',re.I)
LIC=re.compile(r'https://creativecommons\.org/(licenses/by(?:-sa)?/(?:[1-4]\.0|2\.5)(?:/[a-z-]+)?|publicdomain/zero/1\.0)/?')

def load(p,default=None):
    p=ROOT/p
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default

def save(p,data):core.dump(str(p),data)

def existing_pairs():
    seen=set()
    for folder in ('metadata','reference/metadata'):
        for p in (ROOT/folder).glob('*/*.json'):
            r=json.loads(p.read_text());seen.add((r['targetId'],r['assetId']))
    return seen

def candidate(page,target,seen,lead=None):
    info=(page.get('imageinfo') or [{}])[0];m=info.get('extmetadata',{})
    val=lambda k:core.clean(m.get(k,{}).get('value',''))
    lu=val('LicenseUrl').replace('http:','https:')
    if not LIC.fullmatch(lu) or not val('Artist'):return None
    if info.get('mime') not in ('image/jpeg','image/png','image/webp'):return None
    w,h=info.get('width',0),info.get('height',0)
    if min(w,h)<500 or max(w,h)<1200 or max(w,h)/max(1,min(w,h))>3:return None
    pid='commons-'+str(page['pageid'])
    if (target['id'],pid) in seen:return None
    title=page['title'];desc=val('ImageDescription');cats=val('Categories')
    text=' '.join([title,desc,cats])
    if BAD.search(text):return None
    name=target['scientificName'].lower()
    in_caption=name in (title+' '+desc).replace('_',' ').lower()
    if not lead and not in_caption:return None
    code='cc0' if '/zero/' in lu else 'cc-by-sa' if '/by-sa/' in lu else 'cc-by'
    score=(12 if lead else 0)+(8 if name in title.replace('_',' ').lower() else 0)
    score+=12 if re.search('featured pictures|quality images',cats,re.I) else 0
    score+=min(4,min(w,h)/700)
    score-=10 if PART.search(title) else 0
    score-=5 if PART.search(desc[:240]) else 0
    score+=5 if re.search(r'\b(habit|whole plant|full.body|entire|tree)\b',title+' '+desc[:240],re.I) else 0
    return {'target':target,'page':page,'info':info,'assetId':pid,'licenseCode':code,'licenseUrl':lu,'author':val('Artist'),'imageTitle':val('ObjectName') or title,'originalAttribution':val('Attribution') or val('Credit'),'wikipediaPage':lead or {'title':target['scientificName'],'requestedScientificName':target['scientificName'],'fileTitle':title,'url':None},'selectionBasis':'wikipedia_lead_photo' if lead else 'exact_scientific_name_in_file_title_or_description','selectionScore':score,'sourceCaption':desc,'sourceCaptionMatchesRequestedName':in_caption,'sourceMetadataRetrievedAt':core.NOW()}

def search_target(target,seen,lead_candidates):
    found=list(lead_candidates);errors=[]
    q='"'+target['scientificName']+'" filetype:bitmap -drawing -illustration -map -skeleton -fossil -diagram -portrait'
    try:
        j=core.get(core.COMMONS,{'action':'query','format':'json','formatversion':2,'generator':'search','gsrsearch':q,'gsrnamespace':6,'gsrlimit':12,'prop':'imageinfo','iiprop':'url|extmetadata|size|mime|sha1','iiurlwidth':1280})
        for page in j.get('query',{}).get('pages',[]):
            c=candidate(page,target,seen)
            if c:found.append(c)
    except Exception as e:errors.append(str(e))
    unique={c['assetId']:c for c in sorted(found,key=lambda c:c['selectionScore'])}
    ordered=sorted(unique.values(),key=lambda c:c['selectionScore'],reverse=True)
    result=[]
    for c in ordered[:8]:
        if len(result)>=2:break
        try:
            raw=core.get(c['info'].get('thumburl') or c['info']['url'],binary=True)
            im=Image.open(io.BytesIO(raw));im.load();im=ImageOps.exif_transpose(im).convert('RGB')
            if min(im.size)<450:raise ValueError('preview_too_small')
            im.thumbnail((1280,1280),Image.Resampling.LANCZOS)
            p=Path(BATCH)/'previews'/(core.slug(target['scientificName'])+'--'+c['assetId']+'.jpg')
            (ROOT/p).parent.mkdir(parents=True,exist_ok=True);im.save(ROOT/p,'JPEG',quality=90,optimize=True)
            c['previewPath']=str(p);c['previewSha256']=hashlib.sha256((ROOT/p).read_bytes()).hexdigest();c['previewDimensions']=list(im.size)
            c['status']='candidate_pending_visual_review';result.append(c)
        except Exception as e:errors.append(c['assetId']+': '+str(e))
    return result,{'targetId':target['id'],'scientificName':target['scientificName'],'newCandidates':len(result),'eligibleCandidates':len(ordered),'errors':errors}

def lead_candidates(targets,seen):
    mapped,missing=ref.resolve_pages(targets)
    bytarget={};errors=list(missing)
    for start in range(0,len(mapped),5):
        batch=mapped[start:start+5]
        try:
            j=core.get(core.COMMONS,{'action':'query','format':'json','formatversion':2,'titles':'|'.join(i['wikipediaPage']['fileTitle'] for i in batch),'redirects':1,'prop':'imageinfo','iiprop':'url|extmetadata|size|mime|sha1','iiurlwidth':1280})
            q=j.get('query',{});aliases={n['from']:n['to'] for n in q.get('normalized',[])+q.get('redirects',[])};pages={p['title']:p for p in q.get('pages',[])}
            for item in batch:
                name=item['wikipediaPage']['fileTitle'];visited=set()
                while name in aliases and name not in visited:visited.add(name);name=aliases[name]
                p=pages.get(name)
                if p:
                    c=candidate(p,item['target'],seen,item['wikipediaPage'])
                    if c:bytarget.setdefault(item['target']['id'],[]).append(c)
        except Exception as e:errors.append({'batchStart':start,'error':str(e)})
    return bytarget,errors

def make_sheets(records):
    folder=PREFIX/'sheets';folder.mkdir(parents=True,exist_ok=True)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14)
    for start in range(0,len(records),24):
        sheet=Image.new('RGB',(1920,1560),'white');draw=ImageDraw.Draw(sheet)
        for n,r in enumerate(records[start:start+24]):
            x=n%6*320;y=n//6*390
            with Image.open(ROOT/r['previewPath']) as im:
                im=ImageOps.contain(im,(312,330));sheet.paste(im,(x+(320-im.width)//2,y+(330-im.height)//2))
            draw.text((x+4,y+334),f"{r['number']:04d} {r['target']['scientificName']}"[:40],font=font,fill='black')
            draw.text((x+4,y+355),r['assetId']+' '+r['licenseCode'],font=font,fill='black')
        sheet.save(folder/f'sheet-{start//24+1:03d}.jpg',quality=92)

def gather():
    if (PREFIX/'candidates.json').exists():raise RuntimeError('Batch already exists; preserve immutable review evidence.')
    targets=load('data/targets.json')['records'];gaps={t['id'] for t in load('reports/primary-gaps.json')}
    selected=[t for t in targets if t['id'] in gaps]
    selected.sort(key=lambda t:(t.get('collectionTier')!='chronoearth',t['scientificName'].lower()))
    seen=existing_pairs();leads,errors=lead_candidates(selected,seen)
    all_candidates=[];results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(search_target,t,seen,leads.get(t['id'],[])):t for t in selected}
        for n,f in enumerate(concurrent.futures.as_completed(futures),1):
            try:c,r=f.result();all_candidates.extend(c);results.append(r)
            except Exception as e:results.append({'targetId':futures[f]['id'],'error':str(e)})
            if n%25==0:print(json.dumps({'processed':n,'targets':len(selected),'newLicensedPreviews':len(all_candidates)}),flush=True)
    order={t['id']:i for i,t in enumerate(selected)}
    all_candidates.sort(key=lambda c:(order[c['target']['id']],-c['selectionScore'],c['assetId']))
    for n,c in enumerate(all_candidates,1):c['number']=n
    save(BATCH+'/candidates.json',{'schemaVersion':1,'createdAt':core.NOW(),'purpose':'Fill missing primary images, not inflate already-covered taxa','targetCount':len(selected),'records':all_candidates})
    save(BATCH+'/results.json',results);save(BATCH+'/lead-errors.json',errors);make_sheets(all_candidates)
    status={'generatedAt':core.NOW(),'gapTargets':len(selected),'candidateImages':len(all_candidates),'targetsWithCandidates':len({c['target']['id'] for c in all_candidates}),'baseTargetsWithCandidates':len({c['target']['id'] for c in all_candidates if c['target'].get('collectionTier')=='chronoearth'}),'licenseCounts':dict(Counter(c['licenseCode'] for c in all_candidates)),'reviewStatus':'pending_actual_visual_review','previewImagesStored':True,'primaryAdoptionCount':0}
    save(BATCH+'/status.json',status);print(json.dumps(status),flush=True)

def adopt(review_file):
    spec=load(review_file);manifest=load(BATCH+'/candidates.json');indexed={c['number']:c for c in manifest['records']}
    if hashlib.sha256((PREFIX/'candidates.json').read_bytes()).hexdigest()!=spec['candidateManifestSha256']:raise ValueError('Candidate snapshot hash mismatch')
    roles={}
    for role,field in [('primary','primaryNumbers'),('supplementary','supplementaryNumbers'),('exclude','excludeNumbers')]:
        for n in spec.get(field,[]):
            if n in roles or n not in indexed:raise ValueError('Invalid/duplicate review number')
            roles[n]=role
    if len(roles)!=spec['reviewedCount']:raise ValueError('Review count mismatch')
    for p in ('images','metadata','gallery'):(ROOT/'reference'/p).mkdir(parents=True,exist_ok=True)
    saved=[];failures=[]
    for n,role in roles.items():
        if role=='exclude':continue
        c=indexed[n];t=c['target'];sid=core.slug(t['scientificName']);dest=f'reference/metadata/{sid}/{c["assetId"]}.json'
        try:
            if not (ROOT/dest).exists():ref.collect_image(c)
            rec=load(dest);rec['selectionBasis']=c['selectionBasis'];rec['taxonMatch']='scientific_name_wikipedia_lead' if c['selectionBasis']=='wikipedia_lead_photo' else 'exact_scientific_name_in_file_title_or_description'
            rec['sourceCaption']=c['sourceCaption'];rec['acquisitionBatch']=BATCH;rec['reviewedPreviewSha256']=c['previewSha256'];rec['reviewedPreviewPath']=c['previewPath'];save(dest,rec)
            saved.append({'number':n,'targetId':t['id'],'assetId':c['assetId'],'metadataPath':dest,'recommendedRole':role})
        except Exception as e:failures.append({'number':n,'targetId':t['id'],'error':str(e)})
    save(BATCH+'/adoption.json',{'generatedAt':core.NOW(),'reviewFile':review_file,'saved':saved,'failures':failures,'note':'Only explicitly visually selected photographs are promoted to reference/images. Rejected previews are retained as audit evidence, not adopted.'})
    print(json.dumps({'saved':len(saved),'failed':len(failures)}),flush=True)
    if failures:raise RuntimeError('Some selected images could not be saved; preserve partial progress and retry.')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['gather','adopt']);ap.add_argument('--review',default='reviews/gap-20260914.json');args=ap.parse_args()
    if args.mode=='gather':gather()
    else:adopt(args.review)
