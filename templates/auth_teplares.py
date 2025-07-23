import os

def create_auth_templates():
    """創建登入認證相關的模板"""
    
    if not os.path.exists('templates'):
        os.makedirs('templates')

    # 登入頁面模板
    login_template = '''<!DOCTYPE html>
<html>
<head>
    <title>資料庫管理系統 - 登入</title>
    <meta charset="utf-8">
    <style>
        body {
            font-family: 'Arial', 'Microsoft JhengHei', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 0;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.1);
            width: 100%;
            max-width: 400px;
            text-align: center;
        }
        .login-header {
            margin-bottom: 30px;
        }
        .login-header h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
            font-weight: 300;
        }
        .login-header p {
            color: #666;
            margin: 0;
        }
        .form-group {
            margin-bottom: 20px;
            text-align: left;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: #555;
            font-weight: 500;
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 12px;
            border: 2px solid #e1e1e1;
            border-radius: 5px;
            font-size: 16px;
            transition: border-color 0.3s;
            box-sizing: border-box;
        }
        input[type="text"]:focus, input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
        }
        .btn-login {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .btn-login:hover {
            transform: translateY(-2px);
        }
        .flash-messages {
            margin-bottom: 20px;
        }
        .flash {
            padding: 10px;
            margin-bottom: 10px;
            border-radius: 5px;
            text-align: center;
        }
        .flash.error {
            background-color: #fee;
            color: #c33;
            border: 1px solid #fcc;
        }
        .flash.success {
            background-color: #efe;
            color: #363;
            border: 1px solid #cfc;
        }
        .flash.info {
            background-color: #eef;
            color: #336;
            border: 1px solid #ccf;
        }
        .login-footer {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 14px;
            color: #888;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <h1>資料庫管理系統</h1>
            <p>請輸入您的登入資訊</p>
        </div>
        
        <div class="flash-messages">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="flash {{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
        </div>
        
        <form method="POST">
            <div class="form-group">
                <label for="username">使用者名稱</label>
                <input type="text" id="username" name="username" required 
                       value="{{ request.form.username if request.form.username else '' }}">
            </div>
            
            <div class="form-group">
                <label for="password">密碼</label>
                <input type="password" id="password" name="password" required>
            </div>
            
            <button type="submit" class="btn-login">登入</button>
        </form>
        
        <div class="login-footer">
            <p>請聯絡系統管理員取得帳號</p>
        </div>
    </div>
</body>
</html>'''

    # 保存登入模板
    with open(os.path.join('templates', 'login.html'), 'w', encoding='utf-8') as f:
        f.write(login_template)
    
    print("✅ 已生成登入認證模板")

if __name__ == "__main__":
    create_auth_templates()