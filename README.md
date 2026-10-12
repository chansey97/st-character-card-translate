# SillyTavern 角色卡翻译工具

通过 OpenAI Compatible API（兼容 OpenAI Chat Completions 的接口）翻译 V2 风格 JSON 角色卡。七阶段流程依次抽取字段、发现实体、统一译名、生成术语子集、翻译、回填、去重世界书关键词。最终角色卡保留未知字段和扩展。

```mermaid
flowchart TD
    A[原始角色卡 JSON] --> B["1. extract：抽取字段"]
    B --> C["fields/"]
    C --> D["2. discover：实体发现、译名和打分<br/>调用 LLM"]
    D --> E["entities/"]
    E --> F["3. glossary：统一译名"]
    F --> G["glossary.json"]
    C --> H["4. subsets：匹配正文术语、收集关键词译名"]
    G --> H
    H --> I["glossary_subsets/"]
    C --> J["5. translate：翻译<br/>LLM 翻译正文，程序替换关键词<br/>核对世界书条目数和逐项 id"]
    I --> J
    J --> K["translations/"]
    A --> L["6. backfill：回填原卡"]
    K --> L
    L --> M["backfill/原文件名.json"]
    M --> N["7. deduplicate_keys：关键词去重"]
    N --> O["deduplicate_keys/原文件名.json"]
    Z["可选背景文本 .txt"] -.-> D
    Z -.-> J
    G -.-> R["可选：编辑全局 glossary"]
    R -.-> H
    I -.-> S["可选：编辑当前文件的 glossary 子集"]
    S -.-> J
```

最终产物是 `deduplicate_keys/` 中的角色卡。

## 安装

### Portable（Windows x64）

解压 `st-character-card-translate-windows-x64.zip`，保留整个目录及其中的 `_internal/`。无需安装 Python、Git 或下载 Python 依赖；翻译时仍需运行或连接可用的 API 服务。使用本地服务时，可以离线运行。

支持的 Windows 版本取决于构建时使用的 Python；使用 Python 3.14 构建的包要求 Windows 10 或更新版本，见 [Python 的系统支持说明](https://docs.python.org/3.14/using/windows.html#supported-windows-versions)。

按下文[配置](#配置)说明修改 exe 同目录的 `config.toml`，然后在该目录打开 PowerShell：

```powershell
.\st-character-card-translate.exe --help
.\st-character-card-translate.exe "C:\cards\card.json" --source-lang en --output-dir outputs
```

Portable 保留命令行用法，需要在终端中传入参数。下文的 `st-character-card-translate` 命令在此版本中写为 `.\st-character-card-translate.exe`，其余参数相同。相对输入、输出及 `--config-file` 路径仍相对于当前工作目录。

### 从源码安装

需要 Git 和 Python 3.11 或以上版本。以下命令以 Windows PowerShell 为例。

先克隆项目并进入项目目录：

```powershell
git clone https://github.com/chansey97/st-character-card-translate.git
cd st-character-card-translate
```

然后选择以下一种安装方式。

#### 普通安装

适合直接使用工具翻译角色卡。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .
```

#### 开发安装

适合修改源码、运行测试或构建 portable 发行包。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

安装完成后，使用 `st-character-card-translate` 命令。

## 配置

可连接本地或远程的 OpenAI Compatible API 服务。服务及所选模型须支持 Chat Completions 的严格 JSON Schema 结构化输出（`response_format.type="json_schema"`、`json_schema.strict=true`）。

包内默认配置：

```toml
[openai]
base_url = "http://127.0.0.1:8317/v1"
api_key = "123456"
model = "gemini-3.8-flash-high"
max_retries = 2
```

请根据所用 API 服务，通过 TOML 文件覆盖 `base_url`、`api_key` 和 `model`，分别指定服务地址、密钥和模型。配置按 `[openai]` 内的字段逐层覆盖，后加载的同名字段优先：

| 层级 | 从源码安装 | Portable |
| --- | --- | --- |
| 1 | 包内 `config.default.toml` | 包内 `config.default.toml` |
| 2 | 用户配置目录中的 `config.toml` | exe 同目录的 `config.toml` |
| 3 | `--config-file PATH` | `--config-file PATH` |

Portable 随包提供公开默认配置，修改 exe 旁的 `config.toml` 即可；此版本不读取用户配置目录。配置位置与启动命令时的工作目录无关。

从源码安装时，用户配置位置是 `platformdirs.user_config_path("st-character-card-translate", appauthor=False) / "config.toml"`，可在安装环境中运行下列命令查看：

```console
python -c "from platformdirs import user_config_path; print(user_config_path('st-character-card-translate', appauthor=False) / 'config.toml')"
```

第二层配置不存在时跳过，运行时不自动创建；显式指定的文件必须存在。只接受上述四项，每层均独立校验；没有环境变量覆盖层或当前目录自动搜索。`--help` 无需读取配置或连接 API 服务。

## 使用

源语言和目标语言使用 **BCP 47 语言标签**，例如 `en`（英语）、`ja`（日语）、`zh-Hans`（简体中文）、`zh-Hant`（繁体中文）。源语言必填，目标语言默认为 `zh-Hans`。

### 典型用法

完整翻译为简体中文，并将任务产物保存到 `outputs/` 下：

```console
st-character-card-translate examples/main_the-shining-stone-3ab47f90d0c6_json.json --source-lang en --output-dir outputs
```

任务目录为 `<输出父目录>/<输入文件名去扩展名>__<源语言>_to_<目标语言>/`。省略 `--output-dir` 时使用当前目录作为父目录。最终角色卡位于任务目录的 `deduplicate_keys/<原文件名>`；`backfill/` 保留去重前的角色卡。

指定目标语言为日语、世界书每片最多 10 条，并设置输出父目录：

```console
st-character-card-translate examples/main_the-shining-stone-3ab47f90d0c6_json.json --source-lang en --target-lang ja --chunk-size 10 --output-dir outputs
```

运行到全局术语表生成后暂停，便于检查和统一译名：

```console
st-character-card-translate examples/main_the-shining-stone-3ab47f90d0c6_json.json --source-lang en --output-dir outputs --to-stage glossary
```

检查或编辑任务目录中的 `glossary.json` 后，从术语子集生成继续：

```console
st-character-card-translate examples/main_the-shining-stone-3ab47f90d0c6_json.json --source-lang en --output-dir outputs --from-stage subsets
```

从翻译阶段继续，并保留术语及世界书关键词的原文：

```console
st-character-card-translate examples/main_the-shining-stone-3ab47f90d0c6_json.json --source-lang en --output-dir outputs --from-stage translate --no-translate-glossary
```

编辑任务目录中 `translations/` 下的译文后，从回填阶段继续：

```console
st-character-card-translate examples/main_the-shining-stone-3ab47f90d0c6_json.json --source-lang en --output-dir outputs --from-stage backfill
```

续跑时保持输入、语言、背景及输出父目录等参数一致；修改后需要更新的旧产物，须先按[检查、编辑与续跑](#检查编辑与续跑)中的表格清理。

### CLI 参数

| 参数 | 默认值 | 用途 |
| --- | --- | --- |
| `--source-lang LANG` | 必填 | 源语言 BCP 47 标签 |
| `--target-lang LANG` | `zh-Hans` | 目标语言 BCP 47 标签 |
| `--output-dir PATH` | 当前目录 | 输出父目录，始终追加任务目录 |
| `--background PATH` | 无 | UTF-8 文本背景及文风参考，允许 BOM |
| `--config-file PATH` | 无 | 最高优先级的 TOML 配置 |
| `--input-encoding NAME` | `utf-8-sig` | 原卡编码 |
| `--chunk-size N` | `10` | 世界书每片最大条目数，正整数 |
| `--no-translate-glossary` | 关闭 | 保留子集术语及世界书关键词原文 |
| `--delay-between-requests SECONDS` | `0` | 每次模型请求前等待，包括第一次 |
| `--from-stage NAME` | `extract` | 起始阶段，包含该阶段 |
| `--to-stage NAME` | `deduplicate_keys` | 结束阶段，包含该阶段 |

阶段顺序：`extract → discover → glossary → subsets → translate → backfill → deduplicate_keys`。只运行指定区间，不自动补跑上游。成功退出码为 `0`，参数或配置错误为 `2`，阶段失败为 `1`，错误包含阶段与相关路径。

语言标签只检查非空以及 ASCII 字母、数字和连字符，原样用于目录名和请求。单个开场白始终对应一个文件；分片大小只影响世界书。

## 检查、编辑与续跑

所有阶段均以目标文件存在作为唯一复用条件。已有文件不会被自动覆盖，也不会为了复用而读取校验。使用上游数据时才检查其内容。发生错误后，已生成的文件保留。

可在 `glossary.json` 中统一修改译名。每个 `glossary_subsets/` 文件固定包含 `glossary`（正文术语）与 `keywords_glossary`（世界书关键词译名），可分别编辑。跨条目的统一改名应修改全局 glossary 后重建下游；两个词典的人工修改不会自动同步。

修改后请手动删除当前任务目录中的相应产物，再保持输入、语言、背景和输出父目录参数一致续跑：

| 修改内容 | 删除的产物 | 续跑阶段 |
| --- | --- | --- |
| 原卡、编码、分片大小、语言 | 全部任务产物，或换输出父目录 | `extract` |
| 背景、模型、实体提示词、fields | entities 及其全部下游 | `discover` |
| entities | glossary 及其全部下游 | `glossary` |
| 全局 glossary | subsets、translations、回填卡、去重卡 | `subsets` |
| 子集结构或生成规则 | subsets、translations、回填卡、去重卡 | `subsets` |
| 某个子集词典 | 同名译文、回填卡、去重卡 | `translate` |
| 术语模式、翻译提示词 | translations、回填卡、去重卡 | `translate` |
| 某个译文文件 | 回填卡、去重卡 | `backfill` |
| 回填卡 | 去重卡 | `deduplicate_keys` |
| 最终卡 | 无 | 保留编辑后的文件 |

目录对应：subsets 指 `glossary_subsets/`，回填卡指 `backfill/`，去重卡指 `deduplicate_keys/`。人工编辑时保持文件名、JSON 结构、世界书条目数量和顺序及原生 id。备选开场白文件名中的序号对应原数组位置。

工具不支持 PNG、V1、V3 或 `/pattern/flags` 形式的世界书关键词。除普通目标字段、每条开场白以及世界书 `keys`、`secondary_keys`、`content`、`comment` 外，其余数据保留，包括世界书 `name`、`id` 和设置。关键词由程序精确替换及稳定去重；正文的术语采用、格式和 SillyTavern 递归触发效果需要人工检查。

## 构建 portable 发行包

在 Windows 上使用 x64 Python 完成[开发安装](#开发安装)后，双击项目根目录的 `build_portable.bat`，或在终端运行：

```powershell
.\build_portable.bat
```

脚本直接使用项目 `.venv` 中的 PyInstaller，以 `--onedir` 模式打包，不自动安装或下载依赖。构建成功后生成：

```text
dist/
├── st-character-card-translate-windows-x64.zip
└── st-character-card-translate/
    ├── st-character-card-translate.exe
    ├── config.toml
    ├── README.md
    ├── PLAN.md
    └── _internal/
```

将 ZIP 分发给用户即可。包中的 `config.toml` 复制自 `src/st_character_card_translate/config.default.toml`，不会包含打包者项目根目录或用户目录中的个人配置。再次构建会替换上述应用目录和 ZIP，请在解压后的副本中修改配置和使用工具。

## 测试

```console
python -m pytest
python -m pytest tests/live -s
```

默认只运行单元和集成测试，不连接 API。真实测试显式运行，使用相同的默认及用户配置，以两组语言组合发起少量真实请求。输入和输出保存在 `test_outputs/live/<含微秒时间戳>/<case_name>/`，成功和失败均保留并报告路径。检查译文语言、可读性、术语采用，以及宏、标签和格式保留；测试不以固定译文措辞作为断言。

构建 portable ZIP 后，可单独验证解压运行、配置覆盖和七阶段流程；该测试仅连接本地模拟 HTTP 服务：

```console
python -m pytest tests/portable
```

完整数据契约、提示词与验收要求见 [PLAN.md](PLAN.md)。请求采用 [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat) 的严格 JSON Schema，保持同步、串行、非流式执行。
