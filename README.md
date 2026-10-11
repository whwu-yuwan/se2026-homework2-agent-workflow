# 🔍 代码审查工作流 (Code Review Workflow)

一个基于多 Agent 协同的代码审查系统，由 3 个 Agent 组成工作流，自动完成代码读取、审查和修复。

## ✨ 功能特性

- **多 Agent 协同**：CodeAgent、ReviewAgent、FixAgent 三个 Agent 各司其职
- **工作流引擎**：支持顺序执行、条件分支、循环控制
- **自动审查-修复循环**：审查发现问题时自动修复，最多循环 3 轮
- **共享状态管理**：Agent 通过 WorkflowContext 传递数据
- **执行日志**：实时显示每步执行状态和耗时
- **错误恢复**：单步失败可配置是否中断整个流程

## 🛠️ 技术栈

- **Python 3.10+**
- **LangChain**：Agent 框架（工具绑定、消息管理）
- **LangChain OpenAI**：连接 DeepSeek API
- **tiktoken**：上下文 token 管理
- **DeepSeek API**：大语言模型

## 📦 安装与运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 设置 API Key

```bash
# Windows
set DEEPSEEK_API_KEY=your-api-key-here

# Linux/Mac
export DEEPSEEK_API_KEY=your-api-key-here
```

### 3. 运行

```bash
python main.py
```

## 📖 使用示例

### 示例 1：审查文件

```
🧑 You > main.py

🚀 工作流开始: 代码审查工作流
  ⏳ [读取代码] Agent: CodeAgent ...
  ✅ [读取代码] 完成 (2.1s)

  🔄 审查-修复循环 第 1/3 轮
  ⏳ [代码审查] Agent: ReviewAgent ...
  ✅ [代码审查] 完成 (5.3s)
     输出: ## 审查报告 ... NEEDS_FIX

  ⏳ [代码修复] Agent: FixAgent ...
  ✅ [代码修复] 完成 (4.8s)

  🔄 审查-修复循环 第 2/3 轮
  ⏳ [代码审查] Agent: ReviewAgent ...
  ✅ [代码审查] 完成 (4.1s)
     输出: ## 审查报告 ... PASS

  🔄 第 2 轮结果: 审查通过 ✅

✅ 工作流结束: completed (总耗时: 16.3s)
```

### 示例 2：直接粘贴代码

```
🧑 You > def divide(a, b):
    return a / b
```

## 🏗️ 项目结构

```
task2/
├── main.py                    # CLI 入口
├── config.py                  # 全局配置
├── exceptions.py              # 异常体系
├── logger.py                  # 日志配置
├── tools.py                   # 工具集（文件读取、搜索等）
├── requirements.txt           # 依赖
├── README.md                  # 使用文档
├── Design.md                  # 设计文档
├── agents/
│   ├── __init__.py
│   ├── base.py                # BaseAgent 基类
│   ├── code_agent.py          # 编码 Agent
│   ├── review_agent.py        # 审查 Agent
│   └── fix_agent.py           # 修复 Agent
├── workflow/
│   ├── __init__.py
│   ├── engine.py              # WorkflowEngine 核心引擎
│   ├── context.py             # WorkflowContext 共享状态
│   └── flow_logger.py         # 执行日志
├── workflows/
│   ├── __init__.py
│   └── code_review.py         # 代码审查工作流定义
└── tests/
    ├── __init__.py
    ├── test_engine.py          # 引擎测试
    ├── test_agents.py          # Agent 测试
    └── test_workflow.py        # 端到端工作流测试
```

## 🧪 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_engine.py -v
pytest tests/test_agents.py -v
pytest tests/test_workflow.py -v
```

## 🎯 命令说明

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助信息 |
| `/verbose` | 切换详细模式 |
| `/quit` | 退出程序 |

## 📝 设计文档

详见 [Design.md](Design.md)

## 📄 License

MIT