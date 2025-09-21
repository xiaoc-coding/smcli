# SM-CLI

智能网络设备管理命令行工具，类似 Gemini CLI 的交互式终端界面。

## 功能特性

### 🤖 AI智能代理
- **多AI模型支持** - 支持 DeepSeek、GPT-4、GPT-3.5、Claude 3、Gemini Pro 等多种AI模型
- **智能工具调用** - 基于smolagents框架，AI可以自动调用SSH工具执行网络设备操作
- **自然语言交互** - 用自然语言描述需求，AI自动转换为相应的网络设备命令
- **上下文理解** - AI理解网络设备品牌差异，自动选择正确的命令语法

### 🔧 交互式界面
- **Gemini风格CLI** - 类似 Gemini CLI 的用户体验，支持命令历史记录
- **实时反馈** - 显示AI思考过程和工具执行状态
- **彩色输出** - 清晰的彩色界面，提升用户体验

### 🗄️ 设备管理
- **SQLite数据库** - 设备信息存储在SQLite数据库中，支持品牌管理
- **多品牌支持** - 支持Cisco、Arista、Juniper、Huawei、H3C、Fortinet、Palo Alto等主流品牌
- **设备品牌识别** - 自动识别设备品牌，提供相应的命令建议和语法指导

### 🔐 网络连接
- **SSH自动连接** - 支持通过SSH连接和管理网络设备
- **安全认证** - 支持用户名密码认证，自动处理设备认证流程
- **连接测试** - 提供SSH连接测试功能，确保设备可达性

### ⚙️ 配置管理
- **多模型配置** - 支持多AI模型配置和API密钥管理
- **灵活切换** - 运行时动态切换AI模型
- **配置持久化** - 配置信息自动保存，重启后保持设置

## 安装

### 前置要求

在安装SM-CLI之前，请确保已安装以下组件：

1. **Python 3.8+** - 确保系统已安装Python 3.8或更高版本
2. **smolagents** - AI代理框架（核心依赖）

### 预安装smolagents

由于SM-CLI依赖smolagents框架，建议先单独安装：

```bash
# 安装smolagents（包含litellm支持）
pip install "smolagents[litellm]"

# 或者使用conda安装
conda install -c conda-forge smolagents
```

### 快速安装

```bash
# 克隆仓库
git clone <repository-url>
cd sm-cli

# 安装依赖（包含smolagents）
pip install -r requirements.txt

# 创建全局符号链接（推荐）
mkdir -p ~/.local/bin
ln -s $(pwd)/sm-cli ~/.local/bin/sm-cli
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# 现在可以在任何地方使用 sm-cli 命令
sm-cli
```

### 直接运行（无需安装）

```bash
# 安装依赖（包含smolagents）
pip install -r requirements.txt

# 直接运行
python3 sm_cli.py
```

### 验证安装

安装完成后，可以通过以下命令验证：

```bash
# 检查smolagents是否正确安装
python3 -c "import smolagents; print('smolagents安装成功')"

# 运行SM-CLI
sm-cli
```

## 使用方法

### 启动CLI

```bash
sm-cli
```

### 基本命令

- `/help` 或 `/h` - 显示帮助信息
- `/quit` 或 `/q` - 退出程序
- `/clear` 或 `/cls` - 清屏
- `/status` - 显示当前配置状态

### 配置命令

- `/config` - 显示所有配置
- `/reset` - 重置为默认配置

### 设备管理命令

- `/devices` - 列出所有设备
- `/add_device <host> <username> <password> [brand]` - 添加设备
- `/del_device <host>` - 删除设备
- `/search_device <keyword>` - 搜索设备
- `/update_brand <host> <brand>` - 更新设备品牌

### LLM模型管理命令

- `/llm` - 列出所有可用模型
- `/switch_llm <model_key>` - 切换当前模型
- `/set_model_key <model_key> <api_key>` - 设置模型API密钥
- `/current_llm` - 显示当前模型

## 支持的AI模型

| 模型键 | 模型名称 | 描述 |
|--------|----------|------|
| `deepseek` | DeepSeek | DeepSeek Chat模型，适合中文对话 |
| `gpt-4` | GPT-4 | OpenAI GPT-4模型，强大的推理能力 |
| `gpt-3.5` | GPT-3.5 Turbo | OpenAI GPT-3.5 Turbo模型，快速响应 |
| `claude-3` | Claude 3 | Anthropic Claude 3模型，优秀的代码能力 |
| `gemini` | Gemini Pro | Google Gemini Pro模型，多模态能力 |

## 使用示例

### 1. 初始设置

```bash
# 启动SM-CLI
sm-cli

# 查看可用AI模型
/llm

# 设置API密钥（以DeepSeek为例）
/set_model_key deepseek sk-your-deepseek-key

# 切换到指定模型
/switch_llm deepseek

# 查看当前状态
/status
```

### 2. 设备管理

```bash
# 添加设备（支持品牌标识）
/add_device 172.21.1.167 admin r00tme Arista
/add_device 172.21.1.81 admin password123 Cisco
/add_device 192.168.1.1 admin admin123 Huawei

# 查看设备列表
/devices

# 搜索设备
/search_device 172.21

# 更新设备品牌
/update_brand 172.21.1.81 Juniper

# 删除设备
/del_device 192.168.1.1
```

### 3. AI智能对话

SM-CLI的核心功能是通过自然语言与AI交互，AI会自动调用SSH工具执行网络设备操作：

```bash
# 设备状态检查
检查172.21.1.167这台交换机的接口状态

# 设备信息获取
获取设备172.21.1.167的版本信息和运行配置

# 网络诊断
诊断172.21.1.167到172.21.1.81的连通性

# 配置管理
在设备172.21.1.167上创建VLAN 100，名称为"Management"

# 安全配置
在Cisco设备上配置SSH访问，禁用Telnet

# 性能监控
检查Arista设备的CPU和内存使用情况

# 故障排除
分析设备172.21.1.167的日志，查找错误信息
```

### 4. 高级功能

```bash
# 批量操作
为所有Cisco设备配置相同的SNMP社区字符串

# 配置备份
备份所有设备的运行配置到本地文件

# 安全审计
检查所有设备的安全配置，包括密码策略和访问控制

# 网络拓扑
分析网络拓扑，识别设备间的连接关系
```

### 5. 命令历史和管理

```bash
# 查看帮助
/help

# 清屏
/clear

# 查看配置
/config

# 设置AI最大步数
/step 20

# 重置配置
/reset

# 退出程序
/quit
```

## 配置文件

配置文件保存在 `~/.sm-cli/config.json`，包含：

- `timeout` - SSH连接超时时间
- `available_models` - 多模型配置
- `current_model` - 当前使用的模型

## 数据库

设备信息存储在项目目录下的 `devices.db` SQLite数据库中，包含：

- `host` - 设备IP地址
- `username` - 登录用户名
- `password` - 登录密码
- `brand` - 设备品牌

## 环境变量

- `DEEPSEEK_API_KEY` - DeepSeek API密钥
- `OPENAI_API_KEY` - OpenAI API密钥
- `ANTHROPIC_API_KEY` - Anthropic API密钥
- `GOOGLE_API_KEY` - Google API密钥

## 项目结构

```
sm-cli/
├── sm_cli.py          # 主程序文件（Python模块）
├── sm-cli             # 全局可执行脚本（启动器）
├── devices.db         # 设备数据库（SQLite）
├── requirements.txt   # 依赖包列表
├── SM-CLI.md         # AI提示词规范文件
└── README.md         # 说明文档
```

### 文件说明

- **`sm_cli.py`** - 核心Python模块，包含所有功能实现
- **`sm-cli`** - 可执行启动脚本，用于全局命令调用
- **`devices.db`** - SQLite数据库，存储设备信息
- **`SM-CLI.md`** - AI代理的系统提示词，定义网络设备专家角色

## 依赖包

- `smolagents[litellm]` - AI代理框架（核心依赖）
- `paramiko` - SSH连接库
- `readline` - 命令行历史记录

## 故障排除

### 常见问题

#### 1. smolagents安装失败

**问题**: 安装smolagents时出现错误

**解决方案**:
```bash
# 升级pip
pip install --upgrade pip

# 安装smolagents
pip install "smolagents[litellm]"

# 如果仍有问题，尝试使用conda
conda install -c conda-forge smolagents
```

#### 2. AI代理初始化失败

**问题**: 启动时显示"AI代理未初始化"

**解决方案**:
```bash
# 检查API密钥是否设置
/status

# 设置API密钥
/set_model_key deepseek your-api-key

# 重新初始化
/switch_llm deepseek
```

#### 3. SSH连接失败

**问题**: 无法通过SSH连接设备

**解决方案**:
```bash
# 测试SSH连接
ssh_test(host='device-ip')

# 检查设备信息
/device_info device-ip

# 更新设备信息
/update_brand device-ip Brand
```

#### 4. 网络代理问题

**问题**: 在代理环境下无法连接AI服务

**解决方案**:
```bash
# 临时禁用代理
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY

# 或者设置环境变量
export SM_CLI_DEBUG=1
sm-cli
```

#### 5. 设备品牌识别错误

**问题**: AI使用了错误的设备命令

**解决方案**:
```bash
# 更新设备品牌
/update_brand device-ip CorrectBrand

# 查看设备信息
/device_info device-ip

# 手动指定品牌进行对话
"作为Cisco设备，执行show version命令"
```

### 调试模式

启用调试模式获取详细日志：

```bash
# 设置调试环境变量
export SM_CLI_DEBUG=1

# 运行SM-CLI
sm-cli
```

### 日志文件

- 配置文件: `~/.sm-cli/config.json`
- 设备数据库: `./devices.db`
- 错误日志: 在终端输出中查看

### 性能优化

1. **减少AI步数**: 使用 `/step 5` 限制AI最大步数
2. **选择合适模型**: 根据需求选择响应速度或准确性的模型
3. **网络优化**: 确保网络连接稳定，避免代理问题

## 开发

欢迎提交 Issue 和 Pull Request！

### 开发环境设置

```bash
# 克隆仓库
git clone <repository-url>
cd sm-cli

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装开发依赖
pip install -r requirements.txt

# 运行测试
python3 sm_cli.py
```

## 许可证

MIT License# smcli
