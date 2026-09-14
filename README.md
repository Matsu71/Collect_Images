# Collect Images — 現生生物の実写画像集

**写真本体・出典・商用利用条件・クレジットをまとめた、別のサービスでも再利用するための素材集です。** ChronoEarthの現生生物を起点に収集しています。元のChronoEarthリポジトリや公開サービスは変更していません。

## 収集結果（2026-09-14）

| 項目 | 実績 |
|---|---:|
| 収集対象 | 1,000分類群（ChronoEarth由来532＋追加468） |
| 画像を取得できた分類群 | 990 |
| 主画像・補足として残した素材 | **2,363点、983分類群に対応** |
| 姿・主要な特徴が分かる主画像候補を選べた分類群 | **923** |
| 主画像候補の写真×分類群の対応数 | 1092 |
| 補足用の写真×分類群の対応数 | 1272 |
| 不明瞭・図版・誤対応等で除外した対応数 | 106 |
| 取得画像の一覧確認が未実施の対応数 | 0 |

JPEG・WebP・サムネイルを別の写真として数えていません。同じ写真が複数分類群に対応する場合があるため、実際の素材点数と写真×分類群の対応数を区別しています。

**全1,000分類群の主画像が揃ったという意味ではありません。** 花・葉・頭部などの補足写真だけのものや、採用素材がないものもあります。ChronoEarth由来532分類群では、画像取得は522、主画像候補の選定は468です。[主画像未確保リスト](reports/primary-gaps.json) に不足を記録しています。

最新の集計は [reports/curation-status.json](reports/curation-status.json) を正としてください。取得した候補は全件をコンタクトシートで確認し、代表8点は保存JPEGを個別に確認しました。その追加確認で2点を主画像から補足へ変更しています。これは、全件の原寸・画素単位の画質検査、専門家による種の再同定、第三者のすべての権利の保証ではありません。幼体、特殊な色彩、標本、顕微鏡像、遮蔽などの画像別注記を保持してください。

<!-- GAP-PROGRESS-20260914 -->
## 主画像不足の追加収集（2026-09-14）

主画像が不足する分類群を優先し、727枚の新規候補を画像一覧と出典の説明で確認しました。主画像候補242枚、補足用436枚、除外49枚に分け、採用分678枚の画像本体を保存しています。

主画像候補の確保は **586 → 810分類群**、ChronoEarth由来分は **374 → 427分類群**です。未確保は全体190分類群、ChronoEarth由来105分類群です。数字を増やすために花・葉などの部分写真を全身・樹形の主画像へ昇格させてはいません。

追加分は保存前にライセンスを再確認し、目視したプレビューと保存用写真の元画像SHA-1を照合しました。画像本体・WebP・作者・ライセンス・出典・加工情報を保持しています。検索で別の生物に結び付いた1候補は、画像と出典に明記された学名に基づいて対応先を訂正しました。

追加分の除外候補49枚は `batches/gaps-20260914/` の審査証跡だけに残し、採用フォルダへ追加していません。上の「除外した対応数」は従来の取得済み素材の除外数で、この追加候補の除外とは別です。詳しくは [今回の差分と検証](reports/continuation-result-20260914.json)、[目視判定](reviews/gap-20260914.json)、[保存結果](batches/gaps-20260914/adoption.json) を参照してください。
<!-- /GAP-PROGRESS-20260914 -->

<!-- ROUND2-20260914 -->
## 主画像不足の追加収集・第2回（2026-09-14）

残っていた190分類群に絞って新しい写真を取得し、499候補を審査しました。採用した321枚のJPEG・WebP・サムネイル、出典とライセンス、画像別の判定を保存しました。

主画像候補は **810 → 896分類群**、ChronoEarth由来分は **427 → 458分類群**です。残る主画像不足は全体104分類群、ChronoEarth由来74分類群です。

保存マスターは、目視に使ったダウンロード済みJPEGと完全に同一のバイト列です。元撮影データそのものではなく、縦横比を保って縮小・再圧縮した版であることを記録しています。採用しない候補は審査証跡にだけ保持し、`collection/` の採用一覧には含めません。

[今回の差分](reports/continuation-round2-20260914.json) · [保存・権利情報・リンク検証](reports/round2-validation.json) · [画像ごとの審査記録](reviews/round2-decisions-20260914.json)
<!-- /ROUND2-20260914 -->

<!-- ROUND3-20260914 -->
## 主画像不足の追加収集・第3回（2026-09-14）

今回の開始時点で主画像が未確保だった104分類群を対象に、以前の候補と重複しない新しい写真を取得しました。236候補を目視・出典確認し、163枚を画像本体・WebP・出典・権利情報付きで追加しました。

主画像候補は **896 → 923分類群**、ChronoEarth由来は **458 → 468分類群**です。未確保は全体77分類群、ChronoEarth由来64分類群です。補足用の接写・標本・培養像を、件数のために全体像へ昇格させていません。

保存JPEGは目視に使った画像と同一のバイト列です。元撮影ファイルそのものではなく、縮小・再圧縮した保存版です。全923分類群の主画像と、CC0・CC BYに絞った534分類群の書き出しを検証しました。各写真のライセンス条件、標本・発育段階・顕微鏡像等の注記を保持して使ってください。

[今回の実績](reports/continuation-round3-20260914.json) · [保存と書き出し検証](reports/round3-validation.json) · [目視判定](reviews/round3-decisions-20260914.json)
<!-- /ROUND3-20260914 -->

## 利用するファイル

| 用途 | 入口 |
|---|---|
| 主画像候補を1分類群1枚で取得 | [collection/primary.json](collection/primary.json) |
| 主画像の別候補・補足写真も含む採用一覧 | [collection/assets.json](collection/assets.json) |
| 学名・和名・元サービスIDとの対応 | [collection/taxa.json](collection/taxa.json) |
| 出典・作者・ライセンス・加工内容 | [collection/credits.csv](collection/credits.csv)、[ATTRIBUTION.md](collection/ATTRIBUTION.md) |
| 検索・切り替え可能な写真一覧 | [collection/index.html](collection/index.html) |
| 画像ごとの出典・権利・審査記録 | [collection/metadata/](collection/metadata/) |
| 除外理由 | [collection/excluded.json](collection/excluded.json) |

写真一覧はリポジトリをダウンロード／cloneし、`collection/index.html` をブラウザで開いてください。GitHubのHTMLファイル表示画面では写真一覧アプリとして実行されません。初期表示は1分類群1枚の主画像候補で、補足画像・別候補に切り替えられます。

写真の実体は `images/` と `reference/images/` に保存しています。**これらの生の保存フォルダや従来の `catalog/`・`gallery/` は取得・審査用で、除外した画像も含みます。直接一括採用せず、必ず `collection/` の審査後台帳を使ってください。** 初期取得メタデータの `origin`・`author` 等より、審査後の `collection/metadata/` を優先します。

## 他のサービスへ書き出す

```bash
# 主画像候補をWebP＋サムネイル＋権利メタデータ付きで書き出す
python tools/export_collection.py --output ../species-images

# CC0・CC BYだけに絞る（CC BY-SAを含めない）
python tools/export_collection.py --output ../species-images-by --licenses cc0,cc-by

# ChronoEarth由来の対象だけに絞り、高品質JPEGも含める
python tools/export_collection.py --output ../chronoearth-images --tier chronoearth --include-master

# 補足写真・別候補も含む採用素材を書き出す
python tools/export_collection.py --output ../species-images-all --mode accepted
```

出力先には `catalog.json`、`images/`、`thumbnails/`、`metadata/`、`credits.csv`、`ATTRIBUTION.md` が作成されます。画像パスは出力先基準に書き換えます。既存ファイルのある出力先は上書きせず、未確認・除外画像は書き出しません。コピー前後のハッシュを照合します。[書き出しと一覧リンクの検証結果](reports/export-validation.json) を保存しています。

## 商用利用条件とクレジット

対象は画像ごとに明示された **CC0・CC BY・CC BY-SA** です。非商用限定（NC）、改変禁止（ND）、All rights reserved、権利不明の素材は採用しません。観察データのライセンスと写真自体のライセンスを混同しません。

CC BYでは適切なクレジット・出典・ライセンスへのリンク・必要な加工情報を保持します。CC BY-SAでは、それらに加えて改変写真の配布時に適切な同一／互換ライセンス条件等が必要です。2.0・2.5・3.0・4.0等のバージョンが混在するため、画像別の `licenseUrl` を確認してください。リポジトリ全体で写真を一律に再許諾しているわけではありません。

CC0も追跡のため出典を保持します。**一部のCC0写真はAPIから作者名が得られていないため「作者名未取得（CC0・出典参照）」と明示しています。** `no rights reserved` などの権利表記を作者の名前として扱いません。CC0以外の帰属表示が必要な写真では、出典に提示された作者名を保持します。作者名は出典からの転載であり、本人確認や権利帰属の独立検証ではありません。

権利元の申告を確認した記録であり、人物・商標・撮影場所などの別の権利まで保証するものではありません。

公式条件: [CC0](https://creativecommons.org/publicdomain/zero/1.0/) / [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) / [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

詳しい基準は [再利用・品質方針](docs/REUSE_POLICY.ja.md) を参照してください。

## 保存形式・追跡情報

保存JPEGは長辺最大2,048px、配信WebPは長辺最大1,400pxです。JPEGも元ファイルそのものではなく、方向補正・縦横比を保った縮小・再圧縮を行った保存版です。切り抜きや生成AIによる補完・描き換えはしていません。

元画像URL、出典ページ、出典で提供された作者・帰属表記、画像ライセンス、取得日時、加工内容、寸法、ファイルサイズ、ハッシュ、出典APIの証拠メタデータを保持します。

## 収集・審査の再開

`data/targets.json` は元サービスとの対応表です。取り込み時に公開カタログとGitHub内データの一致をハッシュで確認しています。

`scripts/collect.py` は初期対象・追加分類群の取得、`curation/collect_reference.py` は別構図の候補取得を担当します。画像取得と目視判定は別工程です。`reviews/screening-*.json` は固定コミットの画像一覧に対する実際の判定、`reports/detail-sample-review.json` は保存JPEGの個別確認記録です。

審査後の台帳は `python curation/run_reviewed_build.py` で作成します。内部の `build_collection.py` に加え、個別確認の修正と作者欄の正規化を適用します。GitHub Actionsからの実行では、出力画像・台帳・クレジット・書き出し処理まで検証します。時刻ベースの定期実行は設定していません。
