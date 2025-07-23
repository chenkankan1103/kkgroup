import os

def create_management_templates():
    """創建主要管理功能的模板"""
    if not os.path.exists('templates'):
        os.makedirs('templates')

    # 表格選擇模板
    table_select_template = '''<!DOCTYPE html>
<html>
<head>
    <title>選擇表格</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial; background: #2c3e50; color: white; margin: 0; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
        .container { max-width: 800px; margin: 0 auto; }
        .btn { padding: 10px 20px; margin: 5px; text-decoration: none; border-radius: 4px; display: inline-block; font-size: 16px; }
        .btn-primary { background: #3498db; color: white; }
        .btn-danger { background: #e74c3c; color: white; }
        .btn:hover { opacity: 0.8; }
        .table-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; margin-top: 20px; }
        .table-card { background: #34495e; padding: 20px; border-radius: 8px; text-align: center; border: 2px solid transparent; transition: all 0.3s; }
        .table-card:hover { border-color: #3498db; background: #3c5875; cursor: pointer; }
        .table-name { font-size: 18px; font-weight: bold; margin-bottom: 10px; }
        .table-info { font-size: 14px; color: #bdc3c7; }
        .flash { padding: 15px; margin: 15px 0; border-radius: 4px; }
        .success { background: #27ae60; }
        .error { background: #e74c3c; }
        .info { background: #3498db; }
        .warning { background: #f39c12; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>資料庫管理系統</h1>
            <a href="{{ url_for('logout') }}" class="btn btn-danger">登出</a>
        </div>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash {{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <h2>選擇要管理的表格</h2>
        
        <div class="table-grid">
            {% for table in tables %}
            <div class="table-card" onclick="location.href='{{ url_for('dashboard', table_name=table.name) }}'">
                <div class="table-name">{{ table.name }}</div>
                <div class="table-info">
                    記錄數: {{ table.count }}<br>
                    欄位數: {{ table.columns }}
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>'''

    # 儀表板模板
    dashboard_template = '''<!DOCTYPE html>
<html>
<head>
    <title>{{ table_name }} - 管理面板</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial; background: #2c3e50; color: white; margin: 0; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .controls { margin-bottom: 20px; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
        .search-controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .btn { padding: 8px 16px; margin: 2px; text-decoration: none; border-radius: 4px; display: inline-block; border: none; cursor: pointer; font-size: 14px; }
        .btn-success { background: #27ae60; color: white; }
        .btn-danger { background: #e74c3c; color: white; }
        .btn-primary { background: #3498db; color: white; }
        .btn-back { background: #95a5a6; color: white; }
        .btn-warning { background: #f39c12; color: white; }
        .btn:hover { opacity: 0.8; }
        .search-box { padding: 8px; border: 1px solid #5a6c7d; background: #34495e; color: white; border-radius: 4px; min-width: 200px; }
        .search-box:focus { border-color: #3498db; outline: none; }
        .table-container { overflow: auto; max-height: 70vh; border: 1px solid #5a6c7d; }
        table { width: 100%; background: #34495e; border-collapse: collapse; }
        th, td { padding: 8px 12px; border: 1px solid #5a6c7d; text-align: left; }
        th { background: #2c3e50; position: sticky; top: 0; z-index: 10; font-weight: bold; }
        .actions { white-space: nowrap; }
        .flash { padding: 10px; margin: 10px 0; border-radius: 4px; }
        .success { background: #27ae60; }
        .error { background: #e74c3c; }
        .info { background: #3498db; }
        .warning { background: #f39c12; }
        .pagination { margin-top: 20px; text-align: center; }
        .pagination .btn { margin: 0 2px; }
        .pagination .current { background: #f39c12; }
        .record-count { color: #bdc3c7; font-size: 14px; }
        .column-header { cursor: pointer; user-select: none; }
        .column-header:hover { background: #34495e; }
        .sort-indicator { margin-left: 5px; font-size: 12px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ table_name }} 管理面板</h1>
        <div>
            <a href="{{ url_for('table_select') }}" class="btn btn-back">返回表格選擇</a>
            <a href="{{ url_for('logout') }}" class="btn btn-danger">登出</a>
        </div>
    </div>

    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, message in messages %}
                <div class="flash {{ category }}">{{ message }}</div>
            {% endfor %}
        {% endif %}
    {% endwith %}

    <div class="controls">
        <a href="{{ url_for('add_record', table_name=table_name) }}" class="btn btn-success">新增記錄</a>
        <a href="{{ url_for('bulk_edit', table_name=table_name) }}" class="btn btn-warning">批量編輯</a>
        
        <div class="search-controls">
            <form method="GET" style="display: flex; gap: 10px; align-items: center;">
                <input type="text" name="search" class="search-box" placeholder="搜尋..." 
                       value="{{ request.args.get('search', '') }}">
                <select name="search_column" class="search-box" style="min-width: 120px;">
                    <option value="">所有欄位</option>
                    {% for column in columns %}
                    <option value="{{ column }}" 
                            {% if request.args.get('search_column') == column %}selected{% endif %}>
                        {{ column }}
                    </option>
                    {% endfor %}
                </select>
                <button type="submit" class="btn btn-primary">搜尋</button>
                {% if request.args.get('search') %}
                <a href="{{ url_for('dashboard', table_name=table_name) }}" class="btn btn-back">清除</a>
                {% endif %}
            </form>
        </div>
    </div>

    <div class="record-count">
        總計 {{ total_records }} 筆記錄
        {% if request.args.get('search') %}
        （搜尋到 {{ records|length }} 筆）
        {% endif %}
    </div>

    <div class="table-container">
        <table>
            <thead>
                <tr>
                    {% for column in columns %}
                    <th class="column-header" onclick="sortTable('{{ column }}')">
                        {{ column }}
                        {% if request.args.get('sort') == column %}
                            {% if request.args.get('order') == 'desc' %}
                                <span class="sort-indicator">↓</span>
                            {% else %}
                                <span class="sort-indicator">↑</span>
                            {% endif %}
                        {% endif %}
                    </th>
                    {% endfor %}
                    <th class="actions">操作</th>
                </tr>
            </thead>
            <tbody>
                {% for record in records %}
                <tr>
                    {% for column in columns %}
                    <td>{{ record[column] if record[column] is not none else '' }}</td>
                    {% endfor %}
                    <td class="actions">
                        <a href="{{ url_for('edit_record', table_name=table_name, record_id=record[primary_key]) }}" 
                           class="btn btn-primary">編輯</a>
                        <a href="{{ url_for('delete_record', table_name=table_name, record_id=record[primary_key]) }}" 
                           class="btn btn-danger" 
                           onclick="return confirm('確定要刪除這筆記錄嗎？')">刪除</a>
                    </td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="{{ columns|length + 1 }}" style="text-align: center; color: #bdc3c7;">
                        {% if request.args.get('search') %}
                            沒有符合搜尋條件的記錄
                        {% else %}
                            目前沒有記錄
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <!-- 分頁功能（如果需要的話） -->
    {% if pagination and pagination.pages > 1 %}
    <div class="pagination">
        {% if pagination.has_prev %}
            <a href="{{ url_for('dashboard', table_name=table_name, page=pagination.prev_num, **request.args) }}" 
               class="btn btn-primary">上一頁</a>
        {% endif %}
        
        {% for page_num in pagination.iter_pages() %}
            {% if page_num %}
                {% if page_num != pagination.page %}
                    <a href="{{ url_for('dashboard', table_name=table_name, page=page_num, **request.args) }}" 
                       class="btn btn-primary">{{ page_num }}</a>
                {% else %}
                    <span class="btn current">{{ page_num }}</span>
                {% endif %}
            {% else %}
                <span class="btn">...</span>
            {% endif %}
        {% endfor %}
        
        {% if pagination.has_next %}
            <a href="{{ url_for('dashboard', table_name=table_name, page=pagination.next_num, **request.args) }}" 
               class="btn btn-primary">下一頁</a>
        {% endif %}
    </div>
    {% endif %}

    <script>
        function sortTable(column) {
            const urlParams = new URLSearchParams(window.location.search);
            const currentSort = urlParams.get('sort');
            const currentOrder = urlParams.get('order');
            
            if (currentSort === column && currentOrder !== 'desc') {
                urlParams.set('order', 'desc');
            } else {
                urlParams.set('order', 'asc');
            }
            
            urlParams.set('sort', column);
            window.location.search = urlParams.toString();
        }
    </script>
</body>
</html>'''

    # 新增記錄模板
    add_record_template = '''<!DOCTYPE html>
<html>
<head>
    <title>新增記錄 - {{ table_name }}</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial; background: #2c3e50; color: white; margin: 0; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .container { max-width: 600px; margin: 0 auto; }
        .btn { padding: 10px 20px; margin: 5px; text-decoration: none; border-radius: 4px; display: inline-block; border: none; cursor: pointer; font-size: 16px; }
        .btn-success { background: #27ae60; color: white; }
        .btn-danger { background: #e74c3c; color: white; }
        .btn-back { background: #95a5a6; color: white; }
        .btn:hover { opacity: 0.8; }
        .form-group { margin-bottom: 20px; }
        .form-label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-input { width: 100%; padding: 10px; border: 1px solid #5a6c7d; background: #34495e; color: white; border-radius: 4px; font-size: 16px; box-sizing: border-box; }
        .form-input:focus { border-color: #3498db; outline: none; }
        .form-actions { margin-top: 30px; text-align: center; }
        .flash { padding: 15px; margin: 15px 0; border-radius: 4px; }
        .success { background: #27ae60; }
        .error { background: #e74c3c; }
        .info { background: #3498db; }
        .warning { background: #f39c12; }
        .required { color: #e74c3c; }
        .field-info { font-size: 12px; color: #bdc3c7; margin-top: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>新增記錄到 {{ table_name }}</h1>
            <div>
                <a href="{{ url_for('dashboard', table_name=table_name) }}" class="btn btn-back">返回</a>
                <a href="{{ url_for('logout') }}" class="btn btn-danger">登出</a>
            </div>
        </div>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash {{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <form method="POST">
            {% for column in columns %}
                {% if column != primary_key %}
                <div class="form-group">
                    <label class="form-label" for="{{ column }}">
                        {{ column }}
                        <span class="required">*</span>
                    </label>
                    <input type="text" 
                           id="{{ column }}" 
                           name="{{ column }}" 
                           class="form-input"
                           value="{{ request.form.get(column, '') }}"
                           placeholder="請輸入 {{ column }}">
                    <div class="field-info">欄位名稱: {{ column }}</div>
                </div>
                {% endif %}
            {% endfor %}

            <div class="form-actions">
                <button type="submit" class="btn btn-success">新增記錄</button>
                <a href="{{ url_for('dashboard', table_name=table_name) }}" class="btn btn-back">取消</a>
            </div>
        </form>
    </div>
</body>
</html>'''

    # 編輯記錄模板
    edit_record_template = '''<!DOCTYPE html>
<html>
<head>
    <title>編輯記錄 - {{ table_name }}</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial; background: #2c3e50; color: white; margin: 0; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .container { max-width: 600px; margin: 0 auto; }
        .btn { padding: 10px 20px; margin: 5px; text-decoration: none; border-radius: 4px; display: inline-block; border: none; cursor: pointer; font-size: 16px; }
        .btn-success { background: #27ae60; color: white; }
        .btn-danger { background: #e74c3c; color: white; }
        .btn-back { background: #95a5a6; color: white; }
        .btn:hover { opacity: 0.8; }
        .form-group { margin-bottom: 20px; }
        .form-label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-input { width: 100%; padding: 10px; border: 1px solid #5a6c7d; background: #34495e; color: white; border-radius: 4px; font-size: 16px; box-sizing: border-box; }
        .form-input:focus { border-color: #3498db; outline: none; }
        .form-input:disabled { background: #2c3e50; color: #bdc3c7; }
        .form-actions { margin-top: 30px; text-align: center; }
        .flash { padding: 15px; margin: 15px 0; border-radius: 4px; }
        .success { background: #27ae60; }
        .error { background: #e74c3c; }
        .info { background: #3498db; }
        .warning { background: #f39c12; }
        .primary-key { color: #f39c12; }
        .field-info { font-size: 12px; color: #bdc3c7; margin-top: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>編輯記錄 - {{ table_name }}</h1>
            <div>
                <a href="{{ url_for('dashboard', table_name=table_name) }}" class="btn btn-back">返回</a>
                <a href="{{ url_for('logout') }}" class="btn btn-danger">登出</a>
            </div>
        </div>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash {{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <form method="POST">
            {% for column in columns %}
            <div class="form-group">
                <label class="form-label" for="{{ column }}">
                    {{ column }}
                    {% if column == primary_key %}
                        <span class="primary-key">(主鍵)</span>
                    {% endif %}
                </label>
                <input type="text" 
                       id="{{ column }}" 
                       name="{{ column }}" 
                       class="form-input"
                       value="{{ record[column] if record[column] is not none else '' }}"
                       {% if column == primary_key %}disabled{% endif %}
                       placeholder="請輸入 {{ column }}">
                <div class="field-info">
                    {% if column == primary_key %}
                        主鍵欄位，無法修改
                    {% else %}
                        欄位名稱: {{ column }}
                    {% endif %}
                </div>
            </div>
            {% endfor %}

            <div class="form-actions">
                <button type="submit" class="btn btn-success">儲存變更</button>
                <a href="{{ url_for('dashboard', table_name=table_name) }}" class="btn btn-back">取消</a>
            </div>
        </form>
    </div>
</body>
</html>'''

    # 保存所有模板
    templates = {
        'table_select.html': table_select_template,
        'dashboard.html': dashboard_template,
        'add_record.html': add_record_template,
        'edit_record.html': edit_record_template
    }

    for filename, content in templates.items():
        with open(os.path.join('templates', filename), 'w', encoding='utf-8') as f:
            f.write(content)

    print("已生成主要管理功能模板:")
    for filename in templates.keys():
        print(f"  - {filename}")

if __name__ == "__main__":
    create_management_templates()