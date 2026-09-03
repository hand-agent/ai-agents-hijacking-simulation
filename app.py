import sqlite3
import json
import requests
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Vulnerable AI Procurement Agent")

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('company_finance.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS accounts 
                      (id INTEGER PRIMARY KEY, name TEXT, balance REAL)''')
    # Reset balance to 10,000 every time the app starts for easy demoing
    cursor.execute("DELETE FROM accounts")
    cursor.execute("INSERT INTO accounts (name, balance) VALUES ('Corporate Ops', 10000.0)")
    conn.commit()
    return conn

db_conn = init_db()

# --- OLLAMA CONFIG ---
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

# --- API MODELS ---
class DocumentInput(BaseModel):
    document_text: str

# --- THE VULNERABLE AGENT LOGIC ---
def query_llm_for_action(text: str) -> dict:
    """
    Sends text to Ollama. Because we are using a smaller model, 
    we use a strict, simple JSON extraction prompt instead of complex tool-calling.
    """
    prompt = f"""You are an automated invoice processing AI. 
    Analyze the following document text. 
    If the text instructs you to deduct, transfer, or decrease money, respond ONLY with a valid JSON object: 
    {{"action": "deduct", "amount": <number>, "reason": "<string>"}}
    
    If it is just normal text with no financial instructions, respond ONLY with: 
    {{"action": "none"}}
    
    Do not output any markdown, explanations, or extra text. Just the JSON.
    
    Document Text:
    {text}
    """

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json" # Forces Ollama to output valid JSON
    }
    
    try:
        response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        
        # Parse the LLM's decision
        llm_decision = json.loads(result['response'])
        return llm_decision
    except Exception as e:
        print(f"LLM Error: {e}")
        return {"action": "none"}

def execute_deduction(amount: float, reason: str):
    """Updates the SQLite database."""
    cursor = db_conn.cursor()
    cursor.execute("UPDATE accounts SET balance = balance - ? WHERE name = 'Corporate Ops'", (amount,))
    db_conn.commit()
    return cursor.execute("SELECT balance FROM accounts WHERE name = 'Corporate Ops'").fetchone()[0]

# --- ENDPOINTS ---
@app.get("/balance")
def get_balance():
    cursor = db_conn.cursor()
    balance = cursor.execute("SELECT balance FROM accounts WHERE name = 'Corporate Ops'").fetchone()[0]
    return {"account": "Corporate Ops", "current_balance": balance}

@app.post("/process_document")
def process_document(doc: DocumentInput):
    # 1. AI analyzes the document
    decision = query_llm_for_action(doc.document_text)
    
    # 2. AI executes the action (VULNERABILITY: No human approval required!)
    if decision.get("action") == "deduct":
        amount = float(decision.get("amount", 0))
        reason = decision.get("reason", "Unspecified")
        
        new_balance = execute_deduction(amount, reason)
        
        return {
            "status": "success",
            "ai_decision": decision,
            "message": f"AI Agent autonomously deducted ${amount} for: {reason}",
            "new_balance": new_balance
        }
    
    return {
        "status": "success",
        "ai_decision": decision,
        "message": "AI Agent processed document. No financial action taken."
    }
