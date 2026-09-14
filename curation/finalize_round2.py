#!/usr/bin/env python3
"""Validate actual saved round-2 photos and update public collection totals."""
from __future__ import annotations
import hashlib, json, re, subprocess, sys
from pathlib import Path
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[1]

def load(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def save(p,v):(ROOT/p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def check_license_policy():
    import round2_photos as r
    for url in ['https://creativecommons.org/licenses/by/4.0/','https://creativecommons.org/licenses/by-sa/3.0/','https://creativecommons.org/publicdomain/zero/1.0/']:
        assert r.LIC.fullmatch(url),url
    for url in ['https://creativecommons.org/licenses/by-nc/4.0/','https://creativecommons.org/licenses/by-nd/4.0/','https://creativecommons.org/licenses/by-nc-sa/4.0/','https://example.com/licenses/by/4.0/']:
        assert not r.LIC.fullmatch(url),url

def main():
    check_license_policy();status=load('reports/curation-status.json');progress=load('reports/continuation-round2-20260914.json')
    records=load('collection/assets.json')['records'];primary=load('collection/primary.json')['records'];taxa=load('collection/taxa.json')['records']
    assert len(taxa)==status['targetCount']==1000
    assert len(primary)==len({r['targetId'] for r in primary})==status['primaryReadyTaxa']
    assert status['primaryReadyTaxa']>=progress['before']['primaryReadyTaxa']
    assert not progress['failures']
    reviewed=load('reviews/round2-decisions-20260914.json')
    adopted=load('batches/gaps-round2-20260914/adoption.json')
    expected=set(reviewed['primaryNumbers'])|set(reviewed['supplementaryNumbers'])
    assert {r['number'] for r in adopted['saved']}==expected
    invalid=[]
    for item in adopted['saved']:
        rec=load(item['metadataPath']);data=(ROOT/rec['files']['master']).read_bytes()
        assert hashlib.sha256(data).hexdigest()==rec['previewSha256']==rec['sha256']['master']
        assert rec['licenseCode'] in ('cc0','cc-by','cc-by-sa')
        if not rec.get('author') or not rec.get('photoUrl') or not rec.get('licenseUrl'):invalid.append(item)
    assert not invalid
    links=[]
    class Parser(HTMLParser):
        def handle_starttag(self,tag,attrs):
            d=dict(attrs)
            for k in ('href','src'):
                v=d.get(k,'')
                if v and not v.startswith(('http:','https:','#','data:')):links.append(v)
    Parser().feed((ROOT/'collection/index.html').read_text(encoding='utf-8'))
    missing=[v for v in links if not (ROOT/'collection'/v).resolve().is_file()]
    assert not missing,missing[:5]
    verification={'generatedAt':status['generatedAt'],'round2SavedMastersChecked':len(adopted['saved']),'exactReviewedBytes':'pass','licenseAllowlistPositiveAndNegativeTests':'pass','creditsPresent':'pass','galleryLocalLinksChecked':len(links),'galleryMissingAssets':missing,'primaryCountAndDistinctTargets':'pass','originalTargetListPreserved':'pass'}
    save('reports/round2-validation.json',verification)
    readme=ROOT/'README.md';text=readme.read_text(encoding='utf-8')
    replacements={'画像を取得できた分類群':str(status['downloadedTargetCoverage']),'主画像・補足として残した素材':f"**{status['acceptedPhotographs']:,}点、{status['acceptedTaxonCoverage']:,}分類群に対応**",'姿・主要な特徴が分かる主画像候補を選べた分類群':f"**{status['primaryReadyTaxa']}**",'主画像候補の写真×分類群の対応数':str(status['primaryCandidatePhotoPairs']),'補足用の写真×分類群の対応数':str(status['supplementaryPhotoPairs']),'不明瞭・図版・誤対応等で除外した対応数':str(status['excludedPhotoPairs']),'取得画像の一覧確認が未実施の対応数':str(status['pendingReviewPhotoPairs'])}
    for label,value in replacements.items():
        text,n=re.subn(r'^\| '+re.escape(label)+r' \|.*\|$',f'| {label} | {value} |',text,flags=re.M)
        if n!=1:raise ValueError('README schema changed; refusing blind update: '+label)
    text,n=re.subn(r'ChronoEarth由来532分類群では、画像取得は\d+、主画像候補の選定は\d+です。',f"ChronoEarth由来532分類群では、画像取得は{status['chronoearthDownloadedCoverage']}、主画像候補の選定は{status['chronoearthPrimaryReadyTaxa']}です。",text)
    if n!=1:raise ValueError('README source-coverage paragraph changed')
    start='<!-- ROUND2-20260914 -->';end='<!-- /ROUND2-20260914 -->'
    block=f'''{start}
## 主画像不足の追加収集・第2回（2026-09-14）

残っていた190分類群に絞って新しい写真を取得し、{progress['reviewedCandidates']}候補を審査しました。採用した{progress['newPhotoFiles']}枚のJPEG・WebP・サムネイル、出典とライセンス、画像別の判定を保存しました。

主画像候補は **{progress['before']['primaryReadyTaxa']} → {status['primaryReadyTaxa']}分類群**、ChronoEarth由来分は **{progress['before']['chronoearthPrimaryReadyTaxa']} → {status['chronoearthPrimaryReadyTaxa']}分類群**です。残る主画像不足は全体{progress['primaryGapsRemaining']}分類群、ChronoEarth由来{progress['chronoearthPrimaryGapsRemaining']}分類群です。

保存マスターは、目視に使ったダウンロード済みJPEGと完全に同一のバイト列です。元撮影データそのものではなく、縦横比を保って縮小・再圧縮した版であることを記録しています。採用しない候補は審査証跡にだけ保持し、`collection/` の採用一覧には含めません。

[今回の差分](reports/continuation-round2-20260914.json) · [保存・権利情報・リンク検証](reports/round2-validation.json) · [画像ごとの審査記録](reviews/round2-decisions-20260914.json)
{end}
'''
    if start in text:text=re.sub(re.escape(start)+r'.*?'+re.escape(end)+'\n?',lambda _:block,text,flags=re.S)
    else:text=text.replace('## 利用するファイル\n',block+'\n## 利用するファイル\n',1)
    readme.write_text(text,encoding='utf-8')
    print(json.dumps({'progress':progress,'verification':verification},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
