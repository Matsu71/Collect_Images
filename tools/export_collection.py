#!/usr/bin/env python3
"""Export reviewed photographs with their attribution; never export pending/rejected items.

Examples:
  python tools/export_collection.py --output ../species-images
  python tools/export_collection.py --output ../species-images --licenses cc0,cc-by
  python tools/export_collection.py --output ../chronoearth-images --tier chronoearth
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re, shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ALLOWED={'cc0','cc-by','cc-by-sa'}

def checked_source(relative: str) -> Path:
    p=(ROOT/relative).resolve()
    if not p.is_relative_to(ROOT) or not p.is_file():
        raise ValueError(f'Invalid or missing source file: {relative}')
    return p

def copy_checked(relative: str, output: Path, expected_hash: str|None=None) -> str:
    source=checked_source(relative)
    if expected_hash and hashlib.sha256(source.read_bytes()).hexdigest()!=expected_hash:
        raise ValueError(f'Checksum mismatch: {relative}')
    output.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,output)
    return hashlib.sha256(output.read_bytes()).hexdigest()

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--output',type=Path,required=True,help='New or empty destination directory.')
    p.add_argument('--licenses',default='cc0,cc-by,cc-by-sa',help='Comma-separated license codes.')
    p.add_argument('--tier',choices=['all','chronoearth','extension'],default='all')
    p.add_argument('--mode',choices=['primary','accepted'],default='primary',help='Primary: one selected photo per taxon; accepted: primary alternatives and supplements too.')
    p.add_argument('--include-master',action='store_true',help='Also copy the high-quality JPEG master.')
    a=p.parse_args();licenses={x.strip().lower() for x in a.licenses.split(',') if x.strip()}
    if not licenses or not licenses<=ALLOWED:p.error('Use only cc0, cc-by, cc-by-sa.')
    out=a.output.expanduser().resolve()
    protected=[ROOT/part for part in ['.git','collection','images','metadata','reference','catalog','data','gallery','reports','reviews','scripts','tools','curation','.github']]
    if out==ROOT or any(out.is_relative_to(x) for x in protected):p.error('Choose a new export directory, not an existing source/collection directory.')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):p.error('Output must be a new or empty directory; existing files are never overwritten.')
    manifest=ROOT/'collection'/('primary.json' if a.mode=='primary' else 'assets.json')
    if not manifest.is_file():p.error('Run the reviewed-collection builder before exporting.')
    candidates=json.loads(manifest.read_text(encoding='utf-8'))['records']
    records=[r for r in candidates if r['licenseCode'] in licenses and (a.tier=='all' or r.get('collectionTier')==a.tier)]
    if not records:p.error('No reviewed photographs match these filters.')
    out.mkdir(parents=True,exist_ok=True);exported=[]
    for r in records:
        if r.get('status') not in {'primary_candidate','supplementary_only'}:raise ValueError('Unreviewed item in export manifest')
        stem=re.sub(r'[^a-z0-9-]+','-',r['scientificName'].lower()).strip('-')+'--'+r['assetId']
        rec=dict(r);rec['sourceRepositoryMetadata']=r['metadataPath'];rec['sourceStoredFiles']=r['files'];rec['files']={};rec['exportedSha256']={}
        for kind,subdir,extension in [('web','images','.webp'),('thumbnail','thumbnails','.webp')]+([('master','masters','.jpg')] if a.include_master else []):
            rel=f'{subdir}/{stem}{extension}'
            digest=copy_checked(r['files'][kind],out/rel,(r.get('sha256') or {}).get(kind))
            rec['files'][kind]=rel;rec['exportedSha256'][kind]=digest
        original_metadata=json.loads(checked_source(r['metadataPath']).read_text(encoding='utf-8'))
        original_metadata.update(rec);rec['metadataPath']=f'metadata/{stem}.json';original_metadata['metadataPath']=rec['metadataPath']
        mp=out/rec['metadataPath'];mp.parent.mkdir(exist_ok=True);mp.write_text(json.dumps(original_metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        exported.append(rec)
    info={'schemaVersion':1,'exportedAt':datetime.now(timezone.utc).isoformat(timespec='seconds'),'sourceRepository':'https://github.com/Matsu71/Collect_Images','mode':a.mode,'tier':a.tier,'licenseFilter':sorted(licenses),'photoCount':len(exported),'taxonCount':len({r['targetId'] for r in exported}),'records':exported}
    (out/'catalog.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    fields=['scientificName','nameJa','assetId','status','author','source','photoUrl','licenseName','licenseUrl','credit']
    with (out/'credits.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(exported)
    (out/'ATTRIBUTION.md').write_text('# Photograph attribution\n\n'+'\n\n'.join(r['credit'] for r in exported)+'\n',encoding='utf-8')
    (out/'README.md').write_text('# 現生生物写真の再利用パッケージ\n\n写真・クレジット・個別の出典メタデータを一緒に保存しています。写真ごとにライセンスが異なります。作者、出典、ライセンスへのリンク、加工内容を保持して利用してください。CC BY-SA 写真の改変・配布時は当該ライセンス条件を確認してください。\n\n主画像候補は一覧での構図確認を経た候補であり、原寸での精密画質確認、専門的な再同定、すべての権利の保証ではありません。補足画像を含めた場合は、部分像・標本・幼体・顕微鏡像等を各メタデータの review/context 欄に従って区別してください。\n\n`catalog.json` のパスは、このフォルダからの相対パスです。`credits.csv` と `ATTRIBUTION.md` は出典表示に利用できます。\n',encoding='utf-8')
    print(json.dumps({'output':str(out),'photos':info['photoCount'],'taxa':info['taxonCount'],'licenses':sorted(licenses),'fileCopyAndHashes':'pass'},ensure_ascii=False))

if __name__=='__main__':main()
