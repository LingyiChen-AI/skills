# 排版格式测试：这是一篇用来验证 wechat-typeset 输出的文章

这是第一段正文，用来确认段落的字号、行高和颜色是否被正确注入。段落里包含**加粗文本**、*斜体文本*、`行内代码`，以及一条[外部链接](https://publish.raphael.app)。

标点粘连测试：**重点提示**：加粗后面紧跟的全角冒号不应该被换行拆开。*强调*，逗号同理。

## 二级标题：验证标题不继承正文的强调样式

标题里的 **加粗** 和 `代码` 应该继承标题自身颜色，而不是正文里那套背景色处理。

### 三级标题

#### 四级标题

## 列表

无序列表：

- 第一项，短文本
- 第二项，带**加粗**和 `code`
- 第三项，这一项特意写得长一些，用来确认换行之后的缩进和行高是否还正常，不会出现悬挂错位的情况
  - 嵌套子项一
  - 嵌套子项二

有序列表：

1. 步骤一：打开编辑器
2. 步骤二：粘贴内容

   这是列表项里的独立段落，渲染时应该被降级成 `span`，否则微信会把它拆成新块。
3. 步骤三：核对排版

## 引用

> 这是一段引用文本，用来确认左边框、内边距和背景色是否生效。
> 引用里也可能出现**加粗**。

## 代码块

```python
def typeset(markdown: str, theme: str = "apple") -> str:
    """把 Markdown 转成微信可直接粘贴的内联样式 HTML。"""
    html = render(markdown)
    return make_wechat_compatible(html, theme)
```

无语言标注的代码块：

```
$ node render.mjs article.md --theme claude --out article.html
typeset 排版格式测试
```

## 表格

| 主题 ID | 名称 | 适用场景 |
| --- | --- | --- |
| `apple` | Mac | 日常记录，极致留白 |
| `claude` | Claude | 深度长文、文学哲思 |
| `wechat` | 微信原生 | 与平台默认观感一致 |

## 图片

![测试图片](https://cdn.jsdelivr.net/gh/LingyiChen-AI/images/wx-content-cdn/images/2026/04/20260411-9e8d0b-img_01.png)

连续两张图片，应该被合并成并排表格布局：

![左图](https://cdn.jsdelivr.net/gh/LingyiChen-AI/images/wx-content-cdn/images/2026/04/20260411-9e8d0b-img_01.png)

![右图](https://cdn.jsdelivr.net/gh/LingyiChen-AI/images/wx-content-cdn/images/2026/04/20260411-9e8d0b-img_02.png)

---

分隔线上方结束。最后一段用来确认文末不会多出空白块。
