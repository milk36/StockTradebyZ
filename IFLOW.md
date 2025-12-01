# Z哥战法股票量化交易系统

## 项目概述

这是一个基于Z哥战法的Python股票量化选股系统，主要用于A股市场的技术分析和选股策略实现。项目通过Tushare接口获取股票数据，实现了多种技术指标选股策略，包括少妇战法、SuperB1战法、补票战法、填坑战法和上穿60放量战法。

### 主要功能
- **数据获取**: 通过Tushare API获取A股日线数据（前复权）
- **策略选股**: 实现5种不同的技术分析选股策略
- **批量处理**: 支持对股票池进行批量选股分析
- **配置化**: 通过JSON配置文件管理策略参数

### 核心技术栈
- **Python**: 主要编程语言（支持3.11/3.12）
- **Pandas**: 数据处理和分析
- **NumPy/SciPy**: 数值计算和信号处理
- **Tushare**: 股票数据源
- **TQDM**: 进度条显示

## 项目结构

```
D:\GithubProjects\股票-量化\0_zgnb_StockTradebyZ\
├── configs.json             # 策略配置文件
├── fetch_kline.py           # 数据获取脚本
├── select_stock.py          # 选股主程序
├── Selector.py              # 策略实现模块
├── stocklist.csv            # 股票池文件
├── requirements.txt         # 项目依赖
├── 板块轮动提示词.md        # 板块分析提示词
├── README.md               # 项目说明文档
├── CLAUDE.md               # Claude相关文档
├── appendix.json           # 附录配置
├── SectorShift.py          # 板块轮动分析
├── find_stock_by_price_concurrent.py  # 价格筛选工具
├── data/                   # 数据存储目录
├── data_test/              # 测试数据目录
└── __pycache__/            # Python缓存目录
```

## 环境配置

### 依赖安装
```bash
# 创建虚拟环境
conda create -n stock python=3.12 -y
conda activate stock

# 安装依赖
pip install -r requirements.txt
```

### 主要依赖包
- pandas==2.3.0
- tqdm==4.66.4
- tushare==1.4.21
- scipy==1.14.1

### 环境变量配置
需要设置Tushare Token：
```bash
# Windows (PowerShell)
setx TUSHARE_TOKEN "你的token"

# macOS / Linux (bash)
export TUSHARE_TOKEN=你的token
```

## 核心模块说明

### 1. fetch_kline.py - 数据获取模块
- **功能**: 从Tushare获取A股日线数据（前复权）
- **输入**: stocklist.csv中的股票代码列表
- **输出**: CSV格式的K线数据文件到data目录
- **特性**: 
  - 支持并发下载（默认6线程）
  - 自动限流和重试机制
  - 支持排除创业板/科创板/北交所
  - 全量覆盖保存策略

### 2. Selector.py - 策略实现模块
包含5个主要选股策略：
- **BBIKDJSelector**: 少妇战法
- **SuperB1Selector**: SuperB1战法
- **BBIShortLongSelector**: 补票战法
- **PeakKDJSelector**: 填坑战法
- **MA60CrossVolumeWaveSelector**: 上穿60放量战法

通用指标函数：
- `compute_kdj()`: KDJ指标计算
- `compute_bbi()`: BBI指标计算
- `compute_rsv()`: RSV指标计算

### 3. select_stock.py - 选股主程序
- **功能**: 批量执行选股策略
- **输入**: data目录中的CSV数据 + configs.json配置
- **输出**: 控制台结果 + select_results.log日志

## 使用方法

### 1. 下载历史数据
```bash
python fetch_kline.py \
  --start 20240101 \
  --end today \
  --stocklist ./stocklist.csv \
  --exclude-boards gem star bj \
  --out ./data \
  --workers 6
```

### 2. 运行选股策略
```bash
python select_stock.py \
  --data-dir ./data \
  --config ./configs.json \
  --date 2025-09-10
```

## 配置说明

### configs.json 配置结构
每个策略包含以下字段：
- `class`: 策略类名
- `alias`: 策略别名
- `activate`: 是否激活
- `params`: 策略参数

### stocklist.csv 格式
包含股票基本信息：
- ts_code: Tushare股票代码
- symbol: 股票代码
- name: 股票名称
- area: 地区
- industry: 行业

## 开发规范

### 代码风格
- 使用类型注解
- 遵循PEP 8规范
- 函数和类添加docstring
- 使用相对导入

### 日志规范
- 使用logging模块
- 同时输出到控制台和文件
- 不同模块使用不同logger名称

### 错误处理
- 网络请求异常处理
- 数据验证和清洗
- 限流和重试机制

## 扩展开发

### 添加新策略
1. 在Selector.py中继承BaseSelector类
2. 实现select方法
3. 在configs.json中添加策略配置
4. 更新README文档

### 数据源扩展
- 支持其他数据源接口
- 实现数据格式标准化
- 添加数据质量检查

## 注意事项

1. **数据获取限制**: Tushare接口有频率限制，项目已实现限流机制
2. **免责声明**: 本项目仅供学习研究，不构成投资建议
3. **数据准确性**: 请确保Tushare Token有效且有足够权限
4. **风险提示**: 股市有风险，投资需谨慎

## 常见问题

### Q: 数据获取失败怎么办？
A: 检查Tushare Token是否正确，网络连接是否正常，是否触发频率限制

### Q: 如何调整策略参数？
A: 修改configs.json中对应策略的params字段

### Q: 选股结果为空？
A: 检查数据是否完整，策略参数是否合理，市场条件是否满足策略要求

---

*本项目基于@Zettaranc的Z哥战法实现，仅供学习交流使用。*