"""Apply actual final image decisions and narrowly scoped source-rights holds."""
from __future__ import annotations
import json
from pathlib import Path
import remaining_closure
import remaining_targeted

RIGHTS_CONFLICT_DOI='10.5598/imafungus.2011.02.01.12'
RIGHTS_CONFLICT_URL='https://link.springer.com/article/10.5598/imafungus.2011.02.01.12'

def apply(root: Path, decisions: dict, evidence: list) -> None:
    remaining_closure.apply_decisions(decisions,evidence)
    remaining_targeted.apply_decisions(decisions,evidence)
    # Panel crops, when present, carry their own explicitly reviewed coordinates,
    # full-source hash and resulting master hash. Never infer approval from cropping.
    panel_review=root/'reviews/remaining-panels-20260914.json'
    if panel_review.exists():
        import remaining_panels
        remaining_panels.apply_decisions(root,decisions,evidence)
    holds=[]
    for folder in ('metadata','reference/metadata'):
        for path in (root/folder).glob('*/*.json'):
            record=json.loads(path.read_text(encoding='utf-8'))
            source=record.get('originalAttribution','')+' '+str((record.get('imageInfoEvidence') or {}).get('extmetadata',{}).get('Credit',{}).get('value',''))
            if RIGHTS_CONFLICT_DOI not in source:continue
            key=record['targetId']+'|'+record['assetId']
            previous=decisions.get(key,{})
            reason='原典の権利欄の本文はCC BYと記す一方、リンク先はCC BY-NC 4.0です。CommonsのCC BY-SA表示とも一致せず、商用再利用の根拠が確定するまで採用一覧から除外します。元の写真と以前の判定は削除せず保持します。'
            decisions[key]={**previous,'status':'screened','recommendedRole':'exclude','reviewer':'ChatGPT source-rights verification','reviewedAt':'2026-09-14','method':'source_licence_conflict_hold_not_visual_failure','reviewFile':'docs/REMAINING_SEARCH_COMPLETION.ja.md','noteJa':reason,'sourceRightsConflict':{'publisherPage':RIGHTS_CONFLICT_URL,'publisherLinkedLicence':'https://creativecommons.org/licenses/by-nc/4.0/','sourceClaimedLicence':record.get('licenseUrl'),'status':'unresolved_do_not_use_commercially'}}
            holds.append({'targetId':record['targetId'],'assetId':record['assetId'],'metadataPath':str(path.relative_to(root)),'reasonJa':reason,'publisherPage':RIGHTS_CONFLICT_URL})
    output=root/'reports/remaining-source-rights-holds.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({'checkedOn':'2026-09-14','holds':holds,'count':len({(r['targetId'],r['assetId']) for r in holds}),'note':'Only the specific conflicting original article is held. This is not a judgement about other photographs or a claim that the article was definitively relicensed.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    evidence.append({'file':'reports/remaining-source-rights-holds.json','count':len(holds),'kind':'specific_original_article_rights_conflict_not_image_quality_reclassification'})
