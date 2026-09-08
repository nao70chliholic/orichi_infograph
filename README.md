# Orochi Infograph

## コミュニティごとのテーマ

`core.py` の配色とイラストは環境変数で差し替えられる。設定しなければ既定値
（開運オロチ）で動くので、オロチ側は何も渡していない。

| 環境変数 | 既定（開運オロチ） | CNPスタープロジェクト |
|---|---|---|
| `INFOGRAPH_BG_COLOR` | `#B6E18D` | `#2E3350` |
| `INFOGRAPH_PANEL_COLOR` | `#FAFAE6` | `#F5F3EC` |
| `INFOGRAPH_TEXT_COLOR` | `#333366` | `#2E3350` |
| `INFOGRAPH_TITLE_COLOR` | （TEXT と同じ） | `#F3D98B` |
| `INFOGRAPH_UP_COLOR` | `green` | `#2E7D50` |
| `INFOGRAPH_DOWN_COLOR` | `blue` | `#3A5BC7` |
| `INFOGRAPH_CHARACTER` | `plush_orochi.png` | `MAKAMIshinonome.jpg` |
| `INFOGRAPH_CHARACTER_SIZE` | `300` | `260` |
| `INFOGRAPH_CHARACTER_STRIP_BG` | （なし） | `1` |
| `INFOGRAPH_TITLE_SPLIT` | `トークン` | `プロジェクト` |

- `INFOGRAPH_TITLE_COLOR` はタイトルと日時にだけ効く。濃い背景を使うときに、
  パネル内の文字色と分けるためのもの。
- `INFOGRAPH_CHARACTER_STRIP_BG=1` は、四隅から連結している均一な背景を透過に戻す。
  透過PNGをJPGに変換して背景が黒（や白）で潰れた画像用。色での一括指定ではなく
  塗りつぶしで外側からたどるので、キャラクターの黒い輪郭は消えない。
- `INFOGRAPH_CHARACTER_SHAPE=circle` で円形に切り抜ける。背景を残したまま
  アイコンとして置きたいとき用（STRIP_BG を使うなら不要）。
- タイトルは `INFOGRAPH_TITLE_SPLIT` の位置で2行に折る。それでも幅に収まらなければ
  自動でフォントを縮める。

### CNPスタープロジェクトの週次画像：残作業

日次テキストは GitHub Actions 側で動いている（`oridhi_dailicounter` の
`daily_stats_cnp.yml`）。週次画像を出すには、**2026-09-19 以降**に次を行う。

1. `oridhi_dailicounter` に `weekly_report_cnp.yml` を追加する
   （`weekly_report.yml` をコピーして、そちらの README の環境変数表を足す）。
   土曜2週分の行が必要なので、それ以前に置くと必ず失敗する
2. このリポジトリの `.env` に、CNP用の Discord Webhook とチャンネルIDを足す
   （GitHub の Secrets とは別。手で貼る必要がある）

   **⚠️ キー名に注意。** `cli_post_infograph.py` の `_get_webhook_urls()` は
   `DISCORD_WEBHOOK_URL` で**始まる環境変数を全部**投稿先として拾う。
   `.env` に `DISCORD_WEBHOOK_URL_CNP` と書くと、**オロチの日次・週次の画像まで
   CNPチャンネルに飛ぶ。** GitHub Actions はジョブごとに環境変数を渡すので
   問題にならないが、Mac側は同じ `.env` を全実行が読むので事情が違う。

   ```
   CNP_DISCORD_WEBHOOK_URL=...
   CNP_DISCORD_CHANNEL_ID=1546676532167311460
   ```

   先頭を `CNP_` にして収集から外し、CNPの実行時だけ Bot 側が
   `DISCORD_WEBHOOK_URL` として渡し直す（オロチ側の webhook は subprocess の
   環境から取り除く）。こうすればどちらの実行も投稿先が1つだけになる。
3. `bot/main.py` の `weekly_post` を参考に、CNP用の週次タスクを足す。
   `run_cli_script` に上表の環境変数を渡す。読み取り元チャンネルは
   CNP用のもの、`.last_posted.json` はコミュニティごとに分ける

出力は FiNANCiE の CNPスターのコミュニティへ**手で貼る**
（FiNANCiE には公開APIが無く、規約もBOTに否定的なため自動投稿はしない）。
