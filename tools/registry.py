# tools/registry.py - SECURE VERSION with ALL TOOLS
import asyncio
import logging
import subprocess
import os
import re
import json
import sqlite3
import smtplib
import imaplib
import email
from datetime import datetime, timedelta
from typing import Dict, Any, List, Set, Optional
from abc import ABC, abstractmethod
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

BLOCKED_COMMANDS = {
    'rm', 'del', 'format', 'fdisk', 'dd', 'mkfs', 
    'shutdown', 'reboot', 'poweroff', 'regedit',
    'format.com', 'rd', 'rmdir'
}

ALLOWED_PATHS = {
    './workspace', 'workspace', 
    os.path.abspath('./workspace')
}

class SecurityError(Exception):
    pass

class BaseTool(ABC):
    name: str
    description: str
    parameters: Dict[str, Any]
    
    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        pass

class SecureBashTool(BaseTool):
    name = "bash"
    description = "Execute shell commands in sandboxed environment (RESTRICTED)"
    parameters = {
        "command": "string - shell command to execute",
        "timeout": "integer - max execution seconds (default 30)"
    }
    
    def _validate_command(self, command: str) -> None:
        cmd_lower = command.lower().strip()
        tokens = re.split(r'[;&|<>]', cmd_lower)
        for token in tokens:
            token = token.strip()
            base_cmd = token.split()[0] if token.split() else ""
            if base_cmd in BLOCKED_COMMANDS:
                raise SecurityError(f"Command '{base_cmd}' is blocked")
        if '..' in command:
            raise SecurityError("Path traversal (..) is not allowed")
    
    async def execute(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        try:
            self._validate_command(command)
            workspace = os.path.abspath('./workspace')
            os.makedirs(workspace, exist_ok=True)
            
            env = os.environ.copy()
            sensitive_vars = ['PATH', 'HOME', 'USERPROFILE', 'APPDATA', 'TEMP', 'TMP']
            for var in sensitive_vars:
                if var in env:
                    del env[var]
            env['PATH'] = 'C:\\Windows\\System32;C:\\Windows'
            
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workspace,
                env=env
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                return {
                    "stdout": stdout.decode('utf-8', errors='replace'),
                    "stderr": stderr.decode('utf-8', errors='replace'),
                    "returncode": process.returncode,
                    "sandboxed": True,
                    "workspace": workspace
                }
            except asyncio.TimeoutError:
                process.kill()
                return {"error": "Command timed out", "sandboxed": True}
                
        except SecurityError as e:
            return {"error": f"Security blocked: {str(e)}", "blocked": True}
        except Exception as e:
            return {"error": str(e), "sandboxed": True}

class SecureFileTool(BaseTool):
    name = "file"
    description = "Read/write files in workspace (SANDBOXED)"
    parameters = {
        "operation": "read/write/list",
        "path": "relative path in workspace",
        "content": "content for write operations"
    }
    
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
    def __init__(self, workspace_path: str = "./workspace"):
        self.workspace = os.path.abspath(workspace_path)
        os.makedirs(self.workspace, exist_ok=True)
    
    def _validate_path(self, path: str) -> str:
        path = path.replace('\0', '')
        requested_path = os.path.normpath(os.path.join(self.workspace, path))
        real_workspace = os.path.realpath(self.workspace)
        real_requested = os.path.realpath(requested_path)
        
        if not real_requested.startswith(real_workspace):
            raise SecurityError(f"Path '{path}' escapes workspace sandbox")
        
        basename = os.path.basename(real_requested)
        if basename.startswith('.') and basename not in ['.', '..']:
            raise SecurityError("Access to hidden files is blocked")
        
        return real_requested
    
    async def execute(self, operation: str, path: str, content: str = None):
        try:
            safe_path = self._validate_path(path)
            
            if operation == "read":
                if not os.path.exists(safe_path):
                    return {"error": f"File not found: {path}"}
                size = os.path.getsize(safe_path)
                if size > self.MAX_FILE_SIZE:
                    return {"error": f"File too large: {size} bytes"}
                with open(safe_path, 'r', encoding='utf-8', errors='replace') as f:
                    return {"content": f.read()}
                    
            elif operation == "write":
                dir_path = os.path.dirname(safe_path)
                os.makedirs(dir_path, exist_ok=True)
                if content and len(content) > self.MAX_FILE_SIZE:
                    return {"error": f"Content too large: {len(content)} bytes"}
                with open(safe_path, 'w', encoding='utf-8') as f:
                    f.write(content or "")
                return {"success": True, "bytes_written": len(content or "")}
                
            elif operation == "list":
                if not os.path.exists(safe_path):
                    return {"files": []}
                files = os.listdir(safe_path)
                files = [f for f in files if not f.startswith('.')]
                return {"files": files}
            else:
                return {"error": f"Unknown operation: {operation}"}
                
        except SecurityError as e:
            return {"error": f"Security: {str(e)}"}
        except Exception as e:
            return {"error": str(e)}

class RestrictedPythonTool(BaseTool):
    name = "python"
    description = "Execute Python code safely (RESTRICTED)"
    parameters = {"code": "string - Python code to execute"}
    
    ALLOWED_BUILTINS = {
        'abs', 'all', 'any', 'bin', 'bool', 'chr', 'dict', 'dir', 
        'divmod', 'enumerate', 'filter', 'float', 'format', 'frozenset',
        'hasattr', 'hex', 'id', 'int', 'isinstance', 'issubclass', 'iter',
        'len', 'list', 'map', 'max', 'min', 'next', 'oct', 'ord', 'pow',
        'print', 'range', 'repr', 'reversed', 'round', 'set', 'slice',
        'sorted', 'str', 'sum', 'tuple', 'type', 'vars', 'zip'
    }
    
    BLOCKED_IMPORTS = ['os', 'sys', 'subprocess', 'importlib', 'builtins', '__import__']
    
    def _validate_code(self, code: str) -> None:
        code_lower = code.lower()
        for blocked in self.BLOCKED_IMPORTS:
            if f'import {blocked}' in code_lower or f'from {blocked}' in code_lower:
                raise SecurityError(f"Import '{blocked}' is not allowed")
        if '__import__' in code:
            raise SecurityError("Dynamic imports are blocked")
        if any(x in code for x in ['open(', 'file(', 'exec(', 'eval(']):
            raise SecurityError("File operations and code execution are blocked")
    
    async def execute(self, code: str) -> Dict[str, Any]:
        try:
            self._validate_code(code)
            safe_globals = {
                "__builtins__": {name: __builtins__[name] for name in self.ALLOWED_BUILTINS if hasattr(__builtins__, name)},
                "__name__": "__main__"
            }
            
            import concurrent.futures
            import io
            import sys
            
            def run_code():
                old_stdout = sys.stdout
                sys.stdout = io.StringIO()
                try:
                    exec(code, safe_globals)
                    output = sys.stdout.getvalue()
                    return output
                finally:
                    sys.stdout = old_stdout
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_code)
                try:
                    result = future.result(timeout=5)
                    return {"output": result, "sandboxed": True}
                except concurrent.futures.TimeoutError:
                    return {"error": "Code execution timed out (5s limit)", "sandboxed": True}
                    
        except SecurityError as e:
            return {"error": f"Security blocked: {str(e)}", "sandboxed": True}
        except Exception as e:
            return {"error": str(e), "sandboxed": True}

class BrowserTool(BaseTool):
    name = "browser"
    description = "Control browser for web automation (navigate, screenshot, extract text)"
    parameters = {
        "url": "string - URL to navigate to",
        "action": "string - navigate|screenshot|extract|click",
        "selector": "string - CSS selector (for click/extract)",
        "text": "string - text to type"
    }
    
    async def execute(self, url: str = None, action: str = "navigate", 
                     selector: str = None, text: str = None) -> Dict[str, Any]:
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = await context.new_page()
                
                if action == "navigate":
                    await page.goto(url, wait_until="networkidle")
                    title = await page.title()
                    content = await page.evaluate("""() => {
                        const article = document.querySelector('article') || 
                                      document.querySelector('main') || 
                                      document.body;
                        return article.innerText.substring(0, 5000);
                    }""")
                    await browser.close()
                    return {
                        "title": title,
                        "url": url,
                        "content_preview": content[:1000] + "..." if len(content) > 1000 else content,
                        "success": True
                    }
                
                elif action == "screenshot":
                    await page.goto(url, wait_until="networkidle")
                    screenshot_path = f"./workspace/screenshot_{int(asyncio.get_event_loop().time())}.png"
                    await page.screenshot(path=screenshot_path, full_page=True)
                    await browser.close()
                    return {
                        "screenshot_saved": screenshot_path,
                        "success": True
                    }
                
                elif action == "extract":
                    await page.goto(url, wait_until="networkidle")
                    if selector:
                        elements = await page.query_selector_all(selector)
                        texts = []
                        for el in elements[:10]:
                            text_content = await el.inner_text()
                            texts.append(text_content.strip())
                        return {"extracted": texts, "count": len(texts), "success": True}
                    else:
                        text_content = await page.inner_text("body")
                        return {"extracted": text_content[:5000], "success": True}
                
                await browser.close()
                return {"success": True, "action": action}
                
        except ImportError:
            return {"error": "Playwright not installed. Run: pip install playwright && playwright install chromium", "success": False}
        except Exception as e:
            return {"error": str(e), "success": False}

class GitHubTool(BaseTool):
    name = "github"
    description = "Interact with GitHub (repos, issues, PRs)"
    parameters = {
        "action": "string - get_repo|list_issues|create_issue|get_readme",
        "repo": "string - owner/repo format",
        "title": "string - issue title (for create_issue)",
        "body": "string - issue body (for create_issue)"
    }
    
    async def execute(self, action: str, repo: str, title: str = None, 
                     body: str = None) -> Dict[str, Any]:
        import aiohttp
        
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            return {"error": "GitHub token required. Set GITHUB_TOKEN env var.", "success": False}
        
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        base_url = "https://api.github.com"
        
        try:
            async with aiohttp.ClientSession() as session:
                if action == "get_repo":
                    async with session.get(f"{base_url}/repos/{repo}", headers=headers) as resp:
                        data = await resp.json()
                        return {
                            "name": data.get("name"),
                            "stars": data.get("stargazers_count"),
                            "description": data.get("description"),
                            "url": data.get("html_url"),
                            "success": True
                        }
                
                elif action == "get_readme":
                    async with session.get(f"{base_url}/repos/{repo}/readme", headers=headers) as resp:
                        data = await resp.json()
                        import base64
                        content = base64.b64decode(data.get("content", "")).decode("utf-8")
                        return {"readme": content[:2000], "success": True}
                
                elif action == "list_issues":
                    async with session.get(f"{base_url}/repos/{repo}/issues?state=open&per_page=5", headers=headers) as resp:
                        data = await resp.json()
                        issues = [{"number": i["number"], "title": i["title"]} for i in data]
                        return {"issues": issues, "count": len(issues), "success": True}
                
                elif action == "create_issue":
                    if not title:
                        return {"error": "Title required for create_issue", "success": False}
                    payload = {"title": title, "body": body or ""}
                    async with session.post(f"{base_url}/repos/{repo}/issues", 
                                          headers=headers, json=payload) as resp:
                        data = await resp.json()
                        return {
                            "issue_number": data.get("number"),
                            "url": data.get("html_url"),
                            "success": True
                        }
                
                return {"error": f"Unknown action: {action}", "success": False}
                
        except Exception as e:
            return {"error": str(e), "success": False}

class HTTPTool(BaseTool):
    name = "http"
    description = "Make HTTP requests to APIs (GET, POST, etc)"
    parameters = {
        "url": "string - URL to request",
        "method": "string - GET|POST|PUT|DELETE",
        "headers": "object - request headers",
        "body": "object - JSON body for POST/PUT"
    }
    
    async def execute(self, url: str, method: str = "GET", 
                     headers: dict = None, body: dict = None) -> Dict[str, Any]:
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method.upper(),
                    url=url,
                    headers=headers or {},
                    json=body
                ) as resp:
                    text = await resp.text()
                    try:
                        json_data = await resp.json()
                        return {
                            "status": resp.status,
                            "json": json_data,
                            "success": 200 <= resp.status < 300
                        }
                    except:
                        return {
                            "status": resp.status,
                            "text": text[:2000],
                            "success": 200 <= resp.status < 300
                        }
        except Exception as e:
            return {"error": str(e), "success": False}

class DatabaseTool(BaseTool):
    """SQLite database operations"""
    name = "database"
    description = "SQLite database operations (query, insert, create table)"
    parameters = {
        "action": "string - query|insert|create|update|delete",
        "database": "string - database file name (default: agentvault.db)",
        "sql": "string - SQL query to execute",
        "data": "object - data for insert (dict)"
    }
    
    def __init__(self):
        self.db_dir = os.path.abspath('./data')
        os.makedirs(self.db_dir, exist_ok=True)
    
    def _get_connection(self, db_name: str):
        db_path = os.path.join(self.db_dir, db_name)
        return sqlite3.connect(db_path)
    
    async def execute(self, action: str, database: str = "agentvault.db", 
                     sql: str = None, data: dict = None) -> Dict[str, Any]:
        try:
            # Security: Only allow safe SQL operations
            sql_lower = sql.lower() if sql else ""
            
            # Block dangerous operations
            blocked_keywords = ['drop', 'alter', 'grant', 'attach', 'detach']
            for keyword in blocked_keywords:
                if keyword in sql_lower:
                    return {"error": f"SQL operation '{keyword}' is blocked for security", "success": False}
            
            conn = self._get_connection(database)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if action == "query":
                cursor.execute(sql)
                rows = cursor.fetchall()
                results = [dict(row) for row in rows]
                conn.close()
                return {"results": results, "count": len(results), "success": True}
            
            elif action == "insert":
                if data:
                    # Build insert from dict
                    columns = ', '.join(data.keys())
                    placeholders = ', '.join(['?' for _ in data])
                    sql = f"INSERT INTO {sql} ({columns}) VALUES ({placeholders})"
                    cursor.execute(sql, list(data.values()))
                else:
                    cursor.execute(sql)
                conn.commit()
                last_id = cursor.lastrowid
                conn.close()
                return {"success": True, "inserted_id": last_id}
            
            elif action == "create":
                cursor.execute(sql)
                conn.commit()
                conn.close()
                return {"success": True, "message": "Table created"}
            
            elif action == "update" or action == "delete":
                cursor.execute(sql)
                conn.commit()
                affected = cursor.rowcount
                conn.close()
                return {"success": True, "affected_rows": affected}
            
            else:
                conn.close()
                return {"error": f"Unknown action: {action}", "success": False}
                
        except Exception as e:
            return {"error": str(e), "success": False}

class EmailTool(BaseTool):
    """Email operations (SMTP/IMAP)"""
    name = "email"
    description = "Send and read emails via SMTP/IMAP"
    parameters = {
        "action": "string - send|read",
        "to": "string - recipient email (for send)",
        "subject": "string - email subject",
        "body": "string - email body",
        "folder": "string - folder to read from (default: INBOX)",
        "limit": "integer - max emails to read (default: 5)"
    }
    
    async def execute(self, action: str, to: str = None, subject: str = None,
                     body: str = None, folder: str = "INBOX", limit: int = 5) -> Dict[str, Any]:
        try:
            smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            email_user = os.getenv("EMAIL_USER")
            email_pass = os.getenv("EMAIL_PASSWORD")
            
            if not email_user or not email_pass:
                return {
                    "error": "Email credentials not configured. Set EMAIL_USER and EMAIL_PASSWORD in .env",
                    "success": False
                }
            
            if action == "send":
                if not to or not subject:
                    return {"error": "Recipient (to) and subject required", "success": False}
                
                msg = MIMEMultipart()
                msg['From'] = email_user
                msg['To'] = to
                msg['Subject'] = subject
                msg.attach(MIMEText(body or "", 'plain'))
                
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
                server.login(email_user, email_pass)
                server.send_message(msg)
                server.quit()
                
                return {"success": True, "message": f"Email sent to {to}"}
            
            elif action == "read":
                imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
                mail = imaplib.IMAP4_SSL(imap_server)
                mail.login(email_user, email_pass)
                mail.select(folder)
                
                _, search_data = mail.search(None, 'ALL')
                mail_ids = search_data[0].split()
                latest_ids = mail_ids[-limit:] if len(mail_ids) > limit else mail_ids
                
                emails = []
                for mail_id in reversed(latest_ids):
                    _, msg_data = mail.fetch(mail_id, '(RFC822)')
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            emails.append({
                                "from": msg.get("From"),
                                "subject": msg.get("Subject"),
                                "date": msg.get("Date")
                            })
                
                mail.close()
                mail.logout()
                return {"emails": emails, "count": len(emails), "success": True}
            
            else:
                return {"error": f"Unknown action: {action}", "success": False}
                
        except Exception as e:
            return {"error": str(e), "success": False}

class CalendarTool(BaseTool):
    """Simple calendar/task management using SQLite"""
    name = "calendar"
    description = "Calendar and task management (add events, list events, reminders)"
    parameters = {
        "action": "string - add|list|delete",
        "title": "string - event title",
        "date": "string - event date (YYYY-MM-DD)",
        "time": "string - event time (HH:MM)",
        "description": "string - event description",
        "reminder": "integer - reminder minutes before event"
    }
    
    def __init__(self):
        self.db = DatabaseTool()
        # Initialize calendar table
        asyncio.create_task(self._init_table())
    
    async def _init_table(self):
        try:
            await self.db.execute(
                action="create",
                sql="""CREATE TABLE IF NOT EXISTS calendar_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    event_date TEXT,
                    event_time TEXT,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reminder_minutes INTEGER DEFAULT 0
                )"""
            )
        except:
            pass
    
    async def execute(self, action: str, title: str = None, date: str = None,
                     time: str = None, description: str = None, reminder: int = 0) -> Dict[str, Any]:
        try:
            if action == "add":
                if not title or not date:
                    return {"error": "Title and date required", "success": False}
                
                result = await self.db.execute(
                    action="insert",
                    sql="calendar_events",
                    data={
                        "title": title,
                        "event_date": date,
                        "event_time": time or "",
                        "description": description or "",
                        "reminder_minutes": reminder
                    }
                )
                return {
                    "success": True,
                    "message": f"Event '{title}' added for {date}",
                    "event_id": result.get("inserted_id")
                }
            
            elif action == "list":
                today = datetime.now().strftime("%Y-%m-%d")
                sql = f"SELECT * FROM calendar_events WHERE event_date >= '{today}' ORDER BY event_date, event_time LIMIT 20"
                result = await self.db.execute(action="query", sql=sql)
                events = result.get("results", [])
                
                formatted = []
                for e in events:
                    formatted.append(f"{e['event_date']} {e['event_time']}: {e['title']}")
                
                return {
                    "success": True,
                    "events": events,
                    "formatted": "\n".join(formatted) if formatted else "No upcoming events"
                }
            
            elif action == "delete":
                if not title:
                    return {"error": "Event title required for deletion", "success": False}
                sql = f"DELETE FROM calendar_events WHERE title LIKE '%{title}%'"
                result = await self.db.execute(action="delete", sql=sql)
                return {
                    "success": True,
                    "deleted": result.get("affected_rows", 0)
                }
            
            else:
                return {"error": f"Unknown action: {action}", "success": False}
                
        except Exception as e:
            return {"error": str(e), "success": False}

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self._register_defaults()
    
    def _register_defaults(self):
        self.register(SecureBashTool())
        self.register(SecureFileTool())
        self.register(RestrictedPythonTool())
        self.register(BrowserTool())
        self.register(GitHubTool())
        self.register(HTTPTool())
        self.register(DatabaseTool())
        self.register(EmailTool())
        self.register(CalendarTool())
    
    def register(self, tool: BaseTool):
        self.tools[tool.name] = tool
        logger.info(f"Registered secure tool: {tool.name}")
    
    async def execute(self, name: str, parameters: Dict[str, Any]) -> Any:
        if name not in self.tools:
            raise ValueError(f"Unknown tool: {name}")
        return await self.tools[name].execute(**parameters)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            }
            for tool in self.tools.values()
        ]
    
    def get_tools_description(self) -> str:
        return "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools.values()])