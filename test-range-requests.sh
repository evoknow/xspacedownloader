#!/bin/bash

echo "=== Testing Range Requests ==="

echo -e "\n1. Test full file request:"
curl -I https://xspacedownload.com/audio/1lDxLnrWjwkGm.mp3

echo -e "\n2. Test range request (what the browser does when seeking):"
curl -I -H "Range: bytes=0-1023" https://xspacedownload.com/audio/1lDxLnrWjwkGm.mp3

echo -e "\n3. Test another range:"
curl -I -H "Range: bytes=1048576-2097151" https://xspacedownload.com/audio/1lDxLnrWjwkGm.mp3

echo -e "\n4. Test open-ended range:"
curl -I -H "Range: bytes=1048576-" https://xspacedownload.com/audio/1lDxLnrWjwkGm.mp3

echo -e "\n=== Expected Results ==="
echo "Full file: HTTP/1.1 200 OK"
echo "Range requests: HTTP/1.1 206 Partial Content"
echo "Should include: Content-Range: bytes start-end/total"