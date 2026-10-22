# 逐条“出现”动画

## 语义与创作约束

每页按阅读顺序划分逻辑条目：段落、bullet point 或同一条的文字与附图。第一条从进入页面开始直接可见，不添加入场动画。第二条及以后使用 PowerPoint 原生“出现”（Appear），每次单击显示下一条，已出现的条目保持可见。标题、绘画、黑色蒙版、页码与常驻来源不参与逐条入场。只有一条内容的页面不需要入场动画。此要求与整页切换效果无关。

不要把自然换行、一个条目内部的软换行或同一段的续行当成多个条目。新稿创作时，为每个逻辑条目建立独立的可编辑文本框或形状，并设置稳定且唯一的名称，例如 `kratz_s03_item02_text`。英文段落继续使用原生悬挂缩进。若 bullet 是独立形状，应与本条正文共同出现。

同一条目由多个形状组成时，首个形状使用 `OnPageClick`，本条其余形状使用 `WithPrevious`，延迟为0。不得让本条各个形状分别消耗一次点击。使用原生入场效果，不用把整页截图复制成多页来模拟。

## 本地辅助脚本

`scripts/apply_appear.py` 需要 Windows、桌面版 Microsoft PowerPoint，以及 Python 的 `pywin32` 包：

```powershell
python -m pip install pywin32
python scripts/apply_appear.py --help
python scripts/apply_appear.py draft.pptx items.json animated.pptx --report animation-check.json
```

输入、输出和报告可使用绝对路径；路径含空格时加引号。输出必须是尚不存在的新 `.pptx` 文件，脚本先创建独立临时物理副本，以只读方式打开该副本，再保存输出；即使用户已打开同一源文件，也不复用并关闭用户的文稿对象。脚本关闭自己打开的演示文稿，不调用 PowerPoint 的 `Quit()`，不关闭用户原本打开的文稿，也不改变应用窗口或全局设置。若 PowerPoint 原本未运行，它可能在处理结束后保留一个无文稿的后台实例，由系统管理；不要为清理脚本而终止用户进程。

脚本只按显式清单操作，不自动从文本、换行、坐标或字号猜测条目。目标页面如果已有任何主序列或交互序列动画，脚本会明确报冲突，不清空整页动画，也不默默追加到已有点击序列之后。重复对已处理文件运行同样会报冲突。需要重新生成时从加动画前的干净源文件开始；已有复杂动画的文稿须明确核对并调整该页，再使用本脚本。未列入清单的页面保持原有动画。

没有 Windows PowerPoint 时，应选择确实能生成原生入场动画的工具并核验；如果无法做到，交付时明确动画未实现，不能把静态图片或转场称为已实现的逐条“出现”。

## 清单格式

```json
{
  "version": 1,
  "slides": [
    {
      "slide": 3,
      "items": [
        {"id": "first", "shapes": ["kratz_s03_item01_text"]},
        {"id": "second", "shapes": ["kratz_s03_item02_bullet", "kratz_s03_item02_text"]},
        {"id": "third", "shapes": ["kratz_s03_item03_text", "kratz_s03_item03_figure"]}
      ]
    }
  ]
}
```

- `slide` 是演示文稿当前顺序中的页码，从1开始。不要使用 ZIP 包内 XML 文件编号来推断页序。
- `items` 的数组顺序就是讲述顺序；每页至少一项，每项 `id` 唯一。第一项不会生成任何动画。
- `shapes` 是同页顶层形状的准确名称，每个名称仅能归属一个条目。分组内部子对象不能直接按子对象名称定位；可以将一个完整分组作为一个逻辑对象，或在创作时保持独立顶层形状。
- 静态标题、背景、蒙版等不列入 `items`。未列入清单的静态对象仍显示；作者需要确保逻辑条目清单完整，否则遗漏条目会从开页即显示。
- 清单是实际内容编排的一部分，由创作者在制作文本框时一并生成；不要在后处理时无依据推测。

## 核验与证据边界

脚本先检查所有目标页，再添加效果。保存后重新用 PowerPoint COM 打开输出，逐项核对效果数量、顺序、目标对象、`EffectType=1`、触发方式、零延迟、`Exit=0` 和 `AfterEffect=0`。随后检查 OOXML `p:timing` 的目标对象与预期完全一致，确保第一条与静态对象不被动画引用。报告明确写明这是 COM 与保存后 XML 参数验证，没有模拟实际放映。

实际交付时还应在目标 PowerPoint 中进入放映：开页确认第一条可见，逐次点击确认后续条目顺序与累计保留，同一条的多形状同步出现。PDF与静态渲染通常展示最终全显状态，不能据此验证逐次点击。只有实际做过放映检查时，才能报告放映通过；跨软件表现需另行实测。

## Microsoft 官方 API 依据

- [Sequence.AddEffect](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.sequence.addeffect)：创建序列中的原生效果，接受形状、效果、层级和触发方式。
- [Presentations.Open](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.presentations.open)：`ReadOnly=True` 以只读方式打开，`WithWindow=False` 不打开演示文稿窗口。脚本先创建物理副本，因为实际测试发现仅靠 `Untitled=True` 不能保证隔离已打开的同源文稿对象。
- [MsoAnimEffect](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.msoanimeffect)：`msoAnimEffectAppear = 1`。
- [MsoAnimTriggerType](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.msoanimtriggertype)：`msoAnimTriggerOnPageClick = 1`、`msoAnimTriggerWithPrevious = 2`。
- [MsoAnimateByLevel](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.msoanimatebylevel)：`msoAnimateLevelNone = 0`，按整个独立形状处理，不重新按段落层级拆分。
- [Effect.Exit](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.effect.exit) 和 [EffectInformation.AfterEffect](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.effectinformation.aftereffect)：核对为入场效果，完成后不隐藏或变暗。
