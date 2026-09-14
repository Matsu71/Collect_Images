#!/usr/bin/env python3
"""Report completed image work from actual manifests, not from intended candidate counts."""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def save(p,data):
    path=ROOT/p;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    baseline=load('reports/continuation-baseline-20260914.json')
    current=load('reports/curation-status.json')
    adoption=load('batches/gaps-20260914/adoption.json')
    primary=load('collection/primary.json')['records'];assets=load('collection/assets.json')['records']
    assert len(primary)==current['primaryReadyTaxa']
    keys=['acceptedPhotographs','acceptedTaxonCoverage','primaryReadyTaxa','chronoearthPrimaryReadyTaxa','downloadedTargetCoverage','chronoearthDownloadedCoverage']
    result={'generatedAt':datetime.now(timezone.utc).isoformat(timespec='seconds'),'baselineSource':'reports/continuation-baseline-20260914.json','currentSource':'reports/curation-status.json','before':{k:baseline[k] for k in keys},'after':{k:current[k] for k in keys},'change':{k:current[k]-baseline[k] for k in keys},'candidateImagesReviewed':adoption['reviewedCount'],'candidateDecisionCounts':adoption['roleCounts'],'selectedImageFilesSaved':adoption['savedCount'],'selectedTaxaSaved':adoption['savedTaxa'],'saveFailures':adoption['failures'],'primaryGapsRemaining':current['targetCount']-current['primaryReadyTaxa'],'chronoearthPrimaryGapsRemaining':current['chronoearthTargetCount']-current['chronoearthPrimaryReadyTaxa'],'rejectedPreviewsAreNotAdopted':True,'commercialLicenseRecheckedAtSave':True,'reviewPreviewToOriginalImageSha1Checked':True,'limitations':'Counts refer to saved files and catalogue entries. Composition screening and source-caption checks are not expert species re-identification, a pixel-level audit of every master, or an independent warranty of all third-party rights.'}
    temp=Path(os.getenv('RUNNER_TEMP','/tmp'))
    exports={}
    for name,args in [('allLicensePrimaryExport',[]),('cc0AndByPrimaryExport',['--licenses','cc0,cc-by'])]:
        dest=temp/('gap-export-'+name)
        if dest.exists():shutil.rmtree(dest)
        run=subprocess.run([sys.executable,str(ROOT/'tools/export_collection.py'),'--output',str(dest),*args],cwd=ROOT,check=True,text=True,capture_output=True)
        exports[name]=json.loads(run.stdout)
    links=[]
    class Links(HTMLParser):
        def handle_starttag(self,tag,attrs):
            fields=dict(attrs)
            for k in ('src','href'):
                v=fields.get(k,'')
                if v and not v.startswith(('http:','https:','#','data:')):links.append(v)
    Links().feed((ROOT/'collection/index.html').read_text(encoding='utf-8'))
    missing=[p for p in links if not (ROOT/'collection'/p).resolve().is_file()]
    assert not missing,missing[:10]
    assert not any(r.get('author','').lower()=='no rights reserved' for r in assets)
    validation={'validatedAt':result['generatedAt'],**exports,'galleryLocalLinksChecked':len(links),'galleryMissingAssets':missing,'exportCopyAndHashes':'pass','rightsNoticesMisrepresentedAsAuthors':0,'reviewPreviewToOriginalImageSha1Check':'pass' if not adoption['failures'] else 'see_adoption_failures'}
    save('reports/export-validation.json',validation)
    result['portablePrimaryExportValidated']=exports['allLicensePrimaryExport']['photos']
    result['cc0AndByPrimaryExportValidated']=exports['cc0AndByPrimaryExport']['photos']
    save('reports/continuation-result-20260914.json',result)
    readme=ROOT/'README.md';text=readme.read_text(encoding='utf-8')
    replacements={
        '画像を取得できた分類群':f"{current['downloadedTargetCoverage']:,}",
        '主画像・補足として残した素材':f"**{current['acceptedPhotographs']:,}点、{current['acceptedTaxonCoverage']:,}分類群に対応**",
        '姿・主要な特徴が分かる主画像候補を選べた分類群':f"**{current['primaryReadyTaxa']:,}**",
        '主画像候補の写真×分類群の対応数':f"{current['primaryCandidatePhotoPairs']:,}",
        '補足用の写真×分類群の対応数':f"{current['supplementaryPhotoPairs']:,}",
        '不明瞭・図版・誤対応等で除外した対応数':f"{current['excludedPhotoPairs']:,}",
        '取得画像の一覧確認が未実施の対応数':f"{current['pendingReviewPhotoPairs']:,}"
    }
    for label,value in replacements.items():
        text,n=re.subn(r'^\| '+re.escape(label)+r' \|.*\|$',f'| {label} | {value} |',text,flags=re.M)
        if n!=1:raise ValueError('README statistics row missing or duplicated: '+label)
    text,n=re.subn(r'ChronoEarth由来532分類群では、画像取得は\d+、主画像候補の選定は\d+です。',f"ChronoEarth由来532分類群では、画像取得は{current['chronoearthDownloadedCoverage']}、主画像候補の選定は{current['chronoearthPrimaryReadyTaxa']}です。",text)
    if n!=1:raise ValueError('README ChronoEarth coverage sentence no longer matches; avoid blind overwrite')
    start='<!-- GAP-PROGRESS-20260914 -->';end='<!-- /GAP-PROGRESS-20260914 -->'
    block=f'''{start}
## 主画像不足の追加収集（2026-09-14）

主画像が不足する分類群を優先し、{adoption['reviewedCount']:,}枚の新規候補を画像一覧と出典の説明で確認しました。主画像候補{adoption['roleCounts']['primary']}枚、補足用{adoption['roleCounts']['supplementary']}枚、除外{adoption['roleCounts']['exclude']}枚に分け、採用分{adoption['savedCount']}枚の画像本体を保存しています。

主画像候補の確保は **{baseline['primaryReadyTaxa']} → {current['primaryReadyTaxa']}分類群**、ChronoEarth由来分は **{baseline['chronoearthPrimaryReadyTaxa']} → {current['chronoearthPrimaryReadyTaxa']}分類群**です。未確保は全体{result['primaryGapsRemaining']}分類群、ChronoEarth由来{result['chronoearthPrimaryGapsRemaining']}分類群です。数字を増やすために花・葉などの部分写真を全身・樹形の主画像へ昇格させてはいません。

追加分は保存前にライセンスを再確認し、目視したプレビューと保存用写真の元画像SHA-1を照合しました。画像本体・WebP・作者・ライセンス・出典・加工情報を保持しています。検索で別の生物に結び付いた1候補は、画像と出典に明記された学名に基づいて対応先を訂正しました。

追加分の除外候補{adoption['roleCounts']['exclude']}枚は `batches/gaps-20260914/` の審査証跡だけに残し、採用フォルダへ追加していません。上の「除外した対応数」は従来の取得済み素材の除外数で、この追加候補の除外とは別です。詳しくは [今回の差分と検証](reports/continuation-result-20260914.json)、[目視判定](reviews/gap-20260914.json)、[保存結果](batches/gaps-20260914/adoption.json) を参照してください。
{end}
'''
    if start in text:text=re.sub(re.escape(start)+r'.*?'+re.escape(end)+'\n?',lambda _:block,text,flags=re.S)
    else:text=text.replace('## 利用するファイル\n',block+'\n## 利用するファイル\n',1)
    readme.write_text(text,encoding='utf-8')
    # Saved-master samples are exported as review evidence, not counted as extra assets.
    candidates=load('batches/gaps-20260914/candidates.json')['records'];wanted={c['assetId'] for c in candidates if c['number'] in [17,85,107,149,152,166,182,190,267,451,561,723]}
    detail=ROOT/'review-detail-gap';detail.mkdir(exist_ok=True);samples=[]
    for r in primary:
        if r['assetId'] not in wanted:continue
        filename=r['targetId']+'--'+r['assetId']+'.jpg'
        shutil.copy2(ROOT/r['files']['master'],detail/filename)
        samples.append({'targetId':r['targetId'],'scientificName':r['scientificName'],'assetId':r['assetId'],'file':filename,'masterSha256':r['sha256']['master'],'sourceMetadata':r['metadataPath'],'credit':r['credit']})
    save('review-detail-gap/index.json',samples)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
