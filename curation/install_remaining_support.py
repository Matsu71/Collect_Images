#!/usr/bin/env python3
"""Install idempotent compatibility changes for the final remaining-image collection.

A public-domain marker is not a licence grant. Every such image is accepted only
when its separate source-specific rights evidence passes the validator.
"""
from __future__ import annotations
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def replace_once(path,old,new):
    p=ROOT/path;text=p.read_text(encoding='utf-8')
    if new in text:return
    if text.count(old)!=1:raise ValueError(f'Unexpected source structure; refusing blind edit: {path}: {old[:80]}')
    p.write_text(text.replace(old,new,1),encoding='utf-8')

def install():
    replace_once('curation/build_collection.py',"ALLOWED={'cc0','cc-by','cc-by-sa'}","ALLOWED={'cc0','cc-by','cc-by-sa','public-domain'}")
    replace_once('curation/build_collection.py','def verify_record(rec):\n',"def verify_record(rec):\n    if rec.get('licenseCode')=='public-domain':\n        import remaining_closure\n        remaining_closure.verify_public_domain(rec)\n        return\n")
    replace_once('curation/build_collection.py',"{'cc0':0,'cc-by':1,'cc-by-sa':2}","{'cc0':0,'public-domain':0,'cc-by':1,'cc-by-sa':2}")
    replace_once('curation/build_collection.py',"        r['credit']=f\"{r.get('imageTitle',r['scientificName'])}","        if r['licenseCode']=='public-domain':\n            r['licenseName']='Public domain (source-specific basis)'\n        r['credit']=f\"{r.get('imageTitle',r['scientificName'])}")
    replace_once('curation/run_reviewed_build.py','import targeted_review_loader\n','import targeted_review_loader\nimport remaining_review_integration\n')
    replace_once('curation/run_reviewed_build.py','def verify_record(record):\n',"def verify_record(record):\n    if record.get('licenseCode')=='public-domain':\n        import remaining_closure\n        remaining_closure.verify_public_domain(record)\n        record['authorStatus']='source_supplied_not_independently_verified'\n        return\n")
    replace_once('curation/run_reviewed_build.py','    targeted_review_loader.apply(ROOT,decisions,evidence)\n','    targeted_review_loader.apply(ROOT,decisions,evidence)\n    remaining_review_integration.apply(ROOT,decisions,evidence)\n')
    replace_once('tools/export_collection.py',"ALLOWED={'cc0','cc-by','cc-by-sa'}","ALLOWED={'cc0','cc-by','cc-by-sa','public-domain'}")
    replace_once('tools/export_collection.py',"default='cc0,cc-by,cc-by-sa'","default='cc0,cc-by,cc-by-sa,public-domain'")
    replace_once('tools/build_export_gallery.py','<option value="cc-by-sa">CC BY-SA</option>','<option value="cc-by-sa">CC BY-SA</option><option value="public-domain">Public domain</option>')
    policy=ROOT/'docs/REMAINING_SEARCH_COMPLETION.ja.md'
    policy.parent.mkdir(exist_ok=True)
    policy.write_text('''# 未確保画像の最終検索・採用基準

今回の対象は、既存1,000分類群のうち主画像が不足していた76分類群です。全対象を確認し、採用できる画像は保存し、条件を満たす画像を確認できなかった対象は検索記録と理由を残します。将来も画像が存在しないとの断定ではありません。

## 商用再利用の根拠

CC0、CC BY、CC BY-SAに加え、個々のファイルに明示された著作権放棄又は米国政府著作物の根拠を確認したpublic-domain画像を区別して収録します。Public Domain Markはライセンス付与ではありません。表示サイトが政府機関というだけでは採用せず、画像ページ、撮影者・機関、出典、明示された個別の根拠と確認日時を保存します。著作権以外の権利や全法域での状態を一律に保証しません。

第三者の写真、カナダ政府等の著作物、2022年の写真を著作権満了とする矛盾した表示などは、別途根拠が確認できない限りpublic-domainとして扱いません。作者欄が空でも説明欄に撮影機関が明記されている場合は、その原文と場所を残して帰属を補います。サイト名から作者を推測しません。

## 画質と顕微鏡像

元から小さい科学写真は、細胞・殻・体の主要な特徴を実際に確認できた場合のみ、原寸・低解像度であることを明記して採用します。AIによる拡大生成や解剖学的な描き足しは行いません。切片、固定試料、染色、疑似色、培養状態、幼体、標本、宿主と共生体等を区別します。

複数種の図版から一種の実写パネルを切り出す場合は、元画像とそのハッシュ、切り出し座標、対応するラベル・尺度、加工記録を保持します。切り出した部分は新しい撮影画像ではないため、撮影画像数と加工ファイル数を分けます。

## 完了の意味

全対象について画像取得・出典確認・目視選別を実施したことを、全画像が揃ったことと区別します。主画像を確保できない対象に補足画像を黙って割り当てたり、権利不明の素材を採用したりしません。`reports/remaining-closure-outcomes.json`に対象別の最終判断を、`reports/remaining-closure-summary.json`に実画像に基づく集計を残します。
''',encoding='utf-8')
    agents=ROOT/'AGENTS.md';text=agents.read_text(encoding='utf-8');marker='## 未確保画像の最終検索で追加した条件'
    if marker not in text:
        text+='\n\n'+marker+'\n\n詳細は `docs/REMAINING_SEARCH_COMPLETION.ja.md` と対象別の最終結果を参照する。個別の根拠を確認したpublic-domain画像も採用できるが、政府サイトというだけで権利状態を決めない。低解像度科学写真は原寸と限界を明記する。確保できない対象は理由付きで検索完了として扱い、無条件に再試行や自動生成で埋めない。\n'
        agents.write_text(text,encoding='utf-8')

if __name__=='__main__':install()
