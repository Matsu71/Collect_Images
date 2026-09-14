#!/usr/bin/env python3
"""Build the reviewed collection. Raw downloads never become approved by default."""
from __future__ import annotations
import csv, hashlib, html, io, json, re, sys, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'collection'
ALLOWED={'cc0','cc-by','cc-by-sa'}
NOW=lambda:datetime.now(timezone.utc).isoformat(timespec='seconds')

def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,obj):
    p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def text(s):return ' '.join(html.unescape(re.sub('<[^>]+>',' ',str(s or ''))).split())
def key(r):return r['targetId']+'|'+r['assetId']
def scientific_slug(s):return re.sub('[^a-z0-9]+','-',s.lower()).strip('-')

def fetch_index(commit,path):
    if not re.fullmatch('[0-9a-f]{40}',commit) or path not in ('gallery/sheet-index.json','reference/gallery/sheet-index.json'):
        raise ValueError('invalid_pinned_review_reference')
    url=f'https://raw.githubusercontent.com/Matsu71/Collect_Images/{commit}/{path}'
    error=None
    for attempt in range(4):
        try:
            r=requests.get(url,headers={'User-Agent':'CollectImages/1.0 (https://github.com/Matsu71/Collect_Images)'},timeout=60);r.raise_for_status();return r.json()
        except Exception as e:error=e;time.sleep(2**attempt)
    raise RuntimeError(f'Could not load pinned review index: {url}: {error}')

def read_reviews():
    decision={};evidence=[]
    for file in sorted((ROOT/'reviews').glob('screening-*.json')):
        spec=load(file);idx=fetch_index(spec['snapshotCommit'],spec['snapshotIndexPath']);numbered={r['number']:r for r in idx}
        groups={'primary':set(spec.get('primaryNumbers',[])),'supplementary':set(spec.get('supplementaryNumbers',[])),'exclude':set(spec.get('excludeNumbers',[]))}
        claimed=set()
        for role,numbers in groups.items():
            if claimed&numbers:raise ValueError(f'duplicate_review_numbers: {file.name}')
            claimed|=numbers
        if len(claimed)!=spec['reviewedCount'] or not claimed<=set(numbered):raise ValueError(f'invalid_review_count: {file.name}')
        for role,numbers in groups.items():
            for n in numbers:
                item=numbered[n]
                decision[key(item)]={'status':'screened','recommendedRole':role,'reviewer':spec['reviewer'],'reviewedAt':spec['reviewedAt'],'method':spec['method'],'snapshotCommit':spec['snapshotCommit'],'snapshotIndexPath':spec['snapshotIndexPath'],'snapshotNumber':n,'reviewFile':str(file.relative_to(ROOT)),'noteJa':spec.get('notesJa',{}).get(str(n),'主体と主要な形が一覧上で明瞭。' if role=='primary' else '部分・生態・環境等の補足用。' if role=='supplementary' else '姿の見やすさ、または実写の条件により除外。'),'speciesIdentity':'source_taxonomy_only_not_independently_reidentified','fullResolutionInspection':'not_performed'}
        evidence.append({'file':str(file.relative_to(ROOT)),'count':len(claimed),'snapshotCommit':spec['snapshotCommit']})
    return decision,evidence

def infer_context(rec):
    m=(rec.get('imageInfoEvidence') or {}).get('extmetadata',{})
    desc=' '.join(text(m.get(k,{}).get('value','')) for k in ['ImageDescription','Categories','ObjectName']).lower()
    flags=[]
    if re.search(r'\b(dead specimen|dead animal|preserved specimen|taxidermy|pinned specimen|mounted specimen|dried specimen|museum specimen)\b',desc):flags.append('specimen_or_dead_subject_explicit_in_source')
    if re.search(r'\b(electron micrograph|electron microscopy|fluorescen\w*|confocal|micrograph)\b',desc):flags.append('microscopy_or_fluorescence')
    if re.search(r'\b(drawing|illustration|painting|lithograph|engraving|sculpture|plastic model|3d.model|ai.generated|generative ai)\b',desc):flags.append('non_photo_terms_require_review')
    return flags

def verify_record(rec):
    if rec['licenseCode'] not in ALLOWED:raise ValueError('unapproved_license')
    if not rec.get('author') or not rec.get('photoUrl') or not rec.get('licenseUrl'):raise ValueError('missing_attribution')
    if not re.fullmatch(r'https://creativecommons\.org/(licenses/by(?:-sa)?/(?:[1-4]\.0|2\.5)(?:/[a-z-]+)?|publicdomain/zero/1\.0)/?',rec['licenseUrl']):raise ValueError('unapproved_license_url')
    for kind in ('master','web'):
        p=ROOT/rec['files'][kind]
        if not p.is_file():raise ValueError(f'missing_file:{p}')
        b=p.read_bytes()
        if hashlib.sha256(b).hexdigest()!=rec['sha256'][kind]:raise ValueError(f'hash_mismatch:{p}')
        with Image.open(io.BytesIO(b)) as im:im.verify()

def make_sheets(records):
    folder=OUT/'review-sheets';folder.mkdir(parents=True,exist_ok=True)
    for old in folder.glob('primary-*.jpg'):old.unlink()
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14);index=[]
    for offset in range(0,len(records),36):
        sheet=Image.new('RGB',(1800,1620),'white');draw=ImageDraw.Draw(sheet)
        for n,r in enumerate(records[offset:offset+36]):
            x=n%6*300;y=n//6*270
            with Image.open(ROOT/r['files']['web']) as im:
                im=ImageOps.contain(im,(292,224));sheet.paste(im,(x+(300-im.width)//2,y))
            draw.text((x+4,y+228),f"{offset+n+1:04d} {r['scientificName']}"[:36],font=font,fill='black')
            draw.text((x+4,y+247),r['licenseName'][:33],font=font,fill='black')
            index.append({'number':offset+n+1,'assetId':r['assetId'],'targetId':r['targetId'],'scientificName':r['scientificName'],'sheet':f'primary-{offset//36+1:03d}.jpg'})
        sheet.save(folder/f'primary-{offset//36+1:03d}.jpg',quality=91)
    save('collection/review-sheets/index.json',index)

def main():
    OUT.mkdir(exist_ok=True);(OUT/'metadata').mkdir(exist_ok=True)
    reviews,evidence=read_reviews();targets=load(ROOT/'data/targets.json')['records'];targetmap={t['id']:t for t in targets}
    raw=[];invalid=[]
    for folder in ['metadata','reference/metadata']:
        for p in sorted((ROOT/folder).glob('*/*.json')):
            rec=load(p)
            try:verify_record(rec)
            except Exception as e:invalid.append({'path':str(p.relative_to(ROOT)),'error':str(e)});continue
            rec['rawMetadataPath']=str(p.relative_to(ROOT));rec['collectionSource']='reference' if folder.startswith('reference') else 'base';raw.append(rec)
    if invalid:
        save('reports/curation-validation-errors.json',invalid)
        raise RuntimeError(f'{len(invalid)} invalid image/metadata records; collection was not published')
    # Same photograph for the same target may have been found independently by both collectors.
    by_key=defaultdict(list)
    for r in raw:by_key[key(r)].append(r)
    records=[];duplicate_copies=[]
    for k,copies in by_key.items():
        copies.sort(key=lambda r:(r['collectionSource']!='reference',-r['dimensions']['master'][0]*r['dimensions']['master'][1]))
        r=copies[0];r['alternateStoredCopies']=[{'rawMetadataPath':v['rawMetadataPath'],'files':v['files']} for v in copies[1:]]
        if len(copies)>1:duplicate_copies.append({'key':k,'canonical':r['rawMetadataPath'],'otherCopies':[v['rawMetadataPath'] for v in copies[1:]]})
        t=targetmap.get(r['targetId'],{})
        name=r.get('nameJa','')
        if name and not re.search(r'[\u3040-\u30ff\u3400-\u9fff]',name):r['commonNameSource']=name;r['nameJa']=''
        r['sourceTaxonType']=t.get('sourceType');r['visualReview']=reviews.get(k,{'status':'pending','recommendedRole':'pending','speciesIdentity':'source_taxonomy_only_not_independently_reidentified'})
        flags=infer_context(r);r['contextFlags']=flags
        role=r['visualReview']['recommendedRole']
        if role=='primary' and 'specimen_or_dead_subject_explicit_in_source' in flags:
            r['visualReview']['originalRecommendedRole']='primary';r['visualReview']['recommendedRole']='supplementary';r['visualReview']['contextOverride']='Source explicitly labels a specimen/dead subject; preserved as supplementary.';role='supplementary'
        if role=='primary' and 'non_photo_terms_require_review' in flags:
            r['visualReview']['originalRecommendedRole']='primary';r['visualReview']['recommendedRole']='pending';r['visualReview']['contextOverride']='Non-photographic terms in source require individual verification before primary use.';role='pending'
        r['origin']='photograph_visual_screened' if role in ('primary','supplementary') else 'rejected_asset' if role=='exclude' else 'unverified_photo_candidate'
        r['status']='primary_candidate' if role=='primary' else 'supplementary_only' if role=='supplementary' else 'excluded' if role=='exclude' else 'pending_review'
        ver=re.search(r'/([1-4]\.\d)(?:/[a-z-]+)?/?$',r['licenseUrl'])
        r['licenseName']=('CC0 '+(ver.group(1) if ver else '1.0')) if r['licenseCode']=='cc0' else r['licenseCode'].upper().replace('CC-','CC ')+' '+(ver.group(1) if ver else '')
        r['credit']=f"{r.get('imageTitle',r['scientificName'])} [{r['scientificName']}] — {r['author']} / {r['source']}, {r['licenseName']} ({r['licenseUrl']}); source: {r['photoUrl']}. Original attribution: {r.get('originalAttribution','')}. Resized and re-encoded; no subject alteration."
        r['metadataPath']='collection/metadata/'+scientific_slug(r['scientificName'])+'--'+r['assetId']+'.json'
        save(r['metadataPath'],r);records.append(r)
    records.sort(key=lambda r:(r['scientificName'].lower(),r['assetId']))
    groups=defaultdict(list)
    for r in records:groups[r['targetId']].append(r)
    taxa=[];selected=[]
    for target in targets:
        matches=groups.get(target['id'],[]);primaries=[r for r in matches if r['status']=='primary_candidate']
        primaries.sort(key=lambda r:({'cc0':0,'cc-by':1,'cc-by-sa':2}[r['licenseCode']],r['collectionSource']!='reference',-min(r['dimensions']['master'])))
        pick=primaries[0] if primaries else None
        if pick:selected.append(pick)
        nm=target.get('nameJa','');common=None
        if nm and not re.search(r'[\u3040-\u30ff\u3400-\u9fff]',nm):common=nm;nm=''
        taxa.append({'id':target['id'],'scientificName':target['scientificName'],'nameJa':nm,'commonNameSource':common,'collectionTier':target.get('collectionTier'),'chronoearthEventId':target.get('chronoearthEventId'),'primaryPhoto':{'assetId':pick['assetId'],'web':pick['files']['web'],'master':pick['files']['master'],'metadata':pick['metadataPath'],'license':pick['licenseName'],'credit':pick['credit']} if pick else None,'primaryAlternatives':[r['metadataPath'] for r in primaries[1:]],'supplementaryPhotos':[r['metadataPath'] for r in matches if r['status']=='supplementary_only'],'pendingPhotos':[r['metadataPath'] for r in matches if r['status']=='pending_review'],'excludedPhotos':[r['metadataPath'] for r in matches if r['status']=='excluded']})
    selected.sort(key=lambda r:r['scientificName'].lower())
    rawless=lambda r:{k:v for k,v in r.items() if k not in ('photoApiEvidence','observationTaxon','imageInfoEvidence')}
    accepted=[r for r in records if r['status'] in ('primary_candidate','supplementary_only')]
    pending=[r for r in records if r['status']=='pending_review'];excluded=[r for r in records if r['status']=='excluded']
    save('collection/assets.json',{'schemaVersion':1,'generatedAt':NOW(),'records':[rawless(r) for r in accepted]})
    save('collection/primary.json',{'schemaVersion':1,'generatedAt':NOW(),'records':[rawless(r) for r in selected]})
    save('collection/taxa.json',{'schemaVersion':1,'generatedAt':NOW(),'records':taxa})
    save('collection/pending.json',{'records':[rawless(r) for r in pending]});save('collection/excluded.json',{'records':[rawless(r) for r in excluded]})
    save('reports/duplicate-photo-copies.json',duplicate_copies)
    with (OUT/'credits.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['scientificName','nameJa','assetId','status','author','source','photoUrl','licenseName','licenseUrl','credit'];writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(accepted)
    (OUT/'ATTRIBUTION.md').write_text('# Photograph attribution\n\nEach photo retains the license below. Microscopy, specimens, juvenile forms and partial views are distinguished by metadata/review notes.\n\n'+'\n\n'.join(r['credit'] for r in accepted)+'\n',encoding='utf-8')
    selected_keys={key(r) for r in selected};cards=[]
    for r in accepted:
        esc=lambda v:html.escape(str(v or ''),quote=True);role='primary' if key(r) in selected_keys else 'alternative' if r['status']=='primary_candidate' else 'supplementary'
        label={'primary':'主画像候補','alternative':'主画像の別候補','supplementary':'補足画像'}[role]
        cards.append(f'<article data-role="{role}"><a href="../{esc(r["files"]["master"])}"><img loading="lazy" src="../{esc(r["files"]["thumbnail"])}" alt="{esc(r["scientificName"])}"></a><h2>{esc(r.get("nameJa"))}<br><i>{esc(r["scientificName"])}</i></h2><p class="badge">{label} · {esc(r["licenseName"])}</p><p>{esc(r["visualReview"].get("noteJa"))}</p><p>{esc(r["author"])} / <a href="{esc(r["photoUrl"])}">{esc(r["source"])}</a> · <a href="{esc(r["licenseUrl"])}">ライセンス</a></p><small>縮小・再圧縮。<a href="../{esc(r["metadataPath"])}">出典・クレジット・審査記録</a></small></article>')
    page='<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>現生生物の実写画像コレクション</title><style>body{font:15px system-ui;margin:24px;background:#f5f6f8;color:#17202b}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(285px,1fr));gap:18px}article{background:white;padding:14px;border:1px solid #d9dde4;border-radius:10px}article[hidden]{display:none}img{width:100%;height:220px;object-fit:contain}h2{font-size:17px;min-height:42px}p,small{font-size:12px;line-height:1.5}i{font-weight:400}input,select{font:inherit;padding:10px;margin:8px 8px 18px 0}input{width:min(550px,85%)}.badge{font-weight:650}header{max-width:1000px}</style><header><h1>現生生物の実写画像コレクション</h1><p>姿の見やすさを一覧で確認した主画像候補を初期表示します。補足画像・別候補に切り替えられます。未確認画像と除外画像は表示しません。</p><p>各写真の作者・出典・ライセンス・加工情報を保持して再利用してください。CC BY-SA は写真の改変・配布時の条件があります。構図の確認は、専門的な種同定や権利帰属の独立保証ではありません。</p><input id="q" placeholder="和名・学名・作者で検索"><select id="role"><option value="primary">主画像候補（1分類群1枚）</option><option value="alternative">主画像の別候補</option><option value="supplementary">補足画像</option><option value="all">審査済み候補すべて</option></select><p id="count"></p></header><main>'+''.join(cards)+'</main><script>function filter(){const q=document.getElementById("q").value.toLowerCase(),role=document.getElementById("role").value;let n=0;document.querySelectorAll("article").forEach(e=>{e.hidden=!((role==="all"||e.dataset.role===role)&&e.textContent.toLowerCase().includes(q));if(!e.hidden)n++});document.getElementById("count").textContent=n+"枚を表示"}document.getElementById("q").addEventListener("input",filter);document.getElementById("role").addEventListener("change",filter);filter();</script></html>'
    (OUT/'index.html').write_text(page,encoding='utf-8');make_sheets(selected)
    c=Counter(r['status'] for r in records);base_ids={t['id'] for t in targets if t.get('collectionTier')=='chronoearth'}
    distinct=lambda rs:len({(r['source'],r['sourceId']) for r in rs})
    status={'generatedAt':NOW(),'targetCount':len(targets),'chronoearthTargetCount':len(base_ids),'downloadedTargetCoverage':len(groups),'chronoearthDownloadedCoverage':len(set(groups)&base_ids),'rawStoredMetadataRecords':len(raw),'uniqueTaxonPhotoPairs':len(records),'uniqueDownloadedImageAssets':distinct(records),'duplicateStoredCopies':len(raw)-len(records),'visuallyScreenedTaxonPhotoPairs':len(records)-len(pending),'acceptedPhotographs':distinct(accepted),'acceptedTaxonCoverage':len({r['targetId'] for r in accepted}),'primaryCandidatePhotoPairs':c['primary_candidate'],'primaryReadyTaxa':len(selected),'chronoearthPrimaryReadyTaxa':len({r['targetId'] for r in selected}&base_ids),'supplementaryPhotoPairs':c['supplementary_only'],'excludedPhotoPairs':len(excluded),'pendingReviewPhotoPairs':len(pending),'acceptedLicenseCounts':dict(Counter(r['licenseName'] for r in accepted)),'selectedPrimaryLicenseCounts':dict(Counter(r['licenseName'] for r in selected)),'imageFileHashAndDecodeValidation':'pass','attributionAndLicenseUrlValidation':'pass','reviewEvidence':evidence,'limitations':'Primary means composition-screened candidate, not expert re-identification, full-resolution audit, or a warranty of all possible third-party rights. Separate variants, life stages and microscopy are documented.'}
    save('reports/curation-status.json',status)
    save('reports/primary-gaps.json',[t for t in taxa if t['primaryPhoto'] is None])
    print(json.dumps(status,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
