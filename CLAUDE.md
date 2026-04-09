# 3dgs-pp 项目配置

## 环境管理

- **包管理工具**: uv
- **Python 版本**: 3.12

## 快速开始

### 环境初始化

```bash
# 创建虚拟环境并安装依赖
uv venv --python 3.12
uv sync
```

### 运行项目

```bash
# 激活虚拟环境
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate  # Windows

# 运行命令
3dgs-pp --help
```

## 开发规范

### 代码风格
- 使用 black 格式化代码
- 使用 ruff 进行 lint 检查

### 提交规范
- 提交信息使用英文
- 不要自动提交 git，只有用户明确要求时才提交
- 不要自动推送到 GitHub，只有用户明确要求时才推送

## 项目结构

```
3dgs-pp/
├── src/
│   └── 3dgs_pp/
│       ├── ply/
│       ├── cli/
│       ├── core/
│       └── __init__.py
├── tests/
├── pyproject.toml
├── uv.lock
└── README.md
```
