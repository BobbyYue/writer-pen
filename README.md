# 作家那支笔 | Writer Pen

在 Codex 里写中文小说、散文、纪实人物特写和创意文案，也可以拿已有的稿子来改。

[看作品](#作品示例) · [安装并试写](#安装并试写) · [怎么改稿](#怎么改稿)

## 作品示例

| 小说与散文 | 纪实人物特写 | 创意文案 |
| :--- | :--- | :--- |
| 把一段经历写成故事。 | 从有出处的采访和细节写一个真人。 | 为一个主题找一种有辨识度的说法。 |
| [![周一见](docs/images/example-literary.svg)](examples/zhou-yi-jian/README.md) | [![邓煜：以数学为生](docs/images/example-profile.svg)](examples/deng-yu/README.md) | [![经还在西边](docs/images/example-creative.svg)](examples/journey-team/README.md) |
| **[读《周一见》](examples/zhou-yi-jian/README.md#周一见)** | **[读《邓煜：以数学为生》](examples/deng-yu/README.md)** | **[读《经还在西边》](examples/journey-team/README.md#经还在西边)** |
| 他以为这段关系有了下文，连回家的票都叫室友先别买。看一篇短篇怎样写出误会，又不替另一个人解释。 | 一个从小喜欢数学的人，为什么认真考虑过去金融公司？从本人和身边人的回忆，写他的选择与犹豫。 | 取经团队要裁掉一人。五个角色各自开口，同样是说自己不能走，却不必照着同一份述职稿念。 |
| [原始提示词](examples/zhou-yi-jian/prompt.txt) · [看改稿取舍](examples/zhou-yi-jian/README.md#为什么这样改) | [写作提示词（整理版）](examples/deng-yu/writing-prompt.md) · [看采访出处](examples/deng-yu/README.md#采访与资料出处) | [初始提示词](examples/journey-team/prompt.txt) · [看朗读排版](examples/journey-team/story.html) |

三篇都是多轮创作或改稿后的作品。点题名可直接在 GitHub 阅读全文；HTML 文件下载后可离线阅读。

## 安装并试写

**1. 在终端安装。** 已经安装过 writer-pen 的读者直接看第 2 步。首次安装，在终端运行：

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/BobbyYue/writer-pen.git ~/.agents/skills/writer-pen
```

**2. 打开 Codex，把下面整段发到对话里。** 不需要先准备素材。

```text
用 writer-pen 写一篇 300 字以内的短篇，只在对话里给正文。
素材：合租三年，室友搬走前把两把钥匙都留在了桌上。我下班回家，还是按了门铃。
```

想写真人，可以从[邓煜案例的提示词与采访材料](examples/deng-yu/writing-prompt.md)开始；想试角色表达，可以直接用[取经团队的设定](examples/journey-team/prompt.txt)。完整作品默认交付离线 HTML，也可以像上面一样指定只要正文。

<details>
<summary>已安装，怎样更新？找不到技能怎么办？</summary>

用 Git 安装且没有待保留的修改时，在**原安装目录**运行 `git pull --ff-only`。早期按本仓库说明安装的副本可能在 `~/.codex/skills/writer-pen`，不必再克隆第二份。手动安装的副本请先备份本地改动，不要直接覆盖。

首次安装后若没有出现 writer-pen，重启 Codex 再试。参见 [Codex 的技能目录说明](https://developers.openai.com/codex/skills/)。

</details>

## 怎么改稿

已经有稿子，不必从头生成。把原文贴进对话，说清楚你拿不准的地方：

- **[小说与散文](references/revise.md)**：“删掉最后一句，读者还能看出她为什么没进门吗？先比较，不改全文。”
- **[纪实人物特写](references/nonfiction-profile.md)**：“这一节叫‘他决定留下’，哪些材料写出了他的选择，哪些只是后来取得的成绩？”
- **[创意文案](references/creative-copywriting.md)**：“遮住名字，这三段还听得出是谁在说吗？只改最难分辨的一段。”

## 维护与许可

[执行与审读流程](references/workflow.md) · [测试说明](references/testing.md) · [已知限制](docs/known-limitations.md) · [版本记录](CHANGELOG.md)

本项目为预发布版。独立审读需要宿主提供调用能力；程序检查通过不等于读者一定喜欢作品。原创代码和文档采用 [MIT License](LICENSE)，外部采访和引用材料不在此许可范围内。
