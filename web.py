from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
import os
import json
from datetime import datetime
from bulk_edit_template import create_bulk_edit_template

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

ADMIN_USERNAME = 'kkgroup'
ADMIN_PASSWORD = 'kkgroup'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'user_data.db')

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
            except:
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
        changes = data.get('changes', [])
        primary_key = get_primary_key(table_name)
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': '資料庫連接失敗'})
        
        for change in changes:
            if change['action'] == 'update':
                set_clause = ', '.join([f"{field} = ?" for field in change['fields'].keys()])
                values = list(change['fields'].values()) + [change['id']]
                conn.execute(f'UPDATE {table_name} SET {set_clause} WHERE {primary_key} = ?', values)
            
            elif change['action'] == 'insert':
                fields = ', '.join(change['fields'].keys())
                placeholders = ', '.join(['?' for _ in change['fields']])
                values = list(change['fields'].values())
                conn.execute(f'INSERT INTO {table_name} ({fields}) VALUES ({placeholders})', values)
            
            elif change['action'] == 'delete':
                conn.execute(f'DELETE FROM {table_name} WHERE {primary_key} = ?', (change['id'],))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': f'成功保存 {len(changes)} 項變更'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

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

def create_all_templates():
    create_bulk_edit_template()
    print("所有模板已生成")

if __name__ == '__main__':
    create_all_templates()
    app.run(debug=True, host='0.0.0.0', port=20039)