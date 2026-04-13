#!/bin/bash
# ============================================================
# Digital WBS 대시보드 - 서버 시작 스크립트
# 사용법: ./startup.sh [--port PORT]
# ============================================================

set -e

# ----- 기본 설정 -----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/.server.pid"
LOG_FILE="$SCRIPT_DIR/.server.log"
DEFAULT_PORT=8000

# ----- 인자 파싱 -----
PORT="$DEFAULT_PORT"

while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            PORT="$2"
            shift 2
            ;;
        -h|--help)
            echo "사용법: ./startup.sh [옵션]"
            echo ""
            echo "옵션:"
            echo "  --port PORT    포트 번호 (기본값: $DEFAULT_PORT)"
            echo "  -h, --help     도움말"
            echo ""
            echo "WBS 대시보드 (dashboard.html)를 로컬 HTTP 서버로 서빙합니다."
            exit 0
            ;;
        *)
            echo "❌ 알 수 없는 옵션: $1"
            exit 1
            ;;
    esac
done

# ----- 이미 실행 중인지 확인 -----
if [[ -f "$PID_FILE" ]]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "⚠️  서버가 이미 실행 중입니다 (PID: $OLD_PID)"
        echo "   종료 후 다시 시작하려면: ./stop.sh && ./startup.sh"
        exit 1
    else
        echo "🧹 이전 PID 파일 정리 중..."
        rm -f "$PID_FILE"
    fi
fi

# ----- python3 확인 -----
if ! command -v python3 &>/dev/null; then
    echo "❌ python3가 설치되어 있지 않습니다."
    exit 1
fi

# ----- 서버 시작 -----
echo "============================================================"
echo "🚀 Digital WBS 대시보드 시작"
echo "============================================================"
echo "   포트:       $PORT"
echo "   대시보드:   http://localhost:$PORT/dashboard.html"
echo "   로그:       $LOG_FILE"
echo "============================================================"

cd "$SCRIPT_DIR"

nohup python3 -m http.server "$PORT" --bind 0.0.0.0 \
    >> "$LOG_FILE" 2>&1 &

SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

# 서버가 정상적으로 시작되었는지 확인 (최대 5초 대기)
echo -n "⏳ 서버 시작 확인 중"
for i in {1..10}; do
    sleep 0.5
    echo -n "."
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo ""
        echo "❌ 서버 시작 실패! 로그를 확인하세요:"
        tail -20 "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
    # HTTP 응답 확인
    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/dashboard.html" 2>/dev/null | grep -q "200"; then
        echo ""
        echo "✅ 서버가 성공적으로 시작되었습니다! (PID: $SERVER_PID)"
        echo ""
        echo "   🌐 대시보드: http://localhost:$PORT/dashboard.html"
        exit 0
    fi
done

echo ""
if kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "✅ 서버 프로세스 시작됨 (PID: $SERVER_PID)"
    echo ""
    echo "   🌐 대시보드: http://localhost:$PORT/dashboard.html"
else
    echo "❌ 서버 시작 실패! 로그를 확인하세요:"
    tail -20 "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
