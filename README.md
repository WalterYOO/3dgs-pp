# 3dgs-pp - 3DGS Point Cloud Processing Tool

一个高效的 3D Gaussian Splatting PLY 文件处理工具，支持懒加载、终端交互式浏览和空间分块功能。

## 功能特性

- **懒加载读取**：无需一次性加载整个文件，支持超大文件（>10GB）处理
- **终端浏览**：交互式查看高斯点数据，支持翻页、搜索、跳转
- **空间分块**：按 X/Y/Z 方向分割点云，导出为多个 PLY 文件
- **高斯椭球下采样**：支持多种采样方法（均匀、不透明度、随机、体素）

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

### 4. 高斯椭球下采样 (`downsample`)

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
│   │   └── downsample.py   # downsample 命令
│   ├── core/
│   │   ├── bounds.py       # 包围盒计算
│   │   ├── partition.py    # 空间分块
│   │   └── downsampler.py  # 下采样算法
│   └── main.py
├── pyproject.toml
└── README.md
```
