from importlib import import_module
from pathlib import Path
import inspect

async def setup_commands(tree, client):
    # 自動探測 commands 目錄下的所有 .py 檔案
    commands_dir = Path(__file__).parent
    module_files = [f.stem for f in commands_dir.glob("*.py") 
                   if f.is_file() and f.stem != "__init__"]
    
    for module_name in module_files:
        # 跳過特定檔案如果需要
        if module_name in ["__pycache__"]:
            continue
        
        try:
            # 動態導入模組
            module = import_module(f"commands.{module_name}")
            
            # 尋找並呼叫 setup_* 函數
            setup_func_name = f"setup_{module_name}"
            if hasattr(module, setup_func_name):
                setup_func = getattr(module, setup_func_name)
                if inspect.iscoroutinefunction(setup_func):
                    await setup_func(tree, client)
                    print(f"✅ 模組 {module_name} 載入成功")
                else:
                    print(f"⚠️ 警告: {module_name} 的 {setup_func_name} 函數不是異步函數")
            else:
                print(f"⚠️ 警告: 模組 {module_name} 缺少 {setup_func_name} 函數")
        except Exception as e:
            print(f"❌ 模組 {module_name} 載入失敗: {str(e)}")