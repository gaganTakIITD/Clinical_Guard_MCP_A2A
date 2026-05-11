"""Quick ngrok tunnel launcher for ClinicalGuard."""
import sys
from pyngrok import ngrok, conf

conf.get_default().auth_token = "3DXZ60NgMPbPbtmqHiJNJUUgtQ5_4x6t3dQNGDbJ4qN6bDamX"

try:
    tunnel = ngrok.connect(8001, "http")
    print("=" * 60)
    print(f"  NGROK TUNNEL ACTIVE")
    print(f"  Public URL:  {tunnel.public_url}")
    print(f"  Agent Card:  {tunnel.public_url}/.well-known/agent-card.json")
    print(f"  API Key:     clinicalguard-hackathon-2025")
    print("=" * 60)
    print("\nPaste the Public URL into Prompt Opinion.")
    print("Press Ctrl+C to stop.\n")
    ngrok_process = ngrok.get_ngrok_process()
    ngrok_process.proc.wait()
except KeyboardInterrupt:
    ngrok.kill()
    print("\nTunnel closed.")
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
