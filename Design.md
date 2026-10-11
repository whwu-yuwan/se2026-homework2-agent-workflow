# 📐 设计文档 - 代码审查工作流

## 1. 架构概述

### 1.1 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                           用户 (CLI)                                 │
│                              │                                       │
│                              ▼                                       │
│                      ┌──────────────┐                                │
│                      │   main.py    │  CLI 交互界面                   │
│                      └──────┬───────┘                                │
│                             │                                        │
│                             ▼                                        │
│               ┌──────────────────────────┐                          │
│               │    WorkflowEngine         │  工作流引擎               │
│               │  - 顺序执行               │                          │
│               │  - 条件分支               │                          │
│               │  - 循环控制               │                          │
│               │  - 错误恢复               │                          │
│               └───────────┬──────────────┘                          │
│                           │                                          │
│        ┌──────────────────┼──────────────────┐                      │
│        ▼                  ▼                  ▼                      │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│ │  CodeAgent   │  │ ReviewAgent  │  │   FixAgent   │               │
│ │  (读取代码)   │  │  (审查分析)   │  │  (修复代码)   │               │
│ └──────┬───────┘  └──────────────┘  └──────────────┘               │
│        │                                                            │
│        ▼                                                            │
│ ┌──────────────┐  ┌──────────────┐                                │
│ │   tools.py   │  │   BaseAgent  │  Agent 基类                     │
│ │  (文件工具)   │  │  (消息管理)   │                                │
│ └──────────────┘  └──────────────┘                                │
│                                                                    │
│ ┌──────────────────────────────────────┐                          │
│ │           WorkflowContext             │  共享状态                 │
│ │  - code: 当前代码                     │                          │
│ │  - review_result: 审查报告            │                          │
│ │  - review_round: 当前轮次             │                          │
│ │  - has_critical_issues: 是否有问题    │                          │
│ └──────────────────────────────────────┘                          │
│                                                                    │
│  DeepSeek API (via langchain-openai)                               │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 组件职责

| 组件 | 文件 | 职责 |
|------|------|------|
| CLI 界面 | `main.py` | 命令行交互、命令处理 |
| 工作流引擎 | `workflow/engine.py` | 步骤编排、条件分支、循环控制、错误恢复 |
| 共享上下文 | `workflow/context.py` | Agent 间数据传递、状态记录 |
| 执行日志 | `workflow/flow_logger.py` | 实时打印、执行摘要 |
| Agent 基类 | `agents/base.py` | LLM 调用、消息管理、上下文裁剪 |
| 编码 Agent | `agents/code_agent.py` | 读取代码文件、理解代码结构 |
| 审查 Agent | `agents/review_agent.py` | 分析代码质量、发现问题 |
| 修复 Agent | `agents/fix_agent.py` | 根据审查报告修复代码 |
| 工具集 | `tools.py` | 文件读取、目录浏览、代码搜索 |
| 工作流定义 | `workflows/code_review.py` | 代码审查工作流的具体编排 |

## 2. 工作流引擎设计

### 2.1 核心抽象

```python
# Step: 单个工作流步骤
Step(
    name="步骤名称",
    agent=某个Agent实例,
    input_fn=lambda ctx: "从上下文提取输入",
    output_fn=lambda ctx, output: ctx.set("key", output),
    condition=lambda ctx: True/False  # 可选的执行条件
)

# LoopGroup: 循环步骤组
LoopGroup(
    name="循环名称",
    steps=[Step, Step, ...],
    condition=lambda ctx: True继续/False停止,
    max_rounds=3
)
```

### 2.2 执行流程

```
用户输入
    │
    ▼
┌─────────────────────────────────┐
│  Step 1: CodeAgent 读取代码      │
│  input: 用户输入                  │
│  output: ctx.code = 代码内容      │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  LoopGroup: 审查-修复循环         │
│  max_rounds: 3                   │
│                                  │
│  ┌────────────────────────────┐ │
│  │ Step 2: ReviewAgent 审查    │ │
│  │ input: ctx.code             │ │
│  │ output: ctx.review_result   │ │
│  │       ctx.has_critical_issues│ │
│  └────────────┬───────────────┘ │
│               │                  │
│         有问题? ──否──→ 退出循环  │
│               │是                │
│               ▼                  │
│  ┌────────────────────────────┐ │
│  │ Step 3: FixAgent 修复       │ │
│  │ condition: has_critical_issues│ │
│  │ input: code + review_result │ │
│  │ output: ctx.code = 修复后   │ │
│  └────────────────────────────┘ │
│               │                  │
│          回到 Step 2             │
└──────────────┬──────────────────┘
               │
               ▼
         输出最终结果
```

### 2.3 关键设计决策

1. **Step 抽象**：每个步骤通过 `input_fn` 和 `output_fn` 与上下文交互，解耦 Agent 与工作流逻辑
2. **条件执行**：Step.condition 控制单步是否执行，LoopGroup.condition 控制循环是否继续
3. **最大轮次**：防止无限循环，默认 3 轮
4. **结论解析**：从审查报告中解析 `PASS/NEEDS_FIX` 结论，驱动循环条件
5. **错误隔离**：单步失败可通过配置决定是否中断整个流程

## 3. Agent 设计

### 3.1 Agent 层次结构

```
BaseAgent (基类)
├── LLM 初始化
├── 消息管理 (SystemMessage, HumanMessage, AIMessage, ToolMessage)
├── 上下文裁剪 (tiktoken 估算)
├── 工具执行
└── run() 方法: Agent 循环

CodeAgent (继承 BaseAgent)
├── name = "CodeAgent"
├── system_prompt = 代码分析专家
└── tools = [read_file, list_directory, search_code]

ReviewAgent (继承 BaseAgent)
├── name = "ReviewAgent"
├── system_prompt = 代码审查专家
└── tools = []  (纯 LLM 分析)

FixAgent (继承 BaseAgent)
├── name = "FixAgent"
├── system_prompt = 代码修复专家
└── tools = []  (纯 LLM 修复)
```

### 3.2 Agent 通信方式

Agent 之间通过 **WorkflowContext** 间接通信：

```
CodeAgent.run(输入) → 输出 → ctx.code = 输出
                                ↓
ReviewAgent.run(ctx.code) → 输出 → ctx.review_result = 输出
                                       ↓
FixAgent.run(ctx.code + ctx.review_result) → 输出 → ctx.code = 修复后代码
                                                        ↓
                                                   回到 ReviewAgent
```

### 3.3 BaseAgent.run() 流程

```
输入校验 (token 长度)
    │
    ▼
添加 HumanMessage 到历史
    │
    ▼
上下文裁剪
    │
    ▼
Agent 循环 (最多 MAX_TOOL_CALLS_PER_TURN 次)
    │
    ├── 有工具调用 → 执行工具 → 结果加入历史 → 继续循环
    │
    ├── 无工具调用 → 返回文本回复
    │
    └── 轮次耗尽 → 强制生成回复
```

## 4. 共享状态设计 (WorkflowContext)

### 4.1 数据模型

```python
class WorkflowContext:
    _data: Dict[str, Any]       # 通用键值对存储
    _step_results: List[Step]   # 步骤执行记录
    _start_time: float          # 开始时间
    _status: str                # pending | running | completed | failed

    # 便捷属性
    code: str                   # 当前代码
    review_result: str          # 审查报告
    review_round: int           # 当前审查轮次
    has_critical_issues: bool   # 是否有严重问题
```

### 4.2 数据流向

```
Step 1 (CodeAgent):
  输入: ctx["user_input"]
  输出: ctx["code"] = CodeAgent 输出

Step 2 (ReviewAgent):
  输入: ctx["code"]
  输出: ctx["review_result"] = 审查报告
        ctx["has_critical_issues"] = True/False

Step 3 (FixAgent):
  输入: ctx["code"] + ctx["review_result"]
  输出: ctx["code"] = 修复后代码（覆盖原代码）

下一轮 Step 2:
  输入: ctx["code"]（修复后的代码）
  ...
```

## 5. 异常处理

### 5.1 异常类层次

```
WorkflowError (工作流基础异常)
├── AgentError (Agent 基础异常)
│   ├── ToolError    — 工具执行失败
│   ├── APIError     — LLM 调用失败
│   └── ContextError — 输入过长
├── ConfigError      — 配置错误
├── EngineError      — 引擎错误
└── StepError        — 步骤执行失败
```

### 5.2 错误处理策略

| 场景 | 处理方式 |
|------|----------|
| API Key 未设置 | raise ConfigError，提示设置方法 |
| LLM 调用失败 | Agent 内部回滚消息历史，raise APIError |
| 工具执行失败 | 工具内部 raise ToolError，Agent 转为 ToolMessage |
| 步骤执行失败 | Engine 捕获，记录到执行日志，raise EngineError |
| 循环超过最大轮次 | 自动退出循环，输出当前结果 |
| 用户中断 (Ctrl+C) | 优雅退出 |

## 6. 可扩展性设计

### 6.1 新增 Agent

```python
# 1. 继承 BaseAgent
class TestAgent(BaseAgent):
    name = "TestAgent"
    system_prompt = "..."
    tools = [...]

# 2. 在工作流中注册
engine.add_step(Step(
    name="测试步骤",
    agent=TestAgent(),
    input_fn=lambda ctx: ...,
    output_fn=lambda ctx, output: ...,
))
```

### 6.2 新增工作流

```python
# 定义新的工作流
def build_test_workflow() -> WorkflowEngine:
    engine = WorkflowEngine(name="测试工作流")
    engine.add_step(Step(...))
    engine.add_loop(LoopGroup(...))
    return engine
```

### 6.3 新增工具

```python
# 在 tools.py 中定义
@tool
def new_tool(param: str) -> str:
    """工具描述"""
    ...

# 绑定到 Agent
class MyAgent(BaseAgent):
    tools = [read_file, new_tool]
```

## 7. 测试策略

### 7.1 测试覆盖

| 测试类型 | 文件 | 覆盖范围 |
|----------|------|----------|
| 引擎测试 | `test_engine.py` | Step 执行、条件分支、循环控制、错误处理 |
| Agent 测试 | `test_agents.py` | Agent 初始化、消息管理、工具执行 |
| 工作流测试 | `test_workflow.py` | 端到端流程、上下文数据流、审查结论解析 |

### 7.2 测试方法

- **Mock LLM**：使用 `unittest.mock.patch` 模拟 Agent.run()
- **Mock Agent**：验证工作流引擎的编排逻辑
- **上下文测试**：验证数据在 Agent 间正确传递