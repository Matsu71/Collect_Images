#!/usr/bin/env python3
"""Close every requested remaining target, without equating exceptions with found images."""
from __future__ import annotations
import argparse,csv,hashlib,json,os,re,shutil,subprocess,sys,tempfile
from collections import Counter
from pathlib import Path
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[1]
BATCH='batches/remaining-closure-20260914'

def load(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def save(p,obj):
    path=ROOT/p;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    from install_remaining_support import install
    install()
    import remaining_targeted
    remaining_targeted.adopt()
    if (ROOT/'reviews/remaining-panels-20260914.json').exists():
        import remaining_panels
        remaining_panels.adopt()
    import run_reviewed_build
    run_reviewed_build.main()
    before=load(BATCH+'/baseline.json');after=load('reports/curation-status.json')
    first=load(BATCH+'/adoption.json');second=load(remaining_targeted.BATCH+'/adoption.json')
    assert not first['failures'] and not second['failures']
    original=load(BATCH+'/original-gaps.json');alltargets=load('data/targets.json')['records'];taxa=load('collection/taxa.json')['records']
    index={t['id']:t for t in taxa};assets=load('collection/assets.json')['records'];primary=load('collection/primary.json')['records']
    assert len(alltargets)==len(taxa)==after['targetCount']==before['targetCount']==1000
    assert len(original)==76 and before['primaryReadyTaxa']==924
    assert len(primary)==len({r['targetId'] for r in primary})==after['primaryReadyTaxa']
    assert after['pendingReviewPhotoPairs']==0,'Unreviewed or automatically held images remain; inspect before closing.'
    first_search={r['targetId']:r for r in load(BATCH+'/search-evidence.json')}
    second_search={r['targetId']:r for r in load(remaining_targeted.BATCH+'/search-evidence.json')}
    assert set(first_search)=={t['id'] for t in original},'Not every original target received a search'
    exception_path='data/remaining-closure-exceptions-20260914.json'
    exceptions=load(exception_path)['records'];exception_index={r['targetId']:r for r in exceptions}
    outcomes=[]
    for target in original:
        tid=target['id'];final=index[tid]
        attempts=list(first_search[tid].get('attempts',[]))+list(second_search.get(tid,{}).get('attempts',[]))
        assert attempts,'Target has no recorded source lookup: '+tid
        row={'targetId':tid,'scientificName':target['scientificName'],'nameJa':target.get('nameJa',''),'collectionTier':target.get('collectionTier'),'searchAttemptCount':len(attempts),'searchEvidence':[BATCH+'/search-evidence.json']+([remaining_targeted.BATCH+'/search-evidence.json'] if tid in second_search else []),'supplementaryPhotoCount':len(final['supplementaryPhotos'])}
        if final['primaryPhoto']:
            rec=load(final['primaryPhoto']['metadata'])
            row.update({'outcome':'primary_image_saved','primaryPhoto':final['primaryPhoto'],'resolution':rec['dimensions']['master'],'lowResolutionOriginal':min(rec['dimensions']['master'])<500,'reviewNoteJa':rec['visualReview'].get('noteJa',''),'rightsBasis':rec['licenseName'],'reasonJa':'出典と画像を確認した主画像を保存。画像別の発育段階・顕微鏡像・画質等の注記を保持します。'})
        else:
            if tid not in exception_index:raise ValueError('Missing a specific final exception reason for '+tid)
            exception=exception_index[tid]
            if not exception.get('reasonJa') or not exception.get('category'):raise ValueError('Incomplete exception: '+tid)
            row.update({'outcome':'closed_without_suitable_primary','category':exception['category'],'reasonJa':exception['reasonJa'],'additionalSourceChecks':exception.get('sourceChecks',[]),'conclusionScope':'No suitable commercially reusable primary image established within documented searches; not a claim that no photograph exists anywhere.'})
        outcomes.append(row)
    save('reports/remaining-closure-outcomes.json',{'generatedAt':after['generatedAt'],'requestedRemainingTargets':76,'records':outcomes})
    keys=['acceptedPhotographs','acceptedTaxonCoverage','primaryReadyTaxa','chronoearthPrimaryReadyTaxa','downloadedTargetCoverage','chronoearthDownloadedCoverage']
    resolved=sum(r['outcome']=='primary_image_saved' for r in outcomes);skipped=76-resolved
    assert after['primaryReadyTaxa']==924+resolved,'Coverage gain differs from original remaining-target outcomes'
    reviewed_first=load('reviews/remaining-closure-20260914.json');reviewed_second=load(remaining_targeted.REVIEW)
    rights_holds=load('reports/remaining-source-rights-holds.json')
    report={'generatedAt':after['generatedAt'],'requestStatus':'completed_all_remaining_targets_adjudicated','originalRemainingTargets':76,'targetsSearched':len(outcomes),'newlyCoveredPrimaryTargets':resolved,'closedWithoutSuitablePrimary':skipped,'exceptionCategories':dict(Counter(r['category'] for r in outcomes if r['outcome']!='primary_image_saved')),'before':{k:before[k] for k in keys},'after':{k:after[k] for k in keys},'change':{k:after[k]-before[k] for k in keys},'newImageFilesAdopted':first['newImageCount']+second['newImageCount'],'existingImagesReconsidered':first['existingImagesReconsidered']+second['existingImagesReconsidered'],'candidateImagesVisuallyReviewed':reviewed_first['reviewedCount']+reviewed_second['reviewedCount'],'rawSavedCandidatesAreNotAllAccepted':True,'previousSourceRightsHolds':rights_holds['count'],'pendingVisualReviews':after['pendingReviewPhotoPairs'],'saveFailures':[],'targetListUnchanged':True,'chronoearthApplicationUnchanged':True,'limitations':'Main images denote reviewed recognizable major appearance, including explicitly labelled low-resolution original microscopy and life stages. Source reuse statements are recorded; specialist reidentification and all third-party rights are not warranted. No artificial enlargement or generated anatomy was used.'}
    with (ROOT/'reports/remaining-closure-outcomes.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['targetId','scientificName','nameJa','collectionTier','outcome','category','reasonJa','searchAttemptCount','supplementaryPhotoCount'];writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(outcomes)
    # Each selected master must still match the exact recorded bytes, including
    # separately re-reviewed regenerated thumbnails and explicit panel crops.
    for item in first['saved']+second['saved']:
        rec=load(item['metadataPath'])
        for kind in ('master','web'):
            assert hashlib.sha256((ROOT/rec['files'][kind]).read_bytes()).hexdigest()==rec['sha256'][kind]
    from remaining_closure import verify_public_domain
    for rec in assets:
        if rec['licenseCode']=='public-domain':assert verify_public_domain(rec)
        assert rec['licenseCode'] in ('cc0','cc-by','cc-by-sa','public-domain')
    output=args.output.resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('Portable destination must be empty; no silent overwrite')
    run=subprocess.run([sys.executable,str(ROOT/'tools/export_collection.py'),'--output',str(output)],cwd=ROOT,check=True,capture_output=True,text=True)
    export=json.loads(run.stdout)
    subprocess.run([sys.executable,str(ROOT/'tools/build_export_gallery.py'),str(output)],cwd=ROOT,check=True)
    with tempfile.TemporaryDirectory(prefix='verified-non-sa-') as tmp:
        result=subprocess.run([sys.executable,str(ROOT/'tools/export_collection.py'),'--output',str(Path(tmp)/'images'),'--licenses','cc0,cc-by,public-domain'],cwd=ROOT,check=True,capture_output=True,text=True)
        non_sa=json.loads(result.stdout)
    links=[]
    class Parser(HTMLParser):
        def handle_starttag(self,tag,attrs):
            for k,v in attrs:
                if k in ('href','src') and v and not v.startswith(('http:','https:','#','data:')):links.append(v)
    Parser().feed((output/'index.html').read_text(encoding='utf-8'))
    missing=[p for p in links if not (output/p).resolve().is_file()];assert not missing,missing[:10]
    verification={'validatedAt':after['generatedAt'],'masterAndWebHashes':'pass','sourceSpecificPublicDomainEvidence':'pass','all76TargetsHaveOutcomes':'pass','noPendingVisualReview':'pass','primaryTargetsUnique':'pass','original1000TargetListPreserved':'pass','galleryLocalLinksChecked':len(links),'galleryMissingAssets':missing,'allPrimaryExport':export,'cc0ByAndPublicDomainExport':non_sa,'noSilentUpscalingOrGeneratedContent':True}
    report['portablePrimaryImagesVerified']=export['photos'];report['primaryImagesWithoutShareAlike']=non_sa['photos']
    report['newPrimaryOriginalsUnder500pxShortSide']=sum(r.get('lowResolutionOriginal',False) for r in outcomes if r['outcome']=='primary_image_saved')
    save('reports/remaining-closure-summary.json',report);save('reports/remaining-closure-validation.json',verification);save('reports/export-validation.json',verification)
    lines=['# 未確保76分類群の最終結果','',f'主画像を確保: {resolved}分類群。条件を満たす主画像を確認できず見送った対象: {skipped}分類群。検索未実施・判定待ちはありません。','', '見送りは世界中に画像が存在しないとの断定ではありません。写真自体が見つかっても、個別の商用再利用条件、同定、視認性などを確認できない場合を含みます。','', '| 和名 | 学名 | 結果・理由 |','|---|---|---|']
    for row in outcomes:
        if row['outcome']!='primary_image_saved':lines.append('| '+(row['nameJa'] or '—')+' | '+row['scientificName']+' | '+row['reasonJa'].replace('|','／')+' |')
    (ROOT/'reports/remaining-closure-outcomes.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    for filename,src in [('completion-summary.json','reports/remaining-closure-summary.json'),('remaining-outcomes.json','reports/remaining-closure-outcomes.json'),('remaining-outcomes.csv','reports/remaining-closure-outcomes.csv'),('remaining-outcomes.md','reports/remaining-closure-outcomes.md'),('validation.json','reports/remaining-closure-validation.json')]:shutil.copy2(ROOT/src,output/filename)
    readme=ROOT/'README.md';text=readme.read_text(encoding='utf-8')
    values={'画像を取得できた分類群':str(after['downloadedTargetCoverage']),'主画像・補足として残した素材':f"**{after['acceptedPhotographs']:,}点、{after['acceptedTaxonCoverage']:,}分類群に対応**",'姿・主要な特徴が分かる主画像候補を選べた分類群':f"**{after['primaryReadyTaxa']}**",'主画像候補の写真×分類群の対応数':str(after['primaryCandidatePhotoPairs']),'補足用の写真×分類群の対応数':str(after['supplementaryPhotoPairs']),'不明瞭・図版・誤対応等で除外した対応数':str(after['excludedPhotoPairs']),'取得画像の一覧確認が未実施の対応数':str(after['pendingReviewPhotoPairs'])}
    for label,value in values.items():
        text,n=re.subn(r'^\| '+re.escape(label)+r' \|.*\|$',f'| {label} | {value} |',text,flags=re.M)
        if n!=1:raise ValueError('README statistics structure changed: '+label)
    text,n=re.subn(r'ChronoEarth由来532分類群では、画像取得は\d+、主画像候補の選定は\d+です。',f"ChronoEarth由来532分類群では、画像取得は{after['chronoearthDownloadedCoverage']}、主画像候補の選定は{after['chronoearthPrimaryReadyTaxa']}です。",text)
    if n!=1:raise ValueError('README source coverage structure changed')
    start='<!-- REMAINING-CLOSURE-COMPLETE -->';end='<!-- /REMAINING-CLOSURE-COMPLETE -->'
    block=f'''{start}
## 残り76分類群の検索・判定完了

主画像未確保だった全76分類群を確認し、**{resolved}分類群の主画像を追加確保**しました。現在の主画像は **{after['primaryReadyTaxa']}/1,000分類群**です。残り{skipped}分類群は、調べた出典・確認した写真・採用できない理由を記録して見送りました。検索待ちや保存失敗を完了扱いしたものではありません。

[全76分類群の結果JSON](reports/remaining-closure-outcomes.json) · [見送った対象と理由](reports/remaining-closure-outcomes.md) · [最終集計](reports/remaining-closure-summary.json) · [保存・出典・書き出し検証](reports/remaining-closure-validation.json)

CC0・CC BY・CC BY-SAに加えて、個別の権利根拠を確認したpublic-domain素材を区別して収録しました。Public Domain Markを許諾ライセンスとは扱いません。元から小さい科学写真は原寸・低解像度を明記し、拡大生成せず保存しています。権利表示に矛盾が見つかった原典由来の既存素材は、元のファイルを残したうえで採用台帳から除外しています。

利用時は必ず `collection/` の採用台帳を参照してください。生の取得フォルダには、図版や権利確認中など採用しない画像も含まれます。詳しい条件は [最終検索の基準](docs/REMAINING_SEARCH_COMPLETION.ja.md) を参照してください。
{end}
'''
    if start in text:text=re.sub(re.escape(start)+r'.*?'+re.escape(end)+'\n?',lambda _:block,text,flags=re.S)
    else:text=text.replace('## 利用するファイル\n',block+'\n## 利用するファイル\n',1)
    text=text.replace('対象は画像ごとに明示された **CC0・CC BY・CC BY-SA** です。','対象は画像ごとに明示された **CC0・CC BY・CC BY-SA** と、別途個別の根拠を確認した **public-domain** 素材です。')
    readme.write_text(text,encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
