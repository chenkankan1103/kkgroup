import base64
import sys

input_file = sys.argv[1] if len(sys.argv) > 1 else '/tmp/user_data.db.b64'
output_file = sys.argv[2] if len(sys.argv) > 2 else '/home/e193752468/kkgroup/user_data.db'

print(f"Reading {input_file}...")
with open(input_file, 'rb') as f:
    data = f.read()
print(f"Read {len(data)} bytes")

print(f"Decoding base64...")
decoded = base64.b64decode(data)
print(f"Decoded to {len(decoded)} bytes")

print(f"Writing {output_file}...")
with open(output_file, 'wb') as f:
    f.write(decoded)
print(f"Done!")