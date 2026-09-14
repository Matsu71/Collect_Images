#!/usr/bin/env python3
"""Add Wikipedia lead/Commons photographs; do not treat a lead image as visual approval."""
from __future__ import annotations
import concurrent.futures, hashlib, html, io, json, os, re, subprocess, sys, time
from pathlib import Path
from collections import Counter
from PIL import Image, ImageDraw, ImageFont, ImageOps
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import collect as core
WP='https://en.wikipedia.org/w/api.php'
PREFIX='reference'

def dump(path,value):core.dump(path,value)
def read(path,default=None):return core.read(path,default)
def clean(s):return core.clean(s)

def resolve_pages(targets):
    mapped=[];missing=[]
    for start in range(0,len(targets),35):
        batch=targets[start:start+35]
        try:
            j=core.get(WP,{'action':'query','format':'json','formatversion':2,'titles':'|'.join(t['scientificName'] for t in batch),'redirects':1,'prop':'pageimages|info','piprop':'name','inprop':'url'})
            q=j.get('query',{});aliases={}
            for n in q.get('normalized',[])+q.get('redirects',[]):aliases[n['from']]=n['to']
            pages={p['title']:p for p in q.get('pages',[])}
            for t in batch:
                title=t['scientificName'];seen=set()
                while title in aliases and title not in seen:seen.add(title);title=aliases[title]
                p=pages.get(title,{})
                if p.get('pageimage') and not p.get('missing'):
                    mapped.append({'target':t,'wikipediaPage':{'title':p['title'],'pageId':p.get('pageid'),'url':p.get('fullurl'),'requestedScientificName':t['scientificName'],'resolvedTitle':title,'fileTitle':'File:'+p['pageimage']}})
                else:missing.append({'targetId':t['id'],'scientificName':t['scientificName'],'reason':'no_wikipedia_lead_image'})
        except Exception as e:missing.extend({'targetId':t['id'],'scientificName':t['scientificName'],'reason':str(e)} for t in batch)
    return mapped,missing

def add_file_info(mapped):
    prepared=[];rejections=[]
    for start in range(0,len(mapped),5):
        batch=mapped[start:start+5]
        try:
            j=core.get(core.COMMONS,{'action':'query','format':'json','formatversion':2,'titles':'|'.join(item['wikipediaPage']['fileTitle'] for item in batch),'redirects':1,'prop':'imageinfo','iiprop':'url|extmetadata|size|mime|sha1','iiurlwidth':2048})
            q=j.get('query',{});aliases={}
            for n in q.get('normalized',[])+q.get('redirects',[]):aliases[n['from']]=n['to']
            pages={p['title']:p for p in q.get('pages',[])}
            for item in batch:
                title=item['wikipediaPage']['fileTitle'];seen=set()
                while title in aliases and title not in seen:seen.add(title);title=aliases[title]
                page=pages.get(title,{})
                info=(page.get('imageinfo') or [{}])[0];m=info.get('extmetadata',{});val=lambda k:clean(m.get(k,{}).get('value',''))
                lu=val('LicenseUrl').replace('http:','https:');code=None
                if re.fullmatch(r'https://creativecommons\.org/(licenses/by(?:-sa)?/(?:[1-4]\.0|2\.5)(?:/[a-z-]+)?|publicdomain/zero/1\.0)/?',lu):code='cc0' if '/zero/' in lu else 'cc-by-sa' if '/by-sa/' in lu else 'cc-by'
                text=' '.join([title,val('ImageDescription'),val('Categories')]).lower()
                reason=None
                if not code:reason='license_not_on_commercial_reuse_whitelist'
                elif not val('Artist'):reason='author_missing'
                elif info.get('mime') not in ('image/jpeg','image/png','image/webp'):reason='not_supported_photo_mime'
                elif min(info.get('width',0),info.get('height',0))<500:reason='resolution_below_minimum'
                elif re.search(r'\b(drawing|illustration|painting|fossil|skeleton|taxidermy|mounted specimen|ai.generated|generative ai|watercolou?r|distribution map|lithograph|engraving)\b',text):reason='non_photographic_or_specimen_terms'
                if reason:
                    rejections.append({'targetId':item['target']['id'],'scientificName':item['target']['scientificName'],'fileTitle':title,'reason':reason});continue
                item.update({'page':page,'info':info,'licenseCode':code,'licenseUrl':lu,'author':val('Artist'),'imageTitle':val('ObjectName') or title,'originalAttribution':val('Attribution') or val('Credit')})
                prepared.append(item)
        except Exception as e:rejections.extend({'targetId':item['target']['id'],'reason':str(e)} for item in batch)
    return prepared,rejections

def collect_image(item):
    t=item['target'];info=item['info'];page=item['page'];pid='commons-'+str(page['pageid']);sid=core.slug(t['scientificName'])
    url=info.get('thumburl') or info.get('url');raw=core.get(url,binary=True)
    master,web,thumb,od,md,wd,q=core.prepare_photo(raw)
    base=f'{PREFIX}/images/{sid}/{pid}'
    paths={'master':base+'.jpg','web':base+'.webp','thumbnail':base+'-thumb.webp'}
    for k,b in [('master',master),('web',web),('thumbnail',thumb)]:
        p=ROOT/paths[k];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    rec={'schemaVersion':1,'assetId':pid,'targetId':t['id'],'scientificName':t['scientificName'],'nameJa':t.get('nameJa',''),'collectionTier':t.get('collectionTier','chronoearth'),'source':'Wikimedia Commons','sourceId':str(page['pageid']),'imageTitle':item['imageTitle'],'photoUrl':info['descriptionurl'],'downloadUrl':url,'originalUrl':info['url'],'licenseCode':item['licenseCode'],'licenseUrl':item['licenseUrl'],'author':item['author'],'originalAttribution':item['originalAttribution'],'retrievedAt':core.NOW(),'origin':'photo_candidate','status':'collected_pending_visual_review','visualReview':{'status':'pending','fullBodyVisible':'unverified','speciesIdentity':'source_taxonomy_only'},'rightsReview':{'status':'allowed_license_metadata_verified','verifiedAt':core.NOW(),'commercialReuseAllowedByLicense':True,'attributionRequired':item['licenseCode']!='cc0','shareAlikeRequiredForAdaptation':item['licenseCode']=='cc-by-sa','otherRights':'not_warranted'},'selectionBasis':'scientific_name_wikipedia_lead_image_commons_license_checked','taxonMatch':'scientific_name_page_or_redirect','wikipediaPage':item['wikipediaPage'],'files':paths,'dimensions':{'sourceDownload':od,'original':[info.get('width'),info.get('height')],'master':md,'web':wd},'bytes':{'master':len(master),'web':len(web),'thumbnail':len(thumb)},'sha256':{'download':hashlib.sha256(raw).hexdigest(),'master':hashlib.sha256(master).hexdigest(),'web':hashlib.sha256(web).hexdigest()},'changes':['EXIF orientation applied','proportional downsize only; no crop','JPEG/WebP re-encoding','embedded EXIF removed; provenance retained in metadata'],'webQuality':q,'imageInfoEvidence':info}
    rec['credit']=f"{rec['imageTitle']} [{rec['scientificName']}] — {rec['author']} / Wikimedia Commons, {rec['licenseCode'].upper()} ({rec['licenseUrl']}); source: {rec['photoUrl']}. Original attribution: {rec['originalAttribution']}. Resized and re-encoded; no subject alteration."
    dump(f'{PREFIX}/metadata/{sid}/{pid}.json',rec)
    return {'targetId':t['id'],'scientificName':t['scientificName'],'status':'collected','assetId':pid}

def rebuild(results,phase):
    records=[json.loads(p.read_text()) for p in sorted((ROOT/PREFIX/'metadata').glob('*/*.json'))]
    dump('reports/reference-status.json',{'generatedAt':core.NOW(),'phase':phase,'collectedTaxa':len({r['targetId'] for r in records}),'photoCount':len(records),'licenseCounts':dict(Counter(r['licenseCode'] for r in records)),'pendingVisualReview':sum(r['visualReview']['status']=='pending' for r in records),'totalStoredBytes':sum(sum(r['bytes'].values()) for r in records),'note':'Reference candidates are additional photographs, not additional species. No visual approval is inferred.'})
    dump(f'{PREFIX}/results.json',results);dump(f'{PREFIX}/catalog.json',{'records':[{k:v for k,v in r.items() if k!='imageInfoEvidence'} for r in records]})
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14);index=[]
    for offset in range(0,len(records),36):
        sheet=Image.new('RGB',(1800,1620),'white');d=ImageDraw.Draw(sheet)
        for n,r in enumerate(records[offset:offset+36]):
            x=n%6*300;y=n//6*270
            with Image.open(ROOT/r['files']['web']) as im:
                im=ImageOps.contain(im,(292,224));sheet.paste(im,(x+(300-im.width)//2,y))
            d.text((x+4,y+228),f"{offset+n+1:04d} {r['scientificName']}"[:36],font=font,fill='black');d.text((x+4,y+247),r['licenseCode']+' | '+r['sourceId'],font=font,fill='black')
            index.append({'number':offset+n+1,'assetId':r['assetId'],'targetId':r['targetId'],'scientificName':r['scientificName'],'sheet':f'reference-{offset//36+1:03d}.jpg','metadataPath':f'{PREFIX}/metadata/{core.slug(r["scientificName"])}/{r["assetId"]}.json'})
        sheet.save(ROOT/PREFIX/'gallery'/f'reference-{offset//36+1:03d}.jpg',quality=90)
    dump(f'{PREFIX}/gallery/sheet-index.json',index)
    print(f'{phase}: {len(records)} reference photographs',flush=True)

def checkpoint():
    if not os.getenv('GITHUB_ACTIONS'):return
    def run(*a):subprocess.run(a,cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    run('git','config','user.name','Collect Images bot');run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com');run('git','add',PREFIX,'reports/reference-status.json')
    if subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode:
        run('git','commit','-m','Save licensed reference photographs and review sheets [skip ci]')
        for n in range(6):
            try:run('git','pull','--rebase','origin','main');run('git','push','origin','HEAD:main');return
            except subprocess.CalledProcessError:
                if n==5:raise
                time.sleep(4*(n+1))

def main():
    for sub in ['images','metadata','gallery']:(ROOT/PREFIX/sub).mkdir(parents=True,exist_ok=True)
    targets=read('data/targets.json')['records'];base=[t for t in targets if t.get('collectionTier')=='chronoearth']
    done={json.loads(p.read_text())['targetId'] for p in (ROOT/PREFIX/'metadata').glob('*/*.json')}
    mapped,missing=resolve_pages([t for t in base if t['id'] not in done]);print(f'{len(mapped)} lead images resolved',flush=True)
    prepared,rejected=add_file_info(mapped);results=read(f'{PREFIX}/results.json',[])+missing+rejected
    rebuild(results,'reference_collecting')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(collect_image,i):i for i in prepared}
        for n,f in enumerate(concurrent.futures.as_completed(futures),1):
            item=futures[f]
            try:r=f.result()
            except Exception as e:r={'targetId':item['target']['id'],'scientificName':item['target']['scientificName'],'status':'missing','reason':str(e)}
            results.append(r)
            if n%40==0:rebuild(results,'reference_collecting');checkpoint()
    rebuild(results,'reference_collection_complete_visual_review_pending');checkpoint()

if __name__=='__main__':main()
