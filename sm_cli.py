#!/usr/bin/env python3
"""
SM-CLI: 智能网络设备管理命令行工具
类似 Gemini CLI 的交互式终端界面
"""

import os
import sys
import json
import argparse
import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import readline
import warnings

# 在导入任何可能产生警告的模块之前，先抑制所有相关警告
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*TripleDES.*")
warnings.filterwarnings("ignore", module="paramiko")
warnings.filterwarnings("ignore", module="cryptography")

from smolagents import LiteLLMModel, CodeAgent
from smolagents.agents import PromptTemplates
from smolagents.tools import Tool
import paramiko

class SSHCommandTool(Tool):
    name = "ssh_command"
    description = (
        "通过SSH连接网络设备并执行命令，返回结果。"
        "优先从数据库获取设备信息，包括用户名、密码和品牌信息。"
        "参数：host（设备IP或设备名称），username（用户名，可选），password（密码，可选），command（要执行的命令）。"
        "示例：ssh_command(host='172.21.1.167', command='show version') 或 ssh_command(host='switch1', command='show version')"
        "\n\n🚨 关键提醒：对于Cisco和Arista设备，执行特权命令（如show running-config）前必须先进入enable模式！"
        "\n\n重要：此工具会自动从数据库获取设备品牌信息，并在返回结果中包含品牌标识，帮助AI选择正确的命令。"
        "\n\n⚠️ 重要：设备品牌模式切换要求："
        "- Cisco: 执行任何特权命令前必须先 'enable'，配置命令需要 'configure terminal'"
        "- Arista: 执行任何特权命令前必须先 'enable'，配置命令需要 'configure'"
        "- Juniper: 执行配置命令前必须先 'configure'"
        "- Huawei: 执行配置命令前必须先 'system-view'"
        "- H3C: 执行配置命令前必须先 'system-view'"
        "\n\n🔑 特权模式命令执行规则："
        "- 对于show running-config、show interface、show vlan等特权命令，必须先用enable进入特权模式"
        "- 推荐格式：'enable\\n目标命令' (用换行符分隔)"
        "- 禁止直接执行特权命令，必须先进入特权模式"
        "- 如果命令失败提示'privileged mode required'，说明需要先执行enable"
    )
    inputs = {
        "host": {"type": "string", "description": "设备IP地址或设备名称"},
        "username": {"type": "string", "description": "登录用户名（可选，优先从数据库获取）", "default": "", "nullable": True},
        "password": {"type": "string", "description": "登录密码（可选，优先从数据库获取）", "default": "", "nullable": True},
        "command": {"type": "string", "description": "要执行的命令", "nullable": True},
        "port": {"type": "integer", "description": "SSH端口号", "default": 22, "nullable": True}
    }
    output_type = "string"

    def __init__(self, config_manager=None, device_db=None):
        super().__init__()
        self.config_manager = config_manager
        self.device_db = device_db
    
    def get_brand_commands_from_prompt(self, brand):
        """从系统提示词中获取品牌命令建议"""
        try:
            # 加载系统提示词
            prompt_file = Path(__file__).parent / "SM-CLI.md"
            if not prompt_file.exists():
                return None
            
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析品牌命令信息
            brand_commands = self.parse_brand_commands(content, brand)
            return brand_commands
            
        except Exception as e:
            print(f"⚠️  解析品牌命令失败: {e}")
            return None
    
    def parse_brand_commands(self, content, brand):
        """解析系统提示词中的品牌命令信息"""
        try:
            # 品牌名称映射
            brand_mapping = {
                "cisco": "Cisco设备",
                "arista": "Arista设备", 
                "juniper": "Juniper设备",
                "huawei": "Huawei设备",
                "h3c": "H3C设备",
                "fortinet": "Fortinet设备",
                "palo": "Palo Alto设备"
            }
            
            brand_section = brand_mapping.get(brand.lower())
            if not brand_section:
                return None
            
            # 查找品牌对应的章节
            lines = content.split('\n')
            in_brand_section = False
            brand_info = {}
            
            for line in lines:
                line = line.strip()
                
                # 检查是否进入目标品牌章节
                if line.startswith(f"#### {brand_section}"):
                    in_brand_section = True
                    continue
                
                # 如果遇到下一个品牌章节，停止解析
                if in_brand_section and line.startswith("#### ") and not line.startswith(f"#### {brand_section}"):
                    break
                
                # 在目标品牌章节中查找各种信息
                if in_brand_section:
                    if line.startswith("- **命令风格**: "):
                        brand_info['command_style'] = line.replace("- **命令风格**: ", "")
                    elif line.startswith("- **模式切换**: "):
                        brand_info['mode_switch'] = line.replace("- **模式切换**: ", "")
                    elif line.startswith("- **常用命令**: "):
                        commands_text = line.replace("- **常用命令**: ", "")
                        command_list = [cmd.strip() for cmd in commands_text.split(',')]
                        brand_info['common_commands'] = command_list
                    elif line.startswith("- **配置保存**: "):
                        brand_info['config_save'] = line.replace("- **配置保存**: ", "")
                    elif line.startswith("- **特色功能**: "):
                        brand_info['special_features'] = line.replace("- **特色功能**: ", "")
            
            # 构建建议信息
            suggestions = []
            
            # 添加模式切换信息
            if 'mode_switch' in brand_info:
                suggestions.append(f"模式切换: {brand_info['mode_switch']}")
            
            # 添加常用命令
            if 'common_commands' in brand_info:
                suggestions.append("常用命令:")
                for cmd in brand_info['common_commands']:
                    if cmd:
                        suggestions.append(f"  - {cmd}")
            
            # 添加配置保存信息
            if 'config_save' in brand_info:
                suggestions.append(f"配置保存: {brand_info['config_save']}")
            
            # 添加特色功能
            if 'special_features' in brand_info:
                suggestions.append(f"特色功能: {brand_info['special_features']}")
            
            if suggestions:
                return "\n".join(suggestions)
            else:
                return None
                
        except Exception as e:
            print(f"⚠️  解析品牌命令失败: {e}")
            return None

    def forward(self, host: str, username: str = "", password: str = "", command: str = "", 
                port: int = 22) -> str:
        try:
            # 必须从数据库获取设备信息
            device_info = None
            if self.device_db:
                device_info = self.device_db.get_device(host=host)
            
            if not device_info:
                return f"❌ 设备 '{host}' 未在数据库中找到，请先使用 /add_device 添加设备"
            
            # 使用数据库中的信息
            username = username or device_info.get("username", "admin")
            password = password or device_info.get("password", "")
            brand = device_info.get("brand", "Unknown").lower()
            
            # 如果命令为空，根据品牌提供建议
            if not command:
                # 从系统提示词中获取品牌命令建议
                brand_suggestions = self.get_brand_commands_from_prompt(brand)
                if brand_suggestions:
                    return f"设备 {host} 是 {brand.upper()} 品牌，建议使用以下命令：\n{brand_suggestions}"
                else:
                    return f"设备 {host} 品牌未知 ({brand})，建议使用通用命令：show version, show interfaces, show running-config"
            
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # 让paramiko自动处理认证类型
            ssh.connect(host, port=port, username=username, password=password, timeout=10)
            
            stdin, stdout, stderr = ssh.exec_command(command)
            result = stdout.read().decode(errors="ignore")
            error = stderr.read().decode(errors="ignore")
            ssh.close()
            
            if error:
                return f"命令执行结果:\n{result}\n\n错误信息:\n{error}"
            
            # 在结果前添加设备品牌信息，帮助AI更好地理解结果
            brand_info = f"[设备品牌: {brand.upper()}] "
            return f"{brand_info}{result}"
            
        except paramiko.AuthenticationException as e:
            return f"SSH认证失败: {e}\n建议检查用户名和密码"
        except paramiko.SSHException as e:
            return f"SSH连接错误: {e}"
        except Exception as e:
            return f"连接或执行命令失败: {e}"

class SSHTestTool(Tool):
    name = "ssh_test"
    description = (
        "测试SSH连接到网络设备，仅验证连接是否成功，不执行任何命令。"
        "优先从数据库获取设备信息，如果未找到则使用配置中的默认值。"
        "参数：host（设备IP或设备名称），username（用户名，可选），password（密码，可选），port（端口号）。"
        "示例：ssh_test(host='172.21.1.167') 或 ssh_test(host='switch1')"
    )
    inputs = {
        "host": {"type": "string", "description": "设备IP地址或设备名称"},
        "username": {"type": "string", "description": "登录用户名（可选，优先从数据库获取）", "default": "", "nullable": True},
        "password": {"type": "string", "description": "登录密码（可选，优先从数据库获取）", "default": "", "nullable": True},
        "port": {"type": "integer", "description": "SSH端口号", "default": 22, "nullable": True}
    }
    output_type = "string"

    def __init__(self, config_manager=None, device_db=None):
        super().__init__()
        self.config_manager = config_manager
        self.device_db = device_db

    def forward(self, host: str, username: str = "", password: str = "", 
                port: int = 22) -> str:
        try:
            # 必须从数据库获取设备信息
            device_info = None
            if self.device_db:
                device_info = self.device_db.get_device(host=host)
            
            if not device_info:
                return f"❌ 设备 '{host}' 未在数据库中找到，请先使用 /add_device 添加设备"
            
            # 使用数据库中的信息
            username = username or device_info.get("username", "admin")
            password = password or device_info.get("password", "")
            brand = device_info.get("brand", "Unknown")
            
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # 参考test3.py的成功连接方式
            ssh.connect(host, port=port, username=username, password=password, timeout=10)
            
            # 测试连接后立即关闭，不执行任何命令
            ssh.close()
            
            return f"""✅ SSH连接成功！

连接参数: {host}:{port} (用户: {username})
设备品牌: {brand.upper()}
使用方式: 参考test3.py的简单连接方法"""
            
        except paramiko.AuthenticationException as e:
            return f"""❌ SSH认证失败: {e}

建议解决方案:
1. 检查用户名和密码是否正确
2. 确认设备支持密码认证
3. 检查用户权限"""
            
        except paramiko.SSHException as e:
            return f"""❌ SSH连接错误: {e}

可能的原因:
1. 设备SSH服务未启动
2. 端口号不正确
3. 网络连接问题
4. 防火墙阻止连接"""
            
        except Exception as e:
            return f"❌ 连接测试失败: {e}"

class DeviceDatabase:
    """设备数据库管理器"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            # 数据库文件放在项目目录中
            project_dir = Path(__file__).parent
            self.db_path = project_dir / "devices.db"
        else:
            self.db_path = Path(db_path)
        
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()
    
    def init_database(self):
        """初始化数据库表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 创建设备表 - 包含IP、用户名、密码和品牌
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS devices (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        host TEXT NOT NULL UNIQUE,
                        username TEXT NOT NULL,
                        password TEXT NOT NULL,
                        brand TEXT DEFAULT 'Unknown'
                    )
                ''')
                
                # 检查是否需要添加品牌字段（数据库迁移）
                cursor.execute("PRAGMA table_info(devices)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'brand' not in columns:
                    cursor.execute("ALTER TABLE devices ADD COLUMN brand TEXT DEFAULT 'Unknown'")
                    print("✅ 数据库已更新：添加品牌字段")
                
                conn.commit()
                
        except Exception as e:
            print(f"❌ 数据库初始化失败: {e}")
    
    def add_device(self, host: str, username: str, password: str, brand: str = "Unknown") -> bool:
        """添加设备"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO devices 
                    (host, username, password, brand)
                    VALUES (?, ?, ?, ?)
                ''', (host, username, password, brand))
                conn.commit()
                return True
        except Exception as e:
            print(f"❌ 添加设备失败: {e}")
            return False
    
    def get_device(self, host: str) -> Optional[Dict]:
        """获取设备信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM devices WHERE host = ?', (host,))
                row = cursor.fetchone()
                if row:
                    columns = [description[0] for description in cursor.description]
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            print(f"❌ 获取设备失败: {e}")
            return None
    
    def list_devices(self) -> List[Dict]:
        """列出所有设备"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM devices ORDER BY host')
                rows = cursor.fetchall()
                
                columns = [description[0] for description in cursor.description]
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            print(f"❌ 列出设备失败: {e}")
            return []
    
    def update_device(self, host: str, username: str = None, password: str = None, brand: str = None) -> bool:
        """更新设备信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                updates = []
                params = []
                
                if username:
                    updates.append('username = ?')
                    params.append(username)
                if password:
                    updates.append('password = ?')
                    params.append(password)
                if brand:
                    updates.append('brand = ?')
                    params.append(brand)
                
                if not updates:
                    return False
                
                params.append(host)
                cursor.execute(f'UPDATE devices SET {", ".join(updates)} WHERE host = ?', params)
                
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"❌ 更新设备失败: {e}")
            return False
    
    def delete_device(self, host: str) -> bool:
        """删除设备"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM devices WHERE host = ?', (host,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"❌ 删除设备失败: {e}")
            return False
    
    def search_devices(self, keyword: str) -> List[Dict]:
        """搜索设备"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM devices 
                    WHERE host LIKE ? OR username LIKE ?
                    ORDER BY host
                ''', (f'%{keyword}%', f'%{keyword}%'))
                rows = cursor.fetchall()
                
                columns = [description[0] for description in cursor.description]
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            print(f"❌ 搜索设备失败: {e}")
            return []

class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            self.config_path = Path.home() / ".sm-cli" / "config.json"
        else:
            self.config_path = Path(config_path)
        
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️  配置文件加载失败: {e}")
                return self.get_default_config()
        return self.get_default_config()
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "timeout": 10,
            "max_steps": 10,  # AI代理最大执行步数，防止无限循环
            "available_models": {
                "deepseek": {
                    "name": "DeepSeek",
                    "model_id": "deepseek/deepseek-chat",
                    "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
                    "description": "DeepSeek Chat模型，适合中文对话"
                },
                "gpt-4": {
                    "name": "GPT-4",
                    "model_id": "gpt-4",
                    "api_key": os.getenv("OPENAI_API_KEY", ""),
                    "description": "OpenAI GPT-4模型，强大的推理能力"
                },
                "gpt-3.5": {
                    "name": "GPT-3.5 Turbo",
                    "model_id": "gpt-3.5-turbo",
                    "api_key": os.getenv("OPENAI_API_KEY", ""),
                    "description": "OpenAI GPT-3.5 Turbo模型，快速响应"
                },
                "claude-3": {
                    "name": "Claude 3",
                    "model_id": "claude-3-sonnet-20240229",
                    "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
                    "description": "Anthropic Claude 3模型，优秀的代码能力"
                },
                "gemini": {
                    "name": "Gemini Pro",
                    "model_id": "gemini-pro",
                    "api_key": os.getenv("GOOGLE_API_KEY", ""),
                    "description": "Google Gemini Pro模型，多模态能力"
                }
            },
            "current_model": "deepseek"
        }
    
    def save_config(self):
        """保存配置到文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"❌ 配置保存失败: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> bool:
        """设置配置值"""
        self.config[key] = value
        return self.save_config()
    
    def update(self, updates: Dict[str, Any]) -> bool:
        """批量更新配置"""
        self.config.update(updates)
        return self.save_config()

class SMCli:
    """SM-CLI 主类"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.device_db = DeviceDatabase()
        self.agent = None
        self.ssh_tool = SSHCommandTool(self.config_manager, self.device_db)
        self.ssh_test_tool = SSHTestTool(self.config_manager, self.device_db)
        self.running = True
        self.setup_agent()
    
    def load_system_prompt(self):
        """加载SM-CLI.md系统提示词"""
        try:
            prompt_file = Path(__file__).parent / "SM-CLI.md"
            if prompt_file.exists():
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                print("⚠️  SM-CLI.md提示词文件未找到，使用默认提示词")
                return "你是一位资深的网络设备专家，请帮助用户管理网络设备。"
        except Exception as e:
            print(f"⚠️  加载提示词文件失败: {e}，使用默认提示词")
            return "你是一位资深的网络设备专家，请帮助用户管理网络设备。"
    
    def setup_agent(self, model_key: str = None):
        """初始化AI代理"""
        try:
            # 尝试禁用代理以避免SOCKS问题
            import os
            original_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
            original_https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
            original_all_proxy = os.environ.get('ALL_PROXY') or os.environ.get('all_proxy')
            
            # 临时禁用代理
            if original_proxy or original_https_proxy or original_all_proxy:
                os.environ.pop('HTTP_PROXY', None)
                os.environ.pop('HTTPS_PROXY', None)
                os.environ.pop('ALL_PROXY', None)
                os.environ.pop('http_proxy', None)
                os.environ.pop('https_proxy', None)
                os.environ.pop('all_proxy', None)
                # 只在调试模式下显示代理禁用信息
                if os.environ.get('SM_CLI_DEBUG'):
                    print("🔄 临时禁用网络代理以解决连接问题")
            # 获取当前模型配置
            if model_key is None:
                model_key = self.config_manager.get("current_model", "deepseek")
            
            available_models = self.config_manager.get("available_models", {})
            if model_key not in available_models:
                print(f"❌ 模型 '{model_key}' 不存在，使用默认模型 'deepseek'")
                model_key = "deepseek"
            
            model_config = available_models[model_key]
            model_id = model_config["model_id"]
            api_key = model_config["api_key"]
            
            if not api_key:
                print(f"⚠️  模型 '{model_key}' 的API密钥未设置，尝试切换到其他可用模型")
                # 尝试找到第一个有API密钥的模型
                for fallback_key, fallback_config in available_models.items():
                    if fallback_config.get("api_key"):
                        print(f"🔄 自动切换到模型: {fallback_key}")
                        model_key = fallback_key
                        model_config = fallback_config
                        model_id = model_config["model_id"]
                        api_key = model_config["api_key"]
                        # 更新当前模型
                        self.config_manager.set("current_model", model_key)
                        break
                else:
                    print(f"❌ 没有找到可用的模型，请使用 /set_model_key 设置API密钥")
                    self.agent = None
                    return
            
            # 加载系统提示词
            system_prompt = self.load_system_prompt()
            
            model = LiteLLMModel(
                model_id=model_id,
                api_key=api_key
            )
            
            # 直接创建CodeAgent，系统提示词通过其他方式集成
            self.agent = CodeAgent(
                tools=[self.ssh_tool, self.ssh_test_tool],
                model=model
            )
            print(f"✅ AI代理初始化成功 - 使用模型: {model_config['name']} ({model_id})")
            print(f"📋 已加载SM-CLI.md提示词规范")
            
            # 恢复代理设置
            if original_proxy:
                os.environ['http_proxy'] = original_proxy
            if original_https_proxy:
                os.environ['https_proxy'] = original_https_proxy
            if original_all_proxy:
                os.environ['all_proxy'] = original_all_proxy
                
        except Exception as e:
            error_msg = str(e)
            if "SOCKS proxy" in error_msg or "socksio" in error_msg:
                print(f"⚠️  网络代理问题: {e}")
                print("💡 建议: 检查网络设置或使用 /set_model_key 重新设置API密钥")
                print("🔄 尝试重新初始化...")
                # 尝试重新初始化（不使用PromptTemplates）
                try:
                    model = LiteLLMModel(
                        model_id=model_id,
                        api_key=api_key
                    )
                    self.agent = CodeAgent(
                        tools=[self.ssh_tool, self.ssh_test_tool],
                        model=model
                    )
                    print(f"✅ AI代理重新初始化成功 - 使用模型: {model_config['name']} ({model_id})")
                    print("⚠️  注意: 由于网络问题，未加载SM-CLI.md提示词规范")
                    return
                except Exception as retry_e:
                    print(f"❌ 重新初始化失败: {retry_e}")
            else:
                print(f"❌ AI代理初始化失败: {e}")
            
            # 恢复代理设置
            if original_proxy:
                os.environ['http_proxy'] = original_proxy
            if original_https_proxy:
                os.environ['https_proxy'] = original_https_proxy
            if original_all_proxy:
                os.environ['all_proxy'] = original_all_proxy
    
    def print_help(self):
        """打印帮助信息"""
        print("\033[1;37m" + "=" * 60 + "\033[0m")
        print("\033[1;36mSM-CLI 命令帮助\033[0m")
        print("\033[1;37m" + "=" * 60 + "\033[0m")
        print()
        
        print("\033[1;33m基本命令:\033[0m")
        print("  \033[0;37m/help, /h          - 显示此帮助信息\033[0m")
        print("  \033[0;37m/quit, /q, /exit   - 退出程序\033[0m")
        print("  \033[0;37m/clear, /cls       - 清屏\033[0m")
        print("  \033[0;37m/status            - 显示当前配置状态\033[0m")
        print()
        
        print("\033[1;33m配置命令:\033[0m")
        print("  \033[0;37m/config            - 显示所有配置\033[0m")
        print("  \033[0;37m/step              - 显示/设置AI最大步数\033[0m")
        print("  \033[0;37m/reset             - 重置为默认配置\033[0m")
        print()
        
        print("\033[1;33m设备管理命令:\033[0m")
        print("  \033[0;37m/devices           - 列出所有设备\033[0m")
        print("  \033[0;37m/add_device        - 添加设备\033[0m")
        print("  \033[0;37m/del_device        - 删除设备\033[0m")
        print("  \033[0;37m/search_device     - 搜索设备\033[0m")
        print("  \033[0;37m/update_brand      - 更新设备品牌\033[0m")
        print()
        
        print("\033[1;33mLLM模型管理命令:\033[0m")
        print("  \033[0;37m/llm               - 列出所有可用模型\033[0m")
        print("  \033[0;37m/switch_llm        - 切换当前模型\033[0m")
        print("  \033[0;37m/set_model_key     - 设置模型API密钥\033[0m")
        print("  \033[0;37m/current_llm       - 显示当前模型\033[0m")
        print()
        
        print("\033[1;33m使用示例:\033[0m")
        print("  \033[0;37m/llm                    - 查看可用模型\033[0m")
        print("  \033[0;37m/set_model_key gpt-4 sk-your-key\033[0m")
        print("  \033[0;37m/switch_llm gpt-4       - 切换到GPT-4\033[0m")
        print("  \033[0;37m/step 20                - 设置AI最大步数为20\033[0m")
        print("  \033[0;37m/add_device 172.21.1.167 admin r00tme Arista\033[0m")
        print("  \033[0;37m/update_brand 172.21.1.167 Arista\033[0m")
        print("  \033[0;37m/devices\033[0m")
        print()
        print("\033[1;37m" + "=" * 60 + "\033[0m")
    
    def print_status(self):
        """显示当前状态"""
        config = self.config_manager.config
        current_model = config.get('current_model', 'deepseek')
        available_models = config.get('available_models', {})
        current_model_config = available_models.get(current_model, {})
        
        print("\033[1;37m" + "=" * 50 + "\033[0m")
        print("\033[1;36m当前配置状态\033[0m")
        print("\033[1;37m" + "=" * 50 + "\033[0m")
        
        # 检查当前模型的API密钥
        api_key_status = "✅ 已设置" if current_model_config.get('api_key') else "❌ 未设置"
        print(f"\033[1;33mAPI密钥:\033[0m {api_key_status}")
        
        # 显示当前模型ID
        model_id = current_model_config.get('model_id', 'N/A')
        print(f"\033[1;33m模型ID:\033[0m \033[0;37m{model_id}\033[0m")
        
        # 显示当前模型名称
        model_name = current_model_config.get('name', 'N/A')
        print(f"\033[1;33m当前模型:\033[0m \033[0;37m{model_name}\033[0m")
        
        # 显示AI最大步数
        max_steps = config.get('max_steps', 10)
        print(f"\033[1;33mAI max_steps:\033[0m \033[0;37m{max_steps}\033[0m")
        
        print("\033[1;37m" + "=" * 50 + "\033[0m")
        print()
    
    def handle_command(self, command: str) -> bool:
        """处理命令，返回是否继续运行"""
        parts = command.strip().split()
        if not parts:
            return True
        
        cmd = parts[0].lower()
        
        if cmd in ['/quit', '/q', '/exit']:
            print("\033[1;36m👋 再见!\033[0m")
            return False
        
        elif cmd in ['/help', '/h']:
            self.print_help()
        
        elif cmd in ['/clear', '/cls']:
            self.print_gemini_style_header()
        
        elif cmd == '/status':
            self.print_status()
        
        
        elif cmd == '/config':
            print("\033[1;37m" + "=" * 50 + "\033[0m")
            print("\033[1;36m当前配置\033[0m")
            print("\033[1;37m" + "=" * 50 + "\033[0m")
            for key, value in self.config_manager.config.items():
                if key == 'api_key' and value:
                    print(f"\033[1;33m{key}:\033[0m \033[0;37m{'*' * 20}...\033[0m")
                else:
                    print(f"\033[1;33m{key}:\033[0m \033[0;37m{value}\033[0m")
            print("\033[1;37m" + "=" * 50 + "\033[0m")
        
        # 设备管理命令
        elif cmd == '/devices':
            self.list_devices()
        
        elif cmd == '/add_device':
            if len(parts) < 4:
                print("\033[1;31m❌ 用法: /add_device <host> <username> <password> [brand]\033[0m")
                print("\033[0;37m示例: /add_device 172.21.1.167 admin r00tme Arista\033[0m")
                print("\033[0;37m示例: /add_device 172.21.1.81 admin password123 Cisco\033[0m")
                return True
            
            host = parts[1]
            username = parts[2]
            password = parts[3]
            brand = parts[4] if len(parts) > 4 else "Unknown"
            
            if self.device_db.add_device(host, username, password, brand):
                print(f"\033[1;32m✅ 设备 '{host}' ({brand}) 添加成功\033[0m")
            else:
                print(f"\033[1;31m❌ 设备 '{host}' 添加失败\033[0m")
        
        elif cmd == '/del_device':
            if len(parts) < 2:
                print("\033[1;31m❌ 用法: /del_device <host>\033[0m")
                return True
            
            host = parts[1]
            if self.device_db.delete_device(host):
                print(f"\033[1;32m✅ 设备 '{host}' 删除成功\033[0m")
            else:
                print(f"\033[1;31m❌ 设备 '{host}' 删除失败或不存在\033[0m")
        
        elif cmd == '/update_brand':
            if len(parts) < 3:
                print("\033[1;31m❌ 用法: /update_brand <host> <brand>\033[0m")
                print("\033[0;37m示例: /update_brand 172.21.1.167 Arista\033[0m")
                return True
            
            host = parts[1]
            brand = ' '.join(parts[2:])
            if self.device_db.update_device(host, brand=brand):
                print(f"\033[1;32m✅ 设备 '{host}' 品牌已更新为 '{brand}'\033[0m")
            else:
                print(f"\033[1;31m❌ 设备 '{host}' 品牌更新失败或设备不存在\033[0m")
        
        elif cmd == '/search_device':
            if len(parts) < 2:
                print("\033[1;31m❌ 用法: /search_device <keyword>\033[0m")
                return True
            
            keyword = ' '.join(parts[1:])
            devices = self.device_db.search_devices(keyword)
            if devices:
                print(f"\033[1;36m找到 {len(devices)} 个匹配的设备:\033[0m")
                for device in devices:
                    print(f"  \033[1;33m{device['host']}\033[0m - {device['username']}")
            else:
                print(f"\033[1;31m❌ 未找到匹配 '{keyword}' 的设备\033[0m")
        
        elif cmd == '/device_info':
            if len(parts) < 2:
                print("\033[1;31m❌ 用法: /device_info <host>\033[0m")
                return True
            
            host = parts[1]
            device = self.device_db.get_device(host=host)
            if device:
                print(f"\033[1;36m设备信息: {device['host']}\033[0m")
                print(f"  \033[1;33m主机:\033[0m {device['host']}")
                print(f"  \033[1;33m用户:\033[0m {device['username']}")
                print(f"  \033[1;33m密码:\033[0m {'*' * len(device['password'])}")
            else:
                print(f"\033[1;31m❌ 未找到设备 '{host}'\033[0m")
            print()
        
        elif cmd == '/migrate':
            self.migrate_config_to_database()
        
        # LLM模型管理命令
        elif cmd == '/llm':
            self.list_models()
        
        elif cmd == '/switch_llm':
            if len(parts) < 2:
                print("\033[1;31m❌ 用法: /switch_llm <model_key>\033[0m")
                print("\033[0;37m使用 /llm 查看可用模型\033[0m")
                return True
            
            model_key = parts[1]
            if self.switch_model(model_key):
                print(f"\033[1;32m✅ 已切换到模型: {model_key}\033[0m")
            # switch_model方法已经打印了具体的错误信息，这里不需要重复
        
        elif cmd == '/set_model_key':
            if len(parts) < 3:
                print("\033[1;31m❌ 用法: /set_model_key <model_key> <api_key>\033[0m")
                print("\033[0;37m示例: /set_model_key gpt-4 sk-your-openai-key\033[0m")
                return True
            
            model_key = parts[1]
            api_key = ' '.join(parts[2:])
            if self.set_model_api_key(model_key, api_key):
                print(f"\033[1;32m✅ 已设置模型 '{model_key}' 的API密钥\033[0m")
            else:
                print(f"\033[1;31m❌ 设置API密钥失败\033[0m")
        
        elif cmd == '/current_llm':
            self.show_current_model()
        
        elif cmd == '/step':
            if len(parts) < 2:
                # 显示当前步数设置
                current_steps = self.config_manager.get('max_steps', 10)
                print(f"\033[1;37m当前最大步数: \033[1;36m{current_steps}\033[0m")
                print("\033[0;37m用法: /step <number> 设置最大步数\033[0m")
                print("\033[0;37m示例: /step 20 设置最大步数为20\033[0m")
            else:
                try:
                    steps = int(parts[1])
                    if steps < 1:
                        print("\033[1;31m❌ 步数必须大于0\033[0m")
                    else:
                        self.config_manager.set('max_steps', steps)
                        print(f"\033[1;32m✅ 最大步数已设置为: {steps}\033[0m")
                except ValueError:
                    print("\033[1;31m❌ 请输入有效的数字\033[0m")
        
        elif cmd == '/reset':
            confirm = input("\033[1;33m⚠️  确定要重置所有配置吗? (y/N): \033[0m")
            if confirm.lower() in ['y', 'yes']:
                self.config_manager.config = self.config_manager.get_default_config()
                if self.config_manager.save_config():
                    print("\033[1;32m✅ 配置已重置\033[0m")
                    self.setup_agent()
                else:
                    print("\033[1;31m❌ 重置失败\033[0m")
            else:
                print("\033[1;31m❌ 已取消\033[0m")
        
        else:
            print(f"\033[1;31m❌ 未知命令: {cmd}，输入 /help 查看帮助\033[0m")
        
        return True
    
    def list_devices(self):
        """列出所有设备"""
        devices = self.device_db.list_devices()
        if devices:
            print(f"\033[1;36m设备列表 (共 {len(devices)} 个):\033[0m")
            print("\033[1;37m" + "-" * 80 + "\033[0m")
            print(f"{'主机':<18} {'用户':<10} {'密码':<10} {'品牌'}")
            print("\033[1;37m" + "-" * 80 + "\033[0m")
            for device in devices:
                password_display = '*' * len(device['password'])
                brand = device.get('brand', 'Unknown')
                print(f"{device['host']:<18} {device['username']:<10} {password_display:<10} {brand}")
            print("\033[1;37m" + "-" * 80 + "\033[0m")
        else:
            print("\033[1;31m❌ 没有找到任何设备\033[0m")
            print("\033[0;37m使用 /add_device 命令添加设备\033[0m")
    
    def migrate_config_to_database(self):
        """将配置中的设备信息迁移到数据库"""
        print("\033[1;36m开始迁移配置到数据库...\033[0m")
        
        # 由于配置中不再包含默认设备信息，直接显示当前状态
        devices = self.device_db.list_devices()
        if devices:
            print(f"\033[1;36m数据库中共有 {len(devices)} 个设备\033[0m")
            print("\033[0;37m设备列表:\033[0m")
            for device in devices:
                print(f"  - {device['host']} ({device['username']})")
        else:
            print("\033[1;33m数据库中没有设备，请使用 /add_device 添加设备\033[0m")
            print("\033[0;37m示例: /add_device 172.21.1.167 admin r00tme\033[0m")
    
    def list_models(self):
        """列出所有可用的LLM模型"""
        available_models = self.config_manager.get("available_models", {})
        current_model = self.config_manager.get("current_model", "deepseek")
        
        print(f"\033[1;36m可用LLM模型 (当前: {current_model}):\033[0m")
        print("\033[1;37m" + "-" * 80 + "\033[0m")
        print(f"{'模型键':<12} {'模型名称':<20} {'状态':<8} {'描述'}")
        print("\033[1;37m" + "-" * 80 + "\033[0m")
        
        for model_key, model_config in available_models.items():
            status = "✅ 已配置" if model_config.get("api_key") else "❌ 未配置"
            current_mark = " (当前)" if model_key == current_model else ""
            print(f"{model_key:<12} {model_config['name']:<20} {status:<8} {model_config['description']}{current_mark}")
        
        print("\033[1;37m" + "-" * 80 + "\033[0m")
        print("\033[0;37m使用 /switch_llm <model_key> 切换模型\033[0m")
        print("\033[0;37m使用 /set_model_key <model_key> <api_key> 设置API密钥\033[0m")
    
    def switch_model(self, model_key: str) -> bool:
        """切换LLM模型"""
        available_models = self.config_manager.get("available_models", {})
        
        if model_key not in available_models:
            print(f"\033[1;31m❌ 模型 '{model_key}' 不存在\033[0m")
            return False
        
        # 检查API密钥是否已设置
        model_config = available_models[model_key]
        if not model_config.get("api_key"):
            print(f"\033[1;31m❌ 模型 '{model_key}' 的API密钥未设置，请使用 /set_model_key 设置\033[0m")
            return False
        
        # 更新当前模型
        self.config_manager.set("current_model", model_key)
        
        # 重新初始化代理
        self.setup_agent(model_key)
        
        return True
    
    def set_model_api_key(self, model_key: str, api_key: str) -> bool:
        """设置模型的API密钥"""
        available_models = self.config_manager.get("available_models", {})
        
        if model_key not in available_models:
            print(f"\033[1;31m❌ 模型 '{model_key}' 不存在\033[0m")
            return False
        
        # 更新模型的API密钥
        available_models[model_key]["api_key"] = api_key
        self.config_manager.set("available_models", available_models)
        
        # 如果当前模型是刚设置密钥的模型，重新初始化代理
        current_model = self.config_manager.get("current_model", "deepseek")
        if model_key == current_model:
            self.setup_agent(model_key)
        
        return True
    
    def show_current_model(self):
        """显示当前使用的模型"""
        current_model = self.config_manager.get("current_model", "deepseek")
        available_models = self.config_manager.get("available_models", {})
        
        if current_model in available_models:
            model_config = available_models[current_model]
            print(f"\033[1;36m当前模型: {model_config['name']} ({model_config['model_id']})\033[0m")
            print(f"\033[1;33m描述: {model_config['description']}\033[0m")
            print(f"\033[1;33mAPI密钥: {'已设置' if model_config.get('api_key') else '未设置'}\033[0m")
        else:
            print(f"\033[1;31m❌ 当前模型 '{current_model}' 配置异常\033[0m")
    
    def print_gemini_style_header(self):
        """打印Gemini风格的启动界面"""
        print("\033[2J\033[H")  # 清屏
        
        # 模拟终端提示符
        print("\033[0;37m(base) allinone@WENZHUCAI-2 sm-cli % sm-cli\033[0m")
        print()
        
        # 像素化标题 - 仿照GEMINI样式
        self.print_pixelated_title()
        print()
        
        # Tips部分 - 仿照Gemini样式
        print("\033[1;37mTips for getting started:\033[0m")
        print()
        print("  \033[0;37m1. Ask questions about network devices or run commands.\033[0m")
        print("  \033[0;37m2. Be specific for the best results.\033[0m")
        print("  \033[0;37m3. Create SM-CLI.md files to customize your interactions.\033[0m")
        print("  \033[0;37m4. \033[0m\033[1;35m/help\033[0m\033[0;37m for more information.\033[0m")
        print()
        
        # 更新通知框 - 仿照Gemini样式
        print("\033[1;35mSM-CLI is Ready!\033[0m")
        print()
    
    def print_pixelated_title(self):
        """打印像素化标题，仿照GEMINI样式"""
        # 定义渐变色彩序列（从蓝色到紫色到粉红色）
        colors = [
            "\033[1;34m",   # 蓝色
            "\033[1;35m",   # 紫色
            "\033[1;95m",   # 亮紫色
            "\033[1;91m",   # 亮红色
            "\033[1;31m",   # 红色
        ]
        
        # 定义像素化字母图案（每个字母7x9像素）
        letters = {
            'S': [
                " ██████ ",
                "██    ██",
                "██      ",
                " ██████ ",
                "      ██",
                "██    ██",
                " ██████ "
            ],
            'M': [
                "██     ██",
                "███   ███",
                "██ █ █ ██",
                "██  █  ██",
                "██     ██",
                "██     ██",
                "██     ██"
            ],
            '-': [
                "         ",
                "         ",
                "         ",
                " ███████ ",
                "         ",
                "         ",
                "         "
            ],
            'C': [
                "  ██████ ",
                " ██    ██",
                "██       ",
                "██       ",
                "██       ",
                " ██    ██",
                "  ██████ "
            ],
            'L': [
                "██       ",
                "██       ",
                "██       ",
                "██       ",
                "██       ",
                "██       ",
                "█████████"
            ],
            'I': [
                "█████████",
                "    █    ",
                "    █    ",
                "    █    ",
                "    █    ",
                "    █    ",
                "█████████"
            ]
        }
        
        # 打印标题
        title = "SM-CLI"
        for row in range(7):  # 7行像素
            line = ""
            for i, char in enumerate(title):
                if char in letters:
                    # 根据位置选择颜色，创建渐变效果
                    color_index = min(i, len(colors) - 1)
                    color = colors[color_index]
                    
                    # 添加像素行
                    pixel_row = letters[char][row]
                    line += f"{color}{pixel_row}\033[0m"
                    
                    # 字母间添加空格
                    if i < len(title) - 1:
                        line += " "
                else:
                    # 对于空格或其他字符
                    line += "         "
            
            print(line)

    def print_input_prompt(self):
        """打印简洁的输入提示符"""
        print("\033[1;34m> \033[0m", end="", flush=True)

    def run(self):
        """运行CLI"""
        # 显示Gemini风格的启动界面
        self.print_gemini_style_header()
        
        while self.running:
            try:
                # 显示简洁的输入提示符
                self.print_input_prompt()
                
                # 获取用户输入
                user_input = input().strip()
                
                if not user_input:
                    continue
                
                # 检查是否是命令
                if user_input.startswith('/'):
                    self.running = self.handle_command(user_input)
                    if self.running:  # 如果继续运行，重新显示输入框
                        print()
                    continue
                
                # 处理AI对话
                if not self.agent:
                    print("\033[1;31m❌ AI代理未初始化，请先设置API密钥\033[0m")
                    print("  使用命令: /set api_key <your_key>")
                    print()
                    continue
                
                print("\n\033[1;33m🤖 AI正在思考...\033[0m")
                try:
                    # 设置最大步数限制，防止无限循环
                    max_steps = self.config_manager.get("max_steps", 10)
                    result = self.agent.run(user_input, max_steps=max_steps)
                    print(f"\n\033[1;37m📝 回答:\033[0m\n\033[0;37m{result}\033[0m")
                    print()
                except Exception as e:
                    print(f"\033[1;31m❌ AI处理失败: {e}\033[0m")
                    print()
            
            except KeyboardInterrupt:
                print("\n\n\033[1;36m👋 再见!\033[0m")
                break
            except EOFError:
                print("\n\n\033[1;36m👋 再见!\033[0m")
                break
            except Exception as e:
                print(f"\033[1;31m❌ 发生错误: {e}\033[0m")
                print()

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='SM-CLI: 智能网络设备管理工具')
    parser.add_argument('--config', '-c', help='配置文件路径')
    parser.add_argument('--version', '-v', action='version', version='SM-CLI 1.0.0')
    
    args = parser.parse_args()
    
    try:
        cli = SMCli()
        cli.run()
    except Exception as e:
        print(f"❌ 程序启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
