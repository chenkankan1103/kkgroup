#!/usr/bin/env python3
import traceback
from agent_tools import smart_config_modifier

try:
    result = smart_config_modifier(
        user_command='把現在三種大麻種植的時間縮短一小時',
        affected_system='cannabis',
        caller_id=0
    )
    print(result)
except Exception as e:
    print("错误详情：")
    traceback.print_exc()
