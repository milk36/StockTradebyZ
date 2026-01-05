# Z哥战法股票量化交易系统

## 项目概述

这是一个基于Z哥战法的Python股票量化选股系统，主要用于A股市场的技术分析和选股策略实现。项目通过Tushare接口获取股票数据，实现了多种技术指标选股策略，包括少妇战法、SuperB1战法、补票战法、填坑战法和上穿60放量战法。

### 主要功能
- **数据获取**: 通过Tushare API获取A股日线数据（前复权）
- **策略选股**: 实现5种不同的技术分析选股策略
- **批量处理**: 支持对股票池进行批量选股分析
- **配置化**: 通过JSON配置文件管理策略参数
- **板块轮动**: 提供板块轮动分析和提示词模板
- **价格筛选**: 支持按历史价格区间筛选股票
- **并发处理**: 使用多进程/多线程提升处理性能

### 核心技术栈
- **Python**: 主要编程语言（支持3.11/3.12）
- **Pandas**: 数据处理和分析
- **NumPy/SciPy**: 数值计算和信号处理
- **Tushare**: 股票数据源
- **TQDM**: 进度条显示
- **多进程/多线程**: 并发处理提升性能

## 项目结构

```
D:\GithubProjects\股票-量化\0_zgnb_StockTradebyZ\
├── configs.json             # 策略配置文件
├── fetch_kline.py           # 数据获取脚本
├── select_stock.py          # 选股主程序
├── Selector.py              # 策略实现模块
├── stocklist.csv            # 股票池文件
├── requirements.txt         # 项目依赖
├── 板块轮动提示词.md        # 板块分析提示词模板
├── README.md               # 项目说明文档
├── CLAUDE.md               # Claude相关文档
├── appendix.json           # 附录配置
├── SectorShift.py          # 板块轮动分析模块
├── find_stock_by_price_concurrent.py  # 价格筛选工具
├── data/                   # 数据存储目录
├── doc/                    # 文档目录
│   ├── fetch_kline_usage.md    # 数据获取详细使用说明
│   └── *.pdf                  # Z哥战法相关PDF文档
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
  - **新增**: 市值筛选功能（min-market-cap, max-market-cap）
  - **新增**: ST股票剔除功能（默认启用）
  - **新增**: 详细的参数说明和使用场景文档

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

### 4. SectorShift.py - 板块轮动分析模块
- **功能**: 板块轮动分析和行业数据处理
- **特性**: 
  - 从stocklist.csv加载行业信息
  - 支持多种数据格式（CSV、feather、parquet、pkl）
  - 提供板块轮动分析框架

### 5. find_stock_by_price_concurrent.py - 价格筛选工具
- **功能**: 按历史价格区间筛选股票
- **特性**:
  - 支持收盘价、最高价、最低价筛选
  - 多进程/多线程并发处理
  - 时间区间灵活配置
  - 性能统计和错误处理

## 使用方法

### 1. 下载历史数据
```bash
# 基础用法
python fetch_kline.py --start 20240101 --end today --workers 6

# 市值筛选（50-2000亿）
python fetch_kline.py --start 20240101 --end today --min-market-cap 50 --max-market-cap 2000

# 排除特定板块
python fetch_kline.py --start 20240101 --end today --exclude-boards gem star bj

# 包含ST股票
python fetch_kline.py --start 20240101 --end today --include-st

# 自定义输出目录
python fetch_kline.py --start 20240101 --end today --out ./my_data --workers 8
```

### 2. 运行选股策略
```bash
python select_stock.py \
  --data-dir ./data \
  --config ./configs.json \
  --date 2025-09-10
```

### 3. 价格筛选
```bash
# 查找历史价格在指定区间的股票
python find_stock_by_price_concurrent.py \
  --data-dir ./data \
  --start-date 20240101 \
  --end-date 20241231 \
  --min-price 10.0 \
  --max-price 50.0 \
  --price-type close
```

### 4. 板块轮动分析
```python
# 使用SectorShift模块进行板块分析
from SectorShift import analyze_sector_rotation

# 分析板块轮动
results = analyze_sector_rotation(data_dir="./data", stocklist_path="./stocklist.csv")
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

### appendix.json 配置
用于存储额外的配置信息和数据附录。

## 板块轮动分析

### 提示词模板
项目提供了多种板块轮动分析提示词模板：
- **deepseek模板**: 适合资深证券分析师的深度分析
- **元宝模板**: 系统化的选股分析框架
- **指数贡献策略**: 基于权重股的指数增强策略

### 支持的板块
重点关注板块：
- 中央汇金持股
- 券商非银
- 科技/半导体
- 可控核聚变
- 消费/白酒
- 创新药
- 新能源车/固态电池
- 有色金属
- 基建/煤炭

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
- 并发处理错误隔离

### 性能优化
- 多进程/多线程并发处理
- 内存使用优化
- 批量数据处理
- 缓存机制

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

### 板块分析扩展
- 添加新的板块轮动算法
- 集成更多行业数据源
- 实现实时板块监控

## 注意事项

1. **数据获取限制**: Tushare接口有频率限制，项目已实现限流机制
2. **免责声明**: 本项目仅供学习研究，不构成投资建议
3. **数据准确性**: 请确保Tushare Token有效且有足够权限
4. **风险提示**: 股市有风险，投资需谨慎
5. **性能考虑**: 大规模数据处理时注意内存和CPU使用情况

## 常见问题

### Q: 数据获取失败怎么办？
A: 检查Tushare Token是否正确，网络连接是否正常，是否触发频率限制

### Q: 如何调整策略参数？
A: 修改configs.json中对应策略的params字段

### Q: 选股结果为空？
A: 检查数据是否完整，策略参数是否合理，市场条件是否满足策略要求

### Q: 如何使用市值筛选？
A: 使用 `--min-market-cap` 和 `--max-market-cap` 参数（单位：亿元）

### Q: 并发处理如何优化？
A: 根据 `mp.cpu_count()` 和数据规模调整 `--workers` 参数

### Q: 板块轮动分析如何使用？
A: 参考 `板块轮动提示词.md` 中的模板，结合 `SectorShift.py` 模块

---

*本项目基于@Zettaranc的Z哥战法实现，仅供学习交流使用。*