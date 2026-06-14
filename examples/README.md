# 示例输入

这些示例用于本地无 Key 演示、Provider 冒烟测试和提示词回归测试。

每个目录都包含一个 `sample_input.json`，可以这样运行：

```bash
source .venv/bin/activate
python main.py canon-run --input examples/urban-fantasy/sample_input.json --output outputs/urban-fantasy-final-outline.md
```

当前示例：

- `urban-fantasy`：都市高武、规则和制度压迫。
- `xuanhuan`：玄幻升级、宗门政治和力量体系。
- `romance`：关系驱动、家族秘密和社会压力。

生成结果不提交到仓库，默认放在 `outputs/` 下。
