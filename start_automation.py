#!/usr/bin/env python3
"""
Appium MCP 자동화 시작 스크립트

이 스크립트는 Appium MCP 서버를 시작하고 자동으로 디바이스에 연결합니다.
"""

import asyncio
import sys
import json
import os
from app import auto_setup, list_available_devices, check_connection_status

async def main():
    """메인 실행 함수"""
    print("🚀 Appium MCP 자동화를 시작합니다...")
    print("=" * 50)
    
    try:
        # 1. 사용 가능한 디바이스 목록 표시
        print("📱 사용 가능한 디바이스를 검색합니다...")
        devices_info = await list_available_devices()
        print(devices_info)
        print()
        
        # 2. 자동 설정 및 연결
        print("🔧 자동 설정을 시작합니다...")
        setup_result = await auto_setup()
        print(f"결과: {setup_result}")
        print()
        
        # 3. 연결 상태 확인
        print("✅ 연결 상태를 확인합니다...")
        status = await check_connection_status()
        print(status)
        print()
        
        print("🎉 자동화 설정이 완료되었습니다!")
        print("이제 MCP 클라이언트에서 도구들을 사용할 수 있습니다.")
        
    except Exception as e:
        print(f"❌ 오류가 발생했습니다: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 