#!/usr/bin/env python3
"""Create a standalone, attribution-complete HTML gallery in an exported photo package."""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path)
    args=parser.parse_args();root=args.package.resolve()
    manifest=root/'catalog.json'
    if not manifest.is_file():parser.error('An existing exported package containing catalog.json is required')
    data=json.loads(manifest.read_text(encoding='utf-8'));cards=[]
    escape=lambda value:html.escape(str(value or ''),quote=True)
    for record in data['records']:
        if record.get('status') not in ('primary_candidate','supplementary_only'):
            raise ValueError('The portable gallery must not include unreviewed or rejected images')
        for relative in [record['files']['web'],record['files']['thumbnail'],record['metadataPath']]:
            path=(root/relative).resolve()
            if not path.is_relative_to(root) or not path.is_file():raise ValueError('Missing or out-of-package asset')
        name=record.get('nameJa') or record.get('commonNameSource') or record['scientificName']
        note=(record.get('visualReview') or {}).get('noteJa','')
        cards.append(f'''<article data-license="{escape(record['licenseCode'])}">
<a class="image" href="{escape(record['files']['web'])}"><img loading="lazy" decoding="async" src="{escape(record['files']['thumbnail'])}" alt="{escape(name)}"></a>
<h2>{escape(name)}</h2><p class="scientific"><i>{escape(record['scientificName'])}</i></p>
<p class="credit">{escape(record['author'])} · <a href="{escape(record['photoUrl'])}">{escape(record['source'])}</a> · <a href="{escape(record['licenseUrl'])}">{escape(record['licenseName'])}</a></p>
<p>{escape(note)}</p><p class="small">縮小・再圧縮あり。被写体の生成・描き換えはしていません。</p>
<details><summary>出典・加工・利用条件</summary><p>{escape(record['credit'])}</p><p><a href="{escape(record['metadataPath'])}">画像別メタデータ</a></p></details></article>''')
    page='''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>現生生物の写真コレクション</title><style>
*{box-sizing:border-box}body{margin:0;background:#f6f7f8;color:#20262e;font:15px/1.6 system-ui,sans-serif}header,main,footer{max-width:1500px;margin:auto;padding:24px}header{padding-bottom:8px}h1{font-size:28px;margin:0 0 8px}header p{max-width:1050px;margin:8px 0}.controls{display:flex;gap:12px;flex-wrap:wrap;margin-top:18px}label{display:block;font-size:13px}input,select{display:block;font:inherit;padding:10px;border:1px solid #adb8c2;border-radius:6px;background:white}input{width:min(550px,85vw)}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:20px;padding-top:8px}article{background:#fff;border:1px solid #d9dee3;border-radius:10px;padding:16px;overflow:hidden}article[hidden]{display:none}.image{display:flex;align-items:center;justify-content:center;height:245px;background:#fbfcfd}img{max-width:100%;max-height:235px;object-fit:contain}h2{font-size:18px;margin:12px 0 0}.scientific{margin:0 0 12px;color:#4b5560}article p{font-size:13px}.credit,.small,summary{font-size:12px}a{color:#175783}details p{overflow-wrap:anywhere}footer{font-size:13px}#count{font-variant-numeric:tabular-nums}</style></head><body>
<header><h1>現生生物の写真コレクション</h1><p>画像・出典・利用条件を一緒に保存した、持ち出し用の素材集です。画像を押すと配信用の大きな写真を開きます。</p>
<p>主画像は姿や主要な特徴の分かる候補です。専門的な種の再同定や全件の画素単位の画質保証ではありません。標本・顕微鏡像・幼体などは画像別の注記を保持して使ってください。</p>
<div class="controls"><label>生物名・学名・作者を検索<input id="q" type="search" placeholder="検索語を入力"></label><label>ライセンス<select id="license"><option value="all">すべて</option><option value="cc0">CC0</option><option value="cc-by">CC BY</option><option value="cc-by-sa">CC BY-SA</option></select></label></div><p id="count" aria-live="polite"></p></header><main>'''+''.join(cards)+'''</main>
<footer><p>写真ごとに異なるライセンスが適用されます。CC BY・CC BY-SAでは作者・出典・ライセンスリンク・加工情報を保持してください。CC BY-SAの改変写真を配布する場合は、該当ライセンスの継承条件も確認してください。人物等の別の権利まで保証するものではありません。</p><p><a href="catalog.json">素材一覧JSON</a> · <a href="credits.csv">クレジットCSV</a> · <a href="ATTRIBUTION.md">クレジット全文</a> · <a href="README.md">利用方法</a></p></footer>
<script>function filter(){const q=document.getElementById('q').value.trim().toLowerCase(),license=document.getElementById('license').value;let n=0;document.querySelectorAll('article').forEach(e=>{e.hidden=!((license==='all'||e.dataset.license===license)&&e.textContent.toLowerCase().includes(q));if(!e.hidden)n++});document.getElementById('count').textContent=n+'枚を表示';}document.getElementById('q').addEventListener('input',filter);document.getElementById('license').addEventListener('change',filter);filter();</script></body></html>'''
    (root/'index.html').write_text(page,encoding='utf-8')
    print(json.dumps({'gallery':str(root/'index.html'),'photoCount':len(cards),'localImagesAndMetadata':'verified'},ensure_ascii=False))

if __name__=='__main__':main()
