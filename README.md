# 作家那支笔 | Writer Pen

一个用于中文写作与改稿的 Skill。可以把一段经历写成小说，用采访材料写人物特写，也可以让同一件事经由几个角色之口，说出不同的分量。

[看作品](#作品示例) · [安装并试写](#安装并试写) · [怎么改稿](#怎么改稿)

## 作品示例

| 文学写作 · 虚构 | 人物特写 · 纪实 | 创意文案 · 角色表达 |
| :--- | :--- | :--- |
| [![周一见](docs/images/example-literary.svg)](examples/zhou-yi-jian/README.md) | [![邓煜：以数学为生](docs/images/example-profile.svg)](examples/deng-yu/README.md) | [![经还在西边](docs/images/example-creative.svg)](examples/journey-team/README.md) |
| **[读《周一见》](examples/zhou-yi-jian/README.md)** | **[读《邓煜：以数学为生》](examples/deng-yu/README.md)** | **[读《经还在西边》](examples/journey-team/README.md)** |
| 他以为这段关系有了下文，连回家的票都叫室友先别买。看一篇短篇怎样写出误会，又不替另一个人解释。 | 一个从小喜欢数学的人，为什么认真考虑过去金融公司？从本人和身边人的回忆，写他的选择与犹豫。 | 取经团队要裁掉一人。五个角色各自开口，同样是说自己不能走，却不必照着同一份述职稿念。 |
| [原始提示词](examples/zhou-yi-jian/prompt.txt) · [改稿取舍](examples/zhou-yi-jian/README.md#为什么这样改) | [采访与资料出处](examples/deng-yu/README.md#采访与资料出处) · [离线刊物版](examples/deng-yu/story.html) | [初始提示词](examples/journey-team/prompt.txt) · [离线朗读排版](examples/journey-team/story.html) |

三篇都是多轮创作或改稿后的作品。点题名可直接在 GitHub 阅读全文；HTML 文件下载后可离线阅读。

## 安装并试写

**首次安装到 Codex：**

```bash
git clone https://github.com/BobbyYue/writer-pen.git ~/.codex/skills/writer-pen
```

已安装且使用 Git 克隆的副本，可在确认没有待保留的本地修改后，运行 `git -C ~/.codex/skills/writer-pen pull --ff-only`。其他安装方式请先备份本地改动，不要直接覆盖。

**选一句开始，把材料接在后面：**

- **写小说：**“用 writer-pen 把这段经历写成短篇。让读者自己看出两个人对这段关系的理解有什么不同。”
- **写真人：**“用 writer-pen 根据这些采访写一篇人物特写。挑一次有出处的选择展开，不补材料里没有的心理和对白。”
- **写创意文案：**“用 writer-pen 写三位角色对同一件事的陈述。让人不看名字也听得出是谁在说话。”

完整作品默认交付离线 HTML。只想讨论一处，也可以直接说：“只评这个开头，不重写。”

## 怎么改稿

**小说和散文**看人物在具体处境里会怎么做，比较改动对声音、关系和节奏的得失。**纪实人物稿**多一道事实判断：章节写“做选择”，正文究竟写出了本人的取舍，还是只列了后来取得的成绩？**创意文案**从读者、场合和说话的人出发决定结构，不把角色对话都写成轮流反驳。

[小说与散文的改稿方法](references/revise.md) · [纪实人物特写](references/nonfiction-profile.md) · [创意文案](references/creative-copywriting.md)

## 维护与许可

[执行与审读流程](references/workflow.md) · [测试说明](references/testing.md) · [已知限制](docs/known-limitations.md) · [版本记录](CHANGELOG.md)

本项目为预发布版。独立审读需要宿主提供调用能力；程序检查通过不等于读者一定喜欢作品。原创代码和文档采用 [MIT License](LICENSE)，外部采访和引用材料不在此许可范围内。
