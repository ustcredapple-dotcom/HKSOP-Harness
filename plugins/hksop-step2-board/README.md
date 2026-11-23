# 二维面包板布局

输入第一步的 `trace.json` 或通过体检的 `graph.py`。Python 源输入加 `--func build_graph`。通过 `HKSOP_ROOT` 指定只读库，也可自动探测相邻的 HKSOP 本体目录。程序从精简清单和 curation 选型，从同版目录取实测轮廓。随插件携带所需的光学文件读取与追迹代码。输出 project.zzoptics.json、七层工程图、六步审阅页、BOM 和定制件需求。原生 verify 与 export 的结果保存在输出目录；可用 `python3 "$HKSOP_ROOT/hksop.py" serve` 打开编辑器。

本机原生复验依次试用 `HKSOP_NODE`、库内 `config/local-environment.json` 指定的 Node、DeepSeek Harness 自带 Node 和 `PATH` 中的 Node。只有当前进程能够读取并实际启动的解释器才会传给原生工具。
