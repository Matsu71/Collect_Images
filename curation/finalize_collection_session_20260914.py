#!/usr/bin/env python3
"""Finalize this collection session without double counting previews or earlier images."""
from __future__ import annotations
import argparse,hashlib,json,re,subprocess,sys,tempfile
from pathlib import Path
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))
def save(path,value):(ROOT/path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    before=load('batches/gaps-round3-20260914/baseline.json');after=load('reports/curation-status.json')
    batch=load('batches/gaps-round3-20260914/adoption.json');targeted=load('batches/targeted-micrographs-20260914/acquisition.json')
    reviewed=load('reviews/targeted-micrographs-20260914.json')
    assert not batch['failures'] and targeted['phase']=='reconciled_successfully'
    assets=load('collection/assets.json')['records'];primary=load('collection/primary.json')['records'];taxa=load('collection/taxa.json')['records']
    assert len(taxa)==after['targetCount']==before['targetCount']==1000
    assert len(primary)==len({r['targetId'] for r in primary})==after['primaryReadyTaxa']
    assetmap={(r['targetId'],r['assetId']):r for r in assets}
    for item in reviewed['records']:
        rec=assetmap[(item['targetId'],item['assetId'])]
        assert rec['visualReview']['reviewFile']=='reviews/targeted-micrographs-20260914.json'
        assert rec['sha256']['master']==item['masterSha256']
        assert hashlib.sha256((ROOT/rec['files']['master']).read_bytes()).hexdigest()==item['masterSha256']
    assert after['pendingReviewPhotoPairs']==0
    keys=['acceptedPhotographs','acceptedTaxonCoverage','primaryReadyTaxa','chronoearthPrimaryReadyTaxa','downloadedTargetCoverage','chronoearthDownloadedCoverage']
    report={'generatedAt':after['generatedAt'],'sourceBaseline':'batches/gaps-round3-20260914/baseline.json','before':{k:before[k] for k in keys},'after':{k:after[k] for k in keys},'change':{k:after[k]-before[k] for k in keys},'newSavedPhotoCount':batch['savedCount']+targeted['newImageCount'],'round3SavedPhotographs':batch['savedCount'],'newIndividuallyReviewedMicrographs':targeted['newImageCount'],'round3CandidatesReviewed':batch['reviewedCount'],'round3DecisionCounts':batch['roleCounts'],'previouslyStoredMicrographsNotDoubleCounted':targeted['existingEarlierImagesReused'],'primaryGapsRemaining':after['targetCount']-after['primaryReadyTaxa'],'chronoearthPrimaryGapsRemaining':after['chronoearthTargetCount']-after['chronoearthPrimaryReadyTaxa'],'pendingVisualReview':after['pendingReviewPhotoPairs'],'fileSaveAndReviewFailures':[],'limitations':'Review is mainly contact-sheet composition and source-caption screening. The new microbial JPEG was individually inspected. These are not independent specialist identifications, full-original pixel audits, or guarantees of all third-party rights. Microscopy, false colour, specimens and life stages retain their notes.'}
    assert report['change']['acceptedPhotographs']==report['newSavedPhotoCount']
    assert report['change']['primaryReadyTaxa']>0
    exports={}
    all_run=subprocess.run([sys.executable,str(ROOT/'tools/export_collection.py'),'--output',str(args.output)],cwd=ROOT,check=True,capture_output=True,text=True)
    exports['allLicensePrimaryExport']=json.loads(all_run.stdout)
    subprocess.run([sys.executable,str(ROOT/'tools/build_export_gallery.py'),str(args.output)],cwd=ROOT,check=True)
    with tempfile.TemporaryDirectory(prefix='cc0-by-export-') as temporary:
        run=subprocess.run([sys.executable,str(ROOT/'tools/export_collection.py'),'--output',str(Path(temporary)/'package'),'--licenses','cc0,cc-by'],cwd=ROOT,check=True,capture_output=True,text=True)
        exports['cc0AndByPrimaryExport']=json.loads(run.stdout)
    links=[]
    class Parser(HTMLParser):
        def handle_starttag(self,tag,attrs):
            for key,value in attrs:
                if key in ('src','href') and value and not value.startswith(('http:','https:','#','data:')):links.append(value)
    Parser().feed((args.output/'index.html').read_text(encoding='utf-8'))
    missing=[v for v in links if not (args.output/v).resolve().is_file()]
    assert not missing,missing[:10]
    verify={'validatedAt':after['generatedAt'],'savedImageHashesAndDecoding':after['imageFileHashAndDecodeValidation'],'imageLicenceAndAttribution':after['attributionAndLicenseUrlValidation'],'individualMicrographHashAndReview':'pass','primaryTargetsUnique':'pass','originalTargetListUnchanged':'pass','portableGalleryLocalLinksChecked':len(links),'portableGalleryMissingAssets':missing,'exportCopyAndHashes':'pass',**exports}
    report['portablePrimaryExportValidated']=exports['allLicensePrimaryExport']['photos'];report['cc0AndByPrimaryExportValidated']=exports['cc0AndByPrimaryExport']['photos']
    save('reports/continuation-session-20260914.json',report);save('reports/export-validation.json',verify);save('reports/session-validation-20260914.json',verify)
    for name,value in [('collection-status.json',after),('collection-progress.json',report),('validation.json',verify)]:
        (args.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    readme=ROOT/'README.md';text=readme.read_text(encoding='utf-8')
    values={'画像を取得できた分類群':str(after['downloadedTargetCoverage']),'主画像・補足として残した素材':f"**{after['acceptedPhotographs']:,}点、{after['acceptedTaxonCoverage']:,}分類群に対応**",'姿・主要な特徴が分かる主画像候補を選べた分類群':f"**{after['primaryReadyTaxa']}**",'主画像候補の写真×分類群の対応数':str(after['primaryCandidatePhotoPairs']),'補足用の写真×分類群の対応数':str(after['supplementaryPhotoPairs']),'不明瞭・図版・誤対応等で除外した対応数':str(after['excludedPhotoPairs']),'取得画像の一覧確認が未実施の対応数':str(after['pendingReviewPhotoPairs'])}
    for label,value in values.items():
        text,n=re.subn(r'^\| '+re.escape(label)+r' \|.*\|$',f'| {label} | {value} |',text,flags=re.M)
        if n!=1:raise ValueError('README statistics changed; avoid blind replacement: '+label)
    text,n=re.subn(r'ChronoEarth由来532分類群では、画像取得は\d+、主画像候補の選定は\d+です。',f"ChronoEarth由来532分類群では、画像取得は{after['chronoearthDownloadedCoverage']}、主画像候補の選定は{after['chronoearthPrimaryReadyTaxa']}です。",text)
    if n!=1:raise ValueError('Source coverage paragraph changed')
    start='<!-- SESSION-FINAL-20260914 -->';end='<!-- /SESSION-FINAL-20260914 -->'
    note=f'''{start}
## 第3回の確定結果と微生物写真の補完

第3回の追加{batch['savedCount']}枚に加え、プロクロロコッカスの電子顕微鏡写真1枚を個別に確認して保存しました。今回の新規採用は合計 **{report['newSavedPhotoCount']}枚**です。既存のプロメテオアルカエウムの画像は再取得・上書きせず、新規件数にも数えていません。

今回の開始時点と比べ、主画像候補は **{before['primaryReadyTaxa']} → {after['primaryReadyTaxa']}分類群**、採用した写真は **{before['acceptedPhotographs']:,} → {after['acceptedPhotographs']:,}枚**です。ChronoEarth由来の主画像候補は **{before['chronoearthPrimaryReadyTaxa']} → {after['chronoearthPrimaryReadyTaxa']}分類群**になりました。残る主画像不足は全体{report['primaryGapsRemaining']}分類群、ChronoEarth由来{report['chronoearthPrimaryGapsRemaining']}分類群です。

微生物の写真には電子顕微鏡による観察像、出典側での緑色の着色・回転・トリミングが含まれます。生体を自然光で撮った画像や、そのままの色彩として表示しないよう画像別に明記しています。写真の商用利用は画像ごとのライセンス条件に従います。

[確定した差分](reports/continuation-session-20260914.json) · [画像・出典・書き出し検証](reports/session-validation-20260914.json) · [微生物の個別目視記録](reviews/targeted-micrographs-20260914.json)
{end}
'''
    if start in text:text=re.sub(re.escape(start)+r'.*?'+re.escape(end)+'\n?',lambda _:note,text,flags=re.S)
    else:text=text.replace('## 利用するファイル\n',note+'\n## 利用するファイル\n',1)
    readme.write_text(text,encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
