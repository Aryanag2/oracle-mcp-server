#!/usr/bin/env python3
"""
Simple alternative to MCP Inspector - just tests your tools directly
"""
import os
import subprocess
import json
import time

def test_oracle_mcp_server():
    """Test your Oracle MCP server with simple commands"""
    
    print("🔍 SIMPLE MCP SERVER TESTER")
    print("=" * 40)
    
    # Set environment variables
    connection_string = 'ADMIN/ADS_Database_12345@(description= (retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1522)(host=adb.us-ashburn-1.oraclecloud.com))(connect_data=(service_name=q9tjyjeyzhxqwla_dmcherka23ai_high.adb.oraclecloud.com))(security=(ssl_server_dn_match=yes)))'
    
    os.environ['ORACLE_CONNECTION_STRING'] = connection_string
    os.environ['TARGET_SCHEMA'] = 'ADMIN'
    os.environ['CACHE_DIR'] = '.cache'
    
    print("✅ Environment variables set")

    # Start the server process
    print("🚀 Starting MCP server...")
    server_script = os.getenv("MCP_SERVER_PATH", "server/main.py")
    server_dir = os.path.dirname(server_script)
    script_name = os.path.basename(server_script)
    process = subprocess.Popen(
        ['uv', 'run', script_name],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=server_dir
    )
    
    # Wait for initialization
    print("⏳ Waiting 8 seconds for server initialization...")
    time.sleep(8)
    
    # Test sequence
    tests = [
        {
            "name": "Initialize Server",
            "request": {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"roots": {"listChanged": True}},
                    "clientInfo": {"name": "simple-tester", "version": "1.0.0"}
                }
            }
        },
        {
            "name": "List Tools",
            "request": {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            }
        },
        {
            "name": "Get Database Info",
            "request": {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "get_database_info",
                    "arguments": {}
                }
            }
        },
        {
            "name": "Search for Tables",
            "request": {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "search_tables_by_name",
                    "arguments": {"name_pattern": "USER"}
                }
            }
        }
    ]
    
    for test in tests:
        print(f"\n📋 {test['name']}")
        print("-" * 20)
        
        # Send request
        request_json = json.dumps(test['request'])
        print(f"📤 Sending: {request_json}")
        
        try:
            process.stdin.write(request_json + '\n')
            process.stdin.flush()
            
            # Wait for response
            print("⏳ Waiting for response...")
            response = process.stdout.readline()
            
            if response.strip():
                try:
                    response_obj = json.loads(response.strip())
                    print(f"�� Response: {json.dumps(response_obj, indent=2)}")
                except json.JSONDecodeError:
                    print(f"📥 Raw response: {response.strip()}")
            else:
                print("❌ No response received")
                
        except Exception as e:
            print(f"❌ Error: {e}")
        
        time.sleep(2)  # Wait between requests
    
    print(f"\n🛑 Cleaning up...")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    
    print("✅ Test completed!")

def quick_connection_test():
    """Just test if we can connect to the database"""
    print("🔌 QUICK CONNECTION TEST")
    print("=" * 25)
    
    try:
        # Test with a simple Python script
        test_script = '''
import oracledb
import os

connection_string = "ADMIN/ADS_Database_12345@(description= (retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1522)(host=adb.us-ashburn-1.oraclecloud.com))(connect_data=(service_name=q9tjyjeyzhxqwla_dmcherka23ai_high.adb.oraclecloud.com))(security=(ssl_server_dn_match=yes)))"

try:
    conn = oracledb.connect(connection_string)
    print(f"✅ Connected! Database version: {conn.version}")
    
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM user_tables")
    table_count = cursor.fetchone()[0]
    print(f"📊 Found {table_count} tables in your schema")
    
    cursor.execute("SELECT table_name FROM user_tables WHERE ROWNUM <= 5")
    tables = cursor.fetchall()
    print("📋 Sample tables:")
    for table in tables:
        print(f"   • {table[0]}")
    
    conn.close()
    print("✅ Connection test successful!")
    
except Exception as e:
    print(f"❌ Connection failed: {e}")
'''
        
        # Write and run the test script
        with open('/tmp/oracle_test.py', 'w') as f:
            f.write(test_script)
        
        result = subprocess.run(['python3', '/tmp/oracle_test.py'], 
                              capture_output=True, text=True, 
                              cwd='/Users/aryangosaliya/Desktop/oracle-mcp-server')
        
        print(result.stdout)
        if result.stderr:
            print(f"⚠️  Errors: {result.stderr}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

def main():
    print("🔧 SIMPLE MCP TESTING TOOL")
    print("=" * 30)
    print("Choose a test:")
    print("1. Quick connection test (just check if database works)")
    print("2. Full MCP server test (test all the JSON-RPC communication)")
    print("3. Both")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        quick_connection_test()
    elif choice == "2":
        test_oracle_mcp_server()
    elif choice == "3":
        quick_connection_test()
        print("\n" + "="*50 + "\n")
        test_oracle_mcp_server()
    else:
        print("Invalid choice")

if __name__ == "__main__":
    main()
