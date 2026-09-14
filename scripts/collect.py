#!/usr/bin/env python3
"""Collect reproducibly licensed real photos; automatic selection is never visual approval."""
from __future__ import annotations
import concurrent.futures, csv, hashlib, html, io, json, os, re, subprocess, threading, time, unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat
ROOT=Path(__file__).resolve().parents[1]
API='https://api.inaturalist.org/v1'
COMMONS='https://commons.wikimedia.org/w/api.php'
UA='CollectImages/1.0 (https://github.com/Matsu71/Collect_Images; licensed species photographs)'
ALLOWED={'cc0':'https://creativecommons.org/publicdomain/zero/1.0/','cc-by':'https://creativecommons.org/licenses/by/4.0/','cc-by-sa':'https://creativecommons.org/licenses/by-sa/4.0/'}
NOW=lambda: datetime.now(timezone.utc).isoformat(timespec='seconds')
SOURCE_URL='https://chronoearth.pages.dev/js/catalog-data.js'
SOURCE_GIT_SHA='e57c23dc953429f8b07405fb10a8bf62b16545f9'
LOCK=threading.Lock();LAST={};THREAD=threading.local()
MAX_TARGETS=int(os.getenv('MAX_TARGETS','1000'))

def dump(path,value):
    p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(p)

def read(path,default=None):
    p=ROOT/path
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default

def clean(s):
    return ' '.join(html.unescape(re.sub('<[^>]+>',' ',str(s or ''))).split())

def slug(s):
    return re.sub(r'[^a-z0-9]+','-',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()).strip('-')

def get(url,params=None,*,binary=False,tries=3):
    host=urlparse(url).hostname or ''
    if not hasattr(THREAD,'session'):
        THREAD.session=requests.Session();THREAD.session.headers['User-Agent']=UA
    for attempt in range(tries):
        interval=1.10 if host=='api.inaturalist.org' else 0.50 if 'wikimedia' in host else 0.12
        with LOCK:
            delay=max(0,LAST.get(host,0)+interval-time.monotonic())
            if delay:time.sleep(delay)
            LAST[host]=time.monotonic()
        try:
            r=THREAD.session.get(url,params=params,timeout=(15,45),stream=binary)
            if r.status_code in (429,500,502,503,504):
                retry=r.headers.get('Retry-After','')
                time.sleep(min(120,float(retry) if retry.isdigit() else 3*(2**attempt)));r.close();continue
            r.raise_for_status()
            if binary:
                buf=bytearray()
                for chunk in r.iter_content(65536):
                    buf.extend(chunk)
                    if len(buf)>24_000_000:raise ValueError('source_photo_over_24_MB')
                r.close();return bytes(buf)
            return r.json()
        except (requests.RequestException,ValueError) as e:
            if attempt+1>=tries:raise RuntimeError(f'{host}: {str(e)[:180]}') from e
            time.sleep(2**attempt)
    raise RuntimeError(f'{host}: retries_exhausted')

def photo_score(photo,is_default=False):
    dims=photo.get('original_dimensions') or {};w,h=dims.get('width',0),dims.get('height',0)
    aspect=max(w,h)/max(1,min(w,h))
    return (4 if photo.get('license_code')=='cc0' else 3 if photo.get('license_code')=='cc-by' else 1)+(7 if is_default else 0)+min(3,min(w,h)/700)-(5 if aspect>2.5 else 0)

def inat_taxon(target):
    if target.get('inatTaxonId'):results=get(API+'/taxa/'+str(target['inatTaxonId'])).get('results',[])
    else:results=get(API+'/taxa',{'q':target['scientificName'],'per_page':10,'all_names':'true','locale':'ja'}).get('results',[])
    wanted=target['scientificName'].lower().strip()
    for t in results:
        if t.get('name','').lower()==wanted and t.get('is_active',True):return t,'exact_scientific_name'
    for t in results:
        aliases=[n.get('name','').lower() for n in t.get('names',[]) if n.get('lexicon')=='Scientific Names']
        if wanted in aliases and t.get('is_active',True):return t,'authority_scientific_synonym'
    return None,'no_exact_taxon_match'

def inat_candidates(target):
    taxon,match=inat_taxon(target)
    if not taxon:return [],{'reason':match}
    if taxon.get('extinct') or not ({1,47126}&set(taxon.get('ancestor_ids',[]))):return [],{'reason':'not_extant_animal_or_plant'}
    candidates=[];default=taxon.get('default_photo') or {}
    for p in [default]+[v.get('photo',v) for v in taxon.get('taxon_photos',[])]:
        if p.get('license_code') in ALLOWED and p.get('id'):candidates.append((p,None,photo_score(p,p.get('id')==default.get('id'))))
    obs=get(API+'/observations',{'taxon_id':taxon['id'],'photos':'true','photo_license':'cc0,cc-by,cc-by-sa','quality_grade':'research','per_page':12,'order_by':'votes','order':'desc'}).get('results',[])
    for o in obs:
        ot=o.get('taxon') or {}
        if ot.get('id')!=taxon['id'] and taxon['id'] not in ot.get('ancestor_ids',[]):continue
        if o.get('quality_grade')!='research':continue
        for pi,p in enumerate(o.get('photos',[])[:3]):
            if p.get('license_code') not in ALLOWED:continue
            sc=photo_score(p)+min(3,o.get('faves_count',0)/3)+(1 if pi==0 else 0)
            candidates.append((p,o,sc))
    seen=set();out=[]
    for p,o,sc in sorted(candidates,key=lambda x:x[2],reverse=True):
        if p['id'] in seen or p.get('flags'):continue
        seen.add(p['id']);code=p['license_code']
        url=p.get('original_url') or re.sub(r'/(square|small|medium|large)\.', '/original.',p.get('url',''))
        if not url.startswith(('https://inaturalist-open-data.s3.amazonaws.com/','https://static.inaturalist.org/','https://inaturalist.ca/','https://static.inaturalist.ca/')):continue
        attribution=clean(p.get('attribution'))
        author=clean(p.get('attribution_name') or p.get('native_realname') or p.get('native_username') or re.sub(r'^\(c\)\s*|,?\s*some rights reserved.*$|,?\s*all rights reserved.*$','',attribution,flags=re.I))
        if not author and o:author=clean((o.get('user') or {}).get('name') or (o.get('user') or {}).get('login'))
        if not author:continue
        out.append({'source':'iNaturalist','imageTitle':target['scientificName'],'sourceId':str(p['id']),'photoUrl':f"https://www.inaturalist.org/photos/{p['id']}",'downloadUrl':url,'originalUrl':url,'licenseCode':code,'licenseUrl':ALLOWED[code],'author':author,'originalAttribution':attribution,'taxonId':taxon['id'],'acceptedScientificName':taxon['name'],'taxonMatch':match,'taxonRank':taxon.get('rank'),'iconicTaxonName':taxon.get('iconic_taxon_name'),'observationUrl':f"https://www.inaturalist.org/observations/{o['id']}" if o else None,'observationQualityGrade':o.get('quality_grade') if o else None,'selectionBasis':'curated_taxon_photo' if o is None else 'research_grade_observation','selectionScore':sc,'photoApiEvidence':p,'observationTaxon':o.get('taxon') if o else None})
    return out,{'taxonId':taxon['id'],'match':match,'candidateCount':len(out),'acceptedScientificName':taxon['name']}

def commons_candidates(target):
    q='"'+target['scientificName']+'" filetype:bitmap -drawing -illustration -skull -skeleton -fossil -map'
    j=get(COMMONS,{'action':'query','format':'json','formatversion':2,'generator':'search','gsrsearch':q,'gsrnamespace':6,'gsrlimit':5,'prop':'imageinfo','iiprop':'url|extmetadata|size|mime|sha1','iiurlwidth':2048})
    out=[]
    for page in j.get('query',{}).get('pages',[]):
        info=(page.get('imageinfo') or [{}])[0];m=info.get('extmetadata',{});val=lambda k:clean(m.get(k,{}).get('value',''))
        lu=val('LicenseUrl').replace('http:','https:');code=None
        if re.fullmatch(r'https://creativecommons\.org/(licenses/by(?:-sa)?/[1-4]\.0(?:/[a-z-]+)?|publicdomain/zero/1\.0)/?',lu):code='cc0' if 'publicdomain/zero' in lu else 'cc-by-sa' if '/by-sa/' in lu else 'cc-by'
        if not code or not val('Artist') or info.get('mime') not in ('image/jpeg','image/png','image/webp'):continue
        text=' '.join([page['title'],val('ImageDescription'),val('Categories')]).lower()
        if target['scientificName'].lower() not in text:continue
        if re.search(r'\b(drawing|illustration|painting|fossil|skeleton|taxidermy|mounted specimen|ai.generated|generative ai|watercolou?r|distribution map)\b',text):continue
        if min(info.get('width',0),info.get('height',0))<500:continue
        score=(4 if code=='cc0' else 3 if code=='cc-by' else 1)+(5 if 'quality image' in text or 'featured picture' in text else 0)
        out.append({'source':'Wikimedia Commons','imageTitle':val('ObjectName') or page['title'],'sourceId':str(page['pageid']),'photoUrl':info.get('descriptionurl'),'downloadUrl':info.get('thumburl') or info.get('url'),'originalUrl':info.get('url'),'licenseCode':code,'licenseUrl':lu,'author':val('Artist'),'originalAttribution':val('Attribution') or val('Credit'),'acceptedScientificName':target['scientificName'],'taxonMatch':'scientific_name_in_file_metadata','taxonRank':None,'selectionBasis':'commons_scientific_name_and_photo_metadata','selectionScore':score,'commonsTitle':page['title'],'imageInfoEvidence':info})
    return sorted(out,key=lambda x:x['selectionScore'],reverse=True)

def prepare_photo(raw):
    im=Image.open(io.BytesIO(raw));im.load()
    if getattr(im,'is_animated',False):raise ValueError('animated_not_photo')
    im=ImageOps.exif_transpose(im).convert('RGB');w,h=im.size
    if max(w,h)<1000 or min(w,h)<500:raise ValueError('insufficient_resolution')
    if max(w,h)/min(w,h)>3:raise ValueError('extreme_aspect_ratio')
    if max(ImageStat.Stat(im.resize((64,64))).stddev)<12:raise ValueError('near_blank_or_low_variation')
    original_dimensions=[w,h];im.thumbnail((2048,2048),Image.Resampling.LANCZOS)
    master=io.BytesIO();im.save(master,'JPEG',quality=92,optimize=True)
    web=im.copy();web.thumbnail((1400,1400),Image.Resampling.LANCZOS);out=io.BytesIO();quality=86
    while True:
        out.seek(0);out.truncate();web.save(out,'WEBP',quality=quality,method=5)
        if out.tell()<=190_000 or quality<=68:break
        quality-=3
    thumb=im.copy();thumb.thumbnail((360,280),Image.Resampling.LANCZOS);buf=io.BytesIO();thumb.save(buf,'WEBP',quality=78,method=4)
    return master.getvalue(),out.getvalue(),buf.getvalue(),original_dimensions,list(im.size),list(web.size),quality

def collect_one(target):
    errors=[]
    try:candidates,detail=inat_candidates(target)
    except Exception as e:candidates=[];detail={};errors.append(str(e))
    for source_round in range(2):
        if source_round==1:
            try:candidates=commons_candidates(target)
            except Exception as e:errors.append(str(e));break
        for c in candidates[:6]:
            try:
                raw=get(c['downloadUrl'],binary=True);master,web,thumb,orig_dim,md,wd,quality=prepare_photo(raw)
                sid=slug(target['scientificName']);pid=('inat-' if c['source']=='iNaturalist' else 'commons-')+c['sourceId'];base=f'images/{sid}/{pid}'
                paths={'master':base+'.jpg','web':base+'.webp','thumbnail':base+'-thumb.webp'}
                for k,b in [('master',master),('web',web),('thumbnail',thumb)]:
                    p=ROOT/paths[k];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
                credits=f"{c['imageTitle']} [{target['scientificName']}] — {c['author']} / {c['source']}, {c['licenseCode'].upper()} ({c['licenseUrl']}); source: {c['photoUrl']}. Original attribution: {c['originalAttribution']}. Resized and re-encoded; no subject alteration."
                record={'schemaVersion':1,'assetId':pid,'targetId':target['id'],'scientificName':target['scientificName'],'nameJa':target.get('nameJa',''),'collectionTier':target.get('collectionTier','chronoearth'),'origin':'real_photograph','status':'collected_pending_visual_review','visualReview':{'status':'pending','fullBodyVisible':'unverified','speciesIdentity':'source_taxonomy_only'},'rightsReview':{'status':'allowed_license_metadata_verified','verifiedAt':NOW(),'commercialReuseAllowedByLicense':True,'attributionRequired':c['licenseCode']!='cc0','shareAlikeRequiredForAdaptation':c['licenseCode']=='cc-by-sa','otherRights':'not_warranted'},'retrievedAt':NOW(),'files':paths,'dimensions':{'source':orig_dim,'master':md,'web':wd},'bytes':{'master':len(master),'web':len(web),'thumbnail':len(thumb)},'sha256':{'download':hashlib.sha256(raw).hexdigest(),'master':hashlib.sha256(master).hexdigest(),'web':hashlib.sha256(web).hexdigest()},'changes':['EXIF orientation applied','proportional downsize only; no crop','JPEG/WebP re-encoding','embedded EXIF removed; provenance retained in metadata'],'webQuality':quality,'credit':credits,**c}
                dump(f'metadata/{sid}/{pid}.json',record)
                return {'targetId':target['id'],'status':'collected','assetId':pid,'metadataPath':f'metadata/{sid}/{pid}.json','details':detail,'candidateRejections':errors[-6:]}
            except Exception as e:errors.append(f"{c.get('sourceId')}: {str(e)[:220]}")
    return {'targetId':target['id'],'status':'missing','scientificName':target['scientificName'],'details':detail,'reasons':errors[-8:] or ['no_licensed_photo_matching_requirements']}

def git_checkpoint(message):
    if not os.getenv('GITHUB_ACTIONS'):return
    def run(*args):return subprocess.run(args,cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    run('git','config','user.name','Collect Images bot');run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    run('git','add','data','images','metadata','catalog','reports','gallery')
    if subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode:
        run('git','commit','-m',message+' [skip ci]')
        for n in range(4):
            try:run('git','pull','--rebase','origin','main');run('git','push','origin','HEAD:main');return
            except subprocess.CalledProcessError:
                if n==3:raise
                time.sleep(3*(n+1))

def rebuild(targets,results,phase):
    records=[json.loads(p.read_text()) for p in sorted((ROOT/'metadata').glob('*/*.json'))]
    seen_ids={r['targetId'] for r in records};base=[t for t in targets if t.get('collectionTier')=='chronoearth']
    status={'generatedAt':NOW(),'phase':phase,'targetCount':len(targets),'chronoearthTargetCount':len(base),'collectedTaxa':len(seen_ids),'photoCount':len(records),'chronoearthCollected':sum(t['id'] in seen_ids for t in base),'extensionCollected':sum(r.get('collectionTier')=='extension' for r in records),'visuallyApproved':sum(r.get('visualReview',{}).get('status')=='approved' for r in records),'pendingVisualReview':sum(r.get('visualReview',{}).get('status')=='pending' for r in records),'licenseCounts':dict(Counter(r['licenseCode'] for r in records)),'sourceCounts':dict(Counter(r['source'] for r in records)),'totalStoredBytes':sum(sum(r['bytes'].values()) for r in records),'missingTargetCount':len(targets)-len(seen_ids),'note':'Downloaded/license-screened and visually approved are separate counts. Identity and full-body visibility are not inferred from successful downloading.'}
    dump('reports/status.json',status);dump('reports/results.json',results)
    dump('reports/missing.json',[{'id':t['id'],'scientificName':t['scientificName'],'nameJa':t.get('nameJa',''),'tier':t.get('collectionTier')} for t in targets if t['id'] not in seen_ids])
    small=[{k:v for k,v in r.items() if k not in ('photoApiEvidence','observationTaxon','imageInfoEvidence')} for r in records]
    dump('catalog/assets.json',{'schemaVersion':1,'generatedAt':NOW(),'records':small})
    with (ROOT/'catalog'/'credits.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['scientificName','nameJa','author','source','photoUrl','licenseCode','licenseUrl','credit'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(records)
    (ROOT/'catalog'/'ATTRIBUTION.md').write_text('# Image attribution\n\nEach photograph retains its own listed license.\n\n'+'\n\n'.join(r['credit'] for r in records)+'\n',encoding='utf-8')
    cards=[]
    for r in records:
        esc=lambda x:html.escape(str(x or ''),quote=True)
        cards.append(f'<article><a href="../{r["files"]["master"]}"><img loading="lazy" src="../{r["files"]["thumbnail"]}" alt="{esc(r["scientificName"])}"></a><h2>{esc(r["nameJa"])} <i>{esc(r["scientificName"])}</i></h2><p>{esc(r["author"])} / <a href="{esc(r["photoUrl"])}">{esc(r["source"])}</a> · <a href="{esc(r["licenseUrl"])}">{esc(r["licenseCode"])}</a></p><small>{esc(r["visualReview"]["status"])} · <a href="../metadata/{slug(r["scientificName"])}/{r["assetId"]}.json">metadata</a></small></article>')
    (ROOT/'gallery'/'index.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>現生生物 写真コレクション</title><style>body{font:15px system-ui;margin:24px;background:#f5f6f8}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:18px}article{background:white;padding:12px;border:1px solid #ddd;border-radius:10px}img{width:100%;height:220px;object-fit:contain}h2{font-size:16px}p,small{font-size:12px}i{font-weight:400}input{font:inherit;padding:10px;width:80%;margin:16px 0}</style><h1>現生生物の実写写真</h1><p>写真本体・作者・ライセンスを保存。自動選定と目視合格は別管理です。</p><input placeholder="生物名・学名・作者で絞り込み" oninput="document.querySelectorAll(\'article\').forEach(e=>e.hidden=!e.textContent.toLowerCase().includes(this.value.toLowerCase()))"><main>'+''.join(cards)+'</main></html>',encoding='utf-8')
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14);sheet_index=[]
    for offset in range(0,len(records),36):
        subset=records[offset:offset+36];sheet=Image.new('RGB',(1800,1620),'white');d=ImageDraw.Draw(sheet)
        for n,r in enumerate(subset):
            x=(n%6)*300;y=(n//6)*270
            with Image.open(ROOT/r['files']['web']) as im:
                im=ImageOps.contain(im,(292,224));sheet.paste(im,(x+(300-im.width)//2,y))
            d.text((x+4,y+228),f"{offset+n+1:04d} {r['scientificName']}"[:36],font=font,fill='black')
            d.text((x+4,y+247),r['licenseCode']+' | '+r['sourceId'],font=font,fill='black')
            sheet_index.append({'number':offset+n+1,'assetId':r['assetId'],'targetId':r['targetId'],'scientificName':r['scientificName'],'sheet':f'sheet-{offset//36+1:03d}.jpg'})
        sheet.save(ROOT/'gallery'/f'sheet-{offset//36+1:03d}.jpg',quality=90)
    dump('gallery/sheet-index.json',sheet_index)
    print(json.dumps(status,ensure_ascii=False),flush=True)

def load_targets():
    existing=read('data/targets.json')
    if existing:return existing['records']
    raw=get(SOURCE_URL,binary=True);text=raw.decode('utf-8');dec=json.JSONDecoder();obj=None
    for m in re.finditer(r'\{\s*"',text):
        try:
            candidate,_=dec.raw_decode(text[m.start():])
            if isinstance(candidate,dict) and 'events' in candidate:obj=candidate;break
        except ValueError:pass
    if obj is None:raise RuntimeError('public_catalog_not_parseable')
    targets=[]
    for e in obj['events']:
        if not(e.get('isExtant') is True and e.get('recordKind')=='organism'):continue
        sn=e.get('scientific')
        if not sn:continue
        targets.append({'id':e.get('organismId') or e['id'].replace('evt-organism-','org-'),'nameJa':e.get('name',''),'scientificName':sn,'collectionTier':'chronoearth','chronoearthEventId':e['id'],'sourceType':e.get('type'),'displayEligible':e.get('displayEligible')})
    if len(targets)<450:
        dump('reports/import-diagnostic.json',{'events':len(obj['events']),'targetsFound':len(targets),'sampleEvents':obj['events'][:3]})
        raise RuntimeError(f'source_import_requires_schema_review: {len(targets)}')
    targets=list({t['scientificName']:t for t in targets}.values())
    actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    dump('data/targets.json',{'schemaVersion':1,'source':SOURCE_URL,'sourceRepository':'Matsu71/ChronoEarth','sourceBlobSha':actual,'checkedRepoBlobSha':SOURCE_GIT_SHA,'exactSourceMatch':actual==SOURCE_GIT_SHA,'retrievedAt':NOW(),'records':targets})
    return targets

def expansion_targets(targets):
    if len(targets)>=MAX_TARGETS:return targets
    names={t['scientificName'].lower() for t in targets};extra=[]
    for kingdom in [1,47126]:
        j=get(API+'/observations/species_counts',{'taxon_id':kingdom,'quality_grade':'research','photo_license':'cc0,cc-by,cc-by-sa','per_page':500,'page':1,'locale':'ja'})
        for item in j.get('results',[]):
            t=item.get('taxon') or {};sn=t.get('name','')
            if t.get('rank')!='species' or t.get('extinct') or not sn or sn.lower() in names:continue
            names.add(sn.lower());extra.append({'id':'inat-taxon-'+str(t['id']),'nameJa':t.get('preferred_common_name',''),'scientificName':sn,'inatTaxonId':t['id'],'collectionTier':'extension','kingdomId':kingdom})
    animal=[t for t in extra if t['kingdomId']==1];plant=[t for t in extra if t['kingdomId']==47126];ordered=[]
    for a,b in zip(animal,plant):ordered.extend([a,b])
    ordered+=animal[len(plant):]+plant[len(animal):]
    targets+=ordered[:max(0,MAX_TARGETS-len(targets))]
    doc=read('data/targets.json');doc['records']=targets;doc['extensionSource']='iNaturalist research-grade species counts; commercial-photo-license filter';dump('data/targets.json',doc)
    return targets

def main():
    for d in ['data','images','metadata','catalog','reports','gallery']:(ROOT/d).mkdir(exist_ok=True)
    targets=load_targets();results=read('reports/results.json',[])
    done={json.loads(p.read_text())['targetId'] for p in (ROOT/'metadata').glob('*/*.json')}
    for stage in ['chronoearth','extension']:
        if stage=='extension':
            try:targets=expansion_targets(targets)
            except Exception as e:dump('reports/expansion-error.json',{'error':str(e),'at':NOW()});continue
        queue=[t for t in targets if t.get('collectionTier')==stage and t['id'] not in done]
        rebuild(targets,results,stage+'_collecting')
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(collect_one,t):t for t in queue}
            for n,f in enumerate(concurrent.futures.as_completed(futures),1):
                t=futures[f]
                try:r=f.result()
                except Exception as e:r={'targetId':t['id'],'status':'error','reason':str(e)}
                results=[v for v in results if v['targetId']!=t['id']]+[r]
                if r['status']=='collected':done.add(t['id'])
                print(f"{stage} {n}/{len(queue)} {t['scientificName']}: {r['status']}",flush=True)
                if n%50==0:
                    rebuild(targets,results,stage+'_collecting');git_checkpoint(f'Collect and verify licensed photographs: {len(done)} taxa')
        rebuild(targets,results,stage+'_pass_complete');git_checkpoint(f'Complete {stage} photo collection pass: {len(done)} taxa')
    rebuild(targets,results,'collection_pass_complete_visual_review_pending')
    checked=0
    for p in (ROOT/'metadata').glob('*/*.json'):
        r=json.loads(p.read_text());assert r['licenseCode'] in ALLOWED
        assert r['author'] and r['licenseUrl'] and r['photoUrl']
        for k in ('master','web'):
            b=(ROOT/r['files'][k]).read_bytes();assert hashlib.sha256(b).hexdigest()==r['sha256'][k]
            with Image.open(io.BytesIO(b)) as im:im.verify()
        checked+=1
    dump('reports/file-validation.json',{'validatedAt':NOW(),'metadataRecordsChecked':checked,'hashesAndImageDecode':'pass','licenseWhitelistAndCredits':'pass','visualSpeciesReview':'separate_pending_review'})

if __name__=='__main__':main()
