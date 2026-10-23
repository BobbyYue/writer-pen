# 执行与核对：把检查绑定到实际稿件

这是底层接口与记录格式，供排错和维护使用。正常创作从 [统一入口](workflow.md) 开始，
不要在每次写作中手工重建这里的调用顺序。稿件与自查由本模块负责，阶段/轮次由生命周期负责，实际调用由执行器负责。

用于实质创作或改稿，且用户允许在本地留下写作记录时。诊断、构思、练习反馈及简短局部润色
不强制启动完整流程；需要局部版本核对时可用local模式。不把这些记录默认展示给只想看作品的用户。

## 什么由程序检查，什么仍需阅读

| 层次 | 本包能做什么 | 不能据此声称什么 |
|---|---|---|
| 可核验条件 | 指定底稿快照、人物封存、稿件版本、引文是否存在、明确字数与局部边界、记录顺序、交付一致 | 选定的底稿一定符合用户本意；引文一定支持判断 |
| 正文判断 | 按操作方法审读，记录问题、正文依据、反例及处理 | 程序已经验证人物可信、实际修复有效或确实认真通读 |
| 审美取舍 | 比较收益代价，允许不确定、不同偏好和有依据的发展 | 一张表、模型共识或高分证明文学更好 |

程序是 [writing_run.py](../scripts/writing_run.py)，仅用Python标准库，适用于macOS/Linux。
本地运行，无联网、无模型调用、无自动发布。记录含全文，保存在当前任务获准目录；不放入skill、
全局记忆、测试集或发布资源。用户要求不落盘时不用本工具，按文字流程工作并如实说明核对边界。

**这是本地记录与交付检查，不是已接入宿主的强制执行器。** 它能约束经它登记、审读、导出的顺序，
不能阻止模型绕过脚本直接回答，也不能证明正文是在封存后才生成。`prewrite`是操作者的时间性质声明，
不是生成调用证据。更强的顺序保证需要另将实际生成与最终交付入口接入受控程序；本包不擅自安装宿主钩子。

## 底层接口次序

下文`TOOL`指本包`scripts/writing_run.py`，`RUN`是本次新建的记录目录。每个作品版本方向独立建RUN。
同一任务的修订沿用原生命周期及累计轮数，不通过另建RUN清零。先按 [写作阶段](writing-lifecycle.md) 建立`LIFE`。
只记录短的判断和依据，不记录逐步思考过程。先读指定原材料，再确认底稿路径与范围。

1. **登记任务。** 准备`contract.json`，运行`python3 TOOL init RUN --contract contract.json --source 原稿.md`。
   create可无source；revise/local必须提供指定原稿。多篇合集先准确提取本篇净文本，保留原文件与定位，不能把上一版改稿冒充源材料。
   revise还须声明`source_title`：原文的实际题名，或无题时为null。`opening_text`须含正文开头，不能只用相同题名证明开头未变；不靠段落长短猜测题名。
2. **封存与准备。** 按 [人物先行](character-first.md) 先封存分析，再运行
   `python3 TOOL prepare RUN --lifecycle-run LIFE --record 人物记录.record.json --reason "本轮写前人物理解"`。
   分析改变另封存新版本；写中或事后补记用`--timing during`或`retrospective`，不能倒填写前状态。
   无人物中心且已有豁免说明时可省record，仍登记prepare；不要为填表发明人物。
3. **实际写作，登记候选。** 写中先登记单元checkpoint，再运行
   `python3 TOOL draft RUN --lifecycle-run LIFE --checkpoint 场景单元ID --id v1 --file 候选.md`。
   再次修改用v2等新编号登记；不会覆盖旧快照。工作文件若变化而未重新登记，后续完成检查会阻止交付。
4. **净稿阅读。** 只读当前净稿，生成简短clean记录，运行`python3 TOOL review RUN --file clean.json`。
   不给每个检查项凑记录。先记录整体阅读结论，再记录真正发现的问题。
5. **对照与处理。** 再读原稿、人物封存和必要上下文，完成comparison记录，同样用review提交。
   检查正文是否支撑结论，不能只引用一处有利句子；具体操作见 [判断方法](operations.md)。
   需修改则回第3步；新稿旧检查全部失效，不能直接改记录中的版本号续用。
6. **选择与独立审读。** 用`python3 TOOL decide RUN --file decision.json`记录选择；按
   [独立审读](writing-lifecycle.md) 完成计量、候选处置、专业审稿与独立读者，并绑定本轮原生结果。
7. **核对与交付。** 运行`python3 TOOL check RUN --lifecycle-run LIFE`；通过后才能用
   `python3 TOOL deliver RUN --lifecycle-run LIFE --to 新净稿.md`导出，已有文件不会被覆盖。
   已编辑的纯文本目标用`check RUN --lifecycle-run LIFE --final 目标.md`核对。HTML默认交付走
   [文学HTML](html-output.md)：纯文本作为原生候选，实际HTML与版面证据在candidate前绑定，
   最后用`validate_html_output.py --text 稿件.txt --run RUN --lifecycle-run LIFE`核对页面；不要把HTML传给纯文本的`--final`。
   飞书等其他载体仍须核对实际正文及渲染。

低层`check_records()`的`record_checks_satisfied`只表示原生局部记录满足，不代表完整流程通过，也不能导出完成稿。
最终`check/deliver`只有原生自查、独立评审及生命周期共同满足才返回`pass`，仍不是文学质量实证。
同任务完成三轮后，当前稿最后一轮仍fail且有问题时的`--draft`及说明见阶段文档；此前版本pass不阻止草稿展示。
这不是独立通过或发布授权，不能跳过缺记录或旧版本。`check`阻塞退出码2，输入错误退出码1。
运行失败后先修正输入或权限，不无限重试。相同阅读问题反复试改仍无收益时，保留可用版本并说明分歧，不循环冲分。

## 任务记录

以下是虚构改稿示例，不是要求用户填写的问卷。记录由执行者依据当前请求建立：

```json
{
  "mode": "revise",
  "goal": "保留迟疑，把人物作决定的过程写清楚",
  "scope": "用户提供的短篇全文",
  "fiction": "allowed",
  "constraints": ["不改变第一人称"],
  "require_character": true,
  "opening_text": "与原稿正文起始完全相同的进入单元"
}
```

- mode为create/revise/local；fiction为allowed/not_allowed/unspecified。权限是根据请求登记的判断，程序不替用户授权。
  constraints只记录用户实际限制，不把额外自查口径变成新的创作要求。
- 无需人物分析时将require_character设为false，另写character_exemption理由。不得为跳过封存虚报不适用。
- revise的opening_text须是原稿精确前缀，按一个完整进入单元选择，不把标题或随便一个字当作开头范围。
  程序据此发现前缀改变；进入单元选得是否恰当仍需审读。
- 可选min_chars/max_chars只录实际限制，口径为去空白后的Unicode字符数，包含标点；check会返回该计数。与用户“字数”口径不同时先调整约定，不偷换。
- 可选preserve_exact是必须保留的精确文字数组；语义限制仍在constraints中，人物设定需要结合上下文核对。
- local若要自动保护修改区外文字，输入完整原稿并用edit_span=[起点,终点]指定Unicode字符半开区间。
  未提供区间时只记录局部范围，不声称已自动证明全文其他部分未改。用脚本定位字符，不凭肉眼估索引。
- 原始材料在登记后改变，先确认新来源再建新RUN；不要修改run.json绕过提醒。

## 审读记录

用`inspect RUN --artifact draft:v1`取当前快照，用`inspect RUN --diff`看与原稿的实际差异。
不带参数的inspect显示任务、对象编号、登记过程和已发现问题。引用中的artifact必须是已存在编号。

```json
{
  "draft_id": "draft:v1",
  "phase": "clean",
  "coverage": "full",
  "summary": "整体阅读判断，不是已检查三个字",
  "observations": [{"covers": ["paragraph_rhythm"], "claim": "有正文支持的判断", "evidence": [{"artifact": "draft:v1", "quote": "当前净稿中的精确短引"}]}],
  "issues": []
}
```

coverage在local模式为excerpt，其余为full，只指本次登记的作品范围，不能把截断长篇称为整部长篇。
程序核对标记和引文，不证明完整阅读。clean观察只引当前净稿，不把提纲当正文证据。
`covers` 标明每条观察支持的 [检查项](review-coverage.md)，全部观察的并集须覆盖清单；上例仅示范一条，不是完整自查。
相关项目可共用同一条实质观察，不重复填表；尚未检查的项不能靠 `coverage=full` 补成已检查。
问题存在时issues记录：`id`、`kind`（constraint/coherence/preference）、`blocking`布尔值、`claim`、`evidence`。
constraint必须blocking；文学偏好不自动阻塞。每项问题只能由具体正文问题触发，不能为了示范而凑问题。

comparison同样有summary、observations和可选issues，另有：
- 有人物基准时的character：outcome为consistent/development/unsupported/not_expressed，附reason及同时引用当前稿与基准的evidence。
  development另提供development_record路径，封存写中或写后的新理解；保留原基准，不把背景未写出一律算偏离。
- comparisons：每项含kind（opening/key_change/other）、before（source或旧draft编号）、gain、loss、attention_cost、choice、reason、evidence。
  引用须同时覆盖before与当前稿，缺乏明显损失可写“未发现具体损失”并据实说明，不为满足字段发明代价。
  attention_cost写明停顿、关注转移或阅读时间带来的实际得失；慢下来也可以有益，程序不以长短裁决。
  改稿正文有变化须与source比较；登记的开头前缀改变时须有opening比较。其他关键删改由实际审读识别，程序不能自动穷尽。
- resolutions：回应前次已记录问题，含issue（如review:1/f1）、outcome、reason、当前稿evidence。
  fixed需正文确实有变化；误报用withdrawn说明反证；只有preference可以accepted_tradeoff。新稿中旧问题的处理须重新复核，不自动继承“已解决”。
  accepted_tradeoff还须附下方trial，不能只凭“有表现作用”关闭已提出的问题。

关键问题未处理、人物变化仍为unsupported、比较仍为retry/defer，都不能进入已核对交付。
两版都有问题则继续修或交代限制，不靠把问题改成偏好或把引用改为新版本制造完成。
判断可被撤回，撤回须说明具体反证。程序只校验记录结构及引文存在，是否真的修好仍由审读负责。

独立审读提出editorial时，作者选择retain也须在现有取舍文件附`trial`，不增加审稿角色或轮次：

```json
{
  "current": "当前稿中包含问题位置与必要上下文的精确文字",
  "alternative": "实际试写的删除、压缩、移位或重构候选文字",
  "gain": "比较后读者具体多获得什么；可如实说明未发现收益",
  "loss": "比较后损失什么，不编代价",
  "attention_cost": "是否转移关注、延迟反应或形成有益停顿"
}
```

current须来自当前稿并覆盖所回应的问题位置；editorial取舍还须覆盖原问题引文。
alternative不能与原文相同或仅改无关空白；实际试合并或拆分段落时附`kind: "paragraphing"`，
程序允许真实的行段边界变化，不因未换词就否定停顿的作用。
删除版记录维持衔接后的实际文本；不能把“删去即可”当试写。选择revise/defer不强迫先试稿，
但保持本轮未通过，修稿仍在原任务剩余轮次内重新审读。保留选择、原始审读和稿件版本继续绑定。
程序只确认有不同文字与得失记录，不能证明候选认真发展、引用支持解释或读者实际被打动。

decision含draft_id、choice（adopt/retain/retry/defer）、reason、当前稿evidence，可附uncertainty。
retain仅用于完整保留登记原文；保留初稿但无源稿的创作选adopt。评分仍仅在明确要求时附加为诊断，不参与程序决策。
决定作出后再新增审读，必须重新决定；全文改动后重新登记并审读。当前首版采用整稿失效，宁可明确多一次核对，
不冒充能自动理解哪些段落依赖修改；长篇按实际可完整阅读的章节建记录，不硬跑整本。

## 验证此方法是否可靠

维护时运行 [测试说明](testing.md)，不要把固定测试和多人审读塞进每一次写作。
本包记录只提供可检查的过程证据；要判断方法能否减少漏检、误改和阅读退步，还须重复测试与人工比较。
