# Development / 開発

Maintainer notes; these checks are not installation steps and are not included in the user distribution.

開発を継続するための確認手順です。利用者のインストール作業ではなく、提供用パッケージには含めません。

## Development checks

From the repository root, use **the Python environment that runs ComfyUI**. Set `COMFYUI_ROOT` to the ComfyUI source directory:

```powershell
$env:COMFYUI_ROOT = 'C:\ComfyUI'
python -m unittest discover -s tests -v
```

If that environment is not active, replace `python` with its interpreter path. Node.js is needed only for the frontend compatibility tests:

```powershell
node --test tests/space_control_color.test.mjs
```

Tests cover mask geometry, base generation, latent conversion, release scheduling, workflow connections, and color-widget compatibility. They do not establish visual quality across all models.

---

## 日本語

### 開発用の確認

リポジトリのルートから、**ComfyUIが使用するPython環境**で実行します。`COMFYUI_ROOT` にはComfyUIのソースディレクトリを指定してください。

```powershell
$env:COMFYUI_ROOT = 'C:\ComfyUI'
python -m unittest discover -s tests -v
```

環境を有効化していない場合は、`python` をその環境の実行ファイルのパスに置き換えます。フロントエンド互換処理のテストにのみNode.jsが必要です。

```powershell
node --test tests/space_control_color.test.mjs
```

テストは範囲マスク・下地生成・latent変換・下地の解放・ワークフロー接続・色ウィジェットの互換処理を確認します。すべてのモデルでの見た目の品質を保証するものではありません。

## Maintenance notes

- [nodes.py](../comfyui_space_control/nodes.py) defines the public schema, validates controls, corrects latent dimensions, blends the base, and connects the release hook.
- [space_control.py](../comfyui_space_control/space_control.py) builds bases and region masks and implements the release schedule.
- [Frontend compatibility helpers](../comfyui_space_control/web/color_compat.mjs) remove duplicate color widgets from older extensions and migrate saved workflows.

Position values remain unchanged. The current node ID is `ComfyUISpaceControl`; the mode and seed inputs are `space_mode` and `seed`. Older UI workflows migrate on load: CLIP and regional text controls are removed, main positive conditioning bypasses Space Control, and MASK links are remapped and former IMAGE links are removed. Space mode now appears above Color; saved values and converted widget connections are preserved. Color, width, strength, mode, and seed are preserved; five-widget workflows default to color mode and seed zero. Saved API prompts need manual updates: remove clip, positive, contents, and contents_strength; wire the main positive directly to the sampler, and use MASK index 2. The IMAGE output has been replaced by an inline preview.

Use the development checks above when changing the implementation. The examples reference external model files; the repository does not include model weights.


### 保守上の注意

- [nodes.py](../comfyui_space_control/nodes.py)：公開するノード定義、設定値の検証、latent寸法の補正、下地の合成、解放処理の設定。
- [space_control.py](../comfyui_space_control/space_control.py)：下地と範囲マスクの作成、解放スケジュール。
- [フロントエンド互換処理](../comfyui_space_control/web/color_compat.mjs)：旧拡張による色ウィジェットの重複除去、旧ワークフローの接続と設定の移行。

位置値は維持しています。旧UIワークフローは読み込み時に移行し、CLIP・追加テキスト・追加強度を削除、メインのpositiveをサンプラーへ直結、MASKの接続番号を変更し、旧IMAGE接続は削除します。Space modeはColorの上に表示し、保存済み設定と入力に変換した設定欄の接続を保持します。色・幅・下地強度・方式・seedは保持し、5項目の旧設定はcolor方式・seed 0へ移行します。保存済みAPIプロンプトは、clip・positive・contents・contents_strengthを削除し、メインのpositiveをサンプラーへ直接接続してください。MASKは出力番号2です。IMAGE出力はノード内プレビューへ置き換えました。

実装を変更した場合は、この文書の開発用確認を実行してください。ワークフロー例が参照するモデルファイルは別途必要で、このリポジトリにモデルの重みは含まれていません。
