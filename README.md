# 3dgs-pp - 3DGS Point Cloud Processing Tool

一个高效的 3D Gaussian Splatting PLY 文件处理工具，支持懒加载、终端交互式浏览和空间分块功能。

## 功能特性

- **懒加载读取**：无需一次性加载整个文件，支持超大文件（>10GB）处理
- **终端浏览**：交互式查看高斯点数据，支持翻页、搜索、跳转
- **空间分块**：按 X/Y/Z 方向分割点云，导出为多个 PLY 文件
- **高斯椭球过滤**：按数值、百分位、范围条件过滤点云，支持多条件组合
- **高斯椭球下采样**：支持多种采样方法（均匀、不透明度、随机、体素）
- **属性统计分析**：支持统计、分布图绘制、快捷键切换查看
- **坐标平移**：支持具体数值和统计量关键字，各轴独立或统一定义
- **轴变换**：支持轴对换、轴自反、nπ/2 旋转，同步变换坐标、四元数和缩放
- **空间裁剪**：按两点式（AABB）或八点式（凸六面体）裁剪点云，支持反向选择
- **空间填充**：将源 PLY 的点填充到目标 PLY 的指定区域，支持偏移量对齐

## 安装

```bash
# 使用 uv 安装依赖
uv sync
```

## 使用方法

### 1. 查看文件信息 (`info`)

```bash
uv run 3dgs-pp info scene.ply
```

显示文件的元数据、属性列表和包围盒信息。

### 2. 终端交互式浏览 (`view`)

```bash
uv run 3dgs-pp view scene.ply
uv run 3dgs-pp view --page-size 50 --full scene.ply
```

**交互控制**：
- `j` / `↓`：下一页
- `k` / `↑`：上一页
- `g` / `Home`：第一页
- `G` / `End`：最后一页
- `:N`：跳转到第 N 页
- `/搜索词`：搜索
- `e`：展开/折叠完整属性
- `q`：退出
- `?`：显示帮助

### 3. 空间分块 (`split`)

```bash
uv run 3dgs-pp split "2*3*2" scene.ply
uv run 3dgs-pp split --output-dir ./blocks "4*4*4" scene.ply
```

分块规格格式：`Nx*Ny*Nz`，例如 `2*3*2` 表示 X 方向 2 块，Y 方向 3 块，Z 方向 2 块。

注意：分块规格需要用引号括起来，避免 shell 解释 `*` 通配符。

### 4. 高斯椭球过滤 (`filter`)

```bash
# 过滤掉 opacity 低于 5% 分位数的椭球
uv run 3dgs-pp filter --filter "opacity<P5" scene.ply

# 多条件过滤（OR 逻辑：满足任一即过滤）
uv run 3dgs-pp filter --filter "opacity>0.1" --filter "scale_0<P10" scene.ply

# 多条件 AND 逻辑（同时满足才过滤）
uv run 3dgs-pp filter --and --filter "opacity<0.01" --filter "z>100" scene.ply

# 保留模式：仅保留 opacity > P5 的椭球
uv run 3dgs-pp filter --keep --filter "opacity>P5" scene.ply

# 范围过滤：过滤掉 x 不在 [-50, 50] 范围内的椭球
uv run 3dgs-pp filter --filter "x!~[-50,50]" scene.ply

# 指定输出文件
uv run 3dgs-pp filter --filter "opacity<P5" --output result.ply scene.ply

# 使用派生属性过滤
uv run 3dgs-pp filter --filter "volume<P5" scene.ply
uv run 3dgs-pp filter --filter "sphericity>0.9" scene.ply
uv run 3dgs-pp filter --and --filter "volume<P10" --filter "disceness<0.2" scene.ply

# 交互模式
uv run 3dgs-pp filter --interactive scene.ply
```

**过滤表达式格式**：

| 操作符 | 示例 | 说明 |
|--------|------|------|
| `>`, `>=`, `<`, `<=`, `==`, `!=` | `opacity>0.1`, `x<=0` | 数值比较 |
| `>P`, `>=P`, `<P`, `<=P` | `opacity<P5`, `scale_0>=P90` | 百分位比较 |
| `~` | `x~[-10,10]` | 介于数值范围（含边界） |
| `!~` | `x!~[-10,10]` | 不介于数值范围 |
| `~P` | `opacity~P[5,95]` | 介于百分位范围 |
| `!~P` | `z!~P[10,90]` | 不介于百分位范围 |

**派生属性**（间接参数，基于 `scale_0/1/2` 实时计算）：

| 属性名 | 说明 | 计算方式 |
|--------|------|----------|
| `volume` | 椭球体积（成正比） | `exp(s0)*exp(s1)*exp(s2)` |
| `longest_axis` | 最长半轴长度 | `max(exp(s0), exp(s1), exp(s2))` |
| `shortest_axis` | 最短半轴长度 | `min(exp(s0), exp(s1), exp(s2))` |
| `sphericity` | 接近圆球程度，[0,1] | 排序后 `最短/最长` 半轴比 |
| `disceness` | 接近圆盘程度，[0,1] | 排序后 `最短/中位` 半轴比 |
| `rodness` | 接近棒针程度，[0,1] | 排序后 `中位/最长` 半轴比 |

派生属性可以与原始属性（如 `opacity`, `x`, `y`, `z`）在过滤表达式中自由组合。

**选项**：
- `--filter` / `-f`：过滤表达式（可重复指定多次）
- `--and`：多条件使用 AND 逻辑（默认 OR）
- `--keep`：反转逻辑，保留匹配的点而非丢弃
- `--output` / `-o`：输出文件路径（默认：`{原文件名}_filtered.ply`）
- `--interactive` / `-i`：交互模式

**交互控制**：
- `Enter`：输入过滤表达式
- `Esc`：删除最后一个过滤条件
- `a` / `←`：上一个属性
- `d` / `→`：下一个属性
- `w`：切换 AND/OR 逻辑
- `k`：切换保留/丢弃模式
- `c`：清除所有过滤条件
- `s`：保存过滤结果
- `q`：退出
- `?`：显示帮助

### 5. 高斯椭球下采样 (`downsample`)

```bash
# 按比例下采样（保留 50%）
uv run 3dgs-pp downsample --ratio 0.5 scene.ply

# 按数量下采样（保留 10000 个）
uv run 3dgs-pp downsample --count 10000 scene.ply

# 指定采样方法和输出文件
uv run 3dgs-pp downsample --ratio 0.3 --method opacity --output scene_small.ply scene.ply
```

**采样方法**：
- `uniform`：均匀采样（默认，简单高效）
- `opacity`：基于不透明度采样（优先保留重要的点）
- `random`：随机采样（可指定 `--seed` 保证可复现）
- `voxel`：体素聚类采样（保持空间分布均匀性）
- `merge`：高斯椭球合并（平滑合并临近高斯，保持视觉质量）

### 6. 属性统计分析 (`stat`)

```bash
# 交互式统计模式（默认查看第一个数值属性）
uv run 3dgs-pp stat scene.ply

# 指定默认查看的属性
uv run 3dgs-pp stat --attr opacity scene.ply

# 非交互模式：展示所有核心属性统计对比
uv run 3dgs-pp stat --all scene.ply

# 绘制指定属性的分布图并保存
uv run 3dgs-pp stat --attr opacity --plot scene.ply

# 批量绘制核心属性箱线图
uv run 3dgs-pp stat --all --plot --type box --output-dir ./charts scene.ply
```

**交互控制**：
- `a` / `←`：上一个属性
- `d` / `→`：下一个属性
- `s`：切换单属性详细 / 多属性对比模式
- `f`：全屏查看所有属性统计对比
- `o`：保存当前统计信息到文本文件
- `p`：绘制当前属性分布图
- `P`（Shift+p）：批量绘制核心属性分布图
- `q`：退出
- `?`：显示帮助

**统计指标**：Min、Max、Mean、Std、Median、Q1/Q2/Q3、5%/10%/20%/50%/90%/95% 分位数、偏度、峰度

**图表类型**：
- `histogram`：直方图 + KDE 曲线（默认）
- `box`：箱线图
- `violin`：小提琴图

### 7. 坐标平移 (`translate`)

```bash
# 具体数值平移（X +10，Y -5，Z 不变）
uv run 3dgs-pp translate --x 10 --y -5 scene.ply

# 所有轴统一平移
uv run 3dgs-pp translate --all mean scene.ply

# 各轴分别使用统计量
uv run 3dgs-pp translate --x mean --y median --z center scene.ply

# 按最小/最大值平移
uv run 3dgs-pp translate --all min scene.ply
uv run 3dgs-pp translate --x min --y max scene.ply

# 混合模式（数值 + 统计量）
uv run 3dgs-pp translate --x 10 --y mean --z P50 scene.ply

# 指定输出文件
uv run 3dgs-pp translate --all mean --output centered.ply scene.ply

# 交互模式
uv run 3dgs-pp translate --interactive scene.ply
```

**平移量指定方式**：

| 方式 | 示例 | 说明 |
|------|------|------|
| 具体数值 | `--x 10` | 直接加上该数值 |
| `min` | `--x min` | 减去该轴最小值（下边界对齐原点） |
| `max` | `--x max` | 减去该轴最大值（上边界对齐原点） |
| `mean` | `--x mean` | 减去该轴均值（数据中心化） |
| `median` | `--x median` | 减去该轴中值 |
| `center` | `--x center` | 减去包围盒中心 `(min+max)/2` |
| `P<N>` | `--x P50` | 减去该轴 N% 分位数 |

**选项**：
- `--all VAL`：所有轴统一应用同一平移量（与 `--x/--y/--z` 互斥）
- `--x VAL` / `--y VAL` / `--z VAL`：各轴独立设定，未指定轴默认为 0
- `--output` / `-o`：输出文件路径（默认：`{原文件名}_translated.ply`）
- `--interactive` / `-i`：交互模式
- 数值与统计量关键字可在 `--x/--y/--z` 中自由混合使用

**交互控制**：
- `x` / `y` / `z`：切换操作轴
- `<` / `>`：设为 min / max
- `m` / `d` / `c`：设为 mean / median / center
- `p`：输入百分比分位数
- `n`：输入具体数值
- `a`：当前轴设置应用到所有轴
- `r`：重置所有偏移
- `Enter`：确认并写入文件
- `q`：退出

### 8. 轴变换 (`transform`)

```bash
# 轴对换（镜像）：沿 x=y 平面镜像
uv run 3dgs-pp transform --swap xy scene.ply

# 轴对换（镜像）：沿 x=-y 平面镜像
uv run 3dgs-pp transform --swap nxy scene.ply

# 轴自反（镜像）：沿 yz 平面镜像（x 取反）
uv run 3dgs-pp transform --inv x scene.ply

# 轴自反（镜像）：沿 xy 平面镜像（z 取反）
uv run 3dgs-pp transform --inv z scene.ply

# 绕 z 轴旋转 90°
uv run 3dgs-pp transform --rot z 90 scene.ply

# 绕 z 轴旋转 180°
uv run 3dgs-pp transform --rot z 180 scene.ply

# 绕 x 轴旋转 270°
uv run 3dgs-pp transform --rot x 270 scene.ply

# 通用映射表达式：等价于绕 z 轴旋转 90°
uv run 3dgs-pp transform --transform "x->y,y->-x,z->z" scene.ply

# 指定输出文件
uv run 3dgs-pp transform --rot z 90 --output rotated.ply scene.ply

# 交互模式
uv run 3dgs-pp transform --interactive scene.ply
```

**变换类型**：

| 参数 | 示例 | 说明 |
|------|------|------|
| `--swap AXES` | `xy`, `nxy`, `xz`, `nxz`, `yz`, `nyz` | 轴对换（镜像），`n` 前缀表示负号 |
| `--inv AXIS` | `x`, `y`, `z` | 轴自反（镜像），单轴取反 |
| `--rot AXIS ANGLE` | `z 90`, `y 180`, `x 270` | 绕轴 nπ/2 旋转（右手定则） |
| `--transform EXPR` | `x->y,y->-x,z->z` | 通用映射表达式 |

`--swap`、`--inv`、`--rot`、`--transform` 四选一，不可同时指定。

**四元数同步变换**：坐标变换时，四元数虚部 `(rot_1, rot_2, rot_3)` 按相同规则变换。镜像变换（`--swap`、`--inv`）额外取四元数共轭以镜像旋转方向；纯旋转（`--rot`）不取共轭。`rot_0`（w）始终不变。

**缩放同步变换**：`scale_0/1/2` 按坐标轴相同规则做轴置换，但不取符号（scale 为大小，始终为正）。

**选项**：
- `--output` / `-o`：输出文件路径（默认：`{原文件名}_transformed.ply`）
- `--interactive` / `-i`：交互模式

**交互控制**：
- `s`：轴对换模式，选择轴对和符号
- `v`：轴自反模式，选择单轴取反
- `r`：旋转模式，选择旋转轴和角度
- `t`：输入通用映射表达式
- `Enter`：确认并写入文件
- `q`：退出

### 9. 空间裁剪 (`crop`)

```bash
# 两点式（AABB）：裁剪出指定区域内的点
uv run 3dgs-pp crop --p1 -10,-5,0 --p2 10,5,20 scene.ply

# 两点式：保留区域外的点
uv run 3dgs-pp crop --p1 -10,-5,0 --p2 10,5,20 --outside scene.ply

# 八点式（凸六面体）：裁剪出不规则区域内的点
uv run 3dgs-pp crop \
  --p1 0,0,0 --p2 10,0,0 --p3 10,10,0 --p4 0,10,0 \
  --p5 2,2,20 --p6 8,2,20 --p7 8,8,20 --p8 2,8,20 \
  scene.ply

# 指定输出文件
uv run 3dgs-pp crop --p1 -10,-5,0 --p2 10,5,20 --output region.ply scene.ply
```

**区域指定方式**：

| 方式 | 参数 | 说明 |
|------|------|------|
| 两点式 | `--p1 x,y,z --p2 x,y,z` | 轴对齐包围盒，p1 为最小角点，p2 为最大角点 |
| 八点式 | `--p1~--p8 x,y,z` | 凸六面体，8 个顶点构成 6 个面 |

**选项**：
- `--p1`~`--p8`：区域顶点坐标，格式为 `x,y,z`
- `--outside`：保留区域外的点（默认保留区域内的点）
- `--output` / `-o`：输出文件路径（默认：`{原文件名}_cropped.ply`）

### 10. 空间填充 (`fill`)

```bash
# 两点式：将 source.ply 填充到 target.ply 的 AABB 区域
uv run 3dgs-pp fill --source source.ply --p1 -10,-5,0 --p2 10,5,20 target.ply

# 带偏移量填充
uv run 3dgs-pp fill --source source.ply --p1 -10,-5,0 --p2 10,5,20 --offset 5,0,0 target.ply

# 八点式目标区域
uv run 3dgs-pp fill \
  --source source.ply \
  --p1 0,0,0 --p2 10,0,0 --p3 10,10,0 --p4 0,10,0 \
  --p5 2,2,20 --p6 8,2,20 --p7 8,8,20 --p8 2,8,20 \
  target.ply
```

**填充流程**：
1. 对源 PLY 的所有点坐标应用偏移量 `(dx, dy, dz)`
2. 判断偏移后的点哪些落在目标区域内
3. 仅保留落入目标区域内的源点，追加到目标 PLY 中

**选项**：
- `--source FILE`：源 PLY 文件路径（必需）
- `--p1`~`--p8`：目标区域顶点坐标，格式为 `x,y,z`
- `--offset dx,dy,dz`：相对偏移量（默认：`0,0,0`）
- `--output` / `-o`：输出文件路径（默认：`{目标文件名}_filled.ply`）

**注意**：源 PLY 和目标 PLY 必须具有相同的属性结构（相同的属性列表和数据类型），否则会报错。

## 生成测试数据

```bash
# 生成 10000 个点的测试文件
uv run python -m threeds_pp.test_util test_data/sample.ply 10000
```

## 3DGS PLY 属性列表

- `x, y, z`：位置坐标
- `f_dc_0, f_dc_1, f_dc_2`：球面调和基直流分量
- `f_rest_0` 到 `f_rest_44`：球面调和基剩余分量（45个）
- `opacity`：不透明度
- `scale_0, scale_1, scale_2`：缩放
- `rot_0, rot_1, rot_2, rot_3`：旋转（四元数）

## 项目结构

```
3dgs-pp/
├── src/threeds_pp/
│   ├── ply/
│   │   ├── header.py       # PLY 头解析
│   │   ├── reader.py       # 懒加载读取器
│   │   └── writer.py       # PLY 写入器
│   ├── cli/
│   │   ├── info.py         # info 命令
│   │   ├── view.py         # view 命令
│   │   ├── split.py        # split 命令
│   │   ├── stat.py         # stat 命令
│   │   ├── filter.py       # filter 命令
│   │   ├── downsample.py   # downsample 命令
│   │   ├── translate.py    # translate 命令
│   │   ├── transform.py    # transform 命令
│   │   ├── crop.py         # crop 命令
│   │   └── fill.py         # fill 命令
│   ├── core/
│   │   ├── bounds.py       # 包围盒计算
│   │   ├── partition.py    # 空间分块
│   │   ├── stats.py        # 统计分析
│   │   ├── filter.py       # 高斯椭球过滤
│   │   ├── downsampler.py  # 下采样算法
│   │   ├── translate.py    # 坐标平移
│   │   ├── transform.py    # 轴变换
│   │   ├── crop.py         # 空间裁剪
│   │   └── fill.py         # 空间填充
│   └── main.py
├── pyproject.toml
└── README.md
```
