#!/usr/bin/env python3
import argparse
import asyncio
import sys
import json
import os
import secrets

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


def generate_token() -> str:
    """안전한 랜덤 토큰 생성"""
    return secrets.token_urlsafe(32)


async def run_sse(host: str, port: int, token: str | None):
    """SSE 모드로 HTTP 서버 실행 (원격 연결용)"""
    try:
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.responses import JSONResponse, Response
        from starlette.middleware import Middleware
        from starlette.middleware.base import BaseHTTPMiddleware
        import uvicorn
    except ImportError as e:
        print(f"SSE 모드에 필요한 패키지가 없습니다: {e}")
        print("설치: pip install starlette uvicorn")
        sys.exit(1)

    server = create_mcp_server()
    sse = SseServerTransport("/messages/")

    # 토큰 인증 미들웨어
    class TokenAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            # 헬스체크는 인증 없이 허용
            if request.url.path == "/health":
                return await call_next(request)

            # 토큰이 설정된 경우에만 검증
            if token:
                auth_header = request.headers.get("Authorization", "")

                # Bearer 토큰 또는 쿼리 파라미터로 토큰 확인
                token_from_header = None
                if auth_header.startswith("Bearer "):
                    token_from_header = auth_header[7:]

                token_from_query = request.query_params.get("token")

                provided_token = token_from_header or token_from_query

                if not provided_token:
                    return Response(
                        content=json.dumps({"error": "인증 토큰이 필요합니다"}),
                        status_code=401,
                        media_type="application/json"
                    )

                if not secrets.compare_digest(provided_token, token):
                    trace(f"잘못된 토큰 시도: {request.client}")
                    return Response(
                        content=json.dumps({"error": "유효하지 않은 토큰입니다"}),
                        status_code=403,
                        media_type="application/json"
                    )

            return await call_next(request)

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
        return JSONResponse({
            "status": "ok",
            "server": "mobile-mcp",
            "auth_required": token is not None
        })

    # Starlette 앱 설정
    middleware = [Middleware(TokenAuthMiddleware)] if token else []

    app = Starlette(
        debug=False,
        routes=[
            Route("/sse", handle_sse),
            Route("/messages/", handle_messages, methods=["POST"]),
            Route("/health", health),
        ],
        middleware=middleware
    )

    # 토큰 정보 표시
    auth_info = ""
    if token:
        auth_info = f"""
║  Auth Token:    {token}
║
║  인증 방법:
║    1. Header: Authorization: Bearer {token}
║    2. Query:  ?token={token}"""
        masked_token = token[:8] + "..." + token[-4:]
    else:
        auth_info = "║  Auth Token:    없음 (누구나 접속 가능)"
        masked_token = None

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           Mobile MCP Server - SSE Mode                       ║
╠══════════════════════════════════════════════════════════════╣
║  Server URL:    http://{host}:{port}
║  SSE Endpoint:  http://{host}:{port}/sse
║  Messages:      http://{host}:{port}/messages/
║  Health Check:  http://{host}:{port}/health
{auth_info}
╚══════════════════════════════════════════════════════════════╝
""")

    if token:
        print(f"""Claude Desktop 설정 예시 (claude_desktop_config.json):
{{
  "mcpServers": {{
    "mobile-mcp": {{
      "url": "http://{host}:{port}/sse?token={token}"
    }}
  }}
}}

또는 환경변수로 토큰 전달:
{{
  "mcpServers": {{
    "mobile-mcp": {{
      "url": "http://{host}:{port}/sse",
      "headers": {{
        "Authorization": "Bearer {token}"
      }}
    }}
  }}
}}
""")
    else:
        print(f"""Claude Desktop 설정 예시 (claude_desktop_config.json):
{{
  "mcpServers": {{
    "mobile-mcp": {{
      "url": "http://{host}:{port}/sse"
    }}
  }}
}}

⚠️  경고: 토큰 없이 실행 중입니다. --token 옵션으로 인증을 활성화하세요.
""")

    print("Press Ctrl+C to stop the server.\n")

    error(f"mobile-mcp SSE 서버가 {host}:{port}에서 실행 중입니다 (인증: {'활성화' if token else '비활성화'})")

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


async def async_main(mode: str, host: str, port: int, token: str | None):
    """메인 비동기 함수"""
    try:
        if mode == "stdio":
            await run_stdio()
        elif mode == "sse":
            await run_sse(host, port, token)
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

  # 토큰 인증 활성화 (권장)
  mobile-mcp --mode sse --host 0.0.0.0 --port 3000 --token my-secret-token

  # 자동 토큰 생성
  mobile-mcp --mode sse --host 0.0.0.0 --port 3000 --token auto

  # 환경변수로 토큰 설정
  export MOBILE_MCP_TOKEN=my-secret-token
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
        default=51821,
        help="SSE 모드에서 사용할 포트. 기본값: 51821"
    )

    parser.add_argument(
        "--token", "-t",
        default=None,
        help="SSE 모드에서 사용할 인증 토큰. 'auto'로 설정하면 자동 생성. 환경변수 MOBILE_MCP_TOKEN으로도 설정 가능"
    )

    args = parser.parse_args()

    # 토큰 결정: CLI 인자 > 환경변수
    token = args.token or os.environ.get("MOBILE_MCP_TOKEN")

    # 'auto'면 자동 생성
    if token == "auto":
        token = generate_token()
        print(f"자동 생성된 토큰: {token}")

    asyncio.run(async_main(args.mode, args.host, args.port, token))


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
