#!/bin/bash
sqlite3 /home/e193752468/kkgroup/user_data.db << EOF
.mode list
SELECT name FROM sqlite_master WHERE type='table';
EOF
