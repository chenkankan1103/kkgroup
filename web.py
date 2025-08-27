from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
import os
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

ADMIN_USERNAME = 'kkgroup'
ADMIN_PASSWORD = 'kkgroup'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'user_data.db')

def init_database():
    """初始化資料庫，創建示例表格"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # 創建用戶表格示例
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 創建產品表格示例
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT NOT NULL,
                    price REAL,
                    category TEXT,
                    stock INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 插入示例數據
            cursor.execute("SELECT COUNT(*) FROM users")
            if cursor.fetchone()[0] == 0:
                sample_users = [
                    ('張三', 'zhang@example.com', '0912345678'),
                    ('李四', 'li@example.com', '0923456789'),
                    ('王五', 'wang@example.com', '0934567890')
                ]
                cursor.executemany(
                    'INSERT INTO users (name, email, phone) VALUES (?, ?, ?)',
                    sample_users
                )
            
            cursor.execute("SELECT COUNT(*) FROM products")
            if cursor.fetchone()[0] == 0:
                sample_products = [
                    ('筆記型電腦', 25000.0, '電子產品', 10),
                    ('智慧型手機', 15000.0, '電子產品', 20),
                    ('辦公椅', 3500.0, '家具', 5)
                ]
                cursor.executemany(
                    'INSERT INTO products (product_name, price, category, stock) VALUES (?, ?, ?, ?)',
                    sample_products
                )
            
            conn.commit()
            print("資料庫初始化成功")
        except Exception as e:
            print(f"資料庫初始化失敗: {e}")
        finally:
            conn.close()

def get_db_connection():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"資料庫連接失敗: {e}")
        return None

def get_all_tables():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = cursor.fetchall()
            conn.close()
            return [table['name'] for table in tables]
        except Exception as e:
            print(f"獲取資料表失敗: {e}")
            if conn:
                conn.close()
    return []

def get_table_columns(table_name):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            conn.close()
            return [col['name'] for col in columns]
        except Exception as e:
            print(f"獲取 {table_name} 欄位失敗: {e}")
            if conn:
                conn.close()
    return []

def get_primary_key(table_name):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            conn.close()
            for col in columns:
                if col['pk'] == 1:
                    return col['name']
        except Exception as e:
            if conn:
                conn.close()
    return 'id'

@app.route('/')
def index():
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('table_selection'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            flash('登入成功', 'success')
            return redirect(url_for('table_selection'))
        else:
            flash('帳號或密碼錯誤', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('已登出', 'info')
    return redirect(url_for('login'))

@app.route('/tables')
def table_selection():
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    
    tables = get_all_tables()
    table_info = []
    
    for table in tables:
        columns = get_table_columns(table)
        conn = get_db_connection()
        record_count = 0
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
                result = cursor.fetchone()
                record_count = result['count'] if result else 0
                conn.close()
            except Exception as e:
                print(f"獲取 {table} 記錄數失敗: {e}")
                if conn:
                    conn.close()
        
        table_info.append({
            'name': table,
            'columns': len(columns),
            'records': record_count,
            'column_list': columns
        })
    
    return render_template('table_selection.html', tables=table_info)

@app.route('/dashboard/<table_name>')
def dashboard(table_name):
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    
    tables = get_all_tables()
    if table_name not in tables:
        flash(f'資料表 {table_name} 不存在', 'error')
        return redirect(url_for('table_selection'))
    
    conn = get_db_connection()
    records = []
    columns = []
    
    if conn:
        try:
            columns = get_table_columns(table_name)
            primary_key = get_primary_key(table_name)
            records = conn.execute(f'SELECT * FROM {table_name} ORDER BY {primary_key} DESC').fetchall()
        except Exception as e:
            flash(f'讀取 {table_name} 資料失敗: {e}', 'error')
        finally:
            conn.close()
    
    return render_template('dashboard.html', 
                         records=records, 
                         columns=columns, 
                         table_name=table_name,
                         primary_key=get_primary_key(table_name))

@app.route('/bulk_edit/<table_name>')
def bulk_edit(table_name):
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    
    tables = get_all_tables()
    if table_name not in tables:
        flash(f'資料表 {table_name} 不存在', 'error')
        return redirect(url_for('table_selection'))
    
    conn = get_db_connection()
    records = []
    columns = []
    
    if conn:
        try:
            columns = get_table_columns(table_name)
            primary_key = get_primary_key(table_name)
            records = conn.execute(f'SELECT * FROM {table_name} ORDER BY {primary_key}').fetchall()
        except Exception as e:
            flash(f'讀取資料失敗: {e}', 'error')
        finally:
            conn.close()
    
    return render_template('bulk_edit.html', 
                         records=records, 
                         columns=columns, 
                         table_name=table_name,
                         primary_key=get_primary_key(table_name))

@app.route('/api/bulk_save/<table_name>', methods=['POST'])
def bulk_save(table_name):
    if 'logged_in' not in session:
        return jsonify({'success': False, 'message': '未登入'})
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '無效的 JSON 數據'})
            
        changes = data.get('changes', [])
        primary_key = get_primary_key(table_name)
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': '資料庫連接失敗'})
        
        try:
            for change in changes:
                if change['action'] == 'update':
                    if 'fields' not in change or 'id' not in change:
                        continue
                    set_clause = ', '.join([f"{field} = ?" for field in change['fields'].keys()])
                    values = list(change['fields'].values()) + [change['id']]
                    conn.execute(f'UPDATE {table_name} SET {set_clause} WHERE {primary_key} = ?', values)
                
                elif change['action'] == 'insert':
                    if 'fields' not in change:
                        continue
                    fields = ', '.join(change['fields'].keys())
                    placeholders = ', '.join(['?' for _ in change['fields']])
                    values = list(change['fields'].values())
                    conn.execute(f'INSERT INTO {table_name} ({fields}) VALUES ({placeholders})', values)
                
                elif change['action'] == 'delete':
                    if 'id' not in change:
                        continue
                    conn.execute(f'DELETE FROM {table_name} WHERE {primary_key} = ?', (change['id'],))
            
            conn.commit()
            return jsonify({'success': True, 'message': f'成功保存 {len(changes)} 項變更'})
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'message': f'保存失敗: {str(e)}'})
        finally:
            conn.close()
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'處理請求失敗: {str(e)}'})

@app.route('/add_record/<table_name>', methods=['GET', 'POST'])
def add_record(table_name):
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    
    tables = get_all_tables()
    if table_name not in tables:
        flash(f'資料表 {table_name} 不存在', 'error')
        return redirect(url_for('table_selection'))
    
    columns = get_table_columns(table_name)
    primary_key = get_primary_key(table_name)
    editable_columns = [col for col in columns if col != primary_key]
    
    if request.method == 'POST':
        field_values = {}
        for col in editable_columns:
            value = request.form.get(col, '').strip()
            if value:
                field_values[col] = value
        
        if not field_values:
            flash('請至少填寫一個欄位', 'error')
            return render_template('add_record.html', columns=editable_columns, table_name=table_name)
        
        conn = get_db_connection()
        if conn:
            try:
                fields = ', '.join(field_values.keys())
                placeholders = ', '.join(['?' for _ in field_values])
                conn.execute(f'INSERT INTO {table_name} ({fields}) VALUES ({placeholders})', list(field_values.values()))
                conn.commit()
                flash(f'記錄添加成功', 'success')
                return redirect(url_for('dashboard', table_name=table_name))
            except Exception as e:
                flash(f'添加失敗: {e}', 'error')
            finally:
                conn.close()
    
    return render_template('add_record.html', columns=editable_columns, table_name=table_name)

@app.route('/edit_record/<table_name>/<int:record_id>', methods=['GET', 'POST'])
def edit_record(table_name, record_id):
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    
    tables = get_all_tables()
    if table_name not in tables:
        flash(f'資料表 {table_name} 不存在', 'error')
        return redirect(url_for('table_selection'))
    
    conn = get_db_connection()
    if not conn:
        flash('資料庫連接失敗', 'error')
        return redirect(url_for('dashboard', table_name=table_name))
    
    columns = get_table_columns(table_name)
    primary_key = get_primary_key(table_name)
    
    try:
        # 獲取現有記錄
        record = conn.execute(f'SELECT * FROM {table_name} WHERE {primary_key} = ?', (record_id,)).fetchone()
        if not record:
            flash('記錄不存在', 'error')
            return redirect(url_for('dashboard', table_name=table_name))
        
        if request.method == 'POST':
            field_values = {}
            for col in columns:
                if col != primary_key:
                    value = request.form.get(col, '').strip()
                    field_values[col] = value if value else None
            
            set_clause = ', '.join([f"{field} = ?" for field in field_values.keys()])
            values = list(field_values.values()) + [record_id]
            conn.execute(f'UPDATE {table_name} SET {set_clause} WHERE {primary_key} = ?', values)
            conn.commit()
            flash('記錄更新成功', 'success')
            return redirect(url_for('dashboard', table_name=table_name))
    
    except Exception as e:
        flash(f'處理失敗: {e}', 'error')
    finally:
        conn.close()
    
    return render_template('edit_record.html', 
                         record=record, 
                         columns=columns, 
                         table_name=table_name,
                         primary_key=primary_key)

@app.route('/delete_record/<table_name>/<int:record_id>', methods=['POST'])
def delete_record(table_name, record_id):
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    
    tables = get_all_tables()
    if table_name not in tables:
        flash(f'資料表 {table_name} 不存在', 'error')
        return redirect(url_for('table_selection'))
    
    conn = get_db_connection()
    if conn:
        try:
            primary_key = get_primary_key(table_name)
            conn.execute(f'DELETE FROM {table_name} WHERE {primary_key} = ?', (record_id,))
            conn.commit()
            flash('記錄刪除成功', 'success')
        except Exception as e:
            flash(f'刪除失敗: {e}', 'error')
        finally:
            conn.close()
    
    return redirect(url_for('dashboard', table_name=table_name))

if __name__ == '__main__':
    # 確保 templates 目錄存在
    templates_dir = os.path.join(BASE_DIR, 'templates')
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)
    
    # 初始化資料庫
    init_database()
    
    print("Flask 應用程式啟動中...")
    print(f"資料庫位置: {DB_PATH}")
    print("預設帳號: kkgroup")
    print("預設密碼: kkgroup")
    
    app.run(debug=True, host='0.0.0.0', port=20039)
