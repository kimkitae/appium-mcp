import os
import sys
from datetime import datetime


def write_log(message: str) -> None:
    """로그 메시지를 파일과 콘솔에 기록합니다."""
    log_file = os.environ.get('LOG_FILE')
    
    if log_file:
        timestamp = datetime.now().isoformat()
        level_str = "INFO"
        log_message = f"[{timestamp}] {level_str} {message}"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_message + "\n")
    
    # stderr로 출력
    print(message, file=sys.stderr)


def trace(message: str) -> None:
    """추적 로그를 기록합니다."""
    write_log(message)


def error(message: str) -> None:
    """오류 로그를 기록합니다."""
    write_log(message) 