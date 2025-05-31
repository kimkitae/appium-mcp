#!/usr/bin/env python3
import asyncio
import sys
import json
from mcp.server.stdio import stdio_server

from server import create_mcp_server
from logger import error


async def main():
    """메인 함수"""
    try:
        server = create_mcp_server()
        
        # stdio 전송을 통해 서버 실행
        async with stdio_server() as (read_stream, write_stream):
            error("mobile-mcp 서버가 stdio에서 실행 중입니다")
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
            
    except Exception as e:
        error(f"main()에서 치명적 오류 발생: {json.dumps(str(e))}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        error("키보드 인터럽트로 종료됨")
        sys.exit(0)
    except Exception as e:
        print(f"치명적 오류 발생: {e}", file=sys.stderr)
        error(f"치명적 오류 발생: {str(e)}")
        sys.exit(1) 