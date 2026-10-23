# 写作阶段与独立审读

正常写作从 [统一入口](workflow.md) 开始；本页供底层排错与维护。
共同文学准则由 [审读方法](literary-review.md) 单处维护，初始化和独立审读材料自动包含同版本的角色要求。

实质创作和改稿在允许本地记录时使用。原有指定底稿、人物封存、clean净稿自查、comparison对照与取舍均保留。
无人物中心可在原生contract说明人物豁免，不豁免写前、写中、整稿计量或独立审读。
正文中的留白、多义、长句、生僻词和有作用的重复不设比例门槛，不要求读者猜出唯一主题。

下文`W`为`scripts/writing_run.py`，`L`为`scripts/writing_lifecycle.py`；`RUN`存`run.json`，`LIFE`存`lifecycle.json`。
同任务修订保留同一`LIFE`和累计轮数，不能另建目录假装第一次评审。
字段、十项标准的计量边界与真实版面输入见[记录协议](writing-quality-records.md)；日常只读取本次生成的task-packet。

## 写前与写中

1. 先准备plan，运行`python3 L init LIFE --plan plan.json --profile literary`；引用已有材料时加`--source 材料路径`。
   在登记单元前按[受管执行](writing-execution.md)初始化稳定宿主任务ID，使用自动派发与原始返回，不手填调用证明。
   plan声明task、genre、domain、purpose、scope、language、format，reader的knowledge/need，authority的status/basis/reference，
   material的mode/gaps，literary_intent、writing_basis、constraints、reading_path（含id/purpose）；author_context_id记录作者会话标识。
   writing_basis在原计划内分开given、interpretations、choices，具体格式见记录协议；不把解释或风格选择写成用户硬限制。
   purpose直接复用原生contract.goal，scope显式复用contract.scope；不另写近义口径，登记与最终出口都会核对一致性。
   literary_intent只描述本篇具体目标，不承担转述通用方法的职责，不预填审读结论，也不发送给独立读者。
   初始化保存方法摘要，专业包自动带共同准则和反应程度权威段，读者包只带中性阅读问题。
   authority暂为provisional或关键材料缺口未收窄时不能确认完成，不捏造用户授权。
2. 按原有流程init原生RUN、封存人物，再`python3 W prepare RUN --lifecycle-run LIFE --record 人物.record.json --reason 写前理解`。
   人物豁免时省略record；prepare核对literary写前记录，人物封存的时间声明仍须真实。
3. 按实际场景、段落或片段登记写中检查：`python3 L unit LIFE --text 单元.md --record unit.json`。
   unit.json含unit_id、summary、observations（quote/reason），引用实际正文。不是写完后补一句“已检查”。
4. `python3 W draft RUN --lifecycle-run LIFE --checkpoint 单元ID --id v1 --file 正文.md`。
   checkpoint必须已登记且其当前单元仍在本版正文；新稿先复核受影响单元，不能续用过期checkpoint。
   全文候选登记还会核对reading_path中的所有单元，不是提供一个ID就跳过其他场景。

## 整稿与两名独立审读者

先完成当前稿的clean/comparison自查及decide，按[执行说明](execution.md)保留封存对照与问题处理。
随后：

```bash
python3 L measure LIFE --text 正文.md --output measure-v1.json
python3 L candidate LIFE --artifact 正文.md --text 正文.md --report measure-v1.json --record assessment-v1.json
python3 L review-start LIFE --artifact 正文.md --stage after
```

assessment记录各计量维度的正文观察（metrics/quote/reason）或有理由的not_applicable，
并对每个signal_id登记dispositions（retain/pending及reason）。修过正文须重新计量，不把仍存在的提示标为已删除。
优先填写measure自动生成的`REPORT.assessment.json`模板，保留其中真实的text_sha256与report_sha256，不沿用旧稿摘要。
计量是待审线索，不是文学质量分。适用真实版面的载体还须登记layout与原始版面依据；
纯文本通过不能代表HTML、飞书、Word等已核对。

review-start返回本轮professional和reader隔离packet的路径与摘要。实际派给两个fresh上下文，
分别只提供对应packet；reader不接收作者意图、预设答案、人物分析、专业审稿意见或已有自查结论。
专业审稿检查人物知情、内部关系、声音与语言；读者复述读到的人事、记住的细节和不确定处，给正文依据。
作者在进入独立审读前按 [反应程度检查](character-first.md#反应的程度是否有支撑) 处理疑点，
已有意见若只肯定表达用途或念头归属，仍须回到触发和关系核对；不能据此关闭可信度问题。
作者的clean/comparison不算独立角色。context_id不同及packet匹配只提供可核验声明，不能证明真实身份或人类共鸣。

两名角色按各自实际材料包和程序附带的结果格式返回，不手填PASS或复制一份省略必填字段的通用示例。
专业角色须完成context_review与source_attribution；读者须完成attribution_replay及分开理解与体验的reading_response，格式见记录协议。
基础格式与分级在`scripts/review_findings.py`单处维护，并由实际调用入口自动加入提示。
两者context必须彼此不同、不等于作者、且未用于本任务以往轮次；身份由实际调用绑定。

- issues保留必须处理的问题；旧协议的issues仍是阻塞项，不降级为建议来取得pass。
- editorial用于有正文依据的编辑取舍，返回id、impact、reason和当前稿精确quote；不改变审稿者原verdict。
  作者必须另记retain/revise/defer、理由和正文依据。retain附执行说明中的trial，实际比较文字与注意力代价后可保留当前处理；revise/defer仍未解决。
  每项选择绑定稿件、角色和真实审稿返回摘要，换稿、换角色或换审稿记录后不可复用。
- suggestions是同结构的可选建议，不自动阻塞，不要求凑出建议或逐条接受。

统一入口先导入真实结果，若有未决定的editorial则保持本轮开启，等待author-choice后继续finish-review。
这不增加审读轮次，也不能改写原审稿返回；决定修改时结束本轮并按原流程重新登记新稿，仍累计三轮。

```bash
python3 W review RUN --file professional-v1.json
python3 W review RUN --file reader-v1.json
python3 W review-result RUN --to result-v1.json
python3 L review-finish LIFE --result result-v1.json --verdict pass
python3 W check RUN --lifecycle-run LIFE
python3 W deliver RUN --lifecycle-run LIFE --to 新净稿.md
```

review-result根据真实角色记录和原生自查汇总；有问题时用fail结束本轮。已有同一份原生汇总可用`review-result RUN --file 结果.json`绑定，
它核对两名角色与未决问题，不能导入一枚PASS替代审稿。最终核对传递此同一路径给生命周期，不只比文件名或文字相似。
新增评审、改稿或改证据都会使旧结果失效；修稿重新登记、净读、对照、计量并开始下一轮。
同一批专业与读者评审合计一轮，写中与写后共用三轮上限，不各算三轮。

## 三轮后仍未通过

同任务已完成三轮、最后一轮绑定当前稿且仍为fail并有未决问题时，可用
`check RUN --lifecycle-run LIFE --draft`和`deliver RUN --lifecycle-run LIFE --draft --to 草稿.md`。
不要求三轮全部fail；早先版本曾pass不能掩盖当前回归，也不能阻止展示当前稿。
仍须有当前稿的自查、独立结果与处置记录；取舍可登记defer/retry，不能用draft掩盖缺阶段、旧正文或旧证据。
导出正文保持原字节，同时生成`草稿.md.notice.json`，状态为`review-incomplete-draft`，载明未决问题；
这不是当前稿独立通过，也不授权发布。
交付时在正文之外说明未完成，询问先处理哪个问题或调整什么方向，不开启第四轮。

## 核对边界与维护接口

低层`check_records()`只核对原生局部记录，`record_checks_satisfied`不代表完整流程；最终check/deliver无免检开关。
完整pass仍只核对登记过程、版本与证据，不证明实际生成顺序、认真阅读、审美共识或文学提升。
本包不安装宿主钩子，不自动发布，不将正文或评审收进公共案例。

维护时同时检查登记入口与最终出口：前者核对写前记录、当前单元及隔离材料，后者核对同一版本的原生汇总和全部阶段。
`--final`另核对实际目标文件的字节；新导出路径不能冒充已登记候选。
