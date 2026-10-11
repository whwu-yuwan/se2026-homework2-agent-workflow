# 🔍 多 Agent 协同工作流系统

一个基于多 Agent 协同的工作流系统，由 3 个 Agent 组成可编排的工作流，支持代码审查、文档生成等多种业务流程。

## ✨ 功能特性

- **3 个 Agent 协同**：CodeAgent（读取代码）、ReviewAgent（审查/分析）、FixAgent（修复/生成文档）
- **2 个工作流**：代码审查（审查→修复循环）、文档生成（动态并行分析→生成文档）
- **工作流引擎**：支持顺序执行、条件分支、循环控制、静态并行（ParallelGroup）、动态并行（MapParallelStep）
- **Agent 注册机制**：通过 AgentRegistry 动态创建 Agent，支持自定义 prompt 和 tools
- **共享状态管理**：Agent 通过 WorkflowContext 传递数据
- **执行日志**：实时显示每步执行状态和耗时
- **145 个测试全部通过**

## 🛠️ 技术栈

- **Python 3.10+**
- **LangChain**：Agent 框架（工具绑定、消息管理）
- **LangChain OpenAI**：连接 DeepSeek API
- **tiktoken**：上下文 token 管理
- **DeepSeek API**：大语言模型

## 📦 安装与运行

```bash
pip install -r requirements.txt
set DEEPSEEK_API_KEY=your-api-key-here   # Windows
python main.py
```

## 📖 使用方式

运行后选择工作流，输入文件路径或粘贴代码即可：

```
🧑 You > main.py          # 代码审查工作流
🧑 You > /workflow         # 切换到文档生成工作流
🧑 You > /agents           # 查看已注册 Agent
🧑 You > /verbose          # 切换详细模式
```

## 🏗️ 项目结构

```
task2/
├── main.py                    # CLI 入口（支持多工作流选择）
├── config.py                  # 全局配置
├── exceptions.py              # 异常体系（7 个异常类）
├── logger.py                  # 日志配置
├── tools.py                   # 工具集（read_file, list_directory, execute_python, search_code）
├── agents/
│   ├── base.py                # BaseAgent 基类（可配置 prompt/tools）
│   ├── code_agent.py          # 编码 Agent
│   ├── review_agent.py        # 审查 Agent（绑定 read_file/search_code）
│   ├── fix_agent.py           # 修复 Agent（绑定全部 4 个工具）
│   └── registry.py            # Agent 注册表
├── workflow/
│   ├── engine.py              # WorkflowEngine（Step + LoopGroup + ParallelGroup）
│   ├── context.py             # WorkflowContext 共享状态
│   └── flow_logger.py         # 执行日志
├── workflows/
│   ├── code_review.py         # 代码审查工作流
│   └── doc_generation.py      # 文档生成工作流
└── tests/                     # 145 个测试
    ├── test_tools.py          # 工具测试 (33)
    ├── test_agents.py         # Agent 测试 (24)
    ├── test_engine.py         # 引擎测试 (33)
    ├── test_workflow.py       # 工作流测试 (18)
    ├── test_flow_logger.py    # 日志测试 (18)
    ├── test_main.py           # CLI 测试 (13)
    └── test_registry.py       # 注册表测试 (6)
```

## 🧪 运行测试

```bash
pytest tests/ -v
```

## 🎯 命令说明

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助信息 |
| `/workflow` | 切换工作流（代码审查/文档生成） |
| `/agents` | 查看已注册的 Agent 列表 |
| `/verbose` | 切换详细模式 |
| `/quit` | 退出程序 |

## 📝 设计文档

详见 [Design.md](Design.md)（含 Mermaid 流程图、架构图、已知限制）

## 📄 License

MIT