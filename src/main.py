#!/usr/bin/env python3
import argparse
import asyncio
import sys
import json

from .server import create_mcp_server
from .logger import error, trace


async def run_stdio():
    """stdio 모드로 서버 실행 (로컬 사용)"""
    from mcp.server.stdio import stdio_server

    server = create_mcp_server()

    async with stdio_server() as (read_stream, write_stream):
        error("mobile-mcp 서버가 stdio 모드로 실행 중입니다")
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


async def run_sse(host: str, port: int):
    """SSE 모드로 HTTP 서버 실행 (원격 연결용)"""
    try:
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.responses import JSONResponse
        import uvicorn
    except ImportError as e:
        print(f"SSE 모드에 필요한 패키지가 없습니다: {e}")
        print("설치: pip install starlette uvicorn")
        sys.exit(1)

    server = create_mcp_server()
    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        """SSE 연결 핸들러"""
        trace(f"SSE 연결: {request.client}")
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options()
            )

    async def handle_messages(request):
        """메시지 POST 핸들러"""
        await sse.handle_post_message(request.scope, request.receive, request._send)

    async def health(request):
        """헬스체크"""
        return JSONResponse({"status": "ok", "server": "mobile-mcp"})

    # Starlette 앱 설정
    app = Starlette(
        debug=False,
        routes=[
            Route("/sse", handle_sse),
            Route("/messages/", handle_messages, methods=["POST"]),
            Route("/health", health),
        ]
    )

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           Mobile MCP Server - SSE Mode                       ║
╠══════════════════════════════════════════════════════════════╣
║  Server URL:    http://{host}:{port}
║  SSE Endpoint:  http://{host}:{port}/sse
║  Messages:      http://{host}:{port}/messages/
║  Health Check:  http://{host}:{port}/health
╚══════════════════════════════════════════════════════════════╝

Claude Desktop 설정 예시 (claude_desktop_config.json):
{{
  "mcpServers": {{
    "mobile-mcp": {{
      "url": "http://{host}:{port}/sse"
    }}
  }}
}}

Press Ctrl+C to stop the server.
""")

    error(f"mobile-mcp SSE 서버가 {host}:{port}에서 실행 중입니다")

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


async def async_main(mode: str, host: str, port: int):
    """메인 비동기 함수"""
    try:
        if mode == "stdio":
            await run_stdio()
        elif mode == "sse":
            await run_sse(host, port)
        else:
            error(f"알 수 없는 모드: {mode}")
            sys.exit(1)

    except Exception as e:
        error(f"async_main()에서 치명적 오류 발생: {json.dumps(str(e))}")
        raise


def main() -> None:
    """동기 진입점 함수"""
    parser = argparse.ArgumentParser(
        description="Mobile MCP Server - 모바일 디바이스 제어를 위한 MCP 서버",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 로컬 stdio 모드 (Claude Desktop, Claude Code 등)
  mobile-mcp
  mobile-mcp --mode stdio

  # 원격 SSE 모드 (HTTP 서버)
  mobile-mcp --mode sse
  mobile-mcp --mode sse --host 0.0.0.0 --port 8080

  # Ubuntu 서버에서 실행 (외부 접속 허용)
  mobile-mcp --mode sse --host 0.0.0.0 --port 3000
"""
    )

    parser.add_argument(
        "--mode", "-m",
        choices=["stdio", "sse"],
        default="stdio",
        help="실행 모드: stdio (로컬), sse (원격 HTTP). 기본값: stdio"
    )

    parser.add_argument(
        "--host", "-H",
        default="localhost",
        help="SSE 모드에서 바인딩할 호스트. 기본값: localhost (원격 접속은 0.0.0.0)"
    )

    parser.add_argument(
        "--port", "-p",
        type=int,
        default=3000,
        help="SSE 모드에서 사용할 포트. 기본값: 3000"
    )

    args = parser.parse_args()

    asyncio.run(async_main(args.mode, args.host, args.port))


def run() -> None:
    """Backward compatibility entrypoint"""
    main()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        error("키보드 인터럽트로 종료됨")
        sys.exit(0)
    except Exception as e:
        print(f"치명적 오류 발생: {e}", file=sys.stderr)
        error(f"치명적 오류 발생: {str(e)}")
        sys.exit(1)
