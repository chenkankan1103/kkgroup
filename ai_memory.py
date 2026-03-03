"""
AI 記憶系統 - 全局共享的對話/角色/知識記憶庫
支持對話歷史、角色記憶、知識儲存
自動 Token 預算管理
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from logger import print

# ==================== 配置 ====================
# 使用絕對路徑確保所有執行上下文都指向同一個資料庫
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MEMORY_DB_PATH = os.path.join(DATA_DIR, "ai_memory.db")
MAX_TOKENS_FOR_CONTEXT = 1500  # 為上下文預留 token 預算
MEMORY_RETENTION_DAYS = 7  # 記憶保留 7 天

# ==================== 工具函數 ====================
def estimate_tokens(text: str) -> int:
    """粗估 token 數量（1 個字 ≈ 1.3 tokens）"""
    return int(len(text) * 1.3)

def ensure_db_exists():
    """確保數據庫和表已創建"""
    # 這裡使用 DATA_DIR 以對應絕對的資料夾路徑
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # 顯示當前使用的資料庫路徑，便於除錯
    print(f"🔍 使用 AI 記憶資料庫: {MEMORY_DB_PATH}")
    
    conn = sqlite3.connect(MEMORY_DB_PATH)
    cursor = conn.cursor()
    
    # 對話記憶表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dialogue_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_query TEXT NOT NULL,
            ai_response TEXT NOT NULL,
            token_count INTEGER,
            importance REAL DEFAULT 0.5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            accessed_count INTEGER DEFAULT 0
        )
    """)
    
    # 角色記憶表（系統設定）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS personality_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            token_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 知識庫表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER,
            category TEXT DEFAULT 'general',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            accessed_count INTEGER DEFAULT 0
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ AI 記憶數據庫已初始化")


# ==================== 對話記憶管理 ====================
class DialogueMemory:
    """對話記憶管理模組"""
    
    @staticmethod
    def add_dialogue(user_query: str, ai_response: str, importance: float = 0.5):
        """添加對話到記憶庫"""
        try:
            ensure_db_exists()
            
            user_tokens = estimate_tokens(user_query)
            response_tokens = estimate_tokens(ai_response)
            total_tokens = user_tokens + response_tokens
            
            conn = sqlite3.connect(MEMORY_DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO dialogue_memory (user_query, ai_response, token_count, importance)
                VALUES (?, ?, ?, ?)
            """, (user_query, ai_response, total_tokens, importance))
            
            conn.commit()
            conn.close()
            
            print(f"💭 記憶已存儲: {user_query[:30]}... ({total_tokens} tokens)")
        except Exception as e:
            print(f"❌ 添加記憶失敗: {e}")
    
    @staticmethod
    def get_recent_dialogue(max_tokens: int = MAX_TOKENS_FOR_CONTEXT) -> str:
        """獲取最近的對話記憶（不超過 token 預算）"""
        try:
            ensure_db_exists()
            
            conn = sqlite3.connect(MEMORY_DB_PATH)
            cursor = conn.cursor()
            
            # 按重要程度和訪問次數排序，獲取最相關的對話
            cursor.execute("""
                SELECT user_query, ai_response, token_count 
                FROM dialogue_memory
                ORDER BY importance DESC, accessed_count DESC, created_at DESC
                LIMIT 50
            """)
            
            results = cursor.fetchall()
            conn.close()
            
            # 組合對話，不超過 token 預算
            context = []
            total_tokens = 0
            
            for query, response, tokens in results:
                if total_tokens + tokens > max_tokens:
                    break
                context.append(f"用戶: {query}\nAI: {response}")
                total_tokens += tokens
            
            return "\n\n---\n\n".join(context) if context else ""
        except Exception as e:
            print(f"❌ 無法檢索記憶: {e}")
            return ""
    
    @staticmethod
    def cleanup_old_dialogue():
        """清理過期的對話記憶"""
        try:
            ensure_db_exists()
            cutoff_date = datetime.now() - timedelta(days=MEMORY_RETENTION_DAYS)
            
            conn = sqlite3.connect(MEMORY_DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM dialogue_memory
                WHERE created_at < ? AND importance < 0.7
            """, (cutoff_date,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                print(f"🧹 已清理 {deleted_count} 條過期對話記憶")
        except Exception as e:
            print(f"❌ 清理失敗: {e}")


# ==================== 角色記憶管理 ====================
class PersonalityMemory:
    """角色/性格記憶管理"""
    
    @staticmethod
    def set_personality(key: str, value: str):
        """設定角色特性"""
        try:
            ensure_db_exists()
            
            token_count = estimate_tokens(value)
            
            conn = sqlite3.connect(MEMORY_DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO personality_memory (key, value, token_count)
                VALUES (?, ?, ?)
            """, (key, value, token_count))
            
            conn.commit()
            conn.close()
            
            print(f"👤 角色特性已設定: {key}")
        except Exception as e:
            print(f"❌ 設定角色失敗: {e}")
    
    @staticmethod
    def get_personality_context() -> str:
        """獲取所有角色設定作為系統提示詞"""
        try:
            ensure_db_exists()
            
            conn = sqlite3.connect(MEMORY_DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT key, value FROM personality_memory
                ORDER BY updated_at DESC
            """)
            
            results = cursor.fetchall()
            conn.close()
            
            if not results:
                return ""
            
            context_parts = []
            for key, value in results:
                context_parts.append(f"{key}: {value}")
            
            return "\n".join(context_parts)
        except Exception as e:
            print(f"❌ 無法獲取角色設定: {e}")
            return ""
    
    @staticmethod
    def list_personality() -> List[Tuple[str, str]]:
        """列出所有角色特性"""
        try:
            ensure_db_exists()
            
            conn = sqlite3.connect(MEMORY_DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("SELECT key, value FROM personality_memory")
            results = cursor.fetchall()
            conn.close()
            
            return results
        except Exception as e:
            print(f"❌ 列表失敗: {e}")
            return []


# ==================== 知識庫管理 ====================
class KnowledgeBase:
    """知識庫管理"""
    
    @staticmethod
    def add_knowledge(topic: str, content: str, category: str = "general"):
        """添加知識到庫"""
        try:
            ensure_db_exists()
            
            token_count = estimate_tokens(content)
            
            conn = sqlite3.connect(MEMORY_DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO knowledge_base (topic, content, token_count, category)
                VALUES (?, ?, ?, ?)
            """, (topic, content, token_count, category))
            
            conn.commit()
            conn.close()
            
            print(f"📚 知識已添加: {topic} ({token_count} tokens)")
        except Exception as e:
            print(f"❌ 添加知識失敗: {e}")
    
    @staticmethod
    def search_knowledge(keyword: str, max_tokens: int = 1000) -> str:
        """搜索知識庫"""
        try:
            ensure_db_exists()
            
            conn = sqlite3.connect(MEMORY_DB_PATH)
            cursor = conn.cursor()
            
            # 搜索相關知識
            cursor.execute("""
                SELECT topic, content, token_count FROM knowledge_base
                WHERE topic LIKE ? OR content LIKE ?
                ORDER BY accessed_count DESC
                LIMIT 20
            """, (f"%{keyword}%", f"%{keyword}%"))
            
            results = cursor.fetchall()
            
            # 更新訪問計數
            cursor.execute("""
                UPDATE knowledge_base 
                SET accessed_count = accessed_count + 1
                WHERE topic LIKE ? OR content LIKE ?
            """, (f"%{keyword}%", f"%{keyword}%"))
            
            conn.commit()
            conn.close()
            
            # 組合結果
            context = []
            total_tokens = 0
            
            for topic, content, tokens in results:
                if total_tokens + tokens > max_tokens:
                    break
                context.append(f"【{topic}】\n{content}")
                total_tokens += tokens
            
            return "\n\n".join(context) if context else ""
        except Exception as e:
            print(f"❌ 搜索失敗: {e}")
            return ""
    
    @staticmethod
    def get_all_knowledge(max_tokens: int = 2000) -> str:
        """獲取所有知識庫內容"""
        try:
            ensure_db_exists()
            
            conn = sqlite3.connect(MEMORY_DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT topic, content, token_count FROM knowledge_base
                ORDER BY category, accessed_count DESC
            """)
            
            results = cursor.fetchall()
            conn.close()
            
            # 組合知識
            context = []
            total_tokens = 0
            
            for topic, content, tokens in results:
                if total_tokens + tokens > max_tokens:
                    break
                context.append(f"【{topic}】\n{content}")
                total_tokens += tokens
            
            return "\n\n".join(context) if context else ""
        except Exception as e:
            print(f"❌ 獲取知識失敗: {e}")
            return ""


# ==================== 統一的記憶上下文構建 ====================
def build_memory_context() -> Dict[str, str]:
    """構建完整的記憶上下文
    
    返回字典包含：
    - system_instructions: 系統指令 + 角色設定
    - dialogue_history: 對話歷史
    - knowledge_context: 知識庫背景
    """
    try:
        # 獲取角色記憶（系統設定）
        personality = PersonalityMemory.get_personality_context()
        
        # 獲取對話歷史
        dialogue = DialogueMemory.get_recent_dialogue(max_tokens=1000)
        
        # 獲取知識庫
        knowledge = KnowledgeBase.get_all_knowledge(max_tokens=800)
        
        system_instructions = ""
        if personality:
            system_instructions = f"=== AI 角色設定 ===\n{personality}\n\n"
        else:
            system_instructions = "=== AI 設定 ===\n你是一個有幫助的助手。\n\n"
        
        return {
            "system_instructions": system_instructions,
            "dialogue_history": dialogue,
            "knowledge_context": knowledge,
            "estimated_tokens": (
                estimate_tokens(system_instructions) +
                estimate_tokens(dialogue) +
                estimate_tokens(knowledge)
            )
        }
    except Exception as e:
        print(f"❌ 構建記憶上下文失敗: {e}")
        return {
            "system_instructions": "你是一個有幫助的助手。",
            "dialogue_history": "",
            "knowledge_context": "",
            "estimated_tokens": 0
        }


# ==================== 初始化 ====================
def initialize_memory_system():
    """初始化記憶系統"""
    try:
        ensure_db_exists()
        
        # 清理過期記憶
        DialogueMemory.cleanup_old_dialogue()
        
        print("✅ AI 記憶系統已初始化")
    except Exception as e:
        print(f"❌ 記憶系統初始化失敗: {e}")


if __name__ == "__main__":
    # 測試
    initialize_memory_system()
    
    # 設定角色
    PersonalityMemory.set_personality("角色", "你是一個有創意和熱情的助手，喜歡用隱喻和類比解釋複雜概念。")
    PersonalityMemory.set_personality("語氣", "友好、專業、略帶幽默")
    
    # 添加知識
    KnowledgeBase.add_knowledge("KK園區介紹", "這是一個虛擬遊戲園區，有各種小遊戲和互動機制。", "系統")
    
    # 測試對話
    DialogueMemory.add_dialogue(
        "KK園區是什麼？",
        "KK園區是一個虛擬遊戲平台，提供多種遊戲和社交互動體驗。",
        importance=0.8
    )
    
    # 獲取上下文
    context = build_memory_context()
    print("\n=== 完整記憶上下文 ===")
    print(context["system_instructions"])
    print(f"估計 tokens: {context['estimated_tokens']}")
