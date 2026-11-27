# 定制件设计与登记

从 `skills/custom-part-cad/scripts/parse_wishes.py` 读取需求，按 `custom-part-cad` 制作并按 `library-intake` 登记。首次入库与已有版本替换分别处理。需要实体几何时使用本机配置的 CadQuery 解释器。当前设计资料位于各技能的 `references/design-guides/`；两个技能共用 `shared/` 的俯视渲染和验收复用规则。非运行期旧资料保存在仓库 `docs/heritage-archive/`。交接正式器件编号、修订、资产 SHA256 和更新后的精简清单。
