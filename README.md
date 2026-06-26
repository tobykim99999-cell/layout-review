# 排版审核智能体

这是一个 DOCX 优先、本地批处理、多智能体协作的毕业论文排版审核项目。它用确定性规则完成格式审核，用保守的自动修复处理高置信问题，并输出 JSON、Excel、HTML 报告。

## 智能体协作角色

- `DocumentParserAgent`：解析 DOCX 页面、段落、表格段落和基础格式。
- `RuleAuditorAgent`：按规则库执行格式与结构审核。
- `SafeFixerAgent`：只修复规则明确允许的高置信格式问题。
- `QualityGateAgent`：对修复后文档二次审核，确认问题是否收敛。
- `IterationMemoryAgent`：沉淀高频问题、自动修复效果和下一轮优化建议。
- `ReportWriterAgent`：生成机器结果、人工清单和可视化报告。
- `LayoutReviewCoordinator`：编排以上智能体，形成完整工作流。

`SharedReviewState` 是所有智能体共享的上下文，用来传递事实、产物、指标和决策。`SharedLLMService` 是所有智能体可共用的大模型能力层，不是独立智能体。当前默认关闭，可用于后续解释、异常归因、建议润色、规则配置辅助等，但不参与硬规则裁决。

## 快速开始

```powershell
$py = "C:\Users\21483\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$env:PYTHONPATH = "src"
& $py -m layout_review_agent.cli sample .\demo
& $py -m layout_review_agent.cli audit .\demo\bad_thesis.docx --out .\demo\reports --fix-safe
& $py -m layout_review_agent.cli audit .\demo\bad_thesis.docx --out .\demo\reports_llm --llm-advice
& $py -m layout_review_agent.cli batch .\demo --out .\demo\batch_reports --fix-safe --memory-file .\demo\review_memory.jsonl
```

## 本地网页上传模式

如果不想用命令行，最简单方式是在 PyCharm 左侧项目树里找到：

```text
run_web.py
```

右键它，选择：

```text
Run 'run_web'
```

它会自动启动服务并打开浏览器。

也可以在 PyCharm 里配置模块运行：

```text
Module name: layout_review_agent.web
Working directory: D:\my-manage\project\layout-review
Parameters: 留空
```

运行后浏览器打开：

```text
http://127.0.0.1:8000
```

页面支持：

- 上传处理后的 `.docx` 论文；
- 从下拉框选择学校规则库；
- 上传学校论文格式规范或结构化规则库；
- 选择是否自动安全修复；
- 选择是否生成共享 LLM 解释上下文；
- 在线显示审核摘要；
- 下载 `audit_report.html`、`issues.xlsx`、`annotated.docx`、`fixed.docx`、`result.json`、`iteration_insights.json`。

网页模式默认把上传文件和报告保存到：

```text
web_runs\
```

学校规则库默认从这里读取：

```text
rule_profiles\
```

## 桌面智能体助手模式

如果希望运行后就是一个桌面程序，在 PyCharm 左侧项目树里找到：

```text
run_desktop.py
```

右键它，选择：

```text
Run 'run_desktop'
```

桌面助手会直接打开窗口，不需要浏览器。它支持：

- 选择处理后的论文 `.docx`；
- 选择目标学校规则库；
- 导入学校官方规范或结构化 JSON 规则库；
- 勾选自动安全修复；
- 勾选共享 LLM 解释；
- 查看智能体执行状态和日志；
- 打开原文批注 `annotated.docx`；
- 打开安全修复稿 `fixed.docx`；
- 打开 HTML 报告和结果目录。

桌面模式默认把运行结果保存到：

```text
desktop_runs\
```

学校规则库仍然从这里读取：

```text
rule_profiles\
```

如果安装到本地环境，也可以使用：

```powershell
layout-review-desktop
```

## 桌面智能宠物助手模式

如果想要一个小型悬浮助手，在 PyCharm 左侧项目树里找到：

```text
run_pet.py
```

右键它，选择：

```text
Run 'run_pet'
```

它不会打开传统大窗口，而是显示一个蓝白色悬浮机器人。机器人默认置顶、可拖动，点击机器人会展开功能面板，并且会根据任务状态切换动作：

- 待命时轻微漂浮和眨眼；
- 审核时挥手并显示环绕加载动画；
- 完成后提示打开批注、修复稿或报告；
- 失败时显示错误状态。

功能面板已经接入完整审核能力：

- 选择处理后的论文 `.docx`；
- 选择或导入学校规则库；
- 上传学校官方规范并自动生成可选规则库；
- 默认勾选安全修复；
- 默认勾选共享 LLM 解释；
- 审核后打开 `annotated.docx`、`fixed.docx`、`audit_report.html` 和结果目录。

宠物模式默认把运行结果保存到：

```text
pet_runs\
```

如果安装到本地环境，也可以使用：

```powershell
layout-review-pet
```

网页首页有：

```text
上传学校论文格式规范或规则库
```

这里支持两种上传：

- 上传 `.json`：必须是已经结构化好的规则库，系统会校验后加入规则库下拉框。
- 上传 `.docx/.txt/.md`：系统会抽取规范文本并自动规范化为可选规则库。优先调用共享 LLM 生成 JSON；如果 LLM 未配置、调用失败或没有返回 JSON，会启用本地确定性抽取器生成当前引擎可执行的规则。
- 上传 `.pdf`：需要本地安装 PDF 文本抽取依赖；更推荐上传学校发布的 DOCX/TXT/MD 规范。

注意：自动规范化只负责把学校官方规范转换成当前审核引擎可执行的 JSON 规则。最终审核仍以生成后的规则库为准，大模型不会在论文审核时推翻确定性规则。

也可以在 PyCharm 的 Parameters 里指定端口和输出目录：

```text
--host 127.0.0.1 --port 8000 --base-dir web_runs --rules-dir rule_profiles
```

如果安装到本地环境，也可以使用：

```powershell
layout-review audit input.docx --profile default_undergraduate --out reports --fix-safe
layout-review batch docs --profile default_undergraduate --out reports --fix-safe
layout-review-web
layout-review profiles --rules-dir rule_profiles
```

## 共享 LLM 接入预留

LLM 默认关闭。启用 `--llm-advice` 时，如果没有配置模型，系统会输出可交给 LLM 的提示词上下文包；如果配置了 OpenAI-compatible 接口，则会调用模型生成辅助解释。这个能力通过运行上下文注入，后续所有智能体都可以共用。

LLM 配置属性固定为：

- `provider`
- `base_url`
- `api_key`
- `model`
- `temperature`
- `max_tokens`

```powershell
$env:LAYOUT_REVIEW_LLM_BASE_URL = "https://api.example.com/v1/chat/completions"
$env:LAYOUT_REVIEW_LLM_API_KEY = "your-api-key"
$env:LAYOUT_REVIEW_LLM_MODEL = "your-model"
layout-review audit input.docx --llm-advice --llm-provider openai-compatible --llm-temperature 0.2 --llm-max-tokens 1000
```

网页模式更推荐使用本地配置文件。复制：

```text
llm_config.example.json
```

改名为：

```text
llm_config.json
```

然后填写：

```json
{
  "provider": "deepseek",
  "base_url": "https://api.deepseek.com",
  "api_key": "你的 API Key",
  "model": "你的模型名",
  "temperature": 0.2,
  "max_tokens": 4000
}
```

启动网页后打开：

```text
http://127.0.0.1:8000/llm/status
```

如果显示 `enabled: True`，勾选 `llm_advice` 后才会真正调用大模型。`base_url` 可以填服务根地址，系统会自动拼成 `/chat/completions`；也可以直接填完整的 chat completions 地址。

如果要上传学校官方规范并自动生成规则库，建议 `max_tokens` 设为 4000 或更高，否则模型返回的 JSON 可能被截断。

LLM 输出只进入 `shared_llm` 字段和报告说明，不影响合规得分、不触发自动修复、不推翻规则库结论。

## 输出文件

单篇审核会在输出目录生成：

- `result.json`：结构化机器结果。
- `issues.xlsx`：逐条问题清单。
- `audit_report.html`：业务人员可读报告。
- `annotated.docx`：在原文对应段落添加 Word 批注的问题报告。
- `fixed.docx`：启用 `--fix-safe` 时生成，仅包含高置信自动修复。
- `post_fix_result.json`：修复后二次审核结果。
- `shared_llm`：启用 `--llm-advice` 时写入 `result.json`，用于人工复核解释。
- `iteration_insights.json`：单篇智能迭代画像，包括高频规则、问题类别、修复效果和下一轮优化建议。
- `batch_iteration_insights.json`：批量智能迭代画像。
- `memory.jsonl`：使用 `--memory-file` 时追加长期问题记忆。

批量审核会为每篇文档生成独立子目录，并生成 `batch_summary.json`。

## 规则库

默认规则位于 `src/layout_review_agent/rules/default_undergraduate.json`。规则支持页面设置、正文、标题、图表题注和必备章节检查。后续可按学校、学院、学历层次复制并修改规则文件。

重要：`default_undergraduate` 是演示规则，不代表任何学校官方格式要求。真实审核前必须先做目标学校规则库。

学校规则库模板位于：

```text
rule_profiles\school_profile_template.json
```

推荐流程：

1. 复制 `rule_profiles\school_profile_template.json`。
2. 改名为目标学校规则，例如 `xx_university_undergraduate_2026.json`。
3. 修改 `profile_id`、`display_name`、`version`。
4. 在 `source` 里写清楚学校官方规范、模板、发布日期、适用学院/学历层次。
5. 按学校规范修改 `rules` 和 `required_sections`。
6. 启动网页服务，在下拉框选择该学校规则库后再审核论文。

如果你通过网页上传学校官方规范，系统会自动在 `rule_profiles\_sources` 保存原始文件，并在 `rule_profiles` 生成 `is_template: false` 的可选规则库。上传成功后会直接回到论文上传页，并自动选中新生成的规则库；只有在 LLM 和本地抽取器都无法生成任何可执行规则时，才会生成带 `is_template: true` 的草稿并说明失败原因。

规则来源必须优先采用学校官方文件、官方 Word 模板、学院补充要求和人工确认合格样本。智能体和 LLM 都不能凭空决定学校格式标准。

## 当前边界

- 首版只正式支持 `.docx`。
- DOCX 本身不可靠提供真实页码，页码和跨页问题会进入人工复核或后续接入渲染校验。
- 自动修复只处理高确定性格式项，不自动改内容、语义或复杂分页。
