#!/usr/bin/env python3
"""Second-pass source investigation for every target still lacking a main photograph.

Explicit agency credits in a source caption may supply an otherwise blank Artist
field. They are retained as evidence, never invented or inferred from the host.
"""
from __future__ import annotations
import argparse,copy,hashlib,io,json,re,sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from contextlib import contextmanager
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import collect as core
import remaining_closure as base
BATCH='batches/remaining-targeted-20260914'
REVIEW='reviews/remaining-targeted-20260914.json'
EXACT={
 'Mycobacterium tuberculosis':['File:Mycobacterium tuberculosis.jpg'],
 'Salmonella enterica':['File:SalmonellaNIAID.jpg','File:Salmonella typhimurium.png'],
 'Vibrio cholerae':['File:Vibrio cholerae.jpg'],
 'Yersinia pestis':['File:Yersinia pestis.jpg','File:Yersinia pestis Bacteria.jpg','File:Yersinia pestis wayson.jpg'],
 'Thermus aquaticus':['File:Thermus aquaticus.JPG','File:Thermus aquaticus .JPG'],
 'Helicobacter pylori':['File:Helicobacter pylori.jpg','File:Helicobacter pylori2.jpg'],
 'Heterocephalus glaber':['File:Heterocephalus glaber.jpg','File:Nacktmull.jpg','File:Naked mole rat.jpg'],
 'Daubentonia madagascariensis':['File:Aye-aye.jpg','File:Daubentonia madagascariensis.jpg'],
 'Sulfolobus acidocaldarius':['File:Sulfolobus acidocaldarius.jpg'],
 'Nostoc punctiforme':['File:Nostoc punctiforme.jpg'],
 'Candidatus Thiomargarita magnifica':['File:Morphology and ultrastructure of Ca. T. magnifica.jpg'],
 'Phytophthora infestans':['File:Phytophthora infestans sporangia.jpg','File:Phytophthora infestans.jpg'],
 'Rhizobium leguminosarum':['File:Rhizobium leguminosarum.jpg'],
 'Conraua goliath':['File:Conraua goliath.jpg'],
 'Ichthyophis glutinosus':['File:Ichthyophis glutinosus.jpg'],
 'Trichodesmium erythraeum':['File:Trichodesmium erythraeum.jpg','File:Trichodesmium erythraeum.jpeg']
}
CAPTION_CREDITS={
 'File:SalmonellaNIAID.jpg':'Rocky Mountain Laboratories, NIAID, NIH',
 'File:Yersinia pestis.jpg':'Rocky Mountain Laboratories, NIAID, NIH'
}
PLANTS={'Agaricus bisporus','Amborella trichopoda','Camellia sinensis','Cannabis sativa','Corallina officinalis','Fucus vesiculosus','Hevea brasiliensis','Hordeum vulgare','Manihot esculenta','Ulva lactuca','Vitis vinifera','Acer platanoides','Rosa multiflora','Sassafras albidum','Celastrus orbiculatus'}
ANIMALS={'Architeuthis dux','Conraua goliath','Daubentonia madagascariensis','Heterocephalus glaber','Homo sapiens','Ichthyophis glutinosus','Istiophorus platypterus','Petromyzon marinus'}
ORIGINAL_RIGHTS=base.image_rights

def load(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def save(p,obj):core.dump(p,obj)
def sha(b):return hashlib.sha256(b).hexdigest()

def rights_with_documented_caption_credit(page,info):
    original=copy.deepcopy(info)
    meta=info.get('extmetadata',{});artist=core.clean(meta.get('Artist',{}).get('value',''))
    evidence=None
    expected=CAPTION_CREDITS.get(page.get('title'))
    if not artist and expected:
        caption=core.clean(meta.get('ImageDescription',{}).get('value',''))
        if base.normal(expected) not in base.normal(caption):
            return None,'explicit_institution_credit_not_found_in_caption'
        evidence={'field':'ImageDescription','exactSourceCredit':expected,'sourcePage':info['descriptionurl'],'originalArtistWasBlank':True}
        info=copy.deepcopy(info)
        info.setdefault('extmetadata',{})['Artist']={'value':expected,'source':'explicit-credit-in-original-caption'}
    rights,reason=ORIGINAL_RIGHTS(page,info)
    if rights and evidence:rights['authorEvidence']=evidence
    return rights,reason

@contextmanager
def switched():
    old=(base.BATCH,base.REVIEW)
    base.BATCH,base.REVIEW=BATCH,REVIEW
    try:yield
    finally:base.BATCH,base.REVIEW=old

def gather_one(target,seen):
    name=target['scientificName'];variants=[name]
    if name=='Candidatus Thiomargarita magnifica':variants+=['Thiomargarita magnifica']
    if name=='Lactobacillus delbrueckii subsp. bulgaricus':variants+=['Lactobacillus bulgaricus']
    if name=='Salmonella enterica':variants+=['Salmonella typhimurium','Salmonella enterica serovar Typhimurium']
    records=[];attempts=[]
    exact=EXACT.get(name,[])
    if exact:
        try:
            rows,attempt=base.commons_records(target,{'titles':'|'.join(exact),'redirects':1},'verified_exact_source_file_leads',seen,variants,{'sourceFileLeads':exact,'captionAndTaxonRequireVisualAdjudication':True})
            for r in rows:r['selectionScore']+=30
            records+=rows;attempts.append(attempt)
        except Exception as e:attempts.append({'route':'exact_named_source_files','files':exact,'error':str(e)})
    queries=[]
    if name in PLANTS:
        queries=[f'"{name}" (habit OR habitus OR whole OR tree OR plant) -flower -leaf -fruit -herbarium filetype:bitmap',f'"{name}" filetype:bitmap -drawing -illustration -map']
    elif name in ANIMALS:
        queries=[f'"{name}" (living OR alive OR swimming OR walking OR standing OR zoo) filetype:bitmap -model -taxidermy -skeleton',f'"{name}" filetype:bitmap -drawing -illustration -map']
    else:
        queries=[f'"{variants[-1]}" (micrograph OR microscopy OR SEM OR TEM OR cells OR conidia OR sporangia) filetype:bitmap -protein -structure -diagram -agar',f'"{variants[-1]}" filetype:bitmap -protein -diagram -map']
    for q in queries:
        try:
            rows,attempt=base.commons_records(target,{'generator':'search','gsrsearch':q,'gsrnamespace':6,'gsrlimit':45},'focused_microscopy_or_whole_subject_search',seen,variants)
            records+=rows;attempts.append(attempt)
        except Exception as e:attempts.append({'route':'focused_source_search','query':q,'error':str(e)})
    # Search category files as well as the search index. This retrieves images without
    # an English habit caption, but exact scientific identity must remain in metadata.
    for category in [name,'Habitus of '+name] if name in PLANTS else [name]:
        try:
            rows,attempt=base.commons_records(target,{'generator':'categorymembers','gcmtitle':'Category:'+category,'gcmtype':'file','gcmlimit':100},'category_file_inventory',seen,variants)
            records+=rows;attempts.append(attempt)
        except Exception as e:attempts.append({'route':'category_inventory','category':category,'error':str(e)})
    uniq={}
    for r in records:
        if (target['id'],r['assetId']) in seen:continue
        if r['assetId'] not in uniq or r['selectionScore']>uniq[r['assetId']]['selectionScore']:uniq[r['assetId']]=r
    ranked=sorted(uniq.values(),key=lambda r:r['selectionScore'],reverse=True)
    saved=[];errors=[]
    for r in ranked[:12]:
        if len(saved)>=3:break
        try:
            raw=core.get(r['downloadUrl'],binary=True)
            with Image.open(io.BytesIO(raw)) as source:
                if getattr(source,'n_frames',1)>1:raise ValueError('animated_source_excluded')
                source.load();im=ImageOps.exif_transpose(source).convert('RGB')
            if min(im.size)<150 or max(im.size)<260:raise ValueError('original_too_small_for_recognizable_main_photo')
            im.thumbnail((1800,1800),Image.Resampling.LANCZOS);buf=io.BytesIO();im.save(buf,'JPEG',quality=93,optimize=True);body=buf.getvalue()
            path=f"{BATCH}/previews/{core.slug(name)}--{r['assetId']}.jpg"
            (ROOT/path).parent.mkdir(parents=True,exist_ok=True);(ROOT/path).write_bytes(body)
            r.update({'previewPath':path,'previewSha256':sha(body),'previewDimensions':list(im.size),'downloadedSourceSha256':sha(raw),'lowResolutionOriginal':min(im.size)<500,'status':'pending_actual_image_review'})
            saved.append(r)
        except Exception as e:errors.append({'assetId':r['assetId'],'error':str(e)})
    return saved,{'targetId':target['id'],'scientificName':name,'attempts':attempts,'eligibleUniqueCandidates':len(uniq),'savedPreviews':len(saved),'downloadErrors':errors}

def gather():
    if (ROOT/BATCH/'candidates.json').exists():raise ValueError('Immutable second-pass snapshot already exists')
    spec,records,roles=base.decisions();solved={records[n]['target']['id'] for n,role in roles.items() if role=='primary'}
    start=load(base.BATCH+'/original-gaps.json');targets={t['id']:t for t in load('data/targets.json')['records']}
    pending=[targets[t['id']] for t in start if t['id'] not in solved]
    save(BATCH+'/target-list.json',pending)
    seen=base.existing_lookup()
    for p in (ROOT/'batches').glob('*/candidates.json'):
        for r in json.loads(p.read_text()).get('records',[]):seen[(r['target']['id'],r['assetId'])]=r.get('previewPath','earlier_candidate')
    base.image_rights=rights_with_documented_caption_credit
    allrecords=[];searches=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        fs={pool.submit(gather_one,t,seen):t for t in pending}
        for i,f in enumerate(as_completed(fs),1):
            t=fs[f]
            try:rows,report=f.result();allrecords+=rows;searches.append(report)
            except Exception as e:searches.append({'targetId':t['id'],'scientificName':t['scientificName'],'fatalError':str(e)})
            if i%10==0:print(json.dumps({'targetsProcessed':i,'targets':len(pending),'newCandidates':len(allrecords)}),flush=True)
    base.image_rights=ORIGINAL_RIGHTS
    order={t['id']:i for i,t in enumerate(pending)}
    allrecords.sort(key=lambda r:(order[r['target']['id']],-r['selectionScore'],r['assetId']))
    for n,r in enumerate(allrecords,1):r['number']=n
    save(BATCH+'/candidates.json',{'generatedAt':core.NOW(),'records':allrecords});save(BATCH+'/search-evidence.json',searches)
    folder=ROOT/BATCH/'sheets';folder.mkdir(parents=True,exist_ok=True);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',16)
    for offset in range(0,len(allrecords),16):
        sheet=Image.new('RGB',(1920,1760),'white');draw=ImageDraw.Draw(sheet)
        for n,r in enumerate(allrecords[offset:offset+16]):
            x=n%4*480;y=n//4*440
            with Image.open(ROOT/r['previewPath']) as im:
                im.thumbnail((466,360),Image.Resampling.LANCZOS);sheet.paste(im,(x+(480-im.width)//2,y+(360-im.height)//2))
            draw.text((x+6,y+368),f"{r['number']:03d} {r['target']['scientificName']}"[:52],font=font,fill='black')
            draw.text((x+6,y+394),r['assetId']+' '+r['licenseCode'],font=font,fill='black')
            draw.text((x+6,y+416),str(r['previewDimensions']),font=font,fill='black')
        sheet.save(folder/f'targeted-{offset//16+1:03d}.jpg',quality=93)
    report={'generatedAt':core.NOW(),'targetsAttempted':len(pending),'candidateImages':len(allrecords),'candidateTaxa':len({r['target']['id'] for r in allrecords}),'candidateManifestSha256':sha((ROOT/BATCH/'candidates.json').read_bytes()),'visualReview':'pending','licenseCounts':dict(Counter(r['licenseCode'] for r in allrecords))}
    save(BATCH+'/status.json',report);print(json.dumps(report),flush=True)

def adopt():
    with switched():base.adopt()

def apply_decisions(decisions,evidence):
    with switched():base.apply_decisions(decisions,evidence)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('gather','adopt'));a=p.parse_args();{'gather':gather,'adopt':adopt}[a.mode]()
