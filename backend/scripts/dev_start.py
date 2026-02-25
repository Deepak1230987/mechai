"""
Development startup helper.
Launches all services in separate processes for local development.

Usage:
  cd backend
  python -m scripts.dev_start
"""

import subprocess
import sys
import os
import signal

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

processes = []


def start_service(name: str, module: str, port: int | None = None):
    if port:
        cmd = [
            sys.executable, "-m", "uvicorn",
            f"{module}:app",
            "--host", "0.0.0.0",
            "--port", str(port),
            "--reload",
        ]
    else:
        # Worker — no HTTP server
        cmd = [sys.executable, "-m", module]

    print(f"Starting {name}...")
    proc = subprocess.Popen(cmd, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    processes.append((name, proc))
    return proc


def shutdown(signum=None, frame=None):
    print("\nShutting down all services...")
    for name, proc in processes:
        print(f"  Stopping {name} (PID {proc.pid})...")
        proc.terminate()
    for _, proc in processes:
        proc.wait(timeout=5)
    print("All services stopped.")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("=" * 60)
    print("  AI-CAM-RFQ Platform — Development Mode")
    print("=" * 60)

    start_service("API Gateway",  "api_gateway.main", port=8000)
    start_service("Auth Service", "auth_service.main", port=8001)
    start_service("CAD Service",  "cad_service.main", port=8002)
    start_service("CAD Worker",   "cad_worker.main")
    start_service("AI Service",   "ai_service.main", port=8003)

    print()
    print("Services running:")
    print("  API Gateway  → http://localhost:8000  (docs: http://localhost:8000/docs)")
    print("  Auth Service → http://localhost:8001  (docs: http://localhost:8001/docs)")
    print("  CAD Service  → http://localhost:8002  (docs: http://localhost:8002/docs)")
    print("  AI Service   → http://localhost:8003  (docs: http://localhost:8003/docs)")
    print("  CAD Worker   → background process (polling DB)")
    print()
    print("Press Ctrl+C to stop all services.")
    print("=" * 60)

    try:
        for _, proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        shutdown()
