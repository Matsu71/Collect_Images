#!/usr/bin/env python3
"""Complete a bounded, evidenced search of every outstanding primary-image target.

Acquisition is never visual approval. Sources, rights evidence, original dimensions,
failed searches and exact saved JPEG hashes remain available for adjudication.
"""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, io, json, re, sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote
from PIL import Image, ImageDraw, ImageFont, ImageOps
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import collect as core
BATCH='batches/remaining-closure-20260914'
REVIEW='reviews/remaining-closure-20260914.json'
HINTS='data/remaining-closure-hints-20260914.json'
CC_RE=re.compile(r'https://creativecommons\.org/(licenses/by(?:-sa)?/(?:[1-4]\.0|2\.5)(?:/[a-z-]+)?|publicdomain/zero/1\.0)/?')
PD_URL='https://creativecommons.org/publicdomain/mark/1.0/'
PD_TEMPLATE_RE=re.compile(r'\{\{\s*(PD-USGov(?:-[A-Za-z0-9]+)*|PD-self|PD-author|PD-user(?:-[A-Za-z]+)?|PD-release)\s*(?:\||\}\})',re.I)
BAD_TITLE=re.compile(r'\b(diagram|protein|polymerase|phylogenetic|distribution map|spectrogram|lithograph|engraving|replica|skeleton|skull|3d model|painting|drawing|statue|molecular|structure of|gene expression|signaling pathway)\b',re.I)
WHOLE=re.compile(r'\b(habit|habitus|whole|full.body|standing|walking|tree|shrub|micrograph|microscopy|SEM|TEM|cell|cells)\b',re.I)
PART=re.compile(r'\b(flowers?|fruits?|leaves|leaf|bark|seeds?|portrait|heads?|buds?|pollen|feathers?|eggs?|colony|colonies|agar|symptoms)\b',re.I)

def load(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def save(p,obj):core.dump(p,obj)
def sha(b):return hashlib.sha256(b).hexdigest()
def normal(s):return re.sub(r'[^a-z0-9]+',' ',s.lower()).strip()

def existing_lookup():
    result={}
    for folder in ('metadata','reference/metadata'):
        for p in (ROOT/folder).glob('*/*.json'):
            r=json.loads(p.read_text());result[(r['targetId'],r['assetId'])]=str(p.relative_to(ROOT))
    return result

def image_rights(page,info):
    meta=info.get('extmetadata',{});val=lambda k:core.clean(meta.get(k,{}).get('value',''))
    original_url=val('LicenseUrl').replace('http:','https:')
    url=re.sub(r'/deed\.[A-Za-z_-]+/?$','/',original_url)
    author=val('Artist')
    if not author:return None,'author_not_provided'
    if CC_RE.fullmatch(url):
        code='cc0' if '/zero/' in url else 'cc-by-sa' if '/by-sa/' in url else 'cc-by'
        return {'licenseCode':code,'licenseUrl':url,'author':author,'originalLicenseUrl':original_url,'publicDomainBasis':None},None
    # Public-domain status is never inferred merely from the hosting institution.
    if 'public domain' not in val('LicenseShortName').lower() and val('License').lower() not in ('pd','public-domain'):
        return None,'not_an_allowed_reuse_license'
    data=core.get(core.COMMONS,{'action':'parse','format':'json','pageid':page['pageid'],'prop':'wikitext'})
    wikitext=data.get('parse',{}).get('wikitext',{}).get('*','')
    templates=sorted(set(m.group(1) for m in PD_TEMPLATE_RE.finditer(wikitext)))
    if not templates:return None,'public_domain_notice_without_accepted_basis'
    government=[t for t in templates if t.lower().startswith('pd-usgov')]
    if government:
        # A named agency/official source must corroborate the government-work template.
        if not re.search(r'\.gov\b|\.mil\b|\b(CDC|NIAID|NIH|NASA|USDA|USGS|NOAA|USFWS|Department of|U\.S\.)\b',val('Credit')+' '+author+' '+wikitext,re.I):
            return None,'government_work_basis_not_corrobated'
        basis_type='explicit_us_government_work_notice'
    else:
        if not re.search(r'\{\{\s*(own|self)\b|own work|copyright holder|release.{0,80}public domain|PD-author|PD-user',wikitext,re.I|re.S):
            return None,'public_domain_dedication_not_corrobated'
        basis_type='explicit_author_public_domain_dedication'
    basis={'metadataVerified':True,'basisType':basis_type,'templates':templates,'sourcePage':info['descriptionurl'],'sourceWikitext':wikitext,'checkedAt':core.NOW(),'jurisdictionNote':'Public-domain notice as supplied by the source; separate rights and jurisdiction-specific restrictions are not independently warranted.'}
    return {'licenseCode':'public-domain','licenseUrl':PD_URL,'author':author,'originalLicenseUrl':original_url,'publicDomainBasis':basis},None

def commons_records(target,params,route,existing,variants,lead_evidence=None):
    response=core.get(core.COMMONS,{'action':'query','format':'json','formatversion':2,'prop':'imageinfo','iiprop':'url|extmetadata|size|mime|sha1','iiurlwidth':1800,**params})
    pages=response.get('query',{}).get('pages',[]);records=[];rejections=Counter()
    for page in pages:
        info=(page.get('imageinfo') or [{}])[0];title=page.get('title','')
        if not info:continue
        meta=info.get('extmetadata',{});val=lambda k:core.clean(meta.get(k,{}).get('value',''))
        caption=val('ImageDescription');aid='commons-'+str(page['pageid']);w,h=info.get('width',0),info.get('height',0)
        if info.get('mime') not in ('image/jpeg','image/png','image/webp'):rejections['not_static_photo_format']+=1;continue
        if max(w,h)<260 or min(w,h)<150 or max(w,h)/max(1,min(w,h))>6:rejections['unusable_resolution_or_aspect']+=1;continue
        if BAD_TITLE.search(title):rejections['obvious_diagram_or_non_subject_title']+=1;continue
        match=[name for name in variants if normal(name) in normal(title+' '+caption)]
        if not match and not lead_evidence:rejections['no_target_identity_evidence']+=1;continue
        try:rights,reason=image_rights(page,info)
        except Exception as error:rejections['rights_lookup_error']+=1;continue
        if not rights:rejections[reason]+=1;continue
        score=12*bool(WHOLE.search(title))+4*bool(WHOLE.search(caption[:200]))-7*bool(PART.search(title))-2*bool(PART.search(caption[:140]))
        score+=min(4,min(w,h)/400)+8*bool(lead_evidence)+5*bool(re.search('Quality images|Featured pictures',val('Categories'),re.I))
        if min(w,h)<300:score-=6
        if (target['id'],aid) in existing:score-=10
        record={'target':target,'assetId':aid,'source':'Wikimedia Commons','sourceId':str(page['pageid']),'imageTitle':val('ObjectName') or title,'sourceTitle':title,'sourceCaption':caption,'photoUrl':info['descriptionurl'],'originalUrl':info['url'],'downloadUrl':info.get('thumburl') or info['url'],'originalAttribution':val('Attribution') or val('Credit'),'sourceImageInfo':info,'imageInfoEvidence':info,'sourceOriginalSha1':info.get('sha1'),'originalDimensions':[w,h],'identityEvidence':{'route':route,'matchedSearchNames':match,'leadPage':lead_evidence,'notIndependentlyReidentified':True},'existingMetadataPath':existing.get((target['id'],aid)),'selectionScore':score,'retrievedAt':core.NOW(),**rights}
        records.append(record)
    attempt={'route':route,'request':params,'pagesReturned':len(pages),'eligibleCandidates':len(records),'rejectionCounts':dict(rejections)}
    return records,attempt

def lead_photos(target,variants,existing):
    out=[];attempts=[]
    for name in variants[:3]:
        try:
            data=core.get('https://en.wikipedia.org/w/api.php',{'action':'query','format':'json','formatversion':2,'titles':name,'redirects':1,'prop':'pageimages|info','piprop':'name','inprop':'url'})
            pages=data.get('query',{}).get('pages',[])
            for page in pages:
                if not page.get('pageimage'):continue
                evidence={'requestedName':name,'resolvedTitle':page['title'],'sourcePage':page.get('fullurl'),'redirects':data.get('query',{}).get('redirects',[])}
                rows,attempt=commons_records(target,{'titles':'File:'+page['pageimage'],'redirects':1},'scientific_name_wikipedia_lead',existing,variants,evidence)
                out.extend(rows);attempts.append(attempt)
            attempts.append({'route':'wikipedia_scientific_name_lookup','requestedName':name,'resolvedPages':[p.get('title') for p in pages],'imagesReturned':sum(bool(p.get('pageimage')) for p in pages)})
        except Exception as e:attempts.append({'route':'wikipedia_scientific_name_lookup','requestedName':name,'error':str(e)})
    return out,attempts

def inat_photos(target,existing):
    taxon,match=core.inat_taxon(target)
    if not taxon or match!='exact_scientific_name' or taxon.get('extinct'):
        return [],{'route':'additional_inaturalist_observations','result':'no_exact_active_taxon'}
    data=core.get(core.API+'/observations',{'taxon_id':taxon['id'],'quality_grade':'research','photo_license':'cc0,cc-by,cc-by-sa','photos':'true','per_page':35,'page':3,'order_by':'votes','order':'desc'})
    rows=[]
    for obs in data.get('results',[]):
        ot=obs.get('taxon') or {}
        if ot.get('id')!=taxon['id'] and taxon['id'] not in ot.get('ancestor_ids',[]):continue
        for p in obs.get('photos',[])[:2]:
            code=p.get('license_code');aid='inat-'+str(p['id'])
            if code not in core.ALLOWED or p.get('flags') or (target['id'],aid) in existing:continue
            author=core.clean(p.get('attribution_name') or p.get('native_realname') or p.get('native_username'))
            attribution=core.clean(p.get('attribution'))
            if not author and attribution.startswith('(c)'):author=re.sub(r'^\(c\)\s*|,?\s*some rights reserved.*$','',attribution,flags=re.I).strip()
            if not author and code=='cc0':author='unknown'
            if not author:continue
            url=p.get('original_url') or re.sub(r'/(square|small|medium|large)\.', '/original.',p.get('url',''))
            if not url.startswith(('https://inaturalist-open-data.s3.amazonaws.com/','https://static.inaturalist.org/','https://static.inaturalist.ca/')):continue
            rows.append({'target':target,'assetId':aid,'source':'iNaturalist','sourceId':str(p['id']),'imageTitle':target['scientificName'],'sourceTitle':target['scientificName'],'sourceCaption':target['scientificName']+'; '+core.clean(obs.get('description')),'photoUrl':f"https://www.inaturalist.org/photos/{p['id']}",'originalUrl':url,'downloadUrl':url,'licenseCode':code,'licenseUrl':core.ALLOWED[code],'author':author,'originalAttribution':attribution,'photoApiEvidence':p,'observationUrl':f"https://www.inaturalist.org/observations/{obs['id']}",'observationTaxon':ot,'originalDimensions':[p.get('original_dimensions',{}).get('width'),p.get('original_dimensions',{}).get('height')],'selectionScore':min(12,obs.get('faves_count',0)/3),'existingMetadataPath':None,'identityEvidence':{'route':'research_grade_exact_taxon','taxonId':taxon['id'],'notIndependentlyReidentified':True},'retrievedAt':core.NOW()})
    return rows,{'route':'additional_inaturalist_observations','taxonId':taxon['id'],'observationsReturned':len(data.get('results',[])),'eligibleCandidates':len(rows)}

def acquire_target(target,existing,hints):
    variants=list(dict.fromkeys([target['scientificName']]+hints.get('searchVariants',{}).get(target['scientificName'],[])))
    records,attempts=lead_photos(target,variants,existing)
    exact=hints.get('exactFiles',{}).get(target['scientificName'],[])
    if exact:
        try:
            rows,attempt=commons_records(target,{'titles':'|'.join(exact),'redirects':1},'explicit_source_file_leads',existing,variants,{'exactSourceLeads':exact});records.extend(rows);attempts.append(attempt)
        except Exception as e:attempts.append({'route':'explicit_source_file_leads','error':str(e)})
    for name in variants:
        for term in ('','micrograph' if len(variants)==1 and target.get('sourceType') not in ('plant','animal') else 'habit'):
            params={'generator':'search','gsrsearch':'"'+name+'" '+term+' filetype:bitmap -protein -diagram -map','gsrnamespace':6,'gsrlimit':30}
            try:rows,attempt=commons_records(target,params,'commons_named_search',existing,variants);records.extend(rows);attempts.append(attempt)
            except Exception as e:attempts.append({'route':'commons_named_search','query':params['gsrsearch'],'error':str(e)})
    try:rows,attempt=inat_photos(target,existing);records.extend(rows);attempts.append(attempt)
    except Exception as e:attempts.append({'route':'additional_inaturalist_observations','error':str(e)})
    unique={}
    for r in records:
        if r['assetId'] not in unique or r['selectionScore']>unique[r['assetId']]['selectionScore']:unique[r['assetId']]=r
    ordered=sorted(unique.values(),key=lambda r:r['selectionScore'],reverse=True)
    new=[r for r in ordered if not r.get('existingMetadataPath')];old=[r for r in ordered if r.get('existingMetadataPath')]
    # At most one already-stored image may receive higher-resolution reconsideration.
    queue=new[:3]+old[:1]+new[3:];saved=[];hashes=set();errors=[]
    for r in queue[:14]:
        if len(saved)>=4:break
        try:
            raw=core.get(r['downloadUrl'],binary=True)
            with Image.open(io.BytesIO(raw)) as source:
                if getattr(source,'n_frames',1)>1:raise ValueError('animated_source_not_used_as_static_photo')
                source.load();im=ImageOps.exif_transpose(source).convert('RGB')
            w,h=im.size
            if max(w,h)<260 or min(w,h)<150:raise ValueError('insufficient_original_resolution')
            im.thumbnail((1800,1800),Image.Resampling.LANCZOS);buffer=io.BytesIO();im.save(buffer,'JPEG',quality=93,optimize=True);body=buffer.getvalue()
            if sha(body) in hashes:continue
            hashes.add(sha(body));path=f"{BATCH}/previews/{core.slug(target['scientificName'])}--{r['assetId']}.jpg"
            (ROOT/path).parent.mkdir(parents=True,exist_ok=True);(ROOT/path).write_bytes(body)
            r.update({'previewPath':path,'previewSha256':sha(body),'downloadedSourceSha256':sha(raw),'previewDimensions':list(im.size),'lowResolutionOriginal':min(im.size)<500,'status':'candidate_pending_actual_visual_review'})
            saved.append(r)
        except Exception as e:errors.append({'assetId':r['assetId'],'error':str(e)})
    return saved,{'targetId':target['id'],'scientificName':target['scientificName'],'searchVariants':variants,'attempts':attempts,'eligibleUniqueCandidates':len(unique),'savedPreviewCount':len(saved),'downloadErrors':errors}

def gather():
    if (ROOT/BATCH/'candidates.json').exists():raise ValueError('This immutable candidate snapshot already exists')
    hints=load(HINTS);targets={t['id']:t for t in load('data/targets.json')['records']};gaps=load('reports/primary-gaps.json')
    save(BATCH+'/baseline.json',load('reports/curation-status.json'));save(BATCH+'/original-gaps.json',gaps)
    selected=[targets[t['id']] for t in gaps];selected.sort(key=lambda t:(t.get('collectionTier')!='chronoearth',t['scientificName']))
    existing=existing_lookup();records=[];searches=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(acquire_target,t,existing,hints):t for t in selected}
        for n,f in enumerate(concurrent.futures.as_completed(futures),1):
            t=futures[f]
            try:rows,report=f.result();records.extend(rows);searches.append(report)
            except Exception as e:searches.append({'targetId':t['id'],'scientificName':t['scientificName'],'fatalError':str(e)})
            if n%10==0:print(json.dumps({'processed':n,'remainingTargetCount':len(selected),'savedPreviews':len(records)}),flush=True)
    rank={t['id']:n for n,t in enumerate(selected)};records.sort(key=lambda r:(rank[r['target']['id']],-r['selectionScore'],r['assetId']))
    for n,r in enumerate(records,1):r['number']=n
    save(BATCH+'/candidates.json',{'schemaVersion':1,'generatedAt':core.NOW(),'records':records});save(BATCH+'/search-evidence.json',sorted(searches,key=lambda r:rank[r['targetId']]))
    folder=ROOT/BATCH/'sheets';folder.mkdir(parents=True,exist_ok=True);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',16)
    for offset in range(0,len(records),16):
        sheet=Image.new('RGB',(1920,1760),'white');draw=ImageDraw.Draw(sheet)
        for n,r in enumerate(records[offset:offset+16]):
            x=n%4*480;y=n//4*440
            with Image.open(ROOT/r['previewPath']) as im:
                # No upscaling of low-resolution microscopy is hidden in review sheets.
                im.thumbnail((466,360),Image.Resampling.LANCZOS);sheet.paste(im,(x+(480-im.width)//2,y+(360-im.height)//2))
            draw.text((x+6,y+368),f"{r['number']:03d} {r['target']['scientificName']}"[:52],font=font,fill='black')
            draw.text((x+6,y+393),r['assetId']+' '+r['licenseCode'],font=font,fill='black')
            draw.text((x+6,y+417),str(r['previewDimensions'])+(' EXISTING' if r.get('existingMetadataPath') else ''),font=font,fill='black')
        sheet.save(folder/f'closure-{offset//16+1:03d}.jpg',quality=93)
    status={'generatedAt':core.NOW(),'targetCount':len(selected),'targetsAttempted':len(searches),'candidateImages':len(records),'candidateTaxa':len({r['target']['id'] for r in records}),'licenseCounts':dict(Counter(r['licenseCode'] for r in records)),'candidateManifestSha256':sha((ROOT/BATCH/'candidates.json').read_bytes()),'visualReview':'pending','notFoundConclusion':'No conclusion before individual source and image adjudication.'}
    save(BATCH+'/status.json',status);print(json.dumps(status),flush=True)

def decisions():
    spec=load(REVIEW);raw=(ROOT/BATCH/'candidates.json').read_bytes()
    if sha(raw)!=spec['candidateManifestSha256']:raise ValueError('Review candidate hash mismatch')
    records={r['number']:r for r in json.loads(raw)['records']};roles={}
    for role,key in [('primary','primaryNumbers'),('supplementary','supplementaryNumbers'),('exclude','excludeNumbers')]:
        for n in spec.get(key,[]):
            if n not in records or n in roles:raise ValueError('Unknown or duplicate decision')
            roles[n]=role
    if set(roles)!=set(records) or len(roles)!=spec['reviewedCount']:raise ValueError('Every saved candidate must be adjudicated exactly once')
    return spec,records,roles

def adopt():
    spec,records,roles=decisions();saved=[];errors=[]
    for n,r in records.items():
        if roles[n]=='exclude':continue
        t=r['target']
        try:
            body=(ROOT/r['previewPath']).read_bytes()
            if sha(body)!=r['previewSha256']:raise ValueError('Reviewed bytes changed')
            if r.get('existingMetadataPath'):
                metadata=load(r['existingMetadataPath'])
                # Only a proven common original image may reuse older master bytes.
                oldinfo=metadata.get('imageInfoEvidence',{})
                if r['source']=='Wikimedia Commons' and oldinfo.get('sha1')!=r.get('sourceOriginalSha1'):raise ValueError('Existing asset has different source version')
                saved.append({'number':n,'targetId':t['id'],'assetId':r['assetId'],'metadataPath':r['existingMetadataPath'],'recommendedRole':roles[n],'newImage':False,'masterSha256':metadata['sha256']['master']});continue
            base=f"reference/images/{core.slug(t['scientificName'])}/{r['assetId']}";paths={'master':base+'.jpg','web':base+'.webp','thumbnail':base+'-thumb.webp'}
            meta=f"reference/metadata/{core.slug(t['scientificName'])}/{r['assetId']}.json"
            if (ROOT/meta).exists():
                existing=load(meta)
                if existing.get('acquisitionBatch')!=BATCH or existing['sha256']['master']!=sha(body):raise ValueError('Refusing to overwrite unrelated earlier photograph')
                saved.append({'number':n,'targetId':t['id'],'assetId':r['assetId'],'metadataPath':meta,'recommendedRole':roles[n],'newImage':True,'masterSha256':existing['sha256']['master']});continue
            with Image.open(io.BytesIO(body)) as source:source.load();im=source.convert('RGB')
            web=im.copy();web.thumbnail((1400,1400),Image.Resampling.LANCZOS);wb=io.BytesIO();quality=85
            while True:
                wb.seek(0);wb.truncate();web.save(wb,'WEBP',quality=quality,method=5)
                if wb.tell()<=190000 or quality<=68:break
                quality-=3
            thumb=im.copy();thumb.thumbnail((360,280),Image.Resampling.LANCZOS);tb=io.BytesIO();thumb.save(tb,'WEBP',quality=78,method=4)
            payload={'master':body,'web':wb.getvalue(),'thumbnail':tb.getvalue()}
            for key,value in payload.items():
                p=ROOT/paths[key];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value)
            rec={key:value for key,value in r.items() if key not in ('target','number','selectionScore','status')}
            rec.update({'schemaVersion':1,'targetId':t['id'],'scientificName':t['scientificName'],'nameJa':t.get('nameJa',''),'collectionTier':t.get('collectionTier'),'files':paths,'dimensions':{'master':list(im.size),'web':list(web.size)},'bytes':{key:len(value) for key,value in payload.items()},'sha256':{key:sha(value) for key,value in payload.items()},'status':'collected_pending_visual_review','origin':'photo_candidate','acquisitionBatch':BATCH,'visualReview':{'status':'pending'},'rightsReview':{'status':'per_image_reuse_basis_verified_at_acquisition','verifiedAt':r['retrievedAt'],'commercialReuseAllowedBySource':True,'attributionRequired':r['licenseCode'] in ('cc-by','cc-by-sa'),'shareAlikeRequiredForAdaptation':r['licenseCode']=='cc-by-sa','otherRights':'not_warranted'},'changes':['Master is the exact visually reviewed JPEG derivative; not the original source file','Proportional resizing/re-encoding only; no upscaling, no crop, no generative alteration'],'webQuality':quality})
            rec['credit']=f"{rec['imageTitle']} [{rec['scientificName']}] — {rec['author']} / {rec['source']}; {rec['licenseCode']} ({rec['licenseUrl']}); source: {rec['photoUrl']}. Proportionally resized and re-encoded; see image-specific source changes and rights evidence."
            save(meta,rec);saved.append({'number':n,'targetId':t['id'],'assetId':r['assetId'],'metadataPath':meta,'recommendedRole':roles[n],'newImage':True,'masterSha256':sha(body)})
        except Exception as e:errors.append({'number':n,'error':str(e)})
    report={'generatedAt':core.NOW(),'reviewFile':REVIEW,'saved':saved,'newImageCount':sum(r['newImage'] for r in saved),'existingImagesReconsidered':sum(not r['newImage'] for r in saved),'roleCounts':dict(Counter(roles.values())),'failures':errors}
    save(BATCH+'/adoption.json',report);print(json.dumps({k:v for k,v in report.items() if k!='saved'}))
    if errors:raise RuntimeError('Preserved partial progress; selected images require recovery')

def verify_public_domain(rec):
    if rec.get('licenseCode')!='public-domain':return False
    basis=rec.get('publicDomainBasis') or {}
    if rec.get('licenseUrl')!=PD_URL or not basis.get('metadataVerified') or not basis.get('templates'):
        raise ValueError('Public domain lacks an explicit per-image basis')
    if basis.get('sourcePage')!=rec.get('photoUrl') or not basis.get('sourceWikitext'):raise ValueError('Public-domain provenance is incomplete')
    if basis.get('basisType') not in ('explicit_us_government_work_notice','explicit_author_public_domain_dedication'):raise ValueError('Unsupported public-domain basis')
    if not rec.get('author'):raise ValueError('Source credit missing')
    for key in ('master','web'):
        raw=(ROOT/rec['files'][key]).read_bytes()
        if sha(raw)!=rec['sha256'][key]:raise ValueError('Image hash mismatch')
        with Image.open(io.BytesIO(raw)) as im:im.verify()
    return True

def apply_decisions(result,evidence):
    if not (ROOT/REVIEW).exists() or not (ROOT/BATCH/'adoption.json').exists():return
    spec,records,roles=decisions();applied=0
    for row in load(BATCH+'/adoption.json')['saved']:
        n=row['number'];r=records[n];meta=load(row['metadataPath'])
        if meta['sha256']['master']!=row['masterSha256']:raise ValueError('Final adjudication and saved bytes differ')
        result[row['targetId']+'|'+row['assetId']]={'status':'screened','recommendedRole':roles[n],'reviewer':spec['reviewer'],'reviewedAt':spec['reviewedAt'],'method':spec['method'],'reviewFile':REVIEW,'candidateNumber':n,'previewSha256':r['previewSha256'],'masterSha256':row['masterSha256'],'candidateManifestSha256':spec['candidateManifestSha256'],'noteJa':spec.get('notesJa',{}).get(str(n),'主要な姿を目視確認。' if roles[n]=='primary' else '部分・別角度等の補足用。'),'speciesIdentity':'source_taxon_evidence_checked_not_independent_expert_reidentification','fullResolutionInspection':'contact_sheet_screening_unless_individual_review_note_states_otherwise'};applied+=1
    evidence.append({'file':REVIEW,'count':len(roles),'appliedPhotoPairs':applied,'excludedCandidates':sum(v=='exclude' for v in roles.values()),'kind':'all_remaining_targets_final_source_search_and_visual_adjudication'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('gather','adopt'));args=p.parse_args();{'gather':gather,'adopt':adopt}[args.mode]()
