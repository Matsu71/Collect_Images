#!/usr/bin/env python3
"""Report saved round-3 results and validate real export files, not just collection plans."""
from __future__ import annotations
import hashlib,json,os,re,shutil,subprocess,sys
from pathlib import Path
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[1]
def load(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def save(p,v):
    f=ROOT/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    import round3_photos as module
    status=load('reports/curation-status.json');result=load('reports/continuation-round3-20260914.json');adoption=load(module.BATCH+'/adoption.json')
    spec,cs,roles=module.review_data();wanted={n for n,r in roles.items() if r!='exclude'}
    assert {r['number'] for r in adoption['saved']}==wanted
    assert not adoption['failures']
    for item in adoption['saved']:
        r=load(item['metadataPath']);b=(ROOT/r['files']['master']).read_bytes()
        assert hashlib.sha256(b).hexdigest()==r['sha256']['master']==cs[item['number']]['previewSha256']
        assert r['licenseCode'] in ('cc0','cc-by','cc-by-sa') and module.LIC.fullmatch(r['licenseUrl'])
        assert r['author'] and r['photoUrl']
    for code in ('by-nc','by-nd','by-nc-sa','by-nc-nd'):
        assert not module.LIC.fullmatch('https://creativecommons.org/licenses/'+code+'/4.0/')
    primary=load('collection/primary.json')['records'];taxa=load('collection/taxa.json')['records']
    assert len(primary)==len({r['targetId'] for r in primary})==status['primaryReadyTaxa']
    assert len(taxa)==status['targetCount']==1000
    assert status['primaryReadyTaxa']>=result['before']['primaryReadyTaxa']
    links=[]
    class Parser(HTMLParser):
        def handle_starttag(self,tag,attrs):
            for k,v in attrs:
                if k in ('src','href') and v and not v.startswith(('http:','https:','#','data:')):links.append(v)
    Parser().feed((ROOT/'collection/index.html').read_text(encoding='utf-8'))
    missing=[v for v in links if not (ROOT/'collection'/v).resolve().is_file()]
    assert not missing,missing[:10]
    exports={};temp=Path(os.environ.get('RUNNER_TEMP','/tmp'))
    for name,extra in [('allLicensePrimaryExport',[]),('cc0AndByPrimaryExport',['--licenses','cc0,cc-by'])]:
        dest=temp/('round3-validated-'+name)
        if dest.exists():shutil.rmtree(dest)
        run=subprocess.run([sys.executable,str(ROOT/'tools/export_collection.py'),'--output',str(dest),*extra],cwd=ROOT,text=True,capture_output=True,check=True)
        exports[name]=json.loads(run.stdout)
    verify={'validatedAt':status['generatedAt'],'round3NewMastersChecked':len(wanted),'masterEqualsVisuallyReviewedJPEG':'pass','licenseWhitelistAndNegativeNCNDTests':'pass','authorSourceAndLicenseFields':'pass','primaryTargetUniqueness':'pass','targetListPreserved':'pass','galleryLocalLinksChecked':len(links),'galleryMissingAssets':missing,'exportCopyAndHashes':'pass',**exports}
    save('reports/round3-validation.json',verify);save('reports/export-validation.json',verify)
    result['portablePrimaryExportValidated']=exports['allLicensePrimaryExport']['photos'];result['cc0AndByPrimaryExportValidated']=exports['cc0AndByPrimaryExport']['photos'];save('reports/continuation-round3-20260914.json',result)
    f=ROOT/'README.md';text=f.read_text(encoding='utf-8')
    values={'画像を取得できた分類群':str(status['downloadedTargetCoverage']),'主画像・補足として残した素材':f"**{status['acceptedPhotographs']:,}点、{status['acceptedTaxonCoverage']:,}分類群に対応**",'姿・主要な特徴が分かる主画像候補を選べた分類群':f"**{status['primaryReadyTaxa']}**",'主画像候補の写真×分類群の対応数':str(status['primaryCandidatePhotoPairs']),'補足用の写真×分類群の対応数':str(status['supplementaryPhotoPairs']),'不明瞭・図版・誤対応等で除外した対応数':str(status['excludedPhotoPairs']),'取得画像の一覧確認が未実施の対応数':str(status['pendingReviewPhotoPairs'])}
    for label,value in values.items():
        text,n=re.subn(r'^\| '+re.escape(label)+r' \|.*\|$',f'| {label} | {value} |',text,flags=re.M)
        if n!=1:raise ValueError('README table changed: '+label)
    text,n=re.subn(r'ChronoEarth由来532分類群では、画像取得は\d+、主画像候補の選定は\d+です。',f"ChronoEarth由来532分類群では、画像取得は{status['chronoearthDownloadedCoverage']}、主画像候補の選定は{status['chronoearthPrimaryReadyTaxa']}です。",text)
    if n!=1:raise ValueError('README coverage sentence changed')
    start='<!-- ROUND3-20260914 -->';end='<!-- /ROUND3-20260914 -->'
    block=f'''{start}
## 主画像不足の追加収集・第3回（2026-09-14）

今回の開始時点で主画像が未確保だった104分類群を対象に、以前の候補と重複しない新しい写真を取得しました。{result['reviewedCandidates']}候補を目視・出典確認し、{result['newSavedPhotoCount']}枚を画像本体・WebP・出典・権利情報付きで追加しました。

主画像候補は **{result['before']['primaryReadyTaxa']} → {status['primaryReadyTaxa']}分類群**、ChronoEarth由来は **{result['before']['chronoearthPrimaryReadyTaxa']} → {status['chronoearthPrimaryReadyTaxa']}分類群**です。未確保は全体{result['primaryGapsRemaining']}分類群、ChronoEarth由来{result['chronoearthPrimaryGapsRemaining']}分類群です。補足用の接写・標本・培養像を、件数のために全体像へ昇格させていません。

保存JPEGは目視に使った画像と同一のバイト列です。元撮影ファイルそのものではなく、縮小・再圧縮した保存版です。全{status['primaryReadyTaxa']}分類群の主画像と、CC0・CC BYに絞った{result['cc0AndByPrimaryExportValidated']}分類群の書き出しを検証しました。各写真のライセンス条件、標本・発育段階・顕微鏡像等の注記を保持して使ってください。

[今回の実績](reports/continuation-round3-20260914.json) · [保存と書き出し検証](reports/round3-validation.json) · [目視判定](reviews/round3-decisions-20260914.json)
{end}
'''
    if start in text:text=re.sub(re.escape(start)+r'.*?'+re.escape(end)+'\n?',lambda _:block,text,flags=re.S)
    else:text=text.replace('## 利用するファイル\n',block+'\n## 利用するファイル\n',1)
    f.write_text(text,encoding='utf-8')
    print(json.dumps({'result':result,'validation':verify},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
