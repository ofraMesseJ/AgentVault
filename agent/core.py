# agent/core.py - COMPLETE VERSION with ALL TOOLS (Database, Email, Calendar)
import json
import logging
import os
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
import aiohttp

from tools.registry import ToolRegistry
from memory.chroma_store import ChromaMemoryStore

logger = logging.getLogger(__name__)

class AgentRuntime:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.history: List[Dict[str, Any]] = []
        self.tool_registry = ToolRegistry()
        self.memory = ChromaMemoryStore()
        self.ollama_url = "http://localhost:11434/api/chat"
        self.model = "qwen2.5:7b"
        logger.info(f"Agent {session_id} initialized (Ollama mode)")
    
    async def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        user_content = message.get("content", "")
        self.history.append({
            "role": "user",
            "content": user_content,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Check if this is a direct tool command (bypass AI for tool execution)
        tool_plan = await self._detect_tool_use(user_content)
        
        if tool_plan:
            # Execute tool directly
            logger.info(f"Executing tool: {tool_plan}")
            tool_result = await self.tool_registry.execute(tool_plan["tool"], tool_plan["params"])
            
            # Format response based on tool result
            if tool_result.get("success"):
                response_text = self._format_tool_success(tool_plan["tool"], tool_result)
            else:
                response_text = f"Tool execution failed: {tool_result.get('error', 'Unknown error')}"
            
            await self.memory.add(text=user_content, metadata={"tool_used": tool_plan["tool"], "success": str(tool_result.get("success", False))})
            
            self.history.append({
                "role": "assistant",
                "content": response_text,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return {
                "content": response_text,
                "tool_calls": tool_plan,
                "session_id": self.session_id
            }
        
        # No tool detected, use AI for normal chat
        memories = await self.memory.search(user_content, k=3)
        context = self._build_context(memories)
        
        response_text = await self._query_ollama(user_content, context)
        
        await self.memory.add(text=user_content, metadata={"response": response_text})
        
        self.history.append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "content": response_text,
            "tool_calls": None,
            "session_id": self.session_id
        }
    
    async def _detect_tool_use(self, message: str) -> Optional[Dict]:
        """Enhanced tool detection with ALL tools (database, email, calendar, etc.)"""
        msg_lower = message.lower().strip()
        
        # Screenshot patterns (check FIRST - before general browse)
        if any(kw in msg_lower for kw in ["screenshot", "capture", "snapshot"]):
            url_match = re.search(r'https?://[^\s]+', message)
            url = url_match.group(0) if url_match else "https://example.com"
            return {"tool": "browser", "params": {"url": url, "action": "screenshot"}}
        
        # Browser patterns
        if any(kw in msg_lower for kw in ["browse to", "visit", "go to", "open url", "navigate to"]):
            url_match = re.search(r'https?://[^\s]+', message)
            url = url_match.group(0) if url_match else "https://example.com"
            
            if "extract" in msg_lower or "get text" in msg_lower or "headlines" in msg_lower:
                return {"tool": "browser", "params": {"url": url, "action": "extract"}}
            else:
                return {"tool": "browser", "params": {"url": url, "action": "navigate"}}
        
        # HTTP/API patterns
        if any(kw in msg_lower for kw in ["make get request", "http get", "api call", "fetch url", "curl"]):
            url_match = re.search(r'https?://[^\s]+', message)
            if url_match:
                return {"tool": "http", "params": {"url": url_match.group(0), "method": "GET"}}
        
        if any(kw in msg_lower for kw in ["make post request", "http post", "send post"]):
            url_match = re.search(r'https?://[^\s]+', message)
            if url_match:
                return {"tool": "http", "params": {"url": url_match.group(0), "method": "POST"}}
        
        # GitHub patterns
        if any(kw in msg_lower for kw in ["get info for repo", "github repo", "repo info", "repository"]):
            repo_match = re.search(r'([\w-]+/[\w-]+)', message)
            if repo_match:
                repo = repo_match.group(1)
                if "issue" in msg_lower:
                    return {"tool": "github", "params": {"action": "list_issues", "repo": repo}}
                elif "readme" in msg_lower:
                    return {"tool": "github", "params": {"action": "get_readme", "repo": repo}}
                else:
                    return {"tool": "github", "params": {"action": "get_repo", "repo": repo}}
        
        # Database patterns
        if any(kw in msg_lower for kw in ["query database", "db query", "sql query", "run query"]):
            # Extract SQL after "query"
            sql_match = re.search(r'query\s+(.+)', message, re.IGNORECASE | re.DOTALL)
            if sql_match:
                sql = sql_match.group(1).strip()
                return {"tool": "database", "params": {"action": "query", "sql": sql}}
        
        if any(kw in msg_lower for kw in ["insert into", "add to database", "db insert"]):
            return {"tool": "database", "params": {"action": "insert", "sql": message}}
        
        # Email patterns
        if any(kw in msg_lower for kw in ["send email", "send mail", "email to"]):
            # Try to extract recipient
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', message)
            to = email_match.group(0) if email_match else None
            
            # Extract subject after "about" or "subject"
            subject = "No Subject"
            if "about" in msg_lower:
                subject = message.split("about", 1)[-1].split(".")[0].strip()
            elif "subject" in msg_lower:
                subject = message.split("subject", 1)[-1].split(".")[0].strip()
            
            return {"tool": "email", "params": {"action": "send", "to": to, "subject": subject, "body": message}}
        
        if any(kw in msg_lower for kw in ["read email", "check email", "get emails"]):
            return {"tool": "email", "params": {"action": "read"}}
        
        # Calendar patterns
        if any(kw in msg_lower for kw in ["add event", "create event", "schedule"]):
            # Extract date (YYYY-MM-DD format or "today", "tomorrow")
            date_match = re.search(r'\d{4}-\d{2}-\d{2}', message)
            date = date_match.group(0) if date_match else None
            
            # Extract time
            time_match = re.search(r'\d{1,2}:\d{2}', message)
            time = time_match.group(0) if time_match else None
            
            # Title is everything else
            title = message
            for remove in ["add event", "create event", "schedule", "on", "at", date or "", time or ""]:
                title = title.replace(remove, "")
            title = title.strip(" ,.:;")
            
            return {"tool": "calendar", "params": {"action": "add", "title": title or "New Event", "date": date, "time": time}}
        
        if any(kw in msg_lower for kw in ["list events", "show calendar", "my events", "upcoming"]):
            return {"tool": "calendar", "params": {"action": "list"}}
        
        # Bash patterns
        if any(kw in msg_lower for kw in ["bash", "shell", "command", "run", "terminal", "execute"]):
            cmd = message
            for kw in ["run bash command:", "run command:", "execute:", "bash:", "shell:"]:
                if kw in message.lower():
                    cmd = message.split(kw, 1)[-1].strip()
                    break
            
            # Clean up the command
            cmd = cmd.strip('`"\'')
            if cmd and cmd != message:
                return {"tool": "bash", "params": {"command": cmd}}
        
        # File patterns
        if any(kw in msg_lower for kw in ["read file", "open file", "cat file", "show file"]):
            filename = msg_lower.replace("read file", "").replace("open file", "").replace("cat file", "").replace("show file", "").strip()
            filename = filename.split()[0] if filename else "test.txt"
            return {"tool": "file", "params": {"operation": "read", "path": filename}}
        
        if any(kw in msg_lower for kw in ["write file", "create file", "save file"]):
            # Try to extract filename and content
            parts = message.split("with content", 1)
            filename = parts[0].replace("write file", "").replace("create file", "").replace("save file", "").strip()
            content = parts[1].strip(' `"\'') if len(parts) > 1 else ""
            return {"tool": "file", "params": {"operation": "write", "path": filename, "content": content}}
        
        if "list files" in msg_lower or "ls" in msg_lower:
            return {"tool": "file", "params": {"operation": "list", "path": "."}}
        
        # Python patterns
        if any(kw in msg_lower for kw in ["run python", "execute python", "python code"]):
            code = message
            for kw in ["run python:", "execute python:", "python code:", "```python"]:
                if kw in message.lower():
                    code = message.split(kw, 1)[-1].strip()
                    break
            code = code.strip('`"\'')
            if code and len(code) > 5:
                return {"tool": "python", "params": {"code": code}}
        
        return None
    
    def _format_tool_success(self, tool_name: str, result: Dict) -> str:
        """Format tool output nicely (Updated for all 9 tools)"""
        if tool_name == "browser":
            # Check for screenshot first (by looking for screenshot_saved key)
            if result.get("screenshot_saved"):
                return f"📸 Screenshot saved to: {result.get('screenshot_saved')}"
            elif result.get("action") == "extract":
                content = result.get('extracted', '')
                if isinstance(content, list):
                    return "📄 Extracted content:\n" + "\n".join([f"- {c[:200]}" for c in content[:5]])
                else:
                    return f"📄 Extracted content:\n{content[:1000]}..."
            else:
                return f"🌐 Page: {result.get('title', 'Unknown')}\n\n{result.get('content_preview', '')[:800]}..."
        
        elif tool_name == "http":
            status = result.get('status', 0)
            if result.get('json'):
                return f"📡 HTTP {status}\n```json\n{json.dumps(result['json'], indent=2)[:1000]}\n```"
            else:
                return f"📡 HTTP {status}\n{result.get('text', 'No content')[:1000]}..."
        
        elif tool_name == "github":
            if result.get("action") == "get_repo":
                return f"⭐ **{result.get('name')}**\n{result.get('description', 'No description')}\n🔗 {result.get('url')}\n⭐ Stars: {result.get('stars', 0)}"
            elif result.get("issues"):
                issues_text = "\n".join([f"#{i['number']}: {i['title']}" for i in result["issues"][:5]])
                return f"🐛 Issues for {result.get('repo', 'repo')}:\n{issues_text}"
            elif result.get("readme"):
                return f"📖 README:\n{result['readme'][:1500]}..."
            else:
                return json.dumps(result, indent=2)
        
        elif tool_name == "bash":
            stdout = result.get('stdout', '')
            stderr = result.get('stderr', '')
            output = ""
            if stdout:
                output += f"Output:\n{stdout[:1000]}"
            if stderr:
                output += f"\nErrors:\n{stderr[:500]}"
            return output or "Command executed (no output)"
        
        elif tool_name == "file":
            if result.get("content"):
                return f"📄 File content:\n{result['content'][:1500]}..."
            elif result.get("files"):
                return "📁 Files:\n" + "\n".join(result["files"][:20])
            elif result.get("success"):
                return "✅ File operation successful"
            else:
                return json.dumps(result, indent=2)
        
        elif tool_name == "python":
            output = result.get('output', '')
            return f"🐍 Python output:\n{output[:1500]}" if output else "Code executed (no output)"
        
        # NEW TOOLS FORMATTING
        elif tool_name == "database":
            if result.get("results"):
                rows = result["results"]
                if len(rows) == 0:
                    return "📊 Query returned 0 rows"
                # Format as table
                headers = list(rows[0].keys())
                lines = [" | ".join(headers), "-" * 40]
                for row in rows[:10]:  # Limit to 10 rows
                    lines.append(" | ".join([str(row.get(h, ""))[:20] for h in headers]))
                if len(rows) > 10:
                    lines.append(f"... and {len(rows) - 10} more rows")
                return "📊 Database Results:\n" + "\n".join(lines)
            elif result.get("inserted_id"):
                return f"✅ Inserted row with ID: {result['inserted_id']}"
            elif result.get("affected_rows") is not None:
                return f"✅ Affected rows: {result['affected_rows']}"
            else:
                return f"✅ Database operation successful: {result.get('message', '')}"
        
        elif tool_name == "email":
            if result.get("emails"):
                emails = result["emails"]
                lines = [f"📧 Email {i+1}: From: {e.get('from', 'Unknown')}" for i, e in enumerate(emails[:5])]
                lines.append(f"\nSubject: {emails[0].get('subject', 'No subject')}" if emails else "")
                return "📧 Recent Emails:\n" + "\n".join(lines)
            else:
                return f"📧 Email: {result.get('message', 'Operation completed')}"
        
        elif tool_name == "calendar":
            if result.get("formatted"):
                return f"📅 Calendar Events:\n{result['formatted']}"
            elif result.get("event_id"):
                return f"📅 Event added (ID: {result['event_id']})"
            else:
                return f"📅 Calendar: {result.get('message', 'Operation completed')}"
        
        return json.dumps(result, indent=2)[:1000]
    
    async def _query_ollama(self, user_msg: str, context: str) -> str:
        """Query Ollama API"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": f"You are AgentVault AI, a helpful assistant with access to tools. Context: {context}"},
                        {"role": "user", "content": user_msg}
                    ],
                    "stream": False,
                    "options": {"temperature": 0.7}
                }
                async with session.post(self.ollama_url, json=payload) as resp:
                    data = await resp.json()
                    return data["message"]["content"]
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return f"[Error connecting to Ollama: {e}. Is Ollama running?]"
    
    def _build_context(self, memories: List[Dict]) -> str:
        if not memories:
            return ""
        return "Previous info:\n" + "\n".join([f"- {m['text']}" for m in memories])
    
    def get_history(self) -> List[Dict[str, Any]]:
        return self.history