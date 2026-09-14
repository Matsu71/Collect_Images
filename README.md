# Collect Images — 現生生物の実写画像集

**写真本体・作者・出典・商用利用条件を一緒に保存した、サービス横断で再利用するための素材集です。** ChronoEarth の現生生物を起点に、動物・植物などを追加しています。ChronoEarth の元リポジトリや公開サービスは変更していません。

## 収集結果（2026-09-14）

| 項目 | 実績 |
|---|---:|
| 収集対象 | 1,000分類群（ChronoEarth由来532＋追加468） |
| 画像を取得できた分類群 | 986 |
| 主画像・補足画像として残した素材 | **1,201点、923分類群に対応** |
| 姿・主要な特徴が分かる主画像候補を選べた分類群 | **588** |
| 主画像候補の写真と分類群の対応数 | 732 |
| 補足用の写真と分類群の対応数 | 470 |
| 不明瞭・図版・誤対応等で除外した対応数 | 106 |
| 取得画像の一覧確認が未実施の対応数 | 0 |

同じ写真が複数分類群の補足になる場合は、素材の実枚数と「写真×分類群」の対応数を区別しています。JPEG・WebP・サムネイルを別の写真として水増ししていません。

**全1,000分類群の主画像が揃ったという意味ではありません。** 主画像がない分類群には、花・葉・頭部だけ等の補足写真のみのものや、採用素材がないものもあります。ChronoEarth由来の532分類群では、画像取得は518、主画像候補の選定は376です。残りの不足は [主画像未確保リスト](reports/primary-gaps.json) に記録しています。

最新の集計は [reports/curation-status.json](reports/curation-status.json) を正としてください。構図・実写性・明瞭性の確認はコンタクトシートによるスクリーニングで、原寸での全件画質検査、専門家による種の再同定、すべての第三者権利の保証ではありません。幼体、特殊な色彩、標本、顕微鏡像などは各画像の注記を保持してください。

## 利用するファイル

| 用途 | 入口 |
|---|---|
| 主画像候補を1分類群1枚で取得 | [collection/primary.json](collection/primary.json) |
| 主画像の別候補・補足写真も含む採用一覧 | [collection/assets.json](collection/assets.json) |
| 学名・和名・元サービスIDとの対応 | [collection/taxa.json](collection/taxa.json) |
| 作者・出典・ライセンス・加工内容 | [collection/credits.csv](collection/credits.csv)、[ATTRIBUTION.md](collection/ATTRIBUTION.md) |
| 検索・切り替え可能な写真一覧 | [collection/index.html](collection/index.html) |
| 画像ごとの出典・権利・選定記録 | [collection/metadata/](collection/metadata/) |
| 除外理由 | [collection/excluded.json](collection/excluded.json) |

`collection/index.html` はリポジトリをダウンロード／cloneした後にブラウザで開いてください。GitHubのファイル表示画面は、このHTMLを写真一覧アプリとして実行する画面ではありません。初期表示は1分類群1枚の主画像候補で、補足画像・別候補に切り替えられます。

写真は `images/` と `reference/images/` に実体を保存し、上記の採用台帳から参照します。**これらの保存フォルダや従来の `catalog/`・`gallery/` は取得候補の保管・審査用であり、除外したものも含みます。直接一括採用せず、必ず `collection/` の審査済み台帳を使ってください。** 初期取得メタデータの `origin` 等よりも、`collection/metadata/` の審査後の `status`・`visualReview` を優先します。

## 他のサービスへ持ち出す

主画像候補と必要なクレジットをまとめて新しいフォルダへ書き出せます。既存ファイルのある出力先は上書きしません。

```bash
# 主画像候補をWebP＋サムネイル＋権利メタデータ付きで書き出す
python tools/export_collection.py --output ../species-images

# CC0・CC BYだけに絞る（CC BY-SAを含めない）
python tools/export_collection.py --output ../species-images-by --licenses cc0,cc-by

# 元ChronoEarthの対象だけに絞り、高品質JPEGも含める
python tools/export_collection.py --output ../chronoearth-images --tier chronoearth --include-master

# 補足写真・別候補も含む採用素材を書き出す
python tools/export_collection.py --output ../species-images-all --mode accepted
```

出力先には `catalog.json`、`images/`、`thumbnails/`、`metadata/`、`credits.csv`、`ATTRIBUTION.md` が作成されます。台帳内の画像パスも出力先基準に書き換えるので、元リポジトリのフォルダ構成をそのまま持ち込む必要はありません。未確認・除外画像は書き出しません。画像ファイルのハッシュを照合してからコピーします。

## 商用利用条件

対象は画像ごとに明示された **CC0・CC BY・CC BY-SA** です。非商用限定（NC）、改変禁止（ND）、All rights reserved、権利不明の素材は採用しません。掲載サイト全体の条件や観察データのライセンスを、写真自体のライセンスと混同しません。

CC BYでは作者等のクレジット・出典・ライセンスへのリンク・加工内容を保持します。CC BY-SAでは、それらに加えて改変写真の配布時に適切な同一ライセンス条件等が必要です。リポジトリ全体で写真を一律に再許諾しているわけではありません。バージョンは2.0・2.5・3.0・4.0等が混在するので、各画像の `licenseUrl` を確認してください。

CC0も追跡のため出典を保持します。写真の権利元の申告を確認した記録であり、人物・商標・撮影場所などの別の権利まで保証するものではありません。

公式条件: [CC0](https://creativecommons.org/publicdomain/zero/1.0/) / [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) / [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

詳しい基準は [再利用・品質方針](docs/REUSE_POLICY.ja.md) を参照してください。

## 保存形式・追跡情報

保存用JPEGは長辺最大2,048px、配信用WebPは長辺最大1,400pxです。サムネイルは小さな一覧表示用です。JPEGも元ファイルそのものではなく、方向補正・縦横比を保った縮小・再圧縮を行った保存版です。被写体の切り抜き、生成AIによる補完・描き換えは行っていません。

元画像URL、出典ページ、作者、元の帰属表記、画像ライセンス、取得日時、加工内容、寸法、ファイルサイズ、ハッシュ、出典APIのメタデータを記録しています。

## 収集・確認の記録

- `data/targets.json`: 対象と元サービスの対応。取り込み時の公開カタログとGitHub内データの一致をハッシュで確認。
- `scripts/collect.py`: 初期対象の取得と追加分類群の収集。途中再開・分割保存に対応。
- `curation/collect_reference.py`: 別構図の参考候補を個別ライセンス確認付きで取得。
- `reviews/screening-*.json`: 固定コミットの画像一覧に対する実際の目視判定。
- `curation/build_collection.py`: 重複整理、権利情報・ファイルの検証、審査済み台帳の作成。
- `reports/export-validation.json`: 別サービス向け書き出しと写真一覧のローカルリンクの検証結果。

生物数を増やす際も、写真取得・個別権利確認・目視判定を別工程として追加できます。時刻ベースの定期実行は設定していません。
