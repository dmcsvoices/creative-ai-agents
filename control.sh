#!/bin/bash

# Poets Generator Control Script for macOS
PLIST_NAME="com.anthonysmusings.poets-clean"
PLIST_FILE="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
SERVICE_DIR="/Volumes/Tikbalang2TB/Volumes/Tikbalang2TB/Users/tikbalang/poets-cron-service"

case "$1" in
    start)
        echo "🚀 Starting Poets Generator service..."
        launchctl load "$PLIST_FILE"
        echo "✅ Service started (runs every 5 minutes)"
        ;;
    stop)
        echo "🛑 Stopping Poets Generator service..."
        launchctl unload "$PLIST_FILE"
        echo "✅ Service stopped"
        ;;
    restart)
        echo "🔄 Restarting Poets Generator service..."
        launchctl unload "$PLIST_FILE" 2>/dev/null || true
        sleep 2
        launchctl load "$PLIST_FILE"
        echo "✅ Service restarted"
        ;;
    status)
        echo "📊 Checking service status..."
        if launchctl list | grep -q "$PLIST_NAME"; then
            echo "✅ Service is running"
            launchctl list "$PLIST_NAME"
        else
            echo "❌ Service is not running"
        fi
        ;;
    run-once)
        echo "▶️  Running service once manually..."
        cd "$SERVICE_DIR"
        python3 poets_cron_service.py poets_cron_config.json
        ;;
    test)
        echo "🧪 Testing service configuration..."
        cd "$SERVICE_DIR"
        python3 poets_cron_service.py --test
        ;;
    logs)
        echo "📄 Showing recent logs..."
        echo "=== SERVICE LOGS ==="
        tail -20 "$SERVICE_DIR/logs/poets_cron.log" 2>/dev/null || echo "No service logs yet"
        echo
        echo "=== LAUNCHD LOGS ==="
        echo "Check Console app or: log show --predicate 'subsystem == \"com.apple.launchd\"' --last 1h"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|run-once|test|logs}"
        echo
        echo "Commands:"
        echo "  start     - Start the automated service (runs every 5 minutes)"
        echo "  stop      - Stop the automated service"
        echo "  restart   - Restart the service"
        echo "  status    - Check if service is running"
        echo "  run-once  - Run the service manually (for testing)"
        echo "  test      - Test configuration and connectivity"
        echo "  logs      - Show recent log output"
        exit 1
        ;;
esac
